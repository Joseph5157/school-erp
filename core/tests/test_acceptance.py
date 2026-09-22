from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicEnrollment,
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

User = get_user_model()


class Phase1AcceptanceJourneyTests(TestCase):
    """The REQUIREMENTS.md "Phase 1 acceptance journey", exercised end to end.

    These tests walk the whole administrative journey through the real views
    (not the model API) and assert the domain invariants at each step, proving
    Phase 1 behaves as one coherent system rather than as isolated units.
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="administrator", password="pass-12345"
        )
        self.admin_user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="administrator", password="pass-12345")

    def test_full_acceptance_journey(self):
        # Configure school.
        response = self.client.post(reverse("core:school-create"), {"name": "Greenwood High"})
        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.get().name, "Greenwood High")

        # Create Academic Year.
        response = self.client.post(
            reverse("core:academic-year-create"),
            {"name": "2026-2027", "start_date": "2026-06-01", "end_date": "2027-04-30"},
        )
        self.assertRedirects(response, reverse("core:academic-year-list"))
        year = AcademicYear.objects.get()

        # Create Class/Grade and a Section within it.
        self.client.post(reverse("core:class-grade-create"), {"name": "Grade 1"})
        class_grade = ClassGrade.objects.get()
        response = self.client.post(
            reverse("core:section-create", args=[class_grade.pk]), {"name": "A"}
        )
        self.assertRedirects(response, reverse("core:class-grade-detail", args=[class_grade.pk]))
        section = Section.objects.get()

        # Register Applicant -- must not create a Student.
        response = self.client.post(
            reverse("core:applicant-create"),
            {
                "full_name": "Ravi Rao",
                "date_of_birth": "2015-04-01",
                "email": "ravi@example.com",
                "phone": "555-0101",
            },
        )
        self.assertRedirects(response, reverse("core:applicant-list"))
        applicant = Applicant.objects.get()
        self.assertFalse(Student.objects.exists())

        # Associate a Guardian -- must not create a Student.
        self.client.post(reverse("core:guardian-create"), {"full_name": "Asha Rao"})
        guardian = Guardian.objects.get()
        response = self.client.post(
            reverse("core:applicant-guardian-create", args=[applicant.pk]),
            {"guardian": guardian.pk, "relationship_type": RelationshipType.MOTHER},
        )
        self.assertRedirects(response, reverse("core:applicant-detail", args=[applicant.pk]))
        self.assertFalse(Student.objects.exists())

        # Accept the Applicant -- still no Student.
        response = self.client.post(
            reverse("core:applicant-admission-decision", args=[applicant.pk]),
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
        )
        self.assertRedirects(response, reverse("core:applicant-detail", args=[applicant.pk]))
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
        self.assertFalse(Student.objects.exists())

        # Explicitly progress to Student; guardians are carried forward.
        response = self.client.post(reverse("core:applicant-progress", args=[applicant.pk]))
        student = Student.objects.get()
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        self.assertEqual(student.applicant, applicant)
        link = StudentGuardian.objects.get(student=student)
        self.assertEqual(link.guardian, guardian)
        self.assertEqual(link.relationship_type, RelationshipType.MOTHER)
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

        # Create Academic Enrollment (assignment through enrollment).
        response = self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {"academic_year": year.pk, "class_grade": class_grade.pk, "section": section.pk},
        )
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        enrollment = AcademicEnrollment.objects.get()
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(student.current_enrollment, enrollment)

        # View active/current Student profile with identity, placement, guardian.
        response = self.client.get(reverse("core:student-detail", args=[student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, "2026-2027")
        self.assertContains(response, "Grade 1")

        # The original Applicant remains accessible after progression.
        response = self.client.get(reverse("core:applicant-detail", args=[applicant.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")

        # The Student is findable through the basic search/listing.
        response = self.client.get(reverse("core:student-list"), {"q": "Ravi"})
        self.assertEqual(list(response.context["students"]), [student])

    def test_placement_and_status_changes_preserve_history(self):
        # Build the prerequisites for an enrolled Student through the views.
        self.client.post(reverse("core:school-create"), {"name": "Greenwood High"})
        self.client.post(
            reverse("core:academic-year-create"),
            {"name": "2026-2027", "start_date": "2026-06-01", "end_date": "2027-04-30"},
        )
        self.client.post(
            reverse("core:academic-year-create"),
            {"name": "2027-2028", "start_date": "2027-06-01", "end_date": "2028-04-30"},
        )
        self.client.post(reverse("core:class-grade-create"), {"name": "Grade 1"})
        class_grade = ClassGrade.objects.get()
        self.client.post(reverse("core:section-create", args=[class_grade.pk]), {"name": "A"})
        section = Section.objects.get()
        first_year = AcademicYear.objects.get(name="2026-2027")
        second_year = AcademicYear.objects.get(name="2027-2028")

        self.client.post(reverse("core:applicant-create"), {"full_name": "Ravi Rao"})
        applicant = Applicant.objects.get()
        self.client.post(
            reverse("core:applicant-admission-decision", args=[applicant.pk]),
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
        )
        self.client.post(reverse("core:applicant-progress", args=[applicant.pk]))
        student = Student.objects.get()

        # First placement.
        self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {
                "academic_year": first_year.pk,
                "class_grade": class_grade.pk,
                "section": section.pk,
            },
        )
        # Second placement completes the first rather than overwriting it.
        self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {
                "academic_year": second_year.pk,
                "class_grade": class_grade.pk,
                "section": section.pk,
            },
        )

        enrollments = list(student.enrollments.all())
        self.assertEqual(len(enrollments), 2)
        self.assertEqual(
            enrollments[0].status, AcademicEnrollment.Status.ACTIVE
        )
        self.assertEqual(
            enrollments[1].status, AcademicEnrollment.Status.COMPLETED
        )

        # Deactivate, then reactivate: enrollment history is untouched.
        self.client.post(
            reverse("core:student-status-change", args=[student.pk]),
            {"status": Student.Status.INACTIVE},
        )
        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.INACTIVE)
        self.assertEqual(student.enrollments.count(), 2)

        self.client.post(
            reverse("core:student-status-change", args=[student.pk]),
            {"status": Student.Status.ACTIVE},
        )
        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.ACTIVE)
        self.assertEqual(student.enrollments.count(), 2)
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
