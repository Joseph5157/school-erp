"""Crash reporting: unhandled errors are logged and emailed to ADMINS without personal data."""

import logging

from django.conf import settings
from django.core import mail
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path


def crash_view(request):
    guardian_phone = "9876543210"  # noqa: F841 - a local that must not reach the email
    raise RuntimeError("boom in crash_view")


def ok_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("crash/", crash_view),
    path("ok/", ok_view),
]


@override_settings(
    ROOT_URLCONF=__name__,
    ADMINS=[("ops", "ops@example.com")],
    EMAIL_SUBJECT_PREFIX="[school-erp st-marys] ",
    DEBUG=False,
)
class CrashReportingTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def crash(self):
        self.client.cookies["sessionid"] = "secret-session-value"
        return self.client.post(
            "/crash/?q=1",
            {"student_name": "Asha Verma", "password": "hunter2"},
        )

    def test_crash_is_logged_with_traceback(self):
        with self.assertLogs("django.request", "ERROR") as logs:
            response = self.crash()
        self.assertEqual(response.status_code, 500)
        record = logs.records[0]
        self.assertIn("/crash/", record.getMessage())
        self.assertIsNotNone(record.exc_info)
        self.assertIn("boom in crash_view", str(record.exc_info[1]))

    def test_crash_sends_one_plain_text_email_naming_the_school(self):
        self.crash()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ops@example.com"])
        self.assertTrue(message.subject.startswith("[school-erp st-marys] ERROR"))
        self.assertIn("/crash/", message.subject)
        self.assertIn("boom in crash_view", message.body)
        self.assertIn("crash_view", message.body)  # traceback frames are kept
        self.assertEqual(message.alternatives, [])  # no HTML copy

    def test_email_leaves_out_personal_data(self):
        self.crash()
        body = mail.outbox[0].body
        self.assertNotIn("Asha Verma", body)
        self.assertNotIn("hunter2", body)
        self.assertNotIn("9876543210", body)
        self.assertNotIn("secret-session-value", body)

    def test_successful_request_sends_no_email(self):
        self.assertEqual(self.client.get("/ok/").status_code, 200)
        self.assertEqual(mail.outbox, [])

    @override_settings(ADMINS=[])
    def test_no_admins_means_no_email(self):
        self.crash()
        self.assertEqual(mail.outbox, [])


class LoggingConfigTests(SimpleTestCase):
    def test_root_logger_writes_to_console(self):
        handlers = logging.getLogger().handlers
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in handlers))

    def test_request_errors_are_emailed_and_reach_the_console(self):
        request_logger = logging.getLogger("django.request")
        self.assertTrue(
            any(h.__class__.__name__ == "AdminEmailHandler" for h in request_logger.handlers)
        )
        self.assertTrue(request_logger.propagate)

    def test_default_subject_prefix_names_the_instance(self):
        self.assertEqual(settings.EMAIL_SUBJECT_PREFIX, f"[school-erp {settings.ERP_INSTANCE_NAME}] ")
