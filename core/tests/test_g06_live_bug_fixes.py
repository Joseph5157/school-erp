"""G-06 live-bug fixes (ADR 0029 R16, R19).

R19: a password change, including the forced first change, refuses a "new" password equal to the
current one, so a temporary password cannot be kept by re-entering it.
R16: an office reset (guardian or teacher) clears the login's sign-in lockout, so the new
temporary password is not refused, and the clear is audited when there was a lockout.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts import security
from accounts.forms import SAME_PASSWORD_ERROR
from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core import teacher_accounts
from core.tests.test_phase6_guardian_accounts import GuardianFixture

Event = SecurityEvent.EventType
User = get_user_model()


def lock(username):
    for n in range(security.RULE_B_LIMIT):  # Rule B: failures from any sources
        security.record_failure(username, f"source-{n}")


class SamePasswordRefusedTests(GuardianFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.account, self.password = self.create_account()
        self.guardian_client = self.client_class()
        self.guardian_client.login(username="meena.rao", password=self.password)

    def change(self, client, old, new):
        return client.post(reverse("password_change"), {
            "old_password": old, "new_password1": new, "new_password2": new})

    def test_forced_change_refuses_the_temporary_password(self):
        response = self.change(self.guardian_client, self.password, self.password)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SAME_PASSWORD_ERROR)
        self.account.user.refresh_from_db()
        self.assertTrue(self.account.user.must_change_password)
        self.assertFalse(SecurityEvent.objects.filter(event_type=Event.PASSWORD_CHANGED).exists())
        # Still forced: every other page goes back to the change form.
        self.assertRedirects(self.guardian_client.get(reverse("home")), reverse("password_change"),
                             fetch_redirect_response=False)

    def test_a_different_password_is_still_accepted(self):
        response = self.change(self.guardian_client, self.password, "Garden-Path-2026")
        self.assertEqual(response.status_code, 302)
        self.account.user.refresh_from_db()
        self.assertFalse(self.account.user.must_change_password)

    def test_an_ordinary_change_also_refuses_the_same_password(self):
        response = self.change(self.client, "pass-12345", "pass-12345")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SAME_PASSWORD_ERROR)


class ResetClearsLockoutTests(GuardianFixture, TestCase):
    def sign_in(self, username, password):
        client = self.client_class()
        response = client.post(reverse("login"), {"username": username, "password": password})
        return response.status_code == 302

    def test_guardian_reset_clears_a_lockout_and_audits_it(self):
        account, _ = self.create_account()
        lock("meena.rao")
        self.assertIn("meena.rao", security.locked_usernames())
        new = ga.reset_guardian_password(account=account, actor=self.admin)
        self.assertNotIn("meena.rao", security.locked_usernames())
        event = SecurityEvent.objects.get(event_type=Event.LOCKOUT_CLEARED)
        self.assertEqual((event.actor, event.subject_user), (self.admin, account.user))
        self.assertTrue(self.sign_in("meena.rao", new))

    def test_reset_without_a_lockout_records_no_lockout_event(self):
        account, _ = self.create_account()
        security.record_failure("meena.rao", "source-1")  # one failure is not a lockout
        ga.reset_guardian_password(account=account, actor=self.admin)
        self.assertFalse(SecurityEvent.objects.filter(event_type=Event.LOCKOUT_CLEARED).exists())
        self.assertNotIn("meena.rao", security.locked_usernames())

    def test_teacher_reset_clears_a_lockout_and_audits_it(self):
        teacher, _ = teacher_accounts.create_teacher(
            username="asha.rao", first_name="Asha", last_name="Rao", email="", actor=self.admin)
        lock("asha.rao")
        new = teacher_accounts.reset_teacher_password(user=teacher, actor=self.admin)
        self.assertNotIn("asha.rao", security.locked_usernames())
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=Event.LOCKOUT_CLEARED, subject_user=teacher).exists())
        self.assertTrue(self.sign_in("asha.rao", new))
