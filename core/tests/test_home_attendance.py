import datetime

from django.test import TestCase

from core import analytics
from core.models import AttendanceRegister
from core.tests.test_admin_overview_analytics import TODAY, A, AnalyticsFixture, P


class MonthTrendTests(AnalyticsFixture, TestCase):
    def test_down_against_last_month(self):
        for d in (2, 3):
            self.day(datetime.date(2026, 6, d), {self.s1: P, self.s2: P})
        for d in (6, 7):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        t = analytics.month_trend(TODAY)
        self.assertEqual(t["this"], 50.0)
        self.assertEqual(t["direction"], "down")
        self.assertEqual(t["last_label"], "June")
        self.assertEqual(t["change"], round(50.0 - t["last"], 1))

    def test_no_data_this_month(self):
        self.day(datetime.date(2026, 6, 2), {self.s1: P, self.s2: P})
        t = analytics.month_trend(TODAY)
        self.assertIsNone(t["this"])
        self.assertIsNone(t["direction"])

    def test_no_comparison_without_last_month(self):
        AttendanceRegister.objects.filter(date__lt=datetime.date(2026, 7, 1)).delete()
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: A})
        t = analytics.month_trend(TODAY)
        self.assertEqual(t["this"], 50.0)
        self.assertIsNone(t["last"])
        self.assertIsNone(t["change"])
        self.assertIsNone(t["direction"])

    def test_draft_registers_do_not_count(self):
        self.day(datetime.date(2026, 7, 6), {self.s1: A, self.s2: A}, submit=False)
        self.assertIsNone(analytics.month_trend(TODAY)["this"])


class WeekdayPatternTests(AnalyticsFixture, TestCase):
    def test_mondays_stand_out(self):
        for d in (6, 13):  # Mondays
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        for d in (1, 7, 8, 14):  # Wed, Tue, Wed, Tue
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        w = analytics.weekday_pattern(TODAY, days=14)
        self.assertEqual([r["label"] for r in w["rows"]], ["Mon", "Tue", "Wed"])
        self.assertEqual(w["rows"][0]["value"], 50.0)
        self.assertTrue(w["rows"][0]["low"])
        self.assertEqual(w["lowest"]["day"], "Monday")
        self.assertEqual(w["lowest"]["gap"], 33)  # overall 10/12 = 83.3, Monday 50.0

    def test_a_weekday_with_one_day_of_data_is_left_out(self):
        self.day(datetime.date(2026, 7, 13), {self.s1: P, self.s2: A})  # one Monday only
        for d in (7, 14):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        w = analytics.weekday_pattern(TODAY, days=14)
        self.assertEqual([r["label"] for r in w["rows"]], ["Tue"])
        self.assertIsNone(w["lowest"])  # needs two weekdays to compare

    def test_no_day_stands_out_under_two_points(self):
        for d in (6, 7, 13, 14):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        self.assertIsNone(analytics.weekday_pattern(TODAY, days=14)["lowest"])

    def test_no_data(self):
        self.assertEqual(analytics.weekday_pattern(TODAY, days=14), {"rows": [], "lowest": None})
