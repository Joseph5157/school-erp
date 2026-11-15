"""Small shared fixes from the modern-web audits (04, 05, 06, 07, 09).

- Both page shells follow the OS text-size setting and declare the light-only colour scheme.
- Marks "Save draft" is one-shot (one-shot buttons stay disabled after Back, on purpose).
- The marks Enter-to-next-student shortcut ignores Enter that confirms an IME composition.
- The phone menu button reports open/closed as soon as the drawer starts moving.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.tests.test_ui_teacher_marks import MarksFixture

BASE = Path(settings.BASE_DIR)


def read(relative):
    return (BASE / relative).read_text(encoding="utf-8")


class ShellMetaTests(SimpleTestCase):
    def test_both_shells_opt_into_os_text_scale_and_light_scheme(self):
        for shell in ("templates/base.html", "templates/portal/base.html"):
            with self.subTest(shell=shell):
                html = read(shell)
                self.assertIn('<meta name="text-scale" content="scale">', html)
                self.assertIn('<meta name="color-scheme" content="light">', html)

    def test_css_declares_the_light_scheme_on_root(self):
        self.assertIn(":root {\n  color-scheme: light;", read("static/css/erp.css"))


class ScriptTests(SimpleTestCase):
    def setUp(self):
        self.script = read("static/js/erp.js")

    def test_marks_enter_skips_ime_composition(self):
        self.assertIn("if (event.isComposing || event.keyCode === 229) return;", self.script)

    def test_menu_button_state_changes_when_the_drawer_starts_moving(self):
        self.assertIn('drawer.addEventListener("show.bs.offcanvas"', self.script)
        self.assertIn('drawer.addEventListener("hide.bs.offcanvas"', self.script)

    def test_one_shot_buttons_stay_disabled_after_back(self):
        # Publishing a notice has no repeat guard, so a button restored by Back must not
        # come alive again: that would let one click send a second notice to every guardian.
        self.assertNotIn('addEventListener("pageshow"', self.script)


class MarksSaveOnceTests(MarksFixture, TestCase):
    def test_save_draft_is_one_shot(self):
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, '<button type="submit" class="btn btn-primary" data-erp-once>Save draft</button>')
