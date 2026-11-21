"""Student list redesign (PR B): quick-filter chips, class/section filters,
current-placement and guardian columns, and the two empty states."""

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Max
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AcademicYear,
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Section,
    Student,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin


class StudentListFilterTests(AuthorizationClientsMixin, Phase4Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.build_phase4()
        self.url = reverse("core:student-list")

    def names(self, response):
        return [student.full_name for student in response.context["students"]]

    def place(self, name, *, class_grade=None, section=None):
        """Create and enroll a Student; return (student, enrollment)."""
        class_grade = class_grade or self.grade6
        section = section or self.six_a
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name=name),
            full_name=name,
        )
        enrollment = student.enroll(
            academic_year=self.year,
            class_grade=class_grade,
            section=section,
            start_date=date(2026, 6, 1),
        )
        return student, enrollment

    # --- quick-filter chips -------------------------------------------------

    def test_all_chip_is_active_by_default(self):
        response = self.administrator.get(self.url)
        for label in ("All", "New this month", "Not in a class", "Absent 3+ days"):
            self.assertContains(response, label)
        self.assertContains(response, 'aria-current="page">All</a>')

    def test_new_this_month_chip(self):
        self.place("Fresh Student")
        old, _ = self.place("Old Student")
        Student.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=60))

        response = self.administrator.get(self.url, {"chip": "new"})
        self.assertEqual(self.names(response), ["Fresh Student"])
        self.assertContains(response, 'aria-current="page">New this month</a>')

    def test_not_in_a_class_chip(self):
        self.place("Placed Student")
        Student.objects.create(
            applicant=Applicant.objects.create(
                admission_status="ACCEPTED", full_name="Unplaced Student"
            ),
            full_name="Unplaced Student",
        )

        response = self.administrator.get(self.url, {"chip": "unplaced"})
        self.assertEqual(self.names(response), ["Unplaced Student"])

    def test_absent_3plus_days_chip(self):
        _, enrollment = self.place("Absent Student")
        self.place("Present Student")
        for day in (1, 2, 3):
            register = AttendanceRegister.objects.create(
                academic_year=self.year, class_grade=self.grade6,
                section=self.six_a, date=date(2026, 7, day),
            )
            register.capture(enrollment=enrollment, status=AttendanceStatus.ABSENT)

        response = self.administrator.get(self.url, {"chip": "absent"})
        self.assertEqual(self.names(response), ["Absent Student"])

    def _old_year(self):
        return AcademicYear.objects.create(
            name="2024-25", start_date=date(2024, 6, 1), end_date=date(2025, 3, 31)
        )

    def test_unplaced_chip_includes_student_placed_only_in_an_old_year(self):
        self.place("Current Student")
        old_year = self._old_year()
        student = Student.objects.create(
            applicant=Applicant.objects.create(
                admission_status="ACCEPTED", full_name="Old Placement"
            ),
            full_name="Old Placement",
        )
        student.enroll(
            academic_year=old_year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2024, 6, 1),
        )

        response = self.administrator.get(self.url, {"chip": "unplaced"})
        self.assertEqual(self.names(response), ["Old Placement"])

    def test_absent_chip_ignores_absences_from_an_old_year(self):
        old_year = self._old_year()
        student = Student.objects.create(
            applicant=Applicant.objects.create(
                admission_status="ACCEPTED", full_name="Old Absences"
            ),
            full_name="Old Absences",
        )
        old_enrollment = student.enroll(
            academic_year=old_year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2024, 6, 1),
        )
        for day in (1, 2, 3):
            register = AttendanceRegister.objects.create(
                academic_year=old_year, class_grade=self.grade6,
                section=self.six_a, date=date(2024, 7, day),
            )
            register.capture(enrollment=old_enrollment, status=AttendanceStatus.ABSENT)

        response = self.administrator.get(self.url, {"chip": "absent"})
        self.assertEqual(self.names(response), [])

    def test_invalid_chip_is_ignored(self):
        self.place("Student One")
        response = self.administrator.get(self.url, {"chip": "bogus"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ["Student One"])

    # --- class and section filters -----------------------------------------

    def test_class_filter(self):
        grade7 = ClassGrade.objects.create(name="Grade 7")
        seven_a = Section.objects.create(class_grade=grade7, name="A")
        self.place("Six A", section=self.six_a)
        self.place("Seven A", class_grade=grade7, section=seven_a)

        response = self.administrator.get(self.url, {"class": grade7.pk})
        self.assertEqual(self.names(response), ["Seven A"])
        response = self.administrator.get(self.url, {"class": self.grade6.pk})
        self.assertEqual(self.names(response), ["Six A"])

    def test_section_filter(self):
        self.place("Six A", section=self.six_a)
        self.place("Six B", section=self.six_b)

        response = self.administrator.get(self.url, {"section": self.six_a.pk})
        self.assertEqual(self.names(response), ["Six A"])
        self.assertContains(response, "Six A")  # the "Grade 6 A" option label is present

    def test_invalid_class_and_section_are_ignored(self):
        self.place("Student One")
        # IDs one past the highest in use: a fixed number such as 999 can belong to
        # a real class or section on PostgreSQL, where sequences are not reset.
        missing_class = (ClassGrade.objects.aggregate(top=Max("pk"))["top"] or 0) + 1
        missing_section = (Section.objects.aggregate(top=Max("pk"))["top"] or 0) + 1
        response = self.administrator.get(
            self.url, {"class": str(missing_class), "section": str(missing_section)}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.names(response), ["Student One"])

    # --- columns ------------------------------------------------------------

    def test_table_shows_placement_admission_number_and_guardian(self):
        student, _ = self.place("Asha Rao", section=self.six_a)
        student.set_admission_number("A-001")
        StudentGuardian.objects.create(
            student=student,
            guardian=Guardian.objects.create(full_name="Rajesh Rao"),
            relationship_type="FATHER",
        )

        response = self.administrator.get(self.url)
        row = response.context["students"][0]
        self.assertEqual((row.current_class, row.current_section), ("Grade 6", "A"))
        self.assertEqual(row.guardian_rows[0].guardian.full_name, "Rajesh Rao")
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, "A-001")
        self.assertContains(response, "Rajesh Rao")
        self.assertContains(response, "(Father)")
        self.assertContains(response, "Active")

    # --- filters combined with sorting and pagination ----------------------

    def test_chip_and_sort_survive_pagination_links(self):
        for index in range(30):
            self.place(f"Student {index:02d}")
        response = self.administrator.get(self.url, {"chip": "new", "sort": "-name"})
        self.assertEqual(len(self.names(response)), 25)
        self.assertEqual(self.names(response)[0], "Student 29")
        self.assertContains(response, "chip=new")
        self.assertContains(response, "sort=-name")
        self.assertContains(response, "page=2")

    # --- empty states -------------------------------------------------------

    def test_empty_state_with_filters_offers_clear(self):
        self.place("Asha Rao")
        response = self.administrator.get(self.url, {"q": "zzz-no-match"})
        self.assertContains(response, "No students match these filters.")
        self.assertContains(response, "Clear filters")
        self.assertNotContains(response, "No Students found.")

    # --- authorization ------------------------------------------------------

    def test_teacher_cannot_open_student_list(self):
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        self.assertEqual(client.get(self.url).status_code, 403)


PINNED_TODAY = date(2026, 7, 15)


class NoPortalChipTests(AuthorizationClientsMixin, Phase4Fixture, TestCase):
    """The 'No parent on the portal' chip, the target of the home Invite links."""

    def setUp(self):
        super().setUp()
        self.build_phase4()
        self.url = reverse("core:student-list")
        self.user_model = get_user_model()
        self.verifier = self.user_model.objects.create_user(username="verifier")
        patcher = mock.patch("core.views.business_today", return_value=PINNED_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def names(self, response):
        return [student.full_name for student in response.context["students"]]

    def student(self, name, section=None):
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name=name),
            full_name=name,
        )
        student.enroll(
            academic_year=self.year, class_grade=self.grade6,
            section=section or self.six_a, start_date=date(2026, 6, 1),
        )
        return student

    def put_on_portal(self, student, username):
        guardian = Guardian.objects.create(full_name=f"Parent of {student.full_name}")
        link = StudentGuardian.objects.create(
            student=student, guardian=guardian, relationship_type="FATHER"
        )
        GuardianAccount.objects.create(
            user=self.user_model.objects.create_user(username=username),
            guardian=guardian, identity_verified_by=self.verifier,
            identity_verification_method="OTHER", identity_verification_note="x",
            created_by=self.verifier,
        )
        GuardianStudentAccess.objects.create(student_guardian=link, granted_by=self.verifier)

    def test_no_portal_chip_lists_students_without_a_portal_parent(self):
        with_parent = self.student("Has Parent")
        without = self.student("No Parent")
        self.put_on_portal(with_parent, "parent1")

        response = self.administrator.get(self.url, {"chip": "no_portal"})
        names = self.names(response)
        self.assertIn(without.full_name, names)
        self.assertNotIn(with_parent.full_name, names)
        self.assertContains(response, "No parent on the portal")

    def test_no_portal_chip_combines_with_section(self):
        self.put_on_portal(self.student("Has Parent A"), "parent2")
        self.student("No Parent A")
        self.student("No Parent B", section=self.six_b)

        response = self.administrator.get(
            self.url, {"chip": "no_portal", "section": self.six_a.pk}
        )
        self.assertEqual(self.names(response), ["No Parent A"])

    def test_no_portal_chip_needs_guardian_permission(self):
        self.put_on_portal(self.student("Has Parent"), "parent3")
        self.student("No Parent")
        user = self.user_model.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_student"))
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")

        response = client.get(self.url, {"chip": "no_portal"})
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(self.names(response), ["Has Parent", "No Parent"])
        self.assertNotContains(response, "No parent on the portal")
