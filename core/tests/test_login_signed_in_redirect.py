"""A signed-in login opening the login page goes to its home, not a login form inside the app shell.

Before: /accounts/login/ rendered for a signed-in user, so the form appeared with the office
sidebar and account menu around it (looked like "the sidebar shows without logging in").
"""

from django.test import TestCase
from django.urls import reverse

from core.tests.test_authorization import AuthorizationClientsMixin


class SignedInLoginPageTests(AuthorizationClientsMixin, TestCase):
    def test_signed_in_administrator_is_sent_home(self):
        response = self.administrator.get(reverse("login"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_signed_in_login_follows_a_safe_next(self):
        response = self.administrator.get(reverse("login") + "?next=/choose-area/")
        self.assertRedirects(response, "/choose-area/", fetch_redirect_response=False)

    def test_an_outside_next_is_ignored(self):
        response = self.administrator.get(reverse("login") + "?next=https://evil.example/")
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_login_without_an_area_is_sent_home_too(self):
        response = self.non_admin.get(reverse("login"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_anonymous_visitor_still_gets_the_plain_login_page(self):
        response = self.anonymous.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn('name="password"', page)
        self.assertNotIn('id="erp-sidebar"', page)
        self.assertNotIn("erp-account", page)

    def test_anonymous_login_still_works(self):
        response = self.anonymous.post(
            reverse("login"), {"username": "administrator", "password": "pass-12345"}
        )
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
