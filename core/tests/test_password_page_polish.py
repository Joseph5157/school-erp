"""Password pages polish (modern-web audit 05).

- MW05-03: each Show button names its field for screen readers ("Show old password").
- MW05-04: the change form carries the account's username for password managers.
- MW05-05: the match line speaks only when its answer changes, and a mismatch waits for blur.
- MW05-06: phone keyboards don't autocorrect the username and label Enter Next / Done.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

SCRIPT = (Path(settings.BASE_DIR) / "static" / "js" / "erp.js").read_text(encoding="utf-8")


def tag(html, element_id):
    found = re.search(rf'<input[^>]*id="{element_id}"[^>]*>', html)
    assert found, f"no <input id={element_id}> on the page"
    return found.group(0)


class PasswordChangePolishTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ravi.kumar", password="Old-pass-12345")
        self.client.force_login(self.user)
        self.html = self.client.get(reverse("password_change")).content.decode()

    def test_each_show_button_names_its_field(self):
        for field, name in (
            ("id_old_password", "old password"),
            ("id_new_password1", "new password"),
            ("id_new_password2", "new password confirmation"),
        ):
            with self.subTest(field=field):
                self.assertIn(
                    f'aria-controls="{field}" hidden><span data-erp-toggle-label>Show</span>'
                    f'<span class="visually-hidden"> {name}</span></button>',
                    self.html,
                )

    def test_username_context_for_password_managers(self):
        account = tag(self.html, "pw-account")
        self.assertIn('value="ravi.kumar"', account)
        self.assertIn('autocomplete="username"', account)
        self.assertIn("readonly", account)
        self.assertIn('tabindex="-1"', account)  # not a Tab stop; password managers still read it
        self.assertNotIn("name=", account)  # shown, never submitted
        self.assertIn('<label class="form-label" for="pw-account">Username</label>', self.html)

    def test_enter_key_hints(self):
        self.assertIn('enterkeyhint="next"', tag(self.html, "id_old_password"))
        self.assertIn('enterkeyhint="next"', tag(self.html, "id_new_password1"))
        self.assertIn('enterkeyhint="done"', tag(self.html, "id_new_password2"))

    def test_the_change_still_works(self):
        response = self.client.post(reverse("password_change"), {
            "old_password": "Old-pass-12345", "new_password1": "Fresh-pass-6789", "new_password2": "Fresh-pass-6789",
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Fresh-pass-6789"))


class LoginPolishTests(TestCase):
    def test_username_and_password_keyboard_hints(self):
        html = self.client.get(reverse("login")).content.decode()
        username = tag(html, "id_username")
        self.assertIn('autocorrect="off"', username)
        self.assertIn('enterkeyhint="next"', username)
        self.assertIn('enterkeyhint="done"', tag(html, "id_password"))
        self.assertIn(
            '<span data-erp-toggle-label>Show</span><span class="visually-hidden"> password</span></button>', html
        )


class PasswordScriptTests(TestCase):
    def test_toggle_changes_only_the_visible_word(self):
        self.assertIn('button.querySelector("[data-erp-toggle-label]") || button', SCRIPT)
        self.assertIn('word.textContent = showing ? "Show" : "Hide";', SCRIPT)
        self.assertNotIn('button.textContent = showing ? "Show" : "Hide";', SCRIPT)

    def test_match_line_speaks_only_on_change(self):
        self.assertIn("if (state === matchShown) return;", SCRIPT)
        self.assertIn('confirmInput.addEventListener("blur", checkMatchOnLeave);', SCRIPT)
        self.assertNotIn("Passwords don't match yet", SCRIPT)
        self.assertIn('input.addEventListener("blur", checkMatchOnLeave);', SCRIPT)

    def test_match_line_keeps_its_space_so_the_button_does_not_jump(self):
        self.assertIn("if (match) match.hidden = false;", SCRIPT)
        self.assertNotIn("match.hidden = state === null;", SCRIPT)
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-pw-match { color: var(--erp-ink-soft); min-height: 1.5em; }", css)

    def test_next_key_moves_to_the_next_field(self):
        self.assertIn("document.querySelectorAll('input[enterkeyhint=\"next\"]')", SCRIPT)
        self.assertIn("event.isComposing || event.keyCode === 229", SCRIPT)
