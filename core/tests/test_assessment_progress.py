"""Option A3 (admin home path): one source for "marking in progress" and "ready to finalize".

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 6.2 step 5 and
section 9 (PR A3, branch 2). The Academics tab's "Results to finish" count and the assessment
list it links to come from `core.assessment_progress`, each with one business date per request,
so the count and the list cannot drift apart.

All data here is synthetic and local.
"""

import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import assessment_progress, home_academics
from core.models import AcademicEnrollment, Assessment
from core.tests.test_admin_overview_analytics import TODAY, MarksFixture

TOMORROW = TODAY + datetime.timedelta(days=1)


class ProgressFixture(MarksFixture):
    """Work term 2 (from 1 Jul) holds one finalized assessment, one future draft, one due draft
    with no roster, one due draft with an unmarked enrollment, and one due draft that is ready."""

    def setUp(self):
        super().setUp()
        self.done = self.assessment({self.s1: 10, self.s2: 12}, name="Done")
        self.future = self.assessment({}, name="Future", finalize=False)
        Assessment.objects.filter(pk=self.future.pk).update(
            assessment_date=datetime.date(2026, 8, 1))
        grade, section, enrollment = self.second_class()
        AcademicEnrollment.objects.filter(pk=enrollment.pk).update(
            start_date=datetime.date(2026, 12, 1))
        self.no_roster = self.assessment({}, name="No roster", class_grade=grade,
                                         section=section, finalize=False)
        self.unmarked = self.assessment({self.s1: 10}, name="Unmarked", finalize=False)
        self.ready = self.assessment({self.s1: 10, self.s2: None}, name="Ready", finalize=False)
        self.list_url = reverse("core:academic-year-assessments", args=[self.year.pk])

    def listed(self, url_or_params):
        if isinstance(url_or_params, str):
            response = self.administrator.get(url_or_params)
        else:
            response = self.administrator.get(self.list_url, url_or_params)
        self.assertEqual(response.status_code, 200)
        return response, {a.name for a in response.context["assessments"]}

    def work_term_drafts(self):
        return Assessment.objects.filter(term=self.term_b)


class CountParityTests(ProgressFixture, TestCase):
    def test_in_progress_count_equals_the_rows_at_its_link(self):
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual(r["in_progress"], 2)
        _, names = self.listed(r["in_progress_url"])
        self.assertEqual(names, {"No roster", "Unmarked"})
        self.assertEqual(len(names), r["in_progress"])

    def test_ready_to_finalize_is_listed_as_ready_and_not_at_the_in_progress_link(self):
        r = home_academics.results_to_finish(TODAY, publish_rows=True)
        self.assertEqual([row["name"] for row in r["ready"]], ["Ready"])
        _, names = self.listed(r["in_progress_url"])
        self.assertNotIn("Ready", names)

    def test_link_carries_term_draft_due_and_progress(self):
        url = home_academics.results_to_finish(TODAY, publish_rows=True)["in_progress_url"]
        self.assertTrue(url.startswith(self.list_url + "?"))
        self.assertIn(f"term={self.term_b.pk}", url)
        for part in ("status=DRAFT", "due=1", "progress=marking"):
            self.assertIn(part, url)
        _, names = self.listed(url)
        self.assertNotIn("Future", names)
        self.assertNotIn("Done", names)


class SharedRuleTests(ProgressFixture, TestCase):
    def names(self, queryset):
        return set(queryset.values_list("name", flat=True))

    def test_marking_in_progress_and_ready_to_finalize(self):
        qs = self.work_term_drafts()
        self.assertEqual(self.names(assessment_progress.marking_in_progress(qs, today=TODAY)),
                         {"No roster", "Unmarked"})
        self.assertEqual(self.names(assessment_progress.ready_to_finalize(qs, today=TODAY)),
                         {"Ready"})

    def test_absent_counts_as_marked(self):
        # "Ready" has s2 ABSENT; it is still ready.
        qs = self.work_term_drafts().filter(pk=self.ready.pk)
        self.assertTrue(assessment_progress.ready_to_finalize(qs, today=TODAY).exists())

    def test_enrollment_ended_before_the_date_is_not_on_the_roster(self):
        AcademicEnrollment.objects.filter(pk=self.s2.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=datetime.date(2026, 6, 30))
        qs = self.work_term_drafts().filter(pk=self.unmarked.pk)
        # s1 is marked and s2 left before 1 Jul, so "Unmarked" is now ready.
        self.assertTrue(assessment_progress.ready_to_finalize(qs, today=TODAY).exists())
        self.assertFalse(assessment_progress.marking_in_progress(qs, today=TODAY).exists())

    def test_enrollment_starting_after_the_date_is_not_on_the_roster(self):
        AcademicEnrollment.objects.filter(pk=self.s2.pk).update(
            start_date=datetime.date(2026, 7, 2))
        qs = self.work_term_drafts().filter(pk=self.unmarked.pk)
        self.assertTrue(assessment_progress.ready_to_finalize(qs, today=TODAY).exists())

    def test_explicit_date_decides_due(self):
        Assessment.objects.filter(pk=self.unmarked.pk).update(assessment_date=TOMORROW)
        qs = self.work_term_drafts()
        self.assertNotIn("Unmarked",
                         self.names(assessment_progress.marking_in_progress(qs, today=TODAY)))
        self.assertIn("Unmarked",
                      self.names(assessment_progress.marking_in_progress(qs, today=TOMORROW)))

    def test_today_is_required(self):
        qs = self.work_term_drafts()
        with self.assertRaises(TypeError):
            assessment_progress.marking_in_progress(qs)
        with self.assertRaises(TypeError):
            assessment_progress.ready_to_finalize(qs)

    def test_finalized_assessments_are_never_in_either_group(self):
        qs = self.work_term_drafts().filter(pk=self.done.pk)
        self.assertFalse(assessment_progress.marking_in_progress(qs, today=TODAY).exists())
        self.assertFalse(assessment_progress.ready_to_finalize(qs, today=TODAY).exists())


class ListFilterTests(ProgressFixture, TestCase):
    def test_progress_ready_lists_only_ready_drafts(self):
        _, names = self.listed({"term": self.term_b.pk, "progress": "ready"})
        self.assertEqual(names, {"Ready"})

    def test_progress_marking_alone_implies_draft_and_due(self):
        _, names = self.listed({"progress": "marking"})
        self.assertEqual(names, {"No roster", "Unmarked"})

    def test_progress_with_finalized_status_is_a_form_error_and_no_filter(self):
        response, names = self.listed({"status": "FINALIZED", "progress": "marking"})
        self.assertIn("progress", response.context["form"].errors)
        self.assertEqual(names, {"Done", "Future", "No roster", "Unmarked", "Ready"})

    def test_one_date_per_request_for_due_and_progress(self):
        Assessment.objects.filter(pk=self.unmarked.pk).update(assessment_date=TOMORROW)
        calls = []

        def today():
            calls.append(1)
            return TODAY

        with mock.patch("core.views.business_today", side_effect=today):
            _, names = self.listed({"status": "DRAFT", "due": "1", "progress": "marking"})
        self.assertEqual(names, {"No roster"})
        self.assertEqual(len(calls), 1)

    def test_filter_bar_offers_due_and_progress(self):
        response, _ = self.listed({})
        self.assertContains(response, 'name="due"')
        self.assertContains(response, 'name="progress"')
        self.assertContains(response, "Due by today")
        self.assertContains(response, "Marking in progress")
