"""A denied page must not leak another area's navigation into the 403 shell.

`current_area()` used to trust the requested URL: any `my-*` URL counted as "teacher"
before the signed-in user's own entitlement was considered, so a Guardian sent to a
Teacher page got the (correct) 403 wrapped in the Teacher tab bar.
"""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from core.navigation import current_area
from core.tests.test_phase6_access_boundary import BoundaryFixture

TEACHER_URLS = (
    ("core:my-home", ()),
    ("core:my-students", ()),
    ("core:my-assessments", ()),
    ("core:assessment-marks-entry", (1,)),  # not named my-*, still a Teacher page
)

TEACHER_SHELL = ('class="erp-tabbar', 'aria-label="Teaching"', "erp-teacher", "has-tabbar")


class AreaDecisionTests(BoundaryFixture, TestCase):
    def area(self, user, path):
        request = RequestFactory().get(path)
        request.user = user
        request.resolver_match = resolve(path)
        return current_area(request)

    def test_area_follows_the_user_not_the_requested_url(self):
        for name, args in TEACHER_URLS:
            with self.subTest(name=name):
                url = reverse(name, args=args)
                self.assertEqual(self.area(self.user, url), "guardian")  # a Guardian
                self.assertEqual(self.area(self.admin, url), "admin")  # not a Teacher
                self.assertEqual(self.area(self.rao, url), "teacher")  # a real Teacher

    def test_portal_urls_only_count_as_guardian_for_a_guardian(self):
        url = reverse("portal:home")
        self.assertEqual(self.area(self.user, url), "guardian")
        self.assertEqual(self.area(self.rao, url), "teacher")
        self.assertEqual(self.area(self.admin, url), "admin")

    def test_anonymous_has_no_area(self):
        self.assertIsNone(self.area(AnonymousUser(), reverse("core:my-home")))


class NeutralForbiddenShellTests(BoundaryFixture, TestCase):
    def forbidden(self, client, url):
        response = client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'id="forbidden-title"', status_code=403)
        return response

    def test_guardian_on_a_teacher_url_gets_403_without_teacher_navigation(self):
        portal = self.guardian_client()
        for name, args in TEACHER_URLS:
            with self.subTest(name=name):
                response = self.forbidden(portal, reverse(name, args=args))
                for leaked in TEACHER_SHELL:
                    self.assertNotContains(response, leaked, status_code=403)
                self.assertEqual(response.context["current_area"], "guardian")

    def test_403_keeps_the_account_menu_and_a_way_back_to_the_users_own_area(self):
        portal = self.guardian_client()
        response = self.forbidden(portal, reverse("core:my-home"))
        self.assertContains(response, 'class="erp-account"', status_code=403)
        self.assertContains(response, ">Go to my area</a>", status_code=403)
        self.assertContains(response, f'href="{reverse("home")}"', status_code=403)
        landing = portal.get(reverse("home"))
        self.assertRedirects(landing, reverse("portal:home"))

    def test_authorization_is_unchanged_for_the_denied_page(self):
        portal = self.guardian_client()
        for name, args in TEACHER_URLS:
            self.assertEqual(portal.get(reverse(name, args=args)).status_code, 403)

    def test_administrator_who_is_not_a_teacher_sees_their_own_shell_not_teacher_tabs(self):
        response = self.forbidden(self.client, reverse("core:my-home"))  # logged in as admin
        for leaked in TEACHER_SHELL:
            self.assertNotContains(response, leaked, status_code=403)
        self.assertContains(response, 'id="erp-sidebar"', status_code=403)

    def test_teacher_on_a_guardian_page_gets_403_in_their_own_teacher_shell(self):
        teacher = self.client_class()
        self.assertTrue(teacher.login(username="rao", password="pass-12345"))
        response = self.forbidden(teacher, reverse("portal:home"))
        self.assertEqual(response.context["current_area"], "teacher")

    def test_a_real_teacher_page_keeps_the_teacher_shell(self):
        teacher = self.client_class()
        self.assertTrue(teacher.login(username="rao", password="pass-12345"))
        page = teacher.get(reverse("core:my-home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'class="erp-tabbar')
        self.assertContains(page, 'aria-label="Teaching"')
