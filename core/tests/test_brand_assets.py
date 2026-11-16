"""The Everclass logo files (docs/superpowers/specs/2026-11-16-everclass-logo-palette-design.md)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BRAND = Path(settings.BASE_DIR) / "static" / "brand"
LOGO_COLOURS = ("#1bb5a8", "#f5b82e", "#0b2a4a")
OLD_GREEN = "#185842"
MARK_VIEWBOX = "7 6 50 50"


class BrandFileTests(SimpleTestCase):
    def read(self, name):
        return (BRAND / name).read_text(encoding="utf-8").lower()

    def test_mark_is_cropped_to_the_glyph(self):
        # Drawn on a 64-unit grid; the square viewBox crops the empty margin so small sizes stay legible.
        self.assertIn(f'viewbox="{MARK_VIEWBOX}"', self.read("everclass-mark.svg"))

    def test_both_files_use_the_logo_colours_and_not_the_old_green(self):
        for name in ("everclass-mark.svg", "everclass-logo.svg"):
            svg = self.read(name)
            for colour in LOGO_COLOURS:
                with self.subTest(file=name, colour=colour):
                    self.assertIn(colour, svg)
            self.assertNotIn(OLD_GREEN, svg)

    def test_logo_carries_the_product_name(self):
        self.assertIn("Everclass ERP", (BRAND / "everclass-logo.svg").read_text(encoding="utf-8"))


class AppMarkTests(SimpleTestCase):
    def test_inline_mark_is_the_loop_not_the_book_and_sun(self):
        mark = (Path(settings.BASE_DIR) / "templates" / "partials" / "_brand_mark.html").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn(f'<svg class="erp-brand-mark" aria-hidden="true" focusable="false" viewbox="{MARK_VIEWBOX}">', mark)
        self.assertIn("#1bb5a8", mark)
        self.assertNotIn(OLD_GREEN, mark)
        self.assertNotIn("#e9b949", mark)  # the old sun

    def test_inline_mark_draws_the_same_loop_as_the_brand_file(self):
        mark = (Path(settings.BASE_DIR) / "templates" / "partials" / "_brand_mark.html").read_text(encoding="utf-8")
        loop = "M32 37C38 25 54 25 54 37C54 49 38 49 32 37C26 25 10 25 10 37C10 49 26 49 32 37"
        self.assertIn(loop, mark)
        self.assertIn(loop, (BRAND / "everclass-mark.svg").read_text(encoding="utf-8"))


class TemplateColourTests(SimpleTestCase):
    def test_no_template_uses_the_old_brand_green(self):
        base = Path(settings.BASE_DIR)
        roots = [base / "templates", *base.glob("*/templates")]  # project and app templates
        self.assertIn(base / "core" / "templates", roots)
        offenders = [
            str(path.relative_to(base))
            for root in roots
            for path in root.rglob("*.html")
            if OLD_GREEN in path.read_text(encoding="utf-8").lower()
        ]
        self.assertEqual(offenders, [])

    def test_browser_tab_icon_is_the_mark(self):
        head = (Path(settings.BASE_DIR) / "templates" / "partials" / "_pwa_head.html").read_text(encoding="utf-8")
        self.assertIn(
            """<link rel="icon" href="{% static 'brand/everclass-mark.svg' %}" type="image/svg+xml">""", head
        )


class AttendanceToggleColourTests(SimpleTestCase):
    def rule(self, selector):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css[css.index(selector + " {") :]
        return block[: block.index("}")]

    def test_ticked_present_is_success_green_like_the_present_pill(self):
        rule = self.rule(".erp-toggles input:checked + .erp-toggle.is-present")
        self.assertIn("background: var(--erp-ok);", rule)
        self.assertIn("border-color: var(--erp-ok);", rule)
        self.assertNotIn("--erp-action", rule)


class PwaIconTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from core.management.commands.generate_pwa_icons import draw_icon

        cls.maskable = draw_icon(512, rounded=False, glyph_scale=0.72).convert("RGB")

    def test_loop_crossing_is_logo_teal(self):
        # The crossing sits at (32, 37) on the 64-unit grid: 5 units below centre.
        pixel = self.maskable.getpixel((256, 285))
        for got, want in zip(pixel, (0x1B, 0xB5, 0xA8)):
            self.assertLessEqual(abs(got - want), 40, pixel)

    def test_maskable_glyph_stays_inside_the_safe_circle(self):
        radius = 512 * 0.4
        width, height = self.maskable.size
        for y in range(0, height, 4):
            for x in range(0, width, 4):
                if (x - 256) ** 2 + (y - 256) ** 2 > radius**2:
                    self.assertEqual(self.maskable.getpixel((x, y)), (255, 255, 255), (x, y))
