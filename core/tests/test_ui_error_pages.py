"""Friendly error pages: an expired form (CSRF failure) and a server error (500)."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path, reverse

User = get_user_model()


def _boom(request):
    raise RuntimeError("deliberate failure for the 500 page test")


urlpatterns = [path("boom/", _boom)]


class ExpiredFormPageTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_setting_points_at_the_friendly_view(self):
        self.assertEqual(settings.CSRF_FAILURE_VIEW, "accounts.views.csrf_failure")

    def test_login_without_a_valid_token_explains_and_offers_a_fresh_form(self):
        response = self.client.post(reverse("login"), {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403_csrf.html")
        self.assertContains(response, "This page has expired", status_code=403)
        self.assertContains(response, "Nothing was saved.", status_code=403)
        self.assertContains(response, f'href="{reverse("login")}">Open the page again</a>', status_code=403)
        self.assertNotContains(response, "CSRF verification failed", status_code=403)

    def test_logout_retry_goes_home_not_to_the_post_only_logout(self):
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, f'href="{reverse("home")}">Open the page again</a>', status_code=403)

    def test_signed_in_user_keeps_their_shell(self):
        user = User.objects.create_user(username="office1", password="pass-12345")
        user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(user)
        response = self.client.post(reverse("core:school-create"), {})
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'id="erp-sidebar"', status_code=403)
        self.assertContains(response, f'href="{reverse("core:school-create")}">Open the page again</a>', status_code=403)


class ServerErrorPageTests(SimpleTestCase):
    def test_template_renders_with_no_context_or_database(self):
        html = render_to_string("500.html")
        self.assertIn("Something went wrong on our side", html)
        self.assertIn('<a class="btn btn-primary" href="/">Go to my area</a>', html)
        self.assertNotIn("{%", html)

    @override_settings(ROOT_URLCONF="core.tests.test_ui_error_pages")
    def test_unhandled_exception_shows_the_friendly_page(self):
        client = Client(raise_request_exception=False)
        with self.assertLogs("django.request", level="ERROR"):
            response = client.get("/boom/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Something went wrong on our side", response.content.decode())
