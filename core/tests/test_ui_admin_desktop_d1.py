"""UI-D1-1: Teacher assignment History reads as stacked entries; access and actions unchanged."""

import re
from datetime import date

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import TestCase

from core.tests.test_subject_teacher_admin import YEAR_START, AdminFixture


class TeacherAssignmentHistoryLayoutTests(AdminFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.past = self.assign_on(self.rao, YEAR_START)
        self.current = self.assign_on(self.iyer, date(2026, 10, 1))
        self.planned = self.assign_on(self.rao, date(2026, 12, 1))

    def history_cell(self, content):
        return content.split('class="erp-assignment-history-cell"')[1].split("</td>")[0]

    def test_headers_are_scoped_and_the_action_column_is_named(self):
        content = self.client.get(self.list_url).content.decode()
        self.assertIn('class="table erp-assignments-table"', content)
        self.assertEqual(content.count('<th scope="col">'), 6)
        self.assertIn('<span class="visually-hidden">Actions</span>', content)
        self.assertIn('role="region" aria-label="Teacher assignments" tabindex="0"', content)

    def test_every_history_entry_is_kept_with_status_teacher_and_dates(self):
        cell = self.history_cell(self.client.get(self.list_url).content.decode())
        self.assertEqual(cell.count('<li class="erp-assignment-entry">'), 3)
        statuses = re.findall(r'class="badge [^"]+">([^<]+)</span>', cell)
        self.assertEqual(statuses, ["Past", "Current", "Starting soon"])
        self.assertEqual(cell.count('class="erp-assignment-teacher"'), 3)
        # Date tokens never wrap internally; the open-ended label is kept.
        self.assertIn('<span class="text-nowrap">1 Jun 2026</span> &ndash; '
                      '<span class="text-nowrap">30 Sep 2026</span>', cell)
        self.assertIn('<span class="text-nowrap">open-ended</span>', cell)

    def test_actions_sit_on_their_own_line_only_where_permitted(self):
        cell = self.history_cell(self.client.get(self.list_url).content.decode())
        self.assertEqual(cell.count('class="erp-assignment-actions"'), 2)  # the past row has none
        self.assertNotIn(self.end_url(self.past), cell)
        self.assertIn(self.end_url(self.current), cell)
        self.assertNotIn(self.delete_url(self.current), cell)
        self.assertIn(f'<form method="post" action="{self.delete_url(self.planned)}"', cell)

    def test_viewer_without_change_permissions_sees_history_but_no_actions(self):
        viewer = self.make_user("viewer", self.admins)
        self.admins.permissions.remove(*Permission.objects.filter(codename__in=(
            "add_assessmentteacherassignment", "change_assessmentteacherassignment",
            "delete_assessmentteacherassignment",
        )))
        viewer_client = self.client_class()
        viewer_client.login(username=viewer.username, password="pass-12345")
        content = viewer_client.get(self.list_url).content.decode()
        cell = self.history_cell(content)
        self.assertEqual(cell.count('<li class="erp-assignment-entry">'), 3)
        self.assertNotIn("erp-assignment-actions", cell)
        self.assertNotIn("Reassign", content)

    def test_stylesheet_keeps_a_history_floor_and_a_phone_cap(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css[css.index("UI-D1-1: teacher assignment history"):]
        self.assertIn(".erp-assignments-table .erp-assignment-history-cell { min-width: 17rem; }", block)
        self.assertIn("@media (max-width: 575.98px) { .erp-assignment-history { max-width: 18rem; } }", block)
        # Names must not break mid-word.
        self.assertNotIn("overflow-wrap: anywhere", block)
