from django.test import TestCase
from django.urls import reverse

from core.authorization import user_areas
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin


class OverviewLandingTests(AuthorizationClientsMixin, TestCase):
    def test_admin_home_redirects_to_overview(self):
        response = self.administrator.get(reverse("home"))
        self.assertRedirects(
            response, reverse("core:admin-overview"), fetch_redirect_response=False
        )

    def test_overview_renders_for_admin_with_sidebar_link(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:admin-overview"))
        self.assertContains(response, "Overview")

    def test_overview_refuses_non_admin_and_anonymous(self):
        url = reverse("core:admin-overview")
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(url), f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )

    def test_admin_area_lands_on_overview(self):
        areas = {key: url for key, _, url in user_areas(self.admin_user)}
        self.assertEqual(areas["admin"], "core:admin-overview")


class OverviewMultiRoleTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_admin_who_is_also_teacher_still_chooses_area(self):
        self.rao.groups.add(self.admins)
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        self.assertRedirects(
            client.get(reverse("home")), reverse("choose-area"),
            fetch_redirect_response=False,
        )
