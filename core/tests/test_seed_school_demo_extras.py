"""seed_school_demo_extras fills the profile, logo, timetable and notices."""

import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core import timetable
from core.models import (
    AcademicYear,
    Announcement,
    AssessmentTeacherAssignment,
    School,
    SchoolLogo,
    Section,
    TimetablePeriod,
    TimetableSlot,
)


class SeedSchoolDemoExtrasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        creds = Path(tempfile.mkdtemp()) / "creds.csv"
        call_command("seed_school_demo", credentials_file=str(creds), allow_non_debug=True,
                     verbosity=0)
        call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)
        call_command("seed_school_demo_extras", allow_non_debug=True, verbosity=0)

    def test_school_profile_and_logo(self):
        school = School.objects.get()
        self.assertTrue(school.name)
        for value in (school.address, school.affiliation_number, school.principal_name):
            self.assertTrue(value)
            self.assertTrue(value.isascii())
        logo = SchoolLogo.current_for(school)
        self.assertIsNotNone(logo)
        self.assertTrue(bytes(logo.image).startswith(b"\x89PNG"))

    def test_timetable_exists_without_teacher_clashes(self):
        year = AcademicYear.objects.get()
        self.assertEqual(TimetablePeriod.objects.filter(academic_year=year).count(), 8)
        self.assertGreater(TimetableSlot.objects.count(), 0)
        self.assertEqual(timetable.find_all_clashes(year), [])
        sections_with_slots = set(TimetableSlot.objects.values_list("section_id", flat=True))
        self.assertEqual(sections_with_slots, set(Section.objects.values_list("pk", flat=True)))

    def test_every_assigned_offering_is_timetabled_for_its_section(self):
        scheduled = set(TimetableSlot.objects.values_list("section_id", "offering_id"))
        assigned = set(AssessmentTeacherAssignment.objects.values_list("section_id", "offering_id"))
        self.assertEqual(scheduled, assigned)

    def test_four_announcements_to_the_whole_school(self):
        notices = Announcement.objects.all()
        self.assertEqual(notices.count(), 4)
        self.assertTrue(all(n.audience == Announcement.Audience.ALL for n in notices))
        self.assertTrue(all(n.title.isascii() and n.body.isascii() for n in notices))

    def test_refuses_to_run_twice(self):
        with self.assertRaises(CommandError):
            call_command("seed_school_demo_extras", allow_non_debug=True, verbosity=0)
        self.assertEqual(Announcement.objects.count(), 4)
