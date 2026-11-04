"""Task 14: the timetable grid shows one day at a time on phones."""

import re
from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

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
