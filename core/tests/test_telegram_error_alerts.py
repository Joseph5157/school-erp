"""Telegram crash alerts: an optional, privacy-safe ping to the operator for unhandled 500s.

The Railway console log stays the authoritative record. Telegram only says "something broke,
look at the log". The alert is built from the same allow-list as the crash email (Security
Gate 4A), so it carries no personal data, and it must never leak the bot token or chat ID.

Every network call here is mocked; a guard fails any test that tries to open a real
connection. The token and chat ID below are made-up test values.
"""

import io
import json
import logging
import os
import subprocess
import sys
import threading
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.http import Http404, HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from config import telegram_alerts
from config.deployment_safety import telegram_alert_settings

TOKEN = "123456789:TEST-ONLY-fake-token_abcdefghijklmnop"
CHAT_ID = "-1009999000042"
NAME = "Asha Verma"
PHONE = "9876543210"
LOGIN = "meena.guardian"
SECRET_FILE = "/home/jdoe/private-dir/secret_module.py"
FAILURE_LINE = "Telegram crash alert delivery failed; see the Railway log."
BASE_DIR = Path(settings.BASE_DIR)


def crash_plain(request):
    guardian_phone = PHONE  # noqa: F841 - a local that must not reach the alert
    raise RuntimeError("plain")


def crash_other(request):
    raise TypeError("other")


def crash_value(request):
    raise ValueError(f"invalid literal for int() with base 10: '{NAME}'")


def crash_database(request):
    raise IntegrityError(f"DETAIL:  Key (username)=({LOGIN}) already exists.")


def crash_chained(request):
    try:
        raise KeyError(NAME)
    except KeyError as error:
        raise RuntimeError(f"could not reach {PHONE}") from error


def crash_named(request, name):
    raise RuntimeError(f"named route crashed for {name}")


def crash_external(request):
    code = compile("def boom():\n    raise RuntimeError('external')\n\nboom()\n", SECRET_FILE, "exec")
    exec(code, {})  # noqa: S102 - synthetic code, only to give a frame a sensitive filename


def forbidden(request):
    raise PermissionDenied


def missing(request):
    raise Http404("no such student")


def handled_500(request):
    return HttpResponse("handled failure", status=500)


def ok_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("crash/plain/", crash_plain),
    path("crash/other/", crash_other),
    path("crash/value/", crash_value),
    path("crash/database/", crash_database),
    path("crash/chained/", crash_chained),
    path("crash/named/<str:name>/", crash_named),
    path("crash/external/", crash_external),
    path("forbidden/", forbidden),
    path("missing/", missing),
    path("handled/", handled_500),
    path("ok/", ok_view),
]


def plain_403(request, exception=None):
    """The project's error pages need the full site's URLs; this URLconf only has the above."""
    return HttpResponse("forbidden", status=403)


def plain_404(request, exception=None):
    return HttpResponse("not found", status=404)


handler403, handler404 = plain_403, plain_404


class FakeResponse:
    def __init__(self, body=b'{"ok": true, "result": {"message_id": 1}}', status=200):
        self.body, self.status = body, status

    def read(self, amount=-1):
        return self.body if amount is None or amount < 0 else self.body[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status=401):
    """An HTTPError that, like the real one, carries the token-bearing URL and a body."""
    body = io.BytesIO(b'{"ok": false, "description": "Unauthorized ' + TOKEN.encode() + b'"}')
    return HTTPError(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", status, "Unauthorized", Message(), body
    )


def real_network(*args, **kwargs):
    raise AssertionError("a test tried to open a real network connection")


class NoNetworkMixin:
    """Mocks the Telegram transport and fails on any real outgoing connection."""

    def setUp(self):
        super().setUp()
        telegram_alerts.COOLDOWN.clear()
        self.addCleanup(telegram_alerts.COOLDOWN.clear)
        guard = mock.patch("socket.create_connection", side_effect=real_network)
        self.network_guard = guard.start()
        self.addCleanup(guard.stop)
        transport = mock.patch("config.telegram_alerts.urlopen", return_value=FakeResponse())
        self.urlopen = transport.start()
        self.addCleanup(transport.stop)

    def requests(self):
        return [call.args[0] for call in self.urlopen.call_args_list]

    def payloads(self):
        return [json.loads(request.data) for request in self.requests()]

    def only_text(self):
        payloads = self.payloads()
        self.assertEqual(len(payloads), 1)
        return payloads[0]["text"]

    def assert_absent(self, text, *values):
        for value in values:
            with self.subTest(absent=value):
                self.assertNotIn(value, text)


CONFIGURED = dict(
    ROOT_URLCONF=__name__,
    TELEGRAM_ERROR_BOT_TOKEN=TOKEN,
    TELEGRAM_ERROR_CHAT_ID=CHAT_ID,
    ERP_INSTANCE_NAME="st-marys",
    ADMINS=[],
    DEBUG=False,
)


class PairedVariableTests(SimpleTestCase):
    """TELEGRAM_ERROR_BOT_TOKEN and TELEGRAM_ERROR_CHAT_ID are both set, or neither."""

    def test_both_absent_disables_alerts(self):
        self.assertEqual(telegram_alert_settings(None, None, debug=False, testing=False), ("", ""))

    def test_blank_values_behave_as_absent(self):
        for token, chat in (("", ""), ("   ", ""), ("", "  "), (" \t", "\n")):
            with self.subTest(token=token, chat=chat):
                self.assertEqual(
                    telegram_alert_settings(token, chat, debug=False, testing=False), ("", "")
                )

    def test_both_set_enables_alerts_in_production(self):
        self.assertEqual(
            telegram_alert_settings(f" {TOKEN} ", f" {CHAT_ID} ", debug=False, testing=False),
            (TOKEN, CHAT_ID),
        )

    def test_token_without_chat_id_stops_startup_naming_only_the_missing_variable(self):
        for chat in (None, "", "   "):
            with self.subTest(chat=chat):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    telegram_alert_settings(TOKEN, chat, debug=False, testing=False)
                message = str(caught.exception)
                self.assertIn("TELEGRAM_ERROR_CHAT_ID", message)
                self.assertNotIn("TELEGRAM_ERROR_BOT_TOKEN", message)
                self.assert_secret_free(message)

    def test_chat_id_without_token_stops_startup_naming_only_the_missing_variable(self):
        for token in (None, "", "   "):
            with self.subTest(token=token):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    telegram_alert_settings(token, CHAT_ID, debug=False, testing=False)
                message = str(caught.exception)
                self.assertIn("TELEGRAM_ERROR_BOT_TOKEN", message)
                self.assertNotIn("TELEGRAM_ERROR_CHAT_ID", message)
                self.assert_secret_free(message)

    def test_a_half_configured_pair_is_refused_in_debug_and_test_runs_too(self):
        for flags in ({"debug": True, "testing": False}, {"debug": False, "testing": True}):
            with self.subTest(**flags), self.assertRaises(ImproperlyConfigured):
                telegram_alert_settings(TOKEN, "", **flags)

    def test_debug_and_test_runs_never_enable_alerts(self):
        for flags in ({"debug": True, "testing": False}, {"debug": False, "testing": True}):
            with self.subTest(**flags):
                self.assertEqual(telegram_alert_settings(TOKEN, CHAT_ID, **flags), ("", ""))

    def test_this_test_run_has_alerts_off_whatever_the_environment_says(self):
        self.assertEqual(settings.TELEGRAM_ERROR_BOT_TOKEN, "")
        self.assertEqual(settings.TELEGRAM_ERROR_CHAT_ID, "")
        self.assertFalse(telegram_alerts.alerts_configured())

    def assert_secret_free(self, text):
        for secret in (TOKEN, CHAT_ID, "123456789", "fake-token", "9999000042"):
            self.assertNotIn(secret, text)


class SettingsImportTests(SimpleTestCase):
    """Importing config.settings in a clean process, the way gunicorn or manage.py does."""

    NAMES = ["TELEGRAM_ERROR_BOT_TOKEN", "TELEGRAM_ERROR_CHAT_ID"]

    def read_settings(self, **env):
        clean = {
            k: v for k, v in os.environ.items()
            if not k.startswith(("DJANGO_", "DB_", "EMAIL_", "PORTAL_", "TELEGRAM_"))
        }
        clean["DJANGO_SECRET_KEY"] = "Zx9-test-only-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJ"
        clean.update(env)
        code = (
            "import sys; sys.argv = ['manage.py', 'runserver']; import config.settings as s; "
            f"print(repr([getattr(s, n, None) for n in {self.NAMES!r}]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=BASE_DIR, env=clean,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None, result
        return eval(result.stdout.strip().splitlines()[-1]), result  # noqa: S307 - our own repr

    def test_production_without_the_variables_starts_with_alerts_off(self):
        values, result = self.read_settings()
        self.assertEqual(values, ["", ""], result.stderr)

    def test_production_with_both_variables_enables_alerts(self):
        values, result = self.read_settings(
            TELEGRAM_ERROR_BOT_TOKEN=TOKEN, TELEGRAM_ERROR_CHAT_ID=CHAT_ID
        )
        self.assertEqual(values, [TOKEN, CHAT_ID], result.stderr)

    def test_production_with_only_the_token_does_not_start_and_does_not_echo_it(self):
        values, result = self.read_settings(TELEGRAM_ERROR_BOT_TOKEN=TOKEN)
        self.assertIsNone(values)
        error = self.startup_error(result)
        self.assertIn("TELEGRAM_ERROR_CHAT_ID", error)
        self.assertNotIn("TELEGRAM_ERROR_BOT_TOKEN", error)
        self.assertNotIn(TOKEN, result.stderr + result.stdout)
        self.assertNotIn("fake-token", result.stderr + result.stdout)

    def test_production_with_only_the_chat_id_does_not_start_and_does_not_echo_it(self):
        values, result = self.read_settings(TELEGRAM_ERROR_CHAT_ID=CHAT_ID)
        self.assertIsNone(values)
        error = self.startup_error(result)
        self.assertIn("TELEGRAM_ERROR_BOT_TOKEN", error)
        self.assertNotIn("TELEGRAM_ERROR_CHAT_ID", error)
        self.assertNotIn(CHAT_ID, result.stderr + result.stdout)
        self.assertNotIn("9999000042", result.stderr + result.stdout)

    def startup_error(self, result):
        """The ImproperlyConfigured line itself (the traceback above it quotes source code)."""
        lines = [line for line in result.stderr.splitlines()
                 if line.startswith("django.core.exceptions.ImproperlyConfigured")]
        self.assertEqual(len(lines), 1, result.stderr)
        return lines[0]

    def test_debug_with_both_variables_keeps_alerts_off(self):
        values, result = self.read_settings(
            DJANGO_DEBUG="True", TELEGRAM_ERROR_BOT_TOKEN=TOKEN, TELEGRAM_ERROR_CHAT_ID=CHAT_ID
        )
        self.assertEqual(values, ["", ""], result.stderr)


class LoggingConfigTests(SimpleTestCase):
    def test_telegram_sits_beside_the_crash_email_on_django_request(self):
        logger = logging.getLogger("django.request")
        kinds = {type(handler).__name__: handler for handler in logger.handlers}
        self.assertIn("PrivacyAdminEmailHandler", kinds)
        self.assertIn("TelegramAlertHandler", kinds)
        handler = kinds["TelegramAlertHandler"]
        self.assertEqual(handler.level, logging.ERROR)
        self.assertTrue(
            any(type(f).__name__ == "RequireDebugFalse" for f in handler.filters),
            "debug runs must never send",
        )
        self.assertTrue(logger.propagate, "the full traceback must still reach the console")

    def test_telegram_runs_before_the_crash_email(self):
        """SMTP may wait up to EMAIL_TIMEOUT (10 s); the Telegram ping must not wait behind it."""
        names = [type(handler).__name__ for handler in logging.getLogger("django.request").handlers]
        self.assertLess(names.index("TelegramAlertHandler"), names.index("PrivacyAdminEmailHandler"))
        self.assertEqual(settings.LOGGING["loggers"]["django.request"]["handlers"],
                         ["telegram_alerts", "mail_admins"])


@override_settings(**CONFIGURED)
class AlertScopeTests(NoNetworkMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client(raise_request_exception=False)

    def test_a_successful_request_sends_nothing(self):
        self.assertEqual(self.client.get("/ok/").status_code, 200)
        self.urlopen.assert_not_called()

    def test_403_and_404_send_nothing(self):
        self.assertEqual(self.client.get("/forbidden/").status_code, 403)
        self.assertEqual(self.client.get("/missing/").status_code, 404)
        self.assertEqual(self.client.get("/no-such-page/").status_code, 404)
        self.urlopen.assert_not_called()

    def test_a_deliberately_returned_500_without_an_exception_sends_nothing(self):
        self.assertEqual(self.client.get("/handled/").status_code, 500)
        self.urlopen.assert_not_called()

    def test_one_unhandled_500_sends_exactly_one_alert(self):
        self.assertEqual(self.client.get("/crash/plain/").status_code, 500)
        self.assertEqual(self.urlopen.call_count, 1)

    def test_the_request_is_a_json_https_post_with_a_short_timeout(self):
        self.client.get("/crash/plain/")
        request = self.requests()[0]
        self.assertTrue(request.full_url.startswith("https://api.telegram.org/bot"))
        self.assertTrue(request.full_url.endswith("/sendMessage"))
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(self.urlopen.call_args.kwargs["timeout"], 3)

    def test_the_payload_is_private_protected_plain_text_without_previews(self):
        self.client.get("/crash/plain/")
        payload = self.payloads()[0]
        self.assertEqual(payload["chat_id"], CHAT_ID)
        self.assertIs(payload["protect_content"], True)
        self.assertEqual(payload["link_preview_options"], {"is_disabled": True})
        self.assertNotIn("parse_mode", payload)
        self.assertNotIn("entities", payload)

    def test_the_same_500_still_reaches_the_console_with_its_traceback(self):
        with self.assertLogs(level="ERROR") as logs:  # the root logger, i.e. the console
            self.client.get(f"/crash/value/?q={PHONE}")
        record = next(r for r in logs.records if r.name == "django.request")
        self.assertIsNotNone(record.exc_info)
        self.assertIn(NAME, str(record.exc_info[1]))  # the private console keeps the detail
        self.assertEqual(self.urlopen.call_count, 1)

    @override_settings(ADMINS=[("ops", "ops@example.com")])
    def test_the_crash_email_is_unchanged_and_sent_alongside(self):
        self.client.get("/crash/plain/")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ops@example.com"])
        self.assertTrue(message.subject.endswith("ERROR: RuntimeError at /crash/plain/"))
        self.assertIn("Exception chain (outermost first).", message.body)
        self.assertIn("crash_plain", message.body)
        self.assertEqual(self.urlopen.call_count, 1)

    @override_settings(DEBUG=True)
    def test_debug_runs_send_nothing_even_when_configured(self):
        self.client.get("/crash/plain/")
        self.urlopen.assert_not_called()

    @override_settings(TELEGRAM_ERROR_BOT_TOKEN="", TELEGRAM_ERROR_CHAT_ID="")
    def test_unconfigured_means_no_alert_and_no_network(self):
        self.assertEqual(self.client.get("/crash/plain/").status_code, 500)
        self.urlopen.assert_not_called()
        self.network_guard.assert_not_called()


@override_settings(**CONFIGURED)
class AlertPrivacyTests(NoNetworkMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client(raise_request_exception=False)

    def alert(self, url, **extra):
        response = self.client.get(url, **extra)
        self.assertEqual(response.status_code, 500)
        return self.only_text()

    def test_the_alert_says_where_and_what(self):
        text = self.alert("/crash/plain/")
        self.assertTrue(text.startswith("School ERP error\n"))
        for expected in ("Instance: st-marys", "Time (UTC): ", "Status: 500",
                         "Request: GET /crash/plain/", "Exception: RuntimeError",
                         "crash_plain", "Railway logs"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_query_strings_and_concrete_path_values_are_absent(self):
        text = self.alert(f"/crash/named/Asha-Verma/?q={NAME.replace(' ', '+')}&phone={PHONE}")
        self.assert_absent(text, "Asha", "Verma", PHONE, "q=", "phone=", "?")
        self.assertIn("/crash/named/<str:name>/", text)

    def test_client_addresses_forwarded_chain_agent_and_referer_are_absent(self):
        text = self.alert(
            "/crash/plain/",
            REMOTE_ADDR="203.0.113.7",
            HTTP_X_FORWARDED_FOR="198.51.100.9, 192.0.2.44",
            HTTP_USER_AGENT="TestBrowser/9.9",
            HTTP_REFERER="https://school.example/students/?q=Asha",
        )
        self.assert_absent(text, "203.0.113.7", "198.51.100.9", "192.0.2.44", "TestBrowser",
                           "school.example", "HTTP_", "REMOTE_ADDR", "META")

    def test_the_signed_in_username_is_absent(self):
        user = get_user_model().objects.create_user(LOGIN, password="pass-12345")
        self.client.force_login(user)
        text = self.alert("/crash/plain/")
        self.assert_absent(text, LOGIN, "meena", "USER")

    def test_cookies_and_form_values_are_absent(self):
        self.client.cookies["sessionid"] = "secret-session-value"
        response = self.client.post("/crash/plain/", {"student_name": NAME, "password": "hunter2"})
        self.assertEqual(response.status_code, 500)
        text = self.only_text()
        self.assert_absent(text, "secret-session-value", "sessionid", NAME, "hunter2",
                           "student_name", "password")
        self.assertIn("Request: POST /crash/plain/", text)

    def test_exception_messages_and_database_row_details_are_absent(self):
        for url, kind, private in (
            ("/crash/value/", "ValueError", (NAME, "invalid literal")),
            ("/crash/database/", "IntegrityError", (LOGIN, "already exists", "DETAIL")),
            ("/crash/chained/", "KeyError", (NAME, PHONE, "could not reach")),
        ):
            with self.subTest(url=url):
                telegram_alerts.COOLDOWN.clear()
                self.urlopen.reset_mock()
                text = self.alert(url)
                self.assert_absent(text, *private)
                self.assertIn(kind, text)

    def test_traceback_local_variables_and_source_lines_are_absent(self):
        text = self.alert("/crash/plain/")
        self.assert_absent(text, PHONE, "guardian_phone", 'raise RuntimeError("plain")',
                           "Traceback (most recent call last)")

    def test_filesystem_locations_stay_sanitized_as_gate_4a_requires(self):
        text = self.alert("/crash/external/")
        self.assert_absent(text, "/home", "jdoe", "private-dir", SECRET_FILE, str(BASE_DIR),
                           str(BASE_DIR).replace("\\", "/"))
        self.assertIn("external/secret_module.py", text)
        frames = [line for line in text.splitlines() if " in " in line and ":" in line]
        self.assertTrue(frames)
        for line in frames:
            with self.subTest(frame=line):
                self.assertNotRegex(line.strip(), r"^([A-Za-z]:|/|\\)")

    def test_the_token_and_chat_id_never_appear_in_the_alert_text(self):
        text = self.alert("/crash/plain/")
        self.assert_absent(text, TOKEN, CHAT_ID, "api.telegram.org", "fake-token")


class AlertLengthTests(SimpleTestCase):
    """Telegram refuses messages over 4,096 characters; the alert must always fit."""

    def record_with_huge_chain(self):
        long_kinds = [type("E" * 3000 + str(n), (Exception,), {}) for n in range(6)]
        error = None
        for kind in long_kinds:
            try:
                raise kind("x")
            except Exception as raised:
                raised.__cause__ = error
                error = raised
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", (), None)
        record.exc_info = (type(error), error, error.__traceback__)
        record.status_code = 500
        record.request = mock.Mock(method="GET", resolver_match=mock.Mock(route="r/" * 3000))
        return record

    @override_settings(ERP_INSTANCE_NAME="st-marys")
    def test_an_oversized_alert_is_cut_to_fit_and_keeps_the_railway_pointer(self):
        text = telegram_alerts.build_alert_text(self.record_with_huge_chain())
        self.assertLessEqual(len(text), telegram_alerts.MAX_MESSAGE_LENGTH)
        self.assertLessEqual(telegram_alerts.MAX_MESSAGE_LENGTH, 4096)
        self.assertTrue(text.endswith("The full details are in Railway logs."))

    def test_the_fixed_test_message_fits(self):
        self.assertLessEqual(len(telegram_alerts.test_message_text()), 4096)


@override_settings(**CONFIGURED)
class DeliveryFailureTests(NoNetworkMixin, TestCase):
    """A failed alert never hides the crash, never raises and never leaks the configuration."""

    def setUp(self):
        super().setUp()
        self.client = Client(raise_request_exception=False)

    def crash_with_failing_transport(self, failure):
        self.urlopen.side_effect = None
        if isinstance(failure, FakeResponse):
            self.urlopen.return_value = failure
        else:
            self.urlopen.side_effect = failure
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr), self.assertLogs(level="WARNING") as logs:
            response = self.client.get("/crash/value/")
        self.assertEqual(response.status_code, 500)
        output = "\n".join(logs.output) + stderr.getvalue()
        return logs, output

    def assert_failure_reported_safely(self, logs, output):
        crash = [r for r in logs.records if r.name == "django.request"]
        self.assertEqual(len(crash), 1, "the original crash must still be logged")
        self.assertIsNotNone(crash[0].exc_info)
        warnings = [r for r in logs.records if r.name == "config.telegram_alerts"]
        self.assertEqual([r.getMessage() for r in warnings], [FAILURE_LINE])
        self.assertTrue(all(r.exc_info is None for r in warnings))
        for secret in (TOKEN, CHAT_ID, "api.telegram.org", "fake-token", "Unauthorized"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, output)

    def test_timeouts_and_connection_failures_are_swallowed(self):
        for failure in (TimeoutError("timed out"), URLError(TimeoutError("timed out")),
                        URLError(f"bot{TOKEN}"), ConnectionResetError(f"reset {CHAT_ID}"),
                        OSError(f"unreachable bot{TOKEN}")):
            with self.subTest(failure=type(failure).__name__):
                telegram_alerts.COOLDOWN.clear()
                self.assert_failure_reported_safely(*self.crash_with_failing_transport(failure))

    def test_an_http_failure_does_not_hide_the_original_console_log(self):
        for status in (400, 401, 429, 500):
            with self.subTest(status=status):
                telegram_alerts.COOLDOWN.clear()
                self.assert_failure_reported_safely(
                    *self.crash_with_failing_transport(http_error(status))
                )

    def test_a_malformed_or_negative_telegram_response_is_handled_safely(self):
        for body in (b"not json", b"[]", b'{"ok": false, "description": "bad"}', b"",
                     b'"ok"', b"\xff\xfe"):
            with self.subTest(body=body):
                telegram_alerts.COOLDOWN.clear()
                self.assert_failure_reported_safely(
                    *self.crash_with_failing_transport(FakeResponse(body))
                )

    def test_a_non_200_status_without_an_exception_is_a_failure(self):
        self.assert_failure_reported_safely(
            *self.crash_with_failing_transport(FakeResponse(status=202))
        )

    def test_an_unexpected_error_while_sending_is_swallowed(self):
        self.assert_failure_reported_safely(
            *self.crash_with_failing_transport(RuntimeError(f"bot{TOKEN} {CHAT_ID}"))
        )

    def test_the_handler_itself_never_raises(self):
        self.urlopen.side_effect = RuntimeError(TOKEN)
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", (), None)
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record.exc_info = sys.exc_info()
        record.status_code = 500
        with self.assertLogs("config.telegram_alerts", "WARNING"):
            telegram_alerts.TelegramAlertHandler().emit(record)

    def test_if_the_alert_cannot_be_built_a_generic_alert_still_goes_out(self):
        with mock.patch("config.telegram_alerts.crash_facts", side_effect=RuntimeError(NAME)):
            self.client.get("/crash/plain/")
        text = self.only_text()
        self.assert_absent(text, NAME, "Asha")
        self.assertIn("could not be built", text)
        self.assertIn("Railway logs", text)

    def test_delivery_is_not_retried_inside_the_failed_request(self):
        self.crash_with_failing_transport(TimeoutError())
        self.assertEqual(self.urlopen.call_count, 1)


@override_settings(**CONFIGURED)
class CooldownTests(NoNetworkMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client(raise_request_exception=False)

    def test_repeated_identical_errors_inside_the_cooldown_send_one_alert(self):
        for _ in range(5):
            self.client.get("/crash/plain/")
        self.assertEqual(self.urlopen.call_count, 1)

    def test_different_path_values_and_query_strings_count_as_the_same_error(self):
        self.client.get("/crash/named/Asha/?page=1")
        self.client.get("/crash/named/Ravi/?page=2")
        self.assertEqual(self.urlopen.call_count, 1)

    def test_a_different_error_inside_the_cooldown_still_alerts(self):
        self.client.get("/crash/plain/")
        self.client.get("/crash/other/")
        self.client.get("/crash/value/")
        self.assertEqual(self.urlopen.call_count, 3)

    def test_the_same_error_alerts_again_after_five_minutes(self):
        with mock.patch("config.telegram_alerts.time.monotonic", return_value=1000.0):
            self.client.get("/crash/plain/")
        with mock.patch("config.telegram_alerts.time.monotonic", return_value=1000.0 + 299):
            self.client.get("/crash/plain/")
        self.assertEqual(self.urlopen.call_count, 1)
        with mock.patch("config.telegram_alerts.time.monotonic", return_value=1000.0 + 301):
            self.client.get("/crash/plain/")
        self.assertEqual(self.urlopen.call_count, 2)

    def test_the_fingerprint_uses_only_safe_fields(self):
        self.client.get(f"/crash/named/{NAME.replace(' ', '-')}/?q={PHONE}")
        keys = " ".join(repr(key) for key in telegram_alerts.COOLDOWN.keys())
        self.assert_absent(keys, "Asha", PHONE, "named route crashed")
        self.assertIn("/crash/named/<str:name>/", keys)


class CooldownUnitTests(SimpleTestCase):
    def test_the_cooldown_is_thread_safe(self):
        cooldown = telegram_alerts.AlertCooldown()
        barrier = threading.Barrier(40)
        results = []

        def attempt():
            barrier.wait()
            results.append(cooldown.allow(("same",)))

        threads = [threading.Thread(target=attempt) for _ in range(40)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 39)

    def test_the_cooldown_is_bounded(self):
        cooldown = telegram_alerts.AlertCooldown(max_entries=10)
        for number in range(500):
            self.assertTrue(cooldown.allow(("error", number)))
        self.assertLessEqual(len(cooldown), 10)

    def test_the_default_window_is_five_minutes(self):
        self.assertEqual(telegram_alerts.AlertCooldown().window, 300)


TEST_TEXT = (
    "School ERP test alert\n\n"
    "Instance: st-marys\n"
    "This is a test message from the sendtesttelegram command. "
    "Crash alerts for this installation will arrive in this chat.\n\n"
    "No action is needed."
)


@override_settings(**CONFIGURED)
class SendTestTelegramCommandTests(NoNetworkMixin, SimpleTestCase):
    def run_command(self):
        out, err = io.StringIO(), io.StringIO()
        try:
            call_command("sendtesttelegram", stdout=out, stderr=err)
        finally:
            self.output = out.getvalue() + err.getvalue()
        return self.output

    def assert_config_free(self, text):
        for secret in (TOKEN, CHAT_ID, "api.telegram.org", "fake-token", "Unauthorized"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)

    def test_it_sends_only_the_fixed_test_text(self):
        output = self.run_command()
        payload = self.payloads()[0]
        self.assertEqual(payload["text"], TEST_TEXT)
        self.assertIs(payload["protect_content"], True)
        self.assertEqual(payload["link_preview_options"], {"is_disabled": True})
        self.assertNotIn("parse_mode", payload)
        self.assertIn("Telegram test alert sent.", output)
        self.assert_config_free(output)

    def test_it_bypasses_the_crash_cooldown(self):
        self.run_command()
        self.run_command()
        self.assertEqual(self.urlopen.call_count, 2)

    def test_a_delivery_failure_exits_with_a_generic_error(self):
        for failure in (http_error(401), URLError(f"bot{TOKEN}"), TimeoutError(),
                        RuntimeError(f"{TOKEN} {CHAT_ID}")):
            with self.subTest(failure=type(failure).__name__):
                self.urlopen.side_effect = failure
                stderr = io.StringIO()
                with mock.patch("sys.stderr", stderr), \
                        self.assertLogs("config.telegram_alerts", "WARNING") as logs, \
                        self.assertRaises(CommandError) as caught:
                    self.run_command()
                message = str(caught.exception)
                self.assertIn("could not be delivered", message)
                self.assert_config_free(message + self.output + stderr.getvalue()
                                        + "\n".join(logs.output))

    def test_a_negative_telegram_answer_is_a_failure(self):
        self.urlopen.return_value = FakeResponse(b'{"ok": false}')
        with self.assertLogs("config.telegram_alerts", "WARNING"), \
                self.assertRaises(CommandError):
            self.run_command()

    @override_settings(TELEGRAM_ERROR_BOT_TOKEN="", TELEGRAM_ERROR_CHAT_ID="")
    def test_it_requires_configuration_and_sends_nothing_without_it(self):
        with self.assertRaises(CommandError) as caught:
            self.run_command()
        message = str(caught.exception)
        self.assertIn("TELEGRAM_ERROR_BOT_TOKEN", message)
        self.assertIn("TELEGRAM_ERROR_CHAT_ID", message)
        self.urlopen.assert_not_called()
        self.network_guard.assert_not_called()
