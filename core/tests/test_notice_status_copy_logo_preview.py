"""F7: WhatsApp status on a notice, Use as new notice, and the logo preview markup."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core import announcements, notifications
from core.models import Announcement, Guardian, Notification, Section
from core.tests.test_phase7_announcements import AnnouncementFixture

CLASS = Announcement.Audience.CLASS
SECTION = Announcement.Audience.SECTION


def client_with(client_class, *codenames):
    user = get_user_model().objects.create_user("limited", password="pass-12345")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = client_class()
    client.force_login(user)
    return client


class WhatsAppStatusTests(AnnouncementFixture, TestCase):
    def page(self, notice, client=None):
        return (client or self.client).get(reverse("core:announcement-detail", args=[notice.pk]))

    def messages_of(self, notice):
        return Notification.objects.filter(
            idempotency_key__endswith=f":announcement-{notice.pk}"
        ).order_by("pk")

    def test_before_preparing_says_none_are_prepared(self):
        self.assertContains(self.page(self.notice()), "No messages prepared yet")

    def test_counts_only_this_notices_messages(self):
        notice = self.notice()
        other = self.notice(title="Other notice")
        announcements.prepare_messages(notice)
        announcements.prepare_messages(other)
        self.assertEqual(announcements.message_counts(notice)["ready"], 2)

    def test_a_notice_whose_number_ends_the_same_is_not_counted(self):
        notice = self.notice()
        notifications.enqueue(
            guardian=Guardian.objects.first(), student=None, type=Notification.Type.ANNOUNCEMENT,
            template_key=announcements.TEMPLATE_KEY,
            parameters={"portal_url": announcements.notice_url(notice)},
            subject=f"announcement-1{notice.pk}",
        )
        self.assertEqual(announcements.message_counts(notice)["total"], 0)

    def test_each_status_falls_in_its_own_group(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        first, second = self.messages_of(notice)
        notifications.mark_sent(first, user=self.admin)
        notifications.dismiss(second, user=self.admin, reason="Told in person")
        self.assertEqual(
            announcements.message_counts(notice),
            {"ready": 0, "sent": 1, "dismissed": 1, "skipped": 0, "problem": 0, "total": 2},
        )

    def test_delivered_counts_as_sent_and_failed_as_a_problem(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        model = self.messages_of(notice).first()
        for number, status in enumerate((Notification.Status.DELIVERED, Notification.Status.FAILED)):
            Notification.objects.create(
                guardian=model.guardian, type=model.type, template=model.template,
                parameters=model.parameters, channel_mode=model.channel_mode, status=status,
                idempotency_key=f"made-up-{number}:announcement-{notice.pk}",
            )
        counts = announcements.message_counts(notice)
        self.assertEqual((counts["ready"], counts["sent"], counts["problem"]), (2, 1, 1))

    def test_page_shows_counts_and_links_to_the_queue(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        response = self.page(notice)
        self.assertContains(response, "Ready to send")
        self.assertContains(response, reverse("core:notifications-to-send"))
        self.assertNotContains(response, "No messages prepared yet")

    def test_withdrawn_notice_still_shows_its_message_record(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        response = self.page(notice)
        self.assertContains(response, "Dismissed")
        self.assertNotContains(response, reverse("core:announcement-prepare", args=[notice.pk]))

    def test_viewer_without_queue_permission_sees_no_counts(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        client = client_with(self.client_class, "view_announcement")
        self.assertNotContains(self.page(notice, client), "Ready to send")


class UseAsNewNoticeTests(AnnouncementFixture, TestCase):
    def copy_page(self, notice, client=None):
        return (client or self.client).get(
            reverse("core:announcement-create"), {"from": notice.pk}
        )

    def test_detail_page_offers_the_action_on_live_and_withdrawn_notices(self):
        notice = self.notice()
        url = f'{reverse("core:announcement-create")}?from={notice.pk}'
        detail = reverse("core:announcement-detail", args=[notice.pk])
        self.assertContains(self.client.get(detail), url)
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        self.assertContains(self.client.get(detail), url)

    def test_viewer_who_cannot_create_is_not_offered_it(self):
        notice = self.notice()
        client = client_with(self.client_class, "view_announcement")
        response = client.get(reverse("core:announcement-detail", args=[notice.pk]))
        self.assertNotContains(response, f'{reverse("core:announcement-create")}?from=')

    def test_form_is_filled_and_saves_nothing(self):
        notice = self.notice(title="Sports Day", body="On 20 October.")
        before = Announcement.objects.count()
        response = self.copy_page(notice)
        form = response.context["form"]
        self.assertEqual(form["title"].value(), "Sports Day")
        self.assertEqual(form["body"].value(), "On 20 October.")
        self.assertContains(response, "Copied from")
        self.assertEqual(Announcement.objects.count(), before)

    def test_class_and_section_audience_are_copied(self):
        by_class = self.notice(CLASS, class_grade=self.grade6)
        form = self.copy_page(by_class).context["form"]
        self.assertEqual(form["audience"].value(), CLASS)
        self.assertEqual(form["class_grade"].value(), self.grade6.pk)
        section = Section.objects.filter(class_grade=self.grade6).first()
        by_section = self.notice(SECTION, section=section)
        form = self.copy_page(by_section).context["form"]
        self.assertEqual(form["audience"].value(), SECTION)
        self.assertEqual(form["section"].value(), section.pk)

    def test_copy_still_goes_through_preview_before_publishing(self):
        notice = self.notice()
        before = Announcement.objects.count()
        form = self.copy_page(notice).context["form"]
        response = self.client.post(reverse("core:announcement-create"), {
            "title": form["title"].value(), "body": form["body"].value(),
            "audience": form["audience"].value(),
        })
        self.assertTemplateUsed(response, "core/announcement_preview.html")
        self.assertEqual(Announcement.objects.count(), before)

    def test_withdrawn_details_are_not_carried_over(self):
        notice = self.notice()
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        self.assertNotContains(self.copy_page(notice), "Wrong date")

    def test_bad_or_unknown_source_gives_a_blank_form(self):
        for value in ("abc", "99999", ""):
            with self.subTest(value=value):
                response = self.client.get(reverse("core:announcement-create"), {"from": value})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["form"]["title"].value())
                self.assertNotContains(response, "Copied from")

    def test_creator_who_cannot_view_notices_cannot_read_one_through_the_copy(self):
        notice = self.notice(title="Private plan")
        client = client_with(self.client_class, "add_announcement")
        response = self.copy_page(notice, client)
        self.assertNotContains(response, "Private plan")


class LogoPreviewMarkupTests(AnnouncementFixture, TestCase):
    def test_preview_starts_hidden_so_the_page_works_without_javascript(self):
        response = self.client.get(reverse("core:school-detail"))
        self.assertContains(response, "data-erp-logo-preview hidden")
        self.assertContains(response, "data-erp-logo-form")
