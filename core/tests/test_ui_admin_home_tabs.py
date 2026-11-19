"""Admin home tab shell: four tabs by job, each its own URL (?tab=)."""

import datetime
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Student
from core.tests.test_admin_overview_analytics import TODAY, A, AnalyticsFixture, P

URL = reverse("core:admin-overview")
TAB_KEYS = ("today", "attendance", "academics", "parents")


def tab_nav(html):
    match = re.search(r'<nav class="erp-home-tabs" aria-label="Overview sections">(.*?)</nav>', html, re.S)
    assert match, "no tab bar"
    return match.group(1)


def tab_links(html):
    """[(label, href, current)] in page order."""
    return [
        (label, href, bool(current))
        for href, current, label in re.findall(
            r'<a class="erp-home-tab" href="([^"]*)"( aria-current="page")?>([^<]*)</a>', tab_nav(html)
        )
    ]


class HomeTabsTests(AnalyticsFixture, TestCase):
    def get(self, client=None, **params):
        response = (client or self.administrator).get(URL, params)
        self.assertEqual(response.status_code, 200)
        return response

    def current_tab(self, response):
        return [label for label, _, current in tab_links(response.content.decode()) if current]

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_default_tab_is_today_and_marked_current(self):
        response = self.get()
        links = tab_links(response.content.decode())
        self.assertEqual([label for label, _, _ in links], ["Today", "Attendance", "Academics", "Parents"])
        self.assertEqual(
            [href for _, href, _ in links],
            [URL, f"{URL}?tab=attendance", f"{URL}?tab=academics", f"{URL}?tab=parents"],
        )
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertEqual(response.context["tab"], "today")

    def test_each_tab_has_its_own_url(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        response = self.get(tab="attendance")
        self.assertEqual(self.current_tab(response), ["Attendance"])
        self.assertContains(response, "Attendance heatmap")
        self.assertNotContains(response, "Birthdays")
        self.assertNotContains(response, "School at a glance")
        for key, label in (("academics", "Academics"), ("parents", "Parents")):
            with self.subTest(tab=key):
                self.assertEqual(self.current_tab(self.get(tab=key)), [label])

    def test_exactly_one_tab_context_is_built(self):
        names = {"today": "today", "attendance": "attendance_tab",
                 "academics": "academics_tab", "parents": "parents_tab"}
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                context = self.get(tab=key).context
                present = [name for name in names.values() if name in context]
                self.assertEqual(present, [names[key]])

    def test_unknown_or_empty_tab_shows_today(self):
        for value in ("nonsense", ""):
            with self.subTest(tab=value):
                response = self.get(tab=value)
                self.assertEqual(self.current_tab(response), ["Today"])
                self.assertIn("today", response.context)

    def test_old_period_links_are_ignored(self):
        response = self.get(period="term")
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertNotContains(response, "Custom range")
        self.assertNotContains(response, "erp-period")
        self.assertNotContains(response, 'role="status"')

    def test_only_the_active_tab_is_queried(self):
        self.get()  # warm per-process caches
        with CaptureQueriesContext(connection) as today:
            self.get()
        with CaptureQueriesContext(connection) as parents:
            self.get(tab="parents")
        self.assertLess(len(parents), len(today))

    def test_removed_parts_are_gone(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(tab=key)
                for gone in ("Still to finish", "Score bands", "Daily attendance",
                             "erp-ring", "erp-gauge", "Checklist"):
                    self.assertNotContains(response, gone)

    def test_viewer_without_student_permission_sees_no_names(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        Student.objects.filter(pk=self.s2.student_id).update(date_of_birth=datetime.date(2015, 7, 14))
        client = self.viewer("no-students", "view_school", "view_attendanceentry")
        birthdays = self.get(client).context["today"]["birthdays"]
        self.assertEqual(birthdays["count"], 1)
        self.assertEqual((birthdays["today"], birthdays["later"]), ([], []))
        response = self.get(client, tab="attendance")
        self.assertIsNone(response.context["attendance_tab"]["absentees"])
        self.assertNotContains(response, "Frequent absentees")
        self.assertNotContains(response, "Meena Das")
        # Holding students too brings the names back.
        both = self.viewer("both", "view_school", "view_attendanceentry", "view_student")
        self.assertEqual(self.get(both).context["today"]["birthdays"]["today"][0]["name"], "Meena Das")

    def test_nothing_repeats_across_tabs(self):
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(self.superuser_client, tab=key)
                if key == "parents":
                    self.assertContains(response, "Pending access reviews")
                else:
                    self.assertNotContains(response, "Pending access reviews")
                if key != "today":
                    self.assertNotContains(response, "Attendance today")
                    self.assertNotContains(response, "School at a glance")
        today = self.get(self.superuser_client).context["today"]
        self.assertNotIn("access_reviews", [c["key"] for c in today["cards"]])
        self.assertNotIn("attendance", [c["key"] for c in today["cards"]])
        self.assertIn("attendance", today)

    def test_today_context_is_pinned_to_the_business_date(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        today = self.get(self.superuser_client).context["today"]
        self.assertEqual((today["attendance"]["present"], today["attendance"]["absent"]), (1, 1))
        for key in ("compliance", "overdue_marks", "assessments", "birthdays", "glance_cards"):
            self.assertIn(key, today)

    def test_compliance_and_overdue_marks_need_their_view_permissions(self):
        today = self.get(self.viewer("plain", "view_school")).context["today"]
        self.assertIsNone(today["compliance"])
        self.assertIsNone(today["overdue_marks"])
        today = self.get(
            self.viewer("ops", "view_school", "view_attendanceregister", "view_assessment")
        ).context["today"]
        self.assertIsNotNone(today["compliance"])
        self.assertEqual(today["overdue_marks"], [])

    def test_parents_tab_shows_guardians_and_links_only_what_the_viewer_may_open(self):
        response = self.get(self.superuser_client, tab="parents")
        parents = response.context["parents_tab"]
        self.assertEqual(parents["glance"]["key"], "guardians")
        self.assertEqual(parents["announcements_url"], reverse("core:announcement-list"))
        self.assertContains(response, reverse("core:announcement-list"))
        plain = self.get(self.viewer("plain-parents", "view_school"), tab="parents").context["parents_tab"]
        self.assertIsNone(plain["access_review_card"])
        self.assertIsNone(plain["announcements_url"])
        self.assertEqual(plain["glance"]["url"], "")

    def test_tab_bar_markup_and_phone_css(self):
        from pathlib import Path

        from django.conf import settings

        html = self.get().content.decode()
        self.assertIn('<nav class="erp-home-tabs" aria-label="Overview sections">', html)
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-home-tab \{[^}]*min-height: 2\.75rem")
