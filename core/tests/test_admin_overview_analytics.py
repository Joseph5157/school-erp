"""Admin Overview analytics, Gate A (docs/ADMIN_OVERVIEW_ANALYTICS_PLAN.md).

Dates are pinned: the fixture year runs 2026-06-01..2027-04-30 and "today" is patched to
Tue 2026-07-14, so these tests do not depend on the real calendar.
"""

import datetime
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import analytics
from core.models import (
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Section,
)
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin

TODAY = datetime.date(2026, 7, 14)  # Tuesday
P, A = AttendanceStatus.PRESENT, AttendanceStatus.ABSENT


class AnalyticsFixture(AuthorizationClientsMixin, AttendanceFixtureMixin):
    def setUp(self):
        super().setUp()
        # The fixture's own register is dated before every period used below.
        self.build_attendance_fixture(date="2026-06-01")
        self.s1 = self.enrollment
        self.s2 = self.enroll_student("Meena Das", self.class_grade, self.section)
        for target in ("core.reports.business_today", "core.analytics.business_today"):
            patcher = mock.patch(target, return_value=TODAY)
            patcher.start()
            self.addCleanup(patcher.stop)

    def enroll_student(self, name, class_grade, section):
        applicant = Applicant.objects.create(full_name=name)
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        return applicant.progress_to_student().enroll(
            academic_year=self.year, class_grade=class_grade, section=section,
            start_date="2026-06-01",
        )

    def day(self, on_date, statuses, *, section=None, class_grade=None, submit=True):
        """Create a register for `on_date`, capture `{enrollment: status}`, optionally submit."""
        register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=class_grade or self.class_grade,
            section=section or self.section,
            date=on_date,
        )
        for enrollment, status in statuses.items():
            register.capture(enrollment=enrollment, status=status)
        if submit:
            register.submit(actor=self.admin_user)
        return register


class PeriodTests(TestCase):
    def test_default_period_is_the_last_14_days_ending_today(self):
        period = analytics.default_period(TODAY)
        self.assertEqual(period.end, TODAY)
        self.assertEqual(period.start, datetime.date(2026, 7, 1))
        self.assertEqual(period.days, 14)

    def test_previous_period_is_the_same_length_immediately_before(self):
        previous = analytics.previous_period(analytics.default_period(TODAY))
        self.assertEqual(previous.start, datetime.date(2026, 6, 17))
        self.assertEqual(previous.end, datetime.date(2026, 6, 30))
        self.assertEqual(previous.days, 14)


class EmptySchoolTests(TestCase):
    def test_empty_school_is_all_zeroes_and_has_no_chart(self):
        with mock.patch("core.reports.business_today", return_value=TODAY):
            strip = analytics.today_strip(TODAY)
            context = analytics.overview_context(TODAY)
        self.assertEqual(
            strip, {"present": 0, "absent": 0, "expected": 0, "submitted": 0, "not_taken": 0}
        )
        self.assertIsNone(context["chart"])
        self.assertEqual(context["classes"], [])
        self.assertEqual(context["summary"]["status"], "no_data")


class TodayStripTests(AnalyticsFixture, TestCase):
    def test_no_register_yet_is_expected_but_not_submitted(self):
        strip = analytics.today_strip(TODAY)
        self.assertEqual((strip["present"], strip["absent"]), (0, 0))
        self.assertEqual((strip["expected"], strip["submitted"], strip["not_taken"]), (1, 0, 1))

    def test_counts_only_submitted_registers_today(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        strip = analytics.today_strip(TODAY)
        self.assertEqual((strip["present"], strip["absent"]), (0, 0))
        self.assertEqual(strip["expected"], 1)
        self.assertEqual(strip["submitted"], 0)
        self.assertEqual(strip["not_taken"], 1)  # a DRAFT is still "not yet submitted"

    def test_submitted_register_is_counted(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        strip = analytics.today_strip(TODAY)
        self.assertEqual((strip["present"], strip["absent"]), (1, 1))
        self.assertEqual((strip["expected"], strip["submitted"], strip["not_taken"]), (1, 1, 0))

    def test_non_instructional_today_is_not_expected(self):
        sunday = datetime.date(2026, 7, 12)
        strip = analytics.today_strip(sunday)
        self.assertEqual((strip["expected"], strip["not_taken"]), (0, 0))


class DailyTrendTests(AnalyticsFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.period = analytics.default_period(TODAY)  # 2026-07-01 .. 2026-07-14

    def test_returns_percentage_per_day_with_submitted_data_only(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P}, submit=False)  # DRAFT
        points = analytics.daily_trend(self.period)
        self.assertEqual(
            [(p["date"], p["percentage"]) for p in points],
            [(datetime.date(2026, 7, 1), 100.0), (datetime.date(2026, 7, 2), 50.0)],
        )

    def test_days_without_a_submitted_register_are_omitted_not_zero(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        points = analytics.daily_trend(self.period)
        self.assertEqual(len(points), 1)

    def test_other_periods_are_excluded(self):
        self.day(datetime.date(2026, 6, 17), {self.s1: P, self.s2: A})
        self.assertEqual(analytics.daily_trend(self.period), [])


class TrendSummaryTests(AnalyticsFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.period = analytics.default_period(TODAY)

    def test_no_data_at_all(self):
        summary = analytics.trend_summary(self.period)
        self.assertFalse(summary["has_data"])
        self.assertEqual(summary["status"], "no_data")
        self.assertIsNone(summary["peak"])

    def test_no_comparison_without_a_previous_period(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        summary = analytics.trend_summary(self.period)
        self.assertTrue(summary["has_data"])
        self.assertEqual(summary["current"], 100.0)
        self.assertIsNone(summary["previous"])
        self.assertEqual(summary["status"], "no_comparison")

    def test_improving(self):
        self.day(datetime.date(2026, 6, 17), {self.s1: P, self.s2: A})  # previous 50
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})   # current 100
        summary = analytics.trend_summary(self.period)
        self.assertEqual((summary["current"], summary["previous"]), (100.0, 50.0))
        self.assertEqual(summary["delta"], 50.0)
        self.assertEqual(summary["status"], "improving")

    def test_worsening(self):
        self.day(datetime.date(2026, 6, 17), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        self.assertEqual(analytics.trend_summary(self.period)["status"], "worsening")

    def test_steady_within_one_point(self):
        self.day(datetime.date(2026, 6, 17), {self.s1: P, self.s2: A})
        self.day(datetime.date(2026, 7, 1), {self.s1: A, self.s2: P})
        self.assertEqual(analytics.trend_summary(self.period)["status"], "steady")

    def test_peak_and_lowest_days(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        summary = analytics.trend_summary(self.period)
        self.assertEqual(summary["peak"]["date"], datetime.date(2026, 7, 1))
        self.assertEqual(summary["lowest"]["date"], datetime.date(2026, 7, 2))


class ClassComparisonTests(AnalyticsFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.period = analytics.default_period(TODAY)
        self.grade2 = ClassGrade.objects.create(name="Grade 2")
        self.section2 = Section.objects.create(class_grade=self.grade2, name="A")
        self.g2_student = self.enroll_student("Kiran Rao", self.grade2, self.section2)

    def test_lowest_attendance_first(self):
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: P, self.s2: A})
        self.day(d, {self.g2_student: P}, section=self.section2, class_grade=self.grade2)
        rows = analytics.class_comparison(self.period)
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1", "Grade 2"])
        self.assertEqual([r["percentage"] for r in rows], [50.0, 100.0])

    def test_class_with_only_a_draft_register_is_left_out(self):
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: P, self.s2: A})
        self.day(d, {self.g2_student: P}, section=self.section2, class_grade=self.grade2, submit=False)
        rows = analytics.class_comparison(self.period)
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1"])

    def test_no_data_is_an_empty_list(self):
        self.assertEqual(analytics.class_comparison(self.period), [])


class TrendChartTests(TestCase):
    def test_points_scale_into_the_viewbox(self):
        points = [
            {"date": datetime.date(2026, 7, 1), "percentage": 100.0},
            {"date": datetime.date(2026, 7, 2), "percentage": 50.0},
        ]
        chart = analytics.trend_chart(points, width=300, height=100)
        self.assertEqual(len(chart["coords"]), 2)
        self.assertLess(chart["coords"][0][0], chart["coords"][1][0])  # x increases with date
        self.assertLess(chart["coords"][0][1], chart["coords"][1][1])  # higher % is nearer the top
        self.assertTrue(all(0 <= x <= 300 and 0 <= y <= 100 for x, y in chart["coords"]))

    def test_a_single_point_does_not_divide_by_zero(self):
        chart = analytics.trend_chart(
            [{"date": datetime.date(2026, 7, 1), "percentage": 80.0}], width=300, height=100
        )
        self.assertEqual(len(chart["coords"]), 1)

    def test_no_points_gives_no_chart(self):
        self.assertIsNone(analytics.trend_chart([], width=300, height=100))


class FrequentAbsenteesTests(AnalyticsFixture, TestCase):
    """Gate B: a student is listed once absent on at least N submitted days in the period."""

    def setUp(self):
        super().setUp()
        self.period = analytics.default_period(TODAY)  # 2026-07-01 .. 2026-07-14

    def absent_days(self, s2_days, s1_days=()):
        for d in sorted(set(s2_days) | set(s1_days)):
            self.day(
                datetime.date(2026, 7, d),
                {self.s1: A if d in s1_days else P, self.s2: A if d in s2_days else P},
            )

    def test_default_threshold_is_three_absent_days(self):
        self.assertEqual(analytics.ABSENTEE_THRESHOLD_DAYS, 3)

    def test_lists_only_students_at_or_over_the_threshold(self):
        self.absent_days(s2_days=(1, 2, 3), s1_days=(2, 3))  # Wed, Thu, Fri
        result = analytics.frequent_absentees(self.period)
        self.assertEqual([r["name"] for r in result["rows"]], ["Meena Das"])
        self.assertEqual(result["rows"][0]["absent_days"], 3)
        self.assertEqual(result["rows"][0]["class_name"], "Grade 1")
        self.assertEqual(result["total"], 1)

    def test_draft_registers_do_not_count(self):
        self.absent_days(s2_days=(1, 2))
        self.day(datetime.date(2026, 7, 3), {self.s1: P, self.s2: A}, submit=False)
        self.assertEqual(analytics.frequent_absentees(self.period)["rows"], [])

    def test_absences_outside_the_period_do_not_count(self):
        self.day(datetime.date(2026, 6, 17), {self.s1: P, self.s2: A})
        self.day(datetime.date(2026, 6, 18), {self.s1: P, self.s2: A})
        self.absent_days(s2_days=(1,))
        self.assertEqual(analytics.frequent_absentees(self.period)["rows"], [])

    def test_most_absent_first_and_limit_keeps_the_true_total(self):
        self.absent_days(s2_days=(1, 2, 3, 6), s1_days=(1, 2, 3))
        result = analytics.frequent_absentees(self.period, limit=1)
        self.assertEqual([r["name"] for r in result["rows"]], ["Meena Das"])
        self.assertEqual(result["total"], 2)

    def test_row_carries_the_student_id_for_the_detail_link(self):
        self.absent_days(s2_days=(1, 2, 3))
        row = analytics.frequent_absentees(self.period)["rows"][0]
        self.assertEqual(row["student_id"], self.s2.student_id)

    def test_threshold_is_adjustable(self):
        self.absent_days(s2_days=(1,))
        self.assertEqual(len(analytics.frequent_absentees(self.period, threshold=1)["rows"]), 1)


class HeatmapTests(AnalyticsFixture, TestCase):
    def cells(self):
        weeks = analytics.attendance_heatmap(TODAY)
        return weeks, {c["date"]: c for week in weeks for c in week}

    def test_grid_is_whole_monday_to_sunday_weeks(self):
        weeks, cells = self.cells()
        self.assertEqual(len(weeks), 5)  # Mon 15 Jun .. Sun 19 Jul covers the 28 days to today
        self.assertTrue(all(len(week) == 7 for week in weeks))
        self.assertEqual(weeks[0][0]["date"], datetime.date(2026, 6, 15))
        self.assertEqual(weeks[0][0]["date"].weekday(), 0)

    def test_cells_outside_the_28_day_window_are_marked_outside(self):
        _, cells = self.cells()
        self.assertEqual(cells[datetime.date(2026, 6, 15)]["state"], "outside")  # before window
        self.assertEqual(cells[datetime.date(2026, 7, 15)]["state"], "outside")  # future

    def test_data_days_get_a_tier_by_percentage(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        _, cells = self.cells()
        self.assertEqual(cells[datetime.date(2026, 7, 1)]["state"], "data")
        self.assertEqual(cells[datetime.date(2026, 7, 1)]["tier"], "t4")
        self.assertEqual(cells[datetime.date(2026, 7, 2)]["tier"], "t1")

    def test_school_day_without_a_submitted_register_is_no_data_not_zero(self):
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P}, submit=False)  # DRAFT
        _, cells = self.cells()
        self.assertEqual(cells[datetime.date(2026, 7, 6)]["state"], "no_data")
        self.assertEqual(cells[datetime.date(2026, 7, 7)]["state"], "no_data")

    def test_sunday_is_not_a_school_day(self):
        _, cells = self.cells()
        self.assertEqual(cells[datetime.date(2026, 7, 5)]["state"], "not_school")


class OverviewAnalyticsViewTests(AnalyticsFixture, TestCase):
    url = reverse("core:admin-overview")

    def test_empty_school_shows_honest_empty_states(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "Attendance, last 14 days")
        self.assertContains(response, "No submitted attendance in this period yet.")
        self.assertNotContains(response, '<svg class="erp-trend"')

    def test_renders_strip_trend_and_class_bars_with_data(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        self.day(TODAY, {self.s1: P, self.s2: A})
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-today-strip")
        self.assertContains(response, '<svg class="erp-trend"')
        self.assertContains(response, "Grade 1")
        self.assertContains(response, "erp-class-bar")

    def test_chart_has_a_text_alternative(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        response = self.administrator.get(self.url)
        self.assertContains(response, 'role="img"')
        self.assertContains(response, "erp-visually-hidden-data")

    def test_there_is_no_late_status_anywhere(self):
        response = self.administrator.get(self.url)
        self.assertNotContains(response, "Late")

    def test_query_count_stays_bounded(self):
        # One frequent absentee (s2: 3 days) before; two (s1 joins) and more days after.
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        before = len(ctx)
        # More days and more absentee rows must not add queries (no per-row loops).
        for d in (6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: A, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        self.assertEqual(len(ctx), before)

    def make_frequent_absentee(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})

    def test_absentee_cards_link_to_the_student(self):
        self.make_frequent_absentee()
        response = self.administrator.get(self.url)
        self.assertContains(response, "Frequent absentees")
        self.assertContains(response, "Meena Das")
        self.assertContains(
            response, reverse("core:student-detail", args=[self.s2.student_id])
        )
        self.assertContains(response, "3 days absent")

    def test_absentee_empty_state_names_the_threshold(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "Frequent absentees")
        self.assertContains(response, "No student was absent 3 or more days")

    def test_absentee_list_is_hidden_without_permission_to_view_students(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        self.make_frequent_absentee()
        user = get_user_model().objects.create_user(username="overview-only", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="overview-only", password="pass-12345")
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Frequent absentees")
        self.assertNotContains(response, "Meena Das")

    def test_heatmap_renders_with_a_text_alternative(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-heat")
        self.assertContains(response, "erp-heat-cell--t4")
        self.assertContains(response, "erp-heat-cell--not_school")
        self.assertContains(response, "erp-visually-hidden-data")

    def test_non_administrators_are_still_denied(self):
        response = self.non_admin.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Attendance, last 14 days", status_code=403)
