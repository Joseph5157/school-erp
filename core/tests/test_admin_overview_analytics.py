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
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        before = len(ctx)
        # More days of data must not add queries (no per-row loops).
        for d in (3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        self.assertEqual(len(ctx), before)

    def test_non_administrators_are_still_denied(self):
        response = self.non_admin.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Attendance, last 14 days", status_code=403)
