from django.template.loader import render_to_string
from django.test import SimpleTestCase

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
