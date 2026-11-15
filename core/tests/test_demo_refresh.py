"""refresh_demo_school keeps the staging demo school's data current."""

import datetime
import io
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core import announcements, demo_refresh
from core.models import (
    AcademicYear,
    Announcement,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ResultStatus,
    SchoolCalendarDay,
    Section,
    SectionClassTeacher,
    business_today,
)


def last_instructional_day(year, on_or_before):
    day = on_or_before
    while not year.is_instructional_day(day):
        day -= datetime.timedelta(days=1)
    return day


def seed_demo_school():
    creds = Path(tempfile.mkdtemp()) / "creds.csv"
    call_command("seed_school_demo", credentials_file=str(creds), allow_non_debug=True,
                 verbosity=0)
    call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)
    call_command("seed_school_demo_extras", allow_non_debug=True, verbosity=0)


class GuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()

    def test_refuses_without_env_flag(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": ""}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_refuses_without_demo_admin(self):
        get_user_model().objects.filter(username="demo_admin").update(username="someone_else")
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_out_of_season(self):
        year = AcademicYear.objects.get()
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(demo_refresh.NotInSeason):
                demo_refresh.check_guard(year.end_date + datetime.timedelta(days=1))

    def test_passes_and_returns_admin_and_year(self):
        year = AcademicYear.objects.get()
        today = last_instructional_day(year, business_today())
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            admin, found = demo_refresh.check_guard(today)
        self.assertEqual(admin.username, "demo_admin")
        self.assertEqual(found, year)


class RealismTests(SimpleTestCase):
    def test_deterministic(self):
        d = datetime.date(2026, 11, 2)
        self.assertEqual(demo_refresh.is_absent(5, 1, d), demo_refresh.is_absent(5, 1, d))

    def test_rates_are_believable(self):
        days = [datetime.date(2026, 7, 1) + datetime.timedelta(days=i) for i in range(120)]
        rates = [sum(demo_refresh.is_absent(s, 1, d) for d in days) / len(days)
                 for s in range(1, 111)]
        self.assertTrue(0.02 <= sum(rates) / len(rates) <= 0.08)
        self.assertGreaterEqual(sum(r >= 0.09 for r in rates), 3)
        self.assertLess(max(rates), 0.25)

    def test_note_never_empty(self):
        self.assertTrue(all(demo_refresh.absence_note(s, datetime.date(2026, 8, d))
                            for s in range(50) for d in range(1, 29)))


class AttendanceRefreshTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()
        cls.year = AcademicYear.objects.get()
        cls.admin = get_user_model().objects.get(username="demo_admin")
        # Well before the seeded window so nothing exists there yet.
        cls.today = last_instructional_day(
            cls.year, cls.year.start_date + datetime.timedelta(days=40)
        )
        cls.since = cls.today - datetime.timedelta(days=21)

    def _range_days(self):
        day, days = self.since, []
        while day < self.today:
            days.append(day)
            day += datetime.timedelta(days=1)
        return days

    def _draft(self, section, day):
        register = AttendanceRegister(
            academic_year=self.year, class_grade=section.class_grade, section=section, date=day
        )
        register.full_clean()
        register.save()
        return register

    def test_skips_old_drafts_with_an_empty_roster(self):
        class_grade = Section.objects.select_related("class_grade").first().class_grade
        empty = Section.objects.create(class_grade=class_grade, name="Empty")
        day = last_instructional_day(self.year, self.today - datetime.timedelta(days=1))
        register = self._draft(empty, day)
        self.assertFalse(register.eligible_enrollments().exists())
        self.assertEqual(demo_refresh.finish_old_drafts(self.year, self.today, self.admin), 0)
        register.refresh_from_db()
        self.assertEqual(register.status, "DRAFT")

    def test_finishes_old_drafts_without_losing_entries(self):
        section = Section.objects.select_related("class_grade").first()
        day = last_instructional_day(self.year, self.today - datetime.timedelta(days=1))
        register = self._draft(section, day)
        first = register.eligible_enrollments().first()
        register.capture(enrollment=first, status=AttendanceStatus.ABSENT, absence_note="Fever")
        self.assertEqual(demo_refresh.finish_old_drafts(self.year, self.today, self.admin), 1)
        register.refresh_from_db()
        self.assertEqual(register.status, "SUBMITTED")
        self.assertEqual(register.entries.count(), register.eligible_enrollments().count())
        entry = register.entries.get(academic_enrollment=first)
        self.assertEqual((entry.status, entry.absence_note), ("ABSENT", "Fever"))

    def test_backfill_fills_every_section_every_instructional_day(self):
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        days = [d for d in self._range_days() if self.year.is_instructional_day(d)]
        self.assertTrue(days)
        for day in days:
            self.assertEqual(
                AttendanceRegister.objects.filter(date=day, status="SUBMITTED").count(),
                Section.objects.count(),
            )

    def test_backfill_skips_non_instructional_days(self):
        weekday = next(d for d in self._range_days() if self.year.is_instructional_day(d))
        holiday = SchoolCalendarDay(
            academic_year=self.year, date=weekday, is_instructional=False, label="Demo holiday"
        )
        holiday.full_clean()
        holiday.save()
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        skipped = [d for d in self._range_days() if not self.year.is_instructional_day(d)]
        self.assertIn(weekday, skipped)
        self.assertTrue(any(d.weekday() >= 5 for d in skipped))
        self.assertFalse(AttendanceRegister.objects.filter(date__in=skipped).exists())

    def test_backfill_is_idempotent(self):
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        self.assertEqual(
            demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since),
            0,
        )

    def test_submitter_is_class_teacher(self):
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        day = last_instructional_day(self.year, self.today - datetime.timedelta(days=1))
        checked = 0
        for assignment in SectionClassTeacher.objects.effective_on(day).select_related("teacher"):
            register = AttendanceRegister.objects.get(section=assignment.section, date=day)
            self.assertEqual(register.submitted_by, assignment.teacher)
            checked += 1
        self.assertTrue(checked)

    def test_submitter_falls_back_to_demo_admin(self):
        day = last_instructional_day(self.year, self.today - datetime.timedelta(days=1))
        assignment = SectionClassTeacher.objects.effective_on(day).first()
        assignment.end(day - datetime.timedelta(days=1))  # no class teacher from `day` on
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        register = AttendanceRegister.objects.get(section=assignment.section, date=day)
        self.assertEqual(register.submitted_by, self.admin)

    def test_absent_entries_have_notes(self):
        demo_refresh.backfill_attendance(self.year, self.today, self.admin, since=self.since)
        absent = AttendanceEntry.objects.filter(
            register__date__in=self._range_days(), status="ABSENT"
        )
        self.assertTrue(absent.exists())
        self.assertFalse(absent.filter(absence_note="").exists())

    def _demo_sections(self):
        return SectionClassTeacher.objects.effective_on(self.today).filter(
            teacher__username=demo_refresh.DEMO_TEACHER_USERNAME
        ).values_list("section_id", flat=True)

    def test_today_keeps_demo_teacher_sections_open(self):
        demo_refresh.prepare_today(self.year, self.today, self.admin)
        mine = set(self._demo_sections())
        self.assertTrue(mine)
        for section in Section.objects.all():
            register = AttendanceRegister.objects.filter(
                section=section, date=self.today
            ).first()
            if section.pk in mine:
                self.assertTrue(register is None or register.status == "DRAFT")
            else:
                self.assertEqual(register.status, "SUBMITTED")

    def test_today_leaves_started_register_alone(self):
        mine = set(self._demo_sections())
        section = Section.objects.select_related("class_grade").exclude(pk__in=mine).first()
        register = self._draft(section, self.today)
        register.capture(enrollment=register.eligible_enrollments().first(),
                         status=AttendanceStatus.PRESENT)
        demo_refresh.prepare_today(self.year, self.today, self.admin)
        register.refresh_from_db()
        self.assertEqual(register.status, "DRAFT")
        self.assertEqual(register.entries.count(), 1)

    def test_today_skipped_when_not_instructional(self):
        day = self.today
        while self.year.is_instructional_day(day):
            day -= datetime.timedelta(days=1)
        self.assertEqual(demo_refresh.prepare_today(self.year, day, self.admin), 0)


class OpenAssessmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()
        cls.year = AcademicYear.objects.get()
        cls.admin = get_user_model().objects.get(username="demo_admin")
        cls.today = last_instructional_day(cls.year, business_today())
        cls.term = demo_refresh.current_term(cls.year, cls.today)

    def test_current_term_found(self):
        self.assertIsNotNone(self.term)
        self.assertTrue(self.term.start_date <= self.today <= self.term.end_date)

    def test_current_term_none_outside_terms(self):
        self.assertIsNone(
            demo_refresh.current_term(self.year, self.year.end_date + datetime.timedelta(days=5))
        )

    def _first_number(self):
        # Term 1 holds a finalized "Unit Test 1"; later terms start at 1.
        return 2 if self.term.display_order == 1 else 1

    def test_creates_one_open_unit_test_per_assignment(self):
        n = demo_refresh.ensure_open_assessments(self.year, self.today)
        self.assertEqual(n, AssessmentTeacherAssignment.objects.count())
        a = Assessment.objects.filter(term=self.term, status=Assessment.Status.DRAFT).first()
        self.assertEqual(
            (a.name, a.maximum_marks, a.pass_mark),
            (f"Unit Test {self._first_number()}", Decimal(25), Decimal(9)),
        )
        self.assertLessEqual(a.assessment_date, self.today)
        self.assertGreaterEqual(a.assessment_date, self.term.start_date)
        self.assertLess(a.assessment_date.weekday(), 5)

    def test_reuses_existing_open_assessment(self):
        demo_refresh.ensure_open_assessments(self.year, self.today)
        self.assertEqual(demo_refresh.ensure_open_assessments(self.year, self.today), 0)

    def test_next_number_after_finalized(self):
        demo_refresh.ensure_open_assessments(self.year, self.today)
        assignment = AssessmentTeacherAssignment.objects.select_related("teacher").first()
        first = Assessment.objects.get(
            term=self.term, offering=assignment.offering, section=assignment.section,
            status=Assessment.Status.DRAFT,
        )
        for enrollment in first.roster():
            first.save_draft_result(
                enrollment=enrollment, status=ResultStatus.MARKED, score=Decimal(15),
                actor=assignment.teacher,
            )
        first.finalize(actor=self.admin)
        self.assertEqual(demo_refresh.ensure_open_assessments(self.year, self.today), 1)
        nxt = Assessment.objects.get(
            term=self.term, offering=assignment.offering, section=assignment.section,
            status=Assessment.Status.DRAFT,
        )
        self.assertEqual(nxt.name, f"Unit Test {self._first_number() + 1}")

    def test_no_current_term_skips(self):
        with mock.patch.object(demo_refresh, "current_term", return_value=None):
            self.assertEqual(demo_refresh.ensure_open_assessments(self.year, self.today), 0)
        self.assertFalse(Assessment.objects.filter(status=Assessment.Status.DRAFT).exists())


class NoticeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()
        cls.admin = get_user_model().objects.get(username="demo_admin")

    def _newest(self):
        return Announcement.objects.filter(withdrawn_at__isnull=True).latest("published_at")

    def test_pool_is_eight_ascii(self):
        self.assertEqual(len(demo_refresh.NOTICE_POOL), 8)
        for title, body in demo_refresh.NOTICE_POOL:
            self.assertTrue(title.isascii() and body.isascii())

    def test_notice_posted_when_stale(self):
        now = self._newest().published_at + datetime.timedelta(days=8)
        a = demo_refresh.post_notice_if_stale(self.admin, now)
        self.assertEqual(a.audience, Announcement.Audience.ALL)
        self.assertIn(a.title, [t for t, _ in demo_refresh.NOTICE_POOL])

    def test_no_notice_when_recent(self):
        now = self._newest().published_at + datetime.timedelta(days=3)
        self.assertIsNone(demo_refresh.post_notice_if_stale(self.admin, now))

    def test_posted_when_all_withdrawn(self):
        for notice in Announcement.objects.all():
            announcements.withdraw(notice, actor=self.admin, reason="Demo reset")
        a = demo_refresh.post_notice_if_stale(self.admin, datetime.datetime.now(datetime.timezone.utc))
        self.assertEqual(a.title, demo_refresh.NOTICE_POOL[0][0])

    def test_pool_cycles(self):
        titles = [t for t, _ in demo_refresh.NOTICE_POOL]
        first = demo_refresh.post_notice_if_stale(
            self.admin, self._newest().published_at + datetime.timedelta(days=8)
        )
        second = demo_refresh.post_notice_if_stale(
            self.admin, first.published_at + datetime.timedelta(days=8)
        )
        self.assertNotEqual(first.title, second.title)
        self.assertEqual(
            titles.index(second.title), (titles.index(first.title) + 1) % len(titles)
        )


class RefreshCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_demo_school()
        cls.year = AcademicYear.objects.get()

    def test_command_refuses_without_flag(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": ""}):
            with self.assertRaises(CommandError):
                call_command("refresh_demo_school", stdout=io.StringIO())

    def test_command_runs_and_is_idempotent(self):
        today = last_instructional_day(self.year, business_today())
        since = str(today - datetime.timedelta(days=14))
        initial = (AttendanceRegister.objects.count(), Assessment.objects.count())
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            call_command("refresh_demo_school", since=since, stdout=io.StringIO())
            after_first = (AttendanceRegister.objects.count(), Assessment.objects.count())
            self.assertTrue(
                after_first[0] > initial[0] or after_first[1] > initial[1],
                "first run created nothing",
            )
            counts = (AttendanceRegister.objects.count(), Assessment.objects.count(),
                      Announcement.objects.count())
            call_command("refresh_demo_school", since=since, stdout=io.StringIO())
        self.assertEqual(counts, (AttendanceRegister.objects.count(),
                                  Assessment.objects.count(), Announcement.objects.count()))

    def test_step_failure_does_not_stop_others(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}), \
             mock.patch.object(demo_refresh, "backfill_attendance",
                               side_effect=RuntimeError("boom")):
            out = io.StringIO()
            with self.assertRaisesMessage(CommandError, "backfill"):
                call_command("refresh_demo_school", stdout=out, stderr=io.StringIO())
        for line in ("today: ", "assessments: ", "notice: "):
            self.assertIn(line, out.getvalue())
        self.assertNotIn("backfill: ", out.getvalue())
        self.assertTrue(Assessment.objects.filter(status="DRAFT").exists())

    def test_out_of_season_exits_cleanly(self):
        end = self.year.end_date
        before = (AttendanceRegister.objects.count(), Assessment.objects.count(),
                  Announcement.objects.count())
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}), \
             mock.patch("core.management.commands.refresh_demo_school.business_today",
                        return_value=end + datetime.timedelta(days=1)):
            out = io.StringIO()
            call_command("refresh_demo_school", stdout=out)
        self.assertIn("outside", out.getvalue())
        self.assertEqual(before, (AttendanceRegister.objects.count(),
                                  Assessment.objects.count(), Announcement.objects.count()))
