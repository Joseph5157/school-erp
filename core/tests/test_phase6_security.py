"""Phase 6 Gate 7: throttling, sessions, revocation and privacy hardening (ADR 0013)."""

import time
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.checks import run_checks
from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import security
from accounts.forms import GENERIC_ERROR
from accounts.middleware import SEEN_KEY, STARTED_KEY
from accounts.models import LoginFailure, SecurityEvent
from core.tests.test_phase6_access_boundary import BoundaryFixture

User = get_user_model()
Event = SecurityEvent.EventType


class SourceAddressTests(TestCase):
    def request(self, remote, forwarded=None):
        meta = {"REMOTE_ADDR": remote}
        if forwarded:
            meta["HTTP_X_FORWARDED_FOR"] = forwarded
        return RequestFactory().get("/", **meta)

    def test_forwarded_header_ignored_without_trusted_proxies(self):
        request = self.request("203.0.113.9", forwarded="198.51.100.1")
        self.assertEqual(security.client_address(request), "203.0.113.9")

    @override_settings(TRUSTED_PROXIES=["10.0.0.0/8"])
    def test_trusted_proxy_uses_rightmost_untrusted_hop(self):
        request = self.request("10.0.0.5", forwarded="198.51.100.7, 203.0.113.4, 10.0.0.9")
        self.assertEqual(security.client_address(request), "203.0.113.4")
        spoofed = self.request("203.0.113.9", forwarded="1.2.3.4")  # not from a proxy
        self.assertEqual(security.client_address(spoofed), "203.0.113.9")

    def test_canonical_ipv6_and_hash_only(self):
        request = self.request("2001:DB8:0:0:0:0:0:1")
        self.assertEqual(security.client_address(request), "2001:db8::1")
        key = security.source_key(request)
        self.assertEqual(len(key), 64)
        self.assertNotIn("2001", key)


class ThrottlingFixture(BoundaryFixture):
    def attempt(self, password, username="meena", remote="203.0.113.10"):
        client = self.client_class(REMOTE_ADDR=remote)
        return client.post(reverse("login"), {"username": username, "password": password})

    def signed_in(self, response):
        return response.status_code == 302

    def fail(self, times, remote="203.0.113.10", username="meena"):
        for _ in range(times):
            self.attempt("wrong-password", username=username, remote=remote)


class ThrottlingTests(ThrottlingFixture, TestCase):
    def test_rule_a_refuses_even_the_right_password(self):
        self.fail(5)
        response = self.attempt(self.password)
        self.assertFalse(self.signed_in(response))
        self.assertContains(response, GENERIC_ERROR)
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.LOGIN_THROTTLED).exists())
        # Another network source is not affected by Rule A.
        self.assertTrue(self.signed_in(self.attempt(self.password, remote="198.51.100.20")))

    def test_rule_b_refuses_across_sources(self):
        for i in range(20):
            self.fail(1, remote=f"198.51.100.{i + 1}")
        self.assertFalse(self.signed_in(self.attempt(self.password, remote="192.0.2.99")))

    def test_window_and_expiry(self):
        self.fail(5)
        LoginFailure.objects.update(occurred_at=timezone.now() - timedelta(minutes=16))
        self.assertTrue(self.signed_in(self.attempt(self.password)))
        LoginFailure.objects.create(username_key="meena", source_key="x",
                                    occurred_at=timezone.now() - timedelta(hours=25))
        self.attempt("wrong")
        self.assertFalse(LoginFailure.objects.filter(source_key="x").exists())

    def test_success_clears_rule_a_failures_for_that_source(self):
        self.fail(4)
        self.assertTrue(self.signed_in(self.attempt(self.password)))
        self.assertFalse(LoginFailure.objects.filter(username_key="meena").exists())

    def test_messages_are_identical(self):
        inactive = User.objects.create_user(username="gone", password="pass-12345")
        inactive.is_active = False
        inactive.save()
        bodies = []
        for username, password in (("nobody", "x"), ("meena", "wrong"), ("gone", "pass-12345")):
            response = self.attempt(password, username=username, remote="192.0.2.50")
            self.assertContains(response, GENERIC_ERROR)
            bodies.append(response.context["form"].errors.as_text())
        self.fail(5, remote="192.0.2.51")
        throttled = self.attempt(self.password, remote="192.0.2.51")
        bodies.append(throttled.context["form"].errors.as_text())
        self.assertEqual(len(set(bodies)), 1)

    def test_events_never_store_attempted_text_or_raw_address(self):
        self.attempt("SecretAttempt!", username="nobody-here")
        self.attempt("SecretAttempt!", username="meena")
        for event in SecurityEvent.objects.filter(event_type=Event.LOGIN_FAILED):
            flattened = f"{event.detail} {event.source_key}"
            self.assertNotIn("SecretAttempt", flattened)
            self.assertNotIn("nobody-here", flattened)
            self.assertNotIn("203.0.113.10", flattened)
        subjects = list(SecurityEvent.objects.filter(
            event_type=Event.LOGIN_FAILED).values_list("subject_user", flat=True))
        self.assertEqual(sorted(subjects, key=lambda s: s or 0), [None, self.user.pk])

    def test_success_event(self):
        self.attempt(self.password)
        event = SecurityEvent.objects.get(event_type=Event.LOGIN_SUCCEEDED)
        self.assertEqual((event.subject_user, event.event_class), (self.user, "ROUTINE"))


class LockoutAdministrationTests(ThrottlingFixture, TestCase):
    def test_admin_lists_and_clears(self):
        self.fail(5)
        page = self.client.get(reverse("core:login-lockouts"))
        self.assertEqual(page.context["locked"], ["meena"])
        self.client.post(reverse("core:login-lockouts"), {"username": "meena"})
        self.assertTrue(self.signed_in(self.attempt(self.password)))
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.LOCKOUT_CLEARED).exists())

    def test_teacher_cannot_clear(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.assertEqual(teacher.get(reverse("core:login-lockouts")).status_code, 403)


class SessionLimitTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def age_session(self, key, seconds):
        session = self.portal.session
        session[key] = time.time() - seconds
        session.save()

    def test_idle_limit(self):
        self.assertEqual(self.portal.get(reverse("portal:home")).status_code, 200)
        self.age_session(SEEN_KEY, 31 * 60)
        response = self.portal.get(reverse("portal:home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_activity_keeps_session_alive(self):
        self.age_session(SEEN_KEY, 29 * 60)
        self.assertEqual(self.portal.get(reverse("portal:home")).status_code, 200)
        self.assertEqual(self.portal.get(reverse("portal:home")).status_code, 200)

    def test_absolute_limit(self):
        self.age_session(STARTED_KEY, 8 * 60 * 60 + 60)
        response = self.portal.get(reverse("portal:home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_deactivation_ends_sessions(self):
        version = self.user.session_version
        self.user.is_active = False
        self.user.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.session_version, version + 1)
        response = self.portal.get(reverse("portal:home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))


class PurgeCommandTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        old = timezone.now() - timedelta(days=400)
        self.old_routine = SecurityEvent.objects.create(event_type=Event.LOGIN_FAILED,
                                                        event_class="ROUTINE", occurred_at=old)
        self.old_history = SecurityEvent.objects.create(event_type=Event.ACCOUNT_CREATED,
                                                        event_class="HISTORY", occurred_at=old)
        self.recent = SecurityEvent.record(Event.LOGIN_FAILED)
        self.operator = User.objects.create_user(username="operator")
        self.operator.user_permissions.add(Permission.objects.get(codename="purge_securityevent"))

    def test_requires_permission(self):
        with self.assertRaises(CommandError):
            call_command("purge_security_events", by="admin", stdout=StringIO())

    def test_purges_only_old_routine_events_and_records_it(self):
        out = StringIO()
        call_command("purge_security_events", by="operator", dry_run=True, stdout=out)
        self.assertIn("1 routine event(s) would be purged", out.getvalue())
        self.assertTrue(SecurityEvent.objects.filter(pk=self.old_routine.pk).exists())
        call_command("purge_security_events", by="operator", stdout=StringIO())
        remaining = set(SecurityEvent.objects.values_list("pk", flat=True))
        self.assertNotIn(self.old_routine.pk, remaining)
        self.assertTrue({self.old_history.pk, self.recent.pk} <= remaining)
        purge = SecurityEvent.objects.get(event_type=Event.SECURITY_EVENTS_PURGED)
        self.assertEqual((purge.event_class, purge.detail["count"]), ("HISTORY", 1))


class DeploymentSettingsTests(TestCase):
    @override_settings(
        DEBUG=False,
        SECRET_KEY="k" * 20 + "VeryLongRandomProductionSecretKeyValue-0123456789abcdef",
        ALLOWED_HOSTS=["erp.school.example"],
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
    )
    def test_deploy_checks_clean_with_production_settings(self):
        issues = [m for m in run_checks(include_deployment_checks=True)
                  if m.id.startswith("security.")]
        self.assertEqual(issues, [])

    def test_cookie_defaults(self):
        from django.conf import settings

        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.SESSION_IDLE_SECONDS, 1800)
        self.assertEqual(settings.SESSION_ABSOLUTE_SECONDS, 28800)
