"""The stylesheet must parse: a lost brace silently nests every later rule."""
import re

from django.conf import settings
from django.test import SimpleTestCase


class StylesheetIsWellFormedTests(SimpleTestCase):
    def setUp(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.raw = css
        self.css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), css, flags=re.S)

    def test_braces_balance(self):
        open_at = []
        for number, line in enumerate(self.css.split("\n"), start=1):
            for char in line:
                if char == "{":
                    open_at.append(number)
                elif char == "}":
                    self.assertTrue(open_at, f"Extra closing brace on line {number}")
                    open_at.pop()
        self.assertEqual(open_at, [], "Rules never closed, opened on these lines")

    def test_no_merge_conflict_markers(self):
        self.assertIsNone(re.search(r"^(<{7}|={7}|>{7})", self.raw, flags=re.M))

    def test_only_at_rules_hold_other_rules(self):
        """This file does not use CSS nesting, so a selector inside a selector is a lost brace."""
        stack = []
        selector = ""
        for char in self.css:
            if char == "{":
                name = selector.strip()
                if stack and not stack[-1].startswith("@"):
                    self.fail(f"{name[:80]!r} is nested inside {stack[-1][:80]!r}")
                stack.append(name)
                selector = ""
            elif char == "}":
                if stack:
                    stack.pop()
                selector = ""
            elif char == ";":
                selector = ""
            else:
                selector += char
