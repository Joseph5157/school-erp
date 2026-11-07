"""Security Gate 4B: per-student attendance needs `view_attendanceentry`.

The register page keeps its header, workflow state and aggregate counts under
`view_attendanceregister`; student rows, individual statuses and absence notes need
`view_attendanceentry`. The Overview's absentee and attention lists need it too. The data is
withheld from the page context, and the permission is honoured directly or through a group.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.tests.gate4b_support import holders
from core.tests.test_phase7_alerts import AlertFixture

VIEW_REGISTER = "core.view_attendanceregister"
VIEW_ENTRY = "core.view_attendanceentry"
OVERVIEW = reverse("core:admin-overview")


class RegisterDetailTests(AlertFixture, TestCase):
    NOTE = "Fever, called in"

    def url(self, register):
        return reverse("core:attendance-register-detail", args=[register.pk])

    def test_student_rows_need_view_attendanceentry(self):
        register = self.register(note=self.NOTE)
        for how, client in holders(self.client_class, VIEW_REGISTER):
            with self.subTest(how=how):
                page = client.get(self.url(register))
                self.assertEqual(page.status_code, 200)
                for private in ("Asha Rao", "Bina Other", self.NOTE):
                    self.assertNotContains(page, private)
                self.assertEqual(list(page.context["entries"]), [])
                # The register itself and its aggregate count stay visible.
                self.assertEqual(page.context["register"], register)
                self.assertEqual(page.context["marked_count"], 2)
                self.assertContains(page, "Submitted attendance")

    def test_holders_of_view_attendanceentry_see_the_rows(self):
        register = self.register(note=self.NOTE)
        for how, client in holders(self.client_class, VIEW_REGISTER, VIEW_ENTRY):
            with self.subTest(how=how):
                page = client.get(self.url(register))
                for shown in ("Asha Rao", "Bina Other", self.NOTE):
                    self.assertContains(page, shown)
                self.assertEqual(len(list(page.context["entries"])), 2)


class OverviewTests(AlertFixture, TestCase):
    def three_absences_for_asha(self):
        for day in (date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)):
            self.register(day)

    # The analytics use their own copy of today's date, so ask for the October window that
    # holds the three absences; that makes "shown" and "not shown" both meaningful.
    WINDOW = {"period": "custom", "from": "2026-10-01", "to": "2026-10-31"}

    def analytics(self, client):
        page = client.get(OVERVIEW, self.WINDOW)
        self.assertEqual(page.status_code, 200)
        return page, page.context["attendance_analytics"]

    def test_absentee_list_needs_view_attendanceentry_as_well_as_view_student(self):
        self.three_absences_for_asha()
        base = ("core.view_school", "core.view_student")
        for how, client in holders(self.client_class, *base):
            with self.subTest(how=how):
                page, data = self.analytics(client)
                self.assertIsNone(data["absentees"])
                self.assertNotContains(page, "Asha Rao")
        for how, client in holders(self.client_class, "core.view_school", VIEW_ENTRY):
            with self.subTest(how=how, only="attendance"):
                _, data = self.analytics(client)
                self.assertIsNone(data["absentees"])  # names are student data too
        for how, client in holders(self.client_class, *base, VIEW_ENTRY):
            with self.subTest(how=how, holds="both"):
                page, data = self.analytics(client)
                self.assertIsNotNone(data["absentees"])
                self.assertContains(page, "Asha Rao")

    def test_attention_list_needs_attendance_as_well_as_students_and_results(self):
        self.three_absences_for_asha()
        base = ("core.view_school", "core.view_student", "core.view_studentresult")
        for how, client in holders(self.client_class, *base):
            with self.subTest(how=how):
                _, data = self.analytics(client)
                self.assertIsNone(data["attention"])
        for how, client in holders(self.client_class, *base, VIEW_ENTRY):
            with self.subTest(how=how, holds="all"):
                _, data = self.analytics(client)
                self.assertIsNotNone(data["attention"])
