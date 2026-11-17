"""Timetable page: rows for any date (ADR 0021 D10)."""

from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase

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
        self.assertEqual(chips[15]["day"], 16)

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
