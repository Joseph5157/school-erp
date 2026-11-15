"""The product is called Everclass ERP (owner decision, 2026-11-15).

Shown in the header, page titles, the login page, the installed app's name and messages the
system sends. The home-screen label is "Everclass": about 12 characters fit under an icon.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

ROOT = Path(settings.BASE_DIR)
OLD_NAME = "School ERP"


class ProductNameTests(TestCase):
    def test_login_page_title_and_brand(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, 'aria-label="About Everclass ERP"')
        self.assertNotContains(page, OLD_NAME)

    def test_installed_app_names(self):
        data = self.client.get("/manifest.webmanifest").json()
        self.assertEqual((data["name"], data["short_name"]), ("Everclass ERP", "Everclass"))
        self.assertTrue(data["description"].startswith("Everclass ERP "))

    def test_the_old_name_is_gone_from_the_app(self):
        sources = [ROOT / "templates", ROOT / "static" / "js", ROOT / "static" / "css", ROOT / "config"]
        sources += [ROOT / app for app in ("core", "accounts")]
        offenders = []
        for folder in sources:
            for path in folder.rglob("*"):
                if path.suffix not in {".html", ".py", ".js", ".css", ".txt"} or "tests" in path.parts:
                    continue
                if "migrations" in path.parts or "__pycache__" in path.parts:
                    continue
                if OLD_NAME in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])
