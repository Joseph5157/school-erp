"""Modern web audits 15 (NOTIF-01) and 18 (ERR-01, ERR-02, ERR-03): a warning before sign-out, a login
page that says why, a CSRF retry link that never lands on an action-only URL, and no cached copies of
signed-in pages after the session ends."""

import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from accounts.middleware import SEEN_KEY, SESSION_STATUS_PATH, STARTED_KEY
from core.tests.test_phase6_access_boundary import BoundaryFixture

STUDENTS = reverse("core:student-list")


class SessionFixture(BoundaryFixture):
    def age(self, key, seconds, client=None):
        client = client or self.client
        session = client.session
        session[key] = time.time() - seconds
        session.save()

    def query(self, response):
        return {k: v[0] for k, v in parse_qs(urlsplit(response["Location"]).query).items()}


class ExpiryRedirectTests(SessionFixture, TestCase):
    def test_idle_expiry_says_why_keeps_the_query_and_clears_the_cache(self):
        self.age(SEEN_KEY, 31 * 60)
        response = self.client.get(STUDENTS, {"q": "Asha"})
        self.assertTrue(response["Location"].startswith(reverse("login") + "?"))
        self.assertEqual(self.query(response), {"next": f"{STUDENTS}?q=Asha", "expired": "idle"})
        self.assertEqual(response["Clear-Site-Data"], '"cache"')

    def test_absolute_expiry_names_the_eight_hour_limit(self):
        self.age(STARTED_KEY, 8 * 60 * 60 + 60)
        self.assertEqual(self.query(self.client.get(STUDENTS))["expired"], "limit")

    def test_expired_post_says_it_was_not_saved_and_returns_to_the_form_page(self):
        self.age(SEEN_KEY, 31 * 60)
        response = self.client.post(reverse("logout"), HTTP_REFERER=f"http://testserver{STUDENTS}?page=2")
        query = self.query(response)
        self.assertEqual(query["unsaved"], "1")
        self.assertEqual(query["next"], f"{STUDENTS}?page=2")

    def test_a_foreign_referer_is_never_the_return_page(self):
        self.age(SEEN_KEY, 31 * 60)
        response = self.client.post(STUDENTS, HTTP_REFERER="https://evil.example/students/")
        self.assertEqual(self.query(response)["next"], STUDENTS)


class LoginExplanationTests(TestCase):
    def test_idle_note(self):
        page = self.client.get(reverse("login"), {"expired": "idle", "next": STUDENTS})
        self.assertContains(page, "You were signed out after 30 minutes without activity.")
        self.assertNotContains(page, "was not saved")
        self.assertContains(page, f'name="next" value="{STUDENTS}"')

    def test_limit_and_unsaved_note(self):
        page = self.client.get(reverse("login"), {"expired": "limit", "unsaved": "1"})
        self.assertContains(page, "signed in for 8 hours.")
        self.assertContains(page, "What you were saving was not saved.")

    def test_no_note_without_an_expiry_or_after_a_failed_login(self):
        self.assertNotContains(self.client.get(reverse("login")), 'id="login-expired"')
        failed = self.client.post(reverse("login") + "?expired=idle", {"username": "x", "password": "y"})
        self.assertNotContains(failed, 'id="login-expired"')

    def test_wording_matches_the_settings(self):
        self.assertEqual(settings.SESSION_IDLE_SECONDS, 30 * 60)
        self.assertEqual(settings.SESSION_ABSOLUTE_SECONDS, 8 * 60 * 60)


class SessionStatusTests(SessionFixture, TestCase):
    def test_path_constant_matches_the_url(self):
        self.assertEqual(reverse("session-status"), SESSION_STATUS_PATH)

    def test_asking_is_not_activity(self):
        self.age(SEEN_KEY, 20 * 60)
        data = self.client.get(SESSION_STATUS_PATH).json()
        self.assertAlmostEqual(data["idle"], 10 * 60, delta=5)
        self.assertLessEqual(data["absolute"], 8 * 60 * 60)
        self.assertAlmostEqual(self.client.get(SESSION_STATUS_PATH).json()["idle"], 10 * 60, delta=5)

    def test_stay_signed_in_restarts_the_idle_clock(self):
        self.age(SEEN_KEY, 29 * 60)
        data = self.client.post(SESSION_STATUS_PATH).json()
        self.assertAlmostEqual(data["idle"], 30 * 60, delta=5)

    def test_an_expired_session_is_signed_out_not_answered(self):
        self.age(SEEN_KEY, 31 * 60)
        response = self.client.get(SESSION_STATUS_PATH)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_answers_while_a_password_change_is_due(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        client = self.client_class()
        client.login(username="meena", password=self.password)
        response = client.get(SESSION_STATUS_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertIn("idle", response.json())

    def test_signed_out_gets_401_and_answers_are_not_cached(self):
        self.assertEqual(Client().get(SESSION_STATUS_PATH).status_code, 401)
        self.assertIn("no-store", self.client.get(SESSION_STATUS_PATH)["Cache-Control"])


class WarningMarkupTests(SessionFixture, TestCase):
    def test_signed_in_pages_carry_the_hidden_warning(self):
        page = self.client.get(STUDENTS).content.decode()
        self.assertIn('data-erp-session data-idle="1800"', page)
        self.assertIn(f'data-status-url="{SESSION_STATUS_PATH}"', page)
        self.assertIn('role="alert" data-erp-session-say', page)
        self.assertIn(">Stay signed in</button>", page)

    def test_guardian_shell_too_and_not_the_login_page(self):
        self.assertContains(self.guardian_client().get(reverse("portal:home")), "data-erp-session")
        self.assertNotContains(Client().get(reverse("login")), "data-erp-session")

    def test_script_rechecks_before_warning_and_extends_by_post(self):
        js = Path(settings.BASE_DIR, "static", "js", "erp.js").read_text(encoding="utf-8")
        self.assertIn('var box = document.querySelector("[data-erp-session]");', js)
        self.assertIn("if (secondsLeft(data) > WARN + 10) schedule(data); else warn(data);", js)
        self.assertIn('method: "POST", credentials: "same-origin",', js)
        # Only a redirect to the sign-in page counts as signed out (a due password change also redirects).
        self.assertIn("var toLogin = response.redirected && new URL(response.url).pathname === loginPath;", js)
        self.assertIn('expired: Date.now() >= absoluteAt - 5000 ? "limit" : "idle",', js)


class CacheTests(SessionFixture, TestCase):
    def test_signed_in_html_is_not_stored(self):
        cache = self.client.get(STUDENTS)["Cache-Control"]
        self.assertIn("no-store", cache)
        self.assertIn("private", cache)

    def test_a_view_that_sets_its_own_policy_keeps_it(self):
        self.assertEqual(self.client.get(reverse("session-status"))["Cache-Control"],
                         "max-age=0, no-cache, no-store, must-revalidate, private")

    def test_logout_clears_the_browser_cache(self):
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Clear-Site-Data"], '"cache"')


class CsrfRetryTests(SessionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.strict = Client(enforce_csrf_checks=True)
        self.strict.login(username="admin", password="pass-12345")

    def retry(self, response):
        return response.content.decode().split('<a class="btn btn-primary" href="', 1)[1].split('"', 1)[0]

    def test_post_only_action_retries_the_page_that_showed_the_form(self):
        queue = reverse("core:notifications-to-send")
        url = reverse("core:notification-dismiss", args=[1])
        response = self.strict.post(url, HTTP_REFERER=f"http://testserver{queue}?page=2")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.retry(response), f"{queue}?page=2")

    def test_foreign_referer_falls_back_to_the_posted_path(self):
        url = reverse("core:school-create")
        response = self.strict.post(url, HTTP_REFERER="https://evil.example/x")
        self.assertEqual(self.retry(response), url)

    def test_logout_still_goes_home(self):
        response = self.strict.post(reverse("logout"), HTTP_REFERER=f"http://testserver{reverse('logout')}")
        self.assertEqual(self.retry(response), reverse("home"))
