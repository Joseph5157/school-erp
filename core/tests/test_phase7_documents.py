"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

import threading
from datetime import date
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import publication
from core.documents import attendance_summary, bonafide, serials, service
from core.documents.engine import render_pdf
from core.forms import SchoolForm
from core.models import (
    AcademicYear,
    Applicant,
    AttendanceStatus,
    IssuedDocument,
    School,
    Student,
    TermPublication,
)
from core.tests.test_phase6_publication import PublicationFixture
from core.tests.test_phase7_alerts import AlertFixture
from core.tests.test_phase7_announcements import AnnouncementFixture

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


class BonafideTests(AnnouncementFixture, TestCase):
    def stranger(self):
        return Student.objects.create(
            applicant=Applicant.objects.create(full_name="No Enrolment"),
            full_name="No Enrolment")

    def issue(self, student=None, key="BANK", text=""):
        return bonafide.issue_bonafide(student=student or self.asha, purpose_key=key,
                                       purpose_text=text, actor=self.admin)

    def test_issue_for_enrolled_student(self):
        doc = self.issue()
        self.assertTrue(doc.serial.startswith("BON/"))
        self.assertEqual(doc.payload["student_name"], self.asha.full_name)
        self.assertEqual(doc.payload["section_label"], self.six_a.name)
        self.assertEqual(doc.payload["purpose"], "Opening a bank account")
        self.assertEqual(doc.student, self.asha)
        self.assertEqual(doc.issued_by, self.admin)

    def test_other_requires_text_and_uses_it(self):
        with self.assertRaises(ValidationError):
            self.issue(key="OTHER", text="  ")
        doc = self.issue(key="OTHER", text="Visa application")
        self.assertEqual(doc.payload["purpose"], "Visa application")

    def test_unknown_purpose_is_refused(self):
        with self.assertRaises(ValidationError):
            self.issue(key="HOLIDAY")

    def test_student_without_current_enrolment_is_refused(self):
        stranger = self.stranger()
        with self.assertRaises(ValidationError) as caught:
            self.issue(student=stranger)
        self.assertIn("no current enrolment", caught.exception.messages[0])

    def test_student_whose_year_has_ended_is_refused(self):
        self.today = date(2028, 1, 1)  # after the fixture's academic year
        with self.assertRaises(ValidationError):
            self.issue()

    def test_view_issues_and_serves_pdf(self):
        page = self.client.post(reverse("core:bonafide-create"), {
            "student": self.asha.pk, "purpose": "PASSPORT", "purpose_text": ""})
        doc = IssuedDocument.objects.get()
        self.assertRedirects(page, reverse("core:document-pdf", args=[doc.pk]),
                             fetch_redirect_response=False)
        pdf = self.client.get(reverse("core:document-pdf", args=[doc.pk]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_view_shows_the_refusal_for_a_student_without_enrolment(self):
        stranger = self.stranger()
        page = self.client.post(reverse("core:bonafide-create"), {
            "student": stranger.pk, "purpose": "BANK", "purpose_text": ""})
        self.assertContains(page, "no current enrolment")
        self.assertEqual(IssuedDocument.objects.count(), 0)

    def test_teachers_and_guardians_are_forbidden(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        for client in (teacher, self.guardian_client()):
            for name in ("core:document-index", "core:bonafide-create"):
                with self.subTest(name=name):
                    self.assertEqual(client.get(reverse(name)).status_code, 403)


class ReportCardPdfTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = TermPublication.objects.get(student=self.asha, term=self.term1)
        self.guardian_url = reverse(
            "portal:report-card-pdf", args=[self.asha_grant.public_id, self.pub.public_id])
        self.office_url = reverse("core:document-report-card-pdf", args=[self.pub.pk])

    def test_guardian_downloads_own_childs_card(self):
        response = self.portal.get(self.guardian_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        doc = IssuedDocument.objects.get()
        self.assertTrue(doc.serial.startswith("RC/"))
        self.assertIsNone(doc.issued_by)
        self.assertEqual(doc.student, self.asha)
        self.assertEqual(doc.payload["entries"][0]["score"], "15.00")

    def test_second_download_reuses_serial_and_snapshot(self):
        self.portal.get(self.guardian_url)
        self.portal.get(self.guardian_url)
        self.assertEqual(IssuedDocument.objects.count(), 1)
        self.assertEqual(
            SecurityEvent.objects.filter(event_type="DOCUMENT_DOWNLOADED").count(), 2)

    def test_other_guardians_child_is_404(self):
        bina_pub = TermPublication.objects.get(student=self.bina, term=self.term1)
        url = reverse("portal:report-card-pdf",
                      args=[self.asha_grant.public_id, bina_pub.public_id])
        self.assertEqual(self.portal.get(url).status_code, 404)

    def test_stale_publication_gives_nothing_to_guardian_or_office(self):
        publication.mark_stale_for_result(self.result, actor=self.admin)
        self.assertEqual(self.portal.get(self.guardian_url).status_code, 404)
        self.assertEqual(self.client.get(self.office_url).status_code, 404)
        self.assertEqual(IssuedDocument.objects.count(), 0)

    def test_office_prints_any_published_card(self):
        response = self.client.get(self.office_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(IssuedDocument.objects.get().issued_by, self.admin)

    def test_office_lookup_lists_a_students_cards(self):
        page = self.client.get(reverse("core:document-report-cards"),
                               {"student": self.asha.pk})
        self.assertContains(page, self.pub.term_label)
        self.assertContains(page, self.office_url)

    def test_download_button_is_on_the_portal_card_page(self):
        page = self.portal.get(reverse(
            "portal:report-card", args=[self.asha_grant.public_id, self.pub.public_id]))
        self.assertContains(page, self.guardian_url)

    def test_guardian_cannot_use_the_office_route(self):
        self.assertEqual(self.portal.get(self.office_url).status_code, 403)


class AttendanceSummaryTests(AlertFixture, TestCase):
    START, END = date(2026, 10, 1), date(2026, 10, 12)

    def build(self):
        return attendance_summary.build(self.six_a, self.START, self.END)

    def row(self, data, student):
        return next(r for r in data["rows"] if r["student_name"] == student.full_name)

    def test_counts_only_submitted_eligible_entries(self):
        self.register(date(2026, 10, 7))                                # Asha absent
        self.register(date(2026, 10, 8), asha=AttendanceStatus.PRESENT)
        data = self.build()
        asha = self.row(data, self.asha)
        self.assertEqual((asha["present"], asha["absent"], asha["total"]), (1, 1, 2))
        self.assertEqual(asha["percentage"], "50.0")
        self.assertEqual(data["totals"]["total"], 4)
        self.assertEqual(data["section_label"], self.six_a.name)

    def test_draft_register_is_not_counted(self):
        self.register(date(2026, 10, 7), submit=False)
        self.assertEqual(self.build()["totals"]["total"], 0)

    def test_entries_outside_the_range_are_not_counted(self):
        self.register(date(2026, 9, 30))
        self.assertEqual(self.build()["totals"]["total"], 0)

    def test_bad_ranges_are_refused(self):
        for start, end in ((date(2026, 10, 12), date(2026, 10, 1)),
                           (date(2026, 10, 1), date(2027, 6, 1)),
                           (date(2020, 1, 1), date(2020, 2, 1))):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError):
                attendance_summary.build(self.six_a, start, end)

    def test_issue_records_serial_and_serves_pdf(self):
        self.register(date(2026, 10, 7))
        doc = attendance_summary.issue_summary(self.six_a, self.START, self.END,
                                               actor=self.admin)
        self.assertTrue(doc.serial.startswith("ATT/"))
        self.assertIsNone(doc.student)
        response = self.client.get(reverse("core:document-pdf", args=[doc.pk]))
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_page_shows_the_table_and_post_issues(self):
        self.register(date(2026, 10, 7))
        url = reverse("core:attendance-summary")
        params = {"section": self.six_a.pk, "start": "2026-10-01", "end": "2026-10-12"}
        page = self.client.get(url, params)
        self.assertContains(page, self.asha.full_name)
        posted = self.client.post(url, params)
        doc = IssuedDocument.objects.get()
        self.assertRedirects(posted, reverse("core:document-pdf", args=[doc.pk]),
                             fetch_redirect_response=False)

    def test_page_shows_the_refusal_for_a_bad_range(self):
        page = self.client.get(reverse("core:attendance-summary"), {
            "section": self.six_a.pk, "start": "2026-10-12", "end": "2026-10-01"})
        self.assertContains(page, "end date is before")


class DocumentIndexTests(AnnouncementFixture, TestCase):
    def test_index_lists_links_and_recent_documents(self):
        doc = bonafide.issue_bonafide(student=self.asha, purpose_key="BANK",
                                      purpose_text="", actor=self.admin)
        page = self.client.get(reverse("core:document-index"))
        self.assertContains(page, doc.serial)
        self.assertContains(page, reverse("core:bonafide-create"))
        self.assertContains(page, reverse("core:attendance-summary"))
        self.assertContains(page, reverse("core:document-report-cards"))
        self.assertContains(page, reverse("core:document-pdf", args=[doc.pk]))


class FinalReviewFixTests(PublicationFixture, TestCase):
    """Important findings from the final whole-branch review."""

    def issued_card(self):
        self.publish()
        pub = TermPublication.objects.get(student=self.asha, term=self.term1)
        self.portal.get(reverse(
            "portal:report-card-pdf", args=[self.asha_grant.public_id, pub.public_id]))
        return IssuedDocument.objects.get(publication=pub)

    def test_office_reprint_refuses_a_card_that_is_no_longer_current(self):
        doc = self.issued_card()
        publication.mark_stale_for_result(self.result, actor=self.admin)
        before = SecurityEvent.objects.filter(event_type="DOCUMENT_DOWNLOADED").count()
        response = self.client.get(reverse("core:document-pdf", args=[doc.pk]), follow=True)
        self.assertNotEqual(response["Content-Type"], "application/pdf")
        self.assertContains(response, "no longer current")
        self.assertEqual(
            SecurityEvent.objects.filter(event_type="DOCUMENT_DOWNLOADED").count(), before)

    def test_office_reprint_still_works_for_a_current_card(self):
        doc = self.issued_card()
        response = self.client.get(reverse("core:document-pdf", args=[doc.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_inactive_student_gets_no_bonafide(self):
        Student.objects.filter(pk=self.asha.pk).update(status=Student.Status.INACTIVE)
        self.asha.refresh_from_db()
        with self.assertRaises(ValidationError) as caught:
            bonafide.issue_bonafide(student=self.asha, purpose_key="BANK",
                                    purpose_text="", actor=self.admin)
        self.assertIn("inactive", caught.exception.messages[0])

    def test_serial_does_not_depend_on_the_year_name(self):
        year = AcademicYear.objects.create(
            name='Academic Year "2027-2028" (June to March, full session)',
            start_date=date(2027, 6, 1), end_date=date(2028, 3, 31))
        with transaction.atomic():
            serial = serials.next_serial("BONAFIDE", year)
        self.assertEqual(serial, "BON/2027-28/0001")
        self.assertLessEqual(len(serial), 40)
