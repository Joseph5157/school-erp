"""refresh_demo_school keeps the staging demo school's data current."""

import datetime
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from core import demo_refresh
from core.models import (
    AcademicYear,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
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
