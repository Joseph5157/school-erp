from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    AttendanceCorrection,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Guardian,
    RelationshipType,
    School,
    Section,
    Student,
    StudentGuardian,
)

User = get_user_model()


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


class AcademicEnrollmentModelTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Ravi Rao"), full_name="Ravi Rao"
        )
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")

    def _enrollment(self, **overrides):
        values = {
            "student": self.student,
            "academic_year": self.year,
            "class_grade": self.class_grade,
            "section": self.section,
        }
        values.update(overrides)
        return AcademicEnrollment(**values)

    def test_valid_enrollment_defaults_to_active(self):
        enrollment = self._enrollment()
        enrollment.full_clean()
        enrollment.save()

        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)

    def test_clean_rejects_section_from_other_class_grade(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        other_section = Section.objects.create(class_grade=other_class_grade, name="A")

        enrollment = self._enrollment(class_grade=self.class_grade, section=other_section)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()
        self.assertEqual(AcademicEnrollment.objects.count(), 0)

    def test_database_rejects_second_active_enrollment_for_student(self):
        self._enrollment().save()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._enrollment().save()
        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_completed_and_active_enrollment_can_coexist(self):
        AcademicEnrollment.objects.create(
            student=self.student,
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            status=AcademicEnrollment.Status.COMPLETED,
        )

        active = self._enrollment()
        active.full_clean()
        active.save()

        self.assertEqual(AcademicEnrollment.objects.count(), 2)

    def test_student_with_enrollment_cannot_be_deleted(self):
        self._enrollment().save()

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.student.delete()
        self.assertEqual(Student.objects.count(), 1)


class StudentEnrollmentTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Ravi Rao"), full_name="Ravi Rao"
        )
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.next_year = AcademicYear.objects.create(
            name="2027-2028", start_date="2027-06-01", end_date="2028-04-30"
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        self.other_section = Section.objects.create(class_grade=self.class_grade, name="B")

    def test_enroll_creates_active_enrollment(self):
        enrollment = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )

        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(self.student.current_enrollment, enrollment)

    def test_new_placement_completes_previous_enrollment(self):
        first = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )

        second = self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.section
        )

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(second.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(self.student.current_enrollment, second)

    def test_previous_enrollment_is_preserved(self):
        first = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )
        self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.section
        )

        self.assertTrue(AcademicEnrollment.objects.filter(pk=first.pk).exists())
        self.assertEqual(AcademicEnrollment.objects.count(), 2)

    def test_history_accumulates_multiple_completed_enrollments(self):
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )
        self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.other_section
        )

        self.assertEqual(
            AcademicEnrollment.objects.filter(status=AcademicEnrollment.Status.COMPLETED).count(), 1
        )
        self.assertEqual(
            AcademicEnrollment.objects.filter(status=AcademicEnrollment.Status.ACTIVE).count(), 1
        )

    def test_incompatible_section_is_rejected(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        other_section = Section.objects.create(class_grade=other_class_grade, name="A")

        with self.assertRaises(ValidationError):
            self.student.enroll(
                academic_year=self.year,
                class_grade=self.class_grade,
                section=other_section,
            )

        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_duplicate_active_placement_is_rejected(self):
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )

        with self.assertRaises(ValidationError):
            self.student.enroll(
                academic_year=self.year, class_grade=self.class_grade, section=self.section
            )

        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_current_enrollment_is_none_without_enrollment(self):
        self.assertIsNone(self.student.current_enrollment)


class StudentStatusTests(TestCase):
    def setUp(self):
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = self.applicant.progress_to_student()

    def test_new_student_defaults_to_active(self):
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        self.assertIsNone(self.student.status_changed_at)

    def test_deactivate_records_inactive_and_timestamp(self):
        self.student.record_status_change(Student.Status.INACTIVE)

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)
        self.assertIsNotNone(self.student.status_changed_at)

    def test_reactivate_returns_student_to_active(self):
        self.student.record_status_change(Student.Status.INACTIVE)

        self.student.record_status_change(Student.Status.ACTIVE)

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.student.record_status_change("GRADUATED")

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_repeat_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.student.record_status_change(Student.Status.ACTIVE)

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        self.assertIsNone(self.student.status_changed_at)

    def test_status_change_does_not_alter_enrollment_history(self):
        year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        class_grade = ClassGrade.objects.create(name="Grade 1")
        section = Section.objects.create(class_grade=class_grade, name="A")
        enrollment = self.student.enroll(
            academic_year=year, class_grade=class_grade, section=section
        )

        self.student.record_status_change(Student.Status.INACTIVE)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(self.student.current_enrollment, enrollment)

    def test_status_change_preserves_source_applicant(self):
        self.student.record_status_change(Student.Status.INACTIVE)

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
        self.assertEqual(self.student.applicant, self.applicant)


class AttendanceFixtureMixin:
    def build_attendance_fixture(self):
        # Date objects (not strings) so the in-memory AcademicYear dates can be
        # compared against the register date by AttendanceRegister.clean().
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Ravi Rao"), full_name="Ravi Rao"
        )
        self.enrollment = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-07-01",
        )


class AttendanceRegisterModelTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()

    def test_valid_register_can_be_created(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-08-01",
        )
        register.full_clean()
        register.save()

        self.assertEqual(AttendanceRegister.objects.count(), 2)

    def test_clean_rejects_section_from_other_class_grade(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        other_section = Section.objects.create(class_grade=other_class_grade, name="A")

        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=other_section,
            date="2026-08-01",
        )

        with self.assertRaises(ValidationError):
            register.full_clean()
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_clean_rejects_date_before_academic_year(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-05-01",
        )

        with self.assertRaises(ValidationError):
            register.full_clean()
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_clean_rejects_date_after_academic_year(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2027-05-01",
        )

        with self.assertRaises(ValidationError):
            register.full_clean()
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_database_rejects_duplicate_register(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRegister.objects.create(
                academic_year=self.year,
                class_grade=self.class_grade,
                section=self.section,
                date="2026-07-01",
            )
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_database_rejects_same_section_and_date_in_overlapping_academic_year(self):
        overlapping_year = AcademicYear.objects.create(
            name="Overlapping session", start_date="2026-06-01", end_date="2027-04-30"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRegister.objects.create(
                academic_year=overlapping_year,
                class_grade=self.class_grade,
                section=self.section,
                date="2026-07-01",
            )
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_eligible_enrollments_includes_current_placement(self):
        self.assertEqual(list(self.register.eligible_enrollments()), [self.enrollment])

    def test_eligible_enrollments_excludes_other_section(self):
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        other_student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        other_student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section
        )

        self.assertEqual(list(self.register.eligible_enrollments()), [self.enrollment])

    def test_capture_creates_entry(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertEqual(entry.academic_enrollment, self.enrollment)
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_capture_rejects_unknown_status(self):
        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=self.enrollment, status="HOLIDAY")

        self.assertEqual(AttendanceEntry.objects.count(), 0)

    def test_capture_rejects_enrollment_from_other_section(self):
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        other_student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        other_enrollment = other_student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section
        )

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=other_enrollment, status=AttendanceStatus.PRESENT)

        self.assertEqual(AttendanceEntry.objects.count(), 0)

    def test_capture_rejects_completed_enrollment(self):
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section
        )
        self.enrollment.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        self.assertEqual(self.enrollment.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(AttendanceEntry.objects.count(), 0)

    def test_capture_rejects_duplicate_entry(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_register_with_entries_cannot_be_deleted(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.register.delete()
        self.assertEqual(AttendanceRegister.objects.count(), 1)


class AttendanceEntryModelTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def test_entry_defaults_to_present(self):
        entry = AttendanceEntry.objects.create(
            register=self.register, academic_enrollment=self.enrollment
        )

        self.assertEqual(entry.status, AttendanceStatus.PRESENT)

    def test_clean_rejects_enrollment_from_other_section(self):
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        other_student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        other_enrollment = other_student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section
        )

        entry = AttendanceEntry(register=self.register, academic_enrollment=other_enrollment)

        with self.assertRaises(ValidationError):
            entry.full_clean()
        self.assertEqual(AttendanceEntry.objects.count(), 0)

    def test_database_rejects_duplicate_entry(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceEntry.objects.create(
                register=self.register,
                academic_enrollment=self.enrollment,
                status=AttendanceStatus.ABSENT,
            )
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_correction_records_history_and_updates_status(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Guardian reported illness."
        )

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.ABSENT)
        correction = AttendanceCorrection.objects.get()
        self.assertEqual(correction.previous_status, AttendanceStatus.PRESENT)
        self.assertEqual(correction.new_status, AttendanceStatus.ABSENT)
        self.assertEqual(correction.reason, "Guardian reported illness.")
        self.assertEqual(correction.corrected_by, self.actor)

    def test_correction_history_is_preserved_across_changes(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Marked absent."
        )
        entry.record_status_change(
            AttendanceStatus.LATE, actor=self.actor, reason="Arrived later."
        )

        self.assertEqual(entry.corrections.count(), 2)
        statuses = set(
            entry.corrections.values_list("previous_status", "new_status")
        )
        self.assertIn((AttendanceStatus.PRESENT, AttendanceStatus.ABSENT), statuses)
        self.assertIn((AttendanceStatus.ABSENT, AttendanceStatus.LATE), statuses)

    def test_invalid_status_is_rejected_without_change(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        with self.assertRaises(ValidationError):
            entry.record_status_change("HOLIDAY", actor=self.actor, reason="Typo.")

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_repeat_status_is_rejected_without_change(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        with self.assertRaises(ValidationError):
            entry.record_status_change(
                AttendanceStatus.PRESENT, actor=self.actor, reason="No change."
            )

        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_missing_reason_is_rejected_without_change(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        with self.assertRaises(ValidationError):
            entry.record_status_change(AttendanceStatus.ABSENT, actor=self.actor, reason="  ")

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_missing_actor_is_rejected_without_change(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        with self.assertRaises(ValidationError):
            entry.record_status_change(AttendanceStatus.ABSENT, actor=None, reason="Ill.")

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_entry_with_correction_cannot_be_deleted(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Ill."
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            entry.delete()
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_correcting_user_with_correction_cannot_be_deleted(self):
        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Ill."
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.actor.delete()
        self.assertEqual(User.objects.filter(pk=self.actor.pk).count(), 1)
