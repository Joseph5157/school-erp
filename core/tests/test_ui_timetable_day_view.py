"""Task 14: the timetable grid shows one day at a time on phones."""

import re
from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.tests.test_timetable_grid_ui import TODAY, GridFixture, pinned

TUESDAY = date(2026, 10, 20)
SATURDAY = date(2026, 10, 24)
SUNDAY = date(2026, 10, 18)


def phone_html(response):
    html = response.content.decode()
    match = re.search(r'<section class="erp-day-view[^"]*".*?</section>', html, re.S)
    assert match, "phone day view missing"
    return match.group(0)


@pinned()
class DayViewTests(GridFixture, TestCase):
    def setUp(self):
        self.build_grid()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.make_slot(weekday=0)
        self.make_slot(weekday=1, period=self.p2, offering=self.science)

    def phone(self, query=""):
        return phone_html(self.client.get(self.grid_url(on=TODAY) + query))

    def test_day_view_lists_each_period_subject_teacher(self):
        html = self.phone()
        self.assertEqual(len(re.findall(r'class="erp-day-period"', html)), 2)
        self.assertIn("Monday", html)
        self.assertIn("P1", html)
        self.assertIn("P2", html)
        self.assertIn(self.maths.subject.name, html)
        self.assertIn(">rao<", html)
        self.assertNotIn("Science", html)  # that slot is on Tuesday

    def test_empty_period_offers_add_slot(self):
        html = self.phone()
        self.assertIn("No slot scheduled", html)
        self.assertIn(f'href="{self.add_url(period=self.p2, weekday=0, on=TODAY)}"', html)
        self.assertIn("Add slot", html)

    def test_change_and_end_links_keep_their_accessible_names(self):
        html = self.phone()
        name = re.escape(f"{self.maths.subject.name}, P1, Monday")
        self.assertRegex(html, rf'>Change<span class="visually-hidden"> {name}</span>')
        self.assertRegex(html, rf'>End<span class="visually-hidden"> {name}</span>')

    def test_day_param_selects_day(self):
        html = self.phone("&day=1")
        self.assertIn("Science", html)
        self.assertNotIn(f"{self.maths.subject.name}</p>", html)
        self.assertRegex(html, r'aria-current="page">Tuesday</a>')

    def test_tabs_are_plain_links_that_keep_the_date(self):
        html = self.phone()
        self.assertEqual(len(re.findall(r'class="erp-day-tab[ "]', html)), 6)
        self.assertIn(f"?date={TODAY.isoformat()}&amp;day=3", html)

    def test_bad_day_param_uses_default(self):
        for bad in ("&day=abc", "&day=9", "&day=-1", "&day="):
            with self.subTest(bad):
                response = self.client.get(self.grid_url(on=TODAY) + bad)
                self.assertEqual(response.status_code, 200)
                self.assertRegex(phone_html(response), r'aria-current="page">Monday</a>')

    def test_default_is_today_when_a_school_day(self):
        with pinned(TUESDAY):
            html = phone_html(self.client.get(self.grid_url(on=TODAY)))
        self.assertRegex(html, r'aria-current="page">Tuesday</a>')

    def test_default_is_first_school_day_on_sunday_and_closed_saturday(self):
        for today in (SUNDAY, SATURDAY):
            with self.subTest(today), pinned(today):
                html = phone_html(self.client.get(self.grid_url(on=TODAY)))
                self.assertRegex(html, r'aria-current="page">Monday</a>')

    def test_default_is_saturday_when_saturdays_are_instructional(self):
        self.year.saturdays_instructional = True
        self.year.save()
        with pinned(SATURDAY):
            html = phone_html(self.client.get(self.grid_url(on=TODAY)))
        self.assertRegex(html, r'aria-current="page">Saturday</a>')

    def test_non_school_saturday_says_so(self):
        html = self.phone("&day=5")
        self.assertIn("Not a school day", html)
        self.assertNotIn("erp-day-period", html)

    def test_grid_is_unchanged_from_md_up(self):
        html = self.client.get(self.grid_url(on=TODAY)).content.decode()
        self.assertRegex(
            html,
            r'<div class="d-none d-md-block d-print-block">\s*<div class="erp-panel">\s*'
            r'<div class="erp-table-scroll" role="region"',
        )
        self.assertIn('class="erp-day-view d-md-none d-print-none"', html)

    def test_day_view_adds_no_queries_per_day(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.grid_url(on=TODAY))
        before = len(ctx)
        for weekday in range(2, 5):
            self.make_slot(weekday=weekday, offering=self.science)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.grid_url(on=TODAY) + "&day=2")
        self.assertEqual(len(ctx), before)


@pinned()
class DayCarriedThroughTests(GridFixture, TestCase):
    """Editing a slot from the phone day view returns to the same weekday tab."""

    def setUp(self):
        self.build_grid()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.tue = self.make_slot(weekday=1)

    def url(self, name, slot, query):
        return reverse(f"core:{name}", args=[slot.pk]) + query

    def test_links_in_a_day_view_keep_the_day(self):
        html = phone_html(self.client.get(self.grid_url(on=TODAY) + "&day=1"))
        links = re.findall(r'href="([^"]*/slots/[^"]*)"', html)
        self.assertGreaterEqual(len(links), 3)  # change, end, add (P2)
        for link in links:
            self.assertIn("day=1", link, link)

    def test_post_with_day_redirects_with_day(self):
        query = f"?date={TODAY.isoformat()}&day=1"
        response = self.client.post(
            self.url("timetable-slot-end", self.tue, query), {"end_date": "2026-11-30"}
        )
        self.assertRedirects(response, self.grid_url(on=TODAY) + "&day=1")

    def test_forms_carry_day_in_cancel_and_back_links(self):
        query = f"?date={TODAY.isoformat()}&day=1"
        page = self.client.get(self.url("timetable-slot-change", self.tue, query))
        self.assertContains(page, "&amp;day=1")
        future = self.make_slot(weekday=2, start_date=date(2026, 12, 1))
        page = self.client.get(self.url("timetable-slot-delete", future, query))
        self.assertContains(page, "day=1", count=1)  # Cancel
        started = self.client.get(self.url("timetable-slot-delete", self.tue, query))
        self.assertContains(started, "day=1", count=2)  # End this slot, Back to timetable

    def test_bad_day_is_ignored_on_post(self):
        for index, bad in enumerate(("abc", "9", "-1", "", "1<x>")):
            with self.subTest(bad):
                slot = self.make_slot(weekday=index, period=self.p2)
                query = f"?date={TODAY.isoformat()}&day={bad}"
                response = self.client.post(
                    self.url("timetable-slot-end", slot, query), {"end_date": "2026-11-30"}
                )
                self.assertRedirects(response, self.grid_url(on=TODAY))

    def test_no_day_redirects_as_before(self):
        response = self.client.post(
            self.url("timetable-slot-end", self.tue, f"?date={TODAY.isoformat()}"),
            {"end_date": "2026-11-30"},
        )
        self.assertRedirects(response, self.grid_url(on=TODAY))

    def test_view_only_user_sees_no_action_links_in_the_day_view(self):
        from django.contrib.auth.models import Permission

        user = self.make_user("viewer")
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="core",
            codename__in=["view_timetableslot", "view_timetableperiod"],
        ))
        self.client.force_login(user)
        html = phone_html(self.client.get(self.grid_url(on=TODAY) + "&day=1"))
        self.assertNotIn("<a class=\"btn", html)
        self.assertNotIn("/slots/", html.replace("/sections/", ""))
