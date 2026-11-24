"""Modern web audit 13 (search and filters): SF-01, SF-02, SF-04, SF-05 and SF-06."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import notifications
from core.models import Guardian, Notification
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin
from core.tests.test_phase7_alerts import AlertFixture
from core.tests.test_ui_admin_desktop_d1_4a_attendance_list import AttendanceListFixture

QUEUE = reverse("core:notifications-to-send")
SEARCH_HINTS = 'autocorrect="off" autocapitalize="none" spellcheck="false" enterkeyhint="search"'


class AttendanceTodayTests(AttendanceListFixture, TestCase):
    """SF-05: an invalid submission applies no filter, Today included."""

    def setUp(self):
        self.build()
        self.today = date(2026, 7, 6)
        self.register(self.today)
        self.register(date(2026, 7, 1), self.six_b)
        patcher = mock.patch("core.views.business_today", return_value=self.today)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_today_alone_still_shows_only_today(self):
        response = self.client.get(self.url, {"today": "1"})
        self.assertEqual(len(response.context["registers"]), 1)
        self.assertTrue(response.context["today_only"])
        self.assertContains(response, '<input type="hidden" name="today" value="1">')

    def test_today_with_an_invalid_range_shows_all_as_the_message_says(self):
        response = self.client.get(
            self.url, {"today": "1", "start": "2026-09-30", "end": "2026-07-01"}
        )
        self.assertContains(response, "Filters were not applied; showing all registers.", count=1)
        self.assertEqual(len(response.context["registers"]), 2)
        self.assertFalse(response.context["today_only"])
        self.assertNotContains(response, 'name="today"')

    def test_invalid_filters_always_offer_clear_filters(self):
        response = self.client.get(self.url, {"start": "not-a-date"})
        self.assertContains(response, "Clear filters")


class PeopleListBase(AuthorizationClientsMixin, Phase4Fixture):
    def setUp(self):
        super().setUp()
        self.build_phase4()


class StudentChipSortTests(PeopleListBase, TestCase):
    """SF-04: chip links keep a valid sort and drop an invalid one."""

    url = reverse("core:student-list")

    def chip_urls(self, response):
        return [chip["url"] for chip in response.context["chips"]]

    def test_chip_links_keep_the_chosen_sort_but_not_the_page(self):
        response = self.administrator.get(self.url, {"sort": "-name", "page": "2"})
        for url in self.chip_urls(response):
            self.assertIn("sort=-name", url)
            self.assertNotIn("page=", url)

    def test_chip_links_drop_an_unknown_sort(self):
        response = self.administrator.get(self.url, {"sort": "bogus"})
        for url in self.chip_urls(response):
            self.assertNotIn("sort=", url)


class SearchLandmarkTests(PeopleListBase, TestCase):
    """SF-01/SF-02: one native search landmark per filter form, an explicit action, phone hints."""

    def test_list_filters_use_a_search_landmark_with_an_explicit_action(self):
        pages = {
            "core:student-list": "Filter students",
            "core:applicant-list": "Filter applicants",
            "core:attendance-register-list": "Filter attendance registers",
            "core:guardian-list": "Search guardians",
            "core:teacher-list": "Search teachers",
            "core:announcement-list": "Filter announcements",
        }
        for name, label in pages.items():
            with self.subTest(name):
                url = reverse(name)
                page = self.administrator.get(url).content.decode()
                self.assertIn(f'<search aria-label="{label}">\n<form method="get" action="{url}"', page)
                self.assertNotIn('role="search"', page)

    def test_search_fields_turn_off_correction_and_label_the_enter_key(self):
        for name in ("core:student-list", "core:applicant-list"):
            with self.subTest(name):
                page = self.administrator.get(reverse(name)).content.decode()
                field = page.split('<input type="search"', 1)[1].split(">", 1)[0]
                self.assertIn(SEARCH_HINTS, field)


class QueueReturnTests(AlertFixture, TestCase):
    """SF-06: Mark as sent and Dismiss return to the queue page they came from."""

    def setUp(self):
        super().setUp()
        for changed in Guardian.objects.all():
            changed.phone = "98765 43210"
            changed.save()
        self.register()
        [self.message] = list(notifications.to_send())

    def post(self, name, data):
        return self.client.post(reverse(name, args=[self.message.pk]), data)

    def test_mark_sent_keeps_page_and_sort(self):
        response = self.post("core:notification-mark-sent", {"page": "3", "sort": "-created"})
        self.assertRedirects(response, f"{QUEUE}?page=3&sort=-created", fetch_redirect_response=False)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.SENT)

    def test_dismiss_keeps_the_page(self):
        response = self.post("core:notification-dismiss", {"page": "2", "reason": "Told in person"})
        self.assertRedirects(response, f"{QUEUE}?page=2", fetch_redirect_response=False)

    def test_bad_or_first_page_values_fall_back_to_the_plain_queue(self):
        for data in ({}, {"page": "1"}, {"page": "-2"}, {"page": "x"}, {"sort": "guardian"},
                     {"page": "//evil.example"}, {"page": "²"}, {"page": "9" * 5000}):
            with self.subTest(data=data):
                response = self.post("core:notification-mark-sent", data)
                self.assertRedirects(response, QUEUE, fetch_redirect_response=False)

    def test_a_page_the_action_emptied_is_clamped(self):
        response = self.post("core:notification-mark-sent", {"page": "9"})
        page = self.client.get(response.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Marked as sent.")

    def test_queue_forms_carry_no_page_on_page_one(self):
        page = self.client.get(QUEUE).content.decode()
        self.assertIn(f'action="{reverse("core:notification-mark-sent", args=[self.message.pk])}"', page)
        self.assertNotIn('name="page"', page)
