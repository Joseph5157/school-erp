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

    def test_not_taken_registers_need_view_attendanceregister(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        attendance = self.get(self.viewer("school-only", "view_school")).context["today"]["attendance"]
        self.assertIsNone(attendance["not_taken"])  # sections and their teachers are not listed
        self.assertTrue(attendance["school_day"])
        rows = self.get(
            self.viewer("registers", "view_school", "view_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1"])
        self.assertIsNotNone(rows[0]["url"])  # the draft opens on the register page
        rows = self.get(
            self.viewer("add-only", "view_school", "add_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertIsNone(rows)

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

    def test_today_cards_in_order(self):
        html = self.get().content.decode()
        positions = [
            html.index(f'id="{anchor}"')
            for anchor in (
                "glance-title", "att-today-title", "compliance-title", "assess-title", "bday-title",
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_not_taken_row_shows_teacher_and_open_link(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        response = self.get()
        self.assertContains(response, "Not taken yet")
        row = response.context["today"]["attendance"]["not_taken"][0]
        self.assertContains(response, f"{row['class_name']} {row['section_name']}")
        self.assertContains(response, f'href="{row["url"]}">Open')

    def test_all_registers_in_message(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        self.assertContains(self.get(), "All registers are in.")

    def test_before_cutoff_shows_due_by_line(self):
        from unittest import mock

        from django.utils import timezone

        early = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(9, 0)))
        with mock.patch("django.utils.timezone.now", return_value=early):
            response = self.get()
        self.assertContains(response, "Registers are due by 10:00.")
        self.assertNotContains(response, "Not submitted yet")

    def test_compliance_hidden_without_register_permission(self):
        response = self.get(self.viewer("no-reg", "view_school"))
        self.assertNotContains(response, "Teacher compliance")
        self.assertNotContains(response, "Not taken yet")

    def test_home_card_css_is_pinned(self):
        from pathlib import Path

        from django.conf import settings

        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-home-tabs {", css)
        self.assertIn('.erp-home-tab[aria-current="page"]', css)
        self.assertIn(".erp-home-grid {", css)
        self.assertRegex(css, r"@media \(min-width: 992px\) \{ \.erp-home-grid \{ grid-template-columns: repeat\(2")

    def _add_sections(self, count):
        from core.models import ClassGrade, Section

        for i in range(count):
            grade = ClassGrade.objects.create(name=f"Grade {20 + i}")
            section = Section.objects.create(class_grade=grade, name="A")
            self.enroll_student(f"Fold Pupil {i}", grade, section)

    def test_not_taken_list_folds_after_five(self):
        self._add_sections(6)  # plus Grade 1 = 7 sections, none submitted
        html = self.get().content.decode()
        card = html.split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 7)
        self.assertEqual(card.count("<details"), 1)
        self.assertIn("Show all 7 classes", card)
        visible = card.split("<details", 1)[0]
        self.assertEqual(visible.count('class="erp-home-row"'), 5)

    def test_not_taken_list_does_not_fold_at_five_or_fewer(self):
        self._add_sections(4)  # 5 sections in all
        card = self.get().content.decode().split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 5)
        self.assertNotIn("<details", card)

    def test_overdue_marks_hidden_without_view_assessment(self):
        response = self.get(self.viewer("regs-only", "view_school", "view_attendanceregister"))
        self.assertContains(response, "Teacher compliance")
        self.assertNotContains(response, "Marks overdue")
