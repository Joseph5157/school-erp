"""UI-16: every office sidebar link carries a decorative inline-SVG icon beside its visible label."""

import re
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear, School, business_today
from core.navigation import OFFICE_NAV, TEACHER_TABS, office_nav

User = get_user_model()
PARTIAL = Path(__file__).resolve().parents[2] / "templates" / "partials" / "_icon.html"
TAB_PARTIAL = Path(__file__).resolve().parents[2] / "templates" / "partials" / "_tab_icon.html"
ICON = r'<svg class="erp-nav-icon"[^>]*aria-hidden="true"[^>]*>.*?</svg>\s*'


def known_icons():
    return set(re.findall(r'name == "([a-z]+)"', PARTIAL.read_text()))


class OfficeNavIconTests(TestCase):
    def setUp(self):
        School.objects.create(name="Sri Vidya School")
        today = business_today()
        AcademicYear.objects.create(
            name="2026-2027", start_date=today - timedelta(days=30), end_date=today + timedelta(days=300)
        )
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))

    def test_every_office_link_has_an_icon_the_partial_knows(self):
        known = known_icons()
        for _, links in OFFICE_NAV:
            for link in links:
                self.assertIn(link.icon, known, link.label)

    def test_icon_names_are_distinct_per_concept(self):
        names = [link.icon for _, links in OFFICE_NAV for link in links]
        self.assertEqual(len(names), len(set(names)))

    def test_every_partial_branch_is_used_or_documented(self):
        used = {link.icon for _, links in OFFICE_NAV for link in links}
        self.assertEqual(known_icons() - used, set())

    def test_teacher_tab_icons_stay_in_the_tab_partial(self):
        tab_names = set(re.findall(r'name == "([a-z]+)"', TAB_PARTIAL.read_text()))
        for tab in TEACHER_TABS:
            self.assertIn(tab.icon, tab_names)

    def test_rendered_sidebar_has_icon_before_every_label(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("core:school-detail")).content.decode()
        groups = office_nav(self.admin, "school-detail", year=AcademicYear.objects.get())
        links = [link for group in groups for link in group["links"]]
        self.assertGreaterEqual(len(links), 20)
        for link in links:
            pattern = (
                r'<a class="nav-link[^"]*" href="' + re.escape(link["url"]) + r'"[^>]*>\s*'
                + ICON + re.escape(link["label"])
            )
            self.assertRegex(html, pattern, link["label"])

    def test_unknown_icon_name_renders_nothing(self):
        from django.template.loader import render_to_string

        self.assertEqual(render_to_string("partials/_icon.html", {"name": "nope"}).strip(), "")
