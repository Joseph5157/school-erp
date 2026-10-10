"""Phase 4 Gate 6: finalization (ADR 0009)."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Assessment, ResultStatus, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class FinalizationTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assessment = self.make_assessment(maximum="20", pass_mark="8")

    def enter(self, enrollment, status, score=None):
        self.assessment.save_draft_result(
            enrollment=enrollment, status=status, score=score, actor=self.rao
        )

    def complete(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "17")
        self.enter(self.meera_a, ResultStatus.ABSENT)

    def test_complete_assessment_finalizes_with_actor_time(self):
        self.complete()
        self.assessment.finalize(actor=self.admin)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, Assessment.Status.FINALIZED)
        self.assertEqual(self.assessment.finalized_by, self.admin)
        self.assertIsNotNone(self.assessment.finalized_at)
        self.assertIsNone(self.assessment.grading_snapshot)  # no scale applies

    def test_incomplete_assessment_rejected(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "17")
        with self.assertRaisesMessage(ValidationError, "1 Student(s) still have no result"):
            self.assessment.finalize(actor=self.admin)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, Assessment.Status.DRAFT)
        self.assertIsNone(self.assessment.finalized_by)

    def test_empty_roster_rejected(self):
        empty = self.make_assessment(section=self.six_b, name="Empty")
        with self.assertRaisesMessage(ValidationError, "No Students"):
            empty.finalize(actor=self.admin)

    def test_future_assessment_rejected(self):
        future = self.make_assessment(term=self.term2, name="Later", on=date(2026, 12, 15))
        self.assertIn("The assessment date has not been reached.", future.finalization_problems())
        with self.assertRaises(ValidationError):
            future.finalize(actor=self.admin)

    def test_ineligible_result_rejected(self):
        self.complete()
        _, asha_b = self.make_student("Asha Iyer", section=self.six_b)
        StudentResult.objects.create(
            assessment=self.assessment, academic_enrollment=asha_b,
            status=ResultStatus.ABSENT, entered_by=self.rao,
        )
        with self.assertRaisesMessage(ValidationError, "not on the roster"):
            self.assessment.finalize(actor=self.admin)

    def test_only_administrators_finalize(self):
        self.complete()
        for actor in (self.rao, self.make_user("clerk"), None):
            with self.subTest(actor=str(actor)), self.assertRaises(ValidationError):
                self.assessment.finalize(actor=actor)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, Assessment.Status.DRAFT)

    def test_cannot_finalize_twice(self):
        self.complete()
        self.assessment.finalize(actor=self.admin)
        first = Assessment.objects.get(pk=self.assessment.pk).finalized_at
        with self.assertRaisesMessage(ValidationError, "already finalized"):
            self.assessment.finalize(actor=self.admin)
        self.assertEqual(Assessment.objects.get(pk=self.assessment.pk).finalized_at, first)

    def test_finalized_stops_normal_editing(self):
        self.complete()
        self.assessment.finalize(actor=self.admin)
        with self.assertRaisesMessage(ValidationError, "finalized"):
            self.enter(self.ravi_a, ResultStatus.MARKED, "18")
        self.assertEqual(
            StudentResult.objects.get(academic_enrollment=self.ravi_a).score, Decimal("17")
        )
        self.assertTrue(self.assessment.is_locked)

    def test_database_requires_consistent_finalization_fields(self):
        for fields in (
            {"status": Assessment.Status.FINALIZED},
            {"finalized_by": self.admin},
            {"finalized_at": timezone.now()},
            {"grading_snapshot": {"scale": "x", "bands": []}},
        ):
            with self.subTest(fields=list(fields)), self.assertRaises(IntegrityError), (
                transaction.atomic()
            ):
                Assessment.objects.filter(pk=self.assessment.pk).update(**fields)

    def test_incomplete_grading_scale_blocks_finalization(self):
        scale = self.make_scale(bands=((90, "A"), (50, "B")))
        self.complete()
        with self.assertRaisesMessage(ValidationError, "needs a band starting at 0%"):
            self.assessment.finalize(actor=self.admin)
        scale.boundaries.create(label="C", min_percentage=0)
        self.assessment.finalize(actor=self.admin)

    def test_grades_are_frozen_at_finalization(self):
        scale = self.make_scale()
        self.complete()  # Ravi 17/20 = 85% -> B
        ravi = StudentResult.objects.get(academic_enrollment=self.ravi_a)
        self.assertEqual(ravi.grade, "B")  # DRAFT preview uses the live scale
        self.assessment.finalize(actor=self.admin)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.grading_snapshot["scale"], "Standard")
        scale.boundaries.filter(label="A").update(min_percentage=80)  # later policy change
        ravi = StudentResult.objects.get(academic_enrollment=self.ravi_a)
        self.assertEqual(ravi.grade, "B")  # still the finalized grade
        self.assertEqual(scale.grade_for(85), "A")  # live scale did change

    def test_derived_pass_fail_and_percentage(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "8")
        self.enter(self.meera_a, ResultStatus.ABSENT)
        ravi = StudentResult.objects.get(academic_enrollment=self.ravi_a)
        meera = StudentResult.objects.get(academic_enrollment=self.meera_a)
        self.assertEqual((ravi.pass_fail, ravi.percentage), ("PASS", Decimal("40.00")))
        self.assertEqual(meera.pass_fail, "ABSENT")
        self.assertIsNone(meera.grade)
        ravi_low = self.make_assessment(name="Quiz", maximum="10", pass_mark="5")
        ravi_low.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="4.5", actor=self.rao
        )
        self.assertEqual(ravi_low.results.get().pass_fail, "FAIL")
        no_pass = self.make_assessment(name="Practice", maximum="10")
        no_pass.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="1", actor=self.rao
        )
        self.assertIsNone(no_pass.results.get().pass_fail)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class FinalizationViewTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assessment = self.make_assessment()
        self.detail = reverse("core:assessment-detail", args=[self.assessment.pk])
        self.url = reverse("core:assessment-finalize", args=[self.assessment.pk])
        self.client.login(username="admin", password="pass-12345")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def test_detail_lists_problems_until_ready(self):
        page = self.client.get(self.detail)
        self.assertContains(page, "Not ready yet")
        self.assertContains(page, "1 Student(s) still have no result.")
        self.assertNotContains(page, "Finalize results</button>")

    def test_admin_finalizes_from_detail(self):
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="15", actor=self.rao
        )
        self.assertContains(self.client.get(self.detail), "Finalize results</button>")
        self.assertRedirects(self.client.post(self.url), self.detail)
        self.assessment.refresh_from_db()
        self.assertTrue(self.assessment.is_finalized)
        page = self.client.get(self.detail)
        self.assertContains(page, "by admin")
        self.assertContains(page, "75.00%")

    def test_incomplete_finalize_shows_reason(self):
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, "Not finalized")
        self.assessment.refresh_from_db()
        self.assertFalse(self.assessment.is_finalized)

    def test_teacher_cannot_finalize(self):
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="15", actor=self.rao
        )
        self.assertEqual(self.teacher.post(self.url).status_code, 403)
        self.client.get(self.url)  # GET never finalizes
        self.assessment.refresh_from_db()
        self.assertFalse(self.assessment.is_finalized)

    def test_teacher_sees_read_only_finalized_results(self):
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="15", actor=self.rao
        )
        self.assessment.finalize(actor=self.admin)
        page = self.teacher.get(reverse("core:assessment-marks-entry", args=[self.assessment.pk]))
        self.assertContains(page, "This assessment is finalized")
        self.assertIsNone(page.context["form"])
