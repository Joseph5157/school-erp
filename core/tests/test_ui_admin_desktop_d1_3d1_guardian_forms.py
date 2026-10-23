"""UI-D1-3D1: the three legacy Guardian forms adopt the shared form layout.

Views, forms, URLs and permissions are unchanged. All names are synthetic.
"""

import re

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    RelationshipType,
    Student,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture

LONG_NAME = "Venkataraghavan Subramaniam Ramachandran-Krishnamurthy Iyengar"


class GuardianFormsD13D1Tests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        self.applicant = Applicant.objects.create(full_name="Asha Testfield")
        accepted = Applicant.objects.create(full_name="Ravi Testfield", admission_status="ACCEPTED")
        self.student = Student.objects.create(applicant=accepted, full_name="Ravi Testfield")
        self.guardian = Guardian.objects.create(
            full_name="Meena Testfield", phone="555-0100", email="meena@example.test"
        )

    # helpers
    def get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def form_html(self, content):
        match = re.search(r'<form method="post" class="erp-form">.*?</form>', content, re.S)
        self.assertIsNotNone(match, "erp-form not found")
        return match.group(0)

    def field_names(self, content):
        form = self.form_html(content)
        return [
            n for n in re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', form)
            if n != "csrfmiddlewaretoken"
        ]

    def assert_shared_layout(self, content, eyebrow, submit):
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertIn(f'<p class="erp-page-eyebrow">{eyebrow}</p>', content)
        form = self.form_html(content)
        self.assertIn("csrfmiddlewaretoken", form)
        self.assertIn("erp-required-legend", form)
        self.assertIn('class="erp-form-actions"', form)
        self.assertIn("erp-field", form)
        self.assertNotIn("<p>", form)  # no form.as_p
        self.assertEqual(form.count(f">{submit}</button>"), 1)
        self.assertEqual(form.count(">Cancel</a>"), 1)
        self.assertNotIn(" action=", form)

    def assert_cancel(self, content, url):
        self.assertIn(f'<a class="btn btn-link" href="{url}">Cancel</a>', self.form_html(content))

    # Guardian create / edit
    def test_guardian_create_layout_and_fields(self):
        url = reverse("core:guardian-create")
        content = self.get(url)
        self.assert_shared_layout(content, "People", "Save guardian")
        self.assertIn("Create Guardian", content)
        self.assert_cancel(content, reverse("core:guardian-list"))
        self.assertEqual(self.field_names(content), ["full_name", "phone", "email"])
        self.assertIn("<title>", content)

    def test_guardian_edit_layout_prefill_and_cancel(self):
        content = self.get(reverse("core:guardian-edit", args=[self.guardian.pk]))
        self.assert_shared_layout(content, "People", "Save guardian")
        self.assertIn("Edit Meena Testfield", content)
        self.assert_cancel(content, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertEqual(self.field_names(content), ["full_name", "phone", "email"])
        for value in ("Meena Testfield", "555-0100", "meena@example.test"):
            self.assertIn(f'value="{value}"', content)

    def test_guardian_names_are_escaped_and_long_names_render(self):
        g = Guardian.objects.create(full_name='<script>x</script> ' + LONG_NAME)
        content = self.get(reverse("core:guardian-edit", args=[g.pk]))
        self.assertNotIn("<script>x</script>", content)
        self.assertIn("&lt;script&gt;", content)
        self.assertEqual(content.count("<h1"), 1)

    def test_guardian_create_invalid_keeps_values_and_shows_error_once(self):
        before = Guardian.objects.count()
        response = self.client.post(
            reverse("core:guardian-create"),
            {"full_name": "", "phone": "555-0199", "email": "not-an-email"},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(Guardian.objects.count(), before)
        self.assertIn('value="555-0199"', content)
        self.assertIn('value="not-an-email"', content)
        self.assertEqual(content.count("This field is required."), 1)
        self.assertEqual(content.count("Enter a valid email address."), 1)
        self.assertEqual(content.count("<h1"), 1)
        self.assertEqual(content.count("erp-field-errors"), 2)

    def test_guardian_create_and_edit_post_succeed_with_same_destinations(self):
        response = self.client.post(
            reverse("core:guardian-create"), {"full_name": "New Parent", "phone": "", "email": ""}
        )
        self.assertRedirects(response, reverse("core:guardian-list"))
        self.assertTrue(Guardian.objects.filter(full_name="New Parent").exists())
        response = self.client.post(
            reverse("core:guardian-edit", args=[self.guardian.pk]),
            {"full_name": "Meena Renamed", "phone": "", "email": ""},
        )
        self.assertRedirects(response, reverse("core:guardian-detail", args=[self.guardian.pk]))

    # Applicant guardian
    def applicant_url(self):
        return reverse("core:applicant-guardian-create", args=[self.applicant.pk])

    def test_applicant_guardian_layout_and_fields(self):
        content = self.get(self.applicant_url())
        self.assert_shared_layout(content, "Admissions", "Save guardian link")
        self.assertIn("Asha Testfield", content)
        self.assert_cancel(content, reverse("core:applicant-detail", args=[self.applicant.pk]))
        self.assertEqual(self.field_names(content), ["guardian", "relationship_type"])
        self.assertNotIn('name="applicant"', content)

    def test_applicant_guardian_invalid_missing_required(self):
        response = self.client.post(self.applicant_url(), {"guardian": "", "relationship_type": ""})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(ApplicantGuardian.objects.count(), 0)
        self.assertEqual(content.count("This field is required."), 2)
        self.assertEqual(content.count("<h1"), 1)

    def test_applicant_guardian_duplicate_shows_form_error_once_and_keeps_values(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant, guardian=self.guardian, relationship_type=RelationshipType.MOTHER
        )
        response = self.client.post(
            self.applicant_url(),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.FATHER},
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(ApplicantGuardian.objects.count(), 1)
        self.assertEqual(content.count("This Guardian is already associated with this Applicant."), 1)
        self.assertIn("erp-form-errors", content)
        self.assertIn('role="alert"', content)
        self.assertRegex(content, rf'<option value="{self.guardian.pk}" selected>')
        self.assertRegex(content, r'<option value="FATHER" selected>')

    def test_applicant_guardian_valid_post_redirects(self):
        response = self.client.post(
            self.applicant_url(),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.MOTHER},
        )
        self.assertRedirects(response, reverse("core:applicant-detail", args=[self.applicant.pk]))
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    # Student guardian
    def add_url(self):
        return reverse("core:student-guardian-add", args=[self.student.pk])

    def test_student_guardian_create_layout_and_fields(self):
        content = self.get(self.add_url())
        self.assert_shared_layout(content, "People", "Save guardian link")
        self.assertIn("Associate Guardian with Ravi Testfield", content)
        self.assert_cancel(content, reverse("core:student-detail", args=[self.student.pk]))
        self.assertEqual(self.field_names(content), ["guardian", "relationship_type"])
        self.assertNotIn('name="student"', content)

    def link(self):
        return StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian, relationship_type=RelationshipType.MOTHER
        )

    def test_student_relationship_edit_is_relationship_only(self):
        link = self.link()
        content = self.get(reverse("core:student-guardian-edit", args=[link.pk]))
        self.assert_shared_layout(content, "People", "Save relationship")
        self.assertNotIn(">Save guardian link</button>", content)
        self.assertIn("Change relationship", content)
        self.assertIn("Meena Testfield", content)
        self.assertIn("Ravi Testfield", content)
        self.assert_cancel(content, reverse("core:student-detail", args=[self.student.pk]))
        self.assertEqual(self.field_names(content), ["relationship_type"])
        self.assertRegex(content, r'<option value="MOTHER" selected>')

    def test_student_guardian_duplicate_and_missing_required(self):
        self.link()
        response = self.client.post(
            self.add_url(),
            {"guardian": self.guardian.pk, "relationship_type": RelationshipType.FATHER},
        )
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudentGuardian.objects.count(), 1)
        self.assertEqual(content.count("This Guardian is already associated with this Student."), 1)
        self.assertRegex(content, r'<option value="FATHER" selected>')
        response = self.client.post(self.add_url(), {"guardian": "", "relationship_type": ""})
        self.assertEqual(response.content.decode().count("This field is required."), 2)
        self.assertEqual(StudentGuardian.objects.count(), 1)

    def test_student_relationship_edit_invalid_and_valid(self):
        link = self.link()
        url = reverse("core:student-guardian-edit", args=[link.pk])
        response = self.client.post(url, {"relationship_type": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count("This field is required."), 1)
        response = self.client.post(url, {"relationship_type": RelationshipType.FATHER})
        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        link.refresh_from_db()
        self.assertEqual(link.relationship_type, RelationshipType.FATHER)
        self.assertEqual(link.guardian_id, self.guardian.pk)
        self.assertEqual(link.student_id, self.student.pk)

    # Security
    def test_get_never_writes(self):
        link = self.link()
        counts = (Guardian.objects.count(), ApplicantGuardian.objects.count(), StudentGuardian.objects.count())
        for url in (
            reverse("core:guardian-create"),
            reverse("core:guardian-edit", args=[self.guardian.pk]),
            self.applicant_url(),
            self.add_url(),
            reverse("core:student-guardian-edit", args=[link.pk]),
        ):
            self.get(url)
        self.assertEqual(
            counts,
            (Guardian.objects.count(), ApplicantGuardian.objects.count(), StudentGuardian.objects.count()),
        )

    def test_denied_roles_unchanged(self):
        link = self.link()
        urls = [
            reverse("core:guardian-create"),
            reverse("core:guardian-edit", args=[self.guardian.pk]),
            self.applicant_url(),
            self.add_url(),
            reverse("core:student-guardian-edit", args=[link.pk]),
        ]
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        limited = self.make_user("limited")
        limited.user_permissions.add(Permission.objects.get(codename="view_guardian"))
        limited_client = self.client_class()
        limited_client.login(username="limited", password="pass-12345")
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(teacher.get(url).status_code, 403)
                self.assertEqual(limited_client.get(url).status_code, 403)
                self.assertEqual(self.client_class().get(url).status_code, 302)
        self.assertEqual(Guardian.objects.count(), 1)
