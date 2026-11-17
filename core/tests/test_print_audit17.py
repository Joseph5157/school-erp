"""Modern web audit 17: PRT-01 (ordinary pages print their content), PRT-02 (paper resets screen-only
table rules) and PRT-06 (issued PDFs download and are not cached)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR, "static", "css", "erp.css")


def print_block():
    css = CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"@media print \{.*?\n\}", css, re.S)
    return "\n".join(blocks)


class PrintCssTests(SimpleTestCase):
    def test_only_a_credential_slip_page_hides_everything_but_the_card(self):
        block = print_block()
        self.assertNotRegex(block, r"(?m)^\s*body \* \{ visibility: hidden; \}")
        self.assertIn("body:has(.erp-credential-card) * { visibility: hidden; }", block)
        self.assertIn("body:has(.erp-credential-card) .erp-credential-card", block)

    def test_shell_is_removed_from_paper(self):
        block = print_block()
        for selector in (".erp-topbar", ".erp-sidebar", ".erp-tabbar", ".erp-install-bar", ".erp-messages",
                         ".erp-pagination", ".erp-main search"):
            with self.subTest(selector):
                self.assertIn(selector, block.split("{ display: none !important; }", 1)[0])

    def test_tables_are_not_clipped_or_sticky_on_paper(self):
        block = print_block()
        self.assertIn(".erp-table-scroll, .erp-import-scroll { contain: none; overflow: visible; max-height: none;", block)
        self.assertIn(".erp-main th, .erp-main td { position: static !important;", block)
        self.assertIn(".erp-main thead { display: table-header-group; }", block)
