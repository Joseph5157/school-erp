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
