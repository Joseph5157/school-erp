"""G-06 reset spec PR 2 (§4, §6): the improved office reset."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ResetNote, SecurityEvent
from core import guardian_accounts as ga
from core import guardian_records, portal_views
from core.checks import check_someone_can_reset
from core.models import Guardian, GuardianAccount
from core.tests.test_phase6_guardian_accounts import GuardianFixture

Event = SecurityEvent.EventType
Method = GuardianAccount.VerificationMethod
User = get_user_model()
RESET_GROUP = "Portal password resets"


def not_recent():
    """No recent phone change, and the contact audit older than 30 days."""
    quiet = guardian_records.PhoneHistory(recent=False)
    return mock.patch.multiple(
        "core.guardian_accounts", phone_changed_recently=mock.Mock(return_value=quiet)
    )


def not_recent_view():
    quiet = guardian_records.PhoneHistory(recent=False)
    return mock.patch.object(guardian_records, "phone_changed_recently", return_value=quiet)


class Fixture(GuardianFixture):
    def setUp(self):
        super().setUp()
        self.admin.groups.add(Group.objects.get(name=RESET_GROUP))
        self.account, _ = self.create_account()

    def plain_admin(self, username="plainadmin"):
        user = User.objects.create_user(username=username, password="pass-12345")
        user.groups.add(Group.objects.get(name="School Administrators"))
        return user

    def reset_url(self, account=None):
        return reverse("core:guardian-account-reset-password", args=[(account or self.account).pk])

    def token(self):
        return self.client.get(self.reset_url()).context["one_time_token"]

    def post_reset(self, **data):
        return self.client.post(
            self.reset_url(), {"one_time_token": self.token(), "confirmed": "on", **data}
        )

    def resets(self):
        return SecurityEvent.objects.filter(event_type=Event.PASSWORD_RESET_BY_ADMIN)


class ServiceRuleTests(Fixture, TestCase):
    def reset(self, method, note=""):
        return ga.reset_guardian_password(account=self.account, actor=self.admin,
                                          method=method, note=note)

    def test_in_person_reset_records_method_and_stays_routine(self):
        self.reset(Method.IN_PERSON_DOCUMENTS)
        event = self.resets().get()
        self.assertEqual(event.detail, {"method": Method.IN_PERSON_DOCUMENTS})
        self.assertEqual(event.event_class, SecurityEvent.EventClass.ROUTINE)
        self.assertFalse(ResetNote.objects.exists())

    def test_method_must_be_a_reset_method(self):
        for bad in ("", Method.EXISTING_RECORDS, "KNOWN_TO_STAFF"):
            with self.subTest(method=bad), self.assertRaises(ValidationError):
                self.reset(bad)
        self.assertFalse(self.resets().exists())

    def test_in_person_refuses_a_note(self):
        with self.assertRaises(ValidationError):
            self.reset(Method.IN_PERSON_DOCUMENTS, "seen at desk")

    def test_other_needs_a_clean_short_note(self):
        with not_recent():
            for bad in ("", "x" * 101, "called 9845012345", "mail a@b.in", "call 98765 43210",
                        "98765-43210", "+91 98765 43210"):
                with self.subTest(note=bad), self.assertRaises(ValidationError):
                    self.reset(Method.OTHER, bad)
            self.reset(Method.OTHER, "Principal confirmed in the office")
        event = self.resets().get()
        self.assertEqual(event.detail, {"method": Method.OTHER})
        self.assertEqual(event.reset_note.note, "Principal confirmed in the office")

    def test_recent_phone_history_allows_only_in_person(self):
        # The test database's contact audit started moments ago, so phone history is "recent".
        self.assertTrue(guardian_records.phone_changed_recently(self.guardian).recent)
        with self.assertRaises(ValidationError):
            self.reset(Method.OTHER, "Principal confirmed")
        self.reset(Method.IN_PERSON_DOCUMENTS)

    def test_cannot_reset_own_login(self):
        with self.assertRaises(ValidationError):
            ga.reset_guardian_password(account=self.account, actor=self.account.user,
                                       method=Method.IN_PERSON_DOCUMENTS)

    def test_grants_untouched_sessions_end_change_forced(self):
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        version = self.account.user.session_version
        password = self.reset(Method.IN_PERSON_DOCUMENTS)
        grant.refresh_from_db()
        self.account.user.refresh_from_db()
        self.assertTrue(grant.is_active)
        self.assertGreater(self.account.user.session_version, version)
        self.assertTrue(self.account.user.must_change_password)
        self.assertEqual(len(password.replace("-", "")), 12)

    def test_note_is_deleted_with_its_event(self):
        # Reset events are ROUTINE, so the routine purge (after 365 days, enforced by a database
        # trigger) removes them; the note must go with them, not block the purge.
        from django.db import models
        self.assertIs(ResetNote._meta.get_field("event").remote_field.on_delete, models.CASCADE)


class PhoneWindowTests(Fixture, TestCase):
    def test_window_follows_events_and_the_audit_anchor(self):
        later = timezone.now() + timedelta(days=31)  # the anchor is then older than 30 days
        self.assertFalse(guardian_records.phone_changed_recently(self.guardian, now=later).recent)
        self.guardian.phone = "98450 00000"
        self.guardian.save(actor=self.admin)
        history = guardian_records.phone_changed_recently(self.guardian)
        self.assertTrue(history.recent)
        self.assertEqual(history.changed_by, self.admin)
        self.assertTrue(guardian_records.phone_changed_recently(
            self.guardian, now=timezone.now() + timedelta(days=29)).recent)


class ViewTests(Fixture, TestCase):
    def test_form_error_keeps_a_usable_token(self):
        response = self.client.post(self.reset_url(), {"one_time_token": self.token(),
                                                       "confirmed": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.resets().exists())
        response = self.client.post(self.reset_url(), {
            "one_time_token": response.context["one_time_token"], "confirmed": "on",
            "method": Method.IN_PERSON_DOCUMENTS})
        self.assertContains(response, "Password reset")
        self.assertEqual(self.resets().count(), 1)

    def test_confirmation_is_required(self):
        response = self.client.post(self.reset_url(), {
            "one_time_token": self.token(), "method": Method.IN_PERSON_DOCUMENTS})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.resets().exists())

    def test_recent_history_hides_other_and_warns(self):
        page = self.client.get(self.reset_url())
        self.assertContains(page, "Reset only after checking identity documents in person.")
        self.assertNotContains(page, 'value="OTHER"')
        self.assertNotContains(page, 'name="note"')
        with not_recent_view():
            self.assertContains(self.client.get(self.reset_url()), 'value="OTHER"')

    def test_same_actor_phone_change_is_named(self):
        self.guardian.phone = "98450 00000"
        self.guardian.save(actor=self.admin)
        self.assertContains(self.client.get(self.reset_url()), "You changed this number.")

    def test_slip_is_not_cached(self):
        response = self.post_reset(method=Method.IN_PERSON_DOCUMENTS)
        self.assertIn("no-store", response["Cache-Control"])

    def test_history_shows_method_and_note(self):
        with not_recent(), not_recent_view():
            self.post_reset(method=Method.OTHER, note="Principal <b>confirmed</b>")
        page = self.client.get(reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertContains(page, "(other)")
        self.assertContains(page, "Principal &lt;b&gt;confirmed&lt;/b&gt;")


class NamedStaffTests(Fixture, TestCase):
    def test_school_administrator_alone_gets_403(self):
        self.plain_admin()
        client = self.client_class()
        client.login(username="plainadmin", password="pass-12345")
        self.assertEqual(client.get(self.reset_url()).status_code, 403)

    def test_only_the_reset_group_holds_the_permission(self):
        holders = Group.objects.filter(permissions__codename="reset_guardian_password")
        self.assertEqual(list(holders.values_list("name", flat=True)), [RESET_GROUP])

    def test_member_and_superuser_get_200(self):
        self.assertEqual(self.client.get(self.reset_url()).status_code, 200)
        User.objects.create_superuser("root2", password="pass-12345")
        client = self.client_class()
        client.login(username="root2", password="pass-12345")
        self.assertEqual(client.get(self.reset_url()).status_code, 200)

    def test_system_check_warns_when_nobody_can_reset(self):
        self.assertEqual(check_someone_can_reset(), [])
        self.admin.groups.remove(Group.objects.get(name=RESET_GROUP))
        User.objects.filter(is_superuser=True).update(is_active=False)
        self.assertEqual([w.id for w in check_someone_can_reset()], ["core.W001"])

    def test_role_permission_gaps_lists_who_can_reset(self):
        out = StringIO()
        call_command("role_permission_gaps", stdout=out)
        self.assertIn("Who can reset guardian passwords (plus every active superuser):", out.getvalue())
        self.assertIn("admin (Portal password resets group)", out.getvalue())


class ReplacementTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        ga.revoke_account_link(account=self.account, actor=self.admin, reason="wrong person")

    def create(self, actor, method=Method.IN_PERSON_DOCUMENTS, note="Aadhaar card seen"):
        return ga.create_guardian_account(guardian=self.guardian, username="meena.new",
                                          method=method, note=note, actor=actor)

    def test_needs_the_reset_permission(self):
        with self.assertRaises(ValidationError):
            self.create(self.plain_admin())

    def test_existing_records_refused_and_in_person_allowed(self):
        with self.assertRaises(ValidationError):
            self.create(self.admin, method=Method.EXISTING_RECORDS)
        account, _ = self.create(self.admin)
        self.assertTrue(account.is_active)

    def test_other_follows_the_note_and_phone_rules(self):
        with self.assertRaises(ValidationError):  # recent: the audit just started
            self.create(self.admin, method=Method.OTHER, note="Principal confirmed")
        with not_recent(), self.assertRaises(ValidationError):
            self.create(self.admin, method=Method.OTHER, note="call 9845012345")

    def test_link_follows_the_same_rule(self):
        User.objects.create_user(username="other.login")
        with self.assertRaises(ValidationError):
            ga.link_existing_login(guardian=self.guardian, username="other.login",
                                   method=Method.IN_PERSON_DOCUMENTS, note="seen",
                                   actor=self.plain_admin())

    def test_plain_admin_post_to_create_or_link_creates_nothing(self):
        self.plain_admin()
        client = self.client_class()
        client.login(username="plainadmin", password="pass-12345")
        User.objects.create_user(username="other.login")
        posts = (
            ("core:guardian-account-create", {"username": "meena.new"}),
            ("core:guardian-account-link", {"username": "other.login"}),
        )
        for route, extra in posts:
            with self.subTest(route=route):
                response = client.post(reverse(route, args=[self.guardian.pk]), {
                    **extra, "identity_verification_method": Method.IN_PERSON_DOCUMENTS,
                    "identity_verification_note": "Aadhaar card seen",
                })
                self.assertContains(response, "Only staff who can reset parent passwords")
                self.assertFalse(GuardianAccount.objects.filter(
                    guardian=self.guardian, revoked_at__isnull=True).exists())

    def test_replacement_note_is_screened_for_personal_data(self):
        with self.assertRaises(ValidationError):
            self.create(self.admin, note="Seen, phone 98450 12345")

    def test_reset_page_for_a_revoked_link_goes_back_to_the_profile(self):
        response = self.client.get(self.reset_url())
        self.assertRedirects(response, reverse("core:guardian-detail", args=[self.guardian.pk]))

    def test_profile_hides_buttons_without_the_permission(self):
        self.plain_admin()
        client = self.client_class()
        client.login(username="plainadmin", password="pass-12345")
        page = client.get(reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertContains(page, "earlier login was revoked")
        self.assertNotContains(page, reverse("core:guardian-account-create", args=[self.guardian.pk]))

    def test_guardian_without_a_revoked_login_is_unchanged(self):
        fresh = Guardian.objects.create(full_name="New Parent")
        account, _ = ga.create_guardian_account(guardian=fresh, username="new.parent",
                                                method=Method.EXISTING_RECORDS, note="records",
                                                actor=self.plain_admin())
        self.assertTrue(account.is_active)


class PortalNoticeTests(Fixture, TestCase):
    def test_notice_shown_after_a_reset_and_not_after_30_days(self):
        ga.reset_guardian_password(account=self.account, actor=self.admin,
                                   method=Method.IN_PERSON_DOCUMENTS)
        user = self.account.user
        user.refresh_from_db()
        user.set_password("Garden-Path-2026")
        user.must_change_password = False
        user.save()
        client = self.client_class()
        client.login(username=user.username, password="Garden-Path-2026")
        self.assertContains(client.get(reverse("portal:home")),
                            "Your password was reset by the school on")
        self.assertIsNone(portal_views._reset_notice(user, now=timezone.now() + timedelta(days=31)))
