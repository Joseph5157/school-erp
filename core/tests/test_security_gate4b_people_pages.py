"""Security Gate 4B: people pages show a class of personal data only to holders of its permission.

Student pages need `view_guardian` to show guardians (and to search by them), and
`view_attendanceentry` for attendance; guardian pages need `view_student` / `view_applicant`
for children; a teacher workload page is only for teacher accounts. The unauthorised data is
removed from the query and the page context, not only from the HTML, and the permission is
honoured whether held directly or through a group.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, ApplicantGuardian, Guardian
from core.tests.gate4b_support import GUARDIAN_EMAIL, GUARDIAN_PHONE, client_with, holders
from core.tests.test_phase7_alerts import AlertFixture

STUDENT_LIST = reverse("core:student-list")
GUARDIAN_LIST = reverse("core:guardian-list")
VIEW_STUDENT = "core.view_student"
VIEW_GUARDIAN = "core.view_guardian"
VIEW_APPLICANT = "core.view_applicant"
VIEW_ATTENDANCE = "core.view_attendanceentry"


class PeopleFixture(AlertFixture):
    """Asha and Ravi (Meena's children) and Bina (Other Parent's), with contact details."""

    def setUp(self):
        super().setUp()
        Guardian.objects.filter(pk=self.meena.pk).update(
            phone=GUARDIAN_PHONE, email=GUARDIAN_EMAIL
        )
        self.pending = Applicant.objects.create(admission_status="PENDING", full_name="Pending Child")
        ApplicantGuardian.objects.create(
            applicant=self.pending, guardian=self.meena, relationship_type="MOTHER"
        )

    def three_absences_for_asha(self):
        for day in (date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)):
            self.register(day)

    def detail(self, student=None):
        return reverse("core:student-detail", args=[(student or self.asha).pk])


class StudentListTests(PeopleFixture, TestCase):
    def test_guardian_data_needs_view_guardian(self):
        for how, client in holders(self.client_class, VIEW_STUDENT):
            with self.subTest(how=how):
                page = client.get(STUDENT_LIST)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Asha Rao")
                self.assertNotContains(page, "Meena Rao")
                self.assertNotContains(page, "Other Parent")
                self.assertFalse(
                    any(getattr(row, "guardian_rows", None) for row in page.context["students"])
                )

    def test_search_cannot_reach_guardian_fields_without_view_guardian(self):
        for how, client in holders(self.client_class, VIEW_STUDENT):
            for term in ("Meena", "Other Parent", GUARDIAN_PHONE, GUARDIAN_EMAIL):
                with self.subTest(how=how, term=term):
                    page = client.get(STUDENT_LIST, {"q": term})
                    self.assertEqual(page.status_code, 200)
                    for name in ("Asha Rao", "Ravi Rao", "Bina Other"):
                        self.assertNotContains(page, name)

    def test_holders_of_view_guardian_see_and_search_guardians(self):
        for how, client in holders(self.client_class, VIEW_STUDENT, VIEW_GUARDIAN):
            with self.subTest(how=how):
                page = client.get(STUDENT_LIST)
                self.assertContains(page, "Meena Rao")
                self.assertContains(page, "Other Parent")
                found = client.get(STUDENT_LIST, {"q": "Meena"})
                self.assertContains(found, "Asha Rao")
                self.assertContains(found, "Ravi Rao")
                self.assertNotContains(found, "Bina Other")
                by_phone = client.get(STUDENT_LIST, {"q": GUARDIAN_PHONE})
                self.assertContains(by_phone, "Asha Rao")

    def test_absent_filter_needs_view_attendanceentry(self):
        self.three_absences_for_asha()
        for how, client in holders(self.client_class, VIEW_STUDENT):
            with self.subTest(how=how):
                page = client.get(STUDENT_LIST, {"chip": "absent"})
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, "Absent 3+ days")  # the chip is not offered
                # The filter is ignored, so it cannot reveal who has been absent.
                for name in ("Asha Rao", "Ravi Rao", "Bina Other"):
                    self.assertContains(page, name)

    def test_holders_of_view_attendanceentry_get_the_absent_filter(self):
        self.three_absences_for_asha()
        for how, client in holders(self.client_class, VIEW_STUDENT, VIEW_ATTENDANCE):
            with self.subTest(how=how):
                page = client.get(STUDENT_LIST, {"chip": "absent"})
                self.assertContains(page, "Absent 3+ days")
                self.assertContains(page, "Asha Rao")
                self.assertNotContains(page, "Bina Other")
                self.assertNotContains(page, "Ravi Rao")


class StudentDetailTests(PeopleFixture, TestCase):
    def test_guardians_and_attendance_are_hidden_without_their_permissions(self):
        self.register()
        for how, client in holders(self.client_class, VIEW_STUDENT):
            with self.subTest(how=how):
                page = client.get(self.detail())
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, "Meena Rao")
                self.assertNotContains(page, 'id="guardians"')
                self.assertNotContains(page, "Attendance by month")
                self.assertEqual(list(page.context["guardian_links"]), [])
                self.assertEqual(list(page.context["ended_links"]), [])
                self.assertNotIn("guardians", page.context["profile_section_ids"])
                self.assertIsNone(page.context["attendance_months"])

    def test_view_guardian_shows_the_guardians_section(self):
        for how, client in holders(self.client_class, VIEW_STUDENT, VIEW_GUARDIAN):
            with self.subTest(how=how):
                page = client.get(self.detail())
                self.assertContains(page, "Meena Rao")
                self.assertContains(page, 'id="guardians"')
                self.assertNotContains(page, "Attendance by month")

    def test_view_attendanceentry_shows_the_monthly_card(self):
        self.register()
        for how, client in holders(self.client_class, VIEW_STUDENT, VIEW_ATTENDANCE):
            with self.subTest(how=how):
                page = client.get(self.detail())
                self.assertContains(page, "Attendance by month")
                self.assertNotContains(page, "Meena Rao")


class ApplicantDetailTests(PeopleFixture, TestCase):
    def url(self):
        return reverse("core:applicant-detail", args=[self.pending.pk])

    def test_guardians_need_view_guardian(self):
        for how, client in holders(self.client_class, VIEW_APPLICANT):
            with self.subTest(how=how):
                page = client.get(self.url())
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Pending Child")
                self.assertNotContains(page, "Meena Rao")
                self.assertEqual(list(page.context["guardian_links"]), [])

    def test_view_guardian_shows_them(self):
        for how, client in holders(self.client_class, VIEW_APPLICANT, VIEW_GUARDIAN):
            with self.subTest(how=how):
                self.assertContains(client.get(self.url()), "Meena Rao")


class GuardianListTests(PeopleFixture, TestCase):
    def test_children_need_view_student_and_view_applicant(self):
        for how, client in holders(self.client_class, VIEW_GUARDIAN):
            with self.subTest(how=how):
                page = client.get(GUARDIAN_LIST)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Meena Rao")
                for child in ("Asha Rao", "Ravi Rao", "Bina Other", "Pending Child"):
                    self.assertNotContains(page, child)
                for guardian in page.context["guardians"]:
                    self.assertEqual(list(guardian.child_links), [])
                    self.assertEqual(list(guardian.applicant_child_links), [])

    def test_search_cannot_match_children_without_their_permissions(self):
        for how, client in holders(self.client_class, VIEW_GUARDIAN):
            for term in ("Asha", "Ravi", "Bina", "Pending"):
                with self.subTest(how=how, term=term):
                    page = client.get(GUARDIAN_LIST, {"q": term})
                    self.assertEqual(page.status_code, 200)
                    self.assertNotContains(page, "Meena Rao")
                    self.assertNotContains(page, "Other Parent")

    def test_holders_of_the_child_permissions_see_and_search_children(self):
        for how, client in holders(self.client_class, VIEW_GUARDIAN, VIEW_STUDENT, VIEW_APPLICANT):
            with self.subTest(how=how):
                page = client.get(GUARDIAN_LIST)
                for child in ("Asha Rao", "Ravi Rao", "Bina Other", "Pending Child"):
                    self.assertContains(page, child)
                self.assertContains(client.get(GUARDIAN_LIST, {"q": "Asha"}), "Meena Rao")
                self.assertContains(client.get(GUARDIAN_LIST, {"q": "Pending"}), "Meena Rao")

    def test_students_and_applicants_are_separate_permissions(self):
        students_only = client_with(self.client_class, VIEW_GUARDIAN, VIEW_STUDENT)
        page = students_only.get(GUARDIAN_LIST)
        self.assertContains(page, "Asha Rao")
        self.assertNotContains(page, "Pending Child")
        self.assertNotContains(students_only.get(GUARDIAN_LIST, {"q": "Pending"}), "Meena Rao")


class DuplicateGuardianWarningTests(PeopleFixture, TestCase):
    """The add-Guardian duplicate warning lists linked children, so it follows the same rule."""

    def post(self, client):
        return client.post(
            reverse("core:guardian-create"),
            {"full_name": "Meena R", "phone": GUARDIAN_PHONE, "email": ""},
        )

    def test_linked_children_need_the_child_permissions(self):
        for how, client in holders(self.client_class, "core.add_guardian", VIEW_GUARDIAN):
            with self.subTest(how=how):
                page = self.post(client)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Possible duplicate")
                self.assertContains(page, "Meena Rao")
                self.assertNotContains(page, "Asha Rao")
                self.assertNotContains(page, "Pending Child")

    def test_holders_of_the_child_permissions_see_them(self):
        perms = ("core.add_guardian", VIEW_GUARDIAN, VIEW_STUDENT, VIEW_APPLICANT)
        for how, client in holders(self.client_class, *perms):
            with self.subTest(how=how):
                page = self.post(client)
                self.assertContains(page, "Asha Rao")
                self.assertContains(page, "Pending Child")


class TeacherLoadTests(PeopleFixture, TestCase):
    """Teacher workload is for teacher accounts only, not any login by primary key."""

    PERM = "core.view_sectionclassteacher"

    def load(self, client, user):
        return client.get(reverse("core:teacher-load", args=[user.pk]))

    def test_other_kinds_of_login_are_not_found(self):
        self.assign(self.rao, self.maths, self.six_a)
        for how, client in holders(self.client_class, self.PERM):
            with self.subTest(how=how):
                for label, user in (("guardian login", self.user), ("administrator", self.admin)):
                    with self.subTest(login=label):
                        response = self.load(client, user)
                        self.assertEqual(response.status_code, 404)
                        self.assertNotContains(response, user.username, status_code=404)

    def test_a_teacher_can_be_opened_with_or_without_assignments(self):
        self.assign(self.rao, self.maths, self.six_a)
        for how, client in holders(self.client_class, self.PERM):
            with self.subTest(how=how):
                self.assertContains(self.load(client, self.rao), "rao")
                self.assertContains(self.load(client, self.iyer), "iyer")

    def test_a_former_teacher_with_assignments_can_still_be_opened(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.rao.groups.clear()
        for how, client in holders(self.client_class, self.PERM):
            with self.subTest(how=how):
                page = self.load(client, self.rao)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Not an active teacher")

    def test_a_login_that_is_both_teacher_and_guardian_is_still_reachable(self):
        self.user.groups.add(self.teachers)
        for how, client in holders(self.client_class, self.PERM):
            with self.subTest(how=how):
                self.assertEqual(self.load(client, self.user).status_code, 200)
