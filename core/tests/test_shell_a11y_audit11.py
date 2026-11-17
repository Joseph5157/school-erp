"""Modern web audits 11 and 14: skip link, scroll padding, breadcrumbs, High Contrast nav,
dynamic viewport units, Teacher list semantics and long-value wrapping."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin

CSS = Path(settings.BASE_DIR, "static", "css", "erp.css")


def css():
    return CSS.read_text(encoding="utf-8")


class ShellMarkupTests(AuthorizationClientsMixin, Phase4Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.build_phase4()

    def test_skip_link_targets_a_focusable_main(self):
        page = self.administrator.get(reverse("core:student-list")).content.decode()
        self.assertIn('<a class="visually-hidden-focusable erp-skip" href="#main">Skip to content</a>', page)
        self.assertIn('<main id="main" class="erp-main" tabindex="-1">', page)

    def test_current_breadcrumb_is_a_link_with_aria_current(self):
        student, _ = self.make_student("Asha")
        url = reverse("core:student-detail", args=[student.pk])
        page = self.administrator.get(url).content.decode()
        trail = page.split('aria-label="Breadcrumb"', 1)[1].split("</nav>", 1)[0]
        self.assertIn(f'<li><a href="{url}" aria-current="page">', trail)
        self.assertNotIn("<li aria-current", trail)
        self.assertEqual(trail.count('aria-current="page"'), 1)


class ShellCssTests(SimpleTestCase):
    def test_skip_link_floats_and_main_has_no_focus_ring(self):
        self.assertRegex(css(), r"\.erp-skip:focus \{ position: fixed;")
        self.assertIn(".erp-main:focus { outline: none; }", css())

    def test_scroll_padding_replaces_the_section_only_margin(self):
        self.assertIn("html { scroll-padding-top: calc(var(--erp-topbar-h) + var(--erp-space-4)); }", css())
        self.assertIn(".erp-main section[id] { scroll-margin-top: 0; }", css())

    def test_breadcrumb_divider_has_an_empty_alternative(self):
        self.assertIn('content: "/"; content: "/" / "";', css())

    def test_active_navigation_is_underlined_in_high_contrast(self):
        block = re.search(r"@media \(forced-colors: active\) \{\s*\.erp-sidebar \.nav-link\.active[^}]*\}", css())
        self.assertIsNotNone(block)
        self.assertIn("text-decoration: underline", block.group(0))

    def test_overlays_use_dynamic_viewport_units_after_a_static_fallback(self):
        text = css()
        for fallback, dynamic in (
            ("max-height: min(20rem, 70vh);", "max-height: min(20rem, 70dvh);"),
            ("width: min(18rem, calc(100vw - 2rem));", "width: min(18rem, calc(100dvw - 2rem));"),
            ("--bs-offcanvas-width: min(20rem, 86vw);", "--bs-offcanvas-width: min(20rem, 86dvw);"),
            ("max-height: 70vh;", "max-height: 70dvh;"),
        ):
            with self.subTest(dynamic):
                self.assertIn(f"{fallback} {dynamic}", text)


class DetailMarkupTests(SimpleTestCase):
    """Template-level checks for audit 14 DP-03 and DP-05."""

    def read(self, name):
        return Path(settings.BASE_DIR, "core", "templates", "core", name).read_text(encoding="utf-8")

    def test_teacher_assignment_lists_keep_list_semantics(self):
        self.assertEqual(self.read("teacher_detail.html").count('role="list"'), 2)

    def test_long_guardian_and_remark_values_wrap(self):
        self.assertIn('class="erp-panel erp-wrap-anywhere', self.read("guardian_detail.html"))
        self.assertIn("erp-wrap-anywhere", self.read("_guardian_consent.html"))
        self.assertIn('<p class="mb-0 erp-wrap-anywhere">{% if remark %}', self.read("report_term_report_card.html"))
