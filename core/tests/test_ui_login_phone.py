"""Phone login: a teal header with the brand mark, the form on a white sheet. Desktop keeps its showcase."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


def css():
    return (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")


def phone_block():
    text = css()
    start = text.index("@media (max-width: 991.98px) {\n  .erp-content:has(> .erp-login)")
    return text[start : text.index("/* Short screens: the Log in button", start)]


class PhoneLoginTests(TestCase):
    def page(self):
        return self.client.get(reverse("login")).content.decode()

    def test_teal_header_sits_above_the_form_and_the_showcase_keeps_its_artwork(self):
        page = self.page()
        self.assertEqual(page.count('class="erp-login-hero"'), 1)
        self.assertEqual(page.count('class="erp-login-art"'), 1)
        hero = page.index('class="erp-login-hero"')
        self.assertLess(hero, page.index('class="erp-login-hero-mark"'))
        self.assertLess(page.index('class="erp-login-hero-mark"'), page.index("<h1>Log in</h1>"))
        self.assertLess(page.index("Forgot your password?"), page.index("erp-login-showcase"))
        self.assertLess(page.index("erp-login-showcase"), page.index('class="erp-login-art"'))

    def test_header_wording(self):
        page = self.page()
        self.assertIn('<p class="erp-login-hero-name">Everclass ERP</p>', page)
        self.assertIn('<p class="erp-login-hero-title">Welcome back</p>', page)
        self.assertIn(
            '<p class="erp-login-hero-text">Attendance, results and notices for your school.</p>', page
        )

    def test_old_phone_scene_is_gone(self):
        page = self.page()
        self.assertNotIn("erp-login-scene", page)
        self.assertNotIn("erp-login-art-top", page)
        self.assertFalse(
            (Path(settings.BASE_DIR) / "templates" / "registration" / "_login_scene.html").exists()
        )

    def test_page_has_one_heading_level_one(self):
        # "Welcome back" in the header is a paragraph; the page heading stays "Log in".
        self.assertEqual(self.page().count("<h1"), 1)

    def test_artwork_is_hidden_from_screen_readers(self):
        # The top-bar mark, the header mark and the desktop artwork.
        self.assertEqual(self.page().count('aria-hidden="true" focusable="false"'), 3)

    def test_brand_mark_sits_beside_the_product_name(self):
        page = self.page()
        self.assertLess(page.index('class="erp-brand-mark"'), page.index("Everclass ERP</a>"))

    def test_wording_is_kept(self):
        page = self.client.get(reverse("login"))
        for text in (
            "Welcome back",
            "Log in",
            "Use the username the school gave you.",
            "Forgot your password? Ask the school office to reset it.",
        ):
            self.assertContains(page, text)

    def test_page_runs_no_database_queries_for_anonymous_visitors(self):
        with self.assertNumQueries(0):
            self.client.get(reverse("login"))

    def test_phone_rules_do_not_touch_other_pages_using_the_auth_card(self):
        self.assertNotIn(".erp-auth", phone_block())

    def test_phone_header_is_teal_and_the_sheet_is_white(self):
        block = phone_block()
        self.assertIn("background: var(--erp-brand-wash)", block)
        self.assertIn("border-radius: 28px 28px 0 0", block)
        # The header already shows the mark and name, so the top bar is hidden on this page only.
        self.assertIn("body:has(.erp-login) .erp-topbar { display: none; }", block)
        # The duplicate "Welcome back" eyebrow is for desktop.
        self.assertIn(".erp-login-form > .erp-login-eyebrow { display: none; }", block)

    def test_header_shrinks_after_an_error_and_on_short_screens(self):
        text = css()
        self.assertIn(
            ".erp-login-form:has(.alert, .is-invalid) :is(.erp-login-hero-mark, .erp-login-hero-text) { display: none; }",
            text,
        )
        short = text[text.index("/* Short screens: the Log in button") :]
        short = short[: short.index("}\n}") + 3]
        self.assertIn(":is(.erp-login-hero-mark, .erp-login-hero-text) { display: none; }", short)

    def test_desktop_hides_the_phone_header(self):
        text = css()
        desktop = text[text.index("@media (min-width: 992px) {\n  .erp-login-hero") :]
        self.assertIn(".erp-login-hero { display: none; }", desktop[:200])
