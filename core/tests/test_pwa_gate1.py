"""PWA Gate 1: installable, online-only app (docs/PWA_GATE_1_PLAN.md).

The manifest is public install metadata served by a Django view. It must work with or without a
session cookie, must not move the idle clock, and must not widen access to anything else.
"""

import json
import time
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import engines
from django.test import RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from accounts.middleware import MANIFEST_PATH, SEEN_KEY, STARTED_KEY
from core import pwa_views

User = get_user_model()
PWA_STATIC = Path(settings.BASE_DIR) / "static" / "pwa"
ERP_JS = Path(settings.BASE_DIR) / "static" / "js" / "erp.js"


class ManifestTests(TestCase):
    def fetch(self):
        return self.client.get(reverse("pwa-manifest"))

    def test_public_manifest_served_with_manifest_content_type(self):
        response = self.fetch()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        self.assertEqual(set(response["Cache-Control"].split(", ")), {"public", "max-age=3600"})

    def test_install_identity(self):
        data = json.loads(self.fetch().content)
        self.assertEqual(data["id"], "/")
        self.assertEqual(data["start_url"], "/")
        self.assertEqual(data["scope"], "/")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["name"], "School ERP")
        self.assertEqual(data["short_name"], "School ERP")

    def test_paths_are_origin_relative_and_hold_no_account_data(self):
        User.objects.create_user("teacher1", password="pw-123456-xx")
        text = self.fetch().content.decode()
        self.assertNotIn("http", text)
        self.assertNotIn("localhost", text)
        self.assertNotIn("railway", text.lower())
        self.assertNotIn("teacher1", text)

    def test_icons_cover_required_sizes_and_a_maskable_icon(self):
        icons = json.loads(self.fetch().content)["icons"]
        by_purpose = {(i["sizes"], i["purpose"]) for i in icons}
        self.assertIn(("192x192", "any"), by_purpose)
        self.assertIn(("512x512", "any"), by_purpose)
        self.assertIn(("512x512", "maskable"), by_purpose)
        for icon in icons:
            self.assertEqual(icon["type"], "image/png")
            self.assertTrue(icon["src"].startswith("/"))
            self.assertTrue(icon["src"].endswith(".png"))

    def test_colours_match_the_shell_meta_tag(self):
        data = json.loads(self.fetch().content)
        html = engines["django"].from_string("{% include 'partials/_pwa_head.html' %}").render({})
        self.assertIn(f'content="{data["theme_color"]}"', html)

    def test_route_matches_the_path_the_middleware_lets_through(self):
        self.assertEqual(reverse("pwa-manifest"), MANIFEST_PATH)

    def test_post_is_refused(self):
        self.assertEqual(self.client.post(reverse("pwa-manifest")).status_code, 405)


class ManifestSessionRulesTests(TestCase):
    """The manifest bypass is exact: sessions and forced password change still bind elsewhere."""

    def setUp(self):
        self.user = User.objects.create_user("meena", password="pw-123456-xx")
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])

    def sign_in(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[STARTED_KEY] = time.time()
        session[SEEN_KEY] = time.time()
        session.save()

    def require_password_change(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])

    def test_manifest_loads_while_password_change_is_required(self):
        self.require_password_change()
        self.sign_in()
        self.assertEqual(self.client.get(reverse("pwa-manifest")).status_code, 200)
        # ...but the rest of the app still redirects to the password-change page.
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("password_change"), fetch_redirect_response=False)

    def test_manifest_does_not_refresh_the_idle_clock(self):
        self.sign_in()
        long_ago = time.time() - 600
        session = self.client.session
        session[SEEN_KEY] = long_ago
        session.save()
        self.assertEqual(self.client.get(reverse("pwa-manifest")).status_code, 200)
        self.assertEqual(self.client.session[SEEN_KEY], long_ago)

    def test_manifest_does_not_keep_an_expired_session_alive(self):
        self.sign_in()
        session = self.client.session
        session[SEEN_KEY] = time.time() - settings.SESSION_IDLE_SECONDS - 5
        session.save()
        self.assertEqual(self.client.get(reverse("pwa-manifest")).status_code, 200)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_manifest_works_with_a_stale_session_cookie(self):
        self.client.cookies[settings.SESSION_COOKIE_NAME] = "not-a-real-session"
        self.assertEqual(self.client.get(reverse("pwa-manifest")).status_code, 200)

    def test_other_pages_still_require_login(self):
        for name in ("home", "pwa-install"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertTrue(response["Location"].startswith(reverse("login")), name)

    def test_lookalike_paths_get_no_bypass(self):
        self.require_password_change()
        self.sign_in()
        for path in ("/manifest.webmanifest/", "/overview/?x=/manifest.webmanifest"):
            response = self.client.get(path)
            self.assertIn(response.status_code, (302, 404), path)
            if response.status_code == 302:
                self.assertEqual(response["Location"], reverse("password_change"), path)


class ShellTests(TestCase):
    """Both application shells carry the same install metadata."""

    def setUp(self):
        self.user = User.objects.create_user("shell", password="pw-123456-xx")

    def render(self, template):
        request = RequestFactory().get("/")
        request.user = self.user
        source = '{% extends "' + template + '" %}'
        return engines["django"].from_string(source).render({}, request)

    def assert_metadata(self, html):
        self.assertIn(f'<link rel="manifest" href="{reverse("pwa-manifest")}">', html)
        self.assertIn('<meta name="theme-color"', html)
        self.assertIn('<link rel="apple-touch-icon"', html)
        self.assertIn("pwa/apple-touch-icon", html)
        self.assertNotIn("use-credentials", html)

    def test_office_and_teacher_shell(self):
        self.assert_metadata(self.render("base.html"))

    def test_guardian_portal_shell(self):
        self.assert_metadata(self.render("portal/base.html"))

    def test_no_service_worker_is_registered(self):
        for template in ("base.html", "portal/base.html"):
            self.assertNotIn("serviceWorker", self.render(template))
        self.assertNotIn("serviceWorker", ERP_JS.read_text(encoding="utf-8"))
        self.assertFalse((Path(settings.BASE_DIR) / "static" / "sw.js").exists())


class IconTests(TestCase):
    def open(self, name):
        return Image.open(PWA_STATIC / name).convert("RGBA")

    def test_sizes(self):
        for name, size in (
            ("icon-192.png", 192),
            ("icon-512.png", 512),
            ("icon-maskable-512.png", 512),
            ("apple-touch-icon.png", 180),
        ):
            self.assertEqual(self.open(name).size, (size, size), name)

    def test_maskable_and_apple_icons_are_fully_opaque(self):
        for name in ("icon-maskable-512.png", "apple-touch-icon.png"):
            image = self.open(name)
            width, height = image.size
            for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
                self.assertEqual(image.getpixel(point)[3], 255, f"{name} {point}")

    def test_any_icons_have_rounded_transparent_corners(self):
        for name in ("icon-192.png", "icon-512.png"):
            self.assertEqual(self.open(name).getpixel((0, 0))[3], 0, name)

    def test_icons_use_the_cobalt_token(self):
        cobalt = tuple(int(pwa_views.ICON_COLOUR[i:i + 2], 16) for i in (1, 3, 5))
        for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
            image = self.open(name)
            width, height = image.size
            self.assertEqual(image.getpixel((width // 2, int(height * 0.08)))[:3], cobalt, name)


class InstallPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("meena", password="pw-123456-xx")
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.user)

    def test_page_explains_install_on_each_platform(self):
        response = self.client.get(reverse("pwa-install"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add to Home Screen")
        self.assertContains(response, "internet connection")

    def test_custom_install_button_is_hidden_until_the_browser_offers_one(self):
        html = self.client.get(reverse("pwa-install")).content.decode()
        tag_start = html.rindex("<", 0, html.index("data-erp-install"))
        self.assertIn("hidden", html[tag_start:html.index(">", tag_start)])

    def test_account_menu_links_to_the_page(self):
        response = self.client.get(reverse("pwa-install"))
        self.assertContains(response, f'href="{reverse("pwa-install")}"')

    def test_script_only_listens_for_install_when_the_button_exists(self):
        js = ERP_JS.read_text(encoding="utf-8")
        self.assertIn("beforeinstallprompt", js)
        self.assertIn("data-erp-install", js)
