"""Option A3: the assessment list's "Due by today" filter (spec 6.2 step 1, section 9).

`due=1` keeps assessments dated on or before the business date, combines with term, status and
section, and an invalid value makes the form invalid so no filter is applied (the existing
invalid-filter behaviour).

All data here is synthetic and local.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from core.models import Assessment
from core.tests.test_admin_overview_analytics import MarksFixture


class DueFilterTests(MarksFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.past = self.assessment({}, name="Past draft", finalize=False)
        self.future = self.assessment({}, name="Future draft", finalize=False)
        Assessment.objects.filter(pk=self.future.pk).update(
            assessment_date=datetime.date(2026, 8, 1))
        self.term1_done = self.assessment({self.s1: 10}, name="Term 1 done", term=self.term_a)
        grade, section, _ = self.second_class()
        self.other_section = self.assessment({}, name="Other section", class_grade=grade,
                                             section=section, finalize=False)
        self.url = reverse("core:academic-year-assessments", args=[self.year.pk])

    def names(self, **params):
        response = self.administrator.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response, {a.name for a in response.context["assessments"]}

    def test_due_excludes_future_drafts(self):
        _, names = self.names(due="1")
        self.assertNotIn("Future draft", names)
        self.assertIn("Past draft", names)

    def test_without_due_future_drafts_are_listed(self):
        _, names = self.names()
        self.assertIn("Future draft", names)

    def test_due_combines_with_term_status_and_section(self):
        _, names = self.names(due="1", term=self.term_b.pk, status="DRAFT",
                              section=self.section.pk)
        self.assertEqual(names, {"Past draft"})
        _, names = self.names(due="1", term=self.term_a.pk)
        self.assertEqual(names, {"Term 1 done"})

    def test_invalid_due_value_applies_no_filter(self):
        response, names = self.names(due="soon")
        self.assertIn("due", response.context["form"].errors)
        self.assertIn("Future draft", names)

    def test_filtered_note_mentions_the_due_filter(self):
        response, _ = self.names(due="1")
        self.assertContains(response, "Showing assessments that match the filters.")
