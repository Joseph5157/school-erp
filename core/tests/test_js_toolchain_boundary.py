"""Boundary of the browser test toolchain (ADR 0028, ENG-JS-01 spec sections 9 and 10.3).

The browser tests are a test-only Python toolchain: Playwright from requirements-browser.txt and
headless Chromium. Nothing of it may reach production, and no project-managed Node/npm toolchain
may appear. Standard library only.
"""

import re

from django.conf import settings
from django.test import SimpleTestCase

ROOT = settings.BASE_DIR
BROWSER_TESTS = ROOT / "browser_tests"
# Each listed browser test file must exist with at least this many test methods, so tests cannot
# be emptied or removed quietly. Later PRs add their files here.
EXPECTED_BROWSER_TESTS = {"bt_harness.py": 11}
NODE_FILES = ("package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
              "pnpm-lock.yaml", "node_modules")


class ToolchainBoundaryTests(SimpleTestCase):
    def test_playwright_never_reaches_the_production_requirements(self):
        production = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("playwright", production)
        self.assertNotIn("requirements-browser", production)

    def test_browser_requirements_are_exact_pins(self):
        lines = [line.strip() for line in (ROOT / "requirements-browser.txt").read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith("#")]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9.]*$", line)
        self.assertIn("playwright", {line.split("==")[0].lower() for line in lines})

    def test_no_node_toolchain_at_the_root_or_under_static(self):
        for folder in (ROOT, ROOT / "static"):
            for name in NODE_FILES:
                self.assertFalse((folder / name).exists(), f"{folder / name} must not exist")
        self.assertEqual(list((ROOT / "static").rglob("package.json")), [])

    def test_browser_tests_are_never_served_as_static_files(self):
        for folder in settings.STATICFILES_DIRS:
            self.assertNotIn("browser_tests", str(folder))

    def test_the_django_suite_never_imports_browser_tests(self):
        # Django discovers test*.py; browser tests use bt_*.py so `manage.py test` needs no browser.
        self.assertEqual(sorted(p.name for p in BROWSER_TESTS.rglob("test*.py")), [])

    def test_listed_browser_test_files_keep_their_tests(self):
        for name, minimum in EXPECTED_BROWSER_TESTS.items():
            path = BROWSER_TESTS / name
            self.assertTrue(path.exists(), f"{name} is missing")
            count = len(re.findall(r"^\s+def test_\w+\(self", path.read_text(encoding="utf-8"), re.M))
            self.assertGreaterEqual(count, minimum, f"{name} has {count} tests, expected at least {minimum}")

    def test_no_skipped_or_expected_failure_browser_tests(self):
        # main never holds skipped or expected-failing browser tests (spec section 9).
        banned = re.compile(r"\b(skip|skipIf|skipUnless|SkipTest|expectedFailure)\b")
        for path in BROWSER_TESTS.rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(banned.search(line), f"{path.name}:{number}: {line.strip()}")
