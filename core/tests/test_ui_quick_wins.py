"""UI quick wins found in the staging walkthrough: one date style, consistent
page headers, a branded 404, clearer teacher empty states, no duplicate login button."""

import datetime

from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from core.models import School
from core.tests.phase4_fixtures import Phase4Fixture


class HouseDateStyleTests(TestCase):
    def render(self, value):
        return Template("{{ value }}").render(Context({"value": value}))

    def test_bare_dates_use_day_month_year(self):
        self.assertEqual(self.render(datetime.date(2026, 10, 15)), "15 Oct 2026")

    def test_bare_datetimes_include_time(self):
        value = datetime.datetime(2026, 10, 15, 23, 11)
        self.assertEqual(self.render(value), "15 Oct 2026, 23:11")


class PageHeaderConsistencyTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")
        self.client.login(username="admin", password="pass-12345")

    def test_setup_pages_share_the_standard_page_header(self):
        for name in (
            "core:school-detail",
            "core:guardian-list",
            "core:document-index",
            "core:academic-year-list",
        ):
            with self.subTest(name=name):
                page = self.client.get(reverse(name))
                self.assertContains(page, 'class="erp-page-header"')
                self.assertContains(page, "erp-page-eyebrow")

    def test_academic_year_links_are_grouped_by_purpose(self):
        page = self.client.get(reverse("core:academic-year-list"))
        labels = ("Calendar:", "Teaching:", "Assessment:", "Class teachers", "Subject teachers")
        for label in labels:
            self.assertContains(page, label)


class ErrorAndLoginPageTests(TestCase):
    def test_login_page_has_a_single_login_control(self):
        page = self.client.get(reverse("login"))
        self.assertEqual(page.content.decode().count(">Log in</a>"), 0)
        self.assertContains(page, 'type="submit"')

    def test_other_public_pages_keep_the_header_login_link(self):
        page = self.client.get("/definitely-not-a-page/")
        self.assertContains(page, ">Log in</a>", status_code=404)

    def test_unknown_url_renders_branded_404(self):
        page = self.client.get("/definitely-not-a-page/")
        self.assertEqual(page.status_code, 404)
        self.assertContains(page, "We can't find that page", status_code=404)
        self.assertContains(page, "erp.css", status_code=404)


class TeacherEmptyStateTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")
        self.client.login(username="rao", password="pass-12345")

    def test_unassigned_teacher_is_told_who_assigns(self):
        for name, expected in (
            ("core:my-home", "ask the office to check your assignment"),
            ("core:my-students", "Ask the school office"),
            ("core:my-results", "The school office assigns Subjects"),
        ):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(name)), expected)
