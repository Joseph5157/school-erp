"""Populate an empty database with a believable working school for demos.

Grades 1-5 have two sections of six students, Grades 6-10 have one section of
ten, with Telugu-region family names written in English, ten teachers with
subject and class-teacher assignments, parent logins with student access
granted, and recent attendance. Like seed_demo, everything goes through the
domain workflows and the command refuses to run unless the school is empty.

Credentials are written to --credentials-file (CSV) and never printed.
"""

import csv
import random

from django.core.management.base import CommandError
from django.db import transaction

from core.guardian_accounts import create_guardian_account, grant_student_access
from core.management.commands import seed_demo
from core.models import (
    AcademicSubjectOffering,
    Applicant,
    AssessmentTeacherAssignment,
    ClassGrade,
    Guardian,
    GuardianAccount,
    RelationshipType,
    Section,
    SectionClassTeacher,
    StudentGuardian,
    Subject,
)
from core.teacher_accounts import create_teacher

GRADES = range(1, 11)
SECTIONS_BY_GRADE = {grade: ["A", "B"] if grade <= 5 else ["A"] for grade in GRADES}
STUDENTS_PER_SECTION = {grade: 6 if grade <= 5 else 10 for grade in GRADES}

BOYS = [
    "Aarav", "Karthik", "Sai Teja", "Venkat", "Harsha", "Charan", "Pranav", "Rohit",
    "Manoj", "Tarun", "Lokesh", "Naveen", "Vamsi", "Srikar", "Dheeraj", "Akhil",
    "Bharath", "Yashwanth", "Sandeep", "Nikhil", "Ganesh", "Rahul", "Teja", "Varun",
    "Mohan", "Jashwanth", "Hemanth", "Surya", "Kalyan", "Ajay",
]
GIRLS = [
    "Anusha", "Sravani", "Harini", "Meghana", "Divya", "Keerthi", "Lahari", "Pooja",
    "Bhavana", "Navya", "Sahithi", "Vaishnavi", "Chaitra", "Manasa", "Niharika",
    "Sindhu", "Tejaswi", "Mounika", "Hasini", "Varshini", "Anjali", "Swathi",
    "Ramya", "Pavani", "Likhitha", "Deepika", "Sowmya", "Jyothi", "Aishwarya", "Geetha",
]
SURNAMES = [
    "Reddy", "Naidu", "Rao", "Varma", "Chowdary", "Goud", "Sastry", "Raju",
    "Prasad", "Murthy", "Babu", "Yadav", "Naik", "Kumar", "Setty", "Patnaik",
]
FATHERS = [
    "Srinivas", "Ramesh", "Venkata", "Suresh", "Mahesh", "Krishna", "Ravi", "Prasad",
    "Naresh", "Sudhakar", "Anil", "Rajesh", "Gopal", "Madhav", "Satish", "Kiran",
]
MOTHERS = [
    "Lakshmi", "Padmaja", "Sujatha", "Anitha", "Swapna", "Vijaya", "Radha", "Kavitha",
    "Sunitha", "Madhavi", "Rajeswari", "Jyothi", "Savitha", "Aruna", "Durga", "Bhargavi",
]

SUBJECTS = {
    "Telugu": "TEL", "Hindi": "HIN", "English": "ENG", "Mathematics": "MAT",
    "Environmental Science": "EVS", "Science": "SCI", "Social Studies": "SOC",
    "Computer Science": "CSC",
}
PRIMARY = ["Telugu", "Hindi", "English", "Mathematics", "Environmental Science"]
SECONDARY = ["Telugu", "Hindi", "English", "Mathematics", "Science", "Social Studies"]

# (first name, last name, subject taught, grades taught)
TEACHERS = [
    ("Srinivas", "Reddy", "Mathematics", range(1, 6)),
    ("Padmaja", "Naidu", "English", range(1, 6)),
    ("Venkata", "Rao", "Mathematics", range(6, 11)),
    ("Sujatha", "Varma", "English", range(6, 11)),
    ("Lakshmi", "Devi", "Telugu", range(1, 11)),
    ("Ramesh", "Babu", "Hindi", range(1, 11)),
    ("Anitha", "Chowdary", "Environmental Science", range(1, 6)),
    ("Kiran", "Kumar", "Science", range(6, 11)),
    ("Swapna", "Goud", "Social Studies", range(6, 11)),
    ("Mahesh", "Sastry", "Computer Science", range(3, 11)),
]


def grade_of(section):
    return int(section.class_grade.name.split()[-1])


class Command(seed_demo.Command):
    help = (
        "Create a working demo school (Grades 1-10, teachers, parent logins, "
        "attendance) in an empty database."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--credentials-file",
            required=True,
            help="CSV path to write the generated logins to (role, username, password).",
        )

    def handle(self, *args, **options):
        if not seed_demo.settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("Set DJANGO_DEBUG=True or pass --allow-non-debug.")
        if ClassGrade.objects.exists() or Applicant.objects.exists():
            raise CommandError(
                "Classes or applicants already exist; this only runs on an empty school."
            )
        self.rng = random.Random(2026)
        self.demo_password = seed_demo.secrets.token_urlsafe(12)
        self.today = seed_demo.business_today()
        self.credentials = []
        self.used_names = set()
        self.used_usernames = set()

        with transaction.atomic():
            school = self._school()
            self.admin, admin_created = self._demo_admin()
            self.year = self._academic_year()
            self._calendar(self.year)
            self.sections = self._sections()
            self.students_by_section = self._students()
            self._applicants_without_students()
            self._structure_and_teachers()
            self._parent_accounts()
            self._attendance(self.year, self.sections, self.admin)

        if admin_created:
            self.credentials.insert(
                0, ("administrator", seed_demo.DEMO_ADMIN_USERNAME, self.demo_password)
            )
        with open(options["credentials_file"], "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["role", "username", "password"])
            writer.writerows(self.credentials)
        total = sum(len(v) for v in self.students_by_section.values())
        self.stdout.write(self.style.SUCCESS(f"Demo school created for {school}."))
        self.stdout.write(
            f"  {total} students, {len(TEACHERS)} teachers, "
            f"{len(self.credentials)} logins written to {options['credentials_file']}"
        )

    # -- structure ---------------------------------------------------------

    def _sections(self):
        sections = []
        for grade in GRADES:
            class_grade = ClassGrade.objects.create(name=f"Grade {grade}")
            for name in SECTIONS_BY_GRADE[grade]:
                sections.append(Section.objects.create(class_grade=class_grade, name=name))
        return sections

    # -- people ------------------------------------------------------------

    def _student_name(self, pool, family):
        for _ in range(200):
            name = f"{self.rng.choice(pool)} {family}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        raise CommandError("Ran out of unique student names.")

    def _new_family(self):
        family = self.rng.choice(SURNAMES)
        guardians = []
        for relation, first_names in (
            (RelationshipType.FATHER, FATHERS),
            (RelationshipType.MOTHER, MOTHERS),
        ):
            first = self.rng.choice(first_names)
            guardians.append((
                Guardian.objects.create(
                    full_name=f"{first} {family}",
                    phone=f"+91 9{self.rng.randint(100000000, 999999999)}",
                    email=f"{first.lower()}.{family.lower()}{self.rng.randint(10, 99)}@example.com",
                ),
                relation,
            ))
        return family, guardians

    def _students(self):
        students = {}
        siblings_left = 6  # families that reuse the previous family for a second child
        previous = None
        counter = 0
        for section in self.sections:
            grade = grade_of(section)
            students[section.pk] = []
            birth_year = self.year.start_date.year - 5 - grade
            for index in range(STUDENTS_PER_SECTION[grade]):
                if previous and siblings_left and index == 0:
                    family, guardians = previous
                    siblings_left -= 1
                else:
                    family, guardians = self._new_family()
                previous = (family, guardians)
                pool = BOYS if self.rng.random() < 0.5 else GIRLS
                applicant = self._applicant(
                    self._student_name(pool, family), guardians, birth_year
                )
                applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
                student = applicant.progress_to_student()
                student.enroll(
                    academic_year=self.year,
                    class_grade=section.class_grade,
                    section=section,
                    start_date=self.year.start_date,
                )
                counter += 1
                student.set_admission_number(f"ADM{self.year.start_date.year}-{counter:04d}")
                student.current_enrollment.set_roll_number(index + 1)
                students[section.pk].append(student)
        return students

    def _applicants_without_students(self):
        for status in [
            Applicant.AdmissionStatus.PENDING,
            Applicant.AdmissionStatus.PENDING,
            Applicant.AdmissionStatus.ACCEPTED,
            Applicant.AdmissionStatus.REJECTED,
        ]:
            family, guardians = self._new_family()
            applicant = self._applicant(
                self._student_name(self.rng.choice([BOYS, GIRLS]), family),
                guardians,
                self.today.year - 6,
            )
            if status != Applicant.AdmissionStatus.PENDING:
                rejected = status == Applicant.AdmissionStatus.REJECTED
                applicant.record_admission_decision(
                    status, reason="Seat not available." if rejected else ""
                )

    # -- subjects and teachers ---------------------------------------------

    def _structure_and_teachers(self):
        subjects = {
            name: Subject.objects.create(name=name, code=code) for name, code in SUBJECTS.items()
        }
        offerings = {}
        for grade in GRADES:
            names = list(PRIMARY if grade <= 5 else SECONDARY)
            if grade >= 3:
                names.append("Computer Science")
            class_grade = ClassGrade.objects.get(name=f"Grade {grade}")
            for position, name in enumerate(names, start=1):
                offering = AcademicSubjectOffering(
                    academic_year=self.year,
                    class_grade=class_grade,
                    subject=subjects[name],
                    display_order=position,
                )
                offering.full_clean()
                offering.save()
                offerings[(grade, name)] = offering

        teachers = []
        for first, last, subject, grades in TEACHERS:
            username = self._username(f"{first}.{last}")
            user, password = create_teacher(
                username=username,
                first_name=first,
                last_name=last,
                email=f"{username}@example.com",
                actor=self.admin,
            )
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
            self.credentials.append(("teacher", username, password))
            teachers.append((user, grades))
            for section in self.sections:
                grade = grade_of(section)
                if grade not in grades:
                    continue
                assignment = AssessmentTeacherAssignment(
                    teacher=user,
                    offering=offerings[(grade, subject)],
                    section=section,
                    start_date=self.year.start_date,
                )
                assignment.full_clean()
                assignment.save()

        # Class teachers: rotate through the teachers who teach that grade.
        for index, section in enumerate(self.sections):
            candidates = [user for user, grades in teachers if grade_of(section) in grades]
            class_teacher = SectionClassTeacher(
                teacher=candidates[index % len(candidates)],
                academic_year=self.year,
                section=section,
                start_date=self.year.start_date,
            )
            class_teacher.full_clean()
            class_teacher.save()

    # -- parent logins -----------------------------------------------------

    def _username(self, base):
        base = base.lower().replace(" ", "")
        candidate, number = base, 1
        while candidate in self.used_usernames:
            number += 1
            candidate = f"{base}{number}"
        self.used_usernames.add(candidate)
        return candidate

    def _parent_accounts(self):
        """One login per family (the father, or the mother for every fourth link)."""
        covered = set()  # guardian ids that already have a login or share one with a sibling
        families = 0
        for link in StudentGuardian.objects.select_related("guardian").order_by("pk"):
            if link.guardian_id in covered:
                continue
            families += 1
            wanted = RelationshipType.MOTHER if families % 4 == 0 else RelationshipType.FATHER
            parents = StudentGuardian.objects.filter(student=link.student).select_related("guardian")
            chosen = next((p for p in parents if p.relationship_type == wanted), link)
            covered.update(p.guardian_id for p in parents)
            guardian = chosen.guardian
            username = self._username(guardian.full_name.replace(" ", "."))
            account, password = create_guardian_account(
                guardian=guardian,
                username=username,
                method=GuardianAccount.VerificationMethod.EXISTING_RECORDS,
                note="Demo data: verified against admission records.",
                actor=self.admin,
            )
            account.user.must_change_password = False
            account.user.save(update_fields=["must_change_password"])
            self.credentials.append(("parent", username, password))
            for child_link in StudentGuardian.objects.filter(guardian=guardian):
                grant_student_access(student_guardian=child_link, actor=self.admin)
