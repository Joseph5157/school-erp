"""Modern web audit 12 A11Y-02: input, select and checkbox edges meet 3:1 non-text contrast."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR, "static", "css", "erp.css")


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ControlBorderTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")

    def token(self, name):
        return re.search(rf"--erp-{name}: (#[0-9a-f]{{6}});", self.css).group(1)

    def test_control_border_reaches_three_to_one_on_white_and_paper(self):
        border = self.token("control-border")
        self.assertGreaterEqual(contrast(border, self.token("surface")), 3)
        self.assertGreaterEqual(contrast(border, self.token("paper")), 3)

    def test_erp_fields_and_bootstrap_fields_use_the_token(self):
        self.assertNotIn("#aeb6ae", self.css)
        self.assertIn("border: 1px solid var(--erp-control-border);", self.css)
        self.assertIn(
            ".form-control, .form-select, .form-check-input { border-color: var(--erp-control-border); }", self.css
        )
