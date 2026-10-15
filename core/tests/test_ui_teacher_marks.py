"""U3 teacher marks and students: marks entry, gradebook, My students."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.forms import ResultEntryForm
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class MarksFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        _, self.asha = self.make_student("Asha")
        _, self.bina = self.make_student("Bina")
        _, self.ravi = self.make_student("Ravi")
        self.duty = self.assign(self.rao, self.maths, self.six_a)
        self.test1 = self.make_assessment(name="Unit Test 1", on=date(2026, 7, 15))
        self.test2 = self.make_assessment(name="Unit Test 2", on=date(2026, 7, 22))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def entry_url(self, assessment):
        return reverse("core:assessment-marks-entry", args=[assessment.pk])

    def result(self, assessment, enrollment, status, score=None):
        assessment.save_draft_result(
            enrollment=enrollment, status=status,
            score=Decimal(score) if score is not None else None, actor=self.rao,
        )


class ResultFormTests(MarksFixture, TestCase):
    def test_counts_use_saved_results(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        form = ResultEntryForm(assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "12",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": "",
                f"status_{self.ravi.pk}": "", f"score_{self.ravi.pk}": ""}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_zero_score_counts_as_marked(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0"}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts()["marked"], 1)

    def test_status_is_three_radios_and_score_has_keypad_hints(self):
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value=""')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="MARKED"')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="ABSENT"')
        self.assertContains(page, 'inputmode="decimal"')
        self.assertContains(page, 'enterkeyhint="next"')


class MarksEntryPageTests(MarksFixture, TestCase):
    def test_rows_are_fieldsets_with_static_counts(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, '<legend class="visually-hidden">Asha</legend>')
        self.assertEqual(page.content.decode().count("<fieldset"), 3)
        self.assertContains(page, "All 3 · Not entered 2 · Marked 1 · Absent 0")
        self.assertContains(page, "2 not entered")
        self.assertContains(page, "data-erp-marks")
        self.assertContains(page, "blank is <strong>not</strong> absent")

    def test_invalid_post_keeps_typed_values(self):
        data = {f"status_{self.asha.pk}": "ABSENT", f"score_{self.asha.pk}": "5",
                f"status_{self.bina.pk}": "", f"score_{self.bina.pk}": "11"}
        page = self.teacher.post(self.entry_url(self.test1), data)
        self.assertContains(page, "An absent Student has no score.")
        self.assertContains(page, 'value="11"')
        self.assertContains(page, "All 3 · Not entered 1 · Marked 1 · Absent 1")

    def test_saving_still_works(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": ""}
        response = self.teacher.post(self.entry_url(self.test1), data, follow=True)
        self.assertContains(response, "Marks saved as draft.")
        results = {r.academic_enrollment_id: (r.status, r.score)
                   for r in self.test1.results.all()}
        self.assertEqual(results[self.asha.pk], ("MARKED", Decimal("0")))
        self.assertEqual(results[self.bina.pk][0], "ABSENT")
        self.assertNotIn(self.ravi.pk, results)

    def test_finalized_shows_cards_with_not_entered(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        self.force_finalize(self.test1)
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, "This assessment is finalized")
        self.assertContains(page, "18 / 20")
        self.assertContains(page, "Not entered")
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
        self.assertNotContains(page, "<table")
