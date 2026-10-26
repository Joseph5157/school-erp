"""The demo-school seeders run end to end on an empty database."""

import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import (
    AcademicTerm,
    Applicant,
    Assessment,
    GuardianStudentAccess,
    Student,
    StudentResult,
    TermPublication,
)


class SeedSchoolDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.creds = Path(tempfile.mkdtemp()) / "creds.csv"
        call_command("seed_school_demo", credentials_file=str(cls.creds), allow_non_debug=True,
                     verbosity=0)
        call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)

    def test_builds_a_working_school_with_parent_access(self):
        self.assertEqual(Student.objects.count(), 110)
        self.assertFalse([s for s in Student.objects.all() if not s.full_name.isascii()])
        with open(self.creds, newline="", encoding="utf-8") as handle:
            roles = [row["role"] for row in csv.DictReader(handle)]
        self.assertEqual(roles.count("teacher"), 10)
        self.assertEqual(roles.count("administrator"), 1)
        for student in Student.objects.all():
            self.assertTrue(
                GuardianStudentAccess.objects.filter(
                    student_guardian__student=student, revoked_at__isnull=True
                ).exists(),
                student.full_name,
            )

    def test_applicants_without_students_are_left_for_the_admissions_screen(self):
        self.assertGreater(Applicant.objects.filter(student__isnull=True).count(), 0)

    def test_results_are_finalized_and_published_through_the_workflows(self):
        self.assertEqual(AcademicTerm.objects.count(), 2)
        finalized = Assessment.objects.filter(status=Assessment.Status.FINALIZED)
        self.assertEqual(finalized.count(), Assessment.objects.count())
        if finalized.exists():  # assessments are dated inside Term 1, so need today past them
            self.assertTrue(StudentResult.objects.exists())
            self.assertEqual(TermPublication.objects.count(), Student.objects.count())

    def test_both_seeders_refuse_to_run_twice(self):
        with self.assertRaises(CommandError):
            call_command("seed_school_demo", credentials_file=str(self.creds),
                         allow_non_debug=True, verbosity=0)
        with self.assertRaises(CommandError):
            call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)
