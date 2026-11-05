"""Phone login: artwork above centred text on a full white page. Desktop keeps its showcase."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class PhoneLoginTests(TestCase):
    def test_artwork_sits_above_the_form_and_in_the_showcase(self):
        page = self.client.get(reverse("login")).content.decode()
        self.assertEqual(page.count('class="erp-login-scene"'), 1)
        self.assertEqual(page.count('class="erp-login-art"'), 1)
        self.assertLess(page.index("erp-login-art-top"), page.index("Welcome back"))
        self.assertLess(page.index("Forgot your password?"), page.index("erp-login-showcase"))
        self.assertLess(page.index("erp-login-showcase"), page.index('class="erp-login-art"'))

    def test_artwork_is_hidden_from_screen_readers(self):
        page = self.client.get(reverse("login")).content.decode()
        # The brand mark, the phone scene and the desktop artwork.
        self.assertEqual(page.count('aria-hidden="true" focusable="false"'), 3)

    def test_brand_mark_sits_beside_the_product_name(self):
        page = self.client.get(reverse("login")).content.decode()
        self.assertLess(page.index('class="erp-brand-mark"'), page.index("School ERP</a>"))

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
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        start = css.index("@media (max-width: 991.98px) {\n  .erp-content:has(> .erp-login)")
        block = css[start : css.index("/* Short screens: the Log in button", start)]
        self.assertNotIn(".erp-auth", block)
