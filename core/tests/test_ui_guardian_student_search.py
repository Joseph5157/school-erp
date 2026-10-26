"""Finding a student's parents and a parent's children from the two list pages."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, Guardian, Student, StudentGuardian
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
