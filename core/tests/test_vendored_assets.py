"""Front-end libraries are served from our own static files, never from a CDN.

- No template loads a script or stylesheet from another origin.
- Each vendored file still matches its published sha384 checksum (static/vendor/README.md).
- The source maps the minified files point at exist, so collectstatic does not fail.
"""

import base64
import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
VENDOR = BASE / "static" / "vendor"

EXPECTED = {
    "bootstrap/5.3.3/css/bootstrap.min.css":
        "QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH",
    "bootstrap/5.3.3/js/bootstrap.bundle.min.js":
        "YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz",
    "htmx/2.0.4/htmx.min.js":
        "HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+",
    "sortablejs/1.15.6/Sortable.min.js":
        "HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU",
}

# <script src="http..."> or <link ... href="http..." rel="stylesheet"> in any order.
REMOTE_ASSET = re.compile(
    r"<script\b[^>]*\bsrc=[\"'](?:https?:)?//"
    r"|<link\b(?=[^>]*\brel=[\"']?(?:stylesheet|modulepreload|preload))[^>]*\bhref=[\"'](?:https?:)?//",
    re.IGNORECASE,
)


def sha384(path):
    return base64.b64encode(hashlib.sha384(path.read_bytes()).digest()).decode()


class VendoredAssetTests(SimpleTestCase):
    def test_no_template_loads_scripts_or_styles_from_another_origin(self):
        offenders = []
        for folder in (BASE / "templates", BASE / "core" / "templates"):
            for template in folder.rglob("*.html"):
                if REMOTE_ASSET.search(template.read_text(encoding="utf-8")):
                    offenders.append(str(template.relative_to(BASE)))
        self.assertEqual(offenders, [])

    def test_vendored_files_match_their_published_checksums(self):
        for name, digest in EXPECTED.items():
            with self.subTest(file=name):
                self.assertEqual(sha384(VENDOR / name), digest)

    def test_every_vendored_library_keeps_its_license(self):
        for name in EXPECTED:
            library_root = VENDOR / Path(name).parts[0] / Path(name).parts[1]
            with self.subTest(library=str(library_root.relative_to(VENDOR))):
                self.assertTrue((library_root / "LICENSE").is_file())

    def test_source_maps_referenced_by_minified_files_exist(self):
        for name in EXPECTED:
            path = VENDOR / name
            match = re.search(r"sourceMappingURL=(\S+?)\s*(?:\*/)?\s*$", path.read_text(encoding="utf-8"))
            if match:
                with self.subTest(file=name):
                    self.assertTrue((path.parent / match.group(1)).is_file())

    def test_staticfiles_finds_the_vendored_files(self):
        for name in EXPECTED:
            with self.subTest(file=name):
                self.assertIsNotNone(finders.find(f"vendor/{name}"))
