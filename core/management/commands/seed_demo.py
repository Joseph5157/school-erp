"""Populate a local database with realistic demo data for manual testing.

Everything is created through the domain workflows (admission decision,
progression, `Student.enroll`, register capture/submit, audited corrections),
so the demo data obeys the same rules as real use. Dates are computed relative
to today's business date, so the attendance history is always recent.

The command is not re-runnable: it refuses to run when any Class/Grade or
Applicant already exists, and it creates everything in a single transaction
so a failure leaves nothing behind.
"""

import datetime
import random

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Guardian,
    RelationshipType,
    School,
    SchoolCalendarDay,
    Section,
    business_today,
)

DEMO_ADMIN_USERNAME = "demo_admin"
DEMO_ADMIN_PASSWORD = "DemoPass#2026"
ADMIN_GROUP_NAME = "School Administrators"

CLASS_GRADES = ["Grade 1", "Grade 2", "Grade 3"]
SECTION_NAMES = ["A", "B"]
STUDENTS_PER_SECTION = 6
ATTENDANCE_DAYS = 10
ABSENCE_RATE = 0.08

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Ananya", "Diya", "Aadhya", "Saanvi", "Myra", "Anika",
    "Kiara", "Navya", "Ira", "Meera", "Rohan", "Kabir", "Nikhil", "Tara",
    "Riya", "Neha", "Aryan", "Dev", "Zara", "Pooja", "Siddharth", "Lakshmi",
    "Rahul", "Sneha", "Varun", "Priya", "Harsh", "Kavya", "Manav", "Nisha",
]
FAMILY_NAMES = [
    "Sharma", "Iyer", "Nair", "Reddy", "Patel", "Menon", "Gupta", "Joshi",
    "Kulkarni", "Das", "Pillai", "Rao", "Banerjee", "Verma", "Thomas", "Fernandes",
]
FATHER_NAMES = ["Rajesh", "Suresh", "Anil", "Vikram", "Manoj", "Sanjay", "Prakash", "George"]
MOTHER_NAMES = ["Sunita", "Lakshmi", "Anjali", "Deepa", "Kavitha", "Rekha", "Meena", "Mary"]

ABSENCE_NOTES = ["Fever", "Family function", "Doctor's appointment", ""]


class Command(BaseCommand):
    help = (
        "Create demo data (academic year, calendar, classes, students, guardians, "
        "enrollments and recent attendance) for manual testing."
    )

    def handle(self, *args, **options):
        if ClassGrade.objects.exists() or Applicant.objects.exists():
            raise CommandError(
                "Classes or applicants already exist; seed_demo only runs on an empty "
                "school. Use a fresh database to reseed."
            )
        self.rng = random.Random(2026)
        self.today = business_today()
        self.name_pool = iter(self._unique_names())

        with transaction.atomic():
            school = self._school()
            admin = self._demo_admin()
            year = self._academic_year()
            self._calendar(year)
            sections = self._classes_and_sections()
            students = self._students(year, sections)
            self._applicants_without_students()
            self._transfer_one_student(year, sections, students)
            self._attendance(year, sections, admin)

        self.stdout.write(self.style.SUCCESS(f"Demo data created for {school}."))
        self.stdout.write(f"  Academic year: {year} ({year.start_date} to {year.end_date})")
        self.stdout.write(
            f"  Demo staff login: {DEMO_ADMIN_USERNAME} / {DEMO_ADMIN_PASSWORD} "
            f"(member of '{ADMIN_GROUP_NAME}', not a superuser)"
        )

    # -- setup -------------------------------------------------------------

    def _school(self):
        school = School.objects.first()
        if school is None:
            school = School(name="Demo Public School")
            school.full_clean()
            school.save()
        return school

    def _demo_admin(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=DEMO_ADMIN_USERNAME,
            defaults={"first_name": "Demo", "last_name": "Admin"},
        )
        if created:
            user.set_password(DEMO_ADMIN_PASSWORD)
            user.save()
        user.groups.add(Group.objects.get(name=ADMIN_GROUP_NAME))
        return user

    def _academic_year(self):
        # Indian academic calendar: June to March.
        start_year = self.today.year if self.today.month >= 6 else self.today.year - 1
        year = AcademicYear(
            name=f"{start_year}-{str(start_year + 1)[-2:]}",
            start_date=datetime.date(start_year, 6, 1),
            end_date=datetime.date(start_year + 1, 3, 31),
            saturdays_instructional=False,
        )
        year.full_clean()
        year.save()
        return year

    def _calendar(self, year):
        start = year.start_date.year
        holidays = [
            (datetime.date(start, 8, 15), "Independence Day"),
            (datetime.date(start, 10, 2), "Gandhi Jayanti"),
            (datetime.date(start, 12, 25), "Christmas"),
            (datetime.date(start + 1, 1, 26), "Republic Day"),
        ]
        for day, label in holidays:
            # Only weekdays can be holiday exceptions; weekends already are off.
            if year.default_is_instructional(day):
                self._calendar_day(year, day, False, label)

        # A make-up working Saturday inside the attendance window.
        saturday = self.today - datetime.timedelta(days=(self.today.weekday() - 5) % 7 + 7)
        if year.contains(saturday):
            self._calendar_day(year, saturday, True, "Working Saturday (make-up day)")

    def _calendar_day(self, year, day, is_instructional, label):
        entry = SchoolCalendarDay(
            academic_year=year, date=day, is_instructional=is_instructional, label=label
        )
        entry.full_clean()
        entry.save()

    def _classes_and_sections(self):
        sections = []
        for grade_name in CLASS_GRADES:
            grade = ClassGrade.objects.create(name=grade_name)
            for section_name in SECTION_NAMES:
                sections.append(Section.objects.create(class_grade=grade, name=section_name))
        return sections

    # -- people ------------------------------------------------------------

    def _unique_names(self):
        names = [f"{first} {family}" for first in FIRST_NAMES for family in FAMILY_NAMES]
        self.rng.shuffle(names)
        return names

    def _family(self, family_name):
        guardians = []
        for relation, first_names in (
            (RelationshipType.FATHER, FATHER_NAMES),
            (RelationshipType.MOTHER, MOTHER_NAMES),
        ):
            first = self.rng.choice(first_names)
            guardians.append(
                (
                    Guardian.objects.create(
                        full_name=f"{first} {family_name}",
                        phone=f"+91 98{self.rng.randint(10000000, 99999999)}",
                        email=f"{first.lower()}.{family_name.lower()}@example.com",
                    ),
                    relation,
                )
            )
        return guardians

    def _applicant(self, full_name, guardians, birth_year):
        applicant = Applicant.objects.create(
            full_name=full_name,
            date_of_birth=datetime.date(
                birth_year, self.rng.randint(1, 12), self.rng.randint(1, 28)
            ),
        )
        for guardian, relation in guardians:
            ApplicantGuardian.objects.create(
                applicant=applicant, guardian=guardian, relationship_type=relation
            )
        return applicant

    def _students(self, year, sections):
        """Admit and enroll STUDENTS_PER_SECTION students into every Section."""
        students = {}
        previous_family = None
        for section in sections:
            grade_number = int(section.class_grade.name.split()[-1])
            birth_year = year.start_date.year - 5 - grade_number
            students[section.pk] = []
            for index in range(STUDENTS_PER_SECTION):
                full_name = next(self.name_pool)
                # The first student of each Section is a sibling of the student
                # before it, so some guardians have two children.
                if index == 0 and previous_family is not None:
                    family_name, guardians = previous_family
                    full_name = f"{full_name.split()[0]} {family_name}"
                else:
                    family_name = full_name.split()[-1]
                    guardians = self._family(family_name)
                previous_family = (family_name, guardians)

                applicant = self._applicant(full_name, guardians, birth_year)
                applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
                student = applicant.progress_to_student()
                student.enroll(
                    academic_year=year,
                    class_grade=section.class_grade,
                    section=section,
                    start_date=year.start_date,
                )
                students[section.pk].append(student)
        return students

    def _applicants_without_students(self):
        """Applicants still in the admissions pipeline, for the admissions screens."""
        for status in [
            Applicant.AdmissionStatus.PENDING,
            Applicant.AdmissionStatus.PENDING,
            Applicant.AdmissionStatus.PENDING,
            Applicant.AdmissionStatus.ACCEPTED,
            Applicant.AdmissionStatus.REJECTED,
        ]:
            full_name = next(self.name_pool)
            applicant = self._applicant(
                full_name, self._family(full_name.split()[-1]), self.today.year - 6
            )
            if status != Applicant.AdmissionStatus.PENDING:
                applicant.record_admission_decision(status)

    def _transfer_one_student(self, year, sections, students):
        """Move one Grade 1-A student to Grade 1-B partway through the attendance window.

        Shows effective-dated enrollment: the student appears on 1-A registers
        before the transfer date and on 1-B registers from it.
        """
        days = self._attendance_days(year)
        if len(days) < 2:
            return
        transfer_date = days[len(days) // 2]
        source, target = sections[0], sections[1]
        student = students[source.pk].pop()
        student.enroll(
            academic_year=year,
            class_grade=target.class_grade,
            section=target,
            start_date=transfer_date,
        )
        students[target.pk].append(student)

    # -- attendance --------------------------------------------------------

    def _attendance_days(self, year):
        """The last ATTENDANCE_DAYS instructional days up to and including today."""
        days = []
        day = self.today
        while len(days) < ATTENDANCE_DAYS and day >= year.start_date:
            if year.is_instructional_day(day):
                days.append(day)
            day -= datetime.timedelta(days=1)
        return sorted(days)

    def _attendance(self, year, sections, admin):
        """Recent attendance in every state the app distinguishes.

        Every Section is SUBMITTED for every earlier day. On the latest day,
        the first half of the Sections is SUBMITTED, the next one is a
        half-filled DRAFT, and the rest are NOT TAKEN. One submitted entry on
        the earliest day gets an audited correction.
        """
        days = self._attendance_days(year)
        if not days:
            return
        latest = days[-1]
        draft_section = sections[len(sections) // 2]
        not_taken = {s.pk for s in sections[len(sections) // 2 + 1 :]}
        corrected = False

        for day in days:
            for section in sections:
                if day == latest and section.pk in not_taken:
                    continue
                register = AttendanceRegister(
                    academic_year=year,
                    class_grade=section.class_grade,
                    section=section,
                    date=day,
                )
                register.full_clean()
                register.save()
                roster = list(register.eligible_enrollments())
                is_draft = day == latest and section.pk == draft_section.pk
                if is_draft:
                    roster = roster[: len(roster) // 2]
                for enrollment in roster:
                    if self.rng.random() < ABSENCE_RATE:
                        register.capture(
                            enrollment=enrollment,
                            status=AttendanceStatus.ABSENT,
                            absence_note=self.rng.choice(ABSENCE_NOTES),
                        )
                    else:
                        register.capture(enrollment=enrollment, status=AttendanceStatus.PRESENT)
                if is_draft:
                    continue
                register.submit(actor=admin)

                if not corrected:
                    entry = register.entries.order_by("pk").first()
                    new_status = (
                        AttendanceStatus.ABSENT
                        if entry.status == AttendanceStatus.PRESENT
                        else AttendanceStatus.PRESENT
                    )
                    entry.record_status_change(
                        new_status,
                        actor=admin,
                        reason="Teacher confirmed the original mark was a mistake.",
                    )
                    corrected = True
