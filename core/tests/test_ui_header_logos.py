"""Top bar with a school logo and the Everclass mark: both fit on phones (PR #241 review)."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class HeaderLogoCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")

    def rule(self, selector, start=0):
        block = self.css[self.css.index(selector + " {", start) :]
        return block[: block.index("}")]

    def test_brand_shrinks_and_trims_the_name_instead_of_pushing_the_account_menu_off_screen(self):
        brand = self.rule(".erp-brand")
        for declaration in ("min-width: 0;", "overflow: hidden;", "text-overflow: ellipsis;", "white-space: nowrap;"):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, brand)

    def test_divider_does_not_eat_into_the_logo_width(self):
        # border-box sizing: the .5rem padding and 1px hairline sit on top of the 96px image area.
        self.assertIn("max-width: calc(96px + .5rem + 1px);", self.rule(".erp-brand-logo"))

    def test_phones_cap_the_school_logo_narrower(self):
        phone = self.css.index("@media (max-width: 575.98px) {\n  .erp-brand-logo")
        self.assertIn("max-width: calc(56px + .5rem + 1px);", self.rule("  .erp-brand-logo", phone))
