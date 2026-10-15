"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

import threading
from datetime import date
from unittest import mock, skipUnless

from django.db import DatabaseError, connection, connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from accounts.models import SecurityEvent
from core.documents import serials, service
from core.documents.engine import render_pdf
from core.forms import SchoolForm
from core.models import AcademicYear, IssuedDocument, School

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


class IssueServiceTests(TestCase):
    def setUp(self):
        self.year = make_year()
        self.school = School.objects.create(
            name="Sri Vidya", address="1 Main Road", affiliation_number="AP/1",
            principal_name="K. Lakshmi")

    def issue(self):
        return service.issue(document_type="BONAFIDE", academic_year=self.year,
                             payload={"student_name": "Asha"}, actor=None)

    def test_issue_stores_letterhead_and_records_event(self):
        doc = self.issue()
        self.assertEqual(doc.serial, "BON/2026-27/0001")
        self.assertEqual(doc.payload["letterhead"]["principal_name"], "K. Lakshmi")
        event = SecurityEvent.objects.get(event_type="DOCUMENT_ISSUED")
        self.assertEqual(event.detail["serial"], doc.serial)

    def test_reprint_keeps_the_letterhead_it_was_issued_with(self):
        doc = self.issue()
        self.school.principal_name = "New Principal"
        self.school.save()
        captured = {}

        def fake_render(template, context):
            captured.update(context)
            return b"%PDF-fake"

        with mock.patch("core.documents.service.render_pdf", fake_render):
            service.pdf_for(doc, actor=None)
        self.assertEqual(captured["payload"]["letterhead"]["principal_name"], "K. Lakshmi")
        self.assertEqual(
            SecurityEvent.objects.filter(event_type="DOCUMENT_DOWNLOADED").count(), 1)
        self.assertEqual(IssuedDocument.objects.count(), 1)  # a reprint adds no row

    def test_issue_without_a_school_row_uses_blank_letterhead(self):
        School.objects.all().delete()
        doc = self.issue()
        self.assertEqual(doc.payload["letterhead"]["school_name"], "")
