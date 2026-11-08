"""Shared empty state: icon badge, inline variant, next action and clear link."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.tests.test_authorization import AuthorizationClientsMixin


class EmptyPartialTests(SimpleTestCase):
    def render(self, **context):
        return render_to_string("partials/_empty.html", context)

    def test_plain_use_is_unchanged(self):
        html = self.render(title="Nothing yet", text="Add one.")
        self.assertIn('class="erp-empty"', html)
        self.assertIn('<span class="erp-empty-icon" aria-hidden="true">○</span>', html)
        self.assertNotIn("<a ", html)

    def test_icon_renders_in_a_badge(self):
        html = self.render(title="No subjects yet.", icon="subjects")
        self.assertRegex(html, r'class="erp-empty-icon erp-empty-icon--badge" aria-hidden="true">\s*<svg')
        self.assertNotIn("○", html)

    def test_inline_variant_and_actions(self):
        html = self.render(
            title="No notices yet.", inline=True,
            action_url="/notices/new/", action_label="Publish a notice", clear_url="/notices/",
        )
        self.assertIn('class="erp-empty erp-empty--inline"', html)
        self.assertIn(
            '<a class="btn btn-outline-primary btn-sm mt-2" href="/notices/new/">Publish a notice</a>', html
        )
        self.assertIn('<a class="btn btn-outline-secondary btn-sm mt-2" href="/notices/">Clear filters</a>', html)

    def test_action_needs_both_url_and_label(self):
        self.assertNotIn("<a ", self.render(title="x", action_url="/x/"))
        self.assertNotIn("<a ", self.render(title="x", action_label="Go"))

    def test_clear_label_can_be_changed(self):
        html = self.render(title="x", clear_url="/g/", clear_label="Clear search")
        self.assertIn('href="/g/">Clear search</a>', html)


class AdminListEmptyStateTests(AuthorizationClientsMixin, TestCase):
    """Empty admin lists show the shared inline empty state with their area icon."""

    PAGES = (
        "core:class-grade-list", "core:subject-list", "core:teacher-list",
        "core:applicant-list", "core:guardian-list", "core:import-list",
        "core:announcement-list", "core:academic-year-list",
        "core:guardian-access-reviews", "core:login-lockouts", "core:publications-stale",
        "core:timetable-index",
    )

    def test_empty_lists_use_the_inline_empty_state(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.administrator.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="erp-empty erp-empty--inline"')
                self.assertContains(response, "erp-empty-icon--badge")

    def test_guardian_search_offers_clear_search_button(self):
        url = reverse("core:guardian-list")
        response = self.administrator.get(url, {"q": "zzz-none"})
        self.assertContains(response, "No guardians match this search.")
        self.assertContains(
            response, f'<a class="btn btn-outline-secondary btn-sm mt-2" href="{url}">Clear search</a>'
        )
