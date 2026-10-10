from datetime import UTC, date, datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

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
    SchoolCalendarDay,
    Section,
    Student,
    StudentGuardian,
    business_today,
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
            "start_date": date(2026, 6, 1),
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
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        active = self._enrollment(start_date=date(2026, 7, 1))
        active.full_clean()
        active.save()

        self.assertEqual(AcademicEnrollment.objects.count(), 2)

    def test_student_with_enrollment_cannot_be_deleted(self):
        self._enrollment().save()

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.student.delete()
        self.assertEqual(Student.objects.count(), 1)


class BusinessDateTimezoneTests(TestCase):
    """Business dates follow the school's configured timezone, not UTC."""

    # 2026-07-01 19:00 UTC is already 2026-07-02 00:30 in Asia/Kolkata.
    NOW_UTC = datetime(2026, 7, 1, 19, 0, tzinfo=UTC)

    def setUp(self):
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Ravi Rao"), full_name="Ravi Rao"
        )
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")

    def test_project_timezone_is_school_local(self):
        from django.conf import settings

        self.assertEqual(settings.TIME_ZONE, "Asia/Kolkata")
        self.assertTrue(settings.USE_TZ)

    def test_business_today_uses_school_timezone_after_ist_midnight(self):
        with mock.patch("django.utils.timezone.now", return_value=self.NOW_UTC):
            self.assertEqual(business_today(), date(2026, 7, 2))

    @override_settings(TIME_ZONE="UTC")
    def test_business_today_is_driven_by_configured_timezone(self):
        with mock.patch("django.utils.timezone.now", return_value=self.NOW_UTC):
            self.assertEqual(business_today(), date(2026, 7, 1))

    def test_same_day_ist_enrollment_allowed_just_after_midnight(self):
        with mock.patch("django.utils.timezone.now", return_value=self.NOW_UTC):
            enrollment = self.student.enroll(
                academic_year=self.year,
                class_grade=self.class_grade,
                section=self.section,
                start_date=date(2026, 7, 2),
            )

        self.assertEqual(enrollment.start_date, date(2026, 7, 2))

    def test_next_ist_day_still_rejected_as_future(self):
        with mock.patch("django.utils.timezone.now", return_value=self.NOW_UTC):
            with self.assertRaises(ValidationError):
                self.student.enroll(
                    academic_year=self.year,
                    class_grade=self.class_grade,
                    section=self.section,
                    start_date=date(2026, 7, 3),
                )

        self.assertFalse(AcademicEnrollment.objects.exists())


# Fixtures below enroll into the 2027-2028 year; pin "today" after those dates
# so the operational no-future-start rule does not make results clock-dependent.
PINNED_TODAY = date(2027, 12, 31)


@mock.patch("core.models.business_today", new=lambda: PINNED_TODAY)
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
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )

        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(self.student.current_enrollment, enrollment)

    def test_new_placement_completes_previous_enrollment(self):
        first = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )

        second = self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.section,
            start_date=date(2027, 6, 1),
        )

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(second.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(self.student.current_enrollment, second)

    def test_previous_enrollment_is_preserved(self):
        first = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )
        self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.section,
            start_date=date(2027, 6, 1),
        )

        self.assertTrue(AcademicEnrollment.objects.filter(pk=first.pk).exists())
        self.assertEqual(AcademicEnrollment.objects.count(), 2)

    def test_history_accumulates_multiple_completed_enrollments(self):
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )
        self.student.enroll(
            academic_year=self.next_year, class_grade=self.class_grade, section=self.other_section,
            start_date=date(2027, 6, 1),
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
                start_date=date(2026, 6, 1),
            )

        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_duplicate_active_placement_is_rejected(self):
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )

        with self.assertRaises(ValidationError):
            self.student.enroll(
                academic_year=self.year, class_grade=self.class_grade, section=self.section,
                start_date=date(2026, 6, 1),
            )

        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_current_enrollment_is_none_without_enrollment(self):
        self.assertIsNone(self.student.current_enrollment)


@mock.patch("core.models.business_today", new=lambda: PINNED_TODAY)
class AcademicEnrollmentEffectiveDatingTests(TestCase):
    """Gate 1 effective dating (docs/adr/0006-academic-enrollment-effective-dating.md)."""

    def setUp(self):
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Ravi Rao"), full_name="Ravi Rao"
        )
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.next_year = AcademicYear.objects.create(
            name="2027-2028", start_date=date(2027, 6, 1), end_date=date(2028, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section_a = Section.objects.create(class_grade=self.class_grade, name="A")
        self.section_b = Section.objects.create(class_grade=self.class_grade, name="B")

    def _enrollment(self, **overrides):
        values = {
            "student": self.student,
            "academic_year": self.year,
            "class_grade": self.class_grade,
            "section": self.section_a,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return AcademicEnrollment(**values)

    def _enroll(self, section, start_date, year=None):
        return self.student.enroll(
            academic_year=year or self.year,
            class_grade=self.class_grade,
            section=section,
            start_date=start_date,
        )

    # --- model validation -------------------------------------------------

    def test_valid_active_dated_enrollment(self):
        enrollment = self._enrollment()
        enrollment.full_clean()
        enrollment.save()

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.start_date, date(2026, 6, 1))
        self.assertIsNone(enrollment.end_date)

    def test_start_date_is_required(self):
        with self.assertRaises(ValidationError) as ctx:
            self._enrollment(start_date=None).full_clean()
        self.assertIn("start_date", ctx.exception.message_dict)

    def test_active_with_end_date_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._enrollment(end_date=date(2026, 7, 1)).full_clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_completed_without_end_date_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._enrollment(status=AcademicEnrollment.Status.COMPLETED).full_clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_end_before_start_rejected(self):
        enrollment = self._enrollment(
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 6, 30),
        )
        with self.assertRaises(ValidationError) as ctx:
            enrollment.full_clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_single_day_completed_enrollment_allowed(self):
        enrollment = self._enrollment(
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
        enrollment.full_clean()
        enrollment.save()

    def test_start_date_outside_academic_year_rejected(self):
        for start in (date(2026, 5, 31), date(2027, 5, 1)):
            with self.subTest(start=start), self.assertRaises(ValidationError) as ctx:
                self._enrollment(start_date=start).full_clean()
            self.assertIn("start_date", ctx.exception.message_dict)

    def test_overlapping_periods_rejected(self):
        self._enrollment(
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 7, 31),
        ).save()

        for start in (date(2026, 6, 1), date(2026, 7, 15), date(2026, 7, 31)):
            with self.subTest(start=start), self.assertRaises(ValidationError):
                self._enrollment(section=self.section_b, start_date=start).full_clean()

    def test_overlap_with_open_ended_active_rejected(self):
        self._enrollment(start_date=date(2026, 8, 1)).save()

        later_completed = self._enrollment(
            section=self.section_b,
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        with self.assertRaises(ValidationError):
            later_completed.full_clean()

    def test_non_overlapping_historical_and_active_allowed(self):
        self._enrollment(
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 7, 31),
        ).save()

        active = self._enrollment(section=self.section_b, start_date=date(2026, 8, 1))
        active.full_clean()
        active.save()

        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 2)

    def test_other_students_periods_do_not_conflict(self):
        self._enrollment().save()
        other = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        enrollment = self._enrollment(student=other)
        enrollment.full_clean()
        enrollment.save()

    # --- database constraints (bypassing clean) --------------------------

    def test_database_rejects_active_with_end_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._enrollment(end_date=date(2026, 7, 1)).save()
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_database_rejects_completed_without_end_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._enrollment(status=AcademicEnrollment.Status.COMPLETED).save()
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_database_rejects_end_before_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._enrollment(
                status=AcademicEnrollment.Status.COMPLETED,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 6, 30),
            ).save()
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_database_rejects_missing_start_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._enrollment(start_date=None).save()
        self.assertFalse(AcademicEnrollment.objects.exists())

    # --- effective-date lookup -------------------------------------------

    def test_effective_on_exact_boundaries(self):
        completed = self._enrollment(
            status=AcademicEnrollment.Status.COMPLETED,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 7, 31),
        )
        completed.save()
        active = self._enrollment(section=self.section_b, start_date=date(2026, 8, 1))
        active.save()

        expectations = {
            date(2026, 5, 31): None,
            date(2026, 6, 1): completed,
            date(2026, 7, 31): completed,
            date(2026, 8, 1): active,
            date(2030, 1, 1): active,
        }
        for on_date, expected in expectations.items():
            with self.subTest(on_date=on_date):
                self.assertEqual(self.student.enrollment_on(on_date), expected)
                self.assertEqual(
                    list(AcademicEnrollment.objects.effective_on(on_date)),
                    [expected] if expected else [],
                )
        self.assertTrue(completed.is_effective_on(date(2026, 7, 31)))
        self.assertFalse(completed.is_effective_on(date(2026, 8, 1)))
        self.assertTrue(active.is_effective_on("2026-08-01"))

    # --- enroll / transfer workflow --------------------------------------

    def test_enroll_requires_start_date(self):
        with self.assertRaises(ValidationError):
            self._enroll(self.section_a, None)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_enroll_records_explicit_start_date(self):
        enrollment = self._enroll(self.section_a, date(2026, 6, 15))

        self.assertEqual(enrollment.start_date, date(2026, 6, 15))
        self.assertIsNone(enrollment.end_date)
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)

    def test_enroll_rejects_start_outside_academic_year(self):
        with self.assertRaises(ValidationError):
            self._enroll(self.section_a, date(2026, 5, 1))
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_transfer_closes_previous_enrollment_on_day_before(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))

        second = self._enroll(self.section_b, date(2026, 9, 15))

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(first.start_date, date(2026, 6, 1))
        self.assertEqual(first.end_date, date(2026, 9, 14))
        self.assertEqual(first.section, self.section_a)
        self.assertEqual(second.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(second.start_date, date(2026, 9, 15))
        self.assertIsNone(second.end_date)
        self.assertEqual(self.student.current_enrollment, second)

    def test_transfer_on_day_after_start_produces_single_day_history(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))
        self._enroll(self.section_b, date(2026, 6, 2))

        first.refresh_from_db()
        self.assertEqual(first.end_date, date(2026, 6, 1))

    def test_historical_lookup_before_and_after_transfer(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))
        second = self._enroll(self.section_b, date(2026, 9, 15))

        self.assertEqual(self.student.enrollment_on(date(2026, 7, 1)), first)
        self.assertEqual(self.student.enrollment_on(date(2026, 7, 1)).section, self.section_a)
        self.assertEqual(self.student.enrollment_on(date(2026, 9, 14)), first)
        self.assertEqual(self.student.enrollment_on(date(2026, 9, 15)), second)
        self.assertEqual(self.student.enrollment_on(date(2026, 12, 1)).section, self.section_b)
        self.assertIsNone(self.student.enrollment_on(date(2026, 5, 31)))

    def test_transfer_on_or_before_current_start_rejected_without_change(self):
        first = self._enroll(self.section_a, date(2026, 8, 1))

        for start in (date(2026, 8, 1), date(2026, 7, 1)):
            with self.subTest(start=start), self.assertRaises(ValidationError):
                self._enroll(self.section_b, start)

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.ACTIVE)
        self.assertIsNone(first.end_date)
        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_invalid_new_placement_leaves_current_enrollment_untouched(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))

        # Start date falls outside the next Academic Year: the new enrollment
        # fails validation, so closing the current one must roll back.
        with self.assertRaises(ValidationError):
            self._enroll(self.section_a, date(2027, 5, 1), year=self.next_year)

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.ACTIVE)
        self.assertIsNone(first.end_date)
        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_cross_year_progression_keeps_dated_history(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))
        second = self._enroll(self.section_a, date(2027, 6, 1), year=self.next_year)

        first.refresh_from_db()
        self.assertEqual(first.end_date, date(2027, 5, 31))
        self.assertEqual(self.student.enrollment_on(date(2027, 4, 30)), first)
        self.assertEqual(self.student.enrollment_on(date(2027, 6, 1)), second)

    # --- operational no-future-start rule ---------------------------------

    def test_future_initial_enrollment_rejected(self):
        with mock.patch("core.models.business_today", new=lambda: date(2026, 7, 1)):
            with self.assertRaises(ValidationError):
                self._enroll(self.section_a, date(2026, 7, 2))

        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_enrollment_starting_today_allowed(self):
        with mock.patch("core.models.business_today", new=lambda: date(2026, 7, 1)):
            enrollment = self._enroll(self.section_a, date(2026, 7, 1))

        self.assertEqual(enrollment.start_date, date(2026, 7, 1))
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)

    def test_future_transfer_rejected_without_changing_history(self):
        first = self._enroll(self.section_a, date(2026, 6, 1))

        with mock.patch("core.models.business_today", new=lambda: date(2026, 9, 1)):
            with self.assertRaises(ValidationError):
                self._enroll(self.section_b, date(2026, 9, 2))

        first.refresh_from_db()
        self.assertEqual(first.status, AcademicEnrollment.Status.ACTIVE)
        self.assertIsNone(first.end_date)
        self.assertEqual(first.section, self.section_a)
        self.assertEqual(AcademicEnrollment.objects.count(), 1)
        self.assertEqual(self.student.current_enrollment, first)

    def test_enroll_accepts_iso_string_start_date(self):
        enrollment = self._enroll(self.section_a, "2026-06-10")

        self.assertEqual(enrollment.start_date, date(2026, 6, 10))


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
            academic_year=year, class_grade=class_grade, section=section,
            start_date=date(2026, 6, 1),
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


class SchoolCalendarTests(TestCase):
    """Gate 2 minimal school calendar (docs/adr/0008-phase-2-school-calendar-rules.md)."""

    MONDAY = date(2026, 8, 17)
    WEDNESDAY = date(2026, 7, 1)
    SATURDAY = date(2026, 8, 22)
    SUNDAY = date(2026, 8, 23)

    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")

    def _day(self, on_date, is_instructional, **overrides):
        values = {
            "academic_year": self.year,
            "date": on_date,
            "is_instructional": is_instructional,
        }
        values.update(overrides)
        return SchoolCalendarDay(**values)

    def _register(self, on_date):
        return AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date=on_date,
        )

    # --- weekly pattern ---------------------------------------------------

    def test_weekday_is_instructional_by_default(self):
        self.assertTrue(self.year.is_instructional_day(self.MONDAY))
        self.assertTrue(self.year.is_instructional_day(self.WEDNESDAY))

    def test_sunday_is_not_instructional(self):
        self.assertFalse(self.year.is_instructional_day(self.SUNDAY))

    def test_saturday_off_by_default(self):
        self.assertFalse(self.year.saturdays_instructional)
        self.assertFalse(self.year.is_instructional_day(self.SATURDAY))

    def test_saturday_instructional_when_year_says_so(self):
        year = AcademicYear.objects.create(
            name="Six-day year",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 4, 30),
            saturdays_instructional=True,
        )
        self.assertTrue(year.is_instructional_day(self.SATURDAY))
        self.assertFalse(year.is_instructional_day(self.SUNDAY))

    def test_dates_outside_year_are_not_instructional(self):
        self.assertFalse(self.year.is_instructional_day(date(2026, 5, 29)))
        self.assertFalse(self.year.is_instructional_day(date(2027, 5, 3)))

    def test_year_boundaries_are_inclusive(self):
        self.assertTrue(self.year.is_instructional_day(date(2026, 6, 1)))  # Monday
        self.assertTrue(self.year.is_instructional_day(date(2027, 4, 30)))  # Friday

    def test_lookup_accepts_iso_string(self):
        self.assertTrue(self.year.is_instructional_day("2026-08-17"))

    # --- exceptions -------------------------------------------------------

    def test_holiday_exception_makes_weekday_non_instructional(self):
        day = self._day(self.MONDAY, False, label="Closure")
        day.full_clean()
        day.save()

        self.assertFalse(self.year.is_instructional_day(self.MONDAY))

    def test_working_saturday_exception_is_instructional(self):
        day = self._day(self.SATURDAY, True, label="Working Saturday")
        day.full_clean()
        day.save()

        self.assertTrue(self.year.is_instructional_day(self.SATURDAY))
        self.assertFalse(self.year.is_instructional_day(date(2026, 8, 29)))

    def test_working_sunday_exception_is_instructional(self):
        day = self._day(self.SUNDAY, True)
        day.full_clean()
        day.save()

        self.assertTrue(self.year.is_instructional_day(self.SUNDAY))

    def test_exception_matching_weekly_pattern_rejected(self):
        for on_date, is_instructional in (
            (self.MONDAY, True),
            (self.SATURDAY, False),
            (self.SUNDAY, False),
        ):
            with self.subTest(on_date=on_date), self.assertRaises(ValidationError):
                self._day(on_date, is_instructional).full_clean()
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_exception_outside_academic_year_rejected(self):
        for on_date in (date(2026, 5, 29), date(2027, 5, 3)):
            with self.subTest(on_date=on_date), self.assertRaises(ValidationError) as ctx:
                self._day(on_date, False).full_clean()
            self.assertIn("date", ctx.exception.message_dict)

    def test_duplicate_year_and_date_rejected(self):
        self._day(self.MONDAY, False).save()

        with self.assertRaises(ValidationError):
            self._day(self.MONDAY, False, label="again").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._day(self.MONDAY, False, label="again").save()
        self.assertEqual(SchoolCalendarDay.objects.count(), 1)

    def test_same_date_allowed_in_another_academic_year(self):
        self._day(self.MONDAY, False).save()
        other = AcademicYear.objects.create(
            name="Overlapping session", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )

        day = self._day(self.MONDAY, False, academic_year=other)
        day.full_clean()
        day.save()

        self.assertTrue(self.year.calendar_days.filter(date=self.MONDAY).exists())
        self.assertTrue(other.calendar_days.filter(date=self.MONDAY).exists())

    def test_label_can_change_but_date_and_type_cannot(self):
        day = self._day(self.MONDAY, False, label="Closure")
        day.save()

        day.label = "Heavy rain closure"
        day.full_clean()
        day.save()

        for field, value in (("date", date(2026, 8, 18)), ("is_instructional", True)):
            with self.subTest(field=field):
                fresh = SchoolCalendarDay.objects.get(pk=day.pk)
                setattr(fresh, field, value)
                with self.assertRaises(ValidationError):
                    fresh.full_clean()

    # --- attendance protection --------------------------------------------

    def test_holiday_rejected_when_attendance_exists_on_date(self):
        self._register(self.WEDNESDAY)

        with self.assertRaises(ValidationError) as ctx:
            self._day(self.WEDNESDAY, False).full_clean()
        self.assertIn("date", ctx.exception.message_dict)
        self.assertTrue(self.year.is_instructional_day(self.WEDNESDAY))

    def test_holiday_allowed_when_attendance_only_in_other_year(self):
        other = AcademicYear.objects.create(
            name="Overlapping session", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        AttendanceRegister.objects.create(
            academic_year=other,
            class_grade=self.class_grade,
            section=self.section,
            date=self.WEDNESDAY,
        )

        day = self._day(self.WEDNESDAY, False)
        day.full_clean()
        day.save()

    def test_exception_can_be_deleted_without_attendance(self):
        day = self._day(self.MONDAY, False)
        day.save()

        day.delete()

        self.assertFalse(SchoolCalendarDay.objects.exists())
        self.assertTrue(self.year.is_instructional_day(self.MONDAY))

    def test_exception_cannot_be_deleted_when_attendance_exists(self):
        day = self._day(self.SATURDAY, True, label="Working Saturday")
        day.save()
        self._register(self.SATURDAY)

        with self.assertRaises(ValidationError):
            day.delete()

        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())
        self.assertTrue(self.year.is_instructional_day(self.SATURDAY))

    def test_academic_year_with_calendar_days_cannot_be_deleted(self):
        self._day(self.MONDAY, False).save()

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.year.delete()

    # --- Saturday rule ----------------------------------------------------

    def test_saturday_rule_can_change_before_attendance(self):
        self.year.set_saturdays_instructional(True)

        self.year.refresh_from_db()
        self.assertTrue(self.year.saturdays_instructional)
        self.assertTrue(self.year.is_instructional_day(self.SATURDAY))

    def test_saturday_rule_no_op_rejected(self):
        with self.assertRaises(ValidationError):
            self.year.set_saturdays_instructional(False)

    def test_saturday_rule_locked_once_attendance_exists(self):
        self._register(self.WEDNESDAY)

        with self.assertRaises(ValidationError):
            self.year.set_saturdays_instructional(True)

        self.year.refresh_from_db()
        self.assertFalse(self.year.saturdays_instructional)

    def test_saturday_rule_blocked_by_saturday_exceptions(self):
        self._day(self.SATURDAY, True).save()

        with self.assertRaises(ValidationError):
            self.year.set_saturdays_instructional(True)

        self.year.refresh_from_db()
        self.assertFalse(self.year.saturdays_instructional)

    def test_saturday_rule_not_blocked_by_weekday_exceptions(self):
        self._day(self.MONDAY, False).save()

        self.year.set_saturdays_instructional(True)

        self.year.refresh_from_db()
        self.assertTrue(self.year.saturdays_instructional)


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
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date=date(2026, 6, 1),
        )
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-07-01",
        )

    def capture_and_submit(self, *, enrollment, status, absence_note=""):
        """Capture the fixture roster's single entry and submit the register.

        Gate 6: corrections apply only to SUBMITTED attendance.
        """
        entry = self.register.capture(
            enrollment=enrollment, status=status, absence_note=absence_note
        )
        submitter, _ = User.objects.get_or_create(username="register-submitter")
        self.register.submit(actor=submitter)
        return entry


class AttendanceRegisterModelTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()

    def test_valid_register_can_be_created(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-08-03",  # Monday; 2026-08-01 is a non-instructional Saturday
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
            academic_year=self.year, class_grade=self.class_grade, section=other_section,
            start_date=date(2026, 6, 1),
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
            academic_year=self.year, class_grade=self.class_grade, section=other_section,
            start_date=date(2026, 6, 1),
        )

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=other_enrollment, status=AttendanceStatus.PRESENT)

        self.assertEqual(AttendanceEntry.objects.count(), 0)

    def test_capture_accepts_historical_enrollment_effective_on_register_date(self):
        # Gate 3 (ADR 0006/0007): validity follows the date-effective
        # enrollment, so a later transfer does not invalidate earlier dates.
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section,
            start_date=date(2026, 8, 1),
        )
        self.enrollment.refresh_from_db()

        entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        self.assertEqual(self.enrollment.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(entry.academic_enrollment, self.enrollment)

    def test_capture_rejects_completed_enrollment_not_effective_on_date(self):
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")
        self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=other_section,
            start_date=date(2026, 7, 1),
        )
        self.enrollment.refresh_from_db()
        later_register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-07-02",
        )

        with self.assertRaises(ValidationError):
            later_register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

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
            academic_year=self.year, class_grade=self.class_grade, section=other_section,
            start_date=date(2026, 6, 1),
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
        entry = self.capture_and_submit(
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
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Marked absent."
        )
        entry.record_status_change(
            AttendanceStatus.PRESENT, actor=self.actor, reason="Arrived after roll call."
        )

        self.assertEqual(entry.corrections.count(), 2)
        statuses = set(
            entry.corrections.values_list("previous_status", "new_status")
        )
        self.assertIn((AttendanceStatus.PRESENT, AttendanceStatus.ABSENT), statuses)
        self.assertIn((AttendanceStatus.ABSENT, AttendanceStatus.PRESENT), statuses)

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
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Ill."
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            entry.delete()
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_correcting_user_with_correction_cannot_be_deleted(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Ill."
        )

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.actor.delete()
        self.assertEqual(User.objects.filter(pk=self.actor.pk).count(), 1)


class AttendanceGate3StatusTests(AttendanceFixtureMixin, TestCase):
    """Gate 3: PRESENT/ABSENT only (docs/adr/0007-phase-2-attendance-model.md)."""

    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def test_choices_are_exactly_present_and_absent(self):
        self.assertEqual(AttendanceStatus.values, ["PRESENT", "ABSENT"])
        self.assertEqual(
            [value for value, _ in AttendanceEntry._meta.get_field("status").choices],
            ["PRESENT", "ABSENT"],
        )
        for field in ("previous_status", "new_status"):
            with self.subTest(field=field):
                self.assertEqual(
                    [v for v, _ in AttendanceCorrection._meta.get_field(field).choices],
                    ["PRESENT", "ABSENT"],
                )

    def test_late_and_excused_are_unavailable(self):
        self.assertFalse(hasattr(AttendanceStatus, "LATE"))
        self.assertFalse(hasattr(AttendanceStatus, "EXCUSED"))
        for legacy in ("LATE", "EXCUSED"):
            with self.subTest(status=legacy), self.assertRaises(ValidationError):
                self.register.capture(enrollment=self.enrollment, status=legacy)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_correction_to_legacy_status_rejected(self):
        entry = self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        for legacy in ("LATE", "EXCUSED"):
            with self.subTest(status=legacy), self.assertRaises(ValidationError):
                entry.record_status_change(legacy, actor=self.actor, reason="Legacy.")
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_entry_full_clean_rejects_invalid_status(self):
        entry = AttendanceEntry(
            register=self.register, academic_enrollment=self.enrollment, status="LATE"
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn("status", ctx.exception.message_dict)

    def test_database_rejects_legacy_entry_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceEntry.objects.create(
                register=self.register, academic_enrollment=self.enrollment, status="LATE"
            )
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_database_rejects_legacy_correction_status(self):
        entry = self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        for previous, new in (("EXCUSED", "PRESENT"), ("PRESENT", "LATE")):
            with self.subTest(previous=previous, new=new):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    AttendanceCorrection.objects.create(
                        entry=entry,
                        previous_status=previous,
                        new_status=new,
                        reason="Direct write.",
                        corrected_by=self.actor,
                    )
        self.assertFalse(AttendanceCorrection.objects.exists())


class AttendanceGate3AbsenceNoteTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def test_absent_may_have_note(self):
        entry = self.register.capture(
            enrollment=self.enrollment,
            status=AttendanceStatus.ABSENT,
            absence_note="  Fever, guardian called.  ",
        )

        entry.refresh_from_db()
        self.assertEqual(entry.absence_note, "Fever, guardian called.")

    def test_absent_note_is_optional(self):
        entry = self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        self.assertEqual(entry.absence_note, "")

    def test_present_cannot_have_note(self):
        with self.assertRaises(ValidationError):
            self.register.capture(
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
                absence_note="Should not be here.",
            )
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_database_rejects_present_with_note(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceEntry.objects.create(
                register=self.register,
                academic_enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
                absence_note="Direct write.",
            )
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_correcting_absent_to_present_clears_note(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.ABSENT, absence_note="Fever."
        )

        entry.record_status_change(
            AttendanceStatus.PRESENT, actor=self.actor, reason="Arrived after roll call."
        )

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertEqual(entry.absence_note, "")
        correction = entry.corrections.get()
        self.assertEqual(correction.previous_status, AttendanceStatus.ABSENT)
        self.assertEqual(correction.new_status, AttendanceStatus.PRESENT)

    def test_correcting_present_to_absent_works_without_note(self):
        entry = self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        entry.record_status_change(AttendanceStatus.ABSENT, actor=self.actor, reason="Left early.")

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.ABSENT)
        self.assertEqual(entry.absence_note, "")


class AttendanceGate3RegisterLifecycleTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def test_new_register_defaults_to_draft_with_empty_submission_fields(self):
        self.register.refresh_from_db()

        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)
        self.assertIsNone(self.register.submitted_by)
        self.assertIsNone(self.register.submitted_at)

    def test_lifecycle_states_are_exactly_draft_and_submitted(self):
        self.assertEqual(AttendanceRegister.Status.values, ["DRAFT", "SUBMITTED"])

    def test_clean_rejects_new_register_created_as_submitted(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=Section.objects.create(class_grade=self.class_grade, name="B"),
            date=date(2026, 7, 1),
            status=AttendanceRegister.Status.SUBMITTED,
            submitted_by=self.actor,
            submitted_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            register.full_clean()

    def test_database_rejects_draft_with_submission_data(self):
        for fields in (
            {"submitted_by": self.actor},
            {"submitted_at": timezone.now()},
            {"submitted_by": self.actor, "submitted_at": timezone.now()},
        ):
            with self.subTest(fields=list(fields)):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    AttendanceRegister.objects.filter(pk=self.register.pk).update(**fields)
        self.register.refresh_from_db()
        self.assertIsNone(self.register.submitted_by)
        self.assertIsNone(self.register.submitted_at)

    def test_database_rejects_submitted_without_submission_data(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRegister.objects.filter(pk=self.register.pk).update(
                status=AttendanceRegister.Status.SUBMITTED
            )
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)

    def test_database_rejects_unknown_register_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRegister.objects.filter(pk=self.register.pk).update(status="LOCKED")

    def test_capture_leaves_register_draft(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)
        self.assertIsNone(self.register.submitted_at)


class AttendanceGate3ContextTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()

    def test_register_section_must_belong_to_class_grade(self):
        other_grade = ClassGrade.objects.create(name="Grade 2")
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=other_grade,
            section=self.section,
            date="2026-07-02",
        )
        with self.assertRaises(ValidationError) as ctx:
            register.full_clean()
        self.assertIn("section", ctx.exception.message_dict)

    def test_register_date_must_fall_in_academic_year(self):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2027-05-03",
        )
        with self.assertRaises(ValidationError) as ctx:
            register.full_clean()
        self.assertIn("date", ctx.exception.message_dict)

    def test_register_context_locked_once_entries_exist(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")

        for field, value in (("date", date(2026, 7, 2)), ("section", other_section)):
            with self.subTest(field=field):
                register = AttendanceRegister.objects.get(pk=self.register.pk)
                setattr(register, field, value)
                with self.assertRaises(ValidationError):
                    register.full_clean()

    def test_register_context_can_change_while_empty(self):
        register = AttendanceRegister.objects.get(pk=self.register.pk)
        register.date = date(2026, 7, 2)

        register.full_clean()
        register.save()

    def test_unique_register_and_enrollment(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceEntry.objects.create(
                register=self.register,
                academic_enrollment=self.enrollment,
                status=AttendanceStatus.ABSENT,
            )
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_enrollment_from_other_academic_year_rejected(self):
        other_year = AcademicYear.objects.create(
            name="Overlapping session", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        other_student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        other_enrollment = other_student.enroll(
            academic_year=other_year,
            class_grade=self.class_grade,
            section=self.section,
            start_date=date(2026, 6, 1),
        )

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=other_enrollment, status=AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_enrollment_starting_after_register_date_rejected(self):
        late_joiner = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Meera Rao"), full_name="Meera Rao"
        )
        enrollment = late_joiner.enroll(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            start_date=date(2026, 7, 2),
        )

        with self.assertRaises(ValidationError):
            self.register.capture(enrollment=enrollment, status=AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_entry_full_clean_rejects_non_effective_enrollment(self):
        self.student.enroll(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=Section.objects.create(class_grade=self.class_grade, name="B"),
            start_date=date(2026, 6, 15),
        )
        self.enrollment.refresh_from_db()  # now ends 2026-06-14

        entry = AttendanceEntry(
            register=self.register,
            academic_enrollment=self.enrollment,
            status=AttendanceStatus.PRESENT,
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn("academic_enrollment", ctx.exception.message_dict)


class AttendanceGate3HistoryProtectionTests(AttendanceFixtureMixin, TestCase):
    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")
        self.entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        self.entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Left early."
        )

    def test_entry_with_corrections_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.entry.delete()
        self.assertTrue(AttendanceEntry.objects.filter(pk=self.entry.pk).exists())

    def test_enrollment_with_attendance_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.enrollment.delete()

    def test_correcting_actor_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.actor.delete()

    def test_submitting_user_is_protected(self):
        AttendanceRegister.objects.filter(pk=self.register.pk).update(
            status=AttendanceRegister.Status.SUBMITTED,
            submitted_by=self.actor,
            submitted_at=timezone.now(),
        )
        self.register.refresh_from_db()

        self.assertEqual(self.register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(
            list(self.actor.submitted_attendance_registers.all()), [self.register]
        )
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.actor.delete()


class AttendanceLegacyStatusMigrationTests(TransactionTestCase):
    """Migration 0021 must refuse, not convert, legacy LATE/EXCUSED data."""

    before = [("core", "0020_add_school_calendar_permissions_to_group")]
    after = [("core", "0021_attendance_core_reconciliation")]

    def tearDown(self):
        # Remove any deliberately unreconciled legacy rows, then always leave
        # the database fully migrated for the following tests.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        applied = executor.loader.applied_migrations
        if ("core", "0021_attendance_core_reconciliation") not in applied:
            apps = executor.loader.project_state(self.before).apps
            apps.get_model("core", "AttendanceCorrection").objects.all().delete()
            apps.get_model("core", "AttendanceEntry").objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def _seed_legacy(self, apps, *, entry_status, correction=None):
        AcademicYear_ = apps.get_model("core", "AcademicYear")
        ClassGrade_ = apps.get_model("core", "ClassGrade")
        Section_ = apps.get_model("core", "Section")
        Applicant_ = apps.get_model("core", "Applicant")
        Student_ = apps.get_model("core", "Student")
        Enrollment_ = apps.get_model("core", "AcademicEnrollment")
        Register_ = apps.get_model("core", "AttendanceRegister")
        Entry_ = apps.get_model("core", "AttendanceEntry")
        Correction_ = apps.get_model("core", "AttendanceCorrection")
        User_ = apps.get_model("accounts", "User")

        year = AcademicYear_.objects.create(
            name="Legacy", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        grade = ClassGrade_.objects.create(name="Legacy grade")
        section = Section_.objects.create(class_grade=grade, name="A")
        applicant = Applicant_.objects.create(full_name="Legacy Student")
        student = Student_.objects.create(applicant=applicant, full_name="Legacy Student")
        enrollment = Enrollment_.objects.create(
            student=student,
            academic_year=year,
            class_grade=grade,
            section=section,
            start_date=date(2026, 6, 1),
        )
        register = Register_.objects.create(
            academic_year=year, class_grade=grade, section=section, date=date(2026, 7, 1)
        )
        entry = Entry_.objects.create(
            register=register, academic_enrollment=enrollment, status=entry_status
        )
        if correction is not None:
            user = User_.objects.create(username="legacy-admin")
            Correction_.objects.create(
                entry=entry,
                previous_status=correction[0],
                new_status=correction[1],
                reason="Legacy correction.",
                corrected_by=user,
            )
        return entry

    def test_legacy_entry_status_stops_migration_without_conversion(self):
        apps = self._migrate(self.before)
        entry = self._seed_legacy(apps, entry_status="LATE")

        with self.assertRaisesMessage(RuntimeError, "will not be converted automatically"):
            self._migrate(self.after)

        Entry_ = apps.get_model("core", "AttendanceEntry")
        self.assertEqual(Entry_.objects.get(pk=entry.pk).status, "LATE")

    def test_legacy_correction_status_stops_migration(self):
        apps = self._migrate(self.before)
        self._seed_legacy(apps, entry_status="PRESENT", correction=("EXCUSED", "PRESENT"))

        with self.assertRaisesMessage(RuntimeError, "AttendanceCorrection ids [1]"):
            self._migrate(self.after)

    def test_reconciled_data_migrates_and_registers_become_draft(self):
        apps = self._migrate(self.before)
        entry = self._seed_legacy(apps, entry_status="LATE")
        Entry_ = apps.get_model("core", "AttendanceEntry")
        Entry_.objects.filter(pk=entry.pk).update(status="PRESENT")  # manual reconciliation

        new_apps = self._migrate(self.after)

        Register_ = new_apps.get_model("core", "AttendanceRegister")
        register = Register_.objects.get()
        self.assertEqual(register.status, "DRAFT")
        self.assertIsNone(register.submitted_by_id)
        self.assertIsNone(register.submitted_at)
        migrated = new_apps.get_model("core", "AttendanceEntry").objects.get()
        self.assertEqual((migrated.status, migrated.absence_note), ("PRESENT", ""))


@mock.patch("core.models.business_today", new=lambda: date(2026, 10, 10))
class AttendanceGate4Tests(TestCase):
    """Gate 4: date-effective roster and DRAFT -> SUBMITTED workflow (ADR 0007)."""

    WEDNESDAY = date(2026, 7, 1)
    TRANSFER_DATE = date(2026, 9, 1)

    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section_a = Section.objects.create(class_grade=self.class_grade, name="A")
        self.section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        self.ravi = self._student("Ravi Rao")
        self.meera = self._student("Meera Rao")
        self.ravi_a = self._enroll(self.ravi, self.section_a, date(2026, 6, 1))
        self.meera_a = self._enroll(self.meera, self.section_a, date(2026, 6, 1))
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def _student(self, name):
        return Student.objects.create(
            applicant=Applicant.objects.create(full_name=name), full_name=name
        )

    def _enroll(self, student, section, start):
        return student.enroll(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=section,
            start_date=start,
        )

    def _register(self, on_date, section=None):
        register = AttendanceRegister(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=section or self.section_a,
            date=on_date,
        )
        register.full_clean()
        register.save()
        return register

    def _mark_all(self, register, status=AttendanceStatus.PRESENT):
        for enrollment in register.eligible_enrollments():
            register.capture(enrollment=enrollment, status=status)

    # --- roster -----------------------------------------------------------

    def test_roster_is_date_effective_before_transfer(self):
        self._enroll(self.ravi, self.section_b, self.TRANSFER_DATE)
        register = self._register(date(2026, 8, 31))

        self.ravi_a.refresh_from_db()
        self.assertEqual(list(register.eligible_enrollments()), [self.meera_a, self.ravi_a])

    def test_roster_after_transfer_moves_student_to_new_section(self):
        ravi_b = self._enroll(self.ravi, self.section_b, self.TRANSFER_DATE)

        register_a = self._register(self.TRANSFER_DATE)
        register_b = self._register(self.TRANSFER_DATE, section=self.section_b)

        self.assertEqual(list(register_a.eligible_enrollments()), [self.meera_a])
        self.assertEqual(list(register_b.eligible_enrollments()), [ravi_b])

    def test_later_transfer_keeps_student_on_earlier_historical_roster(self):
        register = self._register(self.WEDNESDAY)
        self._enroll(self.ravi, self.section_b, self.TRANSFER_DATE)

        roster = list(register.eligible_enrollments())
        self.assertIn(self.ravi_a, roster)

    def test_late_joiner_not_on_earlier_roster(self):
        late = self._enroll(self._student("Asha Iyer"), self.section_a, date(2026, 7, 2))
        register = self._register(self.WEDNESDAY)

        self.assertNotIn(late, list(register.eligible_enrollments()))

    # --- missing-attendance semantics --------------------------------------

    def test_no_register_means_not_taken(self):
        self.assertEqual(
            AttendanceRegister.attendance_state(self.section_a, self.WEDNESDAY),
            AttendanceRegister.AttendanceState.NOT_TAKEN,
        )

    def test_draft_and_submitted_states(self):
        register = self._register(self.WEDNESDAY)
        self.assertEqual(
            AttendanceRegister.attendance_state(self.section_a, self.WEDNESDAY),
            AttendanceRegister.AttendanceState.DRAFT,
        )

        self._mark_all(register)
        register.submit(actor=self.actor)

        self.assertEqual(
            AttendanceRegister.attendance_state(self.section_a, self.WEDNESDAY),
            AttendanceRegister.AttendanceState.SUBMITTED,
        )

    def test_missing_entry_is_not_absent(self):
        register = self._register(self.WEDNESDAY)
        register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)

        self.assertFalse(
            AttendanceEntry.objects.filter(status=AttendanceStatus.ABSENT).exists()
        )
        self.assertEqual(list(register.unmarked_enrollments()), [self.meera_a])

    # --- DRAFT and submission ----------------------------------------------

    def test_incomplete_draft_is_accepted(self):
        register = self._register(self.WEDNESDAY)
        register.capture(enrollment=self.ravi_a, status=AttendanceStatus.ABSENT)

        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)

    def test_incomplete_submission_rejected(self):
        register = self._register(self.WEDNESDAY)
        register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)

        with self.assertRaisesMessage(ValidationError, "1 Student(s)"):
            register.submit(actor=self.actor)

        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)
        self.assertIsNone(register.submitted_at)

    def test_complete_submission_captures_actor_and_time(self):
        register = self._register(self.WEDNESDAY)
        register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)
        register.capture(enrollment=self.meera_a, status=AttendanceStatus.ABSENT)

        register.submit(actor=self.actor)

        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(register.submitted_by, self.actor)
        self.assertIsNotNone(register.submitted_at)

    def test_submission_requires_actor(self):
        register = self._register(self.WEDNESDAY)
        self._mark_all(register)

        with self.assertRaises(ValidationError):
            register.submit(actor=None)

    def test_repeat_submission_rejected(self):
        register = self._register(self.WEDNESDAY)
        self._mark_all(register)
        register.submit(actor=self.actor)
        first_time = AttendanceRegister.objects.get(pk=register.pk).submitted_at

        with self.assertRaisesMessage(ValidationError, "already been submitted"):
            register.submit(actor=self.actor)

        self.assertEqual(AttendanceRegister.objects.get(pk=register.pk).submitted_at, first_time)

    def test_empty_roster_cannot_be_submitted(self):
        register = self._register(self.WEDNESDAY, section=self.section_b)

        with self.assertRaisesMessage(ValidationError, "no attendance to submit"):
            register.submit(actor=self.actor)

    def test_submission_rejected_with_ineligible_entry(self):
        register = self._register(self.WEDNESDAY)
        self._mark_all(register)
        # An entry whose enrollment is not on the roster can only arise from a
        # direct write; submission must still refuse it.
        outsider = self._enroll(self._student("Asha Iyer"), self.section_b, date(2026, 6, 1))
        AttendanceEntry.objects.create(
            register=register, academic_enrollment=outsider, status=AttendanceStatus.PRESENT
        )

        with self.assertRaisesMessage(ValidationError, "not enrolled in this Section"):
            register.submit(actor=self.actor)

    def test_submitted_register_rejects_new_capture(self):
        register = self._register(self.WEDNESDAY)
        register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)
        register.capture(enrollment=self.meera_a, status=AttendanceStatus.PRESENT)
        register.submit(actor=self.actor)
        register.entries.filter(academic_enrollment=self.ravi_a).delete()  # free the slot

        with self.assertRaisesMessage(ValidationError, "through a correction"):
            register.capture(enrollment=self.ravi_a, status=AttendanceStatus.ABSENT)
        self.assertEqual(register.entries.count(), 1)

    # --- calendar and future dates -----------------------------------------

    def test_future_register_cannot_be_opened(self):
        with self.assertRaisesMessage(ValidationError, "future date"):
            self._register(date(2026, 10, 12))

    def test_register_for_today_can_be_opened(self):
        register = self._register(date(2026, 10, 9))  # Friday; "today" is Saturday 10th
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)

    def test_future_submission_rejected(self):
        register = self._register(self.WEDNESDAY)
        self._mark_all(register)
        AttendanceRegister.objects.filter(pk=register.pk).update(date=date(2026, 10, 12))
        register.refresh_from_db()

        with self.assertRaisesMessage(ValidationError, "future date"):
            register.submit(actor=self.actor)

    def test_non_instructional_date_cannot_be_opened(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 8, 17), is_instructional=False
        )
        for on_date in (date(2026, 8, 17), date(2026, 8, 22), date(2026, 8, 23)):
            with self.subTest(on_date=on_date), self.assertRaisesMessage(
                ValidationError, "not an instructional day"
            ):
                self._register(on_date)

    def test_non_instructional_submission_rejected(self):
        register = AttendanceRegister.objects.create(  # legacy register on a Saturday
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section_a,
            date=date(2026, 8, 22),
        )
        self._mark_all(register)

        with self.assertRaisesMessage(ValidationError, "not an instructional day"):
            register.submit(actor=self.actor)
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)

    def test_working_saturday_accepted_when_instructional(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 8, 22), is_instructional=True
        )
        register = self._register(date(2026, 8, 22))
        self._mark_all(register)

        register.submit(actor=self.actor)

        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)


class AttendanceGate6CorrectionTests(AttendanceFixtureMixin, TestCase):
    """Gate 6: DRAFT = normal edits; SUBMITTED = audited corrections."""

    def setUp(self):
        self.build_attendance_fixture()
        self.actor = User.objects.create_user(username="administrator", password="pass-12345")

    def test_draft_edit_creates_no_correction(self):
        self.register.save_draft_entry(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)
        entry = self.register.save_draft_entry(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertEqual(AttendanceEntry.objects.count(), 1)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_draft_entry_cannot_be_corrected(self):
        entry = self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaisesMessage(ValidationError, "still a draft"):
            entry.record_status_change(AttendanceStatus.ABSENT, actor=self.actor, reason="x")

        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_submitted_entry_cannot_be_draft_edited(self):
        self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        with self.assertRaisesMessage(ValidationError, "through a correction"):
            self.register.save_draft_entry(
                enrollment=self.enrollment, status=AttendanceStatus.ABSENT
            )
        self.assertEqual(AttendanceEntry.objects.get().status, AttendanceStatus.PRESENT)

    def test_submitted_correction_records_full_history(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.ABSENT, absence_note="Fever"
        )

        entry.record_status_change(
            AttendanceStatus.PRESENT, actor=self.actor, reason="Arrived after roll call."
        )

        correction = AttendanceCorrection.objects.get()
        self.assertEqual(
            (
                correction.previous_status,
                correction.new_status,
                correction.previous_absence_note,
                correction.new_absence_note,
                correction.reason,
                correction.corrected_by,
            ),
            ("ABSENT", "PRESENT", "Fever", "", "Arrived after roll call.", self.actor),
        )
        self.assertIsNotNone(correction.created_at)
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.absence_note), ("PRESENT", ""))

    def test_correction_to_absent_can_record_note(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        entry.record_status_change(
            AttendanceStatus.ABSENT, actor=self.actor, reason="Left early.", absence_note=" Ill "
        )

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.absence_note), ("ABSENT", "Ill"))
        self.assertEqual(AttendanceCorrection.objects.get().new_absence_note, "Ill")

    def test_note_on_present_correction_rejected(self):
        entry = self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        with self.assertRaises(ValidationError):
            entry.record_status_change(
                AttendanceStatus.PRESENT, actor=self.actor, reason="x", absence_note="nope"
            )
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_repeated_corrections_preserve_sequence(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        for status, reason in (
            (AttendanceStatus.ABSENT, "first"),
            (AttendanceStatus.PRESENT, "second"),
            (AttendanceStatus.ABSENT, "third"),
        ):
            entry.record_status_change(status, actor=self.actor, reason=reason)

        history = list(
            entry.corrections.order_by("created_at", "pk").values_list(
                "previous_status", "new_status", "reason"
            )
        )
        self.assertEqual(
            history,
            [
                ("PRESENT", "ABSENT", "first"),
                ("ABSENT", "PRESENT", "second"),
                ("PRESENT", "ABSENT", "third"),
            ],
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.ABSENT)

    def test_no_op_and_invalid_corrections_rejected(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

        for status, reason, actor in (
            (AttendanceStatus.PRESENT, "same", self.actor),
            ("LATE", "legacy", self.actor),
            (AttendanceStatus.ABSENT, "   ", self.actor),
            (AttendanceStatus.ABSENT, "no actor", None),
        ):
            with self.subTest(status=status, reason=reason), self.assertRaises(ValidationError):
                entry.record_status_change(status, actor=actor, reason=reason)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_correction_leaves_historical_context_unchanged(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        before = AttendanceRegister.objects.filter(pk=self.register.pk).values(
            "academic_year_id", "class_grade_id", "section_id", "date", "status",
            "submitted_by_id", "submitted_at",
        ).get()

        entry.record_status_change(AttendanceStatus.ABSENT, actor=self.actor, reason="x")

        entry.refresh_from_db()
        self.assertEqual(entry.academic_enrollment_id, self.enrollment.pk)
        self.assertEqual(entry.register_id, self.register.pk)
        after = AttendanceRegister.objects.filter(pk=self.register.pk).values(*before).get()
        self.assertEqual(after, before)
