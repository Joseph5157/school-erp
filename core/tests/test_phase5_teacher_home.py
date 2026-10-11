"""Phase 5 Gate 2: teacher home page and landing (ADR 0011 D11)."""

from datetime import date
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    AttendanceRegister,
    ResultStatus,
    SectionClassTeacher,
    TermRemark,
)
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)
SUNDAY = date(2026, 10, 11)


def on(day):
    return mock.patch.multiple(
        "core.views", business_today=lambda: day
    ), mock.patch("core.models.business_today", new=lambda: day)


class TeacherHomeFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-home")
        self.patches = on(MONDAY)
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def class_teacher(self, teacher, section, start=date(2026, 6, 1)):
        return SectionClassTeacher.assign(
            teacher=teacher, academic_year=self.year, section=section, start_date=start
        )


class LandingTests(TeacherHomeFixture, TestCase):
    def test_teacher_lands_on_my_day_after_login(self):
        client = self.client_class()
        response = client.post(reverse("login"), {"username": "rao", "password": "pass-12345"},
                               follow=True)
        self.assertEqual(response.redirect_chain[-1][0], self.url)

    def test_administrator_lands_on_school(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertRedirects(self.client.get(reverse("home")), reverse("core:school-detail"),
                             fetch_redirect_response=False)

    def test_teacher_with_admin_rights_chooses_an_area(self):
        # Phase 6 (ADR 0013): a login with several areas chooses explicitly.
        self.rao.groups.add(self.admins)
        self.assertRedirects(self.teacher.get(reverse("home")), reverse("choose-area"),
                             fetch_redirect_response=False)

    def test_anonymous_home_requires_login(self):
        response = self.client_class().get(reverse("home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_only_teachers_may_open_my_day(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.make_user("plain")
        plain = self.client_class()
        plain.login(username="plain", password="pass-12345")
        self.assertEqual(plain.get(self.url).status_code, 403)
        self.assertEqual(self.teacher.get(self.url).status_code, 200)

    def test_nav_shows_my_day_to_teachers(self):
        self.assertContains(self.teacher.get(self.url), 'href="/my/"')


class AttendancePanelTests(TeacherHomeFixture, TestCase):
    def state(self):
        rows = self.teacher.get(self.url).context["attendance"]
        return [(row["duty"].section, row["state"]) for row in rows]

    def test_not_a_class_teacher(self):
        response = self.teacher.get(self.url)
        self.assertContains(response, "You are not a class teacher today.")

    def test_states_follow_todays_register(self):
        self.make_student("Asha")
        self.class_teacher(self.rao, self.six_a)
        self.assertEqual(self.state(), [(self.six_a, "NOT_TAKEN")])
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY
        )
        self.assertEqual(self.state(), [(self.six_a, "DRAFT")])
        AttendanceRegister.objects.filter(pk=register.pk).update(
            status="SUBMITTED", submitted_by=self.admin, submitted_at="2026-10-12T09:00:00Z"
        )
        self.assertEqual(self.state(), [(self.six_a, "SUBMITTED")])

    def test_non_instructional_day(self):
        self.class_teacher(self.rao, self.six_a)
        for patch in on(SUNDAY):
            patch.start()
            self.addCleanup(patch.stop)
        self.assertEqual(self.state(), [(self.six_a, "NOT_INSTRUCTIONAL")])

    def test_handed_over_section_disappears(self):
        self.class_teacher(self.rao, self.six_a)
        self.class_teacher(self.iyer, self.six_a, start=MONDAY)
        self.assertEqual(self.state(), [])

    def test_lost_teacher_status_means_no_access(self):
        self.class_teacher(self.rao, self.six_a)
        self.rao.groups.remove(self.teachers)
        self.assertEqual(self.teacher.get(self.url).status_code, 403)


class MarksPanelTests(TeacherHomeFixture, TestCase):
    def test_lists_open_drafts_with_unmarked_students_only(self):
        self.assign(self.rao, self.maths, self.six_a)
        _, asha = self.make_student("Asha")
        _, ravi = self.make_student("Ravi")
        open_one = self.make_assessment(name="UT1", on=date(2026, 7, 15))
        done = self.make_assessment(name="UT2", on=date(2026, 8, 1))
        self.make_assessment(name="Future", on=date(2026, 11, 1), term=self.term2)
        finalized = self.make_assessment(name="Old", on=date(2026, 7, 1))
        self.force_finalize(finalized)
        for enrollment in (asha, ravi):
            done.save_draft_result(enrollment=enrollment, status=ResultStatus.ABSENT,
                                   actor=self.rao)
        open_one.save_draft_result(enrollment=asha, status=ResultStatus.MARKED, score="5",
                                   actor=self.rao)
        rows = self.teacher.get(self.url).context["assessments"]
        self.assertEqual([(a.name, a.unmarked_count) for a in rows], [("UT1", 1)])

    def test_other_teachers_assessments_are_hidden(self):
        self.assign(self.iyer, self.maths, self.six_a)
        self.make_student("Asha")
        self.make_assessment()
        self.assertEqual(self.teacher.get(self.url).context["assessments"], [])


class RemarksPanelTests(TeacherHomeFixture, TestCase):
    def test_counts_written_remarks_for_started_terms(self):
        self.class_teacher(self.rao, self.six_a)
        asha, _ = self.make_student("Asha")
        self.make_student("Ravi")
        TermRemark.objects.create(term=self.term1, student=asha, remark="Good",
                                  written_by=self.rao)
        rows = self.teacher.get(self.url).context["remarks"]
        self.assertEqual(
            [(r["term"], r["expected"], r["written"]) for r in rows],
            [(self.term1, 2, 1), (self.term2, 2, 0)],
        )

    def test_bulk_roster_matches_section_roster_after_transfer(self):
        asha, _ = self.make_student("Asha")
        self.make_student("Ravi", section=self.six_b)
        asha.enroll(academic_year=self.year, class_grade=self.grade6, section=self.six_b,
                    start_date=date(2026, 9, 1))
        for term in (self.term1, self.term2):
            bulk = term.section_rosters([self.six_a, self.six_b])
            for section in (self.six_a, self.six_b):
                with self.subTest(term=term.name, section=section.name):
                    self.assertEqual(bulk[section.pk], term.section_roster(section))


class QueryCountTests(TeacherHomeFixture, TestCase):
    def count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.teacher.get(self.url).status_code, 200)
        return len(ctx.captured_queries)

    def test_queries_do_not_grow_with_duties(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.make_student("Asha")
        self.make_assessment(name="UT1")
        small = self.count()
        self.class_teacher(self.rao, self.six_b)
        self.assign(self.rao, self.maths, self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        for i in range(4):
            self.make_student(f"Student {i}", section=self.six_b)
        self.make_assessment(name="UT2", section=self.six_b)
        self.make_assessment(offering=self.sanskrit, section=self.six_b, name="S1")
        self.assertEqual(self.count(), small)
