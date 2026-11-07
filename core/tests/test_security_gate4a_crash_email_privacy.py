"""Security Gate 4A: crash emails are an allow-list report, not a masked copy of the request.

Crash emails go to a third-party mail provider, so they must carry nothing a student or
guardian could be identified by: no query-string search terms, no client addresses or
headers, no signed-in username, no exception message (a database error can quote the row),
and no concrete URL (a path can hold a name or an identifier). They keep what is needed to
find the bug: the exception types, the route pattern, the method and the traceback frames.
The Railway console log keeps the full detail for the operator.

Everything here uses Django's in-memory mail backend; nothing is sent.
"""

import logging
import os
import sysconfig
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from config import error_reporting

NAME = "Asha Verma"
PHONE = "9876543210"
LOGIN = "meena.guardian"


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
    raise RuntimeError("named route crashed")


def crash_plain(request):
    guardian_phone = PHONE  # noqa: F841 - a local that must not reach the email
    raise RuntimeError("plain")


SECRET_FILE = "/home/jdoe/private-dir/secret_module.py"


def crash_external(request):
    """A traceback frame whose file lives outside the project, with a private path."""
    code = compile("def boom():\n    raise RuntimeError('external')\n\nboom()\n", SECRET_FILE, "exec")
    exec(code, {})  # noqa: S102 - synthetic code, only to give a frame a sensitive filename


def ok_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("crash/external/", crash_external),
    path("crash/value/", crash_value),
    path("crash/database/", crash_database),
    path("crash/chained/", crash_chained),
    path("crash/named/<str:name>/", crash_named),
    path("crash/plain/", crash_plain),
    path("ok/", ok_view),
]


@override_settings(
    ROOT_URLCONF=__name__,
    ADMINS=[("ops", "ops@example.com")],
    EMAIL_SUBJECT_PREFIX="[school-erp st-marys] ",
    ERP_INSTANCE_NAME="st-marys",
    DEBUG=False,
)
class CrashEmailPrivacyTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def report(self, url, **extra):
        response = self.client.get(url, **extra)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        return message, message.subject + "\n" + message.body

    def assert_absent(self, text, *values):
        for value in values:
            with self.subTest(absent=value):
                self.assertNotIn(value, text)

    def test_search_terms_in_the_query_string_are_not_emailed(self):
        _, text = self.report(f"/crash/plain/?q={NAME.replace(' ', '+')}&phone={PHONE}&page=2")
        self.assert_absent(text, "Asha", "Verma", PHONE, "phone=", "q=", "page=2")

    def test_client_addresses_and_headers_are_not_emailed(self):
        _, text = self.report(
            "/crash/plain/",
            REMOTE_ADDR="203.0.113.7",
            HTTP_X_FORWARDED_FOR="198.51.100.9, 192.0.2.44",
            HTTP_USER_AGENT="TestBrowser/9.9",
            HTTP_REFERER="https://school.example/students/?q=Asha",
            HTTP_COOKIE="sessionid=secret-session-value",
        )
        self.assert_absent(
            text, "203.0.113.7", "198.51.100.9", "192.0.2.44", "TestBrowser", "school.example",
            "secret-session-value", "REMOTE_ADDR", "HTTP_", "META",
        )

    def test_exception_message_is_not_emailed_but_its_type_is(self):
        _, text = self.report("/crash/value/")
        self.assert_absent(text, NAME, "Asha", "invalid literal")
        self.assertIn("ValueError", text)

    def test_database_error_detail_is_not_emailed_but_its_type_is(self):
        _, text = self.report("/crash/database/")
        self.assert_absent(text, LOGIN, "already exists", "DETAIL")
        self.assertIn("IntegrityError", text)

    def test_chained_exception_messages_are_not_emailed_but_both_types_are(self):
        _, text = self.report("/crash/chained/")
        self.assert_absent(text, NAME, PHONE, "could not reach")
        self.assertIn("RuntimeError", text)
        self.assertIn("KeyError", text)

    def test_signed_in_username_is_not_emailed(self):
        user = get_user_model().objects.create_user(LOGIN, password="pass-12345")
        self.client.force_login(user)
        _, text = self.report("/crash/plain/")
        self.assert_absent(text, LOGIN, "USER")

    def test_a_path_holding_a_name_is_replaced_by_its_route(self):
        message, text = self.report("/crash/named/Asha-Verma/")
        self.assert_absent(text, "Asha-Verma", "Asha", "Verma")
        self.assertIn("/crash/named/<str:name>/", message.subject)
        self.assertIn("/crash/named/<str:name>/", message.body)

    def test_the_report_still_says_where_and_what(self):
        message, _ = self.report("/crash/plain/")
        body = message.body
        self.assertTrue(message.subject.startswith("[school-erp st-marys] ERROR"))
        self.assertIn("RuntimeError", message.subject)
        self.assertIn("/crash/plain/", message.subject)
        self.assertIn("GET", body)
        self.assertIn("500", body)
        self.assertIn("st-marys", body)
        self.assertIn("crash_plain", body)  # traceback frames are kept
        self.assertIn("test_security_gate4a_crash_email_privacy.py", body)
        self.assertEqual(message.to, ["ops@example.com"])
        self.assertEqual(message.alternatives, [])  # plain text only, no HTML copy

    def test_frames_never_reveal_where_the_code_is_installed(self):
        message, _ = self.report("/crash/plain/")
        frames = [line for line in message.body.splitlines() if line.startswith("    ")]
        self.assertTrue(frames)
        for line in frames:
            with self.subTest(frame=line):
                self.assertNotRegex(line, r"^\s+([A-Za-z]:|/|\\)")  # no absolute path
        self.assertTrue(any("site-packages/django/" in line for line in frames))
        self.assertTrue(any("core/tests/test_security_gate4a" in line for line in frames))

    def test_a_frame_from_an_external_file_shows_only_a_neutral_name(self):
        message, text = self.report("/crash/external/")
        self.assert_absent(text, "/home", "jdoe", "private-dir", SECRET_FILE)
        self.assertIn("external/secret_module.py", message.body)

    def test_traceback_local_variables_are_not_emailed(self):
        _, text = self.report("/crash/plain/")
        self.assert_absent(text, PHONE, "guardian_phone =")

    def test_the_operator_console_log_keeps_the_full_detail(self):
        with self.assertLogs("django.request", "ERROR") as logs:
            self.client.get(f"/crash/value/?q={PHONE}")
        record = logs.records[0]
        self.assertIn(NAME, str(record.exc_info[1]))  # private console, not the mail provider
        self.assertIsNotNone(record.exc_info)

    def test_a_record_without_exception_or_request_still_sends_a_safe_email(self):
        logging.getLogger("django.request").error("Bad Gateway: /somewhere/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.startswith("[school-erp st-marys] ERROR"))

    def test_if_building_the_report_fails_a_generic_email_still_goes_out(self):
        with mock.patch("config.error_reporting.build_report", side_effect=RuntimeError(NAME)):
            self.client.get("/crash/plain/")
        self.assertEqual(len(mail.outbox), 1)
        self.assert_absent(mail.outbox[0].subject + mail.outbox[0].body, NAME, "Asha")
        self.assertIn("could not be built", mail.outbox[0].body)

    def test_a_successful_request_sends_no_email(self):
        self.assertEqual(self.client.get("/ok/").status_code, 200)
        self.assertEqual(mail.outbox, [])

    @override_settings(ADMINS=[])
    def test_no_administrators_means_no_email(self):
        self.client.get("/crash/plain/")
        self.assertEqual(mail.outbox, [])


class FrameLocationTests(SimpleTestCase):
    """Where a frame's file is shown from, whatever the platform or directory layout."""

    PROJECT = Path("/app/school")

    def location(self, filename):
        with override_settings(BASE_DIR=self.PROJECT):
            return error_reporting._safe_location(filename)

    def frames_of(self, filename):
        """Frame lines of a real traceback whose innermost frames come from `filename`."""
        code = compile("def boom():\n    raise ValueError('x')\n\nboom()\n", filename, "exec")
        try:
            exec(code, {})  # noqa: S102 - synthetic code, only to name the frame's file
        except ValueError as error:
            tb = error.__traceback__
        with override_settings(BASE_DIR=self.PROJECT):
            return "\n".join(error_reporting._frames(tb))

    def test_project_file_is_shown_relative_to_the_project(self):
        self.assertEqual(self.location("/app/school/core/views.py"), "core/views.py")

    def test_a_sibling_directory_is_not_mistaken_for_the_project(self):
        self.assertEqual(
            self.location("/app/school-private/secret_module.py"), "external/secret_module.py"
        )
        self.assertEqual(self.location("/app/schoolhouse/core/x.py"), "external/x.py")

    def test_installed_package_is_shown_from_site_packages(self):
        self.assertEqual(
            self.location("/usr/lib/python3.13/site-packages/django/http/response.py"),
            "site-packages/django/http/response.py",
        )
        self.assertEqual(
            self.location("/app/school/.venv/lib/site-packages/pkg/mod.py"),
            "site-packages/pkg/mod.py",
        )

    def test_standard_library_is_shown_from_stdlib(self):
        stdlib = sysconfig.get_paths()["stdlib"]
        shown = self.location(os.path.join(stdlib, "json", "decoder.py"))
        self.assertEqual(shown, "stdlib/json/decoder.py")

    def test_any_other_file_shows_only_its_name(self):
        for filename in (
            "/home/jdoe/private-dir/secret_module.py",
            "C:\\Users\\jdoe\\private-dir\\secret_module.py",
            "/opt/vendor/custom/secret_module.py",
        ):
            with self.subTest(filename=filename):
                self.assertEqual(self.location(filename), "external/secret_module.py")

    def test_pseudo_file_names_are_kept(self):
        for name in ("<string>", "<frozen importlib._bootstrap>"):
            with self.subTest(name=name):
                self.assertEqual(self.location(name), name)

    def test_a_traceback_frame_never_carries_the_private_path(self):
        for filename in (
            "/home/jdoe/private-dir/secret_module.py",
            "C:\\Users\\jdoe\\private-dir\\secret_module.py",
            "/app/school-private/secret_module.py",
        ):
            with self.subTest(filename=filename):
                text = self.frames_of(filename)
                self.assertIn("external/secret_module.py", text)
                for private in ("jdoe", "private-dir", "school-private", "/home", "C:\\", "Users"):
                    self.assertNotIn(private, text)

    def test_no_shown_location_is_ever_an_absolute_path(self):
        for filename in (
            "/home/jdoe/x.py", "C:\\Users\\jdoe\\x.py", "/app/school/core/x.py",
            "/usr/lib/python3.13/site-packages/a/b.py", "relative/dir/x.py",
        ):
            with self.subTest(filename=filename):
                self.assertNotRegex(self.location(filename), r"^([A-Za-z]:|/|\\)")


class MailStaysOffUntilConfiguredTests(SimpleTestCase):
    """Without an SMTP host, production sends nothing; local development prints to the console."""

    def backend(self, host, debug):
        from config.deployment_safety import mail_backend_for

        return mail_backend_for(host, debug=debug)

    def test_no_host_in_production_means_mail_is_discarded(self):
        for host in ("", "   ", None):
            with self.subTest(host=host):
                self.assertEqual(
                    self.backend(host, False), "django.core.mail.backends.dummy.EmailBackend"
                )

    def test_no_host_in_local_development_prints_to_the_console(self):
        self.assertEqual(
            self.backend("", True), "django.core.mail.backends.console.EmailBackend"
        )

    def test_a_host_means_smtp(self):
        for debug in (False, True):
            with self.subTest(debug=debug):
                self.assertEqual(
                    self.backend("smtp.example.com", debug),
                    "django.core.mail.backends.smtp.EmailBackend",
                )
