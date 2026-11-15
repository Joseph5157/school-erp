"""After a rejected POST, errors are announced and focus lands on the problem.

Modern-web audits 04 (marks entry) and 05 (login, password change):
- Marks entry shows the linked error summary, wires each row's error text to its input with
  matching ids, and starts focus on the first invalid score.
- Password change shows the linked summary, marks invalid inputs aria-invalid with their error
  text described, and focuses the first invalid input.
- Login focuses the password when only the password is missing.
"""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.tests.test_ui_teacher_marks import MarksFixture


def input_tag(html, element_id):
    match = re.search(rf'<input[^>]*\bid="{element_id}"[^>]*>', html)
    assert match, f"no input with id {element_id}"
    return match.group(0)


class MarksEntryErrorTests(MarksFixture, TestCase):
    def post_bad_rows(self):
        data = {f"status_{self.asha.pk}": "ABSENT", f"score_{self.asha.pk}": "5",
                f"status_{self.bina.pk}": "MARKED", f"score_{self.bina.pk}": ""}
        return self.teacher.post(self.entry_url(self.test1), data)

    def test_summary_links_each_bad_row_by_student_name(self):
        html = self.post_bad_rows().content.decode()
        self.assertIn('id="form-error-summary"', html)
        self.assertIn(
            f'<a href="#id_score_{self.asha.pk}">Score for Asha: An absent Student has no score.</a>',
            html,
        )
        self.assertIn(
            f'<a href="#id_score_{self.bina.pk}">Score for Bina: Enter a score or choose Absent.</a>',
            html,
        )

    def test_error_text_has_the_id_the_input_points_at(self):
        html = self.post_bad_rows().content.decode()
        tag = input_tag(html, f"id_score_{self.asha.pk}")
        self.assertIn('aria-invalid="true"', tag)
        self.assertIn(f'aria-describedby="id_score_{self.asha.pk}_error"', tag)
        self.assertIn(f'id="id_score_{self.asha.pk}_error"', html)

    def test_focus_starts_on_the_first_invalid_score_only(self):
        html = self.post_bad_rows().content.decode()
        self.assertIn("autofocus", input_tag(html, f"id_score_{self.asha.pk}"))
        self.assertNotIn("autofocus", input_tag(html, f"id_score_{self.bina.pk}"))
        self.assertEqual(html.count("autofocus"), 1)

    def test_valid_rows_and_the_first_visit_have_no_error_state(self):
        html = self.post_bad_rows().content.decode()
        self.assertNotIn("aria-invalid", input_tag(html, f"id_score_{self.ravi.pk}"))
        page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertNotIn("form-error-summary", page)
        self.assertNotIn("autofocus", page)

    def test_scores_are_checked_by_the_server(self):
        # The shared marker makes erp.js send the form to the server instead of a browser pop-up.
        page = self.teacher.get(self.entry_url(self.test1)).content.decode()
        self.assertIn('data-erp-validate="server"', input_tag(page, f"id_score_{self.asha.pk}"))


class PasswordChangeErrorTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="meena", password="old-pass-123")
        self.client.login(username="meena", password="old-pass-123")
        self.url = reverse("password_change")

    def post(self, old="old-pass-123", new1="a-much-better-pass-9", new2="a-much-better-pass-9"):
        data = {"old_password": old, "new_password1": new1, "new_password2": new2}
        return self.client.post(self.url, data).content.decode()

    def test_wrong_old_password_is_summarised_described_and_focused(self):
        html = self.post(old="wrong")
        self.assertIn('id="form-error-summary"', html)
        self.assertIn('<a href="#id_old_password">', html)
        tag = input_tag(html, "id_old_password")
        self.assertIn('aria-invalid="true"', tag)
        self.assertIn('aria-describedby="id_old_password_error"', tag)
        self.assertIn("autofocus", tag)
        self.assertIn('id="id_old_password_error"', html)
        self.assertEqual(html.count("autofocus"), 1)

    def test_mismatch_focuses_the_confirmation_and_keeps_the_rules_description(self):
        html = self.post(new2="something-else-77")
        tag = input_tag(html, "id_new_password2")
        self.assertIn('aria-invalid="true"', tag)
        self.assertIn("autofocus", tag)
        self.assertIn('aria-describedby="pw-rules pw-meter"', input_tag(html, "id_new_password1"))

    def test_weak_new_password_is_described_after_the_rules(self):
        html = self.post(new1="12345678", new2="12345678")
        tag = input_tag(html, "id_new_password2")
        self.assertIn('aria-invalid="true"', tag)
        self.assertIn('aria-describedby="id_new_password2_error"', tag)
        self.assertIn("autofocus", tag)

    def test_first_visit_has_no_error_state(self):
        html = self.client.get(self.url).content.decode()
        self.assertNotIn("form-error-summary", html)
        self.assertNotIn("aria-invalid", html)
        self.assertNotIn("autofocus", html)


class LoginFocusTests(TestCase):
    def setUp(self):
        self.url = reverse("login")

    def test_first_visit_focuses_the_username(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("autofocus", input_tag(html, "id_username"))
        self.assertNotIn("autofocus", input_tag(html, "id_password"))

    def test_missing_password_focuses_the_password(self):
        html = self.client.post(self.url, {"username": "meena", "password": ""}).content.decode()
        self.assertIn("autofocus", input_tag(html, "id_password"))
        self.assertNotIn("autofocus", input_tag(html, "id_username"))

    def test_missing_username_focuses_the_username(self):
        html = self.client.post(self.url, {"username": "", "password": ""}).content.decode()
        self.assertIn("autofocus", input_tag(html, "id_username"))
        self.assertNotIn("autofocus", input_tag(html, "id_password"))

    def test_wrong_credentials_go_back_to_the_username(self):
        html = self.client.post(self.url, {"username": "nobody", "password": "x"}).content.decode()
        self.assertIn("autofocus", input_tag(html, "id_username"))
        self.assertNotIn("autofocus", input_tag(html, "id_password"))
