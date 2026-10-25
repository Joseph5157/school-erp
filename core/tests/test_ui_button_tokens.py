"""UI-15 / UI-08: button tokens, desktop field height and the bare inline toolbar field basis."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TOKENS = {
    "--erp-btn-radius": "var(--erp-radius-sm)",
    "--erp-btn-height": "2.5rem",
    "--erp-btn-height-sm": "2rem",
}


class ButtonTokenTests(SimpleTestCase):
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

    def test_radius_applies_to_every_button_size(self):
        self.assertRegex(
            self.css,
            r"\.btn,\s*\.btn-sm,\s*\.btn-lg\s*\{\s*--bs-btn-border-radius:\s*var\(--erp-btn-radius\);\s*\}",
        )

    def test_desktop_heights_are_scoped_to_768px_and_up(self):
        match = re.search(r"@media \(min-width: 768px\) \{\s*\.btn \{([^}]*)\}\s*\.btn-sm \{([^}]*)\}", self.css)
        self.assertIsNotNone(match)
        self.assertIn("min-height: var(--erp-btn-height);", match.group(1))
        self.assertIn("min-height: var(--erp-btn-height-sm);", match.group(2))
        self.assertRegex(self.css, r"\.btn-sm \{[^}]*\}\s*\.btn-link \{ min-height: 0; \}")

    def test_desktop_field_height_matches_buttons_and_phones_keep_44px(self):
        base = self.rule('.erp-field :where(input:not([type="checkbox"]):not([type="radio"]), select, textarea)')
        self.assertIn("min-height: 2.75rem;", base)
        desktop = self.rule(
            '.erp-field :where(input:not([type="checkbox"]):not([type="radio"]):not([type="file"]), select)'
        )
        self.assertIn("min-height: var(--erp-btn-height);", desktop)
        # 24px line + 2 x .4rem + 2px border is under 40px, so the min-height is what sets the height.
        self.assertIn("padding-block: .4rem;", desktop)
        self.assertIn("textarea { min-height: 7rem;", self.css)
        self.assertRegex(self.css, r"\n\s*\.btn \{ min-height: 2\.75rem; \}\s*\n\}")

    def test_bare_inline_toolbar_field_basis(self):
        rule = self.rule(".erp-toolbar--inline > .erp-field")
        self.assertIn("flex: 1 1 11rem;", rule)
        self.assertNotIn("18rem", rule)
        self.assertRegex(
            self.css,
            r"@media \(min-width: 576px\) \{ \.erp-toolbar--inline > \.erp-field \{ max-width: 17rem; \} \}",
        )
        self.assertIn(
            "@media (max-width: 575.98px) { .erp-toolbar--inline > .erp-field { flex-basis: 100%; } }", self.css
        )

    def test_page_modifier_overrides_are_kept(self):
        for name in ("grading", "results", "publication", "assessment", "document", "attendance-report"):
            with self.subTest(modifier=name):
                self.assertIn(f".erp-toolbar--inline.erp-{name}-toolbar > .erp-field {{", self.css)

    def test_protected_rules_are_intact(self):
        self.assertIn(
            ".erp-panel > .erp-table-scroll { border-radius: 0; scrollbar-gutter: auto; }", self.css
        )
        self.assertRegex(self.rule(".erp-table-scroll:focus-visible"), r"outline:\s*3px solid var\(--erp-focus-color\)")
        self.assertIn("margin-bottom: var(--erp-space-3); padding: var(--erp-space-3) var(--erp-space-4);", self.css)
        outline = self.rule(".btn-outline-secondary")
        self.assertIn("var(--erp-ink)", outline)
        self.assertIn("var(--erp-ink-soft)", outline)
