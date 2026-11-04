"""Guardian access changes ask first and name who they affect. All data is synthetic."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import (
    Applicant,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Student,
    StudentGuardian,
)
from core.tests.test_phase6_security import ThrottlingFixture

User = get_user_model()
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS
CLEARED = SecurityEvent.EventType.LOCKOUT_CLEARED


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class Base:
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345")
        applicant = Applicant.objects.create(admission_status="ACCEPTED", full_name="Asha Rao")
        self.student = Student.objects.create(applicant=applicant, full_name="Asha Rao")
        self.link = StudentGuardian.objects.create(
            student=self.student, guardian=self.guardian, relationship_type="MOTHER"
        )
        self.detail = reverse("core:guardian-detail", args=[self.guardian.pk])

    def account(self):
        account, _ = ga.create_guardian_account(
            guardian=self.guardian, username="meena.rao", method=METHOD, note="Checked in person", actor=self.admin
        )
        return account

    def grant(self):
        return ga.grant_student_access(student_guardian=self.link, actor=self.admin)

    def viewer(self, *codenames):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        return client


class GrantTests(Base, TestCase):
    def url(self):
        return reverse("core:guardian-access-grant", args=[self.link.pk])

    def test_grant_page_shows_guardian_username_student_relationship(self):
        self.account()
        response = self.client.get(self.url())
        self.assertContains(response, "Meena Rao")
        self.assertContains(response, "meena.rao")
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, "Mother")
        self.assertContains(response, ">Grant portal access</button>")
        self.assertFalse(GuardianStudentAccess.objects.exists())

    def test_grant_page_lists_visible_information(self):
        self.account()
        page = self.client.get(self.url()).content.decode()
        for text in ("admission number", "Submitted attendance", "Report cards", "School notices"):
            self.assertIn(text, page)
        self.assertIn("alert alert-warning", page)

    def test_grant_post_grants(self):
        response = self.client.post(self.url())
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.assertEqual(GuardianStudentAccess.objects.filter(revoked_at__isnull=True).count(), 1)
        self.assertEqual(messages_of(response), ["Portal access granted for this Student."])

    def test_second_post_changes_nothing(self):
        self.client.post(self.url())
        response = self.client.post(self.url())
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.assertEqual(GuardianStudentAccess.objects.count(), 1)
        self.assertTrue(messages_of(response))

    def test_get_when_already_granted_redirects_with_message(self):
        self.grant()
        response = self.client.get(self.url())
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.assertTrue(messages_of(response))
        self.assertEqual(GuardianStudentAccess.objects.count(), 1)

    def test_detail_page_links_to_confirmation_without_a_form(self):
        page = self.client.get(self.detail).content.decode()
        self.assertIn(f'href="{self.url()}"', page)
        self.assertNotIn(f'action="{self.url()}"', page)


class RevokeTests(Base, TestCase):
    def test_access_revoke_page_names_both_sides(self):
        self.account()
        grant = self.grant()
        url = reverse("core:guardian-access-revoke", args=[grant.pk])
        response = self.client.get(url)
        self.assertContains(response, "Revoke Meena Rao&#x27;s portal access to Asha Rao")
        self.assertContains(response, "meena.rao")
        self.assertContains(response, "Mother")
        self.assertContains(response, ">Revoke Student access</button>")
        self.assertContains(response, "alert alert-warning")
        self.client.post(url, {"reason": "Left the school"})
        grant.refresh_from_db()
        self.assertFalse(grant.is_active)

    def test_access_revoke_already_revoked_redirects_and_changes_nothing(self):
        grant = self.grant()
        ga.revoke_student_access(grant=grant, actor=self.admin, reason="First")
        url = reverse("core:guardian-access-revoke", args=[grant.pk])
        for response in (self.client.get(url), self.client.post(url, {"reason": "Again"})):
            self.assertRedirects(response, self.detail, fetch_redirect_response=False)
            self.assertTrue(messages_of(response))
        grant.refresh_from_db()
        self.assertEqual(grant.revocation_reason, "First")

    def test_account_revoke_page_says_what_happens(self):
        account = self.account()
        url = reverse("core:guardian-account-revoke", args=[account.pk])
        response = self.client.get(url)
        self.assertContains(response, "Meena Rao")
        self.assertContains(response, "meena.rao")
        self.assertContains(response, "Student access grants are not changed")
        self.assertContains(response, "Open sessions of this login end immediately")
        self.assertContains(response, ">Revoke account link</button>")
        self.client.post(url, {"reason": "Left the school"})
        account.refresh_from_db()
        self.assertFalse(account.is_active)

    def test_account_revoke_already_revoked_redirects(self):
        account = self.account()
        ga.revoke_account_link(account=account, actor=self.admin, reason="First")
        response = self.client.get(reverse("core:guardian-account-revoke", args=[account.pk]))
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.assertTrue(messages_of(response))

    def test_reset_page_names_guardian_and_username(self):
        account = self.account()
        response = self.client.get(reverse("core:guardian-account-reset-password", args=[account.pk]))
        self.assertContains(response, "Meena Rao")
        self.assertContains(response, "meena.rao")


class ConsentTests(Base, TestCase):
    def test_consent_button_says_record_consent_decision(self):
        page = self.client.get(self.detail).content.decode()
        self.assertIn(">Record consent decision</button>", page)


class LockoutTests(ThrottlingFixture, TestCase):
    def confirm(self, username="meena"):
        return reverse("core:login-lockout-clear-confirm") + f"?username={username}"

    def test_lockout_page_names_username_and_says_audited(self):
        self.fail(5)
        response = self.client.get(self.confirm())
        self.assertContains(response, "This lets meena try signing in again now. The action is recorded.")

    def test_lockout_list_links_to_confirmation(self):
        self.fail(5)
        page = self.client.get(reverse("core:login-lockouts")).content.decode()
        self.assertIn(f'href="{self.confirm()}"', page)

    def test_lockout_get_does_not_clear(self):
        self.fail(5)
        self.client.get(self.confirm())
        self.assertFalse(self.signed_in(self.attempt(self.password)))
        self.assertFalse(SecurityEvent.objects.filter(event_type=CLEARED).exists())

    def test_lockout_post_clears(self):
        self.fail(5)
        response = self.client.post(reverse("core:login-lockout-clear-confirm"), {"username": "meena"})
        self.assertRedirects(response, reverse("core:login-lockouts"), fetch_redirect_response=False)
        self.assertTrue(self.signed_in(self.attempt(self.password)))
        self.assertEqual(SecurityEvent.objects.filter(event_type=CLEARED).count(), 1)

    def test_lockout_unknown_username_redirects_with_message(self):
        for response in (
            self.client.get(self.confirm("nobody")),
            self.client.post(reverse("core:login-lockout-clear-confirm"), {"username": "nobody"}),
        ):
            self.assertRedirects(response, reverse("core:login-lockouts"), fetch_redirect_response=False)
            self.assertTrue(messages_of(response))
        self.assertFalse(SecurityEvent.objects.filter(event_type=CLEARED).exists())


class PermissionTests(Base, TestCase):
    def test_view_only_user_is_forbidden(self):
        account = self.account()
        grant = self.grant()
        routes = [
            reverse("core:guardian-access-grant", args=[self.link.pk]),
            reverse("core:guardian-access-revoke", args=[grant.pk]),
            reverse("core:guardian-account-revoke", args=[account.pk]),
            reverse("core:guardian-account-reset-password", args=[account.pk]),
            reverse("core:login-lockout-clear-confirm") + "?username=meena",
        ]
        client = self.viewer("view_guardian", "view_guardianaccount", "view_guardianstudentaccess")
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)
                self.assertEqual(client.post(url, {"reason": "x", "username": "meena"}).status_code, 403)
        self.assertTrue(GuardianStudentAccess.objects.get(pk=grant.pk).is_active)
