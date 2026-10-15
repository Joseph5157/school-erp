"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

from django.test import SimpleTestCase, TestCase

from core.documents.engine import render_pdf
from core.forms import SchoolForm

TELUGU = "క్ష స్త్ర శ్రీ విద్యార్థి"  # conjuncts: ksha, stra, shri, vidyarthi


class EngineTests(SimpleTestCase):
    def test_renders_pdf_with_both_scripts_and_embedded_fonts(self):
        pdf = render_pdf("documents/_engine_check.html",
                         {"latin": "Bonafide certificate 2026-27", "telugu": TELUGU})
        self.assertTrue(pdf.startswith(b"%PDF"))
        # Font names sit inside compressed object streams; each embedded TrueType
        # program (one Latin, one Telugu subset) is its own /Length1 stream.
        self.assertGreaterEqual(pdf.count(b"/Length1"), 2)
        self.assertGreater(len(pdf), 5_000)


class SchoolLetterheadTests(TestCase):
    def test_form_saves_letterhead_fields_and_they_are_optional(self):
        form = SchoolForm({"name": "Sri Vidya School", "notification_channel": "PORTAL_ONLY"})
        self.assertTrue(form.is_valid(), form.errors)
        school = form.save()
        self.assertEqual((school.address, school.affiliation_number, school.principal_name),
                         ("", "", ""))
        form = SchoolForm({"name": "Sri Vidya School", "notification_channel": "PORTAL_ONLY",
                           "address": "1 Main Road, Guntur", "affiliation_number": "AP/123",
                           "principal_name": "K. Lakshmi"}, instance=school)
        self.assertTrue(form.is_valid(), form.errors)
        school = form.save()
        self.assertEqual(school.principal_name, "K. Lakshmi")
