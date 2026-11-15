"""Phone fields open the phone keypad; shared-summary forms are checked by the server.

- Every phone field renders `type="tel"` so phones show the number keypad.
- Forms using FieldAccessibilityMixin mark their inputs with `data-erp-validate="server"`;
  erp.js then turns off the browser's own pop-up checks for those forms, so errors use the
  linked summary, aria-invalid and focus. Without JS the browser checks still run first.
- Long student names wrap on the attendance roster instead of being clipped.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.forms import ApplicantForm, GuardianForm, RecordCorrectionForm

STATIC = Path(settings.BASE_DIR) / "static"


class PhoneFieldTests(SimpleTestCase):
    def test_every_phone_field_is_tel(self):
        for form_class in (ApplicantForm, GuardianForm, RecordCorrectionForm):
            with self.subTest(form=form_class.__name__):
                self.assertIn('type="tel"', str(form_class()["phone"]))


class ServerValidationMarkerTests(SimpleTestCase):
    def test_mixin_forms_mark_their_inputs(self):
        self.assertIn('data-erp-validate="server"', str(ApplicantForm()["full_name"]))

    def test_marker_survives_error_state(self):
        form = ApplicantForm(data={"full_name": ""})
        self.assertFalse(form.is_valid())
        self.assertIn('data-erp-validate="server"', str(form["full_name"]))

    def test_forms_without_the_mixin_keep_browser_checks(self):
        self.assertNotIn("data-erp-validate", str(GuardianForm()["full_name"]))

    def test_erp_js_turns_off_browser_checks_for_marked_forms(self):
        script = (STATIC / "js" / "erp.js").read_text(encoding="utf-8")
        self.assertIn('form.querySelector("[data-erp-validate=server]")', script)
        self.assertIn("form.noValidate = true", script)


class RosterNameWrapTests(SimpleTestCase):
    def test_long_names_wrap(self):
        css = (STATIC / "css" / "erp.css").read_text(encoding="utf-8")
        self.assertIn(
            ".erp-roster-name { grid-column: 2; grid-row: 1; font-weight: 600; "
            "min-width: 0; overflow-wrap: anywhere; }",
            css,
        )
