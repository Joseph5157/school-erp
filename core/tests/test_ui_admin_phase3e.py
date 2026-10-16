from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Applicant
from core.tables import Column, build_table
from core.tests.test_authorization import AuthorizationClientsMixin

YEAR = {"pk": 1, "name": "2026-27"}
STUDENT = {"pk": 1, "full_name": "Asha Rao"}

# template -> (extra context, expected submit label)
SAVE_FORMS = {
    "applicant_guardian_form": ({"applicant": STUDENT}, "Save guardian link"),
    "assessment_form": ({"academic_year": YEAR}, "Save assessment"),
    "calendar_day_form": ({"academic_year": YEAR}, "Save calendar exception"),
    "class_grade_form": ({}, "Save class/grade"),
    "grading_scale_form": ({"academic_year": YEAR}, "Save grading scale"),
    "guardian_form": ({}, "Save guardian"),
    "offering_form": ({"academic_year": YEAR}, "Save subject offering"),
    "school_form": ({}, "Save school details"),
    "section_form": ({"class_grade": {"name": "Grade 6"}}, "Save section"),
    "subject_form": ({"creating": True}, "Save subject"),
    "term_form": ({"academic_year": YEAR}, "Save term"),
}


class VerbObjectSubmitLabelTests(SimpleTestCase):
    def assert_label(self, html, label):
        self.assertIn(f">{label}</button>", html)
        self.assertNotIn(">Save</button>", html)

    def test_forms_name_the_object_they_save(self):
        for name, (context, label) in SAVE_FORMS.items():
            with self.subTest(template=name):
                html = render_to_string(f"core/{name}.html", context)
                self.assert_label(html, label)

    def test_identifier_form_names_admission_or_roll_number(self):
        from core.forms import AdmissionNumberForm, RollNumberForm

        for form, label in (
            (AdmissionNumberForm(), "Save admission number"),
            (RollNumberForm(), "Save roll number"),
        ):
            with self.subTest(label=label):
                html = render_to_string(
                    "core/identifier_form.html",
                    {"form": form, "student": STUDENT, "title": "x"},
                )
                self.assert_label(html, label)

    def test_existing_audit_examples_are_already_specific(self):
        for name, label in (
            ("attendance_register_form", "Open register"),
            ("academic_year_form", "Create academic year"),
            ("enrollment_form", "Record enrollment"),
        ):
            with self.subTest(template=name):
                path = f"core/templates/core/{name}.html"
                with open(path, encoding="utf-8") as handle:
                    self.assertIn(f">{label}</button>", handle.read())


class SecondaryButtonStyleTests(SimpleTestCase):
    def css(self):
        return (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(
            encoding="utf-8"
        )

    def rule(self, selector_start):
        css = self.css()
        start = css.index(selector_start)
        return css[start : css.index("}", start)]

    def test_enabled_secondary_button_uses_active_ink_colours(self):
        rule = self.rule(".btn-outline-secondary {")
        self.assertIn("var(--erp-ink)", rule)
        self.assertIn("var(--erp-ink-soft)", rule)

    def test_disabled_buttons_have_a_distinct_not_allowed_look(self):
        rule = self.rule(".btn:disabled,")
        self.assertIn("not-allowed", rule)
        self.assertIn("opacity", rule)
        self.assertIn("var(--erp-rule)", rule)
        self.assertIn('[aria-disabled="true"]', rule)


class SortParamTests(TestCase):
    columns = (Column("Name", "name", ("full_name",)), Column("Notes"))

    def sort_param(self, query):
        request = RequestFactory().get("/applicants/" + query)
        return build_table(
            request, Applicant.objects.all(), self.columns, "name"
        ).sort_param

    def test_empty_without_sort(self):
        self.assertEqual(self.sort_param(""), "")

    def test_set_with_valid_sort(self):
        self.assertEqual(self.sort_param("?sort=-name"), "-name")
        self.assertEqual(self.sort_param("?sort=name"), "name")

    def test_empty_with_bogus_or_unsortable_sort(self):
        self.assertEqual(self.sort_param("?sort=bogus"), "")
        self.assertEqual(self.sort_param("?sort=-notes"), "")


class SortSurvivesFilteringTests(AuthorizationClientsMixin, TestCase):
    pages = (
        ("core:student-list", "-name", "Clear search"),
        ("core:applicant-list", "-name", "Clear filters"),
        ("core:teacher-list", "-name", "Clear filters"),
        ("core:attendance-register-list", "-date", None),
    )
    hidden = '<input type="hidden" name="sort"'

    def test_hidden_sort_input_only_with_a_valid_sort(self):
        for name, token, _clear in self.pages:
            url = reverse(name)
            with self.subTest(page=name):
                kept = self.administrator.get(url, {"sort": token})
                self.assertContains(kept, f'{self.hidden} value="{token}">')
                for query in ({}, {"sort": "bogus"}):
                    dropped = self.administrator.get(url, query)
                    self.assertNotContains(dropped, self.hidden)

    def test_clear_links_do_not_carry_the_sort(self):
        cases = (
            ("core:student-list", {"q": "x", "sort": "-name"}, "Clear search"),
            ("core:applicant-list", {"status": "applied", "sort": "-name"}, "Clear filters"),
            ("core:teacher-list", {"q": "x", "sort": "-name"}, "Clear filters"),
        )
        for name, query, label in cases:
            with self.subTest(page=name):
                response = self.administrator.get(reverse(name), query)
                self.assertContains(
                    response, f'href="{reverse(name)}">{label}</a>', html=False
                )


User = get_user_model()

# (list url name, existing empty text, create url name, label, view codename or None)
EMPTY_ACTIONS = (
    ("core:announcement-list", "No notices yet.", "core:announcement-create",
     "Publish a notice", "view_announcement"),
    ("core:guardian-list", "No Guardians yet.", "core:guardian-create",
     "Add guardian", "view_guardian"),
    ("core:import-list", "No imports yet.", "core:import-upload",
     "Start an import", "view_importbatch"),
    ("core:academic-year-list", "No Academic Years yet.", "core:academic-year-create",
     "Create academic year", "view_academicyear"),
    ("core:subject-list", "No Subjects yet.", "core:subject-create",
     "Add subject", "view_subject"),
    ("core:class-grade-list", "No Classes/Grades yet.", "core:class-grade-create",
     "Add class/grade", "view_classgrade"),
    ("core:teacher-list", "No teachers yet.", "core:teacher-create",
     "Add teacher", None),
    ("core:applicant-list", "No Applicants yet.", "core:applicant-create",
     "Register applicant", "view_applicant"),
    ("core:student-list", "No Students found.", "core:applicant-list",
     "Review applicants", "view_student"),
    ("core:attendance-register-list", "No attendance registers yet.",
     "core:attendance-register-create", "Open register", "view_attendanceregister"),
)


def action_html(url_name, label):
    return (
        '<br><a class="btn btn-outline-primary btn-sm mt-2" '
        f'href="{reverse(url_name)}">{label}</a>'
    )


class EmptyStateActionTests(AuthorizationClientsMixin, TestCase):
    def test_admin_sees_the_next_action_beside_the_existing_text(self):
        for list_name, text, create_name, label, _view in EMPTY_ACTIONS:
            with self.subTest(page=list_name):
                response = self.administrator.get(reverse(list_name))
                self.assertContains(response, text)
                self.assertContains(response, action_html(create_name, label))

    def test_view_only_user_gets_the_page_without_the_action(self):
        for list_name, text, create_name, label, view in EMPTY_ACTIONS:
            if view is None:
                continue  # teacher list needs the same permission as its action
            with self.subTest(page=list_name):
                user = User.objects.create_user(username=f"v-{view}", password="pass-12345")
                user.user_permissions.add(Permission.objects.get(codename=view))
                client = self.client_class()
                client.login(username=f"v-{view}", password="pass-12345")
                response = client.get(reverse(list_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
                self.assertNotContains(response, action_html(create_name, label))

    def test_informational_lists_stay_plain(self):
        for name, text in (
            ("core:guardian-access-reviews", "No pending access reviews."),
            ("core:login-lockouts", "No usernames are locked."),
            ("core:publications-stale", "None."),
        ):
            with self.subTest(page=name):
                response = self.administrator.get(reverse(name))
                self.assertContains(response, text)
                self.assertNotContains(response, "btn-outline-primary btn-sm mt-2")
