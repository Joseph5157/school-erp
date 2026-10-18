"""U3.1 Teacher Mobile Polish: shell and bottom navigation (Gate T1)."""

import re

from django.test import TestCase
from django.urls import reverse

from core.models import School
from core.navigation import teacher_tabs
from core.tests.phase4_fixtures import Phase4Fixture

TABBAR = re.compile(r'<nav class="erp-tabbar.*?</nav>', re.DOTALL)
BODY_TAG = re.compile(r"<body class=\"([^\"]*)\"")


def tabbar_html(page):
    return TABBAR.search(page.content.decode()).group(0)


def body_classes(page):
    return BODY_TAG.search(page.content.decode()).group(1).split()


class TeacherBottomNavTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")
        self.client.login(username="rao", password="pass-12345")

    def test_data_keeps_desktop_labels_and_adds_mobile_labels(self):
        tabs = teacher_tabs("my-home")
        self.assertEqual([t["label"] for t in tabs],
                         ["My day", "My students", "My assessments", "Results"])
        self.assertEqual([t["mobile_label"] for t in tabs],
                         ["Today", "Students", "Assessments", "Results"])
        self.assertEqual([t["url"] for t in tabs], [
            reverse("core:my-home"), reverse("core:my-students"),
            reverse("core:my-assessments"), reverse("core:my-results"),
        ])

    def test_bottom_bar_labels_and_order(self):
        bar = tabbar_html(self.client.get(reverse("core:my-home")))
        labels = re.findall(r'<span class="erp-tab-label">([^<]+)</span>', bar)
        self.assertEqual(labels, ["Today", "Students", "Assessments", "Results"])
        hrefs = re.findall(r'<a href="([^"]+)"', bar)
        self.assertEqual(hrefs, [
            reverse("core:my-home"), reverse("core:my-students"),
            reverse("core:my-assessments"), reverse("core:my-results"),
        ])

    def test_every_item_has_a_decorative_icon_and_a_text_label(self):
        bar = tabbar_html(self.client.get(reverse("core:my-home")))
        items = re.findall(r"<li>(.*?)</li>", bar, re.DOTALL)
        self.assertEqual(len(items), 4)
        for item in items:
            self.assertIn('class="erp-tab-icon"', item)
            self.assertIn('aria-hidden="true"', item)
            label = re.search(r'<span class="erp-tab-label">([^<]*)</span>', item)
            self.assertTrue(label and label.group(1).strip())

    def test_active_item_is_marked_on_each_destination(self):
        cases = (
            ("core:my-home", "Today"),
            ("core:my-students", "Students"),
            ("core:my-assessments", "Assessments"),
            ("core:my-results", "Results"),
        )
        for url_name, label in cases:
            with self.subTest(url_name):
                bar = tabbar_html(self.client.get(reverse(url_name)))
                self.assertEqual(bar.count('aria-current="page"'), 1)
                active = re.search(
                    r'<a href="[^"]+" class="active" aria-current="page">.*?'
                    r'<span class="erp-tab-label">([^<]+)</span>', bar, re.DOTALL)
                self.assertEqual(active.group(1), label)

    def test_desktop_top_bar_and_page_headings_keep_long_labels(self):
        page = self.client.get(reverse("core:my-students"))
        html = page.content.decode()
        top = re.search(r'<nav class="erp-topbar-links.*?</nav>', html, re.DOTALL).group(0)
        for label in ("My day", "My students", "My assessments", "Results"):
            self.assertIn(f">{label}</a>", top)
        self.assertContains(page, "My students")

    def test_bar_is_still_phone_only(self):
        self.assertIn("d-lg-none", tabbar_html(self.client.get(reverse("core:my-home"))))


class TeacherAreaHookTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def test_teacher_pages_carry_the_hook(self):
        self.client.login(username="rao", password="pass-12345")
        for url_name in ("core:my-home", "core:my-students",
                         "core:my-assessments", "core:my-results"):
            with self.subTest(url_name):
                classes = body_classes(self.client.get(reverse(url_name)))
                self.assertIn("erp-teacher", classes)
                self.assertIn("has-tabbar", classes)

    def test_office_pages_do_not_carry_the_hook(self):
        self.client.login(username="admin", password="pass-12345")
        classes = body_classes(self.client.get(reverse("core:student-list")))
        self.assertNotIn("erp-teacher", classes)

    def test_admin_who_teaches_has_hook_only_in_teaching_area(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        self.assertNotIn("erp-teacher",
                         body_classes(self.client.get(reverse("core:school-detail"))))
        self.assertIn("erp-teacher",
                      body_classes(self.client.get(reverse("core:my-home"))))

    def test_login_page_does_not_carry_the_hook(self):
        self.assertNotIn("erp-teacher", body_classes(self.client.get(reverse("login"))))
