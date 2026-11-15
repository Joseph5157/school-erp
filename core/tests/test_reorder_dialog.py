"""Order pop-ups are native modal dialogs (modern-web audit 06, D-01 and D-03).

A <dialog> opened with showModal() closes on Escape and on the phone's Back, makes the page behind
inert and returns focus to its opener; Bootstrap's modal div did none of the Back part.
"""

import re
from pathlib import Path

from django.apps import apps
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
        # Only this project's templates: the project folder and its own apps (not .venv or site-packages).
        folders = [ROOT / "templates"] + [
            Path(app.path) / "templates" for app in apps.get_app_configs() if Path(app.path).parent == ROOT
        ]
        pages = [page for folder in folders if folder.is_dir() for page in folder.rglob("*.html")]
        self.assertGreater(len(pages), 50)
        offenders = [
            str(page) for page in pages
            if re.search(r'class="modal[ "]|data-bs-toggle="modal"', page.read_text(encoding="utf-8"))
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
        self.assertIn('dialog.addEventListener("close", function () {\n      document.body.style.paddingRight = "";', SCRIPT)

    def test_page_keeps_the_scrollbar_space_while_locked(self):
        self.assertIn("var gap = window.innerWidth - document.documentElement.clientWidth;", SCRIPT)
        self.assertIn('if (gap > 0) document.body.style.paddingRight = gap + "px";', SCRIPT)

    def test_backdrop_tap_closes_only_when_the_press_started_there(self):
        self.assertIn("pressedBackdrop = event.target === dialog;", SCRIPT)
        self.assertIn("if (pressedBackdrop && event.target === dialog) dialog.close();", SCRIPT)


class ReorderDialogCssTests(TestCase):
    def test_bootstrap_modal_styles_are_gone(self):
        self.assertNotIn(".modal-content {", CSS)

    def test_height_follows_the_visible_phone_screen(self):
        self.assertIn("max-height: min(85vh, 45rem); max-height: min(85dvh, 45rem);", CSS)

    def test_page_behind_does_not_scroll(self):
        self.assertIn("body:has(.erp-dialog[open]) { overflow: hidden; }", CSS)
        self.assertIn("overscroll-behavior: contain;", CSS)

    def test_phone_sheet_and_reduced_motion(self):
        self.assertIn(
            ".erp-dialog { width: 100%; max-width: 100%; margin: auto 0 0; border-radius: 1rem 1rem 0 0; }", CSS
        )
        self.assertIn("@media (prefers-reduced-motion: no-preference) {\n  .erp-dialog[open]", CSS)
