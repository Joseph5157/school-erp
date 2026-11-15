"""Static files are served Brotli-compressed when the browser accepts it (modern-web audit 08, P8-08).

WhiteNoise writes .br files at collectstatic only if the Brotli package is installed, so the
requirement is declared rather than left to arrive by chance through another library.
"""

import importlib.util
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class BrotliTests(SimpleTestCase):
    def test_requirements_ask_for_whitenoise_with_brotli(self):
        # Any WhiteNoise version, as long as the [brotli] extra stays on the line.
        text = (Path(settings.BASE_DIR) / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^whitenoise\[brotli\]==\S+\s*$")  # \s*: Windows lines end in \r

    def test_brotli_is_installed_in_this_build(self):
        self.assertIsNotNone(importlib.util.find_spec("brotli"))
