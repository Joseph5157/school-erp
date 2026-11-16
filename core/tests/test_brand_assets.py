"""The Everclass logo files (docs/superpowers/specs/2026-11-16-everclass-logo-palette-design.md)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BRAND = Path(settings.BASE_DIR) / "static" / "brand"
LOGO_COLOURS = ("#1bb5a8", "#f5b82e", "#0b2a4a")
OLD_GREEN = "#185842"


class BrandFileTests(SimpleTestCase):
    def read(self, name):
        return (BRAND / name).read_text(encoding="utf-8").lower()

    def test_mark_uses_the_64_unit_grid(self):
        self.assertIn('viewbox="0 0 64 64"', self.read("everclass-mark.svg"))

    def test_both_files_use_the_logo_colours_and_not_the_old_green(self):
        for name in ("everclass-mark.svg", "everclass-logo.svg"):
            svg = self.read(name)
            for colour in LOGO_COLOURS:
                with self.subTest(file=name, colour=colour):
                    self.assertIn(colour, svg)
            self.assertNotIn(OLD_GREEN, svg)

    def test_logo_carries_the_product_name(self):
        self.assertIn("Everclass ERP", (BRAND / "everclass-logo.svg").read_text(encoding="utf-8"))
