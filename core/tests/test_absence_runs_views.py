"""Option A2: the "Absent in a row" admin report and the class-teacher card on My Home.

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, sections 5.4 and 5.5. The admin
report needs `core.view_attendanceentry` (OD-6). The card shows only the class teacher's own,
unambiguous Section for their year; subject teachers and guardians see nothing new (OD-5).

All data here is synthetic and local.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicYear,
    AttendanceEntry,
    AttendanceRegister,
    SectionClassTeacher,
)
from core.tests.test_absence_runs import MON, RunFixture
from core.tests.test_phase6_access_boundary import BoundaryFixture

A = "ABSENT"
P = "PRESENT"
REPORT = "core:report-absence-runs"


class ViewFixture(RunFixture):
    """Asha (6 A) and Bala (6 B) are absent Wed-Mon (4 school days); Chitra (6 A) is present."""

    def setUp(self):
        super().setUp()
        self.bala, self.bala_e = self.make_student("Bala", section=self.six_b)
        self.chitra, self.chitra_e = self.make_student("Chitra")
        self.mark(date(2026, 10, 6), {self.asha_e: P, self.chitra_e: P})
        self.mark(date(2026, 10, 6), {self.bala_e: P}, section=self.six_b)
        for on in (date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), MON):
            self.mark(on, {self.asha_e: A, self.chitra_e: P})
            self.mark(on, {self.bala_e: A}, section=self.six_b)

    def perm_user(self, username, *perms):
        user = self.make_user(username)
        for perm in perms:
            app_label, codename = perm.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        return user

    def client_for(self, user):
        client = self.client_class()
        client.force_login(user)
        return client

    def report(self, **params):
        user = self.perm_user("viewer", "core.view_attendanceentry")
        return self.client_for(user).get(reverse(REPORT), params)


class AdminReportTests(ViewFixture, TestCase):
    def test_requires_view_attendanceentry(self):
        user = self.perm_user("registers", "core.view_attendanceregister")
        self.assertEqual(self.client_for(user).get(reverse(REPORT)).status_code, 403)

    def test_anonymous_is_sent_to_sign_in(self):
        self.assertEqual(self.client.get(reverse(REPORT)).status_code, 302)

    def test_lists_runs_with_the_default_threshold_and_links_to_student_attendance(self):
        page = self.report()
        self.assertEqual(page.status_code, 200)
        self.assertEqual([r["name"] for r in page.context["rows"]], ["Asha", "Bala"])
        self.assertContains(page, reverse("core:student-attendance", args=[self.asha.pk]))
        self.assertContains(page, "Absent in a row")
        self.assertContains(page, "Weekends and holidays are skipped.")
        self.assertNotContains(page, "Chitra")

    def test_section_filter(self):
        page = self.report(section=self.six_b.pk, threshold="3")
        self.assertEqual([r["name"] for r in page.context["rows"]], ["Bala"])

    def test_threshold_filter_and_empty_state(self):
        page = self.report(threshold="5")
        self.assertEqual(page.context["rows"], [])
        self.assertContains(
            page, "No student has been absent 5 or more school days in a row (as of 12 Oct 2026)."
        )

    def test_an_invalid_threshold_is_a_form_error(self):
        page = self.report(threshold="4")
        self.assertTrue(page.context["form"].errors)
        self.assertIsNone(page.context["rows"])

    def test_an_inactive_student_is_not_listed(self):
        self.asha.status = "INACTIVE"
        self.asha.save(update_fields=["status"])
        self.assertEqual([r["name"] for r in self.report().context["rows"]], ["Bala"])

    def test_at_least_note_names_the_untaken_day(self):
        AttendanceRegister.objects.filter(section=self.six_a, date=date(2026, 10, 7)).update(
            status="DRAFT", submitted_by=None, submitted_at=None)
        page = self.report()
        self.assertContains(page, "At least 3. Not taken on 7 Oct")

    def test_listed_on_attendance_reports(self):
        user = self.perm_user("viewer", "core.view_attendanceentry")
        page = self.client_for(user).get(reverse("core:attendance-reports"))
        self.assertContains(page, reverse(REPORT))
        self.assertContains(page, "Absent in a row")


class GuardianTests(BoundaryFixture, TestCase):
    def test_a_guardian_cannot_reach_the_report(self):
        response = self.guardian_client().get(reverse(REPORT))
        self.assertEqual(response.status_code, 403)


class CardFixture(ViewFixture):
    """Rao is class teacher of 6 A in 2026-27 from `duty_start` (None: no assignment)."""

    duty_start = date(2026, 6, 1)

    def setUp(self):
        super().setUp()
        if self.duty_start is not None:
            self.duty = SectionClassTeacher.assign(
                teacher=self.rao, academic_year=self.year, section=self.six_a,
                start_date=self.duty_start,
            )

    def card(self, user):
        page = self.client_for(user).get(reverse("core:my-home"))
        self.assertEqual(page.status_code, 200)
        return page

    def make_year2(self):
        return AcademicYear.objects.create(
            name="2026-27 overlapping session", start_date=date(2026, 8, 1),
            end_date=date(2027, 5, 31))


class MidRunAssignmentCardTests(CardFixture, TestCase):
    duty_start = date(2026, 10, 8)  # Asha's run began on 7 Oct

    def test_mid_run_assignment_shows_at_least(self):
        page = self.card(self.rao)
        (run,) = page.context["absence_runs"]
        self.assertEqual((run["days"], run["at_least"]), (3, True))
        self.assertContains(page, "at least 3 days")
        admin_rows = self.report().context["rows"]
        self.assertEqual([(r["name"], r["days"]) for r in admin_rows], [("Asha", 4), ("Bala", 4)])


class OtherYearCardTests(CardFixture, TestCase):
    duty_start = None

    def test_class_teacher_of_another_year_sees_no_card(self):
        """Gate 3A: an assignment in another year never reaches the 2026-27 cohort."""
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.make_year2(), section=self.six_a,
            start_date=date(2026, 8, 1))
        self.assertEqual(self.card(self.rao).context["absence_runs"], [])


class TeacherCardTests(CardFixture, TestCase):

    def test_class_teacher_sees_only_their_sections_students(self):
        page = self.card(self.rao)
        self.assertEqual([r["name"] for r in page.context["absence_runs"]], ["Asha"])
        self.assertContains(page, "Absent in a row")
        self.assertContains(page, reverse("core:my-student-detail", args=[self.asha.pk]))
        self.assertContains(page, "4 school days")
        self.assertNotContains(page, "Bala")

    def test_no_card_without_runs(self):
        AttendanceEntry.objects.filter(
            register__date=MON, register__section=self.six_a).update(status=P)
        page = self.card(self.rao)
        self.assertEqual(page.context["absence_runs"], [])
        self.assertNotContains(page, "Absent in a row")

    def test_subject_teacher_sees_no_card(self):
        self.assign(self.iyer, self.maths, self.six_a)
        page = self.card(self.iyer)
        self.assertEqual(page.context["absence_runs"], [])
        self.assertNotContains(page, "Absent in a row")

    def test_ended_assignment_sees_no_card(self):
        SectionClassTeacher.objects.filter(pk=self.duty.pk).update(end_date=date(2026, 10, 9))
        page = self.card(self.rao)
        self.assertEqual(page.context["absence_runs"], [])

    def test_section_with_enrollments_in_two_years_is_left_out(self):
        year2 = self.make_year2()
        self.new_student("Bina Y2").enroll(
            academic_year=year2, class_grade=self.grade6, section=self.six_a,
            start_date=date(2026, 8, 1))
        self.assertEqual(self.card(self.rao).context["absence_runs"], [])
        self.assertIn("Asha", [r["name"] for r in self.report().context["rows"]])

    def test_section_with_two_assignments_across_years_is_left_out(self):
        year2 = self.make_year2()
        SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=year2, section=self.six_a,
            start_date=date(2026, 8, 1))
        self.assertEqual(self.card(self.rao).context["absence_runs"], [])
        self.assertIn("Asha", [r["name"] for r in self.report().context["rows"]])

    def test_deactivated_teacher_is_refused(self):
        client = self.client_for(self.rao)
        self.rao.is_active = False
        self.rao.save(update_fields=["is_active"])
        self.assertNotEqual(client.get(reverse("core:my-home")).status_code, 200)
