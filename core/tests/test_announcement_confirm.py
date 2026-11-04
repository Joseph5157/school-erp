"""Withdrawing a notice and preparing WhatsApp messages ask first (admin mobile audit, task 1)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core import announcements
from core.models import GuardianContactConsent, Notification
from core.tests.test_phase7_announcements import AnnouncementFixture

User = get_user_model()

CONSEQUENCES = [
    "Guardians stop seeing this notice in the portal at once.",
    "WhatsApp messages still waiting to be sent are dismissed.",
    "Messages already sent cannot be recalled.",
    "A published notice cannot be edited. To correct it, publish a new one.",
]


class Base(AnnouncementFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.notice_obj = self.notice()
        self.withdraw_url = reverse("core:announcement-withdraw", args=[self.notice_obj.pk])
        self.prepare_url = reverse("core:announcement-prepare", args=[self.notice_obj.pk])
        self.detail_url = reverse("core:announcement-detail", args=[self.notice_obj.pk])

    def reload(self):
        self.notice_obj.refresh_from_db()
        return self.notice_obj


class WithdrawConfirmTests(Base):
    def test_detail_links_to_withdraw_page_and_has_no_inline_form(self):
        page = self.client.get(self.detail_url)
        self.assertContains(page, f'href="{self.withdraw_url}"')
        self.assertContains(page, "Withdraw this notice")
        self.assertNotContains(page, 'name="reason"')
        self.assertNotContains(page, f'action="{self.withdraw_url}"')

    def test_withdraw_page_shows_title_audience_and_consequences(self):
        page = self.client.get(self.withdraw_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sports Day")
        self.assertContains(page, self.notice_obj.audience_label())
        for line in CONSEQUENCES:
            self.assertContains(page, line)
        self.assertContains(page, "Confirm withdrawal")
        self.assertFalse(self.reload().is_withdrawn)

    def test_blank_reason_rerenders_with_error(self):
        page = self.client.post(self.withdraw_url, {"reason": "  "})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Give a reason for withdrawing this notice.")
        self.assertFalse(self.reload().is_withdrawn)

    def test_confirm_withdraws_and_records_reason(self):
        page = self.client.post(self.withdraw_url, {"reason": "Wrong date"})
        self.assertRedirects(page, self.detail_url)
        notice = self.reload()
        self.assertTrue(notice.is_withdrawn)
        self.assertEqual(notice.withdrawal_reason, "Wrong date")
        self.assertEqual(notice.withdrawn_by, self.admin)

    def test_second_post_changes_nothing(self):
        self.client.post(self.withdraw_url, {"reason": "Wrong date"})
        first = self.reload().withdrawn_at
        page = self.client.post(self.withdraw_url, {"reason": "Other"}, follow=True)
        self.assertContains(page, "This notice has already been withdrawn.")
        notice = self.reload()
        self.assertEqual(notice.withdrawn_at, first)
        self.assertEqual(notice.withdrawal_reason, "Wrong date")

    def test_get_on_a_withdrawn_notice_redirects_with_message(self):
        announcements.withdraw(self.notice_obj, actor=self.admin, reason="Wrong date")
        page = self.client.get(self.withdraw_url)
        self.assertRedirects(page, self.detail_url)
        page = self.client.get(self.withdraw_url, follow=True)
        self.assertContains(page, "This notice has already been withdrawn.")

    def test_withdraw_still_dismisses_waiting_messages(self):
        announcements.prepare_messages(self.notice_obj)
        self.client.post(self.withdraw_url, {"reason": "Wrong date"})
        self.assertFalse(Notification.objects.filter(
            status=Notification.Status.PREPARED).exists())


class PrepareConfirmTests(Base):
    def test_prepare_page_shows_opted_in_count_and_queue_link(self):
        page = self.client.get(self.prepare_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "This queues a message for 2 opted-in guardian(s). "
                                  "Nothing is sent from here.")
        self.assertContains(page, "Prepare messages")
        self.assertContains(page, reverse("core:notifications-to-send"))

    def test_prepare_get_creates_no_notifications(self):
        self.client.get(self.prepare_url)
        self.assertFalse(Notification.objects.exists())

    def test_prepare_post_prepares(self):
        page = self.client.post(self.prepare_url, follow=True)
        self.assertRedirects(page, self.detail_url)
        self.assertContains(page, "Messages ready on the Message queue page: 2.")
        self.assertContains(page, reverse("core:notifications-to-send"))
        self.assertEqual(Notification.objects.count(), 2)

    def test_zero_opted_in_shows_message_and_no_button(self):
        for guardian in (self.meena, self.other):
            self.consent(guardian, GuardianContactConsent.Status.OPTED_OUT)
        page = self.client.get(self.prepare_url)
        self.assertContains(page, "No opted-in guardians")
        self.assertNotContains(page, ">Prepare messages<")
        self.assertNotContains(page, 'method="post" class="erp-form"')
        self.assertFalse(Notification.objects.exists())

    def test_prepare_page_redirects_when_not_assist_or_withdrawn(self):
        from core.models import School
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        page = self.client.get(self.prepare_url)
        self.assertRedirects(page, self.detail_url)
        page = self.client.get(self.prepare_url, follow=True)
        self.assertContains(page, "WhatsApp sending is switched off for this school.")
        School.objects.filter(pk=self.school.pk).update(notification_channel="ASSIST")
        announcements.withdraw(self.notice_obj, actor=self.admin, reason="Wrong date")
        page = self.client.get(self.prepare_url, follow=True)
        self.assertRedirects(page, self.detail_url)
        self.assertContains(page, "This notice has been withdrawn.")
        self.assertFalse(Notification.objects.exists())

    def test_detail_links_to_prepare_page_and_has_no_inline_form(self):
        page = self.client.get(self.detail_url)
        self.assertContains(page, f'href="{self.prepare_url}"')
        self.assertContains(page, "Prepare WhatsApp messages")
        self.assertNotContains(page, f'action="{self.prepare_url}"')


class PermissionAndCopyTests(Base):
    def view_only_client(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_announcement"))
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        return client

    def test_view_only_user_is_forbidden(self):
        viewer = self.view_only_client()
        for url in (self.withdraw_url, self.prepare_url):
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(viewer, method)(url).status_code, 403)
        self.assertFalse(self.reload().is_withdrawn)

    def test_detail_notes_counts_are_eligibility_not_delivery(self):
        page = self.client.get(self.detail_url)
        self.assertContains(page, "Current eligibility; this is not a view or delivery count.")
