"""Phase 3G (audit F20): jump-to-section menus on the student and guardian pages."""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from core import guardian_accounts as ga
from core.models import (
    Applicant,
    Guardian,
    GuardianAccount,
    Student,
    StudentGuardian,
)
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()
NAV = '<nav class="erp-section-nav" aria-label="On this page"'
STUDENT_HEADINGS = [
    "Change status",
    "Status history",
    "Current placement",
    "Enrollment history",
    "Guardians",
]
GUARDIAN_HEADINGS = [
    "Associated Applicants",
    "Guardian Portal account",
    "Student access",
    "Account and access history",
]


def nav_hrefs(html):
    match = re.search(r"<nav class=\"erp-section-nav\".*?</nav>", html, re.S)
    if not match:
        return []
    return re.findall(r'href="#([^"]+)"', match.group(0))


class SectionAssertions:
    def assert_menu_matches_sections(self, html, expected_ids):
        hrefs = nav_hrefs(html)
        self.assertEqual(hrefs, expected_ids)
        for target in hrefs:
            self.assertIn(f'<section id="{target}"', html)
            self.assertEqual(html.count(f'id="{target}"'), 1)
            self.assertIn(f'id="{target}-heading"', html)
        # every rendered profile section is in the menu (no orphans)
        rendered = re.findall(r'<section id="([^"]+)" aria-labelledby', html)
        self.assertEqual(rendered, expected_ids)


class StudentPageTests(SectionAssertions, AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Asha Rao"), full_name="Asha Rao"
        )
        self.url = reverse("core:student-detail", args=[self.student.pk])

    def test_administrator_menu_and_sections(self):
        html = self.administrator.get(self.url).content.decode()

        self.assertIn(NAV, html)
        self.assert_menu_matches_sections(
            html,
            ["status-change", "status-history", "placement", "enrollment-history", "guardians"],
        )
        for heading in STUDENT_HEADINGS:
            self.assertRegex(html, rf'<h2 class="h5" id="[a-z-]+-heading">{heading}</h2>')

    def test_menu_sits_between_header_and_first_section(self):
        html = self.administrator.get(self.url).content.decode()

        self.assertLess(html.index("erp-page-header"), html.index(NAV))
        self.assertLess(html.index(NAV), html.index('<section id="status-change"'))

    def test_view_only_user_has_no_status_change_link_or_anchor(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_student"))
        self.client.login(username="viewer", password="pass-12345")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('href="#status-change"', html)
        self.assertNotIn('id="status-change"', html)
        self.assert_menu_matches_sections(
            html, ["status-history", "placement", "enrollment-history", "guardians"]
        )
        self.assertNotIn("Change status", html)

    def test_existing_texts_still_present(self):
        html = self.administrator.get(self.url).content.decode()

        for text in (
            "No status changes recorded.",
            "No active placement.",
            "No enrollments yet.",
            "No Guardians associated yet.",
            "Deactivate student",
        ):
            self.assertIn(text, html)


class GuardianPageTests(SectionAssertions, AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345")
        asha = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Asha Rao"), full_name="Asha Rao"
        )
        StudentGuardian.objects.create(
            student=asha, guardian=self.guardian, relationship_type="MOTHER"
        )
        self.url = reverse("core:guardian-detail", args=[self.guardian.pk])

    def test_administrator_without_account(self):
        html = self.administrator.get(self.url).content.decode()

        self.assertIn(NAV, html)
        self.assert_menu_matches_sections(
            html, ["applicants", "portal-account", "student-access", "history"]
        )
        self.assertIn("No active portal account.", html)
        for heading in GUARDIAN_HEADINGS:
            self.assertRegex(html, rf'<h2 class="h5 mt-4" id="[a-z-]+-heading">{heading}</h2>|'
                                   rf'<h2 class="h5" id="[a-z-]+-heading">{heading}</h2>')

    def test_administrator_with_account(self):
        ga.create_guardian_account(
            guardian=self.guardian,
            username="meena.rao",
            method=GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS,
            note="Aadhaar card seen by office",
            actor=self.admin_user,
        )

        html = self.administrator.get(self.url).content.decode()

        self.assert_menu_matches_sections(
            html, ["applicants", "portal-account", "student-access", "history"]
        )
        self.assertIn("meena.rao", html)

    def test_view_only_user_sees_only_rendered_sections(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_guardian"))
        self.client.login(username="viewer", password="pass-12345")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # one section only: no menu at all, and no dangling anchors
        self.assertNotIn(NAV, html)
        self.assertEqual(re.findall(r'href="#(?!main")[^"]+"', html), [])  # #main is the skip link
        self.assertIn("Associated Applicants", html)
        self.assertNotIn("Guardian Portal account", html)

    def test_partial_permissions_only_list_rendered_sections(self):
        user = User.objects.create_user(username="viewer2", password="pass-12345")
        user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_guardian", "view_guardianstudentaccess"]
            )
        )
        self.client.login(username="viewer2", password="pass-12345")

        html = self.client.get(self.url).content.decode()

        self.assert_menu_matches_sections(html, ["applicants", "student-access"])


class PartialAndCssTests(TestCase):
    @staticmethod
    def render(sections):
        return render_to_string("partials/_section_nav.html", {"sections": sections})

    def test_zero_and_one_section_render_nothing(self):
        self.assertNotIn("<nav", self.render([]))
        self.assertNotIn("<nav", self.render([{"id": "a", "label": "A"}]))

    def test_three_sections_render_links(self):
        html = self.render(
            [
                {"id": "a", "label": "Alpha"},
                {"id": "b", "label": "Beta"},
                {"id": "c", "label": "Gamma"},
            ]
        )

        self.assertIn(NAV, html)
        self.assertEqual(nav_hrefs(html), ["a", "b", "c"])
        self.assertIn(">Beta</a>", html)

    def test_css_has_menu_and_scroll_margin(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")

        self.assertIn(".erp-section-nav", css)
        self.assertRegex(css, r"\.erp-main section\[id\]\s*\{[^}]*scroll-margin-top")
        self.assertNotIn("--erp-border", css.split(".erp-section-nav", 1)[1][:1500])
        self.assertNotIn("--erp-muted", css.split(".erp-section-nav", 1)[1][:1500])
