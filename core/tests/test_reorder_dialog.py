"""Order pop-ups are native modal dialogs (modern-web audit 06, D-01 and D-03).

A <dialog> opened with showModal() closes on Escape and on the phone's Back, makes the page behind
inert and returns focus to its opener; Bootstrap's modal div did none of the Back part.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

ROOT = Path(settings.BASE_DIR)
SCRIPT = (ROOT / "static" / "js" / "erp.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "css" / "erp.css").read_text(encoding="utf-8")
TEMPLATES = [
    ROOT / "core" / "templates" / "core" / "class_grade_list.html",
    ROOT / "core" / "templates" / "core" / "academic_year_offerings.html",
]


class ReorderDialogMarkupTests(TestCase):
    def test_templates_use_dialog_not_bootstrap_modal(self):
        for path in TEMPLATES:
            with self.subTest(template=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertRegex(text, r'<dialog class="erp-dialog" id="[^"]+" aria-labelledby="[^"]+-title">')
                self.assertIn("data-erp-dialog-open=", text)
                self.assertEqual(text.count("data-erp-dialog-close"), 2)  # the X and Cancel
                for gone in ('class="modal', "data-bs-toggle", "data-bs-dismiss", "data-bs-target"):
                    self.assertNotIn(gone, text)

    def test_no_bootstrap_modal_left_in_any_template(self):
        offenders = [
            str(path) for path in ROOT.rglob("*.html")
            if ".worktrees" not in path.parts and "node_modules" not in path.parts
            and re.search(r'class="modal[ "]|data-bs-toggle="modal"', path.read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(offenders, [])


class ReorderDialogScriptTests(TestCase):
    def test_opens_as_a_modal_and_falls_back_without_dialog_support(self):
        self.assertIn('if (!dialog || typeof dialog.showModal !== "function") return;', SCRIPT)
        self.assertIn("dialog.showModal();", SCRIPT)
        self.assertNotIn("hidden.bs.modal", SCRIPT)

    def test_focus_starts_on_the_first_usable_arrow(self):
        self.assertIn('form.querySelector("[data-erp-reorder-move]:not(:disabled)")', SCRIPT)

    def test_closing_any_way_puts_the_list_back(self):
        self.assertIn('dialog.addEventListener("close", function () {', SCRIPT)

    def test_backdrop_tap_closes_only_when_the_press_started_there(self):
        self.assertIn("pressedBackdrop = event.target === dialog;", SCRIPT)
        self.assertIn("if (pressedBackdrop && event.target === dialog) dialog.close();", SCRIPT)


class ReorderDialogCssTests(TestCase):
    def test_bootstrap_modal_styles_are_gone(self):
        self.assertNotIn(".modal-content {", CSS)

    def test_page_behind_does_not_scroll(self):
        self.assertIn("body:has(.erp-dialog[open]) { overflow: hidden; }", CSS)
        self.assertIn("overscroll-behavior: contain;", CSS)

    def test_phone_sheet_and_reduced_motion(self):
        self.assertIn(
            ".erp-dialog { width: 100%; max-width: 100%; margin: auto 0 0; border-radius: 1rem 1rem 0 0; }", CSS
        )
        self.assertIn("@media (prefers-reduced-motion: no-preference) {\n  .erp-dialog[open]", CSS)
