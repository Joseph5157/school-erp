"""Dependent selectors: a child choice carries its parent so erp.js can narrow it.

The server stays the authority. Every option is still rendered without JavaScript,
and a mismatched pair is still rejected.
"""

import re
from pathlib import Path

from django import forms
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.forms import ParentedSelect
from core.models import (
    AcademicSubjectOffering,
    AttendanceRegister,
    ClassGrade,
    Section,
    Subject,
)
from core.tests.phase4_fixtures import Phase4Fixture


class DependentSelectFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.grade7 = ClassGrade.objects.create(name="Grade 7")
        self.seven_a = Section.objects.create(class_grade=self.grade7, name="A")
        self.history = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade7,
            subject=Subject.objects.create(name="History"),
        )
        self.client.login(username="admin", password="pass-12345")
        self.urls = {
            "offer": reverse("core:offering-create", args=[self.year.pk]),
            "assign": reverse("core:teacher-assignment-create", args=[self.year.pk]),
            "register": reverse("core:attendance-register-create"),
            "students": reverse("core:student-list"),
        }
        self.make_student("Asha")

    def options(self, html, tag_id):
        """The (value, data-parent) pairs of the select with this id."""
        block = re.search(rf'<select[^>]*id="{tag_id}".*?</select>', html, re.S).group(0)
        pairs = []
        for match in re.finditer(r'<option value="([^"]*)"[^>]*>', block):
            parent = re.search(r'data-parent="(\d+)"', match.group(0))
            pairs.append((match.group(1), parent.group(1) if parent else None))
        return pairs


class OptionsCarryTheirParentTests(DependentSelectFixture, TestCase):
    def setUp(self):
        self.build()

    def test_offer_a_subject_sections_carry_their_grade(self):
        html = self.client.get(self.urls["offer"]).content.decode()
        self.assertIn('data-erp-depends-on="id_class_grade"', html)
        for section, grade in ((self.six_a, self.grade6), (self.seven_a, self.grade7)):
            inputs = re.findall(r"<input[^>]*>", html)
            tag = next(i for i in inputs if f'value="{section.pk}"' in i and "checkbox" in i)
            self.assertIn(f'data-parent="{grade.pk}"', tag)

    def test_assign_a_teacher_options_carry_their_parent(self):
        html = self.client.get(self.urls["assign"]).content.decode()
        self.assertIn('data-erp-depends-on="id_offering"', html)
        offerings = dict(self.options(html, "id_offering"))
        self.assertEqual(offerings[str(self.maths.pk)], str(self.grade6.pk))
        self.assertEqual(offerings[str(self.history.pk)], str(self.grade7.pk))
        sections = dict(self.options(html, "id_section"))
        self.assertEqual(sections[str(self.six_a.pk)], str(self.grade6.pk))
        self.assertEqual(sections[str(self.seven_a.pk)], str(self.grade7.pk))

    def test_open_a_register_sections_carry_their_grade(self):
        html = self.client.get(self.urls["register"]).content.decode()
        self.assertIn('data-erp-depends-on="id_class_grade"', html)
        sections = dict(self.options(html, "id_section"))
        self.assertEqual(sections[str(self.six_b.pk)], str(self.grade6.pk))
        self.assertEqual(sections[str(self.seven_a.pk)], str(self.grade7.pk))

    def test_student_filter_sections_carry_their_class(self):
        html = self.client.get(self.urls["students"]).content.decode()
        self.assertIn('data-erp-depends-on="student-class"', html)
        sections = dict(self.options(html, "student-section"))
        self.assertEqual(sections[str(self.six_a.pk)], str(self.grade6.pk))
        self.assertEqual(sections[str(self.seven_a.pk)], str(self.grade7.pk))

    def test_the_blank_choice_has_no_parent(self):
        html = self.client.get(self.urls["register"]).content.decode()
        self.assertIn(("", None), self.options(html, "id_section"))

    def test_widget_renders_the_parent_of_each_option(self):
        field = forms.ModelChoiceField(
            Section.objects.all(), widget=ParentedSelect(parent_attr="class_grade_id")
        )
        self.assertIn(f'data-parent="{self.grade7.pk}"', field.widget.render("s", None))


class AllOptionsRenderWithoutJsTests(DependentSelectFixture, TestCase):
    def setUp(self):
        self.build()

    def test_all_options_render_without_js(self):
        # Nothing is filtered on the server: every Section is in the HTML.
        sections = [self.six_a, self.six_b, self.seven_a]
        for key in ("assign", "register", "students"):
            html = self.client.get(self.urls[key]).content.decode()
            tag = "student-section" if key == "students" else "id_section"
            values = {v for v, _ in self.options(html, tag)}
            for section in sections:
                self.assertIn(str(section.pk), values, key)
            self.assertNotRegex(html, r"<option[^>]*\bhidden\b")
        html = self.client.get(self.urls["offer"]).content.decode()
        for section in sections:
            self.assertIn(f'value="{section.pk}"', html)
        assign = self.client.get(self.urls["assign"]).content.decode()
        offering_values = {v for v, _ in self.options(assign, "id_offering")}
        self.assertTrue({str(self.maths.pk), str(self.history.pk)} <= offering_values)


class ServerStillRejectsAMismatchedPairTests(DependentSelectFixture, TestCase):
    def setUp(self):
        self.build()

    def test_server_still_rejects_a_mismatched_pair(self):
        # Offer a Subject: a Grade 7 Section for a Grade 6 offering.
        science = Subject.objects.create(name="Science")
        response = self.client.post(self.urls["offer"], {
            "class_grade": self.grade6.pk, "subject": science.pk, "sections": [self.seven_a.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Every Section must belong to the selected Class/Grade.")
        self.assertFalse(AcademicSubjectOffering.objects.filter(subject=science).exists())

        # Assign a teacher: a Section of another Grade than the offering's.
        response = self.client.post(self.urls["assign"], {
            "teacher": self.rao.pk, "offering": self.maths.pk, "section": self.seven_a.pk,
            "start_date": "2026-07-01",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This Section does not take this Subject offering.")

        # Open a register: Grade 6 with a Grade 7 Section.
        response = self.client.post(self.urls["register"], {
            "academic_year": self.year.pk, "class_grade": self.grade6.pk,
            "section": self.seven_a.pk, "date": "2026-07-06",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Selected Section does not belong to the selected Class/Grade."
        )
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_student_filter_mismatch_is_not_a_server_error(self):
        # Class 6 with a Class 7 Section filters to nobody; it must not crash.
        response = self.client.get(
            self.urls["students"], {"class": self.grade6.pk, "section": self.seven_a.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Asha")

    def test_failed_form_keeps_the_choices(self):
        response = self.client.post(self.urls["register"], {
            "academic_year": self.year.pk, "class_grade": self.grade6.pk,
            "section": self.seven_a.pk, "date": "2026-07-06",
        })
        html = response.content.decode()
        self.assertRegex(html, rf'<option value="{self.seven_a.pk}"[^>]*selected')
        self.assertRegex(html, rf'<option value="{self.grade6.pk}"[^>]*selected')


class ScriptTests(TestCase):
    def test_script_has_one_block_keyed_off_the_attribute(self):
        path = Path(settings.BASE_DIR) / "static" / "js" / "erp.js"
        text = path.read_text(encoding="utf-8")
        self.assertIn("data-erp-depends-on", text)
        self.assertIn("data-parent", text)
