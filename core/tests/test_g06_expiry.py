"""G-06 reset spec PR 3 (§5, §4.6): temporary passwords expire; first sign-in after a reset."""
import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import security
from accounts.models import SecurityEvent
from config.deployment_safety import parse_start_time
from core import guardian_accounts as ga
from core import teacher_accounts
from core.tests.test_phase6_guardian_accounts import GuardianFixture

Event = SecurityEvent.EventType
User = get_user_model()
ON_LONG_AGO = override_settings(TEMP_PASSWORD_EXPIRY_FROM=timezone.now() - timedelta(days=60))


def backdate(user, *, issued=None, first_used=None):
    fields = {}
    if issued is not None:
        fields["temporary_password_issued_at"] = timezone.now() - issued
    if first_used is not None:
        fields["temporary_password_first_used_at"] = timezone.now() - first_used
    User.objects.filter(pk=user.pk).update(**fields)


def fresh(user):
    return User.objects.get(pk=user.pk)


class Fixture(GuardianFixture):
    def setUp(self):
        super().setUp()
        self.account, self.password = self.create_account()
        self.user = self.account.user

    def works(self, password=None):
        return authenticate(None, username=self.user.username,
                            password=password or self.password) is not None

    def sign_in_form(self, password=None):
        client = self.client_class()
        response = client.post(reverse("login"), {"username": self.user.username,
                                                  "password": password or self.password})
        return client, response


class SettingTests(TestCase):
    def test_parse_start_time(self):
        self.assertIsNone(parse_start_time("X", None))
        self.assertIsNone(parse_start_time("X", "  "))
        self.assertEqual(parse_start_time("X", "2027-01-15T09:00:00+05:30").utcoffset(),
                         timedelta(hours=5, minutes=30))
        for bad in ("tomorrow", "2027-01-15T09:00:00", "2027-13-01T00:00:00+00:00"):
            with self.subTest(value=bad), self.assertRaises(ImproperlyConfigured):
                parse_start_time("X", bad)


class IssueTests(Fixture, TestCase):
    def test_creation_and_reset_stamp_the_fields(self):
        self.assertEqual(fresh(self.user).temporary_password_kind, "CREATED")
        self.assertIsNotNone(fresh(self.user).temporary_password_issued_at)
        ga.reset_guardian_password(account=self.account, actor=self.admin,
                                   method="IN_PERSON_DOCUMENTS")
        self.assertEqual(fresh(self.user).temporary_password_kind, "RESET")
        self.assertIsNone(fresh(self.user).temporary_password_first_used_at)

    def test_teacher_create_and_reset_stamp_the_fields(self):
        teacher, _ = teacher_accounts.create_teacher(username="t.one", first_name="T",
                                                     last_name="One", email="", actor=self.admin)
        self.assertEqual(fresh(teacher).temporary_password_kind, "CREATED")
        root = User.objects.create_superuser("root", password="pass-12345")
        teacher_accounts.reset_teacher_password(user=teacher, actor=root)
        self.assertEqual(fresh(teacher).temporary_password_kind, "RESET")

    def test_linking_an_existing_login_sets_nothing(self):
        existing = User.objects.create_user(username="existing.login", password="pass-12345")
        other = type(self.guardian).objects.create(full_name="Other Parent")
        ga.link_existing_login(guardian=other, username="existing.login",
                               method="IN_PERSON_DOCUMENTS", note="seen", actor=self.admin)
        self.assertIsNone(fresh(existing).temporary_password_issued_at)


class ExpiryRuleTests(Fixture, TestCase):
    def test_off_without_the_switch(self):
        backdate(self.user, issued=timedelta(days=100))
        self.assertTrue(self.works())

    @ON_LONG_AGO
    def test_created_expires_after_14_days(self):
        backdate(self.user, issued=timedelta(days=13))
        self.assertTrue(self.works())
        backdate(self.user, issued=timedelta(days=15))
        self.assertFalse(self.works())

    @ON_LONG_AGO
    def test_reset_expires_after_72_hours(self):
        password = ga.reset_guardian_password(account=self.account, actor=self.admin,
                                              method="IN_PERSON_DOCUMENTS")
        backdate(self.user, issued=timedelta(hours=71))
        self.assertTrue(self.works(password))
        backdate(self.user, issued=timedelta(hours=73))
        self.assertFalse(self.works(password))

    def test_switch_on_gives_old_slips_a_full_window(self):
        backdate(self.user, issued=timedelta(days=30))
        with override_settings(TEMP_PASSWORD_EXPIRY_FROM=timezone.now()):
            self.assertTrue(self.works())
        with override_settings(TEMP_PASSWORD_EXPIRY_FROM=timezone.now() - timedelta(days=15)):
            self.assertFalse(self.works())

    @ON_LONG_AGO
    def test_one_hour_after_first_use(self):
        backdate(self.user, first_used=timedelta(minutes=30))
        self.assertTrue(self.works())
        backdate(self.user, first_used=timedelta(hours=2))
        self.assertFalse(self.works())

    @ON_LONG_AGO
    def test_missing_fields_never_expire_and_never_raise(self):
        User.objects.filter(pk=self.user.pk).update(temporary_password_issued_at=None)
        self.assertTrue(self.works())
        User.objects.filter(pk=self.user.pk).update(
            temporary_password_issued_at=timezone.now() - timedelta(days=30),
            temporary_password_kind="")
        self.assertTrue(self.works())

    @ON_LONG_AGO
    def test_same_response_as_a_wrong_password_and_one_event(self):
        backdate(self.user, issued=timedelta(days=15))
        _, expired = self.sign_in_form()
        _, wrong = self.sign_in_form("not-the-password")
        self.assertEqual(expired.status_code, wrong.status_code)
        self.assertEqual(expired.templates[0].name, wrong.templates[0].name)
        self.assertEqual(expired.context["form"].non_field_errors(),
                         wrong.context["form"].non_field_errors())
        self.sign_in_form()
        event = SecurityEvent.objects.get(event_type=Event.TEMPORARY_PASSWORD_EXPIRED)
        self.assertEqual((event.detail, event.guardian_id_ref), ({"kind": "CREATED"}, self.guardian.pk))
        self.assertEqual(event.event_class, SecurityEvent.EventClass.ROUTINE)

    @ON_LONG_AGO
    def test_a_new_reset_makes_sign_in_work_again(self):
        backdate(self.user, issued=timedelta(days=15))
        self.assertFalse(self.works())
        new = ga.reset_guardian_password(account=self.account, actor=self.admin,
                                         method="IN_PERSON_DOCUMENTS")
        self.assertTrue(self.works(new))

    @ON_LONG_AGO
    def test_signed_in_session_is_still_forced_to_change(self):
        client, _ = self.sign_in_form()
        backdate(self.user, issued=timedelta(days=15))
        self.assertRedirects(client.get(reverse("home")), reverse("password_change"),
                             fetch_redirect_response=False)


class FirstUseAndChangeTests(Fixture, TestCase):
    def test_form_sign_in_starts_the_grace_clock(self):
        self.sign_in_form()
        self.assertIsNotNone(fresh(self.user).temporary_password_first_used_at)

    def test_password_change_clears_the_fields(self):
        client, _ = self.sign_in_form()
        client.post(reverse("password_change"), {"old_password": self.password,
                                                 "new_password1": "Garden-Path-2026",
                                                 "new_password2": "Garden-Path-2026"})
        user = fresh(self.user)
        self.assertFalse(user.must_change_password)
        self.assertEqual((user.temporary_password_issued_at, user.temporary_password_kind,
                          user.temporary_password_first_used_at), (None, "", None))

    def test_first_sign_in_after_reset_recorded_once_for_a_guardian(self):
        password = ga.reset_guardian_password(account=self.account, actor=self.admin,
                                              method="IN_PERSON_DOCUMENTS")
        self.sign_in_form(password)
        self.sign_in_form(password)
        event = SecurityEvent.objects.get(event_type=Event.FIRST_SIGN_IN_AFTER_RESET)
        self.assertEqual((event.subject_user, event.guardian_id_ref), (self.user, self.guardian.pk))

    def test_no_first_sign_in_event_for_a_creation_slip_or_a_teacher(self):
        self.sign_in_form()
        teacher, _ = teacher_accounts.create_teacher(
            username="t.two", first_name="T", last_name="Two", email="", actor=self.admin)
        root = User.objects.create_superuser("root", password="pass-12345")
        reset = teacher_accounts.reset_teacher_password(user=teacher, actor=root)
        self.client_class().post(reverse("login"), {"username": "t.two", "password": reset})
        self.assertFalse(
            SecurityEvent.objects.filter(event_type=Event.FIRST_SIGN_IN_AFTER_RESET).exists())


class ReviewFixTests(Fixture, TestCase):
    def test_sign_in_before_switch_on_keeps_a_grace_hour_after_switch_on(self):
        self.sign_in_form()  # expiry off: starts the clock anyway
        backdate(self.user, first_used=timedelta(days=3))
        with override_settings(TEMP_PASSWORD_EXPIRY_FROM=timezone.now() - timedelta(minutes=10)):
            self.assertTrue(self.works())
        with override_settings(TEMP_PASSWORD_EXPIRY_FROM=timezone.now() - timedelta(hours=2)):
            self.assertFalse(self.works())

    def test_password_change_does_not_undo_a_reset_made_meanwhile(self):
        from accounts.forms import SamePasswordRefusingChangeForm

        stale = fresh(self.user)  # the login as the change request loaded it
        ga.reset_guardian_password(account=self.account, actor=self.admin,
                                   method="IN_PERSON_DOCUMENTS")
        reset = fresh(self.user)
        form = SamePasswordRefusingChangeForm(stale, {
            "old_password": self.password, "new_password1": "Garden-Path-2026",
            "new_password2": "Garden-Path-2026"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        after = fresh(self.user)
        self.assertEqual(after.session_version, reset.session_version)
        self.assertEqual(after.temporary_password_issued_at, reset.temporary_password_issued_at)
        self.assertTrue(after.check_password("Garden-Path-2026"))

    @ON_LONG_AGO
    def test_admin_door_refuses_expired_and_does_not_start_the_clock(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True)  # only staff pass the admin door
        backdate(self.user, issued=timedelta(days=15))
        response = self.client_class().post(reverse("admin:login"), {
            "username": self.user.username, "password": self.password})
        self.assertEqual(response.status_code, 200)  # form shown again, not signed in
        self.assertIsNone(fresh(self.user).temporary_password_first_used_at)

    def test_non_staff_at_the_admin_door_does_not_start_the_clock(self):
        self.client_class().post(reverse("admin:login"), {
            "username": self.user.username, "password": self.password})
        self.assertIsNone(fresh(self.user).temporary_password_first_used_at)

    def test_client_login_does_not_start_the_clock(self):
        self.client_class().login(username=self.user.username, password=self.password)
        self.assertIsNone(fresh(self.user).temporary_password_first_used_at)

    def test_switch_on_in_another_offset(self):
        from datetime import timezone as tz
        backdate(self.user, issued=timedelta(days=1))
        on = (timezone.now() - timedelta(days=2)).astimezone(tz(timedelta(hours=5, minutes=30)))
        with override_settings(TEMP_PASSWORD_EXPIRY_FROM=on):
            self.assertTrue(self.works())

    def test_teacher_slip_shows_works_until_when_switched_on(self):
        root = User.objects.create_superuser("root", password="pass-12345")
        teacher, _ = teacher_accounts.create_teacher(username="t.three", first_name="T",
                                                     last_name="Three", email="", actor=self.admin)
        client = self.client_class()
        client.login(username="root", password="pass-12345")
        url = reverse("core:teacher-reset-password", args=[teacher.pk])
        with ON_LONG_AGO:
            page = client.get(url)
            token = page.context.get("one_time_token") if page.context else None
            response = client.post(url, {"one_time_token": token} if token else {})
        self.assertContains(response, "This password works until")
        self.assertTrue(root)


class BackfillTests(TestCase):
    def test_backfill_and_reverse(self):
        migration = importlib.import_module("accounts.migrations.0012_temporary_password_expiry")
        pending = User.objects.create_user(username="pending", must_change_password=True)
        done = User.objects.create_user(username="done")
        migration.backfill(django_apps, None)
        self.assertEqual(fresh(pending).temporary_password_kind, "CREATED")
        self.assertIsNotNone(fresh(pending).temporary_password_issued_at)
        self.assertIsNone(fresh(done).temporary_password_issued_at)
        migration.clear(django_apps, None)
        self.assertIsNone(fresh(pending).temporary_password_issued_at)


class VisibleExpiryTests(Fixture, TestCase):
    def reset_slip(self):
        self.admin.groups.add(Group.objects.get(name="Portal password resets"))
        url = reverse("core:guardian-account-reset-password", args=[self.account.pk])
        token = self.client.get(url).context["one_time_token"]
        return self.client.post(url, {"one_time_token": token, "confirmed": "on",
                                      "method": "IN_PERSON_DOCUMENTS"})

    def test_slip_shows_works_until_only_when_switched_on(self):
        self.assertNotContains(self.reset_slip(), "This password works until")
        with ON_LONG_AGO:
            self.assertContains(self.reset_slip(), "This password works until")

    @ON_LONG_AGO
    def test_never_signed_in_list_marks_expired(self):
        ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        backdate(self.user, issued=timedelta(days=15))
        response = self.client.get(reverse("core:guardian-never-signed-in"))
        self.assertContains(response, ">Expired<")
        self.assertTrue(security.temporary_password_expired(fresh(self.user)))
