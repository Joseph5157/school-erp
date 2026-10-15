"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

import threading
from datetime import date
from unittest import skipUnless

from django.db import DatabaseError, connection, connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from core.documents import serials
from core.documents.engine import render_pdf
from core.forms import SchoolForm
from core.models import AcademicYear, IssuedDocument

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


def make_year():
    return AcademicYear.objects.create(
        name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31))


class SerialTests(TestCase):
    def setUp(self):
        self.year = make_year()

    def test_serials_count_per_type_and_year(self):
        with transaction.atomic():
            self.assertEqual(serials.next_serial("BONAFIDE", self.year), "BON/2026-27/0001")
            self.assertEqual(serials.next_serial("BONAFIDE", self.year), "BON/2026-27/0002")
            self.assertEqual(serials.next_serial("REPORT_CARD", self.year), "RC/2026-27/0001")
            self.assertEqual(serials.next_serial("ATTENDANCE_SUMMARY", self.year),
                             "ATT/2026-27/0001")

    def test_unknown_type_is_refused(self):
        with transaction.atomic(), self.assertRaises(ValueError):
            serials.next_serial("NOPE", self.year)


class IssuedDocumentHistoryTests(TestCase):
    def setUp(self):
        self.doc = IssuedDocument.objects.create(
            document_type="BONAFIDE", serial="BON/2026-27/0001", academic_year=make_year(),
            payload={"student_name": "Asha"})

    def test_update_is_refused(self):
        self.doc.payload = {"student_name": "Other"}
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.doc.save()

    def test_delete_is_refused(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            IssuedDocument.objects.filter(pk=self.doc.pk).delete()


@skipUnless(connection.vendor == "postgresql", "row locks need PostgreSQL")
class SerialConcurrencyTests(TransactionTestCase):
    def test_simultaneous_issues_get_distinct_serials(self):
        year = make_year()
        results, barrier = [], threading.Barrier(4)

        def worker():
            try:
                barrier.wait()
                with transaction.atomic():
                    results.append(serials.next_serial("BONAFIDE", year))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [f"BON/2026-27/{n:04d}" for n in range(1, 5)])
