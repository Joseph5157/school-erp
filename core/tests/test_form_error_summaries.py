"""Teacher, applicant and associate-guardian forms use the shared error summary.

An invalid submit lists every problem at the top, links each one to its field,
and starts focus on the first invalid field. When only a form-level error exists
there is no field to focus, so focus goes to the summary.
"""

import re

from django.test import TestCase
from django.urls import reverse

from core import teacher_accounts
from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    RelationshipType,
    Student,
    StudentGuardian,
)
from core.tests.test_authorization import AuthorizationClientsMixin

SUMMARY = 'id="form-error-summary"'


class ErrorSummaryAssertions:
    def assert_summary_links_to(self, response, field_id):
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count(SUMMARY), 1)
        summary = re.search(r'id="form-error-summary".*?</div>', content, re.S).group(0)
        self.assertIn(f'href="#{field_id}"', summary)
        self.assertRegex(content, rf'<(?:input|select)[^>]*id="{field_id}"[^>]*>')

    def field_tag(self, response, field_id):
        return re.search(
            rf'<(?:input|select)[^>]*id="{field_id}"[^>]*>', response.content.decode()
        ).group(0)

    def assert_focus_on_field(self, response, field_id):
        tag = self.field_tag(response, field_id)
        self.assertIn("autofocus", tag)
        self.assertIn('aria-invalid="true"', tag)
        self.assertEqual(response.content.decode().count("autofocus"), 1)

    def assert_focus_on_summary(self, response, message):
        content = response.content.decode()
        self.assertEqual(content.count(SUMMARY), 1)
        self.assertRegex(content, r'id="form-error-summary" tabindex="-1" autofocus')
        self.assertEqual(content.count(message), 1)
        self.assertEqual(content.count("autofocus"), 1)


class TeacherFormSummaryTests(ErrorSummaryAssertions, AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher, _ = teacher_accounts.create_teacher(
            username="asha.rao", first_name="Asha", last_name="Rao", email="", actor=self.admin_user
        )

    def test_add_teacher_lists_each_missing_field_and_focuses_the_first(self):
        response = self.administrator.post(reverse("core:teacher-create"), {"username": "new.one"})
        self.assert_summary_links_to(response, "id_first_name")
        self.assert_summary_links_to(response, "id_last_name")
        self.assert_focus_on_field(response, "id_first_name")

    def test_add_teacher_focuses_username_when_the_service_rejects_it(self):
        response = self.administrator.post(reverse("core:teacher-create"), {
            "first_name": "Other", "last_name": "Rao", "username": "asha.rao", "email": "",
        })
        self.assert_summary_links_to(response, "id_username")
        self.assert_focus_on_field(response, "id_username")

    def test_change_username_focuses_username_when_the_service_rejects_it(self):
        teacher_accounts.create_teacher(
            username="taken.name", first_name="T", last_name="N", email="", actor=self.admin_user
        )
        response = self.administrator.post(
            reverse("core:teacher-username", args=[self.teacher.pk]), {"username": "taken.name"}
        )
        self.assert_summary_links_to(response, "id_username")
        self.assert_focus_on_field(response, "id_username")

    def test_deactivate_without_a_reason_links_to_the_reason(self):
        response = self.administrator.post(
            reverse("core:teacher-deactivate", args=[self.teacher.pk]), {"reason": ""}
        )
        self.assert_summary_links_to(response, "id_reason")
        self.assert_focus_on_field(response, "id_reason")

    def test_deactivate_service_error_focuses_the_summary(self):
        teacher_accounts.deactivate_teacher(user=self.teacher, reason="Left", actor=self.admin_user)
        response = self.administrator.post(
            reverse("core:teacher-deactivate", args=[self.teacher.pk]), {"reason": "Again"}
        )
        self.assertEqual(response.status_code, 200)
        self.assert_focus_on_summary(response, "This teacher is already inactive.")


class ApplicantAndGuardianSummaryTests(
    ErrorSummaryAssertions, AuthorizationClientsMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Asha Testfield")
        accepted = Applicant.objects.create(full_name="Ravi Testfield", admission_status="ACCEPTED")
        self.student = Student.objects.create(applicant=accepted, full_name="Ravi Testfield")
        self.guardian = Guardian.objects.create(full_name="Meena Testfield")

    def test_register_applicant_links_to_the_name(self):
        response = self.administrator.post(reverse("core:applicant-create"), {"full_name": ""})
        self.assert_summary_links_to(response, "id_full_name")
        self.assert_focus_on_field(response, "id_full_name")

    def test_applicant_guardian_missing_guardian_links_to_it(self):
        response = self.administrator.post(
            reverse("core:applicant-guardian-create", args=[self.applicant.pk]),
            {"relationship_type": RelationshipType.MOTHER},
        )
        self.assert_summary_links_to(response, "id_guardian")
        self.assert_focus_on_field(response, "id_guardian")

    def test_applicant_guardian_duplicate_focuses_the_summary_and_says_it_once(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant, guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        response = self.administrator.post(
            reverse("core:applicant-guardian-create", args=[self.applicant.pk]),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.FATHER},
        )
        self.assert_focus_on_summary(
            response, "This Guardian is already associated with this Applicant."
        )

    def test_student_guardian_missing_guardian_links_to_it(self):
        response = self.administrator.post(
            reverse("core:student-guardian-add", args=[self.student.pk]),
            {"relationship_type": RelationshipType.MOTHER},
        )
        self.assert_summary_links_to(response, "id_guardian")
        self.assert_focus_on_field(response, "id_guardian")

    def test_student_guardian_duplicate_focuses_the_summary_and_says_it_once(self):
        StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian, relationship_type=RelationshipType.MOTHER
        )
        response = self.administrator.post(
            reverse("core:student-guardian-add", args=[self.student.pk]),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.FATHER},
        )
        self.assert_focus_on_summary(
            response, "This Guardian is already associated with this Student."
        )

    def test_change_relationship_links_to_the_relationship(self):
        link = StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian, relationship_type=RelationshipType.MOTHER
        )
        response = self.administrator.post(
            reverse("core:student-guardian-edit", args=[link.pk]), {"relationship_type": ""}
        )
        self.assert_summary_links_to(response, "id_relationship_type")
        self.assert_focus_on_field(response, "id_relationship_type")

    def test_a_fresh_form_shows_no_summary_and_takes_no_focus(self):
        response = self.administrator.get(reverse("core:applicant-create"))
        content = response.content.decode()
        self.assertNotIn(SUMMARY, content)
        self.assertNotIn("autofocus", content)
