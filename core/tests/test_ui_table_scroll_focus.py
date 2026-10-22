"""Focusable table-scroll regions keep a visible focus ring (PR #97 review follow-up)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TableScrollFocusRuleTests(SimpleTestCase):
    def setUp(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        match = re.search(r"\.erp-table-scroll:focus-visible\s*\{([^}]*)\}", css)
        self.assertIsNotNone(match, "missing .erp-table-scroll:focus-visible rule")
        self.rule = match.group(1)

    def test_ring_is_solid_and_uses_focus_colour(self):
        self.assertRegex(self.rule, r"outline:\s*3px solid var\(--erp-focus-color\)")

    def test_ring_is_drawn_inside_the_clipped_region(self):
        # contain: paint / overflow clip anything outside the box, so the offset must be negative.
        self.assertRegex(self.rule, r"outline-offset:\s*-\d")
