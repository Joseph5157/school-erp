"""Security Gate 4B: pages that are deliberate bundles expose a pinned, limited set of data.

Three screens show data under their own permission on purpose (see docs/PERMISSIONS.md):

* the message queue (`send_notification`) shows who a message is for and its text;
* the guardian access reviews (`view_guardianaccessreview`) show which guardian and student
  an access decision is about;
* the teacher page (`manage_teacher_accounts`) shows that teacher's last ten security events.

These tests pin exactly that, so a later change cannot quietly add contact details, admission
numbers, dates of birth or other people's records to them.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core.models import Applicant, Guardian, Student
from core.tests.gate4b_support import GUARDIAN_EMAIL, GUARDIAN_PHONE, holders
from core.tests.test_phase7_alerts import AlertFixture

SECRET_ADMISSION = "ADM-SECRET-9"
SECRET_STUDENT_EMAIL = "asha.private@example.test"
SECRET_STUDENT_PHONE = "9000011111"


class BundleFixture(AlertFixture):
    def setUp(self):
        super().setUp()
        Guardian.objects.filter(pk=self.meena.pk).update(
            phone=GUARDIAN_PHONE, email=GUARDIAN_EMAIL
        )
        Student.objects.filter(pk=self.asha.pk).update(
            admission_number=SECRET_ADMISSION, email=SECRET_STUDENT_EMAIL,
            phone=SECRET_STUDENT_PHONE, date_of_birth="2013-02-14",
        )

    # What no bundle page may show: contact details, identifiers, dates of birth.
    SENSITIVE = (
        GUARDIAN_PHONE, GUARDIAN_EMAIL, SECRET_ADMISSION, SECRET_STUDENT_EMAIL,
        SECRET_STUDENT_PHONE, "2013-02-14", "14 Feb 2013", "14/02/2013", "Feb. 14, 2013",
    )

    def assert_no_sensitive(self, page):
        for value in self.SENSITIVE:
            with self.subTest(sensitive=value):
                self.assertNotContains(page, value)


class MessageQueueBundleTests(BundleFixture, TestCase):
    def test_the_queue_shows_the_guardian_the_kind_and_the_message_only(self):
        self.register()
        for how, client in holders(self.client_class, "core.send_notification"):
            with self.subTest(how=how):
                page = client.get(reverse("core:notifications-to-send"))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Meena Rao")  # who it is for
                self.assertContains(page, "Absence alert")  # what kind
                self.assertContains(page, "Asha")  # the child's first name, inside the text
                self.assert_no_sensitive(page)
                self.assertNotContains(page, "Asha Rao")  # never the full student name
                self.assertNotContains(page, "wa.me")  # the address comes only from the POST

    def test_each_row_carries_only_the_message_its_text_and_whether_it_can_be_opened(self):
        self.register()
        client = holders(self.client_class, "core.send_notification")[0][1]
        rows = client.get(reverse("core:notifications-to-send")).context["rows"]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row), {"notification", "text", "can_open"})


class AccessReviewBundleTests(BundleFixture, TestCase):
    def pending_review(self):
        unplaced = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Unplaced"),
            full_name="Unplaced Child", admission_number="ADM-UNPLACED-1",
            email="unplaced.private@example.test", phone="9000022222", date_of_birth="2014-05-06",
        )
        grant = ga.grant_student_access(
            student_guardian=self.relate(unplaced, self.meena), actor=self.admin
        )
        return unplaced, grant

    def test_the_review_page_names_the_guardian_and_student_and_nothing_more(self):
        self.pending_review()
        for how, client in holders(self.client_class, "core.view_guardianaccessreview"):
            with self.subTest(how=how):
                page = client.get(reverse("core:guardian-access-reviews"))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Unplaced Child")
                self.assertContains(page, "Meena Rao")
                self.assert_no_sensitive(page)
                for private in ("ADM-UNPLACED-1", "unplaced.private@example.test",
                                "9000022222", "2014-05-06", "6 May 2014", "06/05/2014"):
                    self.assertNotContains(page, private)
                self.assertNotContains(page, "Asha Rao")  # a different child, not under review


class TeacherEventsBundleTests(BundleFixture, TestCase):
    def test_the_teacher_page_shows_only_that_teachers_last_ten_events(self):
        for _ in range(12):
            SecurityEvent.record(
                SecurityEvent.EventType.PASSWORD_RESET_BY_ADMIN, actor=self.admin,
                subject_user=self.iyer,
            )
        SecurityEvent.record(
            SecurityEvent.EventType.PASSWORD_RESET_BY_ADMIN, actor=self.admin,
            subject_user=self.rao,
        )
        for how, client in holders(self.client_class, "accounts.manage_teacher_accounts"):
            with self.subTest(how=how):
                page = client.get(reverse("core:teacher-detail", args=[self.iyer.pk]))
                self.assertEqual(page.status_code, 200)
                events = list(page.context["events"])
                self.assertEqual(len(events), 10)
                self.assertTrue(all(event.subject_user_id == self.iyer.pk for event in events))
