"""Finding a student's parents and a parent's children from the two list pages."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Applicant, ApplicantGuardian, Guardian, Student, StudentGuardian
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin


class GuardianStudentSearchTests(AuthorizationClientsMixin, Phase4Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.build_phase4()
        self.students_url = reverse("core:student-list")
        self.guardians_url = reverse("core:guardian-list")
        self.asha = self.family("Asha Rao", "Rajesh Rao", "9811111111", "Sunita Rao")
        self.ravi = self.family("Ravi Iyer", "Kumar Iyer", "9822222222", "Meena Iyer")

    def family(self, student_name, father_name, father_phone, mother_name):
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name=student_name),
            full_name=student_name,
        )
        student.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        father = Guardian.objects.create(full_name=father_name, phone=father_phone)
        mother = Guardian.objects.create(full_name=mother_name)
        StudentGuardian.objects.create(student=student, guardian=father, relationship_type="FATHER")
        StudentGuardian.objects.create(student=student, guardian=mother, relationship_type="MOTHER")
        return student

    def names(self, response, key):
        return [row.full_name for row in response.context[key]]

    # --- student list ------------------------------------------------------

    def test_student_list_shows_father_and_mother_with_relationship(self):
        response = self.administrator.get(self.students_url)
        self.assertContains(response, "Rajesh Rao")
        self.assertContains(response, "(Father)")
        self.assertContains(response, "Sunita Rao")
        self.assertContains(response, "(Mother)")

    def test_student_search_finds_child_by_parent_name(self):
        response = self.administrator.get(self.students_url, {"q": "Rajesh"})
        self.assertEqual(self.names(response, "students"), ["Asha Rao"])

    def test_student_search_finds_child_by_parent_phone(self):
        response = self.administrator.get(self.students_url, {"q": "9822222222"})
        self.assertEqual(self.names(response, "students"), ["Ravi Iyer"])

    def test_student_search_matching_both_parents_lists_the_child_once(self):
        response = self.administrator.get(self.students_url, {"q": "Rao"})
        self.assertEqual(self.names(response, "students"), ["Asha Rao"])

    # --- guardian list -----------------------------------------------------

    def test_guardian_list_shows_children_with_relationship(self):
        response = self.administrator.get(self.guardians_url)
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, "(Father)")
        self.assertContains(response, "(Mother)")

    def test_guardian_search_finds_parents_by_child_name(self):
        response = self.administrator.get(self.guardians_url, {"q": "Asha"})
        self.assertEqual(self.names(response, "guardians"), ["Rajesh Rao", "Sunita Rao"])

    def test_guardian_search_by_name_and_phone(self):
        response = self.administrator.get(self.guardians_url, {"q": "Kumar"})
        self.assertEqual(self.names(response, "guardians"), ["Kumar Iyer"])
        response = self.administrator.get(self.guardians_url, {"q": "9811111111"})
        self.assertEqual(self.names(response, "guardians"), ["Rajesh Rao"])

    def test_guardian_with_two_children_lists_both(self):
        sibling = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Anil Rao"),
            full_name="Anil Rao",
        )
        father = Guardian.objects.get(full_name="Rajesh Rao")
        StudentGuardian.objects.create(student=sibling, guardian=father, relationship_type="FATHER")
        response = self.administrator.get(self.guardians_url, {"q": "Rajesh"})
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, "Anil Rao")

    def test_guardian_search_with_no_match_says_so(self):
        response = self.administrator.get(self.guardians_url, {"q": "zzzz"})
        self.assertContains(response, "No guardians match this search")

    # --- guardians of applicants -------------------------------------------

    def applicant_guardian(self, applicant_name, guardian_name, relationship="FATHER"):
        applicant = Applicant.objects.create(full_name=applicant_name)
        guardian = Guardian.objects.create(full_name=guardian_name)
        ApplicantGuardian.objects.create(
            applicant=applicant, guardian=guardian, relationship_type=relationship
        )
        return applicant, guardian

    def test_applicant_only_guardian_shows_applicant_with_label_and_link(self):
        applicant, _ = self.applicant_guardian("Aarav Rao", "Vikram Rao")
        response = self.administrator.get(self.guardians_url, {"q": "Vikram"})
        self.assertContains(response, "Aarav Rao")
        self.assertContains(response, "(Applicant, Father)")
        self.assertContains(
            response, reverse("core:applicant-detail", args=[applicant.pk])
        )

    def test_guardian_search_finds_parent_by_applicant_name(self):
        self.applicant_guardian("Aarav Rao", "Vikram Rao")
        response = self.administrator.get(self.guardians_url, {"q": "Aarav"})
        self.assertEqual(self.names(response, "guardians"), ["Vikram Rao"])

    def test_students_are_listed_before_applicants(self):
        applicant = Applicant.objects.create(full_name="Aaa Younger")
        father = Guardian.objects.get(full_name="Rajesh Rao")
        ApplicantGuardian.objects.create(
            applicant=applicant, guardian=father, relationship_type="FATHER"
        )
        response = self.administrator.get(self.guardians_url, {"q": "Rajesh"})
        content = response.content.decode()
        self.assertLess(content.index("Asha Rao"), content.index("Aaa Younger"))

    def test_dash_only_when_guardian_has_neither(self):
        Guardian.objects.create(full_name="Lonely Guardian")
        response = self.administrator.get(self.guardians_url, {"q": "Lonely"})
        self.assertNotContains(response, "(Applicant")
        self.assertContains(response, "<td>-</td>", html=False)

    def test_applicant_who_became_a_student_is_not_listed_twice(self):
        # family() students were accepted applicants; give one a guardian link
        # as the admissions workflow does, and expect only the student entry.
        father = Guardian.objects.get(full_name="Rajesh Rao")
        ApplicantGuardian.objects.create(
            applicant=self.asha.applicant, guardian=father, relationship_type="FATHER"
        )
        response = self.administrator.get(self.guardians_url, {"q": "Rajesh"})
        self.assertNotContains(response, "(Applicant")

    def test_guardian_list_query_count_does_not_grow_with_guardians(self):
        self.administrator.get(self.guardians_url)  # warm caches
        with CaptureQueriesContext(connection) as one:
            self.administrator.get(self.guardians_url)
        for i in range(5):
            self.applicant_guardian(f"Child{i} Nair", f"Parent{i} Nair")
        with CaptureQueriesContext(connection) as many:
            self.administrator.get(self.guardians_url)
        self.assertEqual(len(many), len(one))
