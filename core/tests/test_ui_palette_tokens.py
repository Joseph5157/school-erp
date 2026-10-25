"""UI-10: brand, action and success tokens are split; success no longer aliases the accent."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ACCENT = {"": "#1f6b52", "-strong": "#185842", "-wash": "#e3efe9"}
SUFFIXES = ("", "-strong", "-wash")


class PaletteTokenTests(SimpleTestCase):
    def setUp(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        root = css[css.index(":root {") :]
        self.root = root[: root.index("\n}")]
        self.decls = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", self.root))

    def resolve(self, name):
        value = self.decls[name].strip()
        match = re.fullmatch(r"var\((--erp-[\w-]+)\)", value)
        return self.resolve(match.group(1)) if match else value.lower()

    @staticmethod
    def luminance(hex_colour):
        channels = []
        for index in (1, 3, 5):
            value = int(hex_colour[index : index + 2], 16) / 255
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def contrast(self, first, second):
        high, low = sorted((self.luminance(first), self.luminance(second)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def test_all_nine_tokens_exist(self):
        for family in ("brand", "action", "ok"):
            for suffix in SUFFIXES:
                with self.subTest(token=f"--erp-{family}{suffix}"):
                    self.assertIn(f"--erp-{family}{suffix}", self.decls)

    def test_success_tokens_are_literal_hex_not_aliases(self):
        for suffix in SUFFIXES:
            with self.subTest(suffix=suffix):
                value = self.decls[f"--erp-ok{suffix}"].strip()
                self.assertRegex(value, r"^#[0-9a-fA-F]{6}$")
                self.assertNotIn("var(", value)

    def test_brand_action_and_success_default_to_the_accent_values(self):
        for family in ("brand", "action", "ok"):
            for suffix in SUFFIXES:
                with self.subTest(token=f"--erp-{family}{suffix}"):
                    self.assertEqual(self.resolve(f"--erp-{family}{suffix}"), ACCENT[suffix])

    def test_accent_stays_a_plain_hex_for_existing_tests(self):
        for suffix in SUFFIXES:
            self.assertRegex(self.decls[f"--erp-accent{suffix}"].strip(), r"^#[0-9a-fA-F]{6}$")

    def test_bootstrap_primary_follows_the_action_token(self):
        self.assertEqual(self.decls["--bs-primary"].strip(), "var(--erp-action)")
        self.assertEqual(self.decls["--bs-link-color"].strip(), "var(--erp-action)")
        rgb = tuple(int(self.resolve("--erp-action")[i : i + 2], 16) for i in (1, 3, 5))
        self.assertEqual(self.decls["--bs-primary-rgb"].replace(" ", ""), ",".join(map(str, rgb)))

    def test_strong_text_on_wash_meets_aa(self):
        for family in ("brand", "action", "ok"):
            with self.subTest(family=family):
                ratio = self.contrast(
                    self.resolve(f"--erp-{family}-strong"), self.resolve(f"--erp-{family}-wash")
                )
                self.assertGreaterEqual(ratio, 4.5)
