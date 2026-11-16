"""Small polish found while preparing school demos: filter labels and report-card marks."""

import re
import tempfile
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.forms import (
    AssessmentFilterForm,
    AttendanceRegisterFilterForm,
    MissingAttendanceForm,
)
from core.portal import portal_children, visible_publications


class FilterFormTests(TestCase):
    def _forms(self):
        return (AssessmentFilterForm(), AttendanceRegisterFilterForm(), MissingAttendanceForm())

    def test_section_filters_say_all_sections(self):
        for form in self._forms():
            with self.subTest(form=type(form).__name__):
                html = str(form["section"])
                self.assertIn(">All sections</option>", html)
                self.assertNotIn("---------", html)

    def test_term_filter_says_all_terms(self):
        self.assertIn(">All terms</option>", str(AssessmentFilterForm()["term"]))

    def test_filter_labels_have_no_trailing_colon(self):
        for form in self._forms():
            with self.subTest(form=type(form).__name__):
                self.assertIn(">Section</label>", form["section"].label_tag())


class MarksFormatTests(SimpleTestCase):
    def test_whole_marks_drop_zeros_and_half_marks_are_kept(self):
        template = Template('{{ s|floatformat:"-2" }} / {{ m|floatformat:"-2" }}')
        self.assertEqual(
            template.render(Context({"s": Decimal("85.00"), "m": Decimal("100.00")})), "85 / 100"
        )
        self.assertEqual(
            template.render(Context({"s": Decimal("15.50"), "m": Decimal("20.00")})), "15.50 / 20"
        )


class ReportCardMarksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        creds = Path(tempfile.mkdtemp()) / "creds.csv"
        call_command("seed_school_demo", credentials_file=str(creds), allow_non_debug=True,
                     verbosity=0)
        call_command("seed_school_demo_results", allow_non_debug=True, verbosity=0)

    def test_marks_show_without_trailing_zeros(self):
        guardian = get_user_model().objects.get(username="anil.varma")
        child = next(c for c in portal_children(guardian) if c["visible"])
        pub = next(iter(visible_publications(child["student"])))
        self.client.force_login(guardian)
        response = self.client.get(reverse(
            "portal:report-card", args=[child["grant"].public_id, pub.public_id]
        ))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertRegex(body, r"\d+ / \d+<")
        self.assertIsNone(re.search(r"\.00 / |/ \d+\.00", body))
