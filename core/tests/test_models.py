from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import (
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    ClassGrade,
    Guardian,
    RelationshipType,
    School,
    Section,
    Student,
    StudentGuardian,
)


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


class GuardianModelTests(TestCase):
    def test_valid_guardian_can_be_created(self):
        guardian = Guardian(full_name="Asha Rao", phone="555-0100", email="asha@example.com")
        guardian.full_clean()
        guardian.save()

        self.assertEqual(Guardian.objects.count(), 1)

    def test_full_name_is_required(self):
        guardian = Guardian(full_name="")

        with self.assertRaises(ValidationError):
            guardian.full_clean()
        self.assertEqual(Guardian.objects.count(), 0)

    def test_str_returns_full_name(self):
        guardian = Guardian.objects.create(full_name="Asha Rao")

        self.assertEqual(str(guardian), "Asha Rao")


class ApplicantModelTests(TestCase):
    def test_valid_applicant_can_be_created(self):
        applicant = Applicant(full_name="Ravi Rao")
        applicant.full_clean()
        applicant.save()

        self.assertEqual(Applicant.objects.count(), 1)

    def test_full_name_is_required(self):
        applicant = Applicant(full_name="")

        with self.assertRaises(ValidationError):
            applicant.full_clean()
        self.assertEqual(Applicant.objects.count(), 0)

    def test_new_applicant_defaults_to_pending(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.PENDING)

    def test_creating_an_applicant_creates_no_guardian_relationship(self):
        Applicant.objects.create(full_name="Ravi Rao")

        self.assertEqual(ApplicantGuardian.objects.count(), 0)

    def test_new_applicant_has_no_decision_timestamp(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        self.assertIsNone(applicant.admission_decided_at)

    def test_pending_applicant_can_be_accepted(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
        self.assertIsNotNone(applicant.admission_decided_at)

    def test_pending_applicant_can_be_rejected(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        applicant.record_admission_decision(Applicant.AdmissionStatus.REJECTED)

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.REJECTED)
        self.assertIsNotNone(applicant.admission_decided_at)

    def test_invalid_decision_is_rejected_without_change(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        with self.assertRaises(ValidationError):
            applicant.record_admission_decision("MAYBE")

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.PENDING)
        self.assertIsNone(applicant.admission_decided_at)

    def test_pending_cannot_be_set_as_a_decision(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")

        with self.assertRaises(ValidationError):
            applicant.record_admission_decision(Applicant.AdmissionStatus.PENDING)

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.PENDING)

    def test_second_decision_is_rejected_without_change(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        decided_at = applicant.admission_decided_at

        with self.assertRaises(ValidationError):
            applicant.record_admission_decision(Applicant.AdmissionStatus.REJECTED)

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
        self.assertEqual(applicant.admission_decided_at, decided_at)

    def test_rejected_decision_cannot_be_reversed_to_accepted(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.REJECTED)

        with self.assertRaises(ValidationError):
            applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.REJECTED)


class ApplicantGuardianModelTests(TestCase):
    def setUp(self):
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao")

    def test_valid_relationship_can_be_created(self):
        link = ApplicantGuardian(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        link.full_clean()
        link.save()

        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_relationship_type_is_required(self):
        link = ApplicantGuardian(applicant=self.applicant, guardian=self.guardian)

        with self.assertRaises(ValidationError):
            link.full_clean()
        self.assertEqual(ApplicantGuardian.objects.count(), 0)

    def test_guardian_is_required(self):
        link = ApplicantGuardian(
            applicant=self.applicant, relationship_type=RelationshipType.MOTHER
        )

        with self.assertRaises(ValidationError):
            link.full_clean()
        self.assertEqual(ApplicantGuardian.objects.count(), 0)

    def test_duplicate_association_is_rejected(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        duplicate = ApplicantGuardian(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.GUARDIAN,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_database_rejects_duplicate_association(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ApplicantGuardian.objects.create(
                applicant=self.applicant,
                guardian=self.guardian,
                relationship_type=RelationshipType.MOTHER,
            )
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_guardian_can_be_reused_across_applicants(self):
        sibling = Applicant.objects.create(full_name="Meera Rao")
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        link = ApplicantGuardian(
            applicant=sibling,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        link.full_clean()
        link.save()

        self.assertEqual(self.guardian.applicant_links.count(), 2)

    def test_guardian_with_relationship_cannot_be_deleted(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.guardian.delete()
        self.assertEqual(Guardian.objects.count(), 1)

    def test_applicant_with_relationship_cannot_be_deleted(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.applicant.delete()
        self.assertEqual(Applicant.objects.count(), 1)


class StudentModelTests(TestCase):
    def setUp(self):
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")

    def test_valid_student_can_be_created(self):
        student = Student(applicant=self.applicant, full_name="Ravi Rao")
        student.full_clean()
        student.save()

        self.assertEqual(Student.objects.count(), 1)

    def test_student_defaults_to_active(self):
        student = Student.objects.create(applicant=self.applicant, full_name="Ravi Rao")

        self.assertEqual(student.status, Student.Status.ACTIVE)

    def test_applicant_requires_a_full_name(self):
        student = Student(applicant=self.applicant, full_name="")

        with self.assertRaises(ValidationError):
            student.full_clean()
        self.assertEqual(Student.objects.count(), 0)

    def test_second_student_for_applicant_is_rejected(self):
        Student.objects.create(applicant=self.applicant, full_name="Ravi Rao")
        duplicate = Student(applicant=self.applicant, full_name="Ravi Rao")

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        self.assertEqual(Student.objects.count(), 1)

    def test_database_rejects_second_student_for_applicant(self):
        Student.objects.create(applicant=self.applicant, full_name="Ravi Rao")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.create(applicant=self.applicant, full_name="Ravi Rao")
        self.assertEqual(Student.objects.count(), 1)

    def test_applicant_with_student_cannot_be_deleted(self):
        Student.objects.create(applicant=self.applicant, full_name="Ravi Rao")

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.applicant.delete()
        self.assertEqual(Applicant.objects.count(), 1)


class ApplicantProgressionTests(TestCase):
    def setUp(self):
        self.applicant = Applicant.objects.create(
            full_name="Ravi Rao",
            date_of_birth="2015-04-01",
            email="ravi@example.com",
            phone="555-0101",
        )

    def _accept(self):
        self.applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

    def test_accepted_applicant_progresses_to_student(self):
        self._accept()

        student = self.applicant.progress_to_student()

        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(student.applicant, self.applicant)

    def test_progression_copies_identity_fields(self):
        self._accept()

        student = self.applicant.progress_to_student()

        self.assertEqual(student.full_name, self.applicant.full_name)
        self.assertEqual(student.date_of_birth, self.applicant.date_of_birth)
        self.assertEqual(student.email, self.applicant.email)
        self.assertEqual(student.phone, self.applicant.phone)

    def test_pending_applicant_cannot_progress(self):
        with self.assertRaises(ValidationError):
            self.applicant.progress_to_student()

        self.assertFalse(Student.objects.exists())

    def test_rejected_applicant_cannot_progress(self):
        self.applicant.record_admission_decision(Applicant.AdmissionStatus.REJECTED)

        with self.assertRaises(ValidationError):
            self.applicant.progress_to_student()

        self.assertFalse(Student.objects.exists())

    def test_repeated_progression_does_not_create_another_student(self):
        self._accept()
        self.applicant.progress_to_student()

        with self.assertRaises(ValidationError):
            self.applicant.progress_to_student()

        self.assertEqual(Student.objects.count(), 1)

    def test_progression_carries_applicant_guardians_to_student(self):
        guardian = Guardian.objects.create(full_name="Asha Rao")
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        self._accept()

        student = self.applicant.progress_to_student()

        link = StudentGuardian.objects.get(student=student)
        self.assertEqual(link.guardian, guardian)
        self.assertEqual(link.relationship_type, RelationshipType.MOTHER)

    def test_progression_preserves_applicant_guardian_history(self):
        guardian = Guardian.objects.create(full_name="Asha Rao")
        applicant_link = ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        self._accept()

        self.applicant.progress_to_student()

        self.assertTrue(ApplicantGuardian.objects.filter(pk=applicant_link.pk).exists())
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_progression_without_guardians_creates_no_student_guardians(self):
        self._accept()

        self.applicant.progress_to_student()

        self.assertEqual(StudentGuardian.objects.count(), 0)

    def test_shared_guardian_is_reused_across_siblings(self):
        guardian = Guardian.objects.create(full_name="Asha Rao")
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        sibling = Applicant.objects.create(full_name="Meera Rao")
        ApplicantGuardian.objects.create(
            applicant=sibling,
            guardian=guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        self._accept()
        sibling.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        self.applicant.progress_to_student()
        sibling.progress_to_student()

        self.assertEqual(Guardian.objects.count(), 1)
        self.assertEqual(guardian.student_links.count(), 2)


class StudentGuardianModelTests(TestCase):
    def setUp(self):
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.student = Student.objects.create(applicant=applicant, full_name="Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao")

    def test_valid_relationship_can_be_created(self):
        link = StudentGuardian(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        link.full_clean()
        link.save()

        self.assertEqual(StudentGuardian.objects.count(), 1)

    def test_relationship_type_is_required(self):
        link = StudentGuardian(student=self.student, guardian=self.guardian)

        with self.assertRaises(ValidationError):
            link.full_clean()
        self.assertEqual(StudentGuardian.objects.count(), 0)

    def test_duplicate_association_is_rejected(self):
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )
        duplicate = StudentGuardian(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.GUARDIAN,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        self.assertEqual(StudentGuardian.objects.count(), 1)

    def test_database_rejects_duplicate_association(self):
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGuardian.objects.create(
                student=self.student,
                guardian=self.guardian,
                relationship_type=RelationshipType.MOTHER,
            )
        self.assertEqual(StudentGuardian.objects.count(), 1)

    def test_guardian_with_relationship_cannot_be_deleted(self):
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.guardian.delete()
        self.assertEqual(Guardian.objects.count(), 1)

    def test_student_with_relationship_cannot_be_deleted(self):
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.student.delete()
        self.assertEqual(Student.objects.count(), 1)
