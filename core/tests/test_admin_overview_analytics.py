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

from core import analytics, marks_analytics
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
)
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin

TODAY = datetime.date(2026, 7, 14)  # Tuesday
P, A = AttendanceStatus.PRESENT, AttendanceStatus.ABSENT
# This month to TODAY, as the Attendance and Academics tabs use it: 2026-07-01 .. 2026-07-14.
DEFAULT_PERIOD = analytics.Period(start=datetime.date(2026, 7, 1), end=TODAY)


class AnalyticsFixture(AuthorizationClientsMixin, AttendanceFixtureMixin):
    def setUp(self):
        super().setUp()
        # The fixture's own register is dated before every period used below.
        self.build_attendance_fixture(date="2026-06-01")
        self.s1 = self.enrollment
        self.s2 = self.enroll_student("Meena Das", self.class_grade, self.section)
        # The view reads its own copy of today's date for every tab; pin both.
        for target in ("core.reports.business_today", "core.views.business_today"):
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


class EmptySchoolTests(TestCase):
    def test_empty_school_is_all_zeroes_and_has_no_chart(self):
        with mock.patch("core.reports.business_today", return_value=TODAY):
            strip = analytics.today_strip(TODAY)
        self.assertEqual(
            strip, {"present": 0, "absent": 0, "expected": 0, "submitted": 0, "not_taken": 0}
        )
        self.assertEqual(analytics.daily_trend(DEFAULT_PERIOD), [])
        self.assertEqual(analytics.class_comparison(DEFAULT_PERIOD), [])


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
        self.period = DEFAULT_PERIOD  # 2026-07-01 .. 2026-07-14

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


class ClassComparisonTests(AnalyticsFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.period = DEFAULT_PERIOD
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


class FrequentAbsenteesTests(AnalyticsFixture, TestCase):
    """Gate B: a student is listed once absent on at least N submitted days in the period."""

    def setUp(self):
        super().setUp()
        self.period = DEFAULT_PERIOD  # 2026-07-01 .. 2026-07-14

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
    attendance_url = reverse("core:admin-overview") + "?tab=attendance"

    def test_chart_has_a_text_alternative(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        response = self.administrator.get(self.url)
        self.assertContains(response, 'role="img"')
        self.assertContains(response, "erp-visually-hidden-data")

    def test_heatmap_intro_paragraph_is_closed_before_the_grid(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        html = self.administrator.get(self.attendance_url).content.decode()
        self.assertRegex(html, r'red is under 80%\.</p>\s*<div class="erp-heat"')

    def test_there_is_no_late_status_anywhere(self):
        response = self.administrator.get(self.url)
        self.assertNotContains(response, "Late")

    def test_query_count_stays_bounded(self):
        # One frequent absentee (s2: 3 days) before; two (s1 joins) and more days after.
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.attendance_url)
        before = len(ctx)
        # More days and more absentee rows must not add queries (no per-row loops).
        for d in (6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: A, self.s2: A})
        with CaptureQueriesContext(connection) as ctx:
            self.administrator.get(self.attendance_url)
        self.assertEqual(len(ctx), before)

    def make_frequent_absentee(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})

    def test_absentee_cards_link_to_the_student(self):
        self.make_frequent_absentee()
        response = self.administrator.get(self.attendance_url)
        self.assertContains(response, "Frequent absentees")
        self.assertContains(response, "Meena Das")
        self.assertContains(
            response, reverse("core:student-detail", args=[self.s2.student_id])
        )
        self.assertContains(response, "3 days absent")

    def test_absentee_empty_state_names_the_threshold(self):
        response = self.administrator.get(self.attendance_url)
        self.assertContains(response, "Frequent absentees")
        self.assertContains(response, "Absent 3 or more days, this month.")
        self.assertContains(response, "No student was absent 3 or more days this month.")

    def test_absentee_list_is_hidden_without_permission_to_view_students(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        self.make_frequent_absentee()
        user = get_user_model().objects.create_user(username="overview-only", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="overview-only", password="pass-12345")
        response = client.get(self.attendance_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Frequent absentees")
        self.assertNotContains(response, "Meena Das")

    def test_heatmap_renders_with_a_text_alternative(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: P})
        response = self.administrator.get(self.attendance_url)
        self.assertContains(response, "erp-heat")
        self.assertContains(response, "erp-heat-cell--t4")
        self.assertContains(response, "erp-heat-cell--not_school")
        # AO-02: the exact values are a visible table, not only hover titles.
        html = response.content.decode()
        heat = html[html.index("erp-analytics-card--heat"):]
        heat = heat[:heat.index("</article>")]
        self.assertIn("<summary>View heatmap figures</summary>", heat)
        self.assertIn('<th scope="row">Wed 1 Jul</th><td>100.0%</td>', heat)
        self.assertIn("<td>Not submitted</td>", heat)  # 2 Jul is a school day with no register
        self.assertNotIn("visually-hidden-data", heat)

    def test_charts_have_a_high_contrast_mode(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        block = css[css.index("@media (forced-colors: active) {"):]
        block = block[:block.index("\n}\n")]
        for rule in (
            ".erp-chart-text { fill: CanvasText; }",
            ".erp-class-bar { forced-color-adjust: none; background: Canvas; border: 1px solid CanvasText; }",
            ".erp-heat-cell { forced-color-adjust: none; background: Canvas; color: CanvasText; border-color: CanvasText; }",
            ".erp-heat-cell--t1 { border-width: 3px; }",
            ".erp-heat-cell--no_data { border-style: dashed; color: GrayText; }",
        ):
            self.assertIn(rule, block)
        self.assertNotIn("stroke-dasharray", block)  # the donut draws its segments with dasharray

    def test_non_administrators_are_still_denied(self):
        response = self.non_admin.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Attendance heatmap", status_code=403)


# --- Marks by subject ------------------------------------------------------------------


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
            academic_year=term.academic_year, class_grade=class_grade, subject=subject
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


class SubjectAveragesTests(MarksFixture, TestCase):
    def test_no_assessments_gives_no_reporting_term(self):
        self.assertIsNone(marks_analytics.reporting_term(TODAY))

    def test_draft_assessments_are_not_official(self):
        self.assessment({self.s1: 15}, finalize=False)
        self.assertIsNone(marks_analytics.reporting_term(TODAY))

    def test_reporting_term_is_the_term_with_finalized_results(self):
        self.assessment({self.s1: 15, self.s2: 10})
        self.assertEqual(marks_analytics.reporting_term(TODAY), self.term_b)

    def subject_display(self):
        term = marks_analytics.reporting_term(TODAY)
        return [(r["label"], r["display"]) for r in analytics._subject_rows(term)] if term else []

    def test_different_maximums_are_normalised(self):
        self.assessment({self.s1: 18}, maximum="30", name="Out of 30")  # 60%
        self.assessment({self.s1: 20}, maximum="20", name="Out of 20")  # 100%
        self.assertEqual(self.subject_display(), [("Mathematics", "80%")])

    def test_an_absent_result_is_never_a_zero(self):
        self.assessment({self.s1: 16, self.s2: None})
        self.assertEqual(self.subject_display(), [("Mathematics", "80%")])  # not 40%

    def test_draft_results_do_not_leak_into_a_finalized_average(self):
        self.assessment({self.s1: 20, self.s2: 20}, name="Final one")
        self.assessment({self.s1: 0, self.s2: 0}, name="Still draft", finalize=False)
        self.assertEqual(self.subject_display(), [("Mathematics", "100%")])

    def test_the_latest_term_with_finalized_results_is_used(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        self.assertEqual(marks_analytics.reporting_term(TODAY), self.term_a)
        self.assessment({self.s1: 20}, name="New", term=self.term_b)
        self.assertEqual(marks_analytics.reporting_term(TODAY), self.term_b)
        self.assertEqual(self.subject_display(), [("Mathematics", "100%")])  # term A not mixed in

    def test_a_term_that_has_not_started_is_ignored(self):
        future = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 3", start_date=datetime.date(2026, 10, 1),
            end_date=datetime.date(2026, 12, 31), display_order=3,
        )
        self.assessment({self.s1: 20}, name="Early", term=future)
        self.assertIsNone(marks_analytics.reporting_term(TODAY))


class MarksSnapshotViewTests(MarksFixture, TestCase):
    url = reverse("core:admin-overview") + "?tab=academics"

    def test_renders_term_subject_bars(self):
        self.assessment({self.s1: 15, self.s2: 10})
        response = self.administrator.get(self.url)
        self.assertContains(response, "Marks by subject")
        self.assertContains(response, "Term 2")
        self.assertContains(response, "Mathematics")
        self.assertContains(response, "63%")
        self.assertContains(response, 'aria-label="Mathematics"')

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

    def test_marks_by_subject_lists_lowest_first_and_names_the_term(self):
        science = Subject.objects.create(name="Science")
        self.assessment({self.s1: 18, self.s2: 16}, name="Maths test")  # 90%, 80%: 85
        self.assessment({self.s1: 8, self.s2: 12}, name="Sci test", subject=science)  # 50
        rows = analytics._subject_rows(marks_analytics.reporting_term(TODAY))
        self.assertEqual(
            [(r["label"], r["display"], r["low"]) for r in rows],
            [("Science", "50%", False), ("Mathematics", "85%", False)],
        )
        response = self.administrator.get(self.url)
        self.assertContains(response, "erp-analytics-card--subjects")
        self.assertContains(response, "Marks by subject, Term 2")
        content = response.content.decode()
        self.assertLess(content.index(">Science<"), content.index(">Mathematics<"))
        self.assertContains(response, "erp-class-bar--marks")
        self.assertNotContains(response, "erp-class-bar--low")

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

    def test_no_results_shows_the_existing_empty_message(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "No finalized results yet.", count=2)  # subjects and attention
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

    def test_cards_are_tagged_for_the_desktop_grid(self):
        self.with_data()
        html = self.administrator.get(self.url, {"tab": "attendance"}).content.decode()
        for area in ("heat", "absent"):
            self.assertIn(f"erp-analytics-card--{area}", html)

    def test_heat_cells_name_their_value_on_hover(self):
        self.with_data()
        html = self.administrator.get(self.url, {"tab": "attendance"}).content.decode()
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


# --- Today donut and class rows ---------------------------------------------------------


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

    def test_donut_shows_todays_counts(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        response = self.administrator.get(self.url)
        self.assertContains(response, '<svg class="erp-donut"')
        self.assertContains(response, "Present 1")
        self.assertContains(response, "Absent 1")

    def test_no_school_day_message_replaces_the_donut(self):
        sunday = datetime.date(2026, 7, 12)
        for target in ("core.reports.business_today",):
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

    def test_class_row_shows_one_number_and_flags_low_on_the_unrounded_value(self):
        def row(percentage):
            return {"class_name": "Grade 7", "class_grade_id": 1, "percentage": percentage}

        half = analytics._class_row(row(84.5), False)
        self.assertEqual((half["display"], half["low"]), ("85%", False))
        near = analytics._class_row(row(79.6), False)
        self.assertEqual((near["display"], near["low"]), ("79.6%", True))
        self.assertTrue(analytics._class_row(row(50.0), False)["low"])

    def test_class_comparison_rows_carry_the_shared_display(self):
        self.day(datetime.date(2026, 7, 2), {self.s1: P, self.s2: A})
        row = analytics.class_comparison(DEFAULT_PERIOD)[0]
        self.assertEqual((row["percentage"], row["display"]), (50.0, "50"))

class OverviewChartLayoutTests(AnalyticsFixture, TestCase):
    """Phone order and the By class card's desktop spread, pinned honestly."""

    url = reverse("core:admin-overview")

    def css(self):
        text = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        return text.split("/* ---------- Desktop Overview grid ---------- */", 1)[1]

    def test_desktop_grid_never_reorders_cards(self):
        # AO-01: visual order must equal DOM order so keyboard and screen-reader order match the layout.
        block = self.css().split("\n}\n", 1)[0]
        self.assertNotRegex(block, r"[\s;{]order\s*:")

    def test_phone_details_summary_is_a_44px_tap_target(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-class-more > summary \{[^}]*min-height: 2\.75rem")

    def test_setup_completed_steps_summary_is_a_44px_tap_target(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-setup-done > summary \{[^}]*min-height: 2\.75rem")
        self.assertIn(".erp-setup-done > summary::-webkit-details-marker { display: none; }", css)
        self.assertIn('.erp-setup-done > summary::after { content: "\\25BE";', css)

class AbsentDayCountsTests(AnalyticsFixture, TestCase):
    def test_counts_reportable_absent_days_per_student_in_the_period(self):
        for d, statuses in (
            (1, {self.s1: A, self.s2: P}), (2, {self.s1: A, self.s2: A}), (3, {self.s1: P, self.s2: P}),
        ):
            self.day(datetime.date(2026, 7, d), statuses)
        self.day(datetime.date(2026, 7, 6), {self.s1: A, self.s2: A}, submit=False)  # draft
        self.day(datetime.date(2026, 6, 22), {self.s1: A, self.s2: A})  # before the period
        counts = analytics.absent_day_counts(DEFAULT_PERIOD)
        self.assertEqual(counts, {self.s1.student_id: 2, self.s2.student_id: 1})

    def test_one_query_whatever_the_number_of_days(self):
        for d in (1, 2, 3, 6, 7):
            self.day(datetime.date(2026, 7, d), {self.s1: A, self.s2: A})
        with self.assertNumQueries(1):
            analytics.absent_day_counts(DEFAULT_PERIOD)


class StudentsNeedingAttentionViewTests(MarksFixture, TestCase):
    url = reverse("core:admin-overview") + "?tab=academics"

    def setUp(self):
        super().setUp()
        self.science = Subject.objects.create(name="Science")

    def fail_two(self, enrollment):
        for subject in (self.maths, self.science):
            self.assessment(
                {enrollment: 2}, subject=subject, pass_mark=10, name=f"{subject.name} {enrollment.pk}"
            )

    def login_with(self, username, *codenames):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def card(self, response):
        html = response.content.decode()
        start = html.index("erp-analytics-card--attention")
        return html[start:html.index("</article>", start)]

    def test_rows_link_to_the_student_page_and_state_the_reason(self):
        self.fail_two(self.s1)
        card = self.card(self.administrator.get(self.url))
        self.assertIn("Students needing attention", card)
        self.assertIn(reverse("core:student-detail", args=[self.s1.student_id]), card)
        self.assertIn(self.s1.student.full_name, card)
        self.assertIn("Below pass in Mathematics and Science (Term 2)", card)

    def test_absences_in_the_reason_are_counted_this_month(self):
        self.fail_two(self.s1)
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: A, self.s2: P})
        self.day(datetime.date(2026, 6, 22), {self.s1: A, self.s2: P})  # last month: not counted
        card = self.card(self.administrator.get(self.url))
        self.assertIn("Below pass in Mathematics and Science (Term 2); absent 3 days (this month)", card)

    def test_attention_uses_the_same_threshold_as_frequent_absentees(self):
        self.fail_two(self.s1)
        for d in range(1, 1 + analytics.ABSENTEE_THRESHOLD_DAYS):
            self.day(datetime.date(2026, 7, d), {self.s1: A, self.s2: P})
        absentees = analytics.frequent_absentees(DEFAULT_PERIOD)
        self.assertEqual(absentees["rows"][0]["student_id"], self.s1.student_id)

    def test_empty_state_when_results_are_checked_and_nobody_qualifies(self):
        self.assessment({self.s1: 15}, pass_mark=10)
        card = self.card(self.administrator.get(self.url))
        self.assertIn("No students need attention right now.", card)

    def test_no_finalized_results_is_not_an_all_clear(self):
        card = self.card(self.administrator.get(self.url))
        self.assertIn("No finalized results yet.", card)
        self.assertNotIn("No students need attention right now.", card)

    def test_results_without_pass_marks_say_nobody_can_be_checked(self):
        self.assessment({self.s1: 2})  # finalized, but no pass mark
        card = self.card(self.administrator.get(self.url))
        self.assertIn("No pass marks are set for Term 2, so nobody can be checked yet.", card)
        self.assertNotIn("No students need attention right now.", card)

    def flag(self, count):
        for i in range(count):
            self.fail_two(self.enroll_student(f"Pupil {i:02d}", self.class_grade, self.section))

    def test_twelve_flagged_show_ten_and_the_other_two_sit_behind_show_all(self):
        self.flag(12)
        card = self.card(self.administrator.get(self.url))
        self.assertEqual(card.count("erp-attention-row"), 12)  # none is dropped
        details = card[card.index('<details class="erp-class-more erp-attention-more"'):]
        self.assertIn("<summary>Show all 12 students</summary>", details)
        self.assertEqual(details.count("erp-attention-row"), 2)
        self.assertEqual(card[:card.index("<details")].count("erp-attention-row"), 10)
        self.assertNotIn("Showing 10 of", card)
        self.assertIn("Pupil 11", details)
        self.assertNotIn("Pupil 09", details)

    def test_ten_flagged_have_no_show_all(self):
        self.flag(10)
        card = self.card(self.administrator.get(self.url))
        self.assertEqual(card.count("erp-attention-row"), 10)
        self.assertNotIn("<details", card)
        self.assertNotIn("Show all", card)

    def test_the_attention_details_adds_no_queries(self):
        self.flag(10)
        with CaptureQueriesContext(connection) as ten:
            self.administrator.get(self.url)
        self.flag_more(5)
        with CaptureQueriesContext(connection) as fifteen:
            self.administrator.get(self.url)
        self.assertEqual(len(fifteen), len(ten))

    def flag_more(self, count):
        for i in range(count):
            self.fail_two(self.enroll_student(f"Extra {i:02d}", self.class_grade, self.section))

    def test_a_fallback_term_from_an_earlier_year_names_its_year_everywhere(self):
        old_year = AcademicYear.objects.create(
            name="2025-26", start_date=datetime.date(2025, 6, 1), end_date=datetime.date(2026, 4, 30)
        )
        old_term = AcademicTerm.objects.create(
            academic_year=old_year, name="Term 3", start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 4, 1), display_order=3,
        )
        for subject in (self.maths, self.science):
            self.assessment(
                {self.s1: 2}, subject=subject, pass_mark=10, term=old_term, name=f"{subject.name} old"
            )
        # Term 2 (2026-27) is running but has no finalized results, so Term 3 of 2025-26 is the fallback.
        html = self.administrator.get(self.url).content.decode()
        self.assertEqual(html.count("Term 3, 2025-26"), 2)  # subjects title, attention reason
        self.assertIn("Marks by subject, Term 3, 2025-26", html)
        self.assertIn("Below pass in Mathematics and Science (Term 3, 2025-26)", html)

    def test_a_term_in_the_current_year_is_not_given_a_year(self):
        self.fail_two(self.s1)
        html = self.administrator.get(self.url).content.decode()
        self.assertIn("Marks by subject, Term 2<", html)
        self.assertNotIn("Term 2, 2026-2027", html)

    def test_absences_are_not_queried_when_there_is_no_reporting_term(self):
        with mock.patch.object(analytics, "absent_day_counts") as counts:
            self.administrator.get(self.url)
        counts.assert_not_called()
        self.fail_two(self.s1)
        with mock.patch.object(analytics, "absent_day_counts", return_value={}) as counts:
            self.administrator.get(self.url)
        counts.assert_called_once()

    def test_full_overview_stays_under_the_query_ceiling(self):
        # Measured: 72 queries in this fixture (8 students, 1 register, results in 2 subjects). The
        # ceiling is that plus 5, so a per-student or per-class loop fails it at once.
        enrollments = [self.s1, self.s2]
        for i in range(6):
            enrollments.append(self.enroll_student(f"Pupil {i:02d}", self.class_grade, self.section))
            self.fail_two(enrollments[-1])
        self.day(datetime.date(2026, 7, 1), {e: A if e is self.s1 else P for e in enrollments})
        with CaptureQueriesContext(connection) as ctx:
            response = self.administrator.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(ctx), 77)

    def test_a_view_school_only_viewer_never_touches_results(self):
        self.fail_two(self.s1)
        client = self.login_with("school-only-queries", "view_school")
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        touching = [q["sql"] for q in ctx if "core_studentresult" in q["sql"]]
        self.assertEqual(touching, [])

    def test_list_needs_students_results_and_attendance(self):
        """Gate 4B: the list names students and shows marks and attendance, so it needs all three."""
        self.fail_two(self.s1)
        all_three = self.login_with(
            "all-three", "view_school", "view_student", "view_studentresult", "view_attendanceentry"
        )
        self.assertContains(all_three.get(self.url), "Students needing attention")
        for name, codenames in (
            ("no-attendance", ("view_school", "view_student", "view_studentresult")),
            ("no-results", ("view_school", "view_student", "view_attendanceentry")),
            ("no-students", ("view_school", "view_studentresult", "view_attendanceentry")),
            ("students-only", ("view_school", "view_student")),
            ("results-only", ("view_school", "view_studentresult")),
            ("school-only", ("view_school",)),
        ):
            response = self.login_with(name, *codenames).get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Students needing attention")
            self.assertNotContains(response, self.s1.student.full_name)

    def test_query_count_does_not_grow_with_students(self):
        self.fail_two(self.s1)
        with CaptureQueriesContext(connection) as before:
            self.administrator.get(self.url)
        for i in range(8):
            self.fail_two(self.enroll_student(f"Pupil {i}", self.class_grade, self.section))
        with CaptureQueriesContext(connection) as after:
            self.administrator.get(self.url)
        self.assertEqual(len(after), len(before))

class OverviewNoHoleLayoutTests(AnalyticsFixture, TestCase):
    """Desktop rows must stay full whichever cards are missing; the section names what is missing."""

    url = reverse("core:admin-overview") + "?tab=academics"

    def modifiers(self, client):
        html = client.get(self.url).content.decode()
        return re.search(r'<section class="(erp-analytics[^"]*)"', html).group(1)

    def css(self):
        text = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        return text.split("/* ---------- Desktop Overview grid ---------- */", 1)[1]

    def login_with(self, username, *codenames):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_section_names_a_missing_attention_card(self):
        self.assertNotIn("erp-analytics--no-attention", self.modifiers(self.administrator))
        for name, codenames in (
            ("results-only", ("view_school", "view_studentresult")),
            ("students-only", ("view_school", "view_student")),
            ("school-only", ("view_school",)),
        ):
            self.assertIn("erp-analytics--no-attention", self.modifiers(self.login_with(name, *codenames)))

    def test_desktop_rows_four_and_five_and_the_absentee_fallback(self):
        block = self.css()
        for rule in (
            ".erp-analytics > .erp-analytics-card--attention { grid-column: span 7; align-self: start; }",
            ".erp-analytics > .erp-analytics-card--absent { grid-column: span 5; align-self: start; }",
            ".erp-analytics--no-absent > .erp-analytics-card--attention,\n  .erp-analytics--no-attention > .erp-analytics-card--absent { grid-column: span 12; }",
            ".erp-analytics > .erp-analytics-card--subjects { grid-column: span 7; }",
        ):
            self.assertIn(rule, block)

    def test_show_all_classes_summary_has_a_visible_open_and_closed_cue(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-class-more > summary::after {", css)
        self.assertIn(".erp-class-more[open] > summary::after { transform: rotate(180deg); }", css)
        self.assertRegex(css, r"\.erp-class-more > summary \{[^}]*min-height: 2\.75rem")

    def test_attention_class_name_may_wrap_so_a_long_one_cannot_overflow(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        rule = re.search(r"\.erp-attention-class \{[^}]*\}", css).group(0)
        self.assertNotIn("nowrap", rule)
        self.assertIn("overflow-wrap: anywhere", rule)

    def test_column_charts_share_a_baseline_when_a_label_wraps(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        rule = re.search(r"\.erp-cols \{[^}]*\}", css).group(0)
        self.assertIn("align-items: flex-start", rule)
        self.assertNotIn("flex-end", rule)

class OverviewQueryBudgetTests(MarksFixture, TestCase):
    """Audit 10 (AO-04): one Overview request should not ask the same question twice."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:admin-overview")
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        self.assessment({self.s1: 15, self.s2: 4}, pass_mark=8)

    def test_sidebar_badges_and_overview_cards_share_one_count(self):
        with (
            mock.patch("core.nav_badges.prepared_notification_count", return_value=2) as to_send,
            mock.patch("core.nav_badges.stale_publication_count", return_value=1) as stale,
            mock.patch("core.nav_badges.locked_username_count", return_value=0) as locked,
        ):
            response = self.administrator.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((to_send.call_count, stale.call_count, locked.call_count), (1, 1, 1))

    def test_the_current_term_is_looked_up_once(self):
        with mock.patch("core.analytics.current_term", wraps=analytics.current_term) as lookup:
            self.administrator.get(self.url)
        self.assertEqual(lookup.call_count, 1)

    def test_a_fully_populated_overview_stays_within_its_query_budget(self):
        self.administrator.get(self.url)  # warm per-process caches (content types, permissions)
        with CaptureQueriesContext(connection) as queries:
            self.administrator.get(self.url)
        # 65 when written (AO-04). If a change needs more, find the repeat before raising the cap.
        self.assertLessEqual(len(queries), 65)
