"""Audit 17 (print/export) PRT-03/04/05: issued PDFs survive page breaks.

Stress fixtures push each document past one page, then the laid-out pages are
inspected: rows stay whole, the overall total prints once, every page names the
document and its serial with "Page X of Y", and the PDF carries tags.
"""

import re
import zlib

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core.documents.engine import render_document, render_pdf

LETTERHEAD = {"school_name": "Test School", "address": "", "affiliation_number": "",
              "principal_name": "A. Principal"}
FILLER = "long assessment name " * 3


def _report_card(rows=60):
    return {
        "serial": "RC/2026-27/0001",
        "payload": {
            "letterhead": LETTERHEAD, "student_name": "Asha Rao", "admission_number": "A-1",
            "term_label": "Term 1", "academic_year_label": "2026-27",
            "class_label": "7", "section_label": "B", "is_partial": False,
            "remark_text": "Steady progress. " * 60, "issued_on": "2026-11-18",
            "entries": [
                {"subject": f"Subject {i}", "assessment": f"ROW{i:02d}START {FILLER} ROW{i:02d}END",
                 "date": "2026-07-01", "status": "MARKED", "score": "40",
                 "maximum_marks": "50", "percentage": "80", "grade": "A", "pass_fail": "Pass"}
                for i in range(rows)
            ],
        },
    }


def _attendance(rows=80):
    return {
        "serial": "AS/2026-27/0001",
        "payload": {
            "letterhead": LETTERHEAD, "class_label": "7", "section_label": "B",
            "start": "2026-06-01", "end": "2026-10-31", "issued_on": "2026-11-18",
            "rows": [
                {"student_name": f"ROW{i:02d}START {'Student name ' * 6} ROW{i:02d}END",
                 "present": 90, "absent": 10, "total": 100, "percentage": "90.0"}
                for i in range(rows)
            ],
            "totals": {"present": 7200, "absent": 800, "total": 8000, "percentage": "90.0"},
        },
    }


def _box_text(box, out):
    text = getattr(box, "text", None)
    if text:
        out.append(text)
    for child in getattr(box, "children", None) or []:
        _box_text(child, out)
    return out


def _page_texts(template, context):
    doc = render_document(template, context)
    return [" ".join(_box_text(page._page_box, [])) for page in doc.pages]


def _pdf_objects(pdf):
    """Raw PDF bytes plus every Flate stream decompressed (catalogs sit in object streams)."""
    chunks = [pdf]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            pass
    return b"\n".join(chunks)


class RowsStayWholeTests(SimpleTestCase):
    def _assert_no_split_rows(self, pages, rows):
        self.assertGreater(len(pages), 1, "fixture must span several pages")
        for i in range(rows):
            start = [n for n, t in enumerate(pages) if f"ROW{i:02d}START" in t]
            end = [n for n, t in enumerate(pages) if f"ROW{i:02d}END" in t]
            self.assertEqual(start, end, f"row {i} is split across pages {start} / {end}")

    def test_report_card_rows_never_split(self):
        self._assert_no_split_rows(_page_texts("documents/report_card.html", _report_card()), 60)

    def test_attendance_rows_never_split(self):
        self._assert_no_split_rows(_page_texts("documents/attendance_summary.html", _attendance()), 80)

    def test_section_total_prints_once_on_the_last_page(self):
        pages = _page_texts("documents/attendance_summary.html", _attendance())
        self.assertEqual(sum(t.count("Section total") for t in pages), 1)
        self.assertIn("Section total", pages[-1])

    def test_column_headings_still_repeat(self):
        pages = _page_texts("documents/report_card.html", _report_card())
        for n, text in enumerate(pages[:-1]):
            self.assertIn("Grade", text, f"page {n + 1} lost its column headings")

    def test_signature_stays_with_the_closing_note(self):
        pages = _page_texts("documents/report_card.html", _report_card())
        closing = [n for n, t in enumerate(pages) if "no totals, weighting or ranks" in t]
        signed = [n for n, t in enumerate(pages) if "A. Principal" in t]
        self.assertEqual(closing, signed)


class EveryPageIsIdentifiedTests(SimpleTestCase):
    def _assert_identified(self, pages, *needles):
        total = len(pages)
        for n, text in enumerate(pages, start=1):
            self.assertIn(f"Page {n} of {total}", text)
            for needle in needles:
                self.assertIn(needle, text, f"page {n} is missing {needle!r}")

    def test_report_card_pages(self):
        pages = _page_texts("documents/report_card.html", _report_card())
        self._assert_identified(pages, "Asha Rao", "RC/2026-27/0001", "Term 1 report card")

    def test_attendance_pages(self):
        pages = _page_texts("documents/attendance_summary.html", _attendance())
        self._assert_identified(pages, "Class 7, Section B", "AS/2026-27/0001", "Attendance summary")

    def test_bonafide_is_page_1_of_1_with_serial(self):
        context = {"serial": "BC/2026-27/0001", "payload": {
            "letterhead": LETTERHEAD, "student_name": "Asha Rao", "class_label": "7",
            "section_label": "B", "academic_year_label": "2026-27", "purpose": "Bank account",
            "issued_on": "2026-11-18"}}
        pages = _page_texts("documents/bonafide.html", context)
        self.assertEqual(len(pages), 1)
        self._assert_identified(pages, "BC/2026-27/0001", "Asha Rao")

    def test_letterhead_is_on_the_first_page_only(self):
        pages = _page_texts("documents/report_card.html", _report_card())
        self.assertIn("Test School", pages[0])
        for text in pages[1:]:
            self.assertNotIn("Test School", text)


class TaggedPdfTests(SimpleTestCase):
    def test_pdf_has_structure_tree_language_and_title(self):
        objects = _pdf_objects(render_pdf("documents/report_card.html", _report_card(rows=3)))
        self.assertIn(b"/StructTreeRoot", objects)
        self.assertIn(b"/MarkInfo", objects)
        self.assertIn(b"/Lang", objects)
        self.assertIn(b"/Title", objects)

    def test_tables_have_captions_and_scoped_headers(self):
        card = render_to_string("documents/report_card.html", _report_card(rows=2))
        self.assertIn("<caption>Assessment results</caption>", card)
        self.assertIn('<th scope="col">Subject</th>', card)
        self.assertIn('<th scope="row">Subject 0</th>', card)
        summary = render_to_string("documents/attendance_summary.html", _attendance(rows=2))
        self.assertIn("<caption>Attendance by student</caption>", summary)
        self.assertIn('<th scope="row">Section total</th>', summary)
        self.assertNotIn("<td>Section total", summary)
