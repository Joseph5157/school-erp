"""Phase 4 Gate 4: assessment planning (ADR 0009)."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicSubjectOffering, AcademicYear, Assessment, Subject
from core.tests.phase4_fixtures import Phase4Fixture


class AssessmentRuleTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_valid_assessment_starts_draft(self):
        assessment = self.make_assessment()
        self.assertEqual(assessment.status, Assessment.Status.DRAFT)
        self.assertEqual(assessment.subject, self.maths_subject)
        self.assertEqual(assessment.class_grade, self.grade6)

    def test_future_assessment_can_be_planned(self):
        self.make_assessment(term=self.term2, on=date(2026, 12, 20))

    def test_date_must_fall_inside_term(self):
        for on in (date(2026, 10, 1), date(2026, 5, 31)):
            with self.subTest(on=on), self.assertRaises(ValidationError) as ctx:
                self.make_assessment(on=on)
            self.assertIn("assessment_date", ctx.exception.message_dict)
        self.make_assessment(name="Edge start", on=date(2026, 6, 1))
        self.make_assessment(name="Edge end", on=date(2026, 9, 30))

    def test_term_and_offering_must_share_academic_year(self):
        other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        other = AcademicSubjectOffering.objects.create(
            academic_year=other_year, class_grade=self.grade6, subject=self.maths_subject
        )
        with self.assertRaises(ValidationError) as ctx:
            self.make_assessment(offering=other)
        self.assertIn("term", ctx.exception.message_dict)

    def test_section_must_take_the_offering(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make_assessment(offering=self.sanskrit, section=self.six_a)
        self.assertIn("section", ctx.exception.message_dict)
        self.make_assessment(offering=self.sanskrit, section=self.six_b)

    def test_maximum_marks_positive(self):
        for maximum in ("0", "-5"):
            with self.subTest(maximum=maximum), self.assertRaises(ValidationError):
                self.make_assessment(maximum=maximum)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assessment.objects.create(
                term=self.term1, offering=self.maths, section=self.six_a, name="Bad",
                assessment_date=date(2026, 7, 1), maximum_marks=0,
            )

    def test_pass_mark_within_zero_and_maximum(self):
        for pass_mark in ("21", "-1"):
            with self.subTest(pass_mark=pass_mark), self.assertRaises(ValidationError) as ctx:
                self.make_assessment(pass_mark=pass_mark)
            self.assertIn("pass_mark", ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assessment.objects.create(
                term=self.term1, offering=self.maths, section=self.six_a, name="Bad",
                assessment_date=date(2026, 7, 1), maximum_marks=20, pass_mark=25,
            )
        self.make_assessment(name="Pass equals max", pass_mark="20")
        self.make_assessment(name="No pass mark")

    def test_name_unique_per_offering_section_and_term(self):
        self.make_assessment()
        with self.assertRaises(ValidationError):
            self.make_assessment()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assessment.objects.create(
                term=self.term1, offering=self.maths, section=self.six_a, name="Unit Test 1",
                assessment_date=date(2026, 8, 1), maximum_marks=20,
            )
        self.make_assessment(section=self.six_b)
        self.make_assessment(term=self.term2, on=date(2026, 10, 15))

    def test_new_assessment_cannot_start_finalized(self):
        assessment = Assessment(
            term=self.term1, offering=self.maths, section=self.six_a, name="X",
            assessment_date=date(2026, 7, 1), maximum_marks=20,
            status=Assessment.Status.FINALIZED,
        )
        with self.assertRaises(ValidationError):
            assessment.full_clean()

    def test_unused_draft_can_be_edited_and_deleted(self):
        assessment = self.make_assessment()
        self.assertFalse(assessment.is_locked)
        assessment.maximum_marks = Decimal("25")
        assessment.assessment_date = date(2026, 7, 20)
        assessment.full_clean()
        assessment.save()
        assessment.delete()
        self.assertFalse(Assessment.objects.exists())

    def test_finalized_assessment_is_locked(self):
        assessment = self.make_assessment()
        self.force_finalize(assessment)
        assessment.refresh_from_db()
        self.assertTrue(assessment.is_locked)
        assessment.maximum_marks = Decimal("30")
        with self.assertRaises(ValidationError):
            assessment.full_clean()
        assessment.refresh_from_db()
        assessment.name = "Renamed"  # not a locked field
        assessment.full_clean()
        with self.assertRaises(ValidationError):
            assessment.delete()
        self.assertTrue(Assessment.objects.filter(pk=assessment.pk).exists())

    def test_structures_used_by_assessments_are_protected(self):
        self.make_assessment()
        for obj in (self.term1, self.maths, self.six_a):
            with self.subTest(obj=str(obj)), self.assertRaises(ProtectedError), (
                transaction.atomic()
            ):
                obj.delete()


class AssessmentViewTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.list_url = reverse("core:academic-year-assessments", args=[self.year.pk])
        self.add_url = reverse("core:assessment-create", args=[self.year.pk])
        self.payload = {
            "term": self.term1.pk, "offering": self.maths.pk, "section": self.six_a.pk,
            "name": "Unit Test 1", "assessment_date": "2026-07-15", "maximum_marks": "20",
            "pass_mark": "7",
        }

    def test_plan_list_filter_and_view(self):
        response = self.client.post(self.add_url, self.payload)
        assessment = Assessment.objects.get()
        self.assertRedirects(response, reverse("core:assessment-detail", args=[assessment.pk]))
        self.assertEqual(assessment.pass_mark, Decimal("7"))
        self.make_assessment(section=self.six_b, name="Other section")
        filtered = self.client.get(self.list_url, {"section": self.six_a.pk})
        self.assertEqual(list(filtered.context["assessments"]), [assessment])
        detail = self.client.get(reverse("core:assessment-detail", args=[assessment.pk]))
        self.assertContains(detail, "Unit Test 1")
        self.assertContains(detail, "Draft")

    def test_invalid_plan_shows_errors(self):
        response = self.client.post(
            self.add_url, {**self.payload, "assessment_date": "2026-11-01", "pass_mark": "30"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The date must fall inside Term 1")
        self.assertContains(response, "cannot exceed the maximum marks")
        self.assertFalse(Assessment.objects.exists())

    def test_form_limits_choices_to_the_year(self):
        other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        AcademicSubjectOffering.objects.create(
            academic_year=other_year, class_grade=self.grade6,
            subject=Subject.objects.create(name="History"),
        )
        form = self.client.get(self.add_url).context["form"]
        self.assertEqual(set(form.fields["term"].queryset), {self.term1, self.term2})
        self.assertEqual(set(form.fields["offering"].queryset), {self.maths, self.sanskrit})

    def test_edit_and_delete(self):
        assessment = self.make_assessment()
        self.client.post(
            reverse("core:assessment-update", args=[assessment.pk]),
            {**self.payload, "name": "Unit Test 1 (revised)", "maximum_marks": "25"},
        )
        assessment.refresh_from_db()
        self.assertEqual((assessment.name, assessment.maximum_marks), (
            "Unit Test 1 (revised)", Decimal("25")))
        delete_url = reverse("core:assessment-delete", args=[assessment.pk])
        self.client.get(delete_url)
        self.assertTrue(Assessment.objects.exists())
        self.assertRedirects(self.client.post(delete_url), self.list_url)
        self.assertFalse(Assessment.objects.exists())

    def test_finalized_assessment_cannot_be_edited_or_deleted(self):
        assessment = self.make_assessment()
        self.force_finalize(assessment)
        detail = reverse("core:assessment-detail", args=[assessment.pk])
        self.assertRedirects(
            self.client.post(reverse("core:assessment-update", args=[assessment.pk]),
                             self.payload),
            detail,
        )
        self.client.post(reverse("core:assessment-delete", args=[assessment.pk]))
        self.assertTrue(Assessment.objects.filter(pk=assessment.pk).exists())

    def test_teacher_cannot_plan_or_change_assessments(self):
        assessment = self.make_assessment()
        for url in (
            self.list_url, self.add_url,
            reverse("core:assessment-detail", args=[assessment.pk]),
            reverse("core:assessment-update", args=[assessment.pk]),
            reverse("core:assessment-delete", args=[assessment.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.teacher.post(url, self.payload).status_code, 403)
        self.assertEqual(Assessment.objects.count(), 1)
