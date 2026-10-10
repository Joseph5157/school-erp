"""Phase 4 Gate 3: grading scales (ADR 0009)."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicYear,
    ClassGrade,
    GradeBoundary,
    GradingScale,
    GradingScaleClassGrade,
    grade_from_bands,
)

User = get_user_model()

CBSE_LIKE = [
    (91, "A1"), (81, "A2"), (71, "B1"), (61, "B2"), (51, "C1"), (41, "C2"), (33, "D"), (0, "E"),
]


class GradingFixture:
    def build(self):
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        self.other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.grade6 = ClassGrade.objects.create(name="Grade 6")
        self.grade7 = ClassGrade.objects.create(name="Grade 7")

    def scale(self, name="Standard", bands=CBSE_LIKE, grades=(), year=None):
        scale = GradingScale.objects.create(academic_year=year or self.year, name=name)
        for minimum, label in bands:
            band = GradeBoundary(scale=scale, label=label, min_percentage=Decimal(minimum))
            band.full_clean()
            band.save()
        scale.set_class_grades(grades)
        return scale


class GradeResolutionTests(GradingFixture, TestCase):
    def setUp(self):
        self.build()
        self.standard = self.scale()

    def test_resolution_at_and_between_boundaries(self):
        expectations = {
            100: "A1", 91: "A1", Decimal("90.99"): "A2", 81: "A2", 80: "B1", 33: "D",
            Decimal("32.99"): "E", 0: "E",
        }
        for percentage, grade in expectations.items():
            with self.subTest(percentage=percentage):
                self.assertEqual(self.standard.grade_for(percentage), grade)

    def test_resolution_is_deterministic_regardless_of_band_creation_order(self):
        shuffled = self.scale("Shuffled", bands=list(reversed(CBSE_LIKE)))
        for percentage in range(0, 101):
            self.assertEqual(shuffled.grade_for(percentage), self.standard.grade_for(percentage))

    def test_no_percentage_means_no_grade(self):
        self.assertIsNone(self.standard.grade_for(None))

    def test_out_of_range_percentage_rejected(self):
        for percentage in (-1, Decimal("100.01")):
            with self.subTest(percentage=percentage), self.assertRaises(ValueError):
                self.standard.grade_for(percentage)

    def test_incomplete_scale_gives_no_grade_below_its_lowest_band(self):
        partial = self.scale("Partial", bands=[(50, "Pass")])
        self.assertFalse(partial.is_complete)
        self.assertIsNone(partial.grade_for(40))
        self.assertEqual(partial.grade_for(50), "Pass")
        self.assertTrue(self.standard.is_complete)

    def test_snapshot_resolves_like_the_live_scale_and_survives_edits(self):
        snapshot = self.standard.snapshot()
        self.assertEqual(snapshot["scale"], "Standard")
        self.assertEqual(snapshot["bands"][0], ["91.00", "A1"])
        self.standard.boundaries.filter(label="A1").update(min_percentage=95)
        self.assertEqual(grade_from_bands(snapshot["bands"], 92), "A1")  # frozen
        self.assertEqual(self.standard.grade_for(92), "A2")  # live scale changed


class BoundaryRuleTests(GradingFixture, TestCase):
    def setUp(self):
        self.build()
        self.standard = self.scale()

    def test_label_and_minimum_unique_per_scale(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GradeBoundary.objects.create(scale=self.standard, label="A1", min_percentage=99)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GradeBoundary.objects.create(scale=self.standard, label="Z", min_percentage=91)

    def test_minimum_must_be_between_0_and_100(self):
        for minimum in (Decimal("-1"), Decimal("100.5")):
            band = GradeBoundary(scale=self.standard, label="X", min_percentage=minimum)
            with self.subTest(minimum=minimum), self.assertRaises(ValidationError):
                band.full_clean()
            with self.subTest(db=minimum), self.assertRaises(IntegrityError), (
                transaction.atomic()
            ):
                GradeBoundary.objects.create(scale=self.standard, label="X", min_percentage=minimum)


class ScaleApplicabilityTests(GradingFixture, TestCase):
    def setUp(self):
        self.build()

    def test_scale_for_year_and_grade(self):
        standard = self.scale(grades=[self.grade6])
        self.assertEqual(GradingScale.for_grade(self.year, self.grade6), standard)
        self.assertIsNone(GradingScale.for_grade(self.year, self.grade7))
        self.assertIsNone(GradingScale.for_grade(self.other_year, self.grade6))

    def test_one_scale_per_year_and_grade(self):
        self.scale(grades=[self.grade6])
        with self.assertRaises(ValidationError):
            self.scale("Second", grades=[self.grade6, self.grade7])
        self.assertIsNone(GradingScale.for_grade(self.year, self.grade7))  # nothing applied
        second = GradingScale.objects.get(name="Second")
        with self.assertRaises(IntegrityError), transaction.atomic():
            GradingScaleClassGrade.objects.create(
                scale=second, academic_year=self.year, class_grade=self.grade6
            )
        self.scale("Next year", grades=[self.grade6], year=self.other_year)

    def test_set_class_grades_replaces(self):
        standard = self.scale(grades=[self.grade6])
        standard.set_class_grades([self.grade7])
        self.assertEqual(list(standard.class_grades), [self.grade7])
        self.assertIsNone(GradingScale.for_grade(self.year, self.grade6))

    def test_scale_names_unique_per_year(self):
        self.scale()
        with self.assertRaises(IntegrityError), transaction.atomic():
            GradingScale.objects.create(academic_year=self.year, name="Standard")
        self.scale(year=self.other_year)


class GradingViewTests(GradingFixture, TestCase):
    def setUp(self):
        self.build()
        admin = User.objects.create_user(username="admin", password="pass-12345")
        admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        teacher = User.objects.create_user(username="rao", password="pass-12345")
        teacher.groups.add(Group.objects.get(name="Teachers"))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def test_create_scale_add_and_remove_bands(self):
        response = self.client.post(
            reverse("core:grading-scale-create", args=[self.year.pk]),
            {"name": "Standard", "class_grades": [self.grade6.pk]},
        )
        scale = GradingScale.objects.get()
        detail = reverse("core:grading-scale-detail", args=[scale.pk])
        self.assertRedirects(response, detail)
        self.assertContains(self.client.get(detail), "Add a band starting at 0%")
        add = reverse("core:grade-boundary-create", args=[scale.pk])
        self.client.post(add, {"min_percentage": "50", "label": "Pass"})
        self.client.post(add, {"min_percentage": "0", "label": "Fail"})
        duplicate = self.client.post(add, {"min_percentage": "0", "label": "Again"}, follow=True)
        self.assertContains(duplicate, "already has a band")
        self.assertEqual(scale.grade_for(49), "Fail")
        self.assertNotContains(self.client.get(detail), "Add a band starting at 0%")
        band = scale.boundaries.get(label="Pass")
        remove = reverse("core:grade-boundary-delete", args=[band.pk])
        self.client.get(remove)
        self.assertTrue(scale.boundaries.filter(pk=band.pk).exists())
        self.client.post(remove)
        self.assertFalse(scale.boundaries.filter(pk=band.pk).exists())

    def test_grade_already_using_another_scale_is_refused(self):
        self.scale(grades=[self.grade6])
        response = self.client.post(
            reverse("core:grading-scale-create", args=[self.year.pk]),
            {"name": "Second", "class_grades": [self.grade6.pk]},
        )
        self.assertContains(response, "already uses Standard")
        self.assertEqual(GradingScale.objects.count(), 1)

    def test_edit_scale_name_and_grades(self):
        scale = self.scale(grades=[self.grade6])
        self.client.post(
            reverse("core:grading-scale-update", args=[scale.pk]),
            {"name": "Standard 2026", "class_grades": [self.grade6.pk, self.grade7.pk]},
        )
        scale.refresh_from_db()
        self.assertEqual(scale.name, "Standard 2026")
        self.assertEqual(set(scale.class_grades), {self.grade6, self.grade7})
        listing = self.client.get(
            reverse("core:academic-year-grading-scales", args=[self.year.pk])
        )
        self.assertContains(listing, "Standard 2026")
        self.assertContains(listing, "A1 &ge; 91.00%")

    def test_teacher_cannot_manage_scales(self):
        scale = self.scale()
        band = scale.boundaries.first()
        for url in (
            reverse("core:academic-year-grading-scales", args=[self.year.pk]),
            reverse("core:grading-scale-create", args=[self.year.pk]),
            reverse("core:grading-scale-update", args=[scale.pk]),
            reverse("core:grade-boundary-create", args=[scale.pk]),
            reverse("core:grade-boundary-delete", args=[band.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.teacher.post(url, {"name": "x"}).status_code, 403)
        self.assertEqual(scale.boundaries.count(), len(CBSE_LIKE))
