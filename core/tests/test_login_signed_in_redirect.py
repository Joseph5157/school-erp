"""A signed-in login opening the login page goes to its home, not a login form inside the app shell.

Before: /accounts/login/ rendered for a signed-in user, so the form appeared with the office
sidebar and account menu around it (looked like "the sidebar shows without logging in").
"""

import re

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

    def test_a_next_pointing_at_the_login_page_goes_home_not_500(self):
        # Django refuses to redirect a page to itself (ValueError -> 500); drop that next instead.
        for target in ("/accounts/login/", "/accounts/login/?expired=idle"):
            with self.subTest(target=target):
                response = self.administrator.get(reverse("login"), {"next": target})
                self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_anonymous_login_with_a_login_next_lands_home(self):
        response = self.anonymous.post(
            reverse("login") + "?next=/accounts/login/",
            {"username": "administrator", "password": "pass-12345"},
        )
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


class AccessDeniedPageTests(AuthorizationClientsMixin, TestCase):
    """The 403 page's second button lets a signed-in person switch account: Log out, not a login link
    (a login link now just bounces a signed-in user home, back to the same 403)."""

    def denied_page(self):
        response = self.non_admin.get(reverse("core:school-create"))
        self.assertEqual(response.status_code, 403)
        return response.content.decode()

    def test_offers_a_log_out_form_instead_of_a_sign_in_link(self):
        page = self.denied_page()
        body = page.split('id="forbidden-title"', 1)[1]
        self.assertIn(f'<form method="post" action="{reverse("logout")}"', body)
        self.assertIn('name="csrfmiddlewaretoken"', body)
        self.assertIn(">Log out and sign in as someone else</button>", body)
        self.assertNotIn(f'href="{reverse("login")}"', body)
        self.assertNotIn("Go to the sign-in page", body)

    def test_the_log_out_button_signs_out(self):
        page = self.denied_page()
        body = page.split('id="forbidden-title"', 1)[1]


        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', body).group(1)
        response = self.non_admin.post(reverse("logout"), {"csrfmiddlewaretoken": token})
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(self.non_admin.get(reverse("login")).status_code, 200)
