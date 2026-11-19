import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import home_academics
from core.models import Assessment, TermPublication
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
