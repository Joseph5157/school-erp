from django.conf import settings
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from core.models import Applicant
from core.tests.test_authorization import AuthorizationClientsMixin


class Phase1DesignTokenTests(TestCase):
    def test_stylesheet_defines_shared_spacing_type_and_focus_tokens(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(
            encoding="utf-8"
        )

        for token in (
            "--erp-space-1",
            "--erp-space-7",
            "--erp-text-title",
            "--erp-line-body",
            "--erp-focus-color",
            "--erp-focus-ring",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)
        self.assertIn("@media (max-width: 767.98px)", css)
        self.assertIn("min-height: 2.75rem", css)
        self.assertIn("contain: inline-size paint", css)


class Phase1ComponentTests(TestCase):
    def test_page_header_has_title_purpose_status_and_actions(self):
        html = render_to_string(
            "partials/_page_header.html",
            {
                "eyebrow": "People",
                "title": "Students",
                "purpose": "Find and manage student records.",
                "status_label": "Active",
                "status_tone": "active",
                "primary_url": "/students/create/",
                "primary_label": "Add student",
            },
        )

        self.assertIn('class="erp-page-header"', html)
        self.assertIn('<h1 class="erp-page-title">Students</h1>', html)
        self.assertIn("Find and manage student records.", html)
        self.assertIn("erp-status--active", html)
        self.assertIn('href="/students/create/"', html)

    def test_status_badge_exposes_text_not_color_alone(self):
        html = render_to_string(
            "partials/_status_badge.html", {"label": "Submitted", "tone": "submitted"}
        )

        self.assertIn("erp-status--submitted", html)
        self.assertIn("Status:", html)
        self.assertIn("Submitted", html)


class Phase1AdminPageTests(AuthorizationClientsMixin, TestCase):
    def test_people_lists_use_page_headers_and_status_badges(self):
        applicant = Applicant.objects.create(full_name="Asha Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        applicant.progress_to_student()

        for name, tone in (
            ("core:applicant-list", "accepted"),
            ("core:student-list", "active"),
        ):
            with self.subTest(name=name, tone=tone):
                response = self.administrator.get(reverse(name))
                self.assertContains(response, 'class="erp-page-header"')
                self.assertContains(response, f'class="erp-status erp-status--{tone}"')

    def test_applicant_form_has_required_legend_fields_and_outcome_action(self):
        response = self.administrator.get(reverse("core:applicant-create"))

        self.assertContains(response, "Fields marked with an asterisk are required.")
        self.assertContains(response, 'class="erp-field', count=4)
        self.assertContains(response, ">Register applicant</button>")
        self.assertContains(response, ">Cancel</a>")

    def test_invalid_applicant_form_has_associated_field_error(self):
        response = self.administrator.post(
            reverse("core:applicant-create"),
            {"full_name": "", "date_of_birth": "", "email": "", "phone": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="erp-field is-invalid"')
        self.assertContains(response, 'id="id_full_name_error"')
        self.assertContains(response, 'aria-invalid="true"')

    def test_attendance_open_form_uses_named_action_and_cancel(self):
        response = self.administrator.get(reverse("core:attendance-register-create"))

        self.assertContains(response, 'class="erp-page-header"')
        self.assertContains(response, ">Open register</button>")
        self.assertContains(
            response,
            f'href="{reverse("core:attendance-register-list")}"',
        )

    def test_attendance_list_contains_its_wide_table_in_a_named_scroll_region(self):
        response = self.administrator.get(reverse("core:attendance-register-list"))

        self.assertContains(response, 'class="erp-table-scroll"')
        self.assertContains(response, 'aria-label="Attendance registers"')
