"""Security Gate 1: account protection (audit run-1, fingerprints below).

core/guardian_accounts.py:link_existing_login:privileged-target-link-reset
    A School Administrator could link a superuser, staff or other privileged login
    to a guardian, then reset its password or rename it through the guardian workflow.
hunt-auth:admin-login-throttle-bypass
    /admin/login/ skipped the ERP sign-in throttle, lockout and audit events.

All accounts here are synthetic.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts import security
from accounts.forms import GENERIC_ERROR
from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import TEACHERS_GROUP_NAME, GuardianAccount
from core.tests.test_phase6_guardian_accounts import METHOD, GuardianFixture

User = get_user_model()
Event = SecurityEvent.EventType
PASSWORD = "Correct-Horse-1"


class PrivilegedTargetFixture(GuardianFixture):
    def make_login(self, username, **extra):
        return User.objects.create_user(username=username, password=PASSWORD, **extra)

    def link(self, username):
        return ga.link_existing_login(
            guardian=self.guardian, username=username, method=METHOD,
            note="Seen in person", actor=self.admin,
        )

    def privileged_logins(self):
        """One login per way of holding authority beyond a plain teacher or parent."""
        superuser = self.make_login("root", is_superuser=True)
        staff = self.make_login("opsstaff", is_staff=True)
        office = self.make_login("otheroffice")
        office.groups.add(Group.objects.get(name="School Administrators"))
        direct = self.make_login("directperm")
        direct.user_permissions.add(Permission.objects.get(codename="view_student"))
        teacher_and_office = self.make_login("teacheroffice")
        teacher_and_office.groups.add(
            Group.objects.get(name=TEACHERS_GROUP_NAME),
            Group.objects.get(name="School Administrators"),
        )
        return {
            "superuser": superuser, "staff": staff, "School Administrators member": office,
            "direct permission": direct, "teacher who is also an administrator": teacher_and_office,
        }


class LinkEligibilityTests(PrivilegedTargetFixture, TestCase):
    def test_privileged_logins_cannot_be_linked(self):
        for label, user in self.privileged_logins().items():
            with self.subTest(label):
                with self.assertRaises(ValidationError):
                    self.link(user.username)
                self.assertFalse(GuardianAccount.objects.filter(user=user).exists())
        self.assertFalse(SecurityEvent.objects.filter(event_type=Event.ACCOUNT_LINKED).exists())

    def test_link_view_refuses_a_superuser_and_creates_nothing(self):
        root = self.make_login("root", is_superuser=True)
        response = self.client.post(
            reverse("core:guardian-account-link", args=[self.guardian.pk]),
            {"username": "root", "identity_verification_method": METHOD,
             "identity_verification_note": "Seen in person"},
        )
        self.assertEqual(response.status_code, 200)  # form redisplayed with an error
        self.assertFalse(GuardianAccount.objects.filter(user=root).exists())

    def test_a_teacher_who_is_also_a_parent_can_still_be_linked(self):
        teacher = self.make_login("meena.teacher")
        teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        account = self.link("meena.teacher")
        self.assertEqual(account.user, teacher)

    def test_a_plain_login_can_still_be_linked(self):
        self.make_login("meena.parent")
        self.assertTrue(self.link("meena.parent").is_active)


class ExistingLinkRecheckTests(PrivilegedTargetFixture, TestCase):
    """A login that gained authority after it was linked is no longer manageable here."""

    def linked_then_promoted(self):
        user = self.make_login("meena.parent")
        account = self.link("meena.parent")
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
        return user, account

    def test_password_reset_refused_after_the_login_gained_privileges(self):
        user, account = self.linked_then_promoted()
        with self.assertRaises(ValidationError):
            ga.reset_guardian_password(account=account, actor=self.admin)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.must_change_password)
        self.assertFalse(
            SecurityEvent.objects.filter(event_type=Event.PASSWORD_RESET_BY_ADMIN).exists()
        )

    def test_username_change_refused_after_the_login_gained_privileges(self):
        user, account = self.linked_then_promoted()
        with self.assertRaises(ValidationError):
            ga.change_guardian_username(account=account, new_username="renamed.root",
                                        actor=self.admin)
        user.refresh_from_db()
        self.assertEqual(user.username, "meena.parent")

    def test_reset_view_does_not_change_the_password_of_a_privileged_login(self):
        user, account = self.linked_then_promoted()
        self.client.post(
            reverse("core:guardian-account-reset-password", args=[account.pk]),
            {"confirm": "on"},
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_revoking_the_link_still_works_for_a_privileged_login(self):
        user, account = self.linked_then_promoted()
        revoked = ga.revoke_account_link(account=account, actor=self.admin, reason="Cleanup")
        self.assertFalse(revoked.is_active)

    def test_eligible_teacher_and_parent_still_gets_reset_and_rename(self):
        teacher = self.make_login("meena.teacher")
        teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        account = self.link("meena.teacher")
        password = ga.reset_guardian_password(account=account, actor=self.admin)
        teacher.refresh_from_db()
        self.assertTrue(teacher.check_password(password))
        self.assertEqual(
            ga.change_guardian_username(account=account, new_username="meena.t2",
                                        actor=self.admin),
            "meena.t2",
        )


class AdminLoginThrottleTests(TestCase):
    REMOTE = "203.0.113.50"

    def setUp(self):
        self.staff = User.objects.create_user(
            username="opsadmin", password=PASSWORD, is_staff=True, is_superuser=True
        )
        self.teacher = User.objects.create_user(username="plainteacher", password=PASSWORD)

    def admin_attempt(self, password, username="opsadmin", remote=None):
        client = self.client_class(REMOTE_ADDR=remote or self.REMOTE)
        response = client.post(
            reverse("admin:login"), {"username": username, "password": password, "next": "/admin/"}
        )
        return client, response

    def erp_attempt(self, password, username="opsadmin", remote=None):
        client = self.client_class(REMOTE_ADDR=remote or self.REMOTE)
        return client.post(reverse("login"), {"username": username, "password": password})

    @staticmethod
    def signed_in(client):
        return "_auth_user_id" in client.session

    def test_repeated_failures_at_the_admin_door_lock_out_the_right_password(self):
        for _ in range(5):
            self.admin_attempt("wrong-password")
        client, response = self.admin_attempt(PASSWORD)
        self.assertFalse(self.signed_in(client))
        self.assertNotEqual(response.status_code, 302)
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.LOGIN_FAILED).exists())
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.LOGIN_THROTTLED).exists())

    def test_the_admin_door_shares_the_erp_lockout(self):
        for _ in range(5):
            self.erp_attempt("wrong-password")
        client, _ = self.admin_attempt(PASSWORD)
        self.assertFalse(self.signed_in(client))  # locked at the ERP door, so locked here too

    def test_failures_at_the_admin_door_lock_the_erp_door_too(self):
        for _ in range(5):
            self.admin_attempt("wrong-password")
        self.assertNotEqual(self.erp_attempt(PASSWORD).status_code, 302)

    def test_a_staff_login_still_signs_in_and_is_audited(self):
        client, response = self.admin_attempt(PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.signed_in(client))
        self.assertTrue(
            SecurityEvent.objects.filter(event_type=Event.LOGIN_SUCCEEDED,
                                         subject_user=self.staff).exists()
        )

    def test_a_non_staff_login_is_still_refused_at_the_admin_door(self):
        client, response = self.admin_attempt(PASSWORD, username="plainteacher")
        self.assertFalse(self.signed_in(client))
        self.assertNotEqual(response.status_code, 302)
        self.assertTrue(
            SecurityEvent.objects.filter(event_type=Event.LOGIN_FAILED,
                                         subject_user=self.teacher).exists()
        )

    def test_a_non_staff_login_cannot_probe_passwords_without_limit(self):
        for _ in range(5):
            self.admin_attempt(PASSWORD, username="plainteacher")  # right password, wrong door
        source = security.source_key(RequestFactory().get("/", REMOTE_ADDR=self.REMOTE))
        self.assertTrue(security.is_throttled("plainteacher", source))

    def test_admin_door_failure_text_is_the_generic_message(self):
        _, unknown = self.admin_attempt("x", username="nobody")
        _, wrong = self.admin_attempt("x")
        self.assertEqual(unknown.context["form"].non_field_errors(),
                         wrong.context["form"].non_field_errors())
        self.assertEqual(wrong.context["form"].non_field_errors(), [GENERIC_ERROR])
