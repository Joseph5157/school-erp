"""Progress to Student and Reactivate student stop at a confirmation page."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from core import guardian_accounts as ga
from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    RelationshipType,
    Student,
    StudentStatusChange,
)
from core.tests.test_phase6_access_boundary import RETAIN, REVOKE, BoundaryFixture

User = get_user_model()


class LifecycleFixture:
    def setUp(self):
        admins = Group.objects.get(name="School Administrators")
        self.admin = User.objects.create_user("lc-admin", password="pass-12345")
        self.admin.groups.add(admins)
        self.client.login(username="lc-admin", password="pass-12345")
        self.viewer = User.objects.create_user("lc-viewer", password="pass-12345")
        self.viewer.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_applicant", "view_student"])
        )
        self.viewer_client = self.client_class()
        self.viewer_client.login(username="lc-viewer", password="pass-12345")


class ProgressConfirmTests(LifecycleFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=Guardian.objects.create(full_name="Meena Rao"),
            relationship_type=RelationshipType.MOTHER,
        )
        self.url = reverse("core:applicant-progress", args=[self.applicant.pk])

    def test_progress_page_lists_guardians_to_copy(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meena Rao")
        self.assertContains(response, "Mother")
        self.assertFalse(Student.objects.exists())

    def test_progress_page_says_no_placement_is_created(self):
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "This creates one Student record for Ravi Rao and copies the guardians "
            "listed here. It does not place the student in a class; placement is "
            "managed separately.",
        )
        self.assertContains(response, ">Progress to Student</button>")
        self.assertContains(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )

    def test_progress_post_creates_one_student(self):
        response = self.client.post(self.url)
        student = Student.objects.get()
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        self.assertEqual(student.guardian_links.count(), 1)

    def test_second_post_changes_nothing(self):
        self.client.post(self.url)
        response = self.client.post(self.url, follow=True)
        self.assertEqual(Student.objects.count(), 1)
        self.assertContains(response, "already progressed")

    def test_get_after_progress_redirects_with_message(self):
        self.client.post(self.url)
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.assertContains(response, "already progressed")

    def test_rejected_or_pending_applicant_redirects_with_message(self):
        pending = Applicant.objects.create(full_name="Pia Pending")
        rejected = Applicant.objects.create(full_name="Rex Rejected")
        rejected.record_admission_decision(
            Applicant.AdmissionStatus.REJECTED, reason="Not eligible"
        )
        for applicant in (pending, rejected):
            url = reverse("core:applicant-progress", args=[applicant.pk])
            for method in (self.client.get, self.client.post):
                response = method(url, follow=True)
                self.assertRedirects(
                    response, reverse("core:applicant-detail", args=[applicant.pk])
                )
                self.assertContains(response, "Only an accepted Applicant")
        self.assertFalse(Student.objects.exists())

    def test_detail_links_to_progress_page_and_has_no_inline_form(self):
        page = self.client.get(
            reverse("core:applicant-detail", args=[self.applicant.pk])
        ).content.decode()
        self.assertIn(f'href="{self.url}"', page)
        self.assertNotIn(f'action="{self.url}"', page)

    def test_view_only_user_is_forbidden(self):
        self.assertEqual(self.viewer_client.get(self.url).status_code, 403)
        self.assertEqual(self.viewer_client.post(self.url).status_code, 403)
        self.assertFalse(Student.objects.exists())


class ReactivateConfirmTests(LifecycleFixture, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Asha Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.student.record_status_change(
            Student.Status.INACTIVE, actor=self.admin, reason="Left"
        )
        self.url = reverse("core:student-reactivate-confirm", args=[self.student.pk])
        self.detail = reverse("core:student-detail", args=[self.student.pk])

    def test_get_renders_without_changing_anything(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, 'name="reason"')
        self.assertContains(response, ">Reactivate student</button>")
        self.assertContains(response, "This change has the following consequences:")
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)

    def test_reactivate_page_says_when_there_is_no_placement(self):
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "The student has no current placement. Placement is managed separately.",
        )

    def test_reactivate_requires_reason(self):
        response = self.client.post(self.url, {"reason": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)

    def test_reactivate_records_reason_and_actor(self):
        response = self.client.post(self.url, {"reason": "Returned to school"})
        self.assertRedirects(response, self.detail)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        change = StudentStatusChange.objects.get(
            student=self.student, new_status=Student.Status.ACTIVE
        )
        self.assertEqual(change.reason, "Returned to school")
        self.assertEqual(change.changed_by, self.admin)

    def test_second_post_changes_nothing(self):
        self.client.post(self.url, {"reason": "Returned"})
        response = self.client.post(self.url, {"reason": "Again"}, follow=True)
        self.assertRedirects(response, self.detail)
        self.assertContains(response, "already active")
        self.assertEqual(self.student.status_changes.count(), 2)

    def test_active_student_get_redirects_with_message(self):
        self.client.post(self.url, {"reason": "Returned"})
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, self.detail)
        self.assertContains(response, "already active")

    def test_status_change_endpoint_refuses_reactivation_without_reason(self):
        response = self.client.post(
            reverse("core:student-status-change", args=[self.student.pk]),
            {"status": "ACTIVE"},
        )
        self.assertRedirects(response, self.url)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)

    def test_detail_links_to_reactivate_page_and_has_no_inline_form(self):
        page = self.client.get(self.detail).content.decode()
        self.assertIn(f'href="{self.url}"', page)
        self.assertIn("Reactivate student&hellip;", page)
        self.assertNotIn('name="status" value="ACTIVE"', page)

    def test_view_only_user_is_forbidden(self):
        self.assertEqual(self.viewer_client.get(self.url).status_code, 403)
        response = self.viewer_client.post(self.url, {"reason": "x"})
        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)


class ReactivateConsequenceTests(BoundaryFixture, TestCase):
    """The consequence lines describe what reactivation really does."""

    def setUp(self):
        super().setUp()
        self.second = ga.grant_student_access(
            student_guardian=self.relate(self.asha, self.other), actor=self.admin
        )
        self.asha.record_status_change(
            Student.Status.INACTIVE, actor=self.admin,
            access_decisions={self.asha_grant.pk: RETAIN, self.second.pk: REVOKE},
            reason="Left",
        )
        self.url = reverse("core:student-reactivate-confirm", args=[self.asha.pk])

    def test_reactivate_page_says_placement_is_unchanged(self):
        response = self.client.get(self.url)
        self.assertContains(
            response,
            f"The current placement, {escape(str(self.asha_e))}, is unchanged.",
        )

    def test_reactivate_keeps_retained_grant_and_revoked_stays_revoked(self):
        page = self.client.get(self.url)
        self.assertContains(
            page,
            "Guardian portal access is not changed. Access revoked when the student "
            "was deactivated stays revoked.",
        )
        response = self.client.post(self.url, {"reason": "Returned"})
        self.assertEqual(response.status_code, 302)
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.ACTIVE)
        self.asha_grant.refresh_from_db()
        self.second.refresh_from_db()
        self.assertIsNone(self.asha_grant.revoked_at)
        self.assertIsNotNone(self.second.revoked_at)
