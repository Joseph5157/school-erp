"""Change-password page: live rules checklist, strength meter and match line (progressive enhancement)."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class PasswordStrengthPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ravi.kumar", password="Old-pass-12345")
        self.client.force_login(self.user)

    def page(self):
        return self.client.get(reverse("password_change")).content.decode()

    def test_rules_list_names_the_enforced_rules(self):
        html = self.page()
        rules = re.search(r'<ul class="erp-pw-rules"[^>]*>.*?</ul>', html, re.S)
        self.assertIsNotNone(rules)
        rules = rules.group(0)
        self.assertIn('data-erp-pw-rules data-min-length="8" data-username="ravi.kumar"', rules)
        self.assertIn('<li data-rule="length">At least 8 characters', rules)
        self.assertIn('<li data-rule="numeric">Not only numbers', rules)
        self.assertIn('<li data-rule="username">Not like your username', rules)
        self.assertIn('<li class="erp-pw-note">Avoid common passwords', rules)

    def test_new_password_points_at_the_rules_and_django_help_list_is_gone(self):
        html = self.page()
        self.assertRegex(html, r'id="id_new_password1"[^>]*aria-describedby="pw-rules pw-meter"')
        self.assertNotIn("Your password can’t be too similar", html)

    def test_meter_and_match_line_start_hidden_for_no_js(self):
        html = self.page()
        self.assertIn('<div class="erp-pw-meter" id="pw-meter" data-erp-pw-meter hidden>', html)
        self.assertIn('<p class="erp-pw-match small mt-1" data-erp-pw-match aria-live="polite" hidden></p>', html)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    ])
    def test_minimum_length_follows_the_validator_setting(self):
        html = self.page()
        self.assertIn('data-min-length="12"', html)
        self.assertIn("At least 12 characters", html)

    def test_server_still_rejects_a_weak_password(self):
        response = self.client.post(reverse("password_change"), {
            "old_password": "Old-pass-12345", "new_password1": "12345678", "new_password2": "12345678",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is-invalid")

    def test_script_wires_the_meter(self):
        script = (Path(settings.BASE_DIR) / "static" / "js" / "erp.js").read_text(encoding="utf-8")
        self.assertIn("[data-erp-pw-rules]", script)
        self.assertIn("[data-erp-pw-meter]", script)
        self.assertIn("[data-erp-pw-match]", script)
