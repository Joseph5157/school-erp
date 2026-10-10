"""Phase 4 Gate 7: audited corrections of finalized results (ADR 0009)."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.models import Assessment, ResultCorrection, ResultStatus, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class CorrectionTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.make_scale()
        self.assessment = self.make_assessment(maximum="20", pass_mark="8")
        for enrollment, status, score in (
            (self.ravi_a, ResultStatus.MARKED, "17"),
            (self.meera_a, ResultStatus.ABSENT, None),
        ):
            self.assessment.save_draft_result(
                enrollment=enrollment, status=status, score=score, actor=self.rao
            )
        self.assessment.finalize(actor=self.admin)
        self.ravi_result = StudentResult.objects.get(academic_enrollment=self.ravi_a)
        self.meera_result = StudentResult.objects.get(academic_enrollment=self.meera_a)

    def test_marked_to_marked(self):
        self.ravi_result.correct(
            new_status=ResultStatus.MARKED, new_score="18", actor=self.admin,
            reason="Re-totalled the paper.",
        )
        self.ravi_result.refresh_from_db()
        self.assertEqual(self.ravi_result.score, Decimal("18"))
        correction = ResultCorrection.objects.get()
        self.assertEqual(
            (correction.previous_status, correction.previous_score,
             correction.new_status, correction.new_score, correction.corrected_by,
             correction.reason),
            ("MARKED", Decimal("17"), "MARKED", Decimal("18"), self.admin,
             "Re-totalled the paper."),
        )
        self.assertIsNotNone(correction.created_at)

    def test_absent_to_marked_and_marked_to_absent(self):
        self.meera_result.correct(
            new_status=ResultStatus.MARKED, new_score="15", actor=self.admin,
            reason="Sat the paper late with permission.",
        )
        self.ravi_result.correct(
            new_status=ResultStatus.ABSENT, new_score="99", actor=self.admin,
            reason="Wrong Student marked.",
        )
        self.meera_result.refresh_from_db()
        self.ravi_result.refresh_from_db()
        self.assertEqual((self.meera_result.status, self.meera_result.score),
                         (ResultStatus.MARKED, Decimal("15")))
        self.assertEqual((self.ravi_result.status, self.ravi_result.score),
                         (ResultStatus.ABSENT, None))

    def test_assessment_stays_finalized_and_grade_uses_frozen_bands(self):
        self.ravi_result.correct(
            new_status=ResultStatus.MARKED, new_score="19", actor=self.admin, reason="Re-mark."
        )
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, Assessment.Status.FINALIZED)
        self.ravi_result.refresh_from_db()
        self.assertEqual(self.ravi_result.grade, "A")  # 95% with frozen bands
        self.assertEqual(self.ravi_result.pass_fail, "PASS")

    def test_repeated_corrections_keep_the_whole_sequence(self):
        for score, reason in (("18", "first"), ("16", "second")):
            self.ravi_result.correct(
                new_status=ResultStatus.MARKED, new_score=score, actor=self.admin, reason=reason
            )
        self.ravi_result.correct(
            new_status=ResultStatus.ABSENT, actor=self.admin, reason="third"
        )
        history = list(
            self.ravi_result.corrections.order_by("created_at", "pk").values_list(
                "previous_status", "previous_score", "new_status", "new_score", "reason"
            )
        )
        self.assertEqual(history, [
            ("MARKED", Decimal("17"), "MARKED", Decimal("18"), "first"),
            ("MARKED", Decimal("18"), "MARKED", Decimal("16"), "second"),
            ("MARKED", Decimal("16"), "ABSENT", None, "third"),
        ])

    def test_rejections_change_nothing(self):
        cases = [
            dict(new_status=ResultStatus.MARKED, new_score="17", actor=self.admin, reason="x"),
            dict(new_status=ResultStatus.MARKED, new_score="21", actor=self.admin, reason="x"),
            dict(new_status=ResultStatus.MARKED, new_score="-1", actor=self.admin, reason="x"),
            dict(new_status=ResultStatus.MARKED, new_score=None, actor=self.admin, reason="x"),
            dict(new_status="LATE", new_score="10", actor=self.admin, reason="x"),
            dict(new_status=ResultStatus.MARKED, new_score="18", actor=self.admin, reason=" "),
            dict(new_status=ResultStatus.MARKED, new_score="18", actor=self.rao, reason="x"),
            dict(new_status=ResultStatus.MARKED, new_score="18", actor=None, reason="x"),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                self.ravi_result.correct(**case)
        self.ravi_result.refresh_from_db()
        self.assertEqual(self.ravi_result.score, Decimal("17"))
        self.assertFalse(ResultCorrection.objects.exists())

    def test_draft_results_are_not_corrected(self):
        draft = self.make_assessment(name="Unit Test 2", on=date(2026, 8, 1))
        draft.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="10", actor=self.rao
        )
        with self.assertRaisesMessage(ValidationError, "still a draft"):
            draft.results.get().correct(
                new_status=ResultStatus.MARKED, new_score="11", actor=self.admin, reason="x"
            )

    def test_database_checks_and_history_protection(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResultCorrection.objects.create(
                result=self.ravi_result, previous_status="ABSENT", previous_score=5,
                new_status="MARKED", new_score=6, reason="x", corrected_by=self.admin,
            )
        self.ravi_result.correct(
            new_status=ResultStatus.MARKED, new_score="18", actor=self.admin, reason="x"
        )
        for obj in (self.ravi_result, self.admin):
            with self.subTest(obj=str(obj)), self.assertRaises(ProtectedError), (
                transaction.atomic()
            ):
                obj.delete()


@mock.patch("core.models.business_today", new=lambda: TODAY)
class CorrectionViewTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assessment = self.make_assessment()
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="12", actor=self.rao
        )
        self.result = self.assessment.results.get()
        self.url = reverse("core:result-correct", args=[self.result.pk])
        self.detail = reverse("core:assessment-detail", args=[self.assessment.pk])
        self.client.login(username="admin", password="pass-12345")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def test_draft_redirects_to_detail(self):
        self.assertRedirects(self.client.get(self.url), self.detail)

    def test_admin_corrects_with_reason_and_history_shows(self):
        self.assessment.finalize(actor=self.admin)
        self.assertContains(self.client.get(self.detail), "Correct</a>")
        response = self.client.post(
            self.url, {"status": "MARKED", "score": "14", "reason": "Missed a page."}
        )
        self.assertRedirects(response, self.detail)
        page = self.client.get(self.url)
        self.assertContains(page, "Missed a page.")
        self.assertContains(self.client.get(self.detail), "corrected")

    def test_form_errors(self):
        self.assessment.finalize(actor=self.admin)
        for data, message in (
            ({"status": "MARKED", "score": "", "reason": "x"}, "Enter the corrected score."),
            ({"status": "ABSENT", "score": "3", "reason": "x"}, "An absent Student has no score."),
            ({"status": "MARKED", "score": "25", "reason": "x"}, "less than or equal to 20"),
            ({"status": "MARKED", "score": "12", "reason": "x"}, "already has this value"),
        ):
            with self.subTest(data=data):
                self.assertContains(self.client.post(self.url, data), message)
        self.assertFalse(ResultCorrection.objects.exists())

    def test_teacher_cannot_correct(self):
        self.assessment.finalize(actor=self.admin)
        response = self.teacher.post(self.url, {"status": "MARKED", "score": "20", "reason": "x"})
        self.assertEqual(response.status_code, 403)
        self.result.refresh_from_db()
        self.assertEqual(self.result.score, Decimal("12"))
