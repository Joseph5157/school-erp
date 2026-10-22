"""UI-D1-3B (T2): Teacher detail adopts panels, a definition list and a labelled events region.

Data, links and permissions are unchanged. All names are synthetic.
"""

import re
from datetime import date, datetime, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SecurityEvent
from core.models import SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

LONG_NAME = "Venkataraghavan Subramaniam Ramachandran-Krishnamurthy Iyengar"
Event = SecurityEvent.EventType


class TeacherDetailD13BTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")

    def teacher(self, username="teach1", **extra):
        return self.make_user(username, self.teachers, **extra)

    def get(self, teacher, client=None):
        response = (client or self.client).get(reverse("core:teacher-detail", args=[teacher.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def url(self, name, teacher):
        return reverse(f"core:{name}", args=[teacher.pk])

    def limited_client(self, *codenames):
        user = self.make_user("limited")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="limited", password="pass-12345")
        return client

    # Shell and markup
    def test_panels_headings_and_single_h1(self):
        content = self.get(self.teacher())
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertEqual(content.count('class="erp-panel'), 4)
        for heading in ("Account", "Account actions", "Assignments", "Recent security events"):
            self.assertRegex(content, rf'<h2 class="[^"]*" id="[^"]+">{heading}</h2>')

    def test_definition_list_markup(self):
        content = self.get(self.teacher())
        self.assertIn("<dl", content)
        for label in ("Username", "Email", "Last sign-in", "Must change password"):
            self.assertIn(f'<dt class="col-sm-3">{label}</dt>', content)
        self.assertEqual(content.count('<dd class="col-sm-9">'), 4)

    def test_long_name_not_truncated(self):
        teacher = self.teacher(
            first_name="Venkataraghavan Subramaniam", last_name="Ramachandran-Krishnamurthy Iyengar"
        )
        self.assertIn(LONG_NAME, self.get(teacher))

    # Status and account actions
    def test_active_teacher_shows_active_and_deactivate_only(self):
        teacher = self.teacher()
        content = self.get(teacher)
        self.assertIn("Status: </span>Active", content)
        self.assertNotIn("Status: </span>Inactive", content)
        self.assertIn(f'href="{self.url("teacher-deactivate", teacher)}">Deactivate', content)
        self.assertNotIn(self.url("teacher-reactivate", teacher), content)
        self.assertNotIn(">Reactivate<", content)

    def test_inactive_teacher_shows_inactive_and_reactivate_only(self):
        teacher = self.teacher(is_active=False)
        content = self.get(teacher)
        self.assertIn("Status: </span>Inactive", content)
        self.assertNotIn("Status: </span>Active", content)
        self.assertIn(f'href="{self.url("teacher-reactivate", teacher)}">Reactivate', content)
        self.assertNotIn(self.url("teacher-deactivate", teacher), content)
        self.assertNotIn(">Deactivate<", content)

    def test_reset_and_username_are_plain_links_without_secrets(self):
        teacher = self.teacher()
        page = self.get(teacher)
        content = page[page.index('<main'):]  # the shell's own logout form is outside the page body
        self.assertIn(f'href="{self.url("teacher-reset-password", teacher)}">Reset password</a>', content)
        self.assertIn(f'href="{self.url("teacher-username", teacher)}">Change username</a>', content)
        self.assertNotIn("<form", content)
        self.assertNotIn("csrfmiddlewaretoken", content)
        self.assertNotIn("<button", content)
        self.assertNotIn(teacher.password, content)
        self.assertNotIn("pass-12345", content)

    # Account values
    def test_account_values(self):
        teacher = self.teacher(email="teach@example.test", must_change_password=True)
        teacher.last_login = timezone.make_aware(datetime(2026, 10, 5, 9, 30))
        teacher.save(update_fields=["last_login"])
        content = self.get(teacher)
        self.assertIn('<dd class="col-sm-9">teach1</dd>', content)
        self.assertIn('<dd class="col-sm-9">teach@example.test</dd>', content)
        self.assertIn('<dd class="col-sm-9">5 Oct 2026, 09:30</dd>', content)
        self.assertIn('<dd class="col-sm-9">Yes</dd>', content)

    def test_account_defaults(self):
        content = self.get(self.teacher(must_change_password=False))
        self.assertIn('<dd class="col-sm-9">-</dd>', content)
        self.assertIn('<dd class="col-sm-9">Never</dd>', content)
        self.assertIn('<dd class="col-sm-9">No</dd>', content)

    # Assignments
    def test_assignment_empty_states(self):
        content = self.get(self.teacher())
        self.assertEqual(content.count('<li class="text-muted">None</li>'), 2)
        self.assertIn("Subjects", content)
        self.assertIn("Class teacher", content)

    def test_subject_and_class_assignments_in_order(self):
        teacher = self.teacher()
        self.assign(teacher, self.maths, self.six_a)
        self.assign(teacher, self.sanskrit, self.six_b)
        SectionClassTeacher.objects.create(
            teacher=teacher, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1), end_date=date(2026, 9, 30),
        )
        SectionClassTeacher.objects.create(
            teacher=teacher, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 6, 1),
        )
        content = self.get(teacher)
        self.assertNotIn(">None<", content)
        subject_rows = re.findall(r"<li>(2026-27: [^<]*&middot;[^<]*)</li>", content)
        self.assertEqual(len(subject_rows), 2)
        self.assertIn("Mathematics", subject_rows[0])
        self.assertIn("Sanskrit", subject_rows[1])
        class_rows = re.findall(r"<li>(2026-27: [^<]*&ndash;[^<]*)</li>", content)
        self.assertEqual(len(class_rows), 2)
        self.assertIn("&ndash; 30 Sep 2026", class_rows[0])
        self.assertTrue(class_rows[1].endswith("&ndash; open"))
        self.assertLess(content.index("Subjects"), content.index("Class teacher"))

    def test_workload_link_requires_view_sectionclassteacher(self):
        teacher = self.teacher()
        load = self.url("teacher-load", teacher)
        self.assertIn(f'href="{load}">View full workload', self.get(teacher))
        manage_only = self.limited_client("manage_teacher_accounts")
        content = self.get(teacher, manage_only)
        self.assertNotIn(load, content)
        self.assertNotIn("View full workload", content)

    # Security events
    def test_events_table_markup_and_empty_state(self):
        content = self.get(self.teacher())
        self.assertIn('role="region" aria-label="Recent security events" tabindex="0"', content)
        self.assertIn('<caption class="visually-hidden">Recent security events</caption>', content)
        for heading in ("Event", "When", "By"):
            self.assertIn(f'<th scope="col">{heading}</th>', content)
        self.assertNotIn("<th>", content)
        self.assertIn("No events recorded.", content)

    def test_events_listed_newest_first_with_actor(self):
        teacher = self.teacher()
        SecurityEvent.objects.create(
            event_type=Event.TEACHER_ACCOUNT_CREATED, event_class="HISTORY", actor=self.admin,
            subject_user=teacher, occurred_at=timezone.now() - timedelta(days=2),
        )
        SecurityEvent.record(Event.TEACHER_PASSWORD_RESET, actor=self.admin, subject_user=teacher)
        content = self.get(teacher)
        self.assertNotIn("No events recorded.", content)
        self.assertLess(
            content.index("Teacher password reset"), content.index("Teacher account created")
        )
        self.assertIn("<td>admin</td>", content)
