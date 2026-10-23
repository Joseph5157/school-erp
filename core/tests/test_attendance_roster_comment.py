"""The shared roster partial's developer comment never renders, and its controls are unchanged.

`core/_attendance_capture_table.html` used to open with a two-line `{# ... #}`. Django only
treats single-line `{# #}` as a comment, so the text (and a raw `<form id=...>`) rendered visibly
above the roster on both the Admin register page and the Teacher Attendance page.
"""

from datetime import date
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister, AttendanceStatus, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)
LEAKED = (
    "{#", "#}", "{% comment", "Roster for a DRAFT register", "Include inside",
    "autosave_url (teacher page)", "the form stays the full fallback",
)


class RosterFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")

    def assert_no_leak(self, content):
        for text in LEAKED:
            with self.subTest(leaked=text):
                self.assertNotIn(text, content)

    def assert_roster_controls(self, content, form_open):
        """Everything the partial is responsible for, shared by Admin and Teacher pages."""
        form = content.split(form_open)[1].split("</form>")[0]
        self.assertEqual(form.count('name="csrfmiddlewaretoken"'), 1)
        self.assertIn("data-erp-roster", form)
        for enrollment in (self.asha, self.ravi):
            for value in ("PRESENT", "ABSENT"):
                self.assertIn(f'name="status_{enrollment.pk}" value="{value}"', form)
            self.assertIn(f'name="note_{enrollment.pk}"', form)
        self.assertIn('name="action" value="save"', form)
        self.assertIn('name="action" value="submit"', form)
        self.assertEqual(form.count("<fieldset"), 2)
        return form


class AdminRosterTests(RosterFixture, TestCase):
    def setUp(self):
        self.build()
        self.client.login(username="admin", password="pass-12345")
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY)
        self.register.save_draft_entry(enrollment=self.asha, status=AttendanceStatus.ABSENT,
                                       absence_note="ill")
        self.url = reverse("core:attendance-register-detail", args=[self.register.pk])

    def test_comment_text_is_not_rendered_on_the_admin_register_page(self):
        self.assert_no_leak(self.client.get(self.url).content.decode())

    def test_admin_roster_controls_form_and_actions_are_intact(self):
        content = self.client.get(self.url).content.decode()
        capture = reverse("core:attendance-capture", args=[self.register.pk])
        opener = f'<form method="post" action="{capture}" id="attendance-capture">'
        form = self.assert_roster_controls(content, opener)
        self.assertEqual(content.count('id="attendance-capture"'), 1)
        self.assertEqual(content.count("<form"), content.count("</form>"))
        self.assertNotIn("hx-post", form)  # the Admin page has no autosave
        self.assertIn("Submitting requires Present or Absent for every Student.", form)

    def test_view_only_admin_page_has_no_roster_and_no_leak(self):
        user = get_user_model().objects.create_user("viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_attendanceregister"))
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        content = client.get(self.url).content.decode()
        self.assert_no_leak(content)
        self.assertNotIn("data-erp-roster", content)


class TeacherRosterTests(RosterFixture, TestCase):
    def setUp(self):
        self.build()
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year, section=self.six_a,
                                   start_date=date(2026, 6, 1))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.teacher.post(self.url, {"action": "open"})
        self.autosave = reverse("core:my-attendance-autosave", args=[self.six_a.pk])

    def test_comment_text_is_not_rendered_on_the_teacher_attendance_page(self):
        self.assert_no_leak(self.teacher.get(self.url).content.decode())

    def test_teacher_roster_keeps_its_htmx_autosave_attributes_csrf_and_actions(self):
        content = self.teacher.get(self.url).content.decode()
        form = self.assert_roster_controls(content, '<form method="post" id="attendance-capture"')
        self.assertIn("hx-headers=", content.split('id="attendance-capture"')[1].split(">")[0])
        self.assertEqual(form.count(f'hx-post="{self.autosave}"'), 2)
        for attribute in ('hx-trigger="change"', 'hx-include="this"',
                          'hx-target="find [data-erp-row-status]"', 'hx-swap="innerHTML"',
                          'hx-sync="this:queue last"'):
            self.assertEqual(form.count(attribute), 2, attribute)
        for enrollment in (self.asha, self.ravi):
            self.assertIn(f'hx-vals=\'{{"enrollment": {enrollment.pk}}}\'', form)
        self.assertIn("data-erp-wait-message hidden", form)
        self.assertIn("data-erp-autosave-announce", form)
        self.assertEqual(content.count("<form"), content.count("</form>"))


class PartialSourceTests(TestCase):
    def test_partial_has_no_hash_comment_and_uses_balanced_comment_tags(self):
        source = (Path(settings.BASE_DIR) / "core" / "templates" / "core"
                  / "_attendance_capture_table.html").read_text(encoding="utf-8")
        self.assertNotIn("{#", source)
        self.assertTrue(source.lstrip().startswith("{% comment %}"))
        self.assertEqual(source.count("{% comment %}"), source.count("{% endcomment %}"))
