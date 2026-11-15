"""The product is called Everclass ERP (owner decision, 2026-11-15).

Shown in the header, page titles, the login page, the installed app's name and messages the
system sends. The home-screen label is "Everclass": about 12 characters fit under an icon.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

ROOT = Path(settings.BASE_DIR)
OLD_NAME = "School ERP"
# Any spelling of the old name: "School ERP", "school-erp", "School&nbsp;ERP", any case.
OLD_NAME_ANY = re.compile(r"school(\s|-|&nbsp;)erp", re.IGNORECASE)
# Kept on purpose: crash emails go only to the operator, and two security tests pin this prefix.
ALLOWED = {("config/settings.py", 'EMAIL_SUBJECT_PREFIX = f"[school-erp {ERP_INSTANCE_NAME}] "')}


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
                relative = path.relative_to(ROOT).as_posix()
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if OLD_NAME_ANY.search(line) and (relative, line.strip()) not in ALLOWED:
                        offenders.append(f"{relative}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_the_import_template_download_is_named_for_the_product(self):
        from django.contrib.auth import get_user_model

        admin = get_user_model().objects.create_superuser(username="boss", password="pass-12345")
        self.client.force_login(admin)
        response = self.client.get(reverse("core:import-template"))
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="everclass-erp-import-template.xlsx"'
        )
