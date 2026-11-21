"""Admin home integration with Option A1 and A2.

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 7.
- Today tab: register rows come from `attendance_actions.resolve_missing`, so a missing register
  opens the pre-filled create form, the class teacher is the one of the row's own academic year,
  and a configuration problem is named. "Take register" is never offered where none may be
  taken (archived or overlapping-year sections).
- Late rows name the class teacher of the register's own academic year (Security Gate 3A).
- Attendance tab: an "Absent in a row" card from `attendance_insights.school_absence_runs`, the
  same helper the report it links to uses.

All data here is synthetic and local.
"""

import datetime
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from core import attendance_actions, home_today
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicYear,
    Applicant,
    AttendanceEntry,
    AttendanceRegister,
    SectionClassTeacher,
)
from core.tests.test_admin_overview_analytics import TODAY, A, P
from core.tests.test_home_today import TodayDataFixture, at

Problem = attendance_actions.Problem
URL = reverse("core:admin-overview")
CREATE = reverse("core:attendance-register-create")


def rows(**can):
    return home_today.attendance_today(TODAY, include_rows=True, **can)["not_taken"]


class TodayRegisterRowTests(TodayDataFixture, TestCase):
    def take_url(self, section, year=None):
        return CREATE + "?" + urlencode({
            "academic_year": (year or self.year).pk,
            "class_grade": section.class_grade_id,
            "section": section.pk,
            "date": TODAY.isoformat(),
        })

    def make_teacher_valid(self):
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))

    def make_year2(self):
        return AcademicYear.objects.create(
            name="Overlapping session", start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2027, 5, 31))

    def test_missing_register_opens_the_prefilled_create_form(self):
        self.make_teacher_valid()
        (row,) = rows(can_view_registers=True, can_create_registers=True)
        self.assertEqual(row["url"], self.take_url(self.section))
        self.assertEqual(row["teacher_name"], "Asha Rao")
        self.assertEqual(row["problem_label"], "")

    def test_no_link_without_add_permission(self):
        self.make_teacher_valid()
        (row,) = rows(can_view_registers=True)
        self.assertIsNone(row["url"])

    def test_teacher_who_cannot_sign_in_is_named_as_a_problem(self):
        (row,) = rows(can_view_registers=True, can_create_registers=True)
        self.assertEqual(row["problem_label"], Problem.TEACHER_CANNOT_TAKE.label)
        self.assertEqual(row["teacher_name"], "Asha Rao")
        self.assertEqual(row["url"], self.take_url(self.section))

    def test_section_without_class_teacher_is_named_as_a_problem(self):
        self.make_teacher_valid()
        _, section, _ = self.add_section("Grade 2")
        by_class = {r["class_name"]: r for r in rows(can_create_registers=True)}
        self.assertEqual(by_class["Grade 2"]["problem_label"], Problem.NO_CLASS_TEACHER.label)
        self.assertEqual(by_class["Grade 2"]["teacher_name"], "")
        self.assertEqual(by_class["Grade 2"]["url"], self.take_url(section))

    def test_overlapping_years_never_offer_take_register(self):
        self.make_teacher_valid()
        year2 = self.make_year2()
        applicant = Applicant.objects.create(full_name="Year Two Kid")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        applicant.progress_to_student().enroll(
            academic_year=year2, class_grade=self.class_grade, section=self.section,
            start_date="2026-07-01")
        found = rows(can_view_registers=True, can_create_registers=True)
        self.assertEqual(len(found), 2)  # one row per expected academic year
        for row in found:
            self.assertEqual(row["problem_label"], Problem.OVERLAPPING_YEARS.label)
            self.assertIsNone(row["url"])

    def test_archived_section_never_offers_take_register(self):
        self.make_teacher_valid()
        from core.models import Section

        Section.objects.filter(pk=self.section.pk).update(
            archived_at=timezone.now(), archived_by=self.admin_user)
        (row,) = rows(can_view_registers=True, can_create_registers=True)
        self.assertEqual(row["problem_label"], Problem.ARCHIVED_SECTION.label)
        self.assertIsNone(row["url"])

    def test_draft_needs_view_registers_to_link(self):
        self.make_teacher_valid()
        self.day(TODAY, {self.s1: P}, submit=False)
        (row,) = rows(can_create_registers=True)
        self.assertIsNone(row["url"])

    def test_rows_use_a_fixed_number_of_queries(self):
        self.make_teacher_valid()

        def count():
            with CaptureQueriesContext(connection) as queries:
                rows(can_view_registers=True, can_create_registers=True)
            return len(queries)

        self.add_section("Grade 2")
        two = count()
        for name in ("Grade 3", "Grade 4", "Grade 5", "Grade 6"):
            self.add_section(name)
        self.assertEqual(count(), two)

    def test_draft_register_still_opens_its_page(self):
        self.make_teacher_valid()
        register = self.day(TODAY, {self.s1: P}, submit=False)
        (row,) = rows(can_view_registers=True, can_create_registers=True)
        self.assertEqual(row["state"], AttendanceRegister.AttendanceState.DRAFT)
        self.assertEqual(row["url"], reverse("core:attendance-register-detail", args=[register.pk]))

    def test_late_row_names_the_teacher_of_the_registers_own_year(self):
        year2 = self.make_year2()
        other = get_user_model().objects.create(
            username="mr.iyer", first_name="Ravi", last_name="Iyer")
        SectionClassTeacher.objects.create(
            teacher=other, academic_year=year2, section=self.section,
            start_date=datetime.date(2026, 7, 1))
        register = self.day(TODAY, {self.s1: P, self.s2: A})
        self.submit_at(register, at(11, 0))
        result = home_today.register_compliance(
            TODAY, at(12, 0), datetime.time(10, 0), can_view_registers=True)
        self.assertEqual([r["teacher_name"] for r in result["late"]], ["Asha Rao"])

    def test_today_tab_shows_the_problem_and_take_register_link(self):
        page = self.administrator.get(URL)
        self.assertContains(page, escape(Problem.TEACHER_CANNOT_TAKE.label))
        self.assertContains(page, 'href="{}"'.format(self.take_url(self.section).replace("&", "&amp;")))
        self.assertContains(page, "Take register")


class AttendanceTabAbsenceRunsTests(TodayDataFixture, TestCase):
    def setUp(self):
        super().setUp()
        # s1 absent the last three school days (Fri 10, Mon 13, Tue 14 Jul); s2 present.
        self.day(datetime.date(2026, 7, 9), {self.s1: P, self.s2: P})
        for on in (datetime.date(2026, 7, 10), datetime.date(2026, 7, 13), TODAY):
            self.day(on, {self.s1: A, self.s2: P})

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.force_login(user)
        return client

    def runs(self, client=None):
        page = (client or self.administrator).get(URL, {"tab": "attendance"})
        self.assertEqual(page.status_code, 200)
        return page, page.context["attendance_tab"]["runs"]

    def test_card_lists_the_same_students_as_the_report(self):
        page, runs = self.runs()
        report = self.administrator.get(reverse("core:report-absence-runs"))
        self.assertEqual(
            [(r["student_id"], r["days"]) for r in runs["rows"]],
            [(r["student_id"], r["days"]) for r in report.context["rows"]],
        )
        self.assertEqual(runs["total"], 1)
        self.assertContains(page, "Absent in a row")
        self.assertContains(page, reverse("core:report-absence-runs"))
        self.assertContains(page, "3 school days")

    def test_card_needs_student_names_and_attendance(self):
        page, runs = self.runs(self.viewer("school", "view_school", "view_attendanceentry"))
        self.assertIsNone(runs)
        self.assertNotContains(page, "Absent in a row")

    def test_card_needs_attendance_as_well_as_names(self):
        page, runs = self.runs(self.viewer("names", "view_school", "view_student"))
        self.assertIsNone(runs)
        self.assertNotContains(page, "Absent in a row")

    def test_empty_state(self):
        AttendanceEntry.objects.filter(register__date=TODAY).update(status=P)
        page, runs = self.runs()
        self.assertEqual(runs["rows"], [])
        self.assertContains(page, "No student has been absent 3 or more school days in a row.")

    def test_runs_are_computed_fresh_each_request(self):
        self.assertEqual(self.runs()[1]["total"], 1)
        AttendanceEntry.objects.filter(academic_enrollment=self.s1, register__date=TODAY).update(
            status=P)
        self.assertEqual(self.runs()[1]["total"], 0)
