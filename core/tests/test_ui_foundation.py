"""U1 UI foundation: static files, shell, navigation, auth pages, components."""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.models import School
from core.tests.phase4_fixtures import Phase4Fixture

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


class StaticFilesTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def test_tests_use_plain_static_storage(self):
        self.assertEqual(
            settings.STORAGES["staticfiles"]["BACKEND"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )

    def test_admin_login_renders(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_base_links_stylesheet_and_viewport(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertContains(page, VIEWPORT)
        self.assertContains(page, "/static/css/erp.css")
        self.assertContains(page, "/static/js/erp.js")
