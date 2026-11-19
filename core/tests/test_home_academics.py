import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import home_academics
from core.models import (
    AcademicEnrollment,
    Assessment,
    ClassGrade,
    Section,
    Student,
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
