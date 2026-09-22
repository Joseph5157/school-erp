from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import AcademicYear, ClassGrade, School, Section


class SchoolModelTests(TestCase):
    def test_first_school_can_be_created(self):
        school = School(name="Greenwood High")
        school.full_clean()
        school.save()

        self.assertEqual(School.objects.count(), 1)

    def test_clean_rejects_second_school(self):
        School.objects.create(name="Greenwood High")
        second = School(name="Riverside Academy")

        with self.assertRaises(ValidationError):
            second.full_clean()
        self.assertEqual(School.objects.count(), 1)

    def test_database_rejects_second_school_row(self):
        School.objects.create(name="Greenwood High")

        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="Riverside Academy")
        self.assertEqual(School.objects.count(), 1)

    def test_database_rejects_explicit_non_constant_singleton_id(self):
        # Bypasses clean()/ModelForm entirely (singleton_id is editable=False,
        # so no form can set it -- this simulates direct ORM misuse). Because
        # singleton_id=2 doesn't collide with the existing row's singleton_id=1,
        # only the CheckConstraint (not the unique constraint) can catch this.
        School.objects.create(name="Greenwood High")

        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="Riverside Academy", singleton_id=2)
        self.assertEqual(School.objects.count(), 1)

    def test_database_rejects_non_constant_singleton_id_with_no_existing_row(self):
        # Isolates the CheckConstraint from the unique constraint: this is
        # the very first row, so uniqueness alone would not block it.
        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="Riverside Academy", singleton_id=2)
        self.assertEqual(School.objects.count(), 0)

    def test_existing_school_can_be_updated(self):
        school = School.objects.create(name="Greenwood High")

        school.name = "Greenwood International"
        school.full_clean()
        school.save()

        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(School.objects.get().name, "Greenwood International")


class AcademicYearModelTests(TestCase):
    def test_valid_academic_year_can_be_created(self):
        year = AcademicYear(name="2026-2027", start_date="2026-06-01", end_date="2027-04-30")
        year.full_clean()
        year.save()

        self.assertEqual(AcademicYear.objects.count(), 1)

    def test_clean_rejects_end_date_before_start_date(self):
        year = AcademicYear(name="Invalid", start_date="2026-06-01", end_date="2026-01-01")

        with self.assertRaises(ValidationError):
            year.full_clean()
        self.assertEqual(AcademicYear.objects.count(), 0)

    def test_clean_rejects_equal_dates(self):
        year = AcademicYear(name="Invalid", start_date="2026-06-01", end_date="2026-06-01")

        with self.assertRaises(ValidationError):
            year.full_clean()
        self.assertEqual(AcademicYear.objects.count(), 0)

    def test_database_rejects_end_date_before_start_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicYear.objects.create(
                name="Invalid", start_date="2026-06-01", end_date="2026-01-01"
            )
        self.assertEqual(AcademicYear.objects.count(), 0)


class ClassGradeModelTests(TestCase):
    def test_valid_class_grade_can_be_created(self):
        class_grade = ClassGrade(name="Grade 1")
        class_grade.full_clean()
        class_grade.save()

        self.assertEqual(ClassGrade.objects.count(), 1)

    def test_name_is_required(self):
        class_grade = ClassGrade(name="")

        with self.assertRaises(ValidationError):
            class_grade.full_clean()
        self.assertEqual(ClassGrade.objects.count(), 0)

    def test_duplicate_name_is_rejected(self):
        ClassGrade.objects.create(name="Grade 1")
        duplicate = ClassGrade(name="Grade 1")

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        self.assertEqual(ClassGrade.objects.count(), 1)

    def test_database_rejects_duplicate_name(self):
        ClassGrade.objects.create(name="Grade 1")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassGrade.objects.create(name="Grade 1")
        self.assertEqual(ClassGrade.objects.count(), 1)

    def test_class_grade_with_sections_cannot_be_deleted(self):
        class_grade = ClassGrade.objects.create(name="Grade 1")
        Section.objects.create(class_grade=class_grade, name="A")

        with self.assertRaises(ProtectedError), transaction.atomic():
            class_grade.delete()
        self.assertEqual(ClassGrade.objects.count(), 1)


class SectionModelTests(TestCase):
    def setUp(self):
        self.class_grade = ClassGrade.objects.create(name="Grade 1")

    def test_valid_section_can_be_created(self):
        section = Section(class_grade=self.class_grade, name="A")
        section.full_clean()
        section.save()

        self.assertEqual(Section.objects.count(), 1)

    def test_section_requires_class_grade(self):
        section = Section(name="A")

        with self.assertRaises(ValidationError):
            section.full_clean()
        self.assertEqual(Section.objects.count(), 0)

    def test_database_rejects_section_without_class_grade(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Section.objects.create(name="A")
        self.assertEqual(Section.objects.count(), 0)

    def test_duplicate_name_within_class_grade_is_rejected(self):
        Section.objects.create(class_grade=self.class_grade, name="A")
        duplicate = Section(class_grade=self.class_grade, name="A")

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        self.assertEqual(Section.objects.count(), 1)

    def test_database_rejects_duplicate_name_within_class_grade(self):
        Section.objects.create(class_grade=self.class_grade, name="A")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Section.objects.create(class_grade=self.class_grade, name="A")
        self.assertEqual(Section.objects.count(), 1)

    def test_same_section_name_allowed_in_different_class_grade(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        Section.objects.create(class_grade=self.class_grade, name="A")

        section = Section(class_grade=other_class_grade, name="A")
        section.full_clean()
        section.save()

        self.assertEqual(Section.objects.count(), 2)
