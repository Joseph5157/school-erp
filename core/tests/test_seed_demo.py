from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import (
    AcademicEnrollment,
    Applicant,
    AttendanceCorrection,
    AttendanceRegister,
    ClassGrade,
    SchoolCalendarDay,
    Section,
    Student,
)

PINNED_TODAY = date(2026, 10, 9)  # A Friday.


@mock.patch("core.models.business_today", new=lambda: PINNED_TODAY)
@mock.patch("core.management.commands.seed_demo.business_today", new=lambda: PINNED_TODAY)
class SeedDemoCommandTests(TestCase):
    def seed(self):
        call_command("seed_demo", stdout=StringIO())

    def test_creates_school_structure_and_students(self):
        self.seed()
        self.assertEqual(ClassGrade.objects.count(), 3)
        self.assertEqual(Section.objects.count(), 6)
        self.assertEqual(Student.objects.count(), 36)
        self.assertEqual(
            Applicant.objects.filter(admission_status=Applicant.AdmissionStatus.PENDING).count(),
            3,
        )
        self.assertTrue(SchoolCalendarDay.objects.filter(is_instructional=True).exists())
        self.assertTrue(SchoolCalendarDay.objects.filter(is_instructional=False).exists())

    def test_one_student_is_transferred_with_history(self):
        self.seed()
        completed = AcademicEnrollment.objects.filter(
            status=AcademicEnrollment.Status.COMPLETED
        )
        self.assertEqual(completed.count(), 1)
        self.assertEqual(completed.get().student.enrollments.count(), 2)

    def test_attendance_covers_every_state(self):
        self.seed()
        submitted = AttendanceRegister.objects.filter(status=AttendanceRegister.Status.SUBMITTED)
        self.assertTrue(submitted.exists())
        draft = AttendanceRegister.objects.get(status=AttendanceRegister.Status.DRAFT)
        self.assertEqual(draft.date, PINNED_TODAY)
        self.assertTrue(draft.unmarked_enrollments().exists())
        not_taken = [
            section
            for section in Section.objects.all()
            if AttendanceRegister.attendance_state(section, PINNED_TODAY)
            == AttendanceRegister.AttendanceState.NOT_TAKEN
        ]
        self.assertEqual(len(not_taken), 2)
        self.assertEqual(AttendanceCorrection.objects.count(), 1)

    def test_refuses_to_run_twice(self):
        self.seed()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(Student.objects.count(), 36)
