import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import analytics, home_academics, marks_analytics
from core.models import (
    AcademicEnrollment,
    Assessment,
    ClassGrade,
    Section,
    Student,
    Subject,
    TermPublication,
)
from core.tests.test_admin_overview_analytics import TODAY, MarksFixture


class ResultsToFinishTests(MarksFixture, TestCase):
    def publish(self, enrollment, status):
        return TermPublication.objects.create(
            student=enrollment.student, term=self.term_b, placement=enrollment, version=1,
            status=status, term_label="Term 2", academic_year_label="x", class_grade_label="x",
            section_label="x", fingerprint="x", published_by=self.admin_user,
        )

    def test_no_term_started_is_none(self):
        self.assertIsNone(
            home_academics.results_to_finish(datetime.date(2026, 5, 1), publish_rows=True)
        )

    def test_work_term_is_the_running_term_even_without_finalized_marks(self):
        self.assertEqual(home_academics.work_term(TODAY), self.term_b)

    def test_fully_marked_draft_is_ready_and_partly_marked_is_in_progress(self):
        self.assessment({self.s1: 10, self.s2: 12}, name="All in", finalize=False)
        self.assessment({self.s1: 10}, name="Half", finalize=False)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["in_progress"], 1)
        self.assertEqual([x["name"] for x in r["ready"]], ["All in"])
        self.assertTrue(r["ready"][0]["url"].startswith("/"))
        self.assertIn(f"?term={self.term_b.pk}&status=DRAFT", r["in_progress_url"])

    def test_empty_roster_is_in_progress_not_ready(self):
        grade, section, enrollment = self.second_class()
        enrollment.start_date = datetime.date(2026, 12, 1)
        enrollment.save(update_fields=["start_date"])
        self.assessment({}, class_grade=grade, section=section, finalize=False)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["in_progress"], r["ready"]), (1, []))

    def test_future_drafts_and_finalized_assessments_are_not_counted(self):
        future = self.assessment({self.s1: 10}, name="Future", finalize=False)
        Assessment.objects.filter(pk=future.pk).update(assessment_date=datetime.date(2026, 8, 1))
        self.assessment({self.s1: 10, self.s2: 10}, name="Done")
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["in_progress"], r["ready"]), (0, []))

    def test_finalized_results_without_publication_are_unpublished_by_section(self):
        self.assessment({self.s1: 10, self.s2: None})
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 2)
        row = r["unpublished_sections"][0]
        self.assertEqual((row["class_name"], row["students"]), ("Grade 1", 2))
        self.assertIn(f"?section={self.section.pk}", row["url"])

    def test_published_and_stale_students_are_not_unpublished(self):
        self.assessment({self.s1: 10, self.s2: 12})
        self.publish(self.s1, "PUBLISHED")
        self.publish(self.s2, "STALE")
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["unpublished_students"], r["unpublished_sections"]), (0, []))

    def test_publish_rows_false_keeps_counts_but_no_rows(self):
        self.assessment({self.s1: 10})
        r = home_academics.results_to_finish(TODAY, publish_rows=False)
        self.assertEqual((r["unpublished_students"], r["unpublished_sections"]), (1, []))

    def test_query_count_does_not_grow_with_assessments(self):
        self.assessment({self.s1: 10, self.s2: 10}, name="One", finalize=False)
        self.assessment({self.s1: 10}, name="Fin")  # an unpublished section exists in both runs
        with CaptureQueriesContext(connection) as first:
            home_academics.results_to_finish(TODAY, publish_rows=True)
        grade, section, enrollment = self.second_class()
        for i in range(4):
            self.assessment(
                {enrollment: 5}, name=f"G2 {i}", class_grade=grade, section=section,
                finalize=bool(i % 2),
            )
        with CaptureQueriesContext(connection) as second:
            home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(len(first), len(second))

    def test_non_active_student_is_not_unpublished(self):
        self.assessment({self.s1: 10, self.s2: 12})
        Student.objects.filter(pk=self.s2.student_id).update(status=Student.Status.INACTIVE)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 1)
        self.assertEqual(r["unpublished_sections"][0]["students"], 1)

    def test_enrollment_ended_before_the_date_does_not_block_ready(self):
        self.assessment({self.s1: 10, self.s2: 12}, name="Marked", finalize=False)
        late = self.enroll_student("Left Early", self.class_grade, self.section)
        AcademicEnrollment.objects.filter(pk=late.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 6, 15)
        )
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(([x["name"] for x in r["ready"]], r["in_progress"]), (["Marked"], 0))

    def test_enrollment_starting_after_the_date_does_not_block_ready(self):
        self.assessment({self.s1: 10, self.s2: 12}, name="Marked", finalize=False)
        later = self.enroll_student("Joins Later", self.class_grade, self.section)
        AcademicEnrollment.objects.filter(pk=later.pk).update(start_date=datetime.date(2026, 8, 1))
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(([x["name"] for x in r["ready"]], r["in_progress"]), (["Marked"], 0))

    def test_enrollment_effective_on_the_date_without_a_result_blocks_ready(self):
        self.assessment({self.s1: 10, self.s2: 12}, name="Marked", finalize=False)
        self.enroll_student("Unmarked", self.class_grade, self.section)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["ready"], r["in_progress"]), ([], 1))

    def test_student_with_results_in_two_sections_is_counted_once(self):
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        AcademicEnrollment.objects.filter(pk=self.s1.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 6, 30)
        )
        moved = AcademicEnrollment.objects.create(
            student=self.s1.student, academic_year=self.year, class_grade=self.class_grade,
            section=section_b, start_date=datetime.date(2026, 7, 1),
        )
        self.assessment({self.s1: 10}, name="Before")
        self.assessment({moved: 12}, name="After", section=section_b)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 1)
        self.assertEqual(sum(row["students"] for row in r["unpublished_sections"]), 1)

    def test_student_is_counted_under_their_latest_placement(self):
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")  # higher pk than A
        AcademicEnrollment.objects.filter(pk=self.s1.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 7, 5)
        )
        moved = AcademicEnrollment.objects.create(
            student=self.s1.student, academic_year=self.year, class_grade=self.class_grade,
            section=section_b, start_date=datetime.date(2026, 7, 6),
        )
        self.assessment({self.s1: 10}, name="In A")
        self.assessment({moved: 12}, name="In B", section=section_b)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 1)
        rows = r["unpublished_sections"]
        self.assertEqual([(x["section_name"], x["students"]) for x in rows], [("B", 1)])
        self.assertIn(f"?section={section_b.pk}", rows[0]["url"])

    def test_previous_term_unpublished_still_shows_with_its_own_term(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 1)
        row = r["unpublished_sections"][0]
        self.assertEqual(row["term_name"], "Term 1")
        self.assertTrue(row["url"].startswith(reverse("core:term-publication", args=[self.term_a.pk])))
        self.assertIn(f"?section={self.section.pk}", row["url"])

    def test_work_term_rows_come_before_previous_term_rows(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        self.assessment({self.s2: 10}, name="New")
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 2)
        self.assertEqual([x["term_name"] for x in r["unpublished_sections"]], ["Term 2", "Term 1"])

    def test_previous_term_publication_is_checked_against_that_term(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        TermPublication.objects.create(
            student=self.s1.student, term=self.term_a, placement=self.s1, version=1,
            status="PUBLISHED", term_label="Term 1", academic_year_label="x", class_grade_label="x",
            section_label="x", fingerprint="x", published_by=self.admin_user,
        )
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["unpublished_students"], r["unpublished_sections"]), (0, []))

    def test_previous_term_publish_rows_false_keeps_counts_but_no_rows(self):
        self.assessment({self.s1: 10}, name="Old", term=self.term_a)
        r = home_academics.results_to_finish(TODAY, publish_rows=False)
        self.assertEqual((r["unpublished_students"], r["unpublished_sections"]), (1, []))

    def test_previous_term_drafts_are_not_counted(self):
        self.assessment({self.s1: 10}, name="Old draft", term=self.term_a, finalize=False)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual((r["in_progress"], r["ready"]), (0, []))

    def test_superseded_and_withdrawn_publications_do_not_count_as_published(self):
        self.assessment({self.s1: 10, self.s2: 12})
        self.publish(self.s1, "SUPERSEDED")
        self.publish(self.s2, "WITHDRAWN")
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["unpublished_students"], 2)

    def test_ready_is_oldest_date_first(self):
        zed = self.assessment({self.s1: 10, self.s2: 12}, name="Zed", finalize=False)
        alpha = self.assessment({self.s1: 10, self.s2: 12}, name="Alpha", finalize=False)
        Assessment.objects.filter(pk=zed.pk).update(assessment_date=datetime.date(2026, 7, 2))
        Assessment.objects.filter(pk=alpha.pk).update(assessment_date=datetime.date(2026, 7, 10))
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual([x["name"] for x in r["ready"]], ["Zed", "Alpha"])

    def test_unpublished_sections_follow_class_order_then_section_name(self):
        grade2, section2, enrollment2 = self.second_class()
        ClassGrade.objects.filter(pk=self.class_grade.pk).update(display_order=5)
        ClassGrade.objects.filter(pk=grade2.pk).update(display_order=1)
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        enrollment_b = self.enroll_student("In B", self.class_grade, section_b)
        self.assessment({self.s1: 10}, name="G1A")
        self.assessment({enrollment_b: 10}, name="G1B", section=section_b)
        self.assessment({enrollment2: 10}, name="G2A", class_grade=grade2, section=section2)
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(
            [(x["class_name"], x["section_name"]) for x in r["unpublished_sections"]],
            [("Grade 2", "A"), ("Grade 1", "A"), ("Grade 1", "B")],
        )


class ClassMarksTests(MarksFixture, TestCase):
    def test_previous_term_is_the_last_earlier_term_with_finalized_results(self):
        self.assertIsNone(marks_analytics.previous_term(self.term_b))
        self.assessment({self.s1: 10}, term=self.term_a, name="Draft only", finalize=False)
        self.assertIsNone(marks_analytics.previous_term(self.term_b))
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assertEqual(marks_analytics.previous_term(self.term_b), self.term_a)
        self.assertIsNone(marks_analytics.previous_term(self.term_a))

    def test_pass_rate_counts_ties_as_passes_and_ignores_absent(self):
        self.assessment({self.s1: 10, self.s2: 9}, pass_mark=10)  # 1 of 2 pass
        self.assessment({self.s1: None}, name="Absent", pass_mark=10)  # not judged
        row = home_academics.class_marks(self.term_b)[0]
        self.assertEqual((row["class_name"], row["pass_rate"]), ("Grade 1", 50.0))

    def test_no_pass_mark_is_none_not_zero(self):
        self.assessment({self.s1: 10})
        self.assertIsNone(home_academics.class_marks(self.term_b)[0]["pass_rate"])

    def test_grade_spread_uses_the_frozen_snapshot(self):
        a = self.assessment({self.s1: 18, self.s2: 11})  # 90% A, 55% B
        Assessment.objects.filter(pk=a.pk).update(
            grading_snapshot={"scale": "S", "bands": [["80", "A"], ["50", "B"], ["0", "C"]]}
        )
        row = home_academics.class_marks(self.term_b)[0]
        self.assertEqual(row["grades"], [{"label": "A", "count": 1}, {"label": "B", "count": 1}])
        self.assertEqual(row["grades_display"], "A 1 · B 1")

    def test_no_snapshot_means_no_grades(self):
        self.assessment({self.s1: 18})
        row = home_academics.class_marks(self.term_b)[0]
        self.assertEqual((row["grades"], row["grades_display"]), ([], ""))

    def test_average_and_class_order(self):
        grade2, section2, enrollment2 = self.second_class()
        ClassGrade.objects.filter(pk=self.class_grade.pk).update(display_order=5)
        ClassGrade.objects.filter(pk=grade2.pk).update(display_order=1)
        self.assessment({self.s1: 10, self.s2: 15})  # 50, 75 -> 62.5
        self.assessment({enrollment2: 20}, name="G2", class_grade=grade2, section=section2)
        rows = home_academics.class_marks(self.term_b)
        self.assertEqual(
            [(r["class_name"], r["average"]) for r in rows], [("Grade 2", 100.0), ("Grade 1", 62.5)]
        )

    def test_two_queries(self):
        self.assessment({self.s1: 10, self.s2: 15}, pass_mark=10)
        with CaptureQueriesContext(connection) as q:
            home_academics.class_marks(self.term_b)
        self.assertLessEqual(len(q), 2)

    def test_extremes_hidden_under_four_classes_and_split_without_overlap(self):
        def rows(*avgs):
            return [
                {"class_grade_id": 1, "class_name": f"C{i}", "average": a}
                for i, a in enumerate(avgs)
            ]

        self.assertIsNone(home_academics.class_mark_extremes(rows(70, 80, 90), with_links=False))
        # unsorted input; names order ties
        e = home_academics.class_mark_extremes(rows(95, 70, 90, 80, 85), with_links=False)
        self.assertEqual([r["value"] for r in e["best"]], [95, 90])
        self.assertEqual([r["value"] for r in e["worst"]], [70, 80])
        self.assertEqual(e["best"][0]["display"], "95%")
        self.assertIsNone(e["best"][0]["url"])
        linked = home_academics.class_mark_extremes(rows(60, 70, 80, 90), with_links=True)
        self.assertTrue(linked["best"][0]["url"].startswith("/"))


class SubjectChangeTests(MarksFixture, TestCase):
    def test_subjects_change_against_previous_term(self):
        self.assessment({self.s1: 10}, term=self.term_a)  # 50%
        self.assessment({self.s1: 16})  # 80%
        row = home_academics.subject_changes(self.term_b, self.term_a)[0]
        self.assertEqual((row["display"], row["change"], row["note"]), ("80%", 30.0, "Up 30 points"))

    def test_subject_new_this_term_has_no_change(self):
        science = Subject.objects.create(name="Science")
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assessment({self.s1: 8}, name="Sci", subject=science)
        rows = {r["label"]: r for r in home_academics.subject_changes(self.term_b, self.term_a)}
        self.assertEqual((rows["Science"]["change"], rows["Science"]["note"]), (None, ""))
        self.assertEqual(rows["Science"]["low"], False)

    def test_without_previous_term_and_lowest_first_ties_by_name(self):
        zed = Subject.objects.create(name="Zed")
        art = Subject.objects.create(name="Art")
        self.assessment({self.s1: 10}, name="Z", subject=zed)
        self.assessment({self.s1: 10}, name="A", subject=art)
        self.assessment({self.s1: 20}, name="M")
        rows = home_academics.subject_changes(self.term_b, None)
        self.assertEqual([r["label"] for r in rows], ["Art", "Zed", "Mathematics"])
        self.assertEqual([(r["change"], r["note"]) for r in rows], [(None, "")] * 3)

    def test_unchanged(self):
        self.assessment({self.s1: 16}, term=self.term_a)  # 80
        self.assessment({self.s1: 16})
        self.assertEqual(home_academics.subject_changes(self.term_b, self.term_a)[0]["note"], "No change")


class ChangeWordsTests(TestCase):
    def test_change_words(self):
        self.assertEqual(home_academics.change_words(3.0), "Up 3 points")
        self.assertEqual(home_academics.change_words(-1.5), "Down 1.5 points")
        self.assertEqual(home_academics.change_words(1.0), "Up 1 point")
        self.assertEqual(home_academics.change_words(-1.0), "Down 1 point")
        self.assertEqual(home_academics.change_words(0.0), "No change")
        self.assertEqual(home_academics.change_words(0.04), "No change")

    def test_points_text(self):
        self.assertEqual(marks_analytics.points_text(3.0), "3 points")
        self.assertEqual(marks_analytics.points_text(-1.5), "1.5 points")
        self.assertEqual(marks_analytics.points_text(-1.0), "1 point")
        self.assertEqual(marks_analytics.points_text(0.96), "1 point")


class SplitExtremesTests(TestCase):
    def test_split(self):
        self.assertIsNone(analytics.split_extremes([1, 2, 3]))
        self.assertEqual(analytics.split_extremes([1, 2, 3, 4, 5]), ([5, 4], [1, 2]))
        self.assertEqual(
            analytics.split_extremes([1, 2, 3, 4, 5, 6, 7]), ([7, 6, 5], [1, 2, 3])
        )


class TwoTermFixture(MarksFixture):
    def two_terms(self, a_scores, b_scores):
        """Two assessments per term per student: `{enrollment: (score, score)}` out of 20."""
        for term, scores in ((self.term_a, a_scores), (self.term_b, b_scores)):
            for i in range(2):
                self.assessment({e: s[i] for e, s in scores.items()}, term=term, name=f"T{i}")


class AverageChangeTests(TwoTermFixture, TestCase):
    def test_change_needs_two_marked_results_in_each_term(self):
        self.two_terms(
            {self.s1: (10, 10), self.s2: (10, 10)}, {self.s1: (16, 16), self.s2: (16, None)}
        )
        changes = marks_analytics.student_average_changes(self.term_b, self.term_a)
        self.assertEqual(changes[self.s1.student_id], {"this": 80.0, "last": 50.0, "change": 30.0})
        self.assertNotIn(self.s2.student_id, changes)  # one marked result in term_b

    def test_no_previous_term_gives_no_changes(self):
        self.assertEqual(marks_analytics.student_average_changes(self.term_b, None), {})

    def test_draft_results_do_not_count(self):
        self.two_terms({self.s1: (10, 10)}, {self.s1: (16, 16)})
        self.assessment({self.s1: 0}, term=self.term_b, name="Draft", finalize=False)
        changes = marks_analytics.student_average_changes(self.term_b, self.term_a)
        self.assertEqual(changes[self.s1.student_id]["this"], 80.0)

    def test_two_queries(self):
        self.two_terms({self.s1: (10, 10)}, {self.s1: (16, 16)})
        with CaptureQueriesContext(connection) as ctx:
            marks_analytics.student_average_changes(self.term_b, self.term_a)
        self.assertEqual(len(ctx), 2)


class AtRiskTests(TwoTermFixture, TestCase):
    def test_falling_student_is_at_risk_without_any_below_pass_subject(self):
        self.assessment({self.s1: 15})  # term_b has results, no pass mark
        result = marks_analytics.students_needing_attention(
            self.term_b, {}, falling={self.s1.student_id: -12.0}, falling_label="Term 1",
            period_label="this month",
        )
        self.assertEqual(result["rows"][0]["reason"], "Average down 12 points since Term 1")
        self.assertEqual(result["total"], 1)

    def test_falling_is_added_to_a_below_pass_reason(self):
        science = Subject.objects.create(name="Science")
        self.assessment({self.s1: 5}, pass_mark=10)
        self.assessment({self.s1: 5}, pass_mark=10, subject=science, name="Sci")
        result = marks_analytics.students_needing_attention(
            self.term_b, {}, falling={self.s1.student_id: -12.0}, falling_label="Term 1",
            period_label="this month",
        )
        self.assertEqual(
            result["rows"][0]["reason"],
            "Below pass in Mathematics and Science (Term 2); average down 12 points since Term 1",
        )

    def test_falling_with_one_below_pass_subject_and_absence_joins_all_parts(self):
        self.assessment({self.s1: 5}, pass_mark=10)
        result = marks_analytics.students_needing_attention(
            self.term_b, {self.s1.student_id: 3}, falling={self.s1.student_id: -1.0},
            falling_label="Term 1", period_label="this month",
        )
        self.assertEqual(
            result["rows"][0]["reason"],
            "Below pass in Mathematics (Term 2); absent 3 days (this month); "
            "average down 1 point since Term 1",
        )

    def test_absence_adds_no_absent_part_for_a_falling_only_student(self):
        self.assessment({self.s1: 15})
        result = marks_analytics.students_needing_attention(
            self.term_b, {self.s1.student_id: 5}, falling={self.s1.student_id: -10.0},
            falling_label="Term 1", period_label="this month",
        )
        self.assertEqual(result["rows"][0]["reason"], "Average down 10 points since Term 1")

    def test_defaults_are_unchanged(self):
        self.assessment({self.s1: 5, self.s2: 15}, pass_mark=10)
        result = marks_analytics.students_needing_attention(
            self.term_b, {self.s1.student_id: 3}, period_label="this month"
        )
        self.assertEqual(
            [r["reason"] for r in result["rows"]],
            ["Below pass in Mathematics (Term 2); absent 3 days (this month)"],
        )

    def test_inactive_falling_student_is_not_listed(self):
        self.assessment({self.s1: 15, self.s2: 15})
        Student.objects.filter(pk=self.s2.student_id).update(status=Student.Status.INACTIVE)
        result = marks_analytics.students_needing_attention(
            self.term_b, {},
            falling={self.s1.student_id: -15.0, self.s2.student_id: -20.0},
            falling_label="Term 1", period_label="this month",
        )
        self.assertEqual([r["student_id"] for r in result["rows"]], [self.s1.student_id])

    def test_falling_students_keep_class_then_name_order(self):
        grade, section, ravi = self.second_class()
        self.assessment({self.s1: 15, self.s2: 15})
        self.assessment({ravi: 15}, class_grade=grade, section=section, name="G2")
        result = marks_analytics.students_needing_attention(
            self.term_b, {},
            falling={ravi.student_id: -30.0, self.s1.student_id: -10.0, self.s2.student_id: -11.0},
            falling_label="Term 1", period_label="this month",
        )
        self.assertEqual(
            [r["class_name"] for r in result["rows"]], ["Grade 1", "Grade 1", "Grade 2"]
        )
        names = [r["name"] for r in result["rows"][:2]]
        self.assertEqual(names, sorted(names, key=str.lower))


class ImproverTests(TwoTermFixture, TestCase):
    def test_top_improvers_largest_rise_first_and_only_rises(self):
        changes = {
            self.s1.student_id: {"this": 73.0, "last": 61.0, "change": 12.0},
            self.s2.student_id: {"this": 50.0, "last": 55.0, "change": -5.0},
        }
        rows = home_academics.top_improvers(changes)
        self.assertEqual([r["student_id"] for r in rows], [self.s1.student_id])
        self.assertEqual(rows[0]["display"], "Up 12 points (61% \u2192 73%)")
        self.assertEqual(rows[0]["class_name"], "Grade 1")

    def test_zero_change_is_not_an_improver(self):
        changes = {self.s1.student_id: {"this": 50.0, "last": 50.0, "change": 0.0}}
        self.assertEqual(home_academics.top_improvers(changes), [])

    def test_order_is_by_rise_then_name_not_creation(self):
        zed = self.enroll_student("Zed Zane", self.class_grade, self.section)
        amy = self.enroll_student("Amy Ames", self.class_grade, self.section)
        changes = {
            self.s1.student_id: {"this": 60.0, "last": 50.0, "change": 10.0},
            zed.student_id: {"this": 70.0, "last": 50.0, "change": 20.0},
            amy.student_id: {"this": 70.0, "last": 50.0, "change": 20.0},
        }
        rows = home_academics.top_improvers(changes)
        self.assertEqual(
            [r["student_id"] for r in rows], [amy.student_id, zed.student_id, self.s1.student_id]
        )

    def test_improvers_are_capped_at_five_and_skip_inactive_students(self):
        changes = {}
        for i in range(7):
            e = self.enroll_student(f"Student {i}", self.class_grade, self.section)
            changes[e.student_id] = {"this": 60.0 + i, "last": 50.0, "change": 10.0 + i}
        inactive = self.enroll_student("Gone Away", self.class_grade, self.section)
        Student.objects.filter(pk=inactive.student_id).update(status=Student.Status.INACTIVE)
        changes[inactive.student_id] = {"this": 99.0, "last": 50.0, "change": 49.0}
        rows = home_academics.top_improvers(changes)
        self.assertEqual(len(rows), 5)
        self.assertNotIn(inactive.student_id, [r["student_id"] for r in rows])
        self.assertEqual([r["change"] for r in rows], [16.0, 15.0, 14.0, 13.0, 12.0])

    def test_one_query(self):
        changes = {self.s1.student_id: {"this": 60.0, "last": 50.0, "change": 10.0}}
        with CaptureQueriesContext(connection) as ctx:
            home_academics.top_improvers(changes)
        self.assertEqual(len(ctx), 1)
