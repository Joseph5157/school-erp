"""Security Gate 3A: class-teacher authority is bound to the record's academic year.

Audit run-1 lead core/authorization.py:class_teacher_on:section-date-scope-ignores-academic-year.
Sections have no academic year and academic years may overlap, and the one-class-teacher-per-
section rule is only enforced inside a single year. So two different teachers can both be the
class teacher of the same section on the same date, one per overlapping year. Every class-teacher
check matched only (teacher, section, date), so each teacher could read, and in places write,
the other year's cohort.

All data here is synthetic and local.
"""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import reports
from core.authorization import (
    can_take_attendance,
    can_write_term_remarks,
    class_teacher_duty,
    class_teacher_on,
    class_teacher_sections,
    guardian_contact_visible,
    sole_class_teacher_duty,
    teacher_student_scope,
    term_remark_sections,
)
from core.models import (
    AcademicTerm,
    AcademicYear,
    Applicant,
    AttendanceRegister,
    Guardian,
    SectionClassTeacher,
    Student,
    StudentGuardian,
    TermRemark,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)  # a Monday inside both years and inside Y1's Term 2


class OverlappingYearFixture(Phase4Fixture):
    """Y1 (Jun 2026 - Mar 2027, teacher Rao) and Y2 (Aug 2026 - May 2027, teacher Iyer),
    both class teacher of Grade 6 A on the same date, each with its own cohort."""

    def setUp(self):
        self.build_phase4()
        for target in ("core.views.business_today", "core.models.business_today",
                       "core.reports.business_today"):
            patcher = mock.patch(target, new=lambda: TODAY)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.year1 = self.year
        self.term_y1 = self.term2  # Oct-Dec, running on TODAY
        self.year2 = AcademicYear.objects.create(
            name="2026-27 overlapping session", start_date=date(2026, 8, 1),
            end_date=date(2027, 5, 31),
        )
        self.term_y2 = AcademicTerm.objects.create(
            academic_year=self.year2, name="Term 1", start_date=date(2026, 8, 1),
            end_date=date(2026, 12, 31), display_order=1,
        )
        self.duty_y1 = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year1, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.duty_y2 = SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=self.year2, section=self.six_a,
            start_date=date(2026, 8, 1),
        )
        self.y1_student, self.y1_enrollment = self.make_student("Asha Y1")
        self.y2_student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Bina Y2"),
            full_name="Bina Y2",
        )
        self.y2_enrollment = self.y2_student.enroll(
            academic_year=self.year2, class_grade=self.grade6, section=self.six_a,
            start_date=date(2026, 8, 1),
        )
        guardian = Guardian.objects.create(full_name="Priya Guardian", phone="98450-55555")
        StudentGuardian.objects.create(
            student=self.y1_student, guardian=guardian, relationship_type="MOTHER"
        )
        self.client_y1 = self.client_class()
        self.client_y1.login(username="rao", password="pass-12345")
        self.client_y2 = self.client_class()
        self.client_y2.login(username="iyer", password="pass-12345")

    def y1_register(self):
        return AttendanceRegister.objects.create(
            academic_year=self.year1, class_grade=self.grade6, section=self.six_a, date=TODAY
        )


class TheOverlapIsReachableTests(OverlappingYearFixture, TestCase):
    """The precondition of the exposure. NOT a security check.

    It asserts only that the data state exists: the model lets two different teachers be
    class teacher of one Section on one date, one per overlapping year. It passed before the
    fix and still passes, because the fix binds authority to the year; it does not forbid
    the overlap. In the first run of the reproduction tests this was the one test of 13 that
    passed, and the other 12 failed.
    """

    def test_two_teachers_are_class_teacher_of_one_section_on_one_date(self):
        effective = SectionClassTeacher.objects.filter(section=self.six_a).effective_on(TODAY)
        self.assertEqual({row.teacher for row in effective}, {self.rao, self.iyer})


class HelperContractTests(OverlappingYearFixture, TestCase):
    def test_the_academic_year_is_a_required_keyword(self):
        """No authorization decision can fall back to section and date alone."""
        with self.assertRaises(TypeError):
            class_teacher_on(self.rao, self.six_a, TODAY)
        with self.assertRaises(TypeError):
            can_take_attendance(self.rao, self.six_a, TODAY)
        with self.assertRaises(TypeError):
            class_teacher_duty(self.rao, self.six_a, TODAY)
        with self.assertRaises(TypeError):
            class_teacher_sections(self.rao, TODAY)

    def test_class_teacher_on_is_bound_to_the_given_year(self):
        self.assertTrue(class_teacher_on(self.rao, self.six_a, TODAY, academic_year=self.year1))
        self.assertFalse(class_teacher_on(self.rao, self.six_a, TODAY, academic_year=self.year2))
        self.assertTrue(
            class_teacher_on(self.iyer, self.six_a, TODAY, academic_year=self.year2.pk)
        )
        self.assertFalse(
            class_teacher_on(self.iyer, self.six_a, TODAY, academic_year=self.year1.pk)
        )

    def test_can_take_attendance_is_bound_to_the_registers_year(self):
        self.assertTrue(can_take_attendance(self.rao, self.six_a, TODAY, academic_year=self.year1))
        self.assertFalse(can_take_attendance(self.rao, self.six_a, TODAY, academic_year=self.year2))
        self.assertTrue(can_take_attendance(self.iyer, self.six_a, TODAY, academic_year=self.year2))
        self.assertFalse(
            can_take_attendance(self.iyer, self.six_a, TODAY, academic_year=self.year1)
        )

    def test_duty_lookup_is_bound_to_the_year(self):
        self.assertEqual(
            class_teacher_duty(self.rao, self.six_a, TODAY, academic_year=self.year1),
            self.duty_y1,
        )
        self.assertIsNone(
            class_teacher_duty(self.rao, self.six_a, TODAY, academic_year=self.year2)
        )
        self.assertEqual(
            class_teacher_duty(self.iyer, self.six_a, TODAY, academic_year=self.year2.pk),
            self.duty_y2,
        )
        self.assertIsNone(
            class_teacher_duty(self.iyer, self.six_a, TODAY, academic_year=self.year1)
        )
        self.assertIsNone(
            class_teacher_duty(self.admin, self.six_a, TODAY, academic_year=self.year1)
        )

    def test_sole_duty_is_only_for_the_no_record_case_and_is_never_a_default(self):
        self.assertEqual(sole_class_teacher_duty(self.rao, self.six_a, TODAY), self.duty_y1)
        self.assertEqual(sole_class_teacher_duty(self.iyer, self.six_a, TODAY), self.duty_y2)
        self.assertIsNone(sole_class_teacher_duty(self.admin, self.six_a, TODAY))
        self.assertIsNone(sole_class_teacher_duty(self.rao, self.six_b, TODAY))

    def test_report_helpers_filter_by_year_when_asked_and_keep_their_default(self):
        everyone = {row["student"].full_name for row in reports.section_summary(
            self.six_a, TODAY, TODAY)["rows"]}
        self.assertEqual(everyone, {"Asha Y1", "Bina Y2"})  # default: both years, as before
        only_y1 = reports.section_summary(self.six_a, TODAY, TODAY, academic_year=self.year1)
        self.assertEqual([row["student"].full_name for row in only_y1["rows"]], ["Asha Y1"])
        only_y2 = reports.section_summary(self.six_a, TODAY, TODAY, academic_year=self.year2.pk)
        self.assertEqual([row["student"].full_name for row in only_y2["rows"]], ["Bina Y2"])

    def test_missing_attendance_counts_only_the_requested_year(self):
        both = reports.missing_attendance(TODAY, TODAY, section=self.six_a)
        self.assertEqual(len(both), 2)
        for year in (self.year1, self.year2):
            rows = reports.missing_attendance(TODAY, TODAY, section=self.six_a, academic_year=year)
            self.assertEqual(len(rows), 1)


class AmbiguousDutyTests(OverlappingYearFixture, TestCase):
    """One teacher holding the same Section in both overlapping years."""

    def setUp(self):
        super().setUp()
        # Rao takes Y2's class from Sep 1 (this hands over from Iyer, whose Y2 row ends Aug 31).
        self.duty_y2_rao = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year2, section=self.six_a,
            start_date=date(2026, 9, 1),
        )

    def test_opening_a_register_is_refused_instead_of_guessing_the_year(self):
        self.assertIsNone(sole_class_teacher_duty(self.rao, self.six_a, TODAY))
        page = reverse("core:my-attendance", args=[self.six_a.pk])
        self.assertEqual(self.client_y1.post(page, {"action": "open"}).status_code, 403)
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_an_existing_register_decides_the_year(self):
        register = self.y1_register()
        page = reverse("core:my-attendance", args=[self.six_a.pk])
        self.assertEqual(self.client_y1.get(page).status_code, 200)
        self.assertEqual(
            class_teacher_duty(
                self.rao, self.six_a, TODAY, academic_year=register.academic_year_id
            ),
            self.duty_y1,
        )


class StudentAccessIsYearBoundTests(OverlappingYearFixture, TestCase):
    def test_my_students_lists_only_the_teachers_own_year_cohort(self):
        mine_y1 = self.client_y1.get(reverse("core:my-students"))
        self.assertContains(mine_y1, "Asha Y1")
        self.assertNotContains(mine_y1, "Bina Y2")
        mine_y2 = self.client_y2.get(reverse("core:my-students"))
        self.assertContains(mine_y2, "Bina Y2")
        self.assertNotContains(mine_y2, "Asha Y1")

    def test_scope_contains_only_enrollments_of_the_assignment_year(self):
        self.assertEqual(
            set(teacher_student_scope(self.rao, TODAY)), {self.y1_enrollment}
        )
        self.assertEqual(
            set(teacher_student_scope(self.iyer, TODAY)), {self.y2_enrollment}
        )

    def test_subject_teacher_scope_is_unchanged_and_was_already_year_bound(self):
        """Control: subject-teacher authorization is not touched by Gate 3A.

        It already bound each assignment to its offering's academic year, so it passes before
        and after the fix.
        """
        menon = self.make_user("menon", self.teachers)
        self.assign(menon, self.maths, self.six_a)  # a Y1 Mathematics offering
        self.assertEqual(set(teacher_student_scope(menon, TODAY)), {self.y1_enrollment})

    def test_student_detail_is_refused_for_the_other_years_cohort(self):
        url_y1 = reverse("core:my-student-detail", args=[self.y1_student.pk])
        url_y2 = reverse("core:my-student-detail", args=[self.y2_student.pk])
        self.assertEqual(self.client_y1.get(url_y1).status_code, 200)
        self.assertEqual(self.client_y2.get(url_y2).status_code, 200)
        self.assertEqual(self.client_y2.get(url_y1).status_code, 403)
        self.assertEqual(self.client_y1.get(url_y2).status_code, 403)

    def test_guardian_contacts_are_shown_only_to_the_enrollments_class_teacher(self):
        self.assertTrue(guardian_contact_visible(self.rao, self.y1_enrollment, TODAY))
        self.assertFalse(guardian_contact_visible(self.iyer, self.y1_enrollment, TODAY))
        self.assertTrue(guardian_contact_visible(self.iyer, self.y2_enrollment, TODAY))
        self.assertFalse(guardian_contact_visible(self.rao, self.y2_enrollment, TODAY))

    def test_guardian_name_and_phone_never_reach_the_other_years_teacher(self):
        url = reverse("core:my-student-detail", args=[self.y1_student.pk])
        page = self.client_y1.get(url)
        self.assertContains(page, "Priya Guardian")
        self.assertContains(page, "98450-55555")
        other = self.client_y2.get(url)
        self.assertNotContains(other, "Priya Guardian", status_code=other.status_code)
        self.assertNotContains(other, "98450-55555", status_code=other.status_code)


class ReportCardAndRemarksAreYearBoundTests(OverlappingYearFixture, TestCase):
    def test_report_card_is_refused_for_the_other_years_term(self):
        own_y1 = reverse("core:my-report-card", args=[self.term_y1.pk, self.y1_student.pk])
        own_y2 = reverse("core:my-report-card", args=[self.term_y2.pk, self.y2_student.pk])
        self.assertEqual(self.client_y1.get(own_y1).status_code, 200)
        self.assertEqual(self.client_y2.get(own_y2).status_code, 200)
        self.assertEqual(self.client_y2.get(own_y1).status_code, 403)
        self.assertEqual(self.client_y1.get(own_y2).status_code, 403)

    def test_remark_authority_follows_the_terms_year(self):
        self.assertTrue(can_write_term_remarks(self.rao, self.term_y1, self.six_a))
        self.assertFalse(can_write_term_remarks(self.iyer, self.term_y1, self.six_a))
        self.assertTrue(can_write_term_remarks(self.iyer, self.term_y2, self.six_a))
        self.assertFalse(can_write_term_remarks(self.rao, self.term_y2, self.six_a))

    def test_remark_section_list_does_not_match_another_teachers_row(self):
        self.assertEqual(list(term_remark_sections(self.iyer, self.term_y1)), [])
        self.assertEqual(list(term_remark_sections(self.rao, self.term_y2)), [])
        self.assertEqual(list(term_remark_sections(self.rao, self.term_y1)), [self.six_a])
        self.assertEqual(list(term_remark_sections(self.iyer, self.term_y2)), [self.six_a])

    def test_the_other_years_teacher_cannot_write_or_overwrite_remarks(self):
        url = reverse("core:term-remarks", args=[self.term_y1.pk])
        body = {"section": self.six_a.pk, f"remark_{self.y1_student.pk}": "Overwritten"}
        response = self.client_y2.post(url, body)
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(TermRemark.objects.exists())
        written = self.client_y1.post(url, {**body, f"remark_{self.y1_student.pk}": "Kind and focused"})
        self.assertEqual(written.status_code, 302)
        self.assertEqual(TermRemark.objects.get().remark, "Kind and focused")
        again = self.client_y2.post(url, body)
        self.assertIn(again.status_code, (403, 404))
        self.assertEqual(TermRemark.objects.get().remark, "Kind and focused")


class AttendanceIsYearBoundTests(OverlappingYearFixture, TestCase):
    def test_the_other_years_teacher_cannot_use_a_register_of_another_year(self):
        register = self.y1_register()
        page = reverse("core:my-attendance", args=[self.six_a.pk])
        submit = reverse("core:my-attendance-submit", args=[self.six_a.pk])
        autosave = reverse("core:my-attendance-autosave", args=[self.six_a.pk])
        readonly = reverse("core:my-attendance-register", args=[register.pk])
        self.assertEqual(self.client_y1.get(page).status_code, 200)
        self.assertEqual(self.client_y2.get(page).status_code, 403)
        self.assertEqual(self.client_y2.post(page, {"action": "save"}).status_code, 403)
        self.assertEqual(self.client_y2.get(submit).status_code, 403)
        self.assertEqual(
            self.client_y2.post(autosave, {}, HTTP_HX_REQUEST="true").status_code, 403
        )
        self.assertEqual(self.client_y2.get(readonly).status_code, 403)
        self.assertEqual(self.client_y1.get(readonly).status_code, 200)

    def test_a_register_belongs_to_the_year_of_the_teacher_who_opens_it(self):
        page = reverse("core:my-attendance", args=[self.six_a.pk])
        self.client_y2.post(page, {"action": "open"})
        register = AttendanceRegister.objects.get(section=self.six_a, date=TODAY)
        self.assertEqual(register.academic_year, self.year2)
        self.assertEqual(self.client_y2.get(page).status_code, 200)
        self.assertEqual(self.client_y1.get(page).status_code, 403)

    def test_assignment_report_shows_only_the_rows_own_year(self):
        self.y1_register()
        y1_row = reverse("core:my-attendance-assignment", args=[self.duty_y1.pk])
        y2_row = reverse("core:my-attendance-assignment", args=[self.duty_y2.pk])
        own_y1 = self.client_y1.get(y1_row)
        self.assertContains(own_y1, "Asha Y1")
        self.assertNotContains(own_y1, "Bina Y2")
        own_y2 = self.client_y2.get(y2_row)
        self.assertContains(own_y2, "Bina Y2")
        self.assertNotContains(own_y2, "Asha Y1")
        self.assertEqual([r.academic_year for r in own_y2.context["registers"]], [])
