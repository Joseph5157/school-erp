"""Phase 7 Gates 2 and 4: absence alerts and report-card notices (ADR 0015)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from core.forms import SchoolForm
from core.models import NotificationTemplate, School
from core.tests.test_phase7_notifications import NotificationFixture

BASE = "https://erp.example"
ABSENCE_BODY = (
    "Dear parent, {first_name} was marked absent at school on {date}. "
    "Attendance details: {portal_url}"
)
NOTICE_BODY = (
    "Dear parent, {first_name}'s report card is now available on the school portal: "
    "{portal_url}"
)
ADDRESS_ERROR = "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."


class SeededTemplateTests(TestCase):
    def test_both_texts_are_seeded_approved_and_valid(self):
        for key, body in (("absence-alert", ABSENCE_BODY),
                          ("report-card-published", NOTICE_BODY)):
            with self.subTest(key=key):
                template = NotificationTemplate.objects.get(
                    key=key, channel="WHATSAPP", language="en", version=1)
                self.assertTrue(template.approved)
                self.assertEqual(template.body, body)
                template.full_clean()


class SchoolFormAddressTests(TestCase):
    def form(self, mode):
        return SchoolForm(data={"name": "Greenwood High", "notification_channel": mode})

    @override_settings(PORTAL_BASE_URL="")
    def test_assist_refused_without_portal_address(self):
        form = self.form("ASSIST")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["notification_channel"], [ADDRESS_ERROR])

    @override_settings(PORTAL_BASE_URL="")
    def test_portal_only_allowed_without_portal_address(self):
        self.assertTrue(self.form("PORTAL_ONLY").is_valid())

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_assist_allowed_with_portal_address(self):
        self.assertTrue(self.form("ASSIST").is_valid())


class ToSendWarningTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:notifications-to-send")

    @override_settings(PORTAL_BASE_URL="")
    def test_warning_when_assist_without_portal_address(self):
        page = self.client.get(self.url)
        self.assertTrue(page.context["portal_address_missing"])
        self.assertContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_no_warning_with_portal_address(self):
        page = self.client.get(self.url)
        self.assertFalse(page.context["portal_address_missing"])
        self.assertNotContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL="")
    def test_no_address_warning_in_portal_only(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertFalse(self.client.get(self.url).context["portal_address_missing"])
