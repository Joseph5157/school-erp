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

    def test_stylesheet_scopes_desktop_rules_to_992px(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css[css.index("UI-D0: admin desktop workspace"):]
        self.assertIn("@media (min-width: 992px)", block)
        self.assertIn("max-width: 96rem", block)
