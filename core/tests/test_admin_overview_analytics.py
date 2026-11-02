"""Admin Overview analytics, Gate A (docs/ADMIN_OVERVIEW_ANALYTICS_PLAN.md).

Dates are pinned: the fixture year runs 2026-06-01..2027-04-30 and "today" is patched to
Tue 2026-07-14, so these tests do not depend on the real calendar.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core import analytics
from core.models import (
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    Assessment,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    ResultStatus,
    Section,
    StudentResult,
    Subject,
    TermPublication,
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
        self.assertNotContains(response, '<svg class="erp-trend ')

    def test_renders_strip_trend_and_class_bars_with_data(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        self.day(TODAY, {self.s1: P, self.s2: A})
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-donut")
        self.assertContains(response, '<svg class="erp-trend erp-trend--phone"')
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


# --- Gate C: period filter -------------------------------------------------------------


class ResolvePeriodTests(TestCase):
    """`resolve_period` turns GET params into a safe Period; bad input falls back to 14 days."""

    def setUp(self):
        year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 4, 30)
        )
        self.term = AcademicTerm.objects.create(
            academic_year=year, name="Term 1", start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 9, 30), display_order=1,
        )

    def resolve(self, **params):
        return analytics.resolve_period(params, TODAY)

    def assertFallsBack(self, choice, notice_part=None):
        self.assertEqual(choice["key"], "14d")
        self.assertEqual(choice["period"], analytics.default_period(TODAY))
        if notice_part:
            self.assertIn(notice_part, choice["notice"])

    def test_default_is_14_days_without_a_notice(self):
        choice = self.resolve()
        self.assertFallsBack(choice)
        self.assertEqual(choice["label"], "last 14 days")
        self.assertIsNone(choice["notice"])

    def test_unknown_choice_falls_back_quietly(self):
        choice = self.resolve(period="bogus")
        self.assertFallsBack(choice)
        self.assertIsNone(choice["notice"])

    def test_this_month_runs_from_the_first_to_today(self):
        choice = self.resolve(period="month")
        self.assertEqual(choice["key"], "month")
        self.assertEqual(choice["period"].start, datetime.date(2026, 7, 1))
        self.assertEqual(choice["period"].end, TODAY)
        self.assertEqual(choice["label"], "this month")

    def test_this_term_is_the_term_running_today_capped_at_today(self):
        choice = self.resolve(period="term")
        self.assertEqual(choice["key"], "term")
        self.assertEqual(choice["period"].start, datetime.date(2026, 6, 1))
        self.assertEqual(choice["period"].end, TODAY)  # the term ends later; never the future
        self.assertEqual(choice["label"], "Term 1")
        self.assertEqual(choice["term"], self.term)

    def test_this_term_without_a_running_term_falls_back_with_a_notice(self):
        self.term.delete()
        choice = self.resolve(period="term")
        self.assertFallsBack(choice, "No term is running")
        self.assertIsNone(choice["term"])

    def test_a_finished_term_is_not_the_current_term(self):
        AcademicTerm.objects.filter(pk=self.term.pk).update(end_date=datetime.date(2026, 6, 30))
        self.assertIsNone(self.resolve()["term"])

    def test_custom_range(self):
        choice = self.resolve(period="custom", **{"from": "2026-07-03", "to": "2026-07-10"})
        self.assertEqual(choice["key"], "custom")
        self.assertEqual(choice["period"].start, datetime.date(2026, 7, 3))
        self.assertEqual(choice["period"].end, datetime.date(2026, 7, 10))
        self.assertEqual(choice["label"], "3 Jul – 10 Jul")
        self.assertEqual((choice["custom_from"], choice["custom_to"]), ("2026-07-03", "2026-07-10"))

    def test_custom_end_in_the_future_is_capped_at_today(self):
        choice = self.resolve(period="custom", **{"from": "2026-07-03", "to": "2026-12-31"})
        self.assertEqual(choice["period"].end, TODAY)

    def test_custom_start_in_the_future_falls_back(self):
        self.assertFallsBack(
            self.resolve(period="custom", **{"from": "2026-08-01", "to": "2026-08-10"}),
            "future",
        )

    def test_custom_reversed_range_falls_back(self):
        self.assertFallsBack(
            self.resolve(period="custom", **{"from": "2026-07-10", "to": "2026-07-03"}),
            "before",
        )

    def test_custom_missing_or_invalid_dates_fall_back(self):
        self.assertFallsBack(self.resolve(period="custom"), "dates")
        self.assertFallsBack(
            self.resolve(period="custom", **{"from": "nope", "to": "2026-07-03"}), "dates"
        )

    def test_custom_range_longer_than_a_year_falls_back(self):
        self.assertFallsBack(
            self.resolve(period="custom", **{"from": "2025-01-01", "to": "2026-07-10"}), "year"
        )


class PeriodFilterViewTests(AnalyticsFixture, TestCase):
    url = reverse("core:admin-overview")

    def test_default_view_offers_the_period_choices(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-period")
        self.assertContains(response, 'value="14d"')
        self.assertContains(response, 'value="month"')
        self.assertContains(response, 'value="custom"')

    def test_this_term_choice_is_offered_only_when_a_term_runs_today(self):
        self.assertNotContains(self.administrator.get(self.url), 'value="term"')
        AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 9, 30), display_order=1,
        )
        self.assertContains(self.administrator.get(self.url), 'value="term"')

    def test_this_month_changes_the_window_and_the_title(self):
        # 2026-06-30 is inside the default 14 days' *previous* window but outside "this month".
        self.day(datetime.date(2026, 6, 30), {self.s1: A, self.s2: A})
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: P})
        response = self.administrator.get(self.url, {"period": "month"})
        context = response.context["attendance_analytics"]
        self.assertEqual(context["period"].start, datetime.date(2026, 7, 1))
        self.assertEqual([p["date"] for p in context["points"]], [datetime.date(2026, 7, 2)])
        self.assertContains(response, "Attendance, this month")

    def test_custom_range_drives_the_chart(self):
        self.day(datetime.date(2026, 7, 3), {self.s1: P, self.s2: A})
        self.day(datetime.date(2026, 7, 9), {self.s1: P, self.s2: P})
        response = self.administrator.get(
            self.url, {"period": "custom", "from": "2026-07-03", "to": "2026-07-05"}
        )
        points = response.context["attendance_analytics"]["points"]
        self.assertEqual([p["date"] for p in points], [datetime.date(2026, 7, 3)])
        self.assertContains(response, "3 Jul")

    def test_invalid_custom_range_shows_a_notice_and_the_default_window(self):
        response = self.administrator.get(
            self.url, {"period": "custom", "from": "2026-07-10", "to": "2026-07-03"}
        )
        self.assertContains(response, "Showing the last 14 days instead")
        self.assertEqual(response.context["attendance_analytics"]["period_days"], 14)

    def test_absentees_follow_the_selected_period(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        shorter = self.administrator.get(
            self.url, {"period": "custom", "from": "2026-07-02", "to": "2026-07-14"}
        )
        self.assertEqual(shorter.context["attendance_analytics"]["absentees"]["rows"], [])
        self.assertEqual(
            len(self.administrator.get(self.url).context["attendance_analytics"]["absentees"]["rows"]),
            1,
        )

    def test_period_choice_does_not_change_the_query_count_between_options(self):
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        counts = []
        for params in ({}, {"period": "month"}, {"period": "custom", "from": "2026-07-01", "to": "2026-07-05"}):
            with CaptureQueriesContext(connection) as ctx:
                self.administrator.get(self.url, params)
            counts.append(len(ctx))
        self.assertLessEqual(max(counts) - min(counts), 2)  # term lookup / marks term lookup only


# --- Gate C: marks snapshot ------------------------------------------------------------


class MarksFixture(AnalyticsFixture):
    def setUp(self):
        super().setUp()
        self.term_a = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 6, 30), display_order=1,
        )
        self.term_b = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 2", start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 9, 30), display_order=2,
        )
        self.maths = Subject.objects.create(name="Mathematics")

    def assessment(self, scores, *, name="Unit Test", term=None, class_grade=None, section=None,
                   maximum="20", finalize=True, subject=None, pass_mark=None):
        """An assessment with `{enrollment: score}` results; a score of None is ABSENT."""
        class_grade = class_grade or self.class_grade
        term = term or self.term_b
        subject = subject or self.maths
        offering, _ = AcademicSubjectOffering.objects.get_or_create(
            academic_year=self.year, class_grade=class_grade, subject=subject
        )
        assessment = Assessment(
            term=term, offering=offering, section=section or self.section, name=name,
            assessment_date=term.start_date, maximum_marks=Decimal(maximum),
            pass_mark=None if pass_mark is None else Decimal(str(pass_mark)),
        )
        assessment.full_clean()
        assessment.save()
        for enrollment, score in scores.items():
            StudentResult.objects.create(
                assessment=assessment, academic_enrollment=enrollment, entered_by=self.admin_user,
                status=ResultStatus.ABSENT if score is None else ResultStatus.MARKED,
                score=None if score is None else Decimal(str(score)),
            )
        if finalize:
            Assessment.objects.filter(pk=assessment.pk).update(
                status=Assessment.Status.FINALIZED, finalized_by=self.admin_user,
                finalized_at=timezone.now(), subject_label=subject.name,
            )
        return assessment

    def second_class(self):
        grade = ClassGrade.objects.create(name="Grade 2")
        section = Section.objects.create(class_grade=grade, name="A")
        return grade, section, self.enroll_student("Ravi Jain", grade, section)


class MarksSnapshotTests(MarksFixture, TestCase):
    def test_no_assessments_gives_no_snapshot(self):
        self.assertIsNone(analytics.marks_snapshot(TODAY))

    def test_draft_assessments_are_not_official(self):
        self.assessment({self.s1: 15}, finalize=False)
        self.assertIsNone(analytics.marks_snapshot(TODAY))

    def test_average_is_a_percentage_of_the_maximum_per_class(self):
        self.assessment({self.s1: 15, self.s2: 10})  # 75% and 50%
        snapshot = analytics.marks_snapshot(TODAY)
        self.assertEqual(snapshot["term"], self.term_b)
        self.assertEqual(
            [(r["class_name"], r["average"], r["results"]) for r in snapshot["classes"]],
            [("Grade 1", 62.5, 2)],
        )

    def test_different_maximums_are_normalised(self):
        self.assessment({self.s1: 18}, maximum="30", name="Out of 30")  # 60%
        self.assessment({self.s1: 20}, maximum="20", name="Out of 20")  # 100%
        snapshot = analytics.marks_snapshot(TODAY)
        self.assertEqual(snapshot["classes"][0]["average"], 80.0)

    def test_an_absent_result_is_never_a_zero(self):
        self.assessment({self.s1: 16, self.s2: None})
        snapshot = analytics.marks_snapshot(TODAY)
        self.assertEqual(snapshot["classes"][0]["average"], 80.0)  # not 40.0
        self.assertEqual(snapshot["classes"][0]["results"], 1)
        self.assertEqual(snapshot["absent"], 1)

    def test_draft_results_do_not_leak_into_a_finalized_average(self):
        self.assessment({self.s1: 20, self.s2: 20}, name="Final one")
        self.assessment({self.s1: 0, self.s2: 0}, name="Still draft", finalize=False)
        self.assertEqual(analytics.marks_snapshot(TODAY)["classes"][0]["average"], 100.0)

    def test_classes_are_listed_lowest_average_first(self):
        grade, section, s3 = self.second_class()
        self.assessment({self.s1: 18}, name="G1")
        self.assessment({s3: 8}, name="G2", class_grade=grade, section=section)
        names = [r["class_name"] for r in analytics.marks_snapshot(TODAY)["classes"]]
        self.assertEqual(names, ["Grade 2", "Grade 1"])

    def test_score_bands_count_results_and_sum_to_the_total(self):
        # 100%, 80%, 60%, 35%, and 59.9% which belongs in 40-59.
        self.assessment({self.s1: 20, self.s2: 16}, name="A")
        self.assessment({self.s1: 12, self.s2: 7}, name="B")
        self.assessment({self.s1: 11.98}, name="C")
        snapshot = analytics.marks_snapshot(TODAY)
        counts = {band["label"]: band["count"] for band in snapshot["bands"]}
        self.assertEqual(
            counts,
            {"80% and above": 2, "60–79%": 1, "40–59%": 1, "Below 40%": 1},
        )
        self.assertEqual(sum(counts.values()), snapshot["total"])
        self.assertEqual(sum(band["share"] for band in snapshot["bands"]), 100)

    def test_the_latest_term_with_finalized_results_is_used(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        self.assertEqual(analytics.marks_snapshot(TODAY)["term"], self.term_a)
        self.assessment({self.s1: 20}, name="New", term=self.term_b)
        snapshot = analytics.marks_snapshot(TODAY)
        self.assertEqual(snapshot["term"], self.term_b)
        self.assertEqual(snapshot["classes"][0]["average"], 100.0)  # term A not mixed in

    def test_a_term_that_has_not_started_is_ignored(self):
        future = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 3", start_date=datetime.date(2026, 10, 1),
            end_date=datetime.date(2026, 12, 31), display_order=3,
        )
        self.assessment({self.s1: 20}, name="Early", term=future)
        self.assertIsNone(analytics.marks_snapshot(TODAY))


class MarksSnapshotViewTests(MarksFixture, TestCase):
    url = reverse("core:admin-overview")

    def test_renders_term_class_average_and_bands(self):
        self.assessment({self.s1: 15, self.s2: 10})
        response = self.administrator.get(self.url)
        self.assertContains(response, "Marks by subject")
        self.assertContains(response, "Term 2")
        self.assertContains(response, "Mathematics")
        self.assertContains(response, "63%")
        self.assertContains(response, "80% and above")
        self.assertContains(response, "erp-visually-hidden-data")

    def test_empty_state_is_honest(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "Marks by subject")
        self.assertContains(response, "No finalized results yet.")

    def test_hidden_without_permission_to_view_results(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        self.assessment({self.s1: 15})
        user = get_user_model().objects.create_user(username="no-marks", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="no-marks", password="pass-12345")
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Marks by subject")
        self.assertNotContains(response, "Score bands")

    def test_marks_do_not_follow_the_attendance_period(self):
        self.assessment({self.s1: 15})
        response = self.administrator.get(self.url, {"period": "custom", "from": "2026-07-03", "to": "2026-07-04"})
        self.assertContains(response, "Marks by subject")
        self.assertContains(response, "75%")

    def test_marks_by_subject_lists_lowest_first_and_names_the_term(self):
        science = Subject.objects.create(name="Science")
        self.assessment({self.s1: 18, self.s2: 16}, name="Maths test")  # 90%, 80%: 85
        self.assessment({self.s1: 8, self.s2: 12}, name="Sci test", subject=science)  # 50
        context = analytics.overview_context(TODAY, include_marks=True)
        self.assertEqual(
            [(r["label"], r["display"], r["low"]) for r in context["marks_subjects"]],
            [("Science", "50%", False), ("Mathematics", "85%", False)],
        )
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-analytics-card--subjects")
        self.assertContains(response, "Marks by subject, Term 2")
        content = response.content.decode()
        self.assertLess(content.index(">Science<"), content.index(">Mathematics<"))
        self.assertContains(response, "erp-class-bar--marks")
        self.assertNotContains(response, "erp-class-bar--low")

    def test_score_bands_draw_as_columns_with_counts(self):
        self.assessment({self.s1: 20, self.s2: 16}, name="A")  # 100, 80
        self.assessment({self.s1: 12, self.s2: 7}, name="B")  # 60, 35
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-analytics-card--bands")
        self.assertContains(response, "Score bands, Term 2")
        content = response.content.decode()
        card = content[content.index("erp-analytics-card--bands"):]
        self.assertEqual(card.count('width="24"'), 4)
        for label in ("80% and above", "60–79%", "40–59%", "Below 40%"):
            self.assertIn(f'aria-label="{label}: ', card)
        context = analytics.overview_context(TODAY, include_marks=True)
        self.assertEqual(
            [(r["label"], r["display"]) for r in context["marks"]["band_columns"]],
            [("80% and above", "2"), ("60–79%", "1"), ("40–59%", "0"), ("Below 40%", "1")],
        )
        self.assertIn("Finalized only, absent not counted as zero", card)

    def test_band_column_heights_follow_the_share_not_the_count(self):
        self.assessment({self.s1: 20, self.s2: 20}, name="A")  # both 100%
        columns = analytics.overview_context(TODAY, include_marks=True)["marks"]["band_columns"]
        self.assertEqual(columns[0]["value"], 100)
        self.assertEqual(columns[0]["bar_height"], 120)
        self.assertEqual(columns[3]["bar_height"], 0)

    def test_marks_cards_need_results_permission(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        self.assessment({self.s1: 15})
        user = get_user_model().objects.create_user(username="no-marks2", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="no-marks2", password="pass-12345")
        response = client.get(self.url)
        self.assertNotContains(response, "Marks by subject")
        self.assertNotContains(response, "erp-analytics-card--bands")
        context = analytics.overview_context(TODAY)
        self.assertIsNone(context["marks"])
        self.assertEqual(context["marks_subjects"], [])

    def test_no_results_shows_the_existing_empty_message(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "No finalized results yet.", count=2)
        self.assertNotContains(response, "erp-cols--marks")

    def test_more_results_do_not_add_queries(self):
        self.assessment({self.s1: 15}, name="First")
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        before = len(ctx)
        grade, section, s3 = self.second_class()
        self.assessment({self.s2: 9}, name="Second")
        self.assessment({s3: 12}, name="Third", class_grade=grade, section=section)
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        self.assertEqual(len(ctx), before)


# --- Desktop layout ("Option B" card grid, docs/ui-reviews/desktop-overview-options.html) ---


class DesktopLayoutTests(AnalyticsFixture, TestCase):
    """Desktop gets its own pieces; the phone pieces stay in the page (CSS picks by width)."""

    url = reverse("core:admin-overview")

    def with_data(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P})

    def test_a_wide_chart_is_built_for_desktop_next_to_the_phone_chart(self):
        self.with_data()
        context = analytics.overview_context(TODAY)
        self.assertEqual((context["chart"]["width"], context["chart"]["height"]), (320, 120))
        self.assertEqual((context["chart_wide"]["width"], context["chart_wide"]["height"]), (720, 200))
        html = self.administrator.get(self.url).content.decode()
        self.assertIn('class="erp-trend erp-trend--phone"', html)
        self.assertIn('class="erp-trend erp-trend--wide"', html)

    def test_no_data_means_no_wide_chart_either(self):
        self.assertIsNone(analytics.overview_context(TODAY)["chart_wide"])

    def test_period_quick_links_mark_the_current_choice(self):
        html = self.administrator.get(self.url, {"period": "month"}).content.decode()
        self.assertIn('class="erp-period-seg"', html)
        self.assertRegex(html, r'<a[^>]*href="[^"]*\?period=month"[^>]*aria-current="page"')
        self.assertRegex(html, r'<a[^>]*href="[^"]*\?period=14d"')
        self.assertNotRegex(html, r'<a[^>]*href="[^"]*\?period=14d"[^>]*aria-current')
        self.assertNotIn("?period=term", html)  # no term runs today in this fixture

    def test_trend_card_shows_headline_numbers(self):
        self.with_data()
        html = self.administrator.get(self.url).content.decode()
        stats = re.search(r'<dl class="erp-trend-stats">(.*?)</dl>', html, re.S).group(1)
        for label in ("Average", "Best day", "Lowest day", "Absentees"):
            self.assertIn(label, stats)

    def test_absentee_count_is_left_out_without_permission_to_view_students(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        self.with_data()
        user = get_user_model().objects.create_user(username="desk-only", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="desk-only", password="pass-12345")
        stats = re.search(
            r'<dl class="erp-trend-stats">(.*?)</dl>', client.get(self.url).content.decode(), re.S
        ).group(1)
        self.assertNotIn("Absentees", stats)

    def test_heatmap_card_names_the_lowest_and_best_class(self):
        grade = ClassGrade.objects.create(name="Grade 2")
        section = Section.objects.create(class_grade=grade, name="A")
        s3 = self.enroll_student("Ravi Jain", grade, section)
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})  # Grade 1: 50%
        self.day(datetime.date(2026, 7, 1), {s3: P}, class_grade=grade, section=section)  # 100%
        html = self.administrator.get(self.url).content.decode()
        callouts = re.search(r'<dl class="erp-class-callouts">(.*?)</dl>', html, re.S).group(1)
        self.assertRegex(callouts, r"Lowest class.*Grade 1.*50%")
        self.assertRegex(callouts, r"Best class.*Grade 2.*100%")

    def test_cards_are_tagged_for_the_desktop_grid(self):
        self.with_data()
        html = self.administrator.get(self.url).content.decode()
        for area in ("trend", "heat", "classes", "absent"):
            self.assertIn(f"erp-analytics-card--{area}", html)

    def test_trend_dots_and_heat_cells_name_their_value_on_hover(self):
        self.with_data()
        html = self.administrator.get(self.url).content.decode()
        self.assertIn("<title>1 Jul: 50.0%</title>", html)  # trend dot
        self.assertRegex(html, r'class="erp-heat-cell erp-heat-cell--t1" title="1 Jul: 50\.0%"')

    def test_marks_use_their_own_colour_not_the_attendance_one(self):
        html = self.administrator.get(self.url).content.decode()
        self.assertNotIn("erp-class-bar--marks", html)  # no marks permission/data here
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        for token in ("--erp-viz-attendance:", "--erp-viz-marks:", "--erp-viz-heat-1:", "--erp-viz-low:"):
            self.assertIn(token, css)
        self.assertIn(".erp-class-bar--marks::-webkit-progress-value", css)

    def test_desktop_grid_lives_only_in_the_desktop_media_query(self):
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css.split("/* ---------- Desktop Overview grid ---------- */", 1)[1]
        self.assertTrue(block.lstrip().startswith("@media (min-width: 992px)"))
        self.assertIn(".erp-analytics { display: grid;", block)


# --- Charts: gauge, donut, rings and class columns ------------------------------------------


class OverviewChartCardsTests(AnalyticsFixture, TestCase):
    url = reverse("core:admin-overview")

    def make_term(self, name="Term 1", start=datetime.date(2026, 6, 1),
                  end=datetime.date(2026, 9, 30), order=1):
        return AcademicTerm.objects.create(
            academic_year=self.year, name=name, start_date=start, end_date=end, display_order=order
        )

    def login_with(self, username, *codenames):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def second_class(self, name="Grade 2", student="Kiran Rao"):
        grade = ClassGrade.objects.create(name=name)
        section = Section.objects.create(class_grade=grade, name="A")
        return grade, section, self.enroll_student(student, grade, section)

    def rings(self, **kwargs):
        options = {
            "can_view_results": True, "can_view_publications": True,
            "missing_attendance_url": None, **kwargs,
        }
        return {r["key"]: r for r in analytics.completion_rings(TODAY, **options)}

    def publish(self, enrollment, term, status=TermPublication.Status.PUBLISHED):
        return TermPublication.objects.create(
            student=enrollment.student, term=term, placement=enrollment, version=1, status=status,
            term_label=term.name, academic_year_label="y", class_grade_label="g",
            section_label="A", fingerprint="x", published_by=self.admin_user,
        )

    def test_gauge_is_hidden_when_no_term_runs(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        response = self.administrator.get(self.url)
        self.assertNotContains(response, "erp-gauge")
        self.assertIsNone(analytics.term_attendance(TODAY))

    def test_gauge_is_hidden_when_the_term_has_no_attendance(self):
        self.make_term()
        self.assertIsNone(analytics.term_attendance(TODAY))
        self.assertNotContains(self.administrator.get(self.url), "erp-gauge")

    def test_gauge_uses_the_running_term_and_names_the_80_target(self):
        self.make_term()
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        self.assertEqual(analytics.ATTENDANCE_TARGET_PERCENT, 80)
        data = analytics.term_attendance(TODAY)
        self.assertEqual((data["term"].name, data["percent"]), ("Term 1", 50))
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-gauge")
        self.assertContains(response, "Target 80%")

    def test_gauge_ignores_a_term_that_has_ended(self):
        self.make_term(end=datetime.date(2026, 7, 10))
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        self.assertIsNone(analytics.term_attendance(TODAY))

    def test_donut_shows_todays_counts(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        response = self.administrator.get(self.url)
        self.assertContains(response, '<svg class="erp-donut"')
        self.assertContains(response, "Present 1")
        self.assertContains(response, "Absent 1")

    def test_no_school_day_message_replaces_the_donut(self):
        sunday = datetime.date(2026, 7, 12)
        for target in ("core.reports.business_today", "core.analytics.business_today"):
            patcher = mock.patch(target, return_value=sunday)
            patcher.start()
            self.addCleanup(patcher.stop)
        response = self.administrator.get(self.url)
        self.assertContains(response, "No school day today")
        self.assertNotContains(response, '<svg class="erp-donut"')

    def test_school_day_with_nothing_submitted_says_no_attendance_yet(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "No attendance yet")
        self.assertNotContains(response, "No school day today")
        self.assertNotContains(response, '<svg class="erp-donut"')

    def test_registers_ring_counts_submitted_of_expected(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        self.second_class()  # a second class is expected today but has no register
        strip = analytics.today_strip(TODAY)
        self.assertEqual((strip["submitted"], strip["expected"]), (1, 2))
        ring = self.rings()["registers"]
        self.assertEqual((ring["chart"]["done"], ring["chart"]["total"]), (1, 2))
        self.assertIsNone(ring["url"])
        report = reverse("core:report-missing-attendance")
        self.assertEqual(
            self.rings(missing_attendance_url=report)["registers"]["url"],
            f"{report}?start=2026-07-14&end=2026-07-14",
        )

    def test_registers_ring_links_only_for_viewers_who_can_open_the_report(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        report = reverse("core:report-missing-attendance")
        todays_report = f'href="{report}?start=2026-07-14&amp;end=2026-07-14"'
        self.assertContains(self.administrator.get(self.url), todays_report)
        overview_only = self.login_with("ov-only", "view_school")
        self.assertNotContains(overview_only.get(self.url), f'href="{report}')

    def test_registers_ring_link_opens_a_report_that_lists_the_missing_sections(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        self.second_class()  # expected today, no register yet
        link = self.rings(missing_attendance_url=reverse("core:report-missing-attendance"))[
            "registers"
        ]["url"]
        response = self.administrator.get(link)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 2")

    def test_marks_ring_needs_results_permission(self):
        self.assess(self.make_term(), "Done", datetime.date(2026, 7, 1), True)
        client = self.login_with("ov-only", "view_school")
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Marks entered")
        self.assertContains(self.administrator.get(self.url), "Marks entered")

    def test_publication_ring_needs_publication_permission(self):
        self.assess(self.make_term(), "Done", datetime.date(2026, 7, 1), True)
        client = self.login_with("ov-marks", "view_school", "view_studentresult")
        response = client.get(self.url)
        self.assertContains(response, "Marks entered")
        self.assertNotContains(response, "Results published")
        self.assertContains(self.administrator.get(self.url), "Results published")

    def assess(self, term, name, on_date, final):
        offering, _ = AcademicSubjectOffering.objects.get_or_create(
            academic_year=self.year, class_grade=self.class_grade,
            subject=Subject.objects.get_or_create(name="Mathematics")[0],
        )
        assessment = Assessment(
            term=term, offering=offering, section=self.section, name=name,
            assessment_date=on_date, maximum_marks=Decimal("20"),
        )
        assessment.full_clean()
        assessment.save()
        if final:
            Assessment.objects.filter(pk=assessment.pk).update(
                status=Assessment.Status.FINALIZED, finalized_by=self.admin_user,
                finalized_at=timezone.now(), subject_label="Mathematics",
            )

    def test_marks_ring_counts_finalized_of_assessments_dated_up_to_today(self):
        term = self.make_term()
        self.assess(term, "Done", datetime.date(2026, 7, 1), True)
        self.assess(term, "Open", datetime.date(2026, 7, 2), False)
        self.assess(term, "Later", datetime.date(2026, 8, 1), False)  # after today: not counted
        marks = self.rings()["marks"]
        self.assertEqual((marks["chart"]["done"], marks["chart"]["total"]), (1, 2))

    def test_marks_ring_is_left_out_when_the_term_has_no_assessments_yet(self):
        self.make_term()
        self.assertNotIn("marks", self.rings())

    def test_gauge_percent_is_the_unrounded_value_and_display_is_half_up(self):
        self.make_term()
        for percentage, display, met in ((84.5, "85", True), (79.6, "79.6", False)):
            with mock.patch.object(
                analytics.reports, "counts", return_value={"percentage": percentage}
            ):
                data = analytics.term_attendance(TODAY)
            self.assertEqual(data["chart"]["display"], display)
            self.assertEqual(data["chart"]["met"], met)

    def test_class_row_shows_one_number_and_flags_low_on_the_unrounded_value(self):
        def row(percentage):
            return {"class_name": "Grade 7", "class_grade_id": 1, "percentage": percentage}

        half = analytics._class_row(row(84.5), False)
        self.assertEqual((half["display"], half["low"]), ("85%", False))
        near = analytics._class_row(row(79.6), False)
        self.assertEqual((near["display"], near["low"]), ("79.6%", True))
        self.assertTrue(analytics._class_row(row(50.0), False)["low"])

    def test_lowest_and_best_class_callouts_use_the_same_number_as_the_columns(self):
        classes = [
            {"class_name": "Grade 2", "class_grade_id": 1, "percentage": 84.5,
             "display": "85", "present": 169, "absent": 31},
            {"class_name": "Grade 3", "class_grade_id": 2, "percentage": 100.0,
             "display": "100", "present": 5, "absent": 0},
        ]
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        with mock.patch.object(analytics, "class_comparison", return_value=classes):
            html = self.administrator.get(self.url).content.decode()
        self.assertIn("Grade 2, 85%", html)

    def test_class_comparison_rows_carry_the_shared_display(self):
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        row = analytics.class_comparison(analytics.default_period(TODAY))[0]
        self.assertEqual((row["percentage"], row["display"]), (50.0, "50"))

    def test_published_ring_counts_students_and_drops_stale_versions(self):
        term = self.make_term()
        self.publish(self.s1, term)
        self.publish(self.s2, term, status=TermPublication.Status.STALE)
        published = self.rings()["published"]
        self.assertEqual((published["chart"]["done"], published["chart"]["total"]), (1, 2))

    def deactivate(self, enrollment):
        Student = enrollment.student.__class__
        Student.objects.filter(pk=enrollment.student_id).update(status=Student.Status.INACTIVE)

    def test_published_ring_leaves_out_inactive_students_in_both_numbers(self):
        term = self.make_term()
        self.publish(self.s1, term)
        self.publish(self.s2, term)
        self.deactivate(self.s2)
        published = self.rings()["published"]
        self.assertEqual((published["chart"]["done"], published["chart"]["total"]), (1, 1))

    def test_a_published_student_who_is_not_active_does_not_count(self):
        term = self.make_term()
        self.publish(self.s2, term)
        self.deactivate(self.s2)
        published = self.rings()["published"]
        self.assertEqual((published["chart"]["done"], published["chart"]["total"]), (0, 1))

    def test_a_student_with_two_enrollments_in_the_term_counts_once(self):
        term = self.make_term()
        other = Section.objects.create(class_grade=self.class_grade, name="B")
        self.s1.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other,
            start_date="2026-07-01",
        )
        self.publish(self.s1, term)
        published = self.rings()["published"]
        self.assertEqual((published["chart"]["done"], published["chart"]["total"]), (1, 2))

    def test_withdrawn_and_superseded_publications_do_not_count(self):
        term = self.make_term()
        self.publish(self.s1, term, status=TermPublication.Status.WITHDRAWN)
        self.publish(self.s2, term, status=TermPublication.Status.SUPERSEDED)
        published = self.rings()["published"]
        self.assertEqual((published["chart"]["done"], published["chart"]["total"]), (0, 2))

    def test_term_rings_always_name_their_term_even_while_it_runs(self):
        term = self.make_term()
        self.assess(term, "Done", datetime.date(2026, 7, 1), True)
        rings = self.rings()
        self.assertEqual(rings["marks"]["label"], "Marks entered, Term 1")
        self.assertEqual(rings["published"]["label"], "Results published, Term 1")
        self.assertEqual(rings["registers"]["label"], "Registers today")

    def test_rings_between_terms_name_the_term_that_just_ended(self):
        term = self.make_term("Term 1", end=datetime.date(2026, 7, 10))
        self.assess(term, "Done", datetime.date(2026, 7, 1), True)
        rings = self.rings()
        self.assertEqual(rings["marks"]["term_name"], "Term 1")
        self.assertIn("Term 1", rings["marks"]["label"])
        self.assertIn("Term 1", rings["published"]["label"])
        self.assertNotIn("Term 1", rings["registers"]["label"])

    def test_term_rings_are_hidden_when_no_term_has_started(self):
        self.make_term("Later", start=datetime.date(2026, 9, 1), end=datetime.date(2026, 12, 1))
        self.assertEqual(list(self.rings()), ["registers"])

    def test_class_columns_are_in_class_order_not_by_performance(self):
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: P, self.s2: A})  # Grade 1: 50%
        g2, sec2, s_g2 = self.second_class("Grade 2", "Kiran Rao")
        self.day(d, {s_g2: P}, class_grade=g2, section=sec2)  # Grade 2: 100%
        g3, sec3, s_g3 = self.second_class("Grade 3", "Mina Rao")
        self.day(d, {s_g3: A}, class_grade=g3, section=sec3)  # Grade 3: 0%, still last
        context = analytics.overview_context(TODAY)
        self.assertEqual([c["label"] for c in context["class_columns"]],
                         ["Grade 1", "Grade 2", "Grade 3"])
        self.assertEqual([b["label"] for b in context["class_bars_phone"]],
                         ["Grade 3", "Grade 1", "Grade 2"])

    def test_class_order_is_natural_so_grade_10_follows_grade_9(self):
        d = datetime.date(2026, 7, 2)
        for name, student in (("Grade 10", "Ten Rao"), ("Grade 9", "Nine Rao")):
            grade, section, enrolment = self.second_class(name, student)
            self.day(d, {enrolment: P}, class_grade=grade, section=section)
        labels = [c["label"] for c in analytics.overview_context(TODAY)["class_columns"]]
        self.assertEqual(labels, ["Grade 9", "Grade 10"])

    def test_class_under_80_is_flagged_low(self):
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: P, self.s2: A})
        g2, sec2, s_g2 = self.second_class()
        self.day(d, {s_g2: P}, class_grade=g2, section=sec2)
        columns = {c["label"]: c for c in analytics.overview_context(TODAY)["class_columns"]}
        self.assertTrue(columns["Grade 1"]["low"])
        self.assertEqual(columns["Grade 1"]["display"], "50%")
        self.assertFalse(columns["Grade 2"]["low"])

    def test_phone_bars_are_the_five_lowest_classes(self):
        d = datetime.date(2026, 7, 2)
        for i in range(1, 8):
            grade, section, enrolment = self.second_class(f"Class {i}", f"Pupil {i}")
            self.day(d, {enrolment: P}, class_grade=grade, section=section)  # 100%
        self.day(d, {self.s1: A, self.s2: A})  # Grade 1: 0%
        context = analytics.overview_context(TODAY)
        self.assertEqual(len(context["class_bars_phone"]), 5)
        self.assertEqual(context["class_bars_phone"][0]["label"], "Grade 1")
        self.assertEqual(len(context["class_columns"]), 8)

    def many_classes(self, count):
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: A, self.s2: A})  # Grade 1: 0%
        for i in range(2, count + 1):
            grade, section, enrolment = self.second_class(f"Grade {i}", f"Pupil {i}")
            self.day(d, {enrolment: P}, class_grade=grade, section=section)

    def phone_card(self):
        html = self.administrator.get(self.url).content.decode()
        return html.split("erp-class-phone", 1)[1].split("</article>", 1)[0]

    def test_phone_details_hold_the_classes_beyond_the_five_lowest_in_class_order(self):
        self.many_classes(8)
        context = analytics.overview_context(TODAY)
        self.assertEqual([r["label"] for r in context["class_bars_rest"]],
                         ["Grade 6", "Grade 7", "Grade 8"])
        phone = self.phone_card()
        self.assertIn('<details class="erp-class-more">', phone)
        self.assertIn("Show all classes", phone)

    def test_phone_details_with_six_classes_holds_the_one_remaining_class(self):
        self.many_classes(6)
        details = self.phone_card().split('<details class="erp-class-more">', 1)[1]
        details = details.split("</details>", 1)[0]
        self.assertEqual(details.count("<progress"), 1)
        self.assertIn("Grade 6", details)

    def test_no_phone_details_with_five_or_fewer_classes(self):
        self.many_classes(5)
        self.assertEqual(analytics.overview_context(TODAY)["class_bars_rest"], [])
        phone = self.phone_card()
        self.assertNotIn("erp-class-more", phone)
        self.assertNotIn("Show all classes", phone)

    def test_phone_copy_for_one_class_is_not_the_1_lowest(self):
        self.many_classes(1)
        phone = self.phone_card()
        self.assertNotIn("1 lowest", phone)
        self.assertNotIn("lowest attendance", phone)

    def test_phone_copy_does_not_call_every_class_the_lowest(self):
        self.many_classes(5)
        self.assertNotIn("lowest attendance", self.phone_card())

    def test_phone_copy_says_the_five_lowest_when_more_classes_exist(self):
        self.many_classes(6)
        self.assertIn("The 5 classes with the lowest attendance", self.phone_card())

    def test_class_link_follows_permission_to_open_the_class(self):
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        detail = reverse("core:class-grade-detail", args=[self.class_grade.pk])
        everyone = reverse("core:class-grade-list")
        response = self.administrator.get(self.url)
        self.assertContains(response, f'href="{detail}"')
        self.assertNotContains(response, "erp-all-classes")
        overview_only = self.login_with("ov-only", "view_school")
        response = overview_only.get(self.url)
        self.assertContains(response, "Grade 1")
        self.assertNotContains(response, f'href="{detail}"')
        self.assertNotContains(response, f'href="{everyone}"')

    def test_class_link_absent_without_permission_to_open_it(self):
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        html = self.login_with("ov-only", "view_school").get(self.url).content.decode()
        self.assertNotRegex(html, r'<a[^>]*href="/classes/\d+/"')

    def test_query_count_stays_constant_with_more_classes(self):
        self.make_term()
        d = datetime.date(2026, 7, 2)
        self.day(d, {self.s1: P, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        before = len(ctx)
        for i in (2, 3):
            grade, section, enrolment = self.second_class(f"Grade {i}", f"Pupil {i}")
            self.day(d, {enrolment: P}, class_grade=grade, section=section)
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.url)
        self.assertEqual(len(ctx), before)


class OverviewChartLayoutTests(AnalyticsFixture, TestCase):
    """Phone order and the By class card's desktop spread, pinned honestly."""

    url = reverse("core:admin-overview")

    def css(self):
        text = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        return text.split("/* ---------- Desktop Overview grid ---------- */", 1)[1]

    def test_by_class_comes_before_the_trend_in_the_page_so_phones_show_it_first(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        html = self.administrator.get(self.url).content.decode()
        self.assertLess(
            html.index('class="erp-analytics-card erp-analytics-card--classes"'),
            html.index('class="erp-analytics-card erp-analytics-card--trend"'),
        )

    def test_desktop_grid_order_keeps_trend_above_by_class(self):
        block = self.css()
        self.assertIn(".erp-analytics > .erp-analytics-card--trend { grid-column: span 8; order: 1; }", block)
        self.assertIn(".erp-analytics > .erp-analytics-card--classes { grid-column: span 8; order: 3; }", block)

    def modifiers(self, client):
        html = client.get(self.url).content.decode()
        return re.search(r'<section class="(erp-analytics[^"]*)"', html).group(1)

    def login_with(self, username, *codenames):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_section_names_the_cards_that_are_missing_so_css_can_fill_the_row(self):
        classes = self.modifiers(self.administrator)
        self.assertIn("erp-analytics--no-gauge", classes)  # no running term
        self.assertNotIn("erp-analytics--no-absent", classes)
        AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 9, 30), display_order=1,
        )
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        self.assertEqual(self.modifiers(self.administrator), "erp-analytics")
        classes = self.modifiers(self.login_with("ov-only", "view_school"))
        self.assertIn("erp-analytics--no-absent", classes)
        self.assertNotIn("erp-analytics--no-gauge", classes)

    def test_section_marks_a_missing_rings_card(self):
        self.assertNotIn("erp-analytics--no-rings", self.modifiers(self.administrator))
        sunday = datetime.date(2026, 7, 12)  # no registers expected, so no Registers ring
        for target in ("core.reports.business_today", "core.analytics.business_today"):
            patcher = mock.patch(target, return_value=sunday)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.assertIn("erp-analytics--no-rings", self.modifiers(self.administrator))

    def test_desktop_rows_have_no_holes_when_a_card_is_missing(self):
        block = self.css()
        for rule in (
            ".erp-analytics--no-gauge .erp-analytics-card--donut { grid-column: span 6; }",
            ".erp-analytics--no-rings .erp-analytics-card--gauge,",
            ".erp-analytics--no-gauge.erp-analytics--no-rings .erp-analytics-card--donut { grid-column: span 12; }",
            ".erp-analytics--no-absent > .erp-analytics-card--classes { grid-column: span 12; }",
        ):
            self.assertIn(rule, block)

    def test_a_lone_card_fills_the_phone_row_only_on_phones(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        rule = ".erp-chart-pair .erp-chart-card:only-child { grid-column: 1 / -1; }"
        self.assertEqual(css.count(rule), 1)
        self.assertIn("@media (max-width: 991.98px) {\n  " + rule + "\n}", css)

    def test_phone_details_summary_is_a_44px_tap_target(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-class-more > summary \{[^}]*min-height: 2\.75rem")

    def test_by_class_columns_spread_without_clipping_on_overflow(self):
        block = self.css()
        self.assertTrue(block.lstrip().startswith("@media (min-width: 992px)"))
        self.assertIn(
            ".erp-analytics-card--classes .erp-cols { width: max-content; min-width: 100%; justify-content: space-around; }",
            block,
        )
        self.assertIn(".erp-analytics-card--classes .erp-chart-scroll { margin-block: auto; }", block)
