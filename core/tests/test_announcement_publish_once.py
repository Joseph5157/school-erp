"""Publishing a notice happens once (follow-up to modern-web audit C, #229).

The Publish button is already disabled after one click. This covers Back-then-Publish: the
preview carries a one-time token, so the same draft posted again is refused and the office is
taken to the notice that already went out. Different drafts have their own tokens.
"""

from django.test import TestCase
from django.urls import reverse

from core.models import Announcement
from core.tests.test_phase7_announcements import AnnouncementFixture

CREATE = reverse("core:announcement-create")


class PublishOnceTests(AnnouncementFixture, TestCase):
    def draft(self, **extra):
        return {"title": "Sports Day", "body": "Sports Day is on 20 October.", "audience": "ALL", **extra}

    def preview_token(self, data):
        page = self.client.post(CREATE, data)
        self.assertTemplateUsed(page, "core/announcement_preview.html")
        token = page.context["one_time_token"]
        self.assertContains(page, f'<input type="hidden" name="one_time_token" value="{token}">')
        return token

    def publish(self, data, token):
        return self.client.post(CREATE, {**data, "confirm": "1", "one_time_token": token})

    def test_back_then_publish_again_does_not_send_twice(self):
        data = self.draft()
        token = self.preview_token(data)
        first = self.publish(data, token)
        notice = Announcement.objects.get()
        self.assertRedirects(first, reverse("core:announcement-detail", args=[notice.pk]),
                             fetch_redirect_response=False)
        again = self.publish(data, token)  # the browser's Back page, posted again
        self.assertEqual(Announcement.objects.count(), 1)
        self.assertRedirects(again, reverse("core:announcement-detail", args=[notice.pk]),
                             fetch_redirect_response=False)
        page = self.client.get(again["Location"])
        self.assertContains(page, "This notice was already published, so it was not sent again.")

    def test_two_different_drafts_do_not_block_each_other(self):
        sports, holiday = self.draft(), self.draft(title="Holiday", body="Closed on Friday.")
        sports_token, holiday_token = self.preview_token(sports), self.preview_token(holiday)
        self.assertNotEqual(sports_token, holiday_token)
        self.publish(sports, sports_token)
        self.publish(holiday, holiday_token)
        self.assertEqual(sorted(Announcement.objects.values_list("title", flat=True)), ["Holiday", "Sports Day"])

    def test_the_same_draft_previewed_again_after_publishing_can_be_published_again_on_purpose(self):
        data = self.draft()
        self.publish(data, self.preview_token(data))
        self.publish(data, self.preview_token(data))  # a fresh preview is a deliberate new send
        self.assertEqual(Announcement.objects.count(), 2)

    def test_a_page_opened_before_this_change_still_publishes(self):
        self.client.post(CREATE, {**self.draft(), "confirm": "1"})
        self.assertEqual(Announcement.objects.count(), 1)

    def test_only_the_newest_drafts_tokens_are_kept(self):
        for number in range(8):
            self.preview_token(self.draft(title=f"Draft {number}"))
        tokens = self.client.session["one_time_forms"]
        self.assertEqual(sum(key.startswith("announcement-publish:") for key in tokens), 5)
