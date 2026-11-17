"""Timetable page: rows for any date (ADR 0021 D10)."""

from django.test import TestCase

from core.timetable import teacher_timetable_on, todays_teacher_timetable
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
