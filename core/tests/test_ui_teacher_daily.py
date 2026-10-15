"""U2 teacher daily screens: take attendance, My day, attendance history."""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.forms import AttendanceCaptureForm
from core.models import AttendanceRegister, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class U2Fixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.bina = self.make_student("Bina")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def draft(self, notes=None, **statuses):
        """Open today's register and save entries, e.g. draft(asha="PRESENT")."""
        self.teacher.post(self.url, {"action": "open"})
        data = {"action": "save"}
        for name, status in statuses.items():
            data[f"status_{getattr(self, name).pk}"] = status
        for name, note in (notes or {}).items():
            data[f"note_{getattr(self, name).pk}"] = note
        self.teacher.post(self.url, data)
        return self.register()


class CaptureCountsTests(U2Fixture, TestCase):
    def test_counts_use_saved_entries(self):
        register = self.draft(asha="PRESENT", ravi="ABSENT")
        form = AttendanceCaptureForm(register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        register = self.draft(asha="PRESENT")
        data = {f"status_{self.asha.pk}": "ABSENT", f"status_{self.ravi.pk}": "ABSENT",
                f"status_{self.bina.pk}": ""}
        form = AttendanceCaptureForm(data, register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 0, "absent": 2, "unmarked": 1})


class CapturePartialTests(U2Fixture, TestCase):
    def test_post_names_and_values_unchanged(self):
        self.draft()
        page = self.teacher.get(self.url)
        for enrollment in (self.asha, self.ravi, self.bina):
            self.assertContains(page, f'name="status_{enrollment.pk}" value="PRESENT"')
            self.assertContains(page, f'name="status_{enrollment.pk}" value="ABSENT"')
            self.assertContains(page, f'name="note_{enrollment.pk}"')
        self.assertContains(page, 'name="action" value="save"')
        self.assertContains(page, 'name="action" value="submit"')

    def test_rows_are_fieldsets_named_by_student(self):
        self.draft()
        page = self.teacher.get(self.url)
        self.assertContains(page, '<legend class="erp-roster-name">Asha</legend>')
        self.assertEqual(page.content.decode().count("<fieldset"), 3)

    def test_static_counts(self):
        self.draft(asha="PRESENT", ravi="ABSENT")
        page = self.teacher.get(self.url)
        self.assertContains(page, 'data-erp-count="unmarked">1<')
        self.assertContains(page, 'data-erp-count="present">1<')
        self.assertContains(page, 'data-erp-count="absent">1<')
        self.assertContains(page, "All 3 · Unmarked 1 · Present 1 · Absent 1")
        self.assertContains(page, "1 unmarked")

    def test_saved_note_is_marked_filled(self):
        self.draft(notes={"ravi": "Fever"}, asha="PRESENT", ravi="ABSENT")
        page = self.teacher.get(self.url).content.decode()
        self.assertIn('value="Fever"', page)
        self.assertEqual(page.count('class="erp-note is-filled"'), 1)

    def test_mark_present_button_and_no_inline_script(self):
        self.draft()
        page = self.teacher.get(self.url)
        self.assertContains(page, "Mark unanswered as present")
        self.assertNotContains(page, "<script>")

    def test_office_page_uses_partial(self):
        register = self.draft(asha="PRESENT")
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertContains(page, "data-erp-roster")
        self.assertContains(page, "Marked: 1")
        self.assertContains(page, "Save and submit")

    def test_office_page_hides_submit_without_permission(self):
        register = self.draft()
        clerk = get_user_model().objects.create_user(username="clerk", password="pass-12345")
        clerk.user_permissions.add(
            Permission.objects.get(codename="view_attendanceregister"),
            Permission.objects.get(codename="add_attendanceentry"),
        )
        self.client.login(username="clerk", password="pass-12345")
        page = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertContains(page, "Save draft")
        self.assertNotContains(page, "Save and submit")


class TakeAttendancePageTests(U2Fixture, TestCase):
    def test_tab_bar_hidden_only_while_draft_open(self):
        start = self.teacher.get(self.url)
        self.assertContains(start, "Start today's register")
        self.assertContains(start, 'class="erp-tabbar')
        self.draft()
        drafting = self.teacher.get(self.url)
        self.assertNotContains(drafting, 'class="erp-tabbar')
        self.assertNotContains(drafting, "has-tabbar")
        self.assertContains(drafting, reverse("core:my-home"))
        self.assertContains(self.teacher.get(reverse("core:my-home")), 'class="erp-tabbar')

    def test_tab_bar_back_after_submit(self):
        self.draft(asha="PRESENT", ravi="PRESENT", bina="ABSENT")
        self.register().submit(actor=self.rao)
        self.assertContains(self.teacher.get(self.url), 'class="erp-tabbar')

    def test_draft_and_submitted_pills(self):
        self.draft(asha="PRESENT")
        self.assertContains(self.teacher.get(self.url),
                            '<span class="erp-pill is-draft">Draft</span>')
        self.draft(asha="PRESENT", ravi="PRESENT", bina="ABSENT")
        self.register().submit(actor=self.rao)
        page = self.teacher.get(self.url)
        self.assertContains(page, '<span class="erp-pill is-submitted">Submitted</span>')
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
        self.assertContains(page, "only be changed by an administrator")


class MyDayTests(U2Fixture, TestCase):
    def home(self):
        return self.teacher.get(reverse("core:my-home"))

    def test_not_taken_card(self):
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-pending">Not taken</span>')
        self.assertContains(page, "Take attendance")

    def test_draft_card(self):
        self.draft(asha="PRESENT")
        page = self.home()
        self.assertContains(
            page, '<span class="erp-pill is-draft">Draft &mdash; not yet submitted</span>'
        )
        self.assertContains(page, ">Continue<")

    def test_submitted_card(self):
        self.draft(asha="PRESENT", ravi="PRESENT", bina="PRESENT")
        self.register().submit(actor=self.rao)
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-submitted">Submitted</span>')
        self.assertContains(page, ">View<")

    def test_not_a_school_day_card_has_no_action(self):
        with mock.patch("core.models.AcademicYear.is_instructional_day", return_value=False):
            page = self.home()
        self.assertContains(page, '<span class="erp-pill">Not a school day</span>')
        self.assertNotContains(page, "Take attendance")

    def test_no_tables_on_my_day(self):
        self.assertNotContains(self.home(), "<table")
