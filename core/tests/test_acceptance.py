from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core import reports
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
)

User = get_user_model()


# School form field required since Phase 7 Gate 1 (notification channel).
CHANNEL = {"notification_channel": "PORTAL_ONLY"}


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
        response = self.client.post(
            reverse("core:school-create"), {"name": "Greenwood High", **CHANNEL}
        )
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
            {
                "academic_year": year.pk,
                "class_grade": class_grade.pk,
                "section": section.pk,
                "start_date": "2026-06-01",
            },
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

    # The second placement starts in 2027-2028; pin "today" after it so the
    # no-future-start rule does not make this journey clock-dependent.
    @mock.patch("core.models.business_today", new=lambda: date(2027, 12, 31))
    def test_placement_and_status_changes_preserve_history(self):
        # Build the prerequisites for an enrolled Student through the views.
        self.client.post(reverse("core:school-create"), {"name": "Greenwood High", **CHANNEL})
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
                "start_date": "2026-06-01",
            },
        )
        # Second placement completes the first rather than overwriting it.
        self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {
                "academic_year": second_year.pk,
                "class_grade": class_grade.pk,
                "section": section.pk,
                "start_date": "2027-06-01",
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
            {"status": Student.Status.INACTIVE, "reason": "Test reason"},
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


class Phase2AcceptanceJourneyTests(TestCase):
    """The REQUIREMENTS.md "Phase 2 acceptance journey", exercised end to end."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="administrator", password="pass-12345"
        )
        self.admin_user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="administrator", password="pass-12345")

    def _enrolled_student(self):
        year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        class_grade = ClassGrade.objects.create(name="Grade 1")
        section = Section.objects.create(class_grade=class_grade, name="A")
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        student = applicant.progress_to_student()
        enrollment = student.enroll(
            academic_year=year, class_grade=class_grade, section=section,
            start_date=date(2026, 6, 1),
        )
        return year, class_grade, section, student, enrollment

    def test_full_attendance_journey(self):
        year, class_grade, section, student, enrollment = self._enrolled_student()

        # Open an attendance register for the Class/Grade + Section and date.
        response = self.client.post(
            reverse("core:attendance-register-create"),
            {
                "academic_year": year.pk,
                "class_grade": class_grade.pk,
                "section": section.pk,
                "date": "2026-07-01",
            },
        )
        register = AttendanceRegister.objects.get()
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )

        # Capture a status for the enrolled Student.
        response = self.client.post(
            reverse("core:attendance-capture", args=[register.pk]),
            {f"status_{enrollment.pk}": AttendanceStatus.PRESENT},
        )
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        entry = AttendanceEntry.objects.get()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)

        # View the register and the Student's attendance history.
        response = self.client.get(
            reverse("core:attendance-register-detail", args=[register.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "Present")

        # Submit the complete register; corrections apply to submitted attendance.
        response = self.client.post(
            reverse("core:attendance-register-submit", args=[register.pk])
        )
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)

        # Correct the captured status with a recorded reason.
        response = self.client.post(
            reverse("core:attendance-entry-correct", args=[entry.pk]),
            {"status": AttendanceStatus.ABSENT, "reason": "Guardian reported illness."},
        )
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.ABSENT)
        correction = AttendanceCorrection.objects.get()
        self.assertEqual(correction.previous_status, AttendanceStatus.PRESENT)
        self.assertEqual(correction.new_status, AttendanceStatus.ABSENT)
        self.assertEqual(correction.reason, "Guardian reported illness.")

        # View the Student's attendance summary over a date range.
        response = self.client.get(
            reverse("core:student-attendance", args=[student.pk]),
            {"start": "2026-07-01", "end": "2026-07-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)
        self.assertContains(response, "Absent")


@mock.patch("core.models.business_today", new=lambda: date(2026, 10, 10))
class Phase2ReconciledAcceptanceJourneyTests(TestCase):
    """Gate 8: the reconciled Phase 2 journey (PHASE_2_RECONCILIATION_PLAN.md).

    One coherent journey through the real views: calendar, date-effective
    enrollment, DRAFT -> SUBMITTED registers, corrections, a transfer,
    missing attendance and reports.
    """

    WED = date(2026, 7, 8)
    THU = date(2026, 7, 9)
    FRI = date(2026, 7, 10)
    HOLIDAY = date(2026, 7, 13)  # Monday
    TRANSFER = date(2026, 7, 15)  # Wednesday
    WORKING_SATURDAY = date(2026, 7, 18)

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="administrator", password="pass-12345"
        )
        self.admin_user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="administrator", password="pass-12345")

    def _student(self, name):
        self.client.post(reverse("core:applicant-create"), {"full_name": name})
        applicant = Applicant.objects.get(full_name=name)
        self.client.post(
            reverse("core:applicant-admission-decision", args=[applicant.pk]),
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
        )
        self.client.post(reverse("core:applicant-progress", args=[applicant.pk]))
        return Student.objects.get(applicant=applicant)

    def _enroll(self, student, section, start):
        response = self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {
                "academic_year": self.year.pk,
                "class_grade": self.grade.pk,
                "section": section.pk,
                "start_date": start.isoformat(),
            },
        )
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        return AcademicEnrollment.objects.get(student=student, section=section)

    def _open(self, section, on_date):
        response = self.client.post(
            reverse("core:attendance-register-create"),
            {
                "academic_year": self.year.pk,
                "class_grade": self.grade.pk,
                "section": section.pk,
                "date": on_date.isoformat(),
            },
        )
        register = AttendanceRegister.objects.get(section=section, date=on_date)
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        return register

    def _mark(self, register, marks, action=None):
        data = {}
        for enrollment, (status, note) in marks.items():
            data[f"status_{enrollment.pk}"] = status
            data[f"note_{enrollment.pk}"] = note
        if action:
            data["action"] = action
        return self.client.post(reverse("core:attendance-capture", args=[register.pk]), data)

    def test_reconciled_phase_2_journey(self):
        # Academic Year with Saturdays off.
        self.client.post(
            reverse("core:academic-year-create"),
            {"name": "2026-2027", "start_date": "2026-06-01", "end_date": "2027-04-30"},
        )
        self.year = AcademicYear.objects.get()
        self.assertFalse(self.year.saturdays_instructional)

        # Calendar: a holiday and a working Saturday.
        calendar_add = reverse("core:calendar-day-create", args=[self.year.pk])
        self.client.post(
            calendar_add,
            {"date": self.HOLIDAY.isoformat(), "is_instructional": "False", "label": "Holiday"},
        )
        self.client.post(
            calendar_add,
            {
                "date": self.WORKING_SATURDAY.isoformat(),
                "is_instructional": "True",
                "label": "Working Saturday",
            },
        )
        self.assertEqual(SchoolCalendarDay.objects.count(), 2)
        self.assertTrue(self.year.is_instructional_day(self.WED))
        self.assertFalse(self.year.is_instructional_day(self.HOLIDAY))
        self.assertTrue(self.year.is_instructional_day(self.WORKING_SATURDAY))

        # Structure and Students with effective-dated enrollment in Section A.
        self.client.post(reverse("core:class-grade-create"), {"name": "Grade 1"})
        self.grade = ClassGrade.objects.get()
        for name in ("A", "B"):
            self.client.post(reverse("core:section-create", args=[self.grade.pk]), {"name": name})
        section_a = Section.objects.get(name="A")
        section_b = Section.objects.get(name="B")
        ravi = self._student("Ravi Rao")
        meera = self._student("Meera Rao")
        ravi_a = self._enroll(ravi, section_a, date(2026, 6, 1))
        meera_a = self._enroll(meera, section_a, date(2026, 6, 1))

        # Open Section A attendance; the date-effective roster has both Students.
        register = self._open(section_a, self.WED)
        detail = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertEqual(detail.context["capture_form"].enrollments, [meera_a, ravi_a])

        # Save an incomplete DRAFT: only Ravi, absent with a note.
        self._mark(register, {ravi_a: ("ABSENT", "Fever")})
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)
        self.assertEqual(reports.student_summary(ravi)["total"], 0)  # DRAFT never counts

        # Mark the rest and submit the complete register.
        self._mark(register, {ravi_a: ("ABSENT", "Fever"), meera_a: ("PRESENT", "")}, "submit")
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(register.submitted_by, self.admin_user)

        # Reports show the submitted result.
        absent = self.client.get(
            reverse("core:report-daily-absentees"), {"date": self.WED.isoformat()}
        )
        self.assertContains(absent, "Ravi Rao")
        self.assertContains(absent, "Fever")
        self.assertEqual(reports.student_summary(ravi)["percentage"], 0.0)

        # Correct the submitted status; the audit trail is preserved.
        entry = AttendanceEntry.objects.get(register=register, academic_enrollment=ravi_a)
        response = self.client.post(
            reverse("core:attendance-entry-correct", args=[entry.pk]),
            {"status": "PRESENT", "reason": "Arrived after roll call."},
        )
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.absence_note), ("PRESENT", ""))
        correction = AttendanceCorrection.objects.get()
        self.assertEqual(
            (correction.previous_status, correction.previous_absence_note, correction.new_status),
            ("ABSENT", "Fever", "PRESENT"),
        )
        self.assertEqual(reports.student_summary(ravi)["percentage"], 100.0)

        # Transfer Ravi to Section B effective on a specified date.
        ravi_b = self._enroll(ravi, section_b, self.TRANSFER)
        ravi_a.refresh_from_db()
        self.assertEqual(ravi_a.end_date, date(2026, 7, 14))

        # Old attendance remains under Section A.
        entry.refresh_from_db()
        self.assertEqual(entry.register.section, section_a)
        self.assertEqual(entry.academic_enrollment, ravi_a)

        # The working-Saturday Section B roster includes Ravi; Section A's does not.
        register_b = self._open(section_b, self.WORKING_SATURDAY)
        self.assertEqual(list(register_b.eligible_enrollments()), [ravi_b])
        self._mark(register_b, {ravi_b: ("PRESENT", "")}, "submit")
        register_b.refresh_from_db()
        self.assertTrue(register_b.is_submitted)
        register_a_sat = self._open(section_a, self.WORKING_SATURDAY)
        self.assertEqual(list(register_a_sat.eligible_enrollments()), [meera_a])

        # The holiday cannot be opened at all.
        response = self.client.post(
            reverse("core:attendance-register-create"),
            {
                "academic_year": self.year.pk,
                "class_grade": self.grade.pk,
                "section": section_a.pk,
                "date": self.HOLIDAY.isoformat(),
            },
        )
        self.assertContains(response, "not an instructional day")

        # Leave Thursday missing and Friday as DRAFT for Section A.
        friday = self._open(section_a, self.FRI)
        self._mark(friday, {ravi_a: ("ABSENT", "")})

        missing = self.client.get(
            reverse("core:report-missing-attendance"),
            {"start": "2026-07-06", "end": "2026-07-18", "section": section_a.pk},
        )
        rows = {(row["date"], row["state"]) for row in missing.context["rows"]}
        self.assertIn((self.THU, AttendanceRegister.AttendanceState.NOT_TAKEN), rows)
        self.assertIn((self.FRI, AttendanceRegister.AttendanceState.DRAFT), rows)
        self.assertIn((self.WORKING_SATURDAY, AttendanceRegister.AttendanceState.DRAFT), rows)
        missing_dates = {on_date for on_date, _ in rows}
        self.assertNotIn(self.WED, missing_dates)  # submitted
        self.assertNotIn(self.HOLIDAY, missing_dates)  # holiday never missing
        self.assertNotIn(date(2026, 7, 11), missing_dates)  # ordinary Saturday
        self.assertNotIn(date(2026, 7, 12), missing_dates)  # Sunday

        # Missing and DRAFT attendance do not lower the percentage.
        history = self.client.get(reverse("core:student-attendance", args=[ravi.pk]))
        self.assertEqual(history.context["percentage"], 100.0)
        self.assertEqual(history.context["total"], 2)  # WED (A, corrected) + SAT (B)
        sections = [e.register.section for e in history.context["entries"]]
        self.assertEqual(sections, [section_a, section_a, section_b])  # incl. Friday draft

        # Monthly summary for Section A reflects the same semantics.
        monthly = self.client.get(
            reverse("core:report-monthly-section"),
            {"section": section_a.pk, "month": "2026-07"},
        )
        rows = {row["student"]: row for row in monthly.context["summary"]["rows"]}
        self.assertEqual(rows[ravi]["percentage"], 100.0)
        self.assertEqual(rows[meera]["percentage"], 100.0)
