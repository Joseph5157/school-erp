"""Subject scores for charts (ADR 0022): display-only, FINALIZED + MARKED results only."""

import datetime
from unittest import mock

from django.db import connection
from django.db.models import Q
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import marks_analytics
from core.models import AcademicEnrollment, AcademicTerm, Assessment, Section, Subject
from core.tests.test_admin_overview_analytics import TODAY, MarksFixture


class MarksAnalyticsFixture(MarksFixture):
    def setUp(self):
        super().setUp()
        self.science = Subject.objects.create(name="Science")

    def score_for(self, enrollment, term=None, subject="Mathematics", **kwargs):
        scores = marks_analytics.student_subject_scores(
            enrollment.student, term or self.term_b, **kwargs
        )
        return {s.subject_name: s for s in scores}.get(subject)

    def more_students(self, count, section=None):
        return [
            self.enroll_student(f"Extra {i}", self.class_grade, section or self.section)
            for i in range(count)
        ]


class ReportingTermTests(MarksAnalyticsFixture, TestCase):
    def test_reporting_term_prefers_the_running_term_with_results(self):
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assessment({self.s1: 10}, term=self.term_b)
        self.assertEqual(marks_analytics.reporting_term(TODAY), self.term_b)

    def test_reporting_term_falls_back_when_the_running_term_has_no_results(self):
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assessment({self.s1: 10}, term=self.term_b, finalize=False)
        self.assertEqual(marks_analytics.reporting_term(TODAY), self.term_a)

    def test_reporting_term_is_none_without_results(self):
        self.assertIsNone(marks_analytics.reporting_term(TODAY))

    def test_a_term_that_has_not_started_is_never_chosen(self):
        future = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 3", start_date=datetime.date(2026, 10, 1),
            end_date=datetime.date(2026, 12, 1), display_order=3,
        )
        self.assessment({self.s1: 10}, term=future)
        self.assertIsNone(marks_analytics.reporting_term(TODAY))


class SubjectScoreTests(MarksAnalyticsFixture, TestCase):
    def test_draft_assessments_are_ignored(self):
        self.assessment({self.s1: 10}, finalize=False)
        self.assertEqual(marks_analytics.student_subject_scores(self.s1.student, self.term_b), [])
        self.assertEqual(marks_analytics.subject_averages(self.term_b), [])

    def test_score_is_the_plain_average_of_test_percentages(self):
        self.assessment({self.s1: 10}, name="A", maximum="20")
        self.assessment({self.s1: 40}, name="B", maximum="50")
        self.assertEqual(self.score_for(self.s1).score, 65.0)  # not 50/70

    def test_zero_score_counts_as_a_real_zero(self):
        self.assessment({self.s1: 0})
        score = self.score_for(self.s1)
        self.assertIsNotNone(score)
        self.assertEqual(score.score, 0.0)

    def test_absent_for_every_test_leaves_the_subject_out(self):
        self.assessment({self.s1: None})
        self.assertEqual(marks_analytics.student_subject_scores(self.s1.student, self.term_b), [])

    def test_absent_test_is_skipped_not_zeroed(self):
        self.assessment({self.s1: 10}, name="Sat")
        self.assessment({self.s1: None}, name="Missed")
        self.assertEqual(self.score_for(self.s1).score, 50.0)

    def test_pass_compare_uses_only_tests_sat_with_a_pass_mark(self):
        self.assessment({self.s1: 8}, name="A", pass_mark=10)
        self.assessment({self.s1: 20}, name="B")
        self.assessment({self.s1: None}, name="C", pass_mark=20)
        score = self.score_for(self.s1)
        self.assertEqual(score.score, 70.0)
        self.assertEqual(score.pass_percent, 50.0)
        self.assertTrue(score.below_pass)

    def test_meeting_the_pass_mark_is_not_below(self):
        self.assessment({self.s1: 10}, pass_mark=10)
        score = self.score_for(self.s1)
        self.assertEqual(score.pass_percent, 50.0)
        self.assertFalse(score.below_pass)

    def test_no_pass_mark_means_no_pass_percent(self):
        self.assessment({self.s1: 2})
        score = self.score_for(self.s1)
        self.assertIsNone(score.pass_percent)
        self.assertFalse(score.below_pass)

    def test_scores_come_back_in_subject_name_order(self):
        self.assessment({self.s1: 10}, subject=self.science, name="S")
        self.assessment({self.s1: 10}, name="M")
        names = [
            s.subject_name
            for s in marks_analytics.student_subject_scores(self.s1.student, self.term_b)
        ]
        self.assertEqual(names, ["Mathematics", "Science"])

    def test_renamed_subject_groups_like_the_report_card(self):
        old = self.assessment({self.s1: 20}, name="Before")
        Assessment.objects.filter(pk=old.pk).update(subject_label="Maths (old)")
        self.assessment({self.s1: 10}, name="After")
        scores = {
            s.subject_name: s.score
            for s in marks_analytics.student_subject_scores(self.s1.student, self.term_b)
        }
        self.assertEqual(scores, {"Maths (old)": 100.0, "Mathematics": 50.0})


class SectionAverageTests(MarksAnalyticsFixture, TestCase):
    def test_section_average_hidden_under_5_students_and_shown_at_5(self):
        extras = self.more_students(3)
        self.assessment({self.s1: 20, self.s2: 10, extras[0]: 10, extras[1]: 10})
        self.assertIsNone(self.score_for(self.s1).section_average)  # 4 students
        self.assessment({extras[2]: 10}, name="Second")  # a 5th student has marks
        # percents: 100, 50, 50, 50, 50
        self.assertAlmostEqual(self.score_for(self.s1).section_average, 60.0)

    def test_section_average_uses_the_term_placement_section_after_a_move(self):
        other = Section.objects.create(class_grade=self.class_grade, name="B")
        AcademicEnrollment.objects.filter(pk=self.s1.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 7, 5)
        )
        moved = AcademicEnrollment.objects.create(
            student=self.s1.student, academic_year=self.year, class_grade=self.class_grade,
            section=other, start_date=datetime.date(2026, 7, 6),
        )
        in_b = self.more_students(4, section=other)
        in_a = self.more_students(5)
        self.assessment({moved: 20, **{e: 20 for e in in_b}}, section=other, name="B test")
        self.assessment({e: 0 for e in in_a}, section=self.section, name="A test")
        self.assertEqual(self.score_for(self.s1).section_average, 100.0)  # B, not A's zeros

    def test_scope_limits_the_score_and_the_section_average(self):
        extras = self.more_students(3)
        everyone = {self.s1: 0, self.s2: 0, **{e: 0 for e in extras}}
        low = self.assessment(everyone, name="Low")
        self.assessment({e: 20 for e in everyone}, name="High")
        scoped = self.score_for(self.s1, scope=Q(assessment=low))
        self.assertEqual(scoped.score, 0.0)
        self.assertEqual(scoped.section_average, 0.0)
        unscoped = self.score_for(self.s1)
        self.assertEqual(unscoped.score, 50.0)
        self.assertEqual(unscoped.section_average, 50.0)


class SubjectAveragesAndTermsTests(MarksAnalyticsFixture, TestCase):
    def test_subject_averages_are_lowest_first(self):
        self.assessment({self.s1: 18, self.s2: 14}, name="M")  # 80
        self.assessment({self.s1: 6, self.s2: 10}, subject=self.science, name="S")  # 40
        rows = marks_analytics.subject_averages(self.term_b)
        self.assertEqual(
            [(r["subject_name"], r["average"], r["results"]) for r in rows],
            [("Science", 40.0, 2), ("Mathematics", 80.0, 2)],
        )

    def test_marked_results_exposes_percent_and_subject_name(self):
        self.assessment({self.s1: 15, self.s2: None})
        rows = list(marks_analytics.marked_results(self.term_b))
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0].percent), 75.0)
        self.assertEqual(rows[0].subject_name, "Mathematics")

    def test_terms_with_results_are_newest_first(self):
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assessment({self.s1: 10}, term=self.term_b)
        self.assessment({self.s2: 10}, term=self.term_a, name="Other student")
        self.assertEqual(
            marks_analytics.terms_with_results(self.s1.student), [self.term_b, self.term_a]
        )
        self.assertEqual(marks_analytics.terms_with_results(self.s2.student), [self.term_a])

    def test_query_count_does_not_grow_with_students_or_subjects(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                marks_analytics.student_subject_scores(self.s1.student, self.term_b)
            return len(ctx)

        self.assessment({self.s1: 10}, name="M")
        before = count()
        extras = self.more_students(4)
        self.assessment({e: 10 for e in [self.s1, *extras]}, subject=self.science, name="S")
        self.assertEqual(count(), before)


class PlacementAndPrivacyTests(MarksAnalyticsFixture, TestCase):
    def move_to_b(self, on):
        """Move s1 from section A to a new section B, effective `on`."""
        other = Section.objects.create(class_grade=self.class_grade, name="B")
        AcademicEnrollment.objects.filter(pk=self.s1.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=on - datetime.timedelta(days=1)
        )
        moved = AcademicEnrollment.objects.create(
            student=self.s1.student, academic_year=self.year, class_grade=self.class_grade,
            section=other, start_date=on,
        )
        return other, moved

    def test_a_term_before_the_move_compares_with_the_section_of_that_term(self):
        in_a = self.more_students(4)
        self.assessment({self.s1: 20, **{e: 20 for e in in_a}}, term=self.term_a, name="A")
        other, moved = self.move_to_b(datetime.date(2026, 7, 6))
        in_b = self.more_students(5, section=other)
        self.assessment(
            {moved: 0, **{e: 0 for e in in_b}}, term=self.term_b, section=other, name="B"
        )
        # s1 is in B now, but Term 1 ended while they were in A.
        self.assertEqual(self.score_for(self.s1, term=self.term_a).section_average, 100.0)

    def test_own_score_keeps_results_from_both_enrollments(self):
        self.assessment({self.s1: 20}, name="old section")
        other, moved = self.move_to_b(datetime.date(2026, 7, 6))
        self.assessment({moved: 0}, section=other, name="new section")
        self.assertEqual(self.score_for(self.s1).score, 50.0)

    def test_five_distinct_students_are_needed_not_five_results(self):
        extra = self.more_students(1)[0]
        for name in ("First", "Second"):
            self.assessment({self.s1: 10, self.s2: 10, extra: 10}, name=name)  # 6 results
        self.assertIsNone(self.score_for(self.s1).section_average)

    def test_a_pass_mark_of_zero_is_a_real_pass_mark(self):
        self.assessment({self.s1: 0}, pass_mark=0)
        score = self.score_for(self.s1)
        self.assertEqual(score.pass_percent, 0.0)
        self.assertFalse(score.below_pass)

    def test_no_placement_in_the_term_means_no_section_average(self):
        self.assessment({self.s1: 10})
        with mock.patch.object(AcademicTerm, "enrollment_for", return_value=None):
            score = self.score_for(self.s1)
        self.assertEqual(score.score, 50.0)
        self.assertIsNone(score.section_average)
