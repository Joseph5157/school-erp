"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

from django.test import SimpleTestCase

from core.documents.engine import render_pdf

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
