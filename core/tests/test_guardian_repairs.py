"""Completed-scope repairs: Student-Guardian administration and Guardian editing."""

from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse

from core.models import (
    Applicant,
    Guardian,
    GuardianStudentAccess,
    RelationshipType,
    StudentGuardian,
)
from core.notifications import whatsapp_link
from core.tests.test_authorization import AuthorizationClientsMixin


def make_student(name):
    applicant = Applicant.objects.create(full_name=name)
    applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
    return applicant.progress_to_student()


class StudentGuardianAddTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = make_student("Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao", phone="9876543210")
        self.url = reverse("core:student-guardian-add", args=[self.student.pk])
        self.payload = {
            "guardian": self.guardian.pk,
            "relationship_type": RelationshipType.MOTHER,
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.payload)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(StudentGuardian.objects.exists())

    def test_non_admin_is_forbidden(self):
        self.assertEqual(self.non_admin.post(self.url, self.payload).status_code, 403)
        self.assertFalse(StudentGuardian.objects.exists())

    def test_administrator_attaches_guardian_to_existing_student(self):
        response = self.administrator.post(self.url, self.payload)
        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        link = StudentGuardian.objects.get()
        self.assertEqual((link.student, link.guardian), (self.student, self.guardian))
        self.assertEqual(link.relationship_type, RelationshipType.MOTHER)

    def test_one_guardian_can_have_several_students(self):
        sibling = make_student("Mira Rao")
        self.administrator.post(self.url, self.payload)
        self.administrator.post(
            reverse("core:student-guardian-add", args=[sibling.pk]), self.payload
        )
        self.assertEqual(self.guardian.student_links.count(), 2)

    def test_duplicate_is_rejected_without_a_second_record(self):
        StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        response = self.administrator.post(self.url, self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already associated")
        self.assertEqual(StudentGuardian.objects.count(), 1)

    def test_missing_relationship_creates_nothing(self):
        response = self.administrator.post(self.url, {"guardian": self.guardian.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentGuardian.objects.exists())

    def test_unknown_student_is_404(self):
        url = reverse("core:student-guardian-add", args=[self.student.pk + 999])
        self.assertEqual(self.administrator.post(url, self.payload).status_code, 404)

    def test_student_page_offers_the_action(self):
        page = self.administrator.get(reverse("core:student-detail", args=[self.student.pk]))
        self.assertContains(page, self.url)


class StudentGuardianRelationshipChangeTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = make_student("Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao")
        self.link = StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian,
            relationship_type=RelationshipType.OTHER,
        )
        self.url = reverse("core:student-guardian-edit", args=[self.link.pk])

    def test_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"relationship_type": RelationshipType.MOTHER})
        self.assertEqual(response.status_code, 403)

    def test_administrator_changes_relationship_only(self):
        response = self.administrator.post(self.url, {"relationship_type": RelationshipType.MOTHER})
        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.link.refresh_from_db()
        self.assertEqual(self.link.relationship_type, RelationshipType.MOTHER)
        self.assertEqual((self.link.student, self.link.guardian), (self.student, self.guardian))

    def test_invalid_value_is_rejected(self):
        response = self.administrator.post(self.url, {"relationship_type": "NEIGHBOUR"})
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.relationship_type, RelationshipType.OTHER)


class GuardianEditTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.guardian = Guardian.objects.create(full_name="Asha Rao", phone="bad")
        self.url = reverse("core:guardian-edit", args=[self.guardian.pk])
        self.payload = {"full_name": "Asha Rao", "phone": "9876543210", "email": "a@example.com"}

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.payload)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_non_admin_is_forbidden(self):
        self.assertEqual(self.non_admin.post(self.url, self.payload).status_code, 403)
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.phone, "bad")

    def test_administrator_fixes_phone_and_email(self):
        response = self.administrator.post(self.url, self.payload)
        self.assertRedirects(response, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.phone, "9876543210")
        self.assertEqual(self.guardian.email, "a@example.com")

    def test_blank_name_is_rejected(self):
        response = self.administrator.post(self.url, {**self.payload, "full_name": ""})
        self.assertEqual(response.status_code, 200)
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.full_name, "Asha Rao")

    def test_detail_page_links_to_edit(self):
        page = self.administrator.get(reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertContains(page, self.url)


class CrossPhaseBoundaryTests(AuthorizationClientsMixin, TestCase):
    """The repairs must not widen Phase 6 access or bypass Phase 7 phone handling."""

    def setUp(self):
        super().setUp()
        self.student = make_student("Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao", phone="not a phone")

    def test_new_link_grants_no_portal_access(self):
        self.administrator.post(
            reverse("core:student-guardian-add", args=[self.student.pk]),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.MOTHER},
        )
        self.assertEqual(StudentGuardian.objects.count(), 1)
        self.assertFalse(GuardianStudentAccess.objects.exists())

    def test_relationship_change_touches_no_access_records(self):
        link = StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian,
            relationship_type=RelationshipType.OTHER,
        )
        self.administrator.post(
            reverse("core:student-guardian-edit", args=[link.pk]),
            {"relationship_type": RelationshipType.MOTHER},
        )
        self.assertFalse(GuardianStudentAccess.objects.exists())

    def test_fixing_the_phone_makes_the_whatsapp_link_available(self):
        notification = SimpleNamespace(
            guardian=self.guardian,
            parameters={},
            template=SimpleNamespace(body="Hello"),
        )
        self.assertIsNone(whatsapp_link(notification))
        self.administrator.post(
            reverse("core:guardian-edit", args=[self.guardian.pk]),
            {"full_name": "Asha Rao", "phone": "9876543210", "email": ""},
        )
        self.guardian.refresh_from_db()
        self.assertIn("wa.me/", whatsapp_link(notification))
