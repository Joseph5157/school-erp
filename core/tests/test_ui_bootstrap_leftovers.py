"""Stock Bootstrap list groups and coloured badges are replaced by the app's own components."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATE_DIRS = ("templates", "core/templates")


def template_sources():
    base = Path(settings.BASE_DIR)
    for folder in TEMPLATE_DIRS:
        for path in (base / folder).rglob("*.html"):
            yield path.relative_to(base), path.read_text(encoding="utf-8")


class BootstrapLeftoverTests(SimpleTestCase):
    def test_no_template_uses_list_group(self):
        offenders = [str(path) for path, text in template_sources() if "list-group" in text]
        self.assertEqual(offenders, [], "use .erp-link-list / .erp-link-row instead")

    def test_no_template_uses_bootstrap_colour_badges(self):
        offenders = [str(path) for path, text in template_sources() if 'class="badge ' in text]
        self.assertEqual(offenders, [], 'use partials/_status_badge.html instead')

    def test_link_list_and_dialog_styles_exist(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        for selector in (".erp-link-list {", ".erp-link-row {", ".modal-content {", ".modal.fade .modal-dialog {"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
