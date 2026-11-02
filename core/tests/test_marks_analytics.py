"""Subject scores for charts (ADR 0022): display-only, FINALIZED + MARKED results only."""

import datetime
from unittest import mock

from django.db import connection
from django.db.models import Q
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import marks_analytics
from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    Assessment,
    ClassGrade,
    Section,
    Student,
    Subject,
)
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


class StudentsNeedingAttentionTests(MarksAnalyticsFixture, TestCase):
    """The Overview list: 2+ subjects below pass, or 1 below pass and frequent absence."""

    def setUp(self):
        super().setUp()
        self.english = Subject.objects.create(name="English")

    def below(self, enrollment, *subjects, term=None):
        """A failing test (score 2 of 20, pass 10) in each named subject."""
        for subject in subjects:
            self.assessment(
                {enrollment: 2}, name=f"{subject.name} {enrollment.pk} {term and term.pk}", subject=subject,
                pass_mark=10,
                term=term,
            )

    def attention(self, absent=None, **kwargs):
        return marks_analytics.students_needing_attention(
            self.term_b, absent or {}, period_label="last 14 days", **kwargs
        )

    def test_two_subjects_below_pass_is_listed(self):
        self.below(self.s1, self.maths, self.science)
        result = self.attention()
        self.assertEqual(result["total"], 1)
        row = result["rows"][0]
        self.assertEqual(row["student_id"], self.s1.student_id)
        self.assertEqual(row["name"], self.s1.student.full_name)
        self.assertEqual(row["class_name"], self.class_grade.name)
        self.assertEqual(row["below_subjects"], ["Mathematics", "Science"])
        self.assertIsNone(row["absent_days"])

    def test_one_subject_below_pass_alone_is_not_listed(self):
        self.below(self.s1, self.maths)
        result = self.attention()
        self.assertEqual((result["rows"], result["total"]), ([], 0))
        self.assertTrue(result["has_pass_marks"])

    def test_one_subject_plus_frequent_absence_is_listed(self):
        self.below(self.s1, self.maths)
        result = self.attention({self.s1.student_id: 3})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["absent_days"], 3)

    def test_one_subject_with_too_few_absences_is_not_listed(self):
        self.below(self.s1, self.maths)
        self.assertEqual(self.attention({self.s1.student_id: 2})["total"], 0)
        self.assertEqual(self.attention({self.s1.student_id: 2}, threshold=2)["total"], 1)

    def test_frequent_absence_alone_is_not_listed(self):
        self.assessment({self.s1: 15}, pass_mark=10)
        self.assertEqual(self.attention({self.s1.student_id: 9})["total"], 0)

    def test_subject_with_no_pass_mark_never_counts(self):
        self.below(self.s1, self.maths)
        self.assessment({self.s1: 2}, name="No mark", subject=self.science)  # no pass mark
        self.assessment({self.s1: 2}, name="No mark 2", subject=self.english)
        self.assertEqual(self.attention()["total"], 0)

    def test_a_score_exactly_on_the_pass_mark_is_not_below(self):
        self.assessment({self.s1: 10}, subject=self.maths, pass_mark=10, name="M")
        self.assessment({self.s1: 10}, subject=self.science, pass_mark=10, name="S")
        # 6 of 18 against a pass mark of 6: the same 33.33...% on both sides.
        self.assessment({self.s1: 6}, subject=self.english, maximum="18", pass_mark=6, name="E")
        self.assertEqual(self.attention()["total"], 0)

    def test_same_rule_as_the_student_page(self):
        # Fails Maths on the test with a pass mark; the high test without one must not change that.
        self.assessment({self.s1: 2}, subject=self.maths, pass_mark=10, name="Fail")
        self.assessment({self.s1: 20}, subject=self.maths, name="Great but no pass mark")
        self.below(self.s1, self.science)
        listed = marks_analytics.students_needing_attention(
            self.term_b, {}, period_label="last 14 days"
        )["rows"][0]
        page = {
            s.subject_name
            for s in marks_analytics.student_subject_scores(self.s1.student, self.term_b)
            if s.below_pass
        }
        self.assertEqual(set(listed["below_subjects"]), page)

    def test_a_test_the_student_was_absent_for_does_not_move_the_pass_mark(self):
        # Maths: 12/20 on a test with pass 10 (60% vs 50%); absent from a test with pass 16.
        # Against both pass marks it would read 60% vs 65%, below pass. It must not.
        self.assessment({self.s1: 12}, subject=self.maths, pass_mark=10, name="Sat")
        self.assessment({self.s1: None}, subject=self.maths, pass_mark=16, name="Missed")
        self.below(self.s1, self.science)
        self.assertEqual(self.attention()["total"], 0)  # Science alone is not enough
        maths = {s.subject_name: s for s in marks_analytics.student_subject_scores(
            self.s1.student, self.term_b)}["Mathematics"]
        self.assertFalse(maths.below_pass)

    def test_a_tie_across_tests_with_mixed_maximums_is_not_below(self):
        # Test 1: 1 of 3 against a pass mark of 0 of 3. Test 2: 3 of 9 against 6 of 9.
        # Averaged, the score is one third and so is the pass mark, a real tie. The database
        # returns 33.3333333333333333 for one and 33.33333333333333335 for the other.
        self.assessment({self.s1: 1}, subject=self.maths, maximum="3", pass_mark=0, name="T1")
        self.assessment({self.s1: 3}, subject=self.maths, maximum="9", pass_mark=6, name="T2")
        self.below(self.s1, self.science)
        self.assertEqual(self.attention()["total"], 0)  # Maths is a tie, so only Science is below
        maths = {s.subject_name: s for s in marks_analytics.student_subject_scores(
            self.s1.student, self.term_b)}["Mathematics"]
        self.assertFalse(maths.below_pass)

    def test_only_tests_the_student_was_marked_on_count(self):
        self.assessment({self.s1: None, self.s2: 2}, subject=self.maths, pass_mark=10, name="A")
        self.assessment({self.s1: None, self.s2: 2}, subject=self.science, pass_mark=10, name="B")
        rows = self.attention()["rows"]
        self.assertEqual([r["student_id"] for r in rows], [self.s2.student_id])

    def test_draft_assessments_and_other_terms_do_not_count(self):
        self.assessment({self.s1: 2}, subject=self.maths, pass_mark=10, finalize=False, name="D1")
        self.assessment({self.s1: 2}, subject=self.science, pass_mark=10, finalize=False, name="D2")
        self.below(self.s1, self.maths, self.science, term=self.term_a)
        self.assertEqual(self.attention()["total"], 0)

    def test_inactive_student_is_left_out(self):
        self.below(self.s1, self.maths, self.science)
        Student.objects.filter(pk=self.s1.student_id).update(status=Student.Status.INACTIVE)
        self.assertEqual(self.attention()["total"], 0)

    def test_student_without_an_active_enrollment_is_left_out(self):
        self.below(self.s1, self.maths, self.science)
        AcademicEnrollment.objects.filter(pk=self.s1.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 6, 30)
        )
        self.assertEqual(self.attention()["total"], 0)

    def test_rows_order_by_class_then_name_not_by_performance(self):
        grade10 = ClassGrade.objects.create(name="Grade 10")
        grade2 = ClassGrade.objects.create(name="Grade 2")
        sec10 = Section.objects.create(class_grade=grade10, name="A")
        sec2 = Section.objects.create(class_grade=grade2, name="A")
        zed = self.enroll_student("Zed Best", grade2, sec2)
        amy = self.enroll_student("Amy Worst", grade10, sec10)
        for enrollment, grade, section, score in (
            (zed, grade2, sec2, 9),
            (amy, grade10, sec10, 0),
            (self.s2, self.class_grade, self.section, 5),
        ):
            for subject in (self.maths, self.science):
                self.assessment(
                    {enrollment: score}, subject=subject, class_grade=grade, section=section,
                    pass_mark=10, name=f"{subject.name} {enrollment.pk}",
                )
        names = [r["name"] for r in self.attention()["rows"]]
        # Class order is natural (the fixture's class, then Grade 2, then Grade 10).
        self.assertEqual(names, ["Meena Das", "Zed Best", "Amy Worst"])

    def test_limit_keeps_the_true_total(self):
        for enrollment in (self.s1, self.s2):
            self.below(enrollment, self.maths, self.science)
        result = self.attention(limit=1)
        self.assertEqual((len(result["rows"]), result["total"]), (1, 2))

    def test_reason_names_term_and_period(self):
        self.below(self.s1, self.english, self.maths)
        row = marks_analytics.students_needing_attention(
            self.term_b, {self.s1.student_id: 4}, period_label="last 14 days"
        )["rows"][0]
        self.assertEqual(
            row["reason"],
            "Below pass in English and Mathematics (Term 2); absent 4 days (last 14 days)",
        )

    def test_reason_wording_for_one_day_three_subjects_and_no_absence(self):
        self.below(self.s1, self.english, self.maths, self.science)

        def reason(days):
            absent = {self.s1.student_id: days} if days else {}
            return marks_analytics.students_needing_attention(
                self.term_b, absent, period_label="this month"
            )["rows"][0]["reason"]

        self.assertEqual(
            reason(1),
            "Below pass in English, Mathematics and Science (Term 2); absent 1 day (this month)",
        )
        self.assertEqual(reason(0), "Below pass in English, Mathematics and Science (Term 2)")

    def test_query_count_does_not_grow_with_students(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                marks_analytics.students_needing_attention(
                    self.term_b, {}, period_label="last 14 days"
                )
            return len(ctx)

        self.below(self.s1, self.maths, self.science)
        before = count()
        for extra in self.more_students(10):
            self.below(extra, self.maths, self.science)
        self.assertEqual(self.attention()["total"], 11)
        self.assertEqual(count(), before)

    def test_has_pass_marks_says_whether_anyone_could_be_checked(self):
        self.assessment({self.s1: 2}, subject=self.maths, name="No pass mark")
        self.assertFalse(self.attention()["has_pass_marks"])
        self.assessment({self.s1: 2}, subject=self.science, pass_mark=10, name="With pass mark")
        self.assertTrue(self.attention()["has_pass_marks"])
        # A draft test with a pass mark does not count.
        self.assessment({self.s1: 2}, subject=self.maths, pass_mark=10, term=self.term_a,
                        finalize=False, name="Draft")
        self.assertFalse(
            marks_analytics.students_needing_attention(
                self.term_a, {}, period_label="last 14 days"
            )["has_pass_marks"]
        )

    def test_no_term_means_nothing_to_check(self):
        result = marks_analytics.students_needing_attention(None, {}, period_label="x")
        self.assertEqual(result, {"rows": [], "total": 0, "has_pass_marks": False})

    def test_period_label_is_required(self):
        with self.assertRaises(TypeError):
            marks_analytics.students_needing_attention(self.term_b, {})
