"""Audit 19 (PR 4): upload forms submit once with busy wording, route focus to errors, filter file types."""

import re

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core import school_logo
from core.tests.test_school_logo import LogoFixture, image_bytes
from core.tests.test_ui_admin_desktop_d1_6e_bulk_imports import UPLOAD, Base, html

JS = (settings.BASE_DIR / "static" / "js" / "erp.js").read_text(encoding="utf-8")


def tag(page, pattern):
    return re.search(pattern, page).group(0)


class LogoUploadTests(LogoFixture, TestCase):
    def setUp(self):
        self.build_logo_fixture()
        self.admin_client = self.client_for(self.admin)

    def page(self):
        return self.admin_client.get(reverse("core:school-detail")).content.decode()

    def test_file_input_filters_types_and_carries_the_limits(self):
        field = tag(self.page(), r'<input type="file"[^>]*name="image"[^>]*>')
        self.assertIn('accept="image/png,image/jpeg,.png,.jpg,.jpeg"', field)
        self.assertIn(f'data-erp-max-bytes="{school_logo.MAX_UPLOAD_BYTES}"', field)
        self.assertIn(f'data-erp-max-px="{school_logo.MAX_DIMENSION}"', field)

    def test_submit_button_submits_once_with_busy_wording(self):
        button = tag(self.page(), r'<button type="submit"[^>]*>\s*Upload logo')
        self.assertIn("data-erp-once", button)
        self.assertIn('data-erp-once-busy="Uploading logo…"', button)

    def test_rejected_upload_shows_a_summary_and_focuses_the_file_input(self):
        response = self.upload(self.admin_client, b"not an image", "logo.png")
        page = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="form-error-summary"', page)
        self.assertIn("before uploading the logo", page)
        self.assertIn('href="#id_image"', page)
        field = tag(page, r'<input type="file"[^>]*name="image"[^>]*>')
        self.assertIn('aria-invalid="true"', field)
        self.assertIn("autofocus", field)
        self.assertIn("id_image_error", field)
        self.assertEqual(page.count("autofocus"), 1)

    def test_valid_upload_still_redirects(self):
        response = self.upload(self.admin_client, image_bytes("PNG"))
        self.assertRedirects(response, reverse("core:school-detail"))


class ImportUploadTests(Base):
    def test_file_input_filters_to_xlsx(self):
        field = tag(html(self.client.get(UPLOAD)), r'<input type="file"[^>]*name="file"[^>]*>')
        self.assertIn(
            'accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"', field
        )

    def test_check_button_submits_once_with_busy_wording(self):
        button = tag(html(self.client.get(UPLOAD)), r'<button type="submit"[^>]*>\s*Check file')
        self.assertIn("data-erp-once", button)
        self.assertIn('data-erp-once-busy="Checking file…"', button)

    def test_rejected_file_focuses_the_file_input(self):
        page = html(self.upload(b"name,class\n", name="students.csv"))
        field = tag(page, r'<input type="file"[^>]*name="file"[^>]*>')
        self.assertIn('aria-invalid="true"', field)
        self.assertIn("autofocus", field)
        self.assertEqual(page.count("autofocus"), 1)

    def test_confirm_import_submits_once_with_busy_wording(self):
        button = tag(self.page(self.clean()), r'<button type="submit"[^>]*>\s*Confirm import')
        self.assertIn("data-erp-once", button)
        self.assertIn('data-erp-once-busy="Importing records…"', button)


class UploadScriptTests(TestCase):
    """The shared script: busy wording + status, reset on Back; logo checks before previewing."""

    def test_submit_once_shows_busy_wording_and_a_polite_status(self):
        block = JS.split('querySelectorAll("[data-erp-once]")')[1][:1500]
        self.assertIn("data-erp-once-busy", block)
        self.assertIn('setAttribute("aria-busy", "true")', block)
        self.assertIn('setAttribute("role", "status")', block)
        self.assertIn("pageshow", block)  # Back from the next page re-enables the button

    def test_logo_preview_checks_size_and_type_before_decoding(self):
        block = JS.split("[data-erp-logo-form]")[1][:3000]
        self.assertLess(block.index("data-erp-max-bytes"), block.index("createObjectURL"))
        self.assertIn("data-erp-max-px", block)
        self.assertIn("will be refused", block)
