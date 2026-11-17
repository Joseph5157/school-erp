"""Timetable page: rows for any date (ADR 0021 D10)."""

import re
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import SchoolCalendarDay
from core.navigation import teacher_tabs
from core.timetable import (
    date_strip,
    parse_timetable_date,
    teacher_timetable_on,
    todays_teacher_timetable,
)
from core.tests.test_phase5_teacher_home import MONDAY, SUNDAY
from core.tests.test_ui_teacher_timetable import TUESDAY, TimetableDashboardFixture


class TimetableRowsOnTests(TimetableDashboardFixture, TestCase):
    def rows(self, on_date, assignments):
        return teacher_timetable_on(
            assignments, on_date, lambda year: year.is_instructional_day(on_date)
        )

    def test_rows_for_a_given_date_match_that_dates_weekday(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()                                    # Monday
        self.slot(weekday=1, period=self.p2)           # Tuesday
        rows = self.rows(TUESDAY, mine)
        self.assertEqual([r["period"] for r in rows], ["P2"])
        self.assertEqual([r["subject"] for r in rows], ["Mathematics"])

    def test_rows_carry_the_period_sequence(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        self.assertEqual(self.rows(MONDAY, mine)[0]["sequence"], 1)

    def test_none_when_the_date_is_not_an_instructional_day(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        self.assertIsNone(self.rows(SUNDAY, mine))

    def test_todays_wrapper_still_returns_the_same_rows(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        check = lambda year: year.is_instructional_day(MONDAY)
        self.assertEqual(
            todays_teacher_timetable(mine, MONDAY, check),
            teacher_timetable_on(mine, MONDAY, check),
        )


class ParseTimetableDateTests(SimpleTestCase):
    TODAY = date(2026, 11, 17)

    def test_parse_accepts_a_valid_date_inside_the_window(self):
        self.assertEqual(
            parse_timetable_date("2026-11-20", self.TODAY), date(2026, 11, 20)
        )

    def test_parse_falls_back_to_today_for_garbage_empty_none_and_out_of_window(self):
        today = self.TODAY
        for raw in ("abc", "", None, "2026-13-40", "9999-12-31", "0001-01-01"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_timetable_date(raw, today), today)
        low = today - timedelta(days=366)
        high = today + timedelta(days=366)
        self.assertEqual(parse_timetable_date(low.isoformat(), today), low)
        self.assertEqual(parse_timetable_date(high.isoformat(), today), high)
        past = (low - timedelta(days=1)).isoformat()
        future = (high + timedelta(days=1)).isoformat()
        self.assertEqual(parse_timetable_date(past, today), today)
        self.assertEqual(parse_timetable_date(future, today), today)


class DateStripTests(SimpleTestCase):
    TODAY = date(2026, 11, 17)  # Tuesday

    def test_strip_has_30_chips_monday_to_saturday_no_sundays(self):
        chips = date_strip(self.TODAY, self.TODAY)
        self.assertEqual(len(chips), 30)
        self.assertEqual(chips[0]["date"], date(2026, 11, 2))   # Monday, 2 weeks back
        self.assertEqual(chips[-1]["date"], date(2026, 12, 5))  # Saturday, 2 weeks on
        self.assertEqual(
            [c["weekday"] for c in chips[:6]],
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        )
        self.assertNotIn(6, [c["date"].weekday() for c in chips])
        self.assertEqual(chips[12]["day"], 16)

    def test_strip_marks_exactly_one_selected_and_one_today_and_none_when_today_is_outside(self):
        selected = date(2026, 11, 19)
        chips = date_strip(selected, self.TODAY)
        self.assertEqual(
            [c["date"] for c in chips if c["is_selected"]], [selected]
        )
        self.assertEqual(
            [c["date"] for c in chips if c["is_today"]], [self.TODAY]
        )
        far = date_strip(date(2026, 11, 19), date(2027, 6, 1))
        self.assertEqual(sum(c["is_today"] for c in far), 0)
        self.assertEqual(sum(c["is_selected"] for c in far), 1)

    def test_strip_marks_month_start_on_first_chip_of_a_new_month(self):
        chips = date_strip(self.TODAY, self.TODAY)
        self.assertEqual(
            [c["date"] for c in chips if c["month_start"]], [date(2026, 12, 1)]
        )

    def test_strip_for_a_sunday_selection_still_builds(self):
        sunday = date(2026, 11, 22)
        chips = date_strip(sunday, self.TODAY)
        self.assertEqual(len(chips), 30)
        self.assertFalse(any(c["is_selected"] for c in chips))


class TimetablePageTests(TimetableDashboardFixture, TestCase):
    """The /my/timetable/ page (fixture business date is Monday 12 Oct 2026)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-timetable")

    def get(self, date_value=None, client=None):
        client = client or self.teacher
        return client.get(self.url, {"date": date_value} if date_value is not None else {})

    def test_teacher_sees_own_periods_for_the_chosen_date(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=1, period=self.p2)           # Tuesday P2
        tue = self.get("2026-10-13")
        self.assertEqual(tue.status_code, 200)
        self.assertEqual(
            [r["period"] for r in tue.context["rows"]], ["P2"]
        )
        self.assertContains(tue, "Grade 6 - A")
        self.assertContains(tue, "Mathematics")
        self.assertContains(tue, "Tuesday, 13 October 2026")
        self.assertEqual(self.get("2026-10-12").context["rows"], [])
        self.assertContains(
            self.get("2026-10-12"), "No periods scheduled for you on this day."
        )

    def test_default_date_is_today_with_no_query(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.get()
        self.assertEqual(page.context["selected"], MONDAY)
        self.assertEqual(page.context["today"], MONDAY)
        self.assertTrue(page.context["is_today"])
        self.assertEqual([r["period"] for r in page.context["rows"]], ["P1"])
        self.assertContains(page, "Monday, 12 October 2026")
        self.assertContains(page, "‹ My day")
        self.assertEqual(page.content.decode().count("<h1"), 1)

    def test_bad_date_values_load_today_not_500(self):
        for raw in ("abc", "", "2026-13-40", "9999-12-31", "0001-01-01"):
            with self.subTest(raw=raw):
                page = self.get(raw)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context["selected"], MONDAY)

    def test_sunday_shows_non_school_sentence_and_strip(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.get(SUNDAY.isoformat())
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.context["rows"])
        self.assertContains(page, "No school timetable on this day.")
        self.assertContains(page, 'aria-label="Pick a day"')
        self.assertEqual(len(page.context["strip"]), 30)

    def test_no_assignments_shows_empty_sentence(self):
        page = self.get()
        self.assertEqual(page.context["rows"], [])
        self.assertContains(page, "No periods scheduled for you on this day.")

    def test_holiday_shows_non_school_sentence(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=MONDAY, is_instructional=False, label="Holiday"
        )
        page = self.get()
        self.assertIsNone(page.context["rows"])
        self.assertContains(page, "No school timetable on this day.")
        self.assertNotContains(page, "No periods scheduled for you on this day.")

    def test_past_date_uses_assignments_effective_then(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 4))
        self.assign_between(self.iyer, self.maths, self.six_a, date(2026, 10, 5))
        self.slot()
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        past = "2026-10-05"                            # a Monday, Iyer's first day
        self.assertEqual(self.get(past).context["rows"], [])
        self.assertEqual(
            [r["subject"] for r in self.get(past, iyer).context["rows"]], ["Mathematics"]
        )
        before = "2026-09-28"                          # Rao's last Monday
        self.assertEqual(
            [r["subject"] for r in self.get(before).context["rows"]], ["Mathematics"]
        )
        self.assertEqual(self.get(before, iyer).context["rows"], [])

    def test_other_teachers_slots_never_appear(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.slot(section=self.six_a)
        self.slot(section=self.six_b, period=self.p2)
        page = self.get()
        self.assertEqual(
            [(r["period"], str(r["section"])) for r in page.context["rows"]],
            [("P1", "Grade 6 - A")],
        )
        self.assertContains(page, "Grade 6 - A")
        self.assertNotContains(page, "Grade 6 - B")

    def test_non_teacher_gets_403(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.make_user("parent")
        guardian = self.client_class()
        guardian.login(username="parent", password="pass-12345")
        self.assertEqual(guardian.get(self.url).status_code, 403)
        self.assertEqual(self.client_class().get(self.url).status_code, 302)

    def test_selected_chip_has_aria_current_and_today_link_goes_to_bare_route(self):
        page = self.get("2026-10-14")
        html = page.content.decode()
        self.assertEqual(html.count('aria-current="date"'), 1)
        selected = re.search(r'<a[^>]*aria-current="date"[^>]*>', html).group(0)
        self.assertIn("date=2026-10-14", selected)
        self.assertIn("erp-tt-chip", selected)
        self.assertRegex(html, r'<a[^>]*href="' + re.escape(self.url) + r'"[^>]*>\s*Today\s*</a>')
        self.assertContains(page, "October 2026")

    def test_today_tab_stays_active(self):
        active = [
            t["mobile_label"] for t in teacher_tabs("my-timetable") if t["active"]
        ]
        self.assertEqual(active, ["Today"])
