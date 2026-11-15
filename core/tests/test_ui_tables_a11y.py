"""Tables (modern-web audit 07).

- T-02: in the Students, Teachers and Guardians tables the person's name is the row header.
- T-03: every card list keeps a phone sort control, from one shared partial (Guardians had none).
- T-01: sort headers keep a usable tap target inside panels, and the direction arrow is a
  decorative span hidden from screen readers (aria-sort already says the direction).
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import TEACHERS_GROUP_NAME, Guardian
from core.tests.test_authorization import AuthorizationClientsMixin
from core.tests.test_ui_student_phone_cards import admit

CSS = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")


class ListTablesTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = admit("Asha Rao")
        self.teacher = get_user_model().objects.create_user(username="rao", first_name="Ravi", last_name="Rao")
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        self.guardian = Guardian.objects.create(full_name="Meena Rao")

    def page(self, name):
        return self.administrator.get(reverse(name)).content.decode()

    def test_the_name_cell_is_a_row_header(self):
        for name, detail in (
            ("core:student-list", reverse("core:student-detail", args=[self.student.pk])),
            ("core:teacher-list", reverse("core:teacher-detail", args=[self.teacher.pk])),
            ("core:guardian-list", reverse("core:guardian-detail", args=[self.guardian.pk])),
        ):
            with self.subTest(page=name):
                html = self.page(name)
                row = re.search(r"<tbody>\s*<tr>\s*(<t[hd][^>]*>)", html)
                self.assertEqual(row.group(1), '<th scope="row">')
                self.assertIn(f'href="{detail}"', html)

    def test_every_card_list_has_a_phone_sort_control(self):
        for name, label in (
            ("core:student-list", "Sort students"),
            ("core:teacher-list", "Sort teachers"),
            ("core:guardian-list", "Sort guardians"),
        ):
            with self.subTest(page=name):
                html = self.page(name)
                self.assertRegex(
                    html, rf'<nav class="erp-card-sort d-md-none d-print-none" aria-label="{label}">'
                )

    def test_no_sort_control_without_results(self):
        Guardian.objects.all().delete()
        self.assertNotIn("erp-card-sort", self.page("core:guardian-list"))

    def test_the_sort_arrow_is_hidden_from_screen_readers(self):
        html = self.page("core:guardian-list")
        self.assertRegex(
            html,
            r'aria-sort="ascending">\s*<a class="erp-sort-link" href="[^"]*">Name'
            r'<span class="erp-sort-arrow" aria-hidden="true">&#9650;</span></a>',
        )


class SortHeaderCssTests(TestCase):
    def test_arrow_is_no_longer_generated_text(self):
        self.assertNotIn(".erp-sort-link::after", CSS)

    def test_sort_links_in_panels_keep_a_24px_target(self):
        self.assertIn(".erp-panel .erp-sort-link { min-height: 1.5rem; }", CSS)
        self.assertNotIn(".erp-panel .erp-sort-link { min-height: 0; }", CSS)

    def test_row_headers_keep_normal_weight_and_alignment(self):
        self.assertIn(
            '.erp-rows-link > tbody th[scope="row"] { font-weight: inherit; text-align: start; }', CSS
        )
