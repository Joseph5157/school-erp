"""Security Gate 4B: documents depend on the permissions of the data they contain.

`issue_document` opens the Documents area. Choosing a student needs `view_student`; a report
card (listing or PDF) needs `view_studentresult`; an attendance summary needs
`view_attendanceentry`. A direct request for a PDF without the needed permission returns 403,
and the recently-issued list only shows documents the user could open. Permissions count
whether held directly or through a group. PDF rendering is stubbed: access is what is tested.
"""

from unittest import mock

from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from core.documents import attendance_summary, bonafide, report_card
from core.models import IssuedDocument
from core.tests.gate4b_support import holders
from core.tests.test_phase6_access_boundary import TODAY
from core.tests.test_phase7_alerts import AlertFixture

ISSUE = "core.issue_document"
VIEW_STUDENT = "core.view_student"
VIEW_RESULT = "core.view_studentresult"
VIEW_ENTRY = "core.view_attendanceentry"
PDF = "core.document_views.service.pdf_response"


class DocumentFixture(AlertFixture):
    def setUp(self):
        super().setUp()
        self.pub = next(p for p in self.publish() if p.student == self.asha)
        self.register()
        self.bonafide = bonafide.issue_bonafide(
            student=self.asha, purpose_key=bonafide.PURPOSES[0][0], purpose_text="",
            actor=self.admin,
        )
        self.summary = attendance_summary.issue_summary(
            self.six_a, TODAY, TODAY, actor=self.admin
        )
        self.card = report_card.document_for(self.pub, actor=self.admin)

    def pdf_url(self, document):
        return reverse("core:document-pdf", args=[document.pk])


class DirectPdfTests(DocumentFixture, TestCase):
    def cases(self):
        return (
            ("bonafide", self.pdf_url(self.bonafide), VIEW_STUDENT),
            ("attendance summary", self.pdf_url(self.summary), VIEW_ENTRY),
            ("report card document", self.pdf_url(self.card), VIEW_RESULT),
            (
                "report card by publication",
                reverse("core:document-report-card-pdf", args=[self.pub.pk]),
                VIEW_RESULT,
            ),
        )

    def test_a_direct_pdf_request_without_the_data_permission_is_forbidden(self):
        for label, url, _ in self.cases():
            for how, client in holders(self.client_class, ISSUE):
                with self.subTest(label=label, how=how), mock.patch(PDF) as render:
                    self.assertEqual(client.get(url).status_code, 403)
                    render.assert_not_called()

    def test_the_wrong_data_permission_is_not_enough(self):
        wrong = {VIEW_STUDENT: VIEW_ENTRY, VIEW_ENTRY: VIEW_RESULT, VIEW_RESULT: VIEW_STUDENT}
        for label, url, needed in self.cases():
            for how, client in holders(self.client_class, ISSUE, wrong[needed]):
                with self.subTest(label=label, how=how), mock.patch(PDF):
                    self.assertEqual(client.get(url).status_code, 403)

    def test_holders_of_the_data_permission_can_open_it(self):
        for label, url, needed in self.cases():
            for how, client in holders(self.client_class, ISSUE, needed):
                with self.subTest(label=label, how=how), mock.patch(
                    PDF, return_value=HttpResponse("pdf")
                ):
                    self.assertEqual(client.get(url).status_code, 200)

    def test_issue_document_alone_is_not_enough_to_open_the_documents_area_pdfs(self):
        # The open question is answered one way only: dependencies are enforced.
        for how, client in holders(self.client_class, ISSUE):
            with self.subTest(how=how), mock.patch(PDF):
                for document in (self.bonafide, self.summary, self.card):
                    self.assertEqual(client.get(self.pdf_url(document)).status_code, 403)


class ChooserAndFormTests(DocumentFixture, TestCase):
    def test_student_selection_needs_view_student(self):
        url = reverse("core:bonafide-create")
        for how, client in holders(self.client_class, ISSUE):
            with self.subTest(how=how):
                self.assertEqual(client.get(url).status_code, 403)
                posted = client.post(url, {"student": self.asha.pk, "purpose": "BANK"})
                self.assertEqual(posted.status_code, 403)
        before = IssuedDocument.objects.count()
        for how, client in holders(self.client_class, ISSUE, VIEW_STUDENT):
            with self.subTest(how=how, holds="view_student"):
                page = client.get(url)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Asha Rao")
        self.assertEqual(IssuedDocument.objects.count(), before)

    def test_report_card_chooser_needs_students_and_results(self):
        url = reverse("core:document-report-cards")
        for perms in ((ISSUE,), (ISSUE, VIEW_STUDENT), (ISSUE, VIEW_RESULT)):
            for how, client in holders(self.client_class, *perms):
                with self.subTest(perms=perms, how=how):
                    self.assertEqual(client.get(url).status_code, 403)
        for how, client in holders(self.client_class, ISSUE, VIEW_STUDENT, VIEW_RESULT):
            with self.subTest(how=how, holds="both"):
                self.assertEqual(client.get(url).status_code, 200)

    def test_attendance_summary_needs_view_attendanceentry(self):
        url = reverse("core:attendance-summary")
        params = {"section": self.six_a.pk, "start": TODAY.isoformat(), "end": TODAY.isoformat()}
        before = IssuedDocument.objects.count()
        for how, client in holders(self.client_class, ISSUE):
            with self.subTest(how=how):
                self.assertEqual(client.get(url).status_code, 403)
                self.assertEqual(client.get(url, params).status_code, 403)
                self.assertEqual(client.post(url, params).status_code, 403)
        self.assertEqual(IssuedDocument.objects.count(), before)  # nothing issued
        for how, client in holders(self.client_class, ISSUE, VIEW_ENTRY):
            with self.subTest(how=how, holds="view_attendanceentry"):
                page = client.get(url, params)
                self.assertEqual(page.status_code, 200)
                self.assertIsNotNone(page.context["summary"])


class RecentlyIssuedTests(DocumentFixture, TestCase):
    def recent(self, client):
        page = client.get(reverse("core:document-index"))
        self.assertEqual(page.status_code, 200)
        return page, {doc.pk for doc in page.context["recent"]}

    def test_the_list_only_shows_documents_the_user_could_open(self):
        expectations = (
            ((ISSUE,), set()),
            ((ISSUE, VIEW_STUDENT), {self.bonafide.pk}),
            ((ISSUE, VIEW_ENTRY), {self.summary.pk}),
            ((ISSUE, VIEW_RESULT), {self.card.pk}),
            (
                (ISSUE, VIEW_STUDENT, VIEW_ENTRY, VIEW_RESULT),
                {self.bonafide.pk, self.summary.pk, self.card.pk},
            ),
        )
        for perms, expected in expectations:
            for how, client in holders(self.client_class, *perms):
                with self.subTest(perms=perms, how=how):
                    page, shown = self.recent(client)
                    self.assertEqual(shown, expected)
                    if not expected:
                        self.assertNotContains(page, "Asha Rao")
                        self.assertNotContains(page, self.bonafide.serial)
