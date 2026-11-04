"""Save and submit stops at a confirmation page; only that page's POST submits."""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister, School, SectionClassTeacher
from core.navigation import TEACHER_TAB_PARENTS
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()
MONDAY = date(2026, 10, 12)
CONFIRM_BUTTON = "Confirm and submit attendance"


class SubmitConfirmFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for target in ("core.views.business_today", "core.models.business_today"):
            patcher = mock.patch(target, new=lambda: MONDAY)
            patcher.start()
            self.addCleanup(patcher.stop)
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.six_a.class_grade,
            section=self.six_a, date=MONDAY,
        )

    def marks(self, action="submit", asha="PRESENT", ravi="ABSENT", note=""):
        data = {"action": action}
        if asha:
            data[f"status_{self.asha.pk}"] = asha
        if ravi:
            data[f"status_{self.ravi.pk}"] = ravi
        if note:
            data[f"note_{self.ravi.pk}"] = note
        return data

    def assert_draft(self):
        self.register.refresh_from_db()
        self.assertFalse(self.register.is_submitted)

    def assert_submitted_by(self, user):
        self.register.refresh_from_db()
        self.assertTrue(self.register.is_submitted)
        self.assertEqual(self.register.submitted_by, user)


class AdminSubmitConfirmTests(SubmitConfirmFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.office_user = User.objects.create_user("office", password="pass-12345")
        self.office_user.groups.add(Group.objects.get(name="School Administrators"))
        self.office = self.client_class()
        self.office.login(username="office", password="pass-12345")
        self.capture_url = reverse("core:attendance-capture", args=[self.register.pk])
        self.confirm_url = reverse("core:attendance-register-submit", args=[self.register.pk])
        self.detail_url = reverse("core:attendance-register-detail", args=[self.register.pk])

    def test_save_and_submit_saves_the_draft_and_opens_the_confirmation(self):
        response = self.office.post(self.capture_url, self.marks())

        self.assertRedirects(response, self.confirm_url)
        self.assert_draft()
        self.assertEqual(self.register.entries.count(), 2)

    def test_confirmation_page_shows_context_counts_and_notes(self):
        self.office.post(self.capture_url, self.marks(note="Fever"))
        page = self.office.get(self.confirm_url)

        self.assertContains(page, CONFIRM_BUTTON)
        self.assertContains(page, str(self.six_a))
        self.assertContains(page, "Monday, 12 October 2026")
        self.assertEqual(
            page.context["summary"], {"total": 2, "present": 1, "absent": 1, "notes": 1}
        )
        self.assertContains(page, "All 2 students are marked.")
        self.assertContains(page, "through a correction")
        self.assertContains(page, f'href="{self.detail_url}"')
        self.assert_draft()

    def test_confirming_submits_with_the_user_recorded(self):
        self.office.post(self.capture_url, self.marks())
        response = self.office.post(self.confirm_url, follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "Attendance submitted.")
        self.assert_submitted_by(self.office_user)

    def test_incomplete_register_returns_to_roster_with_draft_kept(self):
        response = self.office.post(self.capture_url, self.marks(ravi=""), follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "Draft saved but not submitted.")
        self.assertContains(response, "Attendance is incomplete")
        self.assert_draft()
        self.assertEqual(self.register.entries.count(), 1)

    def test_opening_confirmation_for_an_incomplete_register_goes_back(self):
        response = self.office.get(self.confirm_url, follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "Attendance is incomplete")
        self.assertNotContains(response, CONFIRM_BUTTON)

    def test_confirmation_for_a_submitted_register_goes_to_the_register(self):
        self.office.post(self.capture_url, self.marks())
        self.office.post(self.confirm_url)
        response = self.office.get(self.confirm_url, follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertNotContains(response, CONFIRM_BUTTON)

    def test_second_confirm_does_not_change_the_submission(self):
        self.office.post(self.capture_url, self.marks())
        self.office.post(self.confirm_url)
        submitted_at = AttendanceRegister.objects.get(pk=self.register.pk).submitted_at
        response = self.office.post(self.confirm_url, follow=True)

        self.assertContains(response, "already been submitted")
        self.assertEqual(
            AttendanceRegister.objects.get(pk=self.register.pk).submitted_at, submitted_at
        )

    def test_capture_only_user_stays_on_the_register_without_a_confirmation(self):
        self.office_user.groups.clear()
        self.office_user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=("view_attendanceregister", "add_attendanceentry")
            )
        )
        response = self.office.post(self.capture_url, self.marks(), follow=True)

        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "You do not have permission to submit.")
        self.assertEqual(self.office.get(self.confirm_url).status_code, 403)

    def test_save_draft_does_not_open_the_confirmation(self):
        response = self.office.post(self.capture_url, self.marks(action="save"))

        self.assertRedirects(response, self.detail_url)
        self.assert_draft()

    def test_alert_line_shows_only_when_alerts_will_be_prepared(self):
        self.office.post(self.capture_url, self.marks())
        self.assertNotContains(self.office.get(self.confirm_url), "Absence messages")

        School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST
        )
        self.assertContains(
            self.office.get(self.confirm_url),
            "Absence messages for 1 student will be prepared for office staff to send, "
            "where a guardian has portal access.",
        )

    def test_no_alert_line_when_nobody_is_absent(self):
        School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST
        )
        self.office.post(self.capture_url, self.marks(ravi="PRESENT"))

        self.assertNotContains(self.office.get(self.confirm_url), "Absence messages")


class TeacherSubmitConfirmTests(SubmitConfirmFixture, TestCase):
    def setUp(self):
        super().setUp()
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.confirm_url = reverse("core:my-attendance-submit", args=[self.six_a.pk])

    def test_save_and_submit_opens_the_confirmation_without_submitting(self):
        response = self.teacher.post(self.url, self.marks())

        self.assertRedirects(response, self.confirm_url)
        self.assert_draft()
        self.assertEqual(self.register.entries.count(), 2)

    def test_confirmation_page_links_back_and_names_who_corrects(self):
        self.teacher.post(self.url, self.marks(note="Fever"))
        page = self.teacher.get(self.confirm_url)

        self.assertContains(page, CONFIRM_BUTTON)
        self.assertEqual(
            page.context["summary"], {"total": 2, "present": 1, "absent": 1, "notes": 1}
        )
        self.assertContains(page, f'href="{self.url}"')
        self.assertContains(page, "an administrator")
        self.assert_draft()

    def test_confirming_submits_and_returns_to_the_attendance_page(self):
        self.teacher.post(self.url, self.marks())
        response = self.teacher.post(self.confirm_url, follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, "Attendance saved and submitted.")
        self.assert_submitted_by(self.rao)

    def test_incomplete_register_stays_on_the_attendance_page(self):
        response = self.teacher.post(self.url, self.marks(ravi=""), follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, "Draft saved but not submitted.")
        self.assert_draft()

    def test_opening_confirmation_for_an_incomplete_register_goes_back(self):
        response = self.teacher.get(self.confirm_url, follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, "Attendance is incomplete")

    def test_confirmation_for_a_submitted_register_goes_to_the_attendance_page(self):
        self.teacher.post(self.url, self.marks())
        self.teacher.post(self.confirm_url)
        response = self.teacher.get(self.confirm_url, follow=True)

        self.assertRedirects(response, self.url)
        self.assertNotContains(response, CONFIRM_BUTTON)

    def test_another_teacher_cannot_open_or_post_the_confirmation(self):
        self.teacher.post(self.url, self.marks())
        User.objects.create_user("other", password="pass-12345")
        other = self.client_class()
        other.login(username="other", password="pass-12345")

        self.assertEqual(other.get(self.confirm_url).status_code, 403)
        self.assertEqual(other.post(self.confirm_url).status_code, 403)
        self.assert_draft()

    def test_no_register_today_is_not_found(self):
        self.register.delete()

        self.assertEqual(self.teacher.get(self.confirm_url).status_code, 404)
        self.assertEqual(self.teacher.post(self.confirm_url).status_code, 404)

    def test_confirmation_page_belongs_to_my_day(self):
        self.assertEqual(TEACHER_TAB_PARENTS["my-attendance-submit"], "my-home")


class UnsavedWarningScriptTests(TestCase):
    """The warning lives in erp.js; pin that it is wired to non-autosave rosters only."""

    def test_warning_is_only_armed_without_autosave(self):
        with open(finders.find("js/erp.js"), encoding="utf-8") as script:
            source = script.read()

        block = source.split("Unsaved-changes warning")[1].split("// Marks entry")[0]
        self.assertIn("if (!autosaveOn)", block)
        self.assertIn('"beforeunload"', block)
