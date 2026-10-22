import datetime

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear
from core.tests.test_authorization import AuthorizationClientsMixin


class AdminDesktopD0Tests(AuthorizationClientsMixin, TestCase):
    """UI-D0 desktop spike: shared panel pattern, no change to access or content."""

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 3, 31)
        )

    def get(self, name, *args):
        return self.administrator.get(reverse(name, args=args))

    def test_data_screens_use_the_shared_panel(self):
        for name, args in (
            ("core:student-list", ()),
            ("core:academic-year-list", ()),
            ("core:academic-year-teacher-assignments", (self.year.pk,)),
        ):
            with self.subTest(page=name):
                response = self.get(name, *args)
                self.assertContains(response, 'class="erp-panel"')
                self.assertContains(response, "erp-table-scroll")

    def test_student_filters_render_as_a_toolbar(self):
        response = self.get("core:student-list")
        self.assertContains(response, 'class="erp-toolbar" role="search"')

    def test_year_list_action_lives_in_the_page_header(self):
        response = self.get("core:academic-year-list")
        self.assertContains(response, "erp-page-header-actions")
        self.assertContains(response, reverse("core:academic-year-create"))
        self.assertContains(response, "Create Academic Year")

    def test_teacher_assignments_has_page_header_and_assign_action(self):
        response = self.get("core:academic-year-teacher-assignments", self.year.pk)
        self.assertContains(response, '<h1 class="erp-page-title">Teacher assignments</h1>')
        self.assertContains(response, "2026-27")
        self.assertContains(response, "Assign a teacher")

    def test_year_list_keeps_values_on_one_line_and_groups_links(self):
        response = self.get("core:academic-year-list")
        content = response.content.decode()
        self.assertContains(response, 'class="table erp-years-table"')
        self.assertContains(response, '<td class="text-nowrap fw-semibold">2026-27</td>')
        self.assertEqual(content.count('<td class="text-nowrap">'), 3)
        self.assertEqual(content.count('class="erp-year-links-group"'), 3)
        self.assertContains(response, '<span class="visually-hidden">Year pages</span>')
        # Links are spaced by the flex group; a text dot could start a wrapped line.
        self.assertNotIn("&middot;", content.split('class="erp-year-links"')[1].split("</ul>")[0])

    def ui_d0_css(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        return css[css.index("UI-D0: admin desktop workspace"):]

    def test_stylesheet_scopes_only_workspace_rules_to_992px(self):
        block = self.ui_d0_css()
        desktop = block[block.index("@media (min-width: 992px)"):]
        shared = block[: block.index("@media (min-width: 992px)")]
        self.assertIn("max-width: 96rem", desktop)
        self.assertIn(".erp-sidebar .nav-link.active::before", desktop)
        # Panel, toolbar and table patterns apply at every width on purpose.
        for selector in (".erp-panel {", ".erp-toolbar {", ".erp-panel .table > thead th", ".erp-years-table td.text-nowrap"):
            with self.subTest(selector=selector):
                self.assertIn(selector, shared)
                self.assertNotIn(selector, desktop)

    def test_stylesheet_mobile_safeguards(self):
        block = self.ui_d0_css()
        self.assertIn("@media (hover: hover) { .erp-panel .table > tbody > tr:hover", block)
        self.assertIn(".erp-panel > .erp-table-scroll { border-radius: 0; scrollbar-gutter: auto; }", block)
        self.assertIn("@media (max-width: 575.98px) { .erp-toolbar--inline > .erp-field { flex-basis: 100%; } }", block)
        self.assertIn("@media (max-width: 575.98px) { .erp-year-links { max-width: 16rem; } }", block)
