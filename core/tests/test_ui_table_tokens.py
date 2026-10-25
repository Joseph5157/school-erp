"""UI-14: table-only type and spacing tokens, and the shared panel table rules that read them."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TOKENS = {
    "--erp-table-head-size": ".8125rem",
    "--erp-table-head-weight": "600",
    "--erp-table-head-tracking": ".04em",
    "--erp-table-pad-y": ".75rem",
    "--erp-table-pad-x": "1rem",
    "--erp-table-head-pad-y": ".75rem",
}


class TableTokenTests(SimpleTestCase):
    def setUp(self):
        self.css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")

    def rule(self, selector):
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(match, f"missing rule {selector}")
        return match.group(1)

    def test_tokens_are_declared_with_the_stated_values(self):
        root = self.rule(":root")
        for name, value in TOKENS.items():
            with self.subTest(token=name):
                self.assertRegex(root, re.escape(name) + r":\s*" + re.escape(value) + r"\s*;")

    def test_panel_header_rule_reads_the_tokens_and_has_no_literal(self):
        rule = self.rule(".erp-panel .table > thead th")
        self.assertNotIn(".7rem", rule)
        for name in (
            "head-size", "head-weight", "head-tracking", "head-pad-y", "pad-x",
        ):
            with self.subTest(token=name):
                self.assertIn(f"var(--erp-table-{name})", rule)
        self.assertIn("text-transform: uppercase", rule)
        self.assertIn("white-space: nowrap", rule)
        self.assertIn("background: var(--erp-paper)", rule)

    def test_panel_cells_read_the_padding_tokens(self):
        rule = self.rule(".erp-panel .table > tbody td, .erp-panel .table > tbody th")
        self.assertIn("padding: var(--erp-table-pad-y) var(--erp-table-pad-x)", rule)

    def test_report_card_header_uses_the_head_tokens(self):
        rule = self.rule(".erp-rc-table thead th")
        for name in ("head-size", "head-weight", "head-tracking"):
            with self.subTest(token=name):
                self.assertIn(f"var(--erp-table-{name})", rule)

    def test_protected_rules_are_intact(self):
        self.assertIn(
            ".erp-panel > .erp-table-scroll { border-radius: 0; scrollbar-gutter: auto; }", self.css
        )
        focus = self.rule(".erp-table-scroll:focus-visible")
        self.assertRegex(focus, r"outline:\s*3px solid var\(--erp-focus-color\)")
        self.assertRegex(focus, r"outline-offset:\s*-\d")
