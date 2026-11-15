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
        for number in range(25):
            self.preview_token(self.draft(title=f"Draft {number}"))
        tokens = self.client.session["one_time_forms"]
        self.assertEqual(sum(key.startswith("announcement-publish:") for key in tokens), 20)

    def test_a_draft_whose_token_was_trimmed_still_publishes(self):
        oldest = self.draft(title="Oldest")
        token = self.preview_token(oldest)
        for number in range(25):  # pushes the oldest token out of the session
            self.preview_token(self.draft(title=f"Draft {number}"))
        self.publish(oldest, token)
        self.assertTrue(Announcement.objects.filter(title="Oldest").exists())

    def test_previewing_a_draft_again_makes_it_the_newest(self):
        first = self.draft(title="First")
        token = self.preview_token(first)
        for number in range(19):
            self.preview_token(self.draft(title=f"Draft {number}"))
        self.assertEqual(self.preview_token(first), token)  # same draft, same token, now newest
        for number in range(19, 25):
            self.preview_token(self.draft(title=f"Draft {number}"))
        self.assertIn(token, self.client.session["one_time_forms"].values())  # not trimmed
        self.publish(first, token)
        self.assertEqual(self.publish(first, token).status_code, 302)
        self.assertEqual(Announcement.objects.filter(title="First").count(), 1)

    def test_class_and_section_repeats_are_refused_too(self):
        for extra in ({"audience": "CLASS", "class_grade": self.grade6.pk},
                      {"audience": "SECTION", "section": self.six_a.pk}):
            with self.subTest(audience=extra["audience"]):
                data = self.draft(title=f"For {extra['audience']}", **extra)
                token = self.preview_token(data)
                self.publish(data, token)
                self.publish(data, token)
                self.assertEqual(Announcement.objects.filter(title=data["title"]).count(), 1)

    def test_titles_and_bodies_do_not_run_together_in_the_draft_key(self):
        one = self.preview_token(self.draft(title="Sports Day A", body="bc text"))
        two = self.preview_token(self.draft(title="Sports Day Ab", body="c text"))
        self.assertNotEqual(one, two)


class PublishOnceWithoutViewPermissionTests(AnnouncementFixture, TestCase):
    def test_someone_who_can_only_add_goes_back_to_the_form(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        adder = get_user_model().objects.create_user(username="adder", password="pass-12345")
        adder.user_permissions.add(Permission.objects.get(codename="add_announcement"))
        self.client.force_login(adder)
        data = {"title": "Sports Day", "body": "Sports Day is on 20 October.", "audience": "ALL"}
        token = self.client.post(CREATE, data).context["one_time_token"]
        self.client.post(CREATE, {**data, "confirm": "1", "one_time_token": token})
        again = self.client.post(CREATE, {**data, "confirm": "1", "one_time_token": token})
        self.assertRedirects(again, CREATE, fetch_redirect_response=False)
        self.assertEqual(Announcement.objects.count(), 1)
