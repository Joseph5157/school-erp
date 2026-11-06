"""Security Gate 2: deployment safety (audit run-1, fingerprint config/settings.py:SECRET_KEY:hardcoded-insecure-fallback).

Production must not start with a missing, blank or committed-fallback secret key, and an
unrecognised value for a transport-security flag or a malformed proxy list must stop startup
instead of silently weakening it. Debug and test runs are unchanged.

Every key and address here is a made-up test value.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.deployment_safety import (
    check_secret_key,
    parse_flag,
    parse_trusted_proxies,
    resolve_https,
)

STRONG_KEY = "Zx9-test-only-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJ"
COMMITTED_STYLE_KEY = "django-insecure-" + "a1b2c3d4" * 6
BASE_DIR = Path(settings.BASE_DIR)


class SecretKeyRuleTests(SimpleTestCase):
    def test_production_refuses_a_missing_blank_or_insecure_key(self):
        for label, key in {
            "committed-style django-insecure- key": COMMITTED_STYLE_KEY,
            "blank": "",
            "whitespace only": "   ",
        }.items():
            with self.subTest(label):
                with self.assertRaises(ImproperlyConfigured):
                    check_secret_key(key, debug=False, testing=False)

    def test_the_error_names_the_variable_and_never_echoes_the_key(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            check_secret_key(COMMITTED_STYLE_KEY, debug=False, testing=False)
        message = str(caught.exception)
        self.assertIn("DJANGO_SECRET_KEY", message)
        self.assertNotIn(COMMITTED_STYLE_KEY, message)
        self.assertNotIn("a1b2c3d4", message)

    def test_a_real_looking_key_is_accepted(self):
        check_secret_key(STRONG_KEY, debug=False, testing=False)

    def test_debug_and_test_runs_keep_working_without_a_real_key(self):
        check_secret_key(COMMITTED_STYLE_KEY, debug=True, testing=False)
        check_secret_key("", debug=True, testing=False)
        check_secret_key(COMMITTED_STYLE_KEY, debug=False, testing=True)


class FlagParsingTests(SimpleTestCase):
    def test_recognised_spellings(self):
        for raw in ("True", "true", "TRUE", " 1 ", "yes", "on"):
            with self.subTest(raw):
                self.assertTrue(parse_flag("DJANGO_HTTPS", raw))
        for raw in ("False", "false", "0", "no", "off", ""):
            with self.subTest(raw):
                self.assertFalse(parse_flag("DJANGO_HTTPS", raw, default=True))

    def test_unset_uses_the_default(self):
        self.assertFalse(parse_flag("DJANGO_HTTPS", None))
        self.assertTrue(parse_flag("EMAIL_USE_TLS", None, default=True))

    def test_an_unrecognised_value_stops_startup_and_names_the_variable(self):
        for raw in ("ture", "enabled", "2", "tru e"):
            with self.subTest(raw):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    parse_flag("DJANGO_HTTPS", raw)
                self.assertIn("DJANGO_HTTPS", str(caught.exception))


class HttpsResolutionTests(SimpleTestCase):
    """HTTPS must never be silently lost in production."""

    def test_production_defaults_to_https_when_unset_or_blank(self):
        for raw in (None, "", "   "):
            with self.subTest(repr(raw)):
                self.assertTrue(resolve_https(raw, debug=False, testing=False))

    def test_production_accepts_an_explicit_true(self):
        for raw in ("True", "true", "1", "yes", "on"):
            with self.subTest(raw):
                self.assertTrue(resolve_https(raw, debug=False, testing=False))

    def test_production_refuses_an_explicit_false_and_names_the_variable(self):
        for raw in ("False", "false", "0", "no", "off"):
            with self.subTest(raw):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    resolve_https(raw, debug=False, testing=False)
                self.assertIn("DJANGO_HTTPS", str(caught.exception))

    def test_production_refuses_a_mistyped_value_and_names_the_variable(self):
        for raw in ("ture", "enabled", "2"):
            with self.subTest(raw):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    resolve_https(raw, debug=False, testing=False)
                self.assertIn("DJANGO_HTTPS", str(caught.exception))
                self.assertNotIn(raw, str(caught.exception).replace("DJANGO_HTTPS", ""))

    def test_debug_and_test_runs_keep_the_plain_http_default(self):
        for flags in ({"debug": True, "testing": False}, {"debug": False, "testing": True}):
            with self.subTest(flags):
                self.assertFalse(resolve_https(None, **flags))
                self.assertFalse(resolve_https("False", **flags))
                self.assertTrue(resolve_https("True", **flags))


class TrustedProxyParsingTests(SimpleTestCase):
    def test_valid_entries_are_kept_in_order(self):
        self.assertEqual(
            parse_trusted_proxies("10.0.0.0/8, 192.0.2.7 ,2001:db8::/32"),
            ["10.0.0.0/8", "192.0.2.7", "2001:db8::/32"],
        )

    def test_empty_means_no_trusted_proxy(self):
        self.assertEqual(parse_trusted_proxies(""), [])
        self.assertEqual(parse_trusted_proxies(" , "), [])

    def test_a_malformed_entry_stops_startup_without_echoing_it(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            parse_trusted_proxies("10.0.0.0/8, not-an-address")
        message = str(caught.exception)
        self.assertIn("DJANGO_TRUSTED_PROXIES", message)
        self.assertNotIn("not-an-address", message)


class SettingsImportTests(SimpleTestCase):
    """Importing config.settings in a clean process, the way gunicorn or manage.py does."""

    @staticmethod
    def run_python(code, **env):
        clean = {
            k: v for k, v in os.environ.items()
            if not k.startswith(("DJANGO_", "DB_", "EMAIL_", "PORTAL_"))
        }
        clean.update(env)
        return subprocess.run(
            [sys.executable, "-c", code], cwd=BASE_DIR, env=clean,
            capture_output=True, text=True, timeout=120,
        )

    def load_settings(self, **env):
        code = "import sys; sys.argv = ['manage.py', 'runserver']; import config.settings"
        return self.run_python(code, **env)

    def read_settings(self, names, **env):
        """Import settings in a clean process and return the named values, or the failed result."""
        code = (
            "import sys; sys.argv = ['manage.py', 'runserver']; import config.settings as s; "
            f"print(repr([getattr(s, n, None) for n in {list(names)!r}]))"
        )
        result = self.run_python(code, **env)
        if result.returncode != 0:
            return None, result
        return eval(result.stdout.strip().splitlines()[-1]), result  # noqa: S307 - our own repr

    TRANSPORT = ("HTTPS", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT",
                 "SECURE_HSTS_SECONDS", "SECURE_HSTS_PRELOAD")

    def test_production_without_djangohttps_defaults_to_full_https_protection(self):
        values, result = self.read_settings(self.TRANSPORT, DJANGO_SECRET_KEY=STRONG_KEY)
        self.assertEqual(values, [True, True, True, True, 31536000, False], result.stderr)

    def test_production_with_a_blank_djangohttps_defaults_to_https(self):
        values, result = self.read_settings(self.TRANSPORT, DJANGO_SECRET_KEY=STRONG_KEY,
                                            DJANGO_HTTPS="")
        self.assertEqual(values[:4], [True, True, True, True], result.stderr)

    def test_production_with_djangohttps_false_does_not_start(self):
        for raw in ("False", "false", "0", "off"):
            with self.subTest(raw):
                values, result = self.read_settings(self.TRANSPORT, DJANGO_SECRET_KEY=STRONG_KEY,
                                                    DJANGO_HTTPS=raw)
                self.assertIsNone(values)
                self.assertIn("DJANGO_HTTPS", result.stderr)

    def test_debug_keeps_plain_http_for_local_development(self):
        values, result = self.read_settings(self.TRANSPORT, DJANGO_DEBUG="True")
        self.assertEqual(values, [False, False, False, False, 0, False], result.stderr)
        values, result = self.read_settings(self.TRANSPORT, DJANGO_DEBUG="True",
                                            DJANGO_HTTPS="False")
        self.assertEqual(values[0], False, result.stderr)

    def test_the_ci_environment_starts(self):
        """CI sets a placeholder key and DEBUG False, and nothing else."""
        values, result = self.read_settings(
            self.TRANSPORT, DJANGO_SECRET_KEY="ci-only-not-a-real-secret", DJANGO_DEBUG="False"
        )
        self.assertIsNotNone(values, result.stderr)

    def test_hsts_preload_stays_optional_and_false_is_valid(self):
        for raw, expected in ((None, False), ("False", False), ("false", False),
                              ("True", True)):
            with self.subTest(repr(raw)):
                env = {"DJANGO_SECRET_KEY": STRONG_KEY}
                if raw is not None:
                    env["DJANGO_HSTS_PRELOAD"] = raw
                values, result = self.read_settings(self.TRANSPORT, **env)
                self.assertEqual(values[5], expected, result.stderr)

    def test_a_mistyped_hsts_preload_flag_does_not_start(self):
        values, result = self.read_settings(self.TRANSPORT, DJANGO_SECRET_KEY=STRONG_KEY,
                                            DJANGO_HSTS_PRELOAD="tru")
        self.assertIsNone(values)
        self.assertIn("DJANGO_HSTS_PRELOAD", result.stderr)

    def test_a_staging_style_configuration_starts_with_everything_enabled(self):
        values, result = self.read_settings(
            self.TRANSPORT + ("SECURE_PROXY_SSL_HEADER", "TRUSTED_PROXIES", "ALLOWED_HOSTS"),
            DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_HTTPS="True",
            DJANGO_TRUSTED_PROXIES="100.64.0.0/10", DJANGO_ALLOWED_HOSTS="erp.school.example",
        )
        self.assertEqual(
            values,
            [True, True, True, True, 31536000, False,
             ("HTTP_X_FORWARDED_PROTO", "https"), ["100.64.0.0/10"], ["erp.school.example"]],
            result.stderr,
        )

    def test_production_without_a_secret_key_does_not_start(self):
        result = self.load_settings()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_with_the_committed_fallback_style_key_does_not_start(self):
        result = self.load_settings(DJANGO_SECRET_KEY=COMMITTED_STYLE_KEY)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(COMMITTED_STYLE_KEY, result.stderr + result.stdout)

    def test_production_with_a_real_key_starts(self):
        result = self.load_settings(DJANGO_SECRET_KEY=STRONG_KEY)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_debug_without_a_key_still_starts_for_local_development(self):
        result = self.load_settings(DJANGO_DEBUG="True")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_misspelled_https_flag_does_not_silently_turn_https_off(self):
        result = self.load_settings(DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_HTTPS="ture")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_HTTPS", result.stderr)

    def test_lowercase_true_now_turns_https_on(self):
        code = (
            "import sys; sys.argv = ['manage.py', 'runserver']; import config.settings as s; "
            "print(s.HTTPS, s.SESSION_COOKIE_SECURE, s.SECURE_SSL_REDIRECT)"
        )
        result = self.run_python(code, DJANGO_SECRET_KEY=STRONG_KEY, DJANGO_HTTPS="true")
        self.assertEqual(result.stdout.strip(), "True True True", result.stderr)

    def test_a_malformed_proxy_list_does_not_start(self):
        result = self.load_settings(DJANGO_SECRET_KEY=STRONG_KEY,
                                    DJANGO_TRUSTED_PROXIES="10.0.0.0/8,bad entry")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_TRUSTED_PROXIES", result.stderr)

    def test_email_tls_flag_is_parsed_strictly(self):
        result = self.load_settings(DJANGO_SECRET_KEY=STRONG_KEY, EMAIL_HOST="smtp.example.test",
                                    EMAIL_USE_TLS="flase")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EMAIL_USE_TLS", result.stderr)
