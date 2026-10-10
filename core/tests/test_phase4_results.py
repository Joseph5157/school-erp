"""Phase 4 Gate 5: date-effective roster and teacher DRAFT results (ADR 0009/0010)."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.models import Assessment, ResultStatus, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class RosterTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.asha, self.asha_b = self.make_student("Asha Iyer", section=self.six_b)

    def test_roster_is_section_and_date_effective(self):
        assessment = self.make_assessment()
        self.assertEqual(list(assessment.roster()), [self.meera_a, self.ravi_a])

    def test_transfer_keeps_old_roster_and_moves_student_for_later_dates(self):
        early = self.make_assessment(on=date(2026, 7, 15))
        ravi_b = self.ravi.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_b,
            start_date=date(2026, 8, 1),
        )
        self.ravi_a.refresh_from_db()
        late_a = self.make_assessment(name="Unit Test 2", on=date(2026, 8, 20))
        late_b = self.make_assessment(name="Unit Test 2", section=self.six_b, on=date(2026, 8, 20))
        self.assertIn(self.ravi_a, early.roster())
        self.assertNotIn(self.ravi_a, late_a.roster())
        self.assertIn(ravi_b, late_b.roster())

    def test_late_joiner_not_on_earlier_roster(self):
        _, late = self.make_student("Dev Nair", start=date(2026, 7, 20))
        self.assertNotIn(late, self.make_assessment(on=date(2026, 7, 15)).roster())


@mock.patch("core.models.business_today", new=lambda: TODAY)
class DraftResultTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assessment = self.make_assessment(maximum="20", pass_mark="7")

    _DEFAULT = object()

    def enter(self, enrollment, status, score=None, actor=_DEFAULT, assessment=None):
        return (assessment or self.assessment).save_draft_result(
            enrollment=enrollment,
            status=status,
            score=score,
            actor=self.rao if actor is self._DEFAULT else actor,
        )

    def test_assigned_teacher_enters_marked_and_absent(self):
        marked = self.enter(self.ravi_a, ResultStatus.MARKED, "17")
        absent = self.enter(self.meera_a, ResultStatus.ABSENT)
        self.assertEqual((marked.score, marked.entered_by), (Decimal("17"), self.rao))
        self.assertEqual(marked.percentage, Decimal("85.00"))
        self.assertIsNone(absent.score)
        self.assertIsNone(absent.percentage)

    def test_zero_is_a_valid_mark_not_absence(self):
        result = self.enter(self.ravi_a, ResultStatus.MARKED, "0")
        self.assertEqual((result.status, result.score), (ResultStatus.MARKED, Decimal("0")))

    def test_score_bounds(self):
        for score in ("-1", "20.01"):
            with self.subTest(score=score), self.assertRaises(ValidationError):
                self.enter(self.ravi_a, ResultStatus.MARKED, score)
        self.enter(self.ravi_a, ResultStatus.MARKED, "20")

    def test_marked_needs_score_and_absent_drops_any_score(self):
        with self.assertRaises(ValidationError):
            self.enter(self.ravi_a, ResultStatus.MARKED, None)
        result = self.enter(self.ravi_a, ResultStatus.ABSENT, "12")
        self.assertIsNone(result.score)

    def test_database_rejects_inconsistent_status_and_score(self):
        for status, score in (
            (ResultStatus.MARKED, None), (ResultStatus.ABSENT, 5), (ResultStatus.MARKED, -1),
            ("LATE", 5),
        ):
            with self.subTest(status=status, score=score), self.assertRaises(IntegrityError), (
                transaction.atomic()
            ):
                StudentResult.objects.create(
                    assessment=self.assessment, academic_enrollment=self.ravi_a,
                    status=status, score=score, entered_by=self.rao,
                )

    def test_incomplete_draft_is_fine_and_missing_is_not_absent(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "15")
        self.assertEqual(list(self.assessment.unmarked_enrollments()), [self.meera_a])
        self.assertFalse(self.assessment.results.filter(status=ResultStatus.ABSENT).exists())
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.status, Assessment.Status.DRAFT)

    def test_draft_edit_updates_in_place(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "15")
        self.enter(self.ravi_a, ResultStatus.ABSENT)
        self.enter(self.ravi_a, ResultStatus.MARKED, "16")
        result = StudentResult.objects.get()
        self.assertEqual((result.status, result.score), (ResultStatus.MARKED, Decimal("16")))

    def test_unique_result_per_enrollment(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "15")
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentResult.objects.create(
                assessment=self.assessment, academic_enrollment=self.ravi_a,
                status=ResultStatus.ABSENT, entered_by=self.rao,
            )

    def test_only_assigned_teacher_may_enter(self):
        self.assign(self.iyer, self.maths, self.six_b)
        for actor in (self.iyer, self.admin, None):
            with self.subTest(actor=str(actor)), self.assertRaises(ValidationError):
                self.enter(self.ravi_a, ResultStatus.MARKED, "10", actor=actor)
        self.assertFalse(StudentResult.objects.exists())

    def test_no_entry_before_assessment_date(self):
        future = self.make_assessment(term=self.term2, name="End of term", on=date(2026, 12, 15))
        with self.assertRaisesMessage(ValidationError, "before the assessment date"):
            self.enter(self.ravi_a, ResultStatus.MARKED, "10", assessment=future)

    def test_entry_on_the_assessment_date_is_allowed(self):
        today = self.make_assessment(term=self.term2, name="Today", on=TODAY)
        self.enter(self.ravi_a, ResultStatus.MARKED, "10", assessment=today)

    def test_student_not_on_roster_rejected(self):
        _, asha_b = self.make_student("Asha Iyer", section=self.six_b)
        _, late = self.make_student("Dev Nair", start=date(2026, 8, 1))
        for enrollment in (asha_b, late):
            with self.subTest(student=str(enrollment.student)), self.assertRaises(
                ValidationError
            ):
                self.enter(enrollment, ResultStatus.MARKED, "10")

    def test_historical_enrollment_after_transfer_still_accepted(self):
        self.ravi.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_b,
            start_date=date(2026, 8, 1),
        )
        self.ravi_a.refresh_from_db()
        result = self.enter(self.ravi_a, ResultStatus.MARKED, "18")
        self.assertEqual(result.academic_enrollment.section, self.six_a)

    def test_finalized_assessment_rejects_draft_entry(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "15")
        Assessment.objects.filter(pk=self.assessment.pk).update(
            status=Assessment.Status.FINALIZED
        )
        with self.assertRaisesMessage(ValidationError, "finalized"):
            self.enter(self.ravi_a, ResultStatus.MARKED, "16")
        self.assertEqual(StudentResult.objects.get().score, Decimal("15"))

    def test_results_lock_assessment_context_and_deletion(self):
        self.enter(self.ravi_a, ResultStatus.MARKED, "15")
        self.assessment.refresh_from_db()
        self.assertTrue(self.assessment.is_locked)
        self.assessment.maximum_marks = Decimal("25")
        with self.assertRaises(ValidationError):
            self.assessment.full_clean()
        self.assessment.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.assessment.delete()
        for obj in (self.ravi_a, self.rao):
            with self.subTest(obj=str(obj)), self.assertRaises(ProtectedError), (
                transaction.atomic()
            ):
                obj.delete()


@mock.patch("core.models.business_today", new=lambda: TODAY)
class MarksEntryViewTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.assessment = self.make_assessment()
        self.url = reverse("core:assessment-marks-entry", args=[self.assessment.pk])
        self.rao_client = self.client_class()
        self.rao_client.login(username="rao", password="pass-12345")
        self.iyer_client = self.client_class()
        self.iyer_client.login(username="iyer", password="pass-12345")
        self.client.login(username="admin", password="pass-12345")

    def data(self, **rows):
        payload = {}
        for enrollment, (status, score) in rows.items():
            payload[f"status_{enrollment}"] = status
            payload[f"score_{enrollment}"] = score
        return payload

    def test_my_assessments_lists_only_assigned(self):
        self.make_assessment(section=self.six_b, name="Other section")
        response = self.rao_client.get(reverse("core:my-assessments"))
        self.assertEqual(list(response.context["assessments"]), [self.assessment])
        self.assertContains(response, "My assessments")

    def test_teacher_saves_partial_draft(self):
        response = self.rao_client.post(
            self.url, self.data(**{str(self.ravi_a.pk): ("", "17")})
        )
        self.assertRedirects(response, self.url)
        result = StudentResult.objects.get()
        self.assertEqual((result.status, result.score), (ResultStatus.MARKED, Decimal("17")))
        page = self.rao_client.get(self.url)
        self.assertContains(page, "blank is <strong>not</strong> absent")

    def test_form_validation_errors(self):
        response = self.rao_client.post(
            self.url,
            self.data(**{
                str(self.ravi_a.pk): ("ABSENT", "5"),
                str(self.meera_a.pk): ("MARKED", "25"),
            }),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An absent Student has no score.")
        self.assertFalse(StudentResult.objects.exists())

    def test_other_teacher_and_admin_cannot_enter(self):
        self.assertEqual(self.iyer_client.get(self.url).status_code, 403)
        self.assertEqual(
            self.iyer_client.post(
                self.url, self.data(**{str(self.ravi_a.pk): ("MARKED", "10")})
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.url).status_code, 403)  # admin is not a teacher
        self.assertFalse(StudentResult.objects.exists())

    def test_future_assessment_shows_when_entry_opens(self):
        future = self.make_assessment(term=self.term2, name="Later", on=date(2026, 12, 15))
        response = self.rao_client.get(reverse("core:assessment-marks-entry", args=[future.pk]))
        self.assertContains(response, "Marks entry opens on")
        self.assertIsNone(response.context["form"])

    def test_admin_sees_results_and_completeness(self):
        self.assessment.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.ABSENT, actor=self.rao
        )
        response = self.client.get(reverse("core:assessment-detail", args=[self.assessment.pk]))
        self.assertContains(response, "results entered: 1")
        self.assertContains(response, "Not entered")
        self.assertContains(response, "Absent")
        self.assertEqual(response.context["teacher"], self.rao)

    def test_teacher_cannot_open_admin_assessment_pages(self):
        for url in (
            reverse("core:assessment-detail", args=[self.assessment.pk]),
            reverse("core:academic-year-assessments", args=[self.year.pk]),
        ):
            self.assertEqual(self.rao_client.get(url).status_code, 403)

    def test_menu_link_only_for_teachers(self):
        self.assertContains(self.rao_client.get(reverse("core:my-assessments")), "My assessments")
        admin_page = self.client.get(reverse("core:academic-year-list"))
        self.assertNotContains(admin_page, reverse("core:my-assessments"))
