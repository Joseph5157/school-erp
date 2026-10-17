"""Phase 5 Gate 5: limited, read-only teacher student access (ADR 0012 D8, D9)."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.authorization import can_view_student_as_teacher, teacher_student_scope
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    Guardian,
    ResultStatus,
    SectionClassTeacher,
    StudentGuardian,
    StudentResult,
    Subject,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)


class StudentAccessTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: TODAY),
                      mock.patch("core.models.business_today", new=lambda: TODAY)):
            patch.start()
            self.addCleanup(patch.stop)
        # rao: class teacher of 6A; iyer: teaches Maths in 6A only.
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 6, 1))
        self.assign(self.iyer, self.maths, self.six_a)
        self.asha, self.asha_e = self.make_student("Asha")
        self.bina, self.bina_e = self.make_student("Bina", section=self.six_b)
        self.asha.date_of_birth = date(2014, 5, 1)
        self.asha.phone = "98450-00001"
        self.asha.save()
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345",
                                           email="meena@example.com")
        StudentGuardian.objects.create(student=self.asha, guardian=guardian,
                                       relationship_type="MOTHER")
        self.rao_client = self.login("rao")
        self.iyer_client = self.login("iyer")
        self.asha_url = reverse("core:my-student-detail", args=[self.asha.pk])

    def login(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    # --- scope ---

    def test_scope_for_class_and_subject_teacher(self):
        self.assertEqual(set(teacher_student_scope(self.rao, TODAY)), {self.asha_e})
        self.assertEqual(set(teacher_student_scope(self.iyer, TODAY)), {self.asha_e})
        self.assertFalse(can_view_student_as_teacher(self.rao, self.bina, TODAY))

    def test_student_list(self):
        page = self.rao_client.get(reverse("core:my-students"))
        groups = page.context["groups"]
        self.assertEqual([(g["section"], g["is_class_teacher"]) for g in groups],
                         [(self.six_a, True)])
        self.assertContains(page, "Asha")
        self.assertNotContains(page, "Bina")
        groups = self.iyer_client.get(reverse("core:my-students")).context["groups"]
        self.assertFalse(groups[0]["is_class_teacher"])

    def test_out_of_scope_student_is_forbidden(self):
        url = reverse("core:my-student-detail", args=[self.bina.pk])
        self.assertEqual(self.rao_client.get(url).status_code, 403)
        self.assertEqual(self.iyer_client.get(url).status_code, 403)

    # --- admission number (ADR 0012 D8) ---

    def give_admission_numbers(self):
        self.asha.admission_number = "A-1023"
        self.asha.save()
        self.bina.admission_number = "B-2044"
        self.bina.save()

    def test_class_teacher_sees_the_admission_number(self):
        self.give_admission_numbers()
        page = self.rao_client.get(self.asha_url)
        self.assertContains(page, "Admission number")
        self.assertContains(page, "A-1023")

    def test_subject_teacher_sees_the_admission_number(self):
        self.give_admission_numbers()
        page = self.iyer_client.get(self.asha_url)
        self.assertContains(page, "A-1023")

    def test_admission_number_is_left_out_when_none_is_recorded(self):
        page = self.rao_client.get(self.asha_url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Admission number")

    def test_out_of_scope_admission_number_is_not_exposed(self):
        self.give_admission_numbers()
        url = reverse("core:my-student-detail", args=[self.bina.pk])
        for client in (self.rao_client, self.iyer_client):
            response = client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertNotContains(response, "B-2044", status_code=403)
        # And the class list never leaks it either.
        self.assertNotContains(self.rao_client.get(reverse("core:my-students")), "B-2044")

    def test_transferred_student_leaves_old_teachers_list(self):
        self.asha.enroll(academic_year=self.year, class_grade=self.grade6,
                         section=self.six_b, start_date=TODAY)
        self.assertEqual(self.rao_client.get(self.asha_url).status_code, 403)
        self.assertNotContains(self.rao_client.get(reverse("core:my-students")), "Asha")

    def test_subject_offering_from_another_year_gives_no_scope(self):
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        offering = AcademicSubjectOffering.objects.create(
            academic_year=next_year, class_grade=self.grade6, subject=self.maths_subject
        )
        bina_teacher = self.make_user("kapoor", self.teachers)
        self.assign(bina_teacher, offering, self.six_b)
        self.assertFalse(teacher_student_scope(bina_teacher, TODAY).exists())

    def test_lost_status_and_non_teachers(self):
        self.rao.groups.remove(self.teachers)
        self.assertEqual(self.rao_client.get(self.asha_url).status_code, 403)
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.asha_url).status_code, 403)

    # --- field-level visibility ---

    def test_class_teacher_sees_guardian_contact(self):
        page = self.rao_client.get(self.asha_url)
        self.assertContains(page, "Meena Rao")
        self.assertContains(page, "98450-12345")
        self.assertContains(page, "meena@example.com")

    def test_subject_teacher_does_not_see_guardians(self):
        page = self.iyer_client.get(self.asha_url)
        self.assertNotContains(page, "Meena Rao")
        self.assertNotContains(page, "98450-12345")

    def test_never_shows_dob_or_student_contact(self):
        for client in (self.rao_client, self.iyer_client):
            page = client.get(self.asha_url)
            self.assertNotContains(page, "2014")
            self.assertNotContains(page, "98450-00001")
            self.assertNotContains(page, reverse("core:student-detail", args=[self.asha.pk]))

    def test_read_only(self):
        response = self.rao_client.post(self.asha_url, {"full_name": "Changed"})
        self.assertEqual(response.status_code, 200)
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.full_name, "Asha")

    # --- results ---

    def test_results_follow_assignments(self):
        maths = self.make_assessment(name="Maths UT")
        science_offering = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Science"),
        )
        science = self.make_assessment(offering=science_offering, name="Science UT")
        draft = self.make_assessment(name="Draft UT", on=date(2026, 8, 1))
        for assessment in (maths, science, draft):
            StudentResult.objects.create(assessment=assessment, academic_enrollment=self.asha_e,
                                         status=ResultStatus.MARKED, score=10,
                                         entered_by=self.admin)
        self.force_finalize(maths)
        self.force_finalize(science)
        rao_results = self.rao_client.get(self.asha_url).context["results"]
        iyer_results = self.iyer_client.get(self.asha_url).context["results"]
        self.assertEqual({r.assessment.name for r in rao_results}, {"Maths UT", "Science UT"})
        self.assertEqual({r.assessment.name for r in iyer_results}, {"Maths UT"})

    def test_attendance_summary_shown(self):
        page = self.rao_client.get(self.asha_url)
        self.assertEqual(page.context["attendance"]["total"], 0)
        self.assertContains(page, "Attendance this year")

    def test_class_teacher_results_limited_to_own_dates(self):
        SectionClassTeacher.assign(teacher=self.iyer, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 9, 1))
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 10, 1))
        before = self.make_assessment(name="July UT", on=date(2026, 7, 15))
        during_iyer = self.make_assessment(name="Sept UT", on=date(2026, 9, 15))
        for assessment in (before, during_iyer):
            StudentResult.objects.create(assessment=assessment, academic_enrollment=self.asha_e,
                                         status=ResultStatus.ABSENT, entered_by=self.admin)
            self.force_finalize(assessment)
        self.maths.teacher_assignments.get().end(date(2026, 8, 31))  # iyer stops teaching Maths
        names = {r.assessment.name for r in self.rao_client.get(self.asha_url).context["results"]}
        self.assertEqual(names, {"July UT"})
