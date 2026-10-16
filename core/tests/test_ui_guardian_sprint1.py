"""Guardian UI Sprint 1 tests (findings G-01, G-02, G-04, G-05, G-07, G-10)."""

import uuid
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from core.tests.test_phase6_access_boundary import BoundaryFixture

GRANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PUB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class ReportCardGradeFallbackTests(TestCase):
    def render(self, grade_label, pass_fail_label="Pass"):
        entry = SimpleNamespace(
            subject_label="Science",
            assessment_label="Unit Test 1",
            assessment_date=None,
            status="MARKED",
            score=29,
            maximum_marks=50,
            percentage=58,
            grade_label=grade_label,
            pass_fail_label=pass_fail_label,
        )
        pub = SimpleNamespace(
            term_label="Term 1",
            academic_year_label="2026-27",
            class_grade_label="Grade 6",
            section_label="A",
            public_id=PUB_ID,
            is_partial=False,
            remark_text="",
        )
        student = SimpleNamespace(full_name="Anusha Rao")
        grant = SimpleNamespace(public_id=GRANT_ID)
        return render_to_string(
            "portal/report_card.html",
            {
                "entries": [entry],
                "pub": pub,
                "student": student,
                "grant": grant,
                "children": [],
                "user": SimpleNamespace(get_username=lambda: "g"),
            },
        )

    def test_blank_grade_shows_not_graded(self):
        html = self.render("")
        self.assertIn("Not graded", html)
        self.assertIn("Pass", html)

    def test_real_grade_is_shown_not_placeholder(self):
        html = self.render("B1")
        self.assertIn(">B1<", html)
        self.assertNotIn("Not graded", html)


class ForbiddenPageTests(BoundaryFixture, TestCase):
    # BoundaryFixture.setUp already logs self.client in as the administrator.

    def test_non_guardian_gets_403_with_branded_body(self):
        response = self.client.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'id="forbidden-title"', status_code=403)
        self.assertContains(response, reverse("login"), status_code=403)

    def test_anonymous_still_redirects_not_403(self):
        anonymous = self.client_class()
        response = anonymous.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
