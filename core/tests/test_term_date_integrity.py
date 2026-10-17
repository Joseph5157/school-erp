"""Term dates cannot move underneath assessments and finalized results (R7)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicTerm
from core.tests.phase4_fixtures import Phase4Fixture


class TermDateIntegrityTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def edit(self, term, **changes):
        term = AcademicTerm.objects.get(pk=term.pk)
        for field, value in changes.items():
            setattr(term, field, value)
        term.full_clean()
        term.save()
        return term

    # --- before anything is finalized -------------------------------------

    def test_shrinking_past_an_existing_assessment_is_rejected(self):
        self.make_assessment(term=self.term1, on=date(2026, 9, 15))
        with self.assertRaisesMessage(ValidationError, "Unit Test 1"):
            self.edit(self.term1, end_date=date(2026, 8, 31))
        self.term1.refresh_from_db()
        self.assertEqual(self.term1.end_date, date(2026, 9, 30))

    def test_moving_the_start_past_an_existing_assessment_is_rejected(self):
        self.make_assessment(term=self.term1, on=date(2026, 6, 10))
        with self.assertRaises(ValidationError):
            self.edit(self.term1, start_date=date(2026, 6, 20))

    def test_expanding_is_allowed_while_nothing_is_finalized(self):
        self.make_assessment(term=self.term2, on=date(2026, 11, 15), name="Mid")
        term = self.edit(self.term2, end_date=date(2027, 1, 31))
        self.assertEqual(term.end_date, date(2027, 1, 31))

    def test_shrinking_that_still_contains_every_assessment_is_allowed(self):
        self.make_assessment(term=self.term1, on=date(2026, 7, 15))
        term = self.edit(self.term1, end_date=date(2026, 9, 1))
        self.assertEqual(term.end_date, date(2026, 9, 1))

    def test_an_assessment_on_the_boundary_day_is_kept(self):
        self.make_assessment(term=self.term1, on=date(2026, 9, 30))
        self.edit(self.term1, start_date=date(2026, 6, 15))
        with self.assertRaises(ValidationError):
            self.edit(self.term1, end_date=date(2026, 9, 29))

    def test_assessments_of_other_terms_do_not_block_the_edit(self):
        self.make_assessment(term=self.term2, on=date(2026, 11, 15))
        term = self.edit(self.term1, end_date=date(2026, 9, 1))
        self.assertEqual(term.end_date, date(2026, 9, 1))

    # --- once a result is finalized ---------------------------------------

    def finalized_in(self, term, on):
        assessment = self.make_assessment(term=term, on=on, name="Final")
        self.force_finalize(assessment)
        return assessment

    def test_extending_a_frozen_term_is_rejected(self):
        self.finalized_in(self.term2, date(2026, 11, 15))
        with self.assertRaisesMessage(ValidationError, "finalized"):
            self.edit(self.term2, end_date=date(2027, 1, 31))

    def test_shrinking_a_frozen_term_is_rejected(self):
        self.finalized_in(self.term2, date(2026, 11, 15))
        with self.assertRaisesMessage(ValidationError, "finalized"):
            self.edit(self.term2, end_date=date(2026, 12, 20))

    def test_moving_the_start_of_a_frozen_term_is_rejected(self):
        self.finalized_in(self.term2, date(2026, 11, 15))
        with self.assertRaises(ValidationError):
            self.edit(self.term2, start_date=date(2026, 10, 5))

    def test_name_stays_editable_on_a_frozen_term(self):
        self.finalized_in(self.term2, date(2026, 11, 15))
        term = self.edit(self.term2, name="Second Term")
        self.assertEqual(term.name, "Second Term")

    def test_saving_unchanged_dates_on_a_frozen_term_is_allowed(self):
        self.finalized_in(self.term2, date(2026, 11, 15))
        self.edit(self.term2, display_order=2)

    def test_a_finalized_assessment_in_another_term_does_not_freeze_this_one(self):
        self.finalized_in(self.term1, date(2026, 7, 15))
        term = self.edit(self.term2, end_date=date(2027, 1, 31))
        self.assertEqual(term.end_date, date(2027, 1, 31))

    # --- through the administrator page -----------------------------------

    def test_the_edit_page_shows_the_reason_and_saves_nothing(self):
        self.make_assessment(term=self.term1, on=date(2026, 9, 15))
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:term-update", args=[self.term1.pk]),
            {"name": "Term 1", "start_date": "2026-06-01", "end_date": "2026-08-31",
             "display_order": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unit Test 1")
        self.term1.refresh_from_db()
        self.assertEqual(self.term1.end_date, date(2026, 9, 30))
