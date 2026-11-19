import datetime
from unittest import mock

from django.test import TestCase

from core import analytics
from core.models import AttendanceRegister
from core.tests.test_admin_overview_analytics import TODAY, A, AnalyticsFixture, MarksFixture, P


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


def _rows(*pcts):
    return [{"class_grade_id": i, "class_name": f"C{i}", "class_order": i, "present": 0, "absent": 0,
             "percentage": p} for i, p in enumerate(sorted(pcts), start=1)]


class ClassExtremesTests(TestCase):
    def test_hidden_under_four_classes(self):
        self.assertIsNone(analytics.class_extremes(_rows(70, 80, 90), with_links=False))

    def test_four_or_five_classes_split_without_overlap(self):
        for rows in (_rows(70, 80, 90, 95), _rows(70, 80, 85, 90, 95)):
            c = analytics.class_extremes(rows, with_links=False)
            self.assertEqual([r["value"] for r in c["worst"]], [70, 80])
            self.assertEqual([r["value"] for r in c["best"]], [95, 90])

    def test_three_each_from_six_or_more(self):
        c = analytics.class_extremes(_rows(60, 70, 80, 85, 90, 95, 99), with_links=False)
        self.assertEqual([r["value"] for r in c["worst"]], [60, 70, 80])
        self.assertEqual([r["value"] for r in c["best"]], [99, 95, 90])
        self.assertIsNone(c["best"][0]["url"])

    def test_links_only_when_allowed(self):
        c = analytics.class_extremes(_rows(60, 70, 80, 90), with_links=True)
        self.assertTrue(c["best"][0]["url"].startswith("/"))


class LowAttendanceTests(MarksFixture, TestCase):  # term_b = 2026-07-01..09-30
    def test_below_75_this_term_lowest_first(self):
        for d, s2 in zip((1, 2, 3, 6, 7, 8), (A, A, A, A, P, P)):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: s2})
        result = analytics.low_attendance_students(self.term_b, TODAY)
        self.assertEqual([(r["name"], r["percentage"]) for r in result["rows"]], [("Meena Das", 33.3)])
        self.assertEqual(result["total"], 1)

    def test_exactly_75_is_not_listed(self):
        for d, s2 in zip((1, 2, 3, 6, 7, 8, 9, 10), (A, A, P, P, P, P, P, P)):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: s2})
        self.assertEqual(analytics.low_attendance_students(self.term_b, TODAY)["rows"], [])

    def test_needs_five_marked_days(self):
        for d in (1, 2, 3, 6):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        self.assertEqual(analytics.low_attendance_students(self.term_b, TODAY)["rows"], [])

    def test_tab_context_switches_views_and_handles_no_term(self):
        ctx = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        self.assertEqual(ctx["absent_view"], "term")
        self.assertNotIn("no_term", ctx["absentees"])
        bogus = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="bogus")
        self.assertEqual(bogus["absent_view"], "month")
        self.term_b.delete()
        none = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        self.assertTrue(none["absentees"]["no_term"])
        hidden = analytics.attendance_tab_context(TODAY, include_absentees=False, absent_view="term")
        self.assertIsNone(hidden["absentees"])

    def test_only_the_chosen_view_is_queried(self):
        with mock.patch("core.analytics.low_attendance_students") as term_list:
            analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="month")
        term_list.assert_not_called()
        with mock.patch("core.analytics.frequent_absentees") as month_list:
            analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        month_list.assert_not_called()
