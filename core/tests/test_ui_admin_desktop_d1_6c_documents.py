"""UI-D1-6C: Documents (index, Bonafide, Attendance summary, Report card PDFs) presentation and navigation.

Presentation only. These tests also re-prove the safeguards the page change must not touch: a GET never issues,
a POST creates exactly one audited IssuedDocument, PDF responses keep their status and headers, and the
report card list is the current published snapshot only.
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from accounts.models import SecurityEvent
from core import publication
from core.breadcrumbs import breadcrumb_context
from core.documents import attendance_summary, bonafide
from core.models import AttendanceStatus, IssuedDocument, Student, TermPublication
from core.portal import visible_publications
from core.tests.test_phase7_alerts import AlertFixture

User = get_user_model()
ACTIVE_LINK = r'<a class="nav-link active" href="([^"]+)"'
INDEX = reverse("core:document-index")
BONAFIDE = reverse("core:bonafide-create")
SUMMARY = reverse("core:attendance-summary")
CARDS = reverse("core:document-report-cards")
ISSUED = SecurityEvent.EventType.DOCUMENT_ISSUED


def html(response):
    return response.content.decode()


class Base(AlertFixture):
    def client_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._viewers}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def teacher(self):
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        return client

    def params(self, **overrides):
        return {"section": self.six_a.pk, "start": "2026-10-01", "end": "2026-10-12", **overrides}

    def issued_events(self):
        return SecurityEvent.objects.filter(event_type=ISSUED).count()

    def bonafide_data(self, **overrides):
        return {"student": self.asha.pk, "purpose": "BANK", "purpose_text": "", **overrides}


class IndexTests(Base, TestCase):
    def test_header_types_and_empty_state(self):
        page = html(self.client.get(INDEX))
        self.assertRegex(page, r'<h1 class="erp-page-title">Documents</h1>')
        self.assertEqual(page.count("<h1"), 1)
        for url, label in ((BONAFIDE, "Bonafide certificate"), (CARDS, "Report card PDF"),
                           (SUMMARY, "Attendance summary")):
            self.assertIn(f'<a href="{url}">{label}</a>', page)
        self.assertIn("Nothing issued yet.", page)
        self.assertIn('role="region" aria-label="Recently issued documents" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertEqual(page.count('scope="col"'), 5)

    def test_recent_table_has_row_headers_and_descriptive_pdf_links(self):
        doc = bonafide.issue_bonafide(student=self.asha, purpose_key="BANK", purpose_text="", actor=self.admin)
        page = html(self.client.get(INDEX))
        self.assertIn(f'<th scope="row" class="fw-semibold text-nowrap">{doc.serial}</th>', page)
        pdf = reverse("core:document-pdf", args=[doc.pk])
        self.assertIn(f'<a href="{pdf}">PDF<span class="visually-hidden"> for {doc.serial}</span></a>', page)
        self.assertNotIn("Nothing issued yet.", page)
        self.assertIn(self.asha.full_name, page)

    def test_a_get_never_issues(self):
        self.client.get(INDEX)
        self.assertFalse(IssuedDocument.objects.exists())
        self.assertEqual(self.issued_events(), 0)

    def test_permission_outcomes_are_unchanged(self):
        self.assertEqual(self.client_class().get(INDEX).status_code, 302)
        self.assertEqual(self.teacher().get(INDEX).status_code, 403)
        self.assertEqual(self.guardian_client().get(INDEX).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(INDEX).status_code, 403)
        _, issuer = self.client_with("issue_document")
        self.assertEqual(issuer.get(INDEX).status_code, 200)


class BonafideTests(Base, TestCase):
    def test_form_structure(self):
        page = html(self.client.get(BONAFIDE))
        self.assertRegex(page, r'<h1 class="erp-page-title">Bonafide certificate</h1>')
        self.assertIn('<form method="post" class="erp-form">', page)
        self.assertIn("Fields marked with an asterisk are required.", page)
        for name in ("student", "purpose", "purpose_text"):
            self.assertIn(f'name="{name}"', page)
        self.assertIn("Issue certificate", page)
        self.assertIn("assigns the next serial number", page)
        self.assertIn(f'<a class="btn btn-link" href="{INDEX}">Cancel</a>', page)
        self.assertFalse(IssuedDocument.objects.exists())

    def test_post_issues_exactly_once_with_audit_and_redirects_to_the_pdf(self):
        response = self.client.post(BONAFIDE, self.bonafide_data())
        doc = IssuedDocument.objects.get()
        self.assertRedirects(response, reverse("core:document-pdf", args=[doc.pk]), fetch_redirect_response=False)
        self.assertTrue(doc.serial.startswith("BON/"))
        self.assertEqual(doc.issued_by, self.admin)
        self.assertEqual(self.issued_events(), 1)
        self.assertEqual(doc.payload["student_name"], self.asha.full_name)

    def test_invalid_post_shows_summary_and_issues_nothing(self):
        page = html(self.client.post(BONAFIDE, self.bonafide_data(student="")))
        self.assertIn('id="form-error-summary"', page)
        self.assertIn("Fix 1 problem before issuing:", page)
        self.assertIn('href="#id_student"', page)
        self.assertFalse(IssuedDocument.objects.exists())
        page = html(self.client.post(BONAFIDE, self.bonafide_data(purpose="OTHER")))
        self.assertIn('id="form-error-summary"', page)
        self.assertFalse(IssuedDocument.objects.exists())

    def test_service_refusal_is_shown_and_nothing_is_issued(self):
        Student.objects.filter(pk=self.asha.pk).update(status=Student.Status.INACTIVE)
        page = html(self.client.post(BONAFIDE, self.bonafide_data()))
        self.assertIn("inactive", page)
        self.assertIn('id="form-error-summary"', page)
        self.assertFalse(IssuedDocument.objects.exists())
        self.assertEqual(self.issued_events(), 0)

    def test_csrf_is_still_enforced(self):
        strict = self.client_class(enforce_csrf_checks=True)
        strict.login(username="admin", password="pass-12345")
        self.assertEqual(strict.post(BONAFIDE, self.bonafide_data()).status_code, 403)
        self.assertFalse(IssuedDocument.objects.exists())

    def test_permission_outcomes_are_unchanged(self):
        self.assertEqual(self.client_class().get(BONAFIDE).status_code, 302)
        self.assertEqual(self.teacher().get(BONAFIDE).status_code, 403)
        self.assertEqual(self.guardian_client().post(BONAFIDE, self.bonafide_data()).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.post(BONAFIDE, self.bonafide_data()).status_code, 403)
        self.assertFalse(IssuedDocument.objects.exists())


class AttendanceSummaryTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.register(date(2026, 10, 7))                                  # Asha absent, Bina present
        self.register(date(2026, 10, 8), asha=AttendanceStatus.PRESENT)

    def test_unbound_page_has_the_filter_only_and_issues_nothing(self):
        page = html(self.client.get(SUMMARY))
        self.assertRegex(page, r'<h1 class="erp-page-title">Attendance summary</h1>')
        self.assertIn('<form method="get" class="erp-toolbar erp-toolbar--inline erp-document-toolbar"', page)
        self.assertNotIn("form-error-summary", page)
        self.assertNotIn("Issue PDF with serial number", page)
        self.assertFalse(IssuedDocument.objects.exists())

    def test_summary_table_equals_the_service_and_a_get_never_issues(self):
        response = self.client.get(SUMMARY, self.params())
        page = html(response)
        data = attendance_summary.build(self.six_a, date(2026, 10, 1), date(2026, 10, 12))
        self.assertEqual(response.context["summary"]["totals"], data["totals"])
        self.assertIn('role="region" aria-label="Attendance summary" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertIn('<th scope="row">Section total</th>', page)
        row = next(r for r in data["rows"] if r["student_name"] == self.asha.full_name)
        self.assertIn(
            f'<th scope="row" class="fw-normal text-break">{row["student_name"]}</th>'
            f'<td class="erp-num">{row["present"]}</td><td class="erp-num">{row["absent"]}</td>'
            f'<td class="erp-num">{row["total"]}</td><td class="erp-num">{row["percentage"]}</td>', page)
        self.assertFalse(IssuedDocument.objects.exists())
        self.assertEqual(self.issued_events(), 0)

    def test_issue_form_keeps_its_hidden_fields_and_round_trips_to_one_audited_issuance(self):
        page = html(self.client.get(SUMMARY, self.params()))
        form = re.search(r'<form method="post">(.*?)</form>', page, re.S).group(1)
        hidden = dict(re.findall(r'<input type="hidden" name="(section|start|end)" value="([^"]*)"', form))
        self.assertEqual(set(hidden), {"section", "start", "end"})
        self.assertEqual(hidden["section"], str(self.six_a.pk))
        self.assertIn("Issue PDF with serial number", form)
        response = self.client.post(SUMMARY, hidden)
        doc = IssuedDocument.objects.get()
        self.assertRedirects(response, reverse("core:document-pdf", args=[doc.pk]), fetch_redirect_response=False)
        self.assertTrue(doc.serial.startswith("ATT/"))
        self.assertEqual(self.issued_events(), 1)

    def test_bad_range_shows_the_refusal_in_the_summary_and_issues_nothing(self):
        page = html(self.client.get(SUMMARY, self.params(start="2026-10-12", end="2026-10-01")))
        self.assertIn("end date is before", page)
        self.assertIn('id="form-error-summary"', page)
        self.assertNotIn("Issue PDF with serial number", page)
        page = html(self.client.post(SUMMARY, self.params(start="2026-10-12", end="2026-10-01")))
        self.assertIn("end date is before", page)
        self.assertFalse(IssuedDocument.objects.exists())

    def test_missing_fields_show_a_linked_summary(self):
        page = html(self.client.get(SUMMARY, {"section": self.six_a.pk}))
        self.assertIn("Fix 2 problems before showing the summary:", page)
        self.assertIn('href="#id_start"', page)

    def test_empty_range_keeps_the_legacy_text(self):
        page = html(self.client.get(SUMMARY, self.params(start="2026-09-01", end="2026-09-05")))
        self.assertIn("No submitted attendance in this range.", page)

    def test_back_link_and_permission_outcomes(self):
        self.assertIn(f'<a class="btn btn-link" href="{INDEX}">Back</a>', html(self.client.get(SUMMARY)))
        self.assertEqual(self.client_class().get(SUMMARY).status_code, 302)
        self.assertEqual(self.teacher().get(SUMMARY).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.post(SUMMARY, self.params()).status_code, 403)
        self.assertFalse(IssuedDocument.objects.exists())


class ReportCardTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = TermPublication.objects.get(student=self.asha, term=self.term1)

    def listing(self):
        return self.client.get(CARDS, {"student": self.asha.pk})

    def test_unbound_page_prompts_and_lists_nothing(self):
        page = html(self.client.get(CARDS))
        self.assertRegex(page, r'<h1 class="erp-page-title">Report card PDFs</h1>')
        self.assertIn("Choose a Student to list their current published report cards.", page)
        self.assertNotIn("form-error-summary", page)

    def test_list_is_a_labelled_table_with_descriptive_pdf_links_to_the_same_route(self):
        response = self.listing()
        page = html(response)
        self.assertEqual(response.context["publications"], visible_publications(self.asha))
        url = reverse("core:document-report-card-pdf", args=[self.pub.pk])
        name = f"{self.asha.full_name}, {self.pub.term_label} {self.pub.academic_year_label}"
        self.assertIn(f'<a href="{url}">PDF<span class="visually-hidden"> for {name}</span></a>', page)
        self.assertIn(f'<th scope="row" class="fw-semibold">{self.pub.term_label}</th>', page)
        self.assertIn('role="region"', page)
        self.assertIn("<caption", page)
        self.assertEqual(page.count('scope="col"'), 3)

    def test_rendering_the_list_never_issues(self):
        self.listing()
        self.client.get(CARDS)
        self.assertFalse(IssuedDocument.objects.exists())
        self.assertEqual(self.issued_events(), 0)

    def test_stale_card_is_excluded(self):
        self.assertEqual([p.pk for p in self.listing().context["publications"]], [self.pub.pk])
        publication.mark_stale_for_result(self.result, actor=self.admin)
        response = self.listing()
        self.assertEqual(response.context["publications"], [])
        self.assertEqual(response.context["publications"], visible_publications(self.asha))
        self.assertIn("No published report cards for this student.", html(response))
        self.assertNotIn(reverse("core:document-report-card-pdf", args=[self.pub.pk]), html(response))

    def test_superseded_and_withdrawn_versions_are_excluded(self):
        self.result.correct(new_status=self.result.status, new_score="16", actor=self.admin, reason="Recount")
        self.publish()
        versions = TermPublication.objects.filter(student=self.asha, term=self.term1)
        current = versions.get(status=TermPublication.Status.PUBLISHED)
        old = versions.exclude(pk=current.pk).get()
        self.assertNotEqual(old.status, TermPublication.Status.PUBLISHED)
        page = html(self.listing())
        self.assertIn(reverse("core:document-report-card-pdf", args=[current.pk]), page)
        self.assertNotIn(reverse("core:document-report-card-pdf", args=[old.pk]), page)
        publication.withdraw(current, actor=self.admin, reason="Wrong release")
        response = self.listing()
        self.assertEqual(response.context["publications"], [])
        self.assertNotIn(reverse("core:document-report-card-pdf", args=[current.pk]), html(response))
        self.assertNotIn(reverse("core:document-report-card-pdf", args=[old.pk]), html(response))

    def test_pdf_route_keeps_status_content_type_and_disposition(self):
        url = reverse("core:document-report-card-pdf", args=[self.pub.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertRegex(response["Content-Disposition"], r'^inline; filename="RC-[^"/]+\.pdf"$')
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(IssuedDocument.objects.count(), 1)
        self.client.get(url)
        self.assertEqual(IssuedDocument.objects.count(), 1)  # the snapshot and serial are reused

    def test_pdf_route_is_unavailable_for_a_stale_card(self):
        url = reverse("core:document-report-card-pdf", args=[self.pub.pk])
        publication.mark_stale_for_result(self.result, actor=self.admin)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_pdf_authorization_is_unchanged(self):
        url = reverse("core:document-report-card-pdf", args=[self.pub.pk])
        self.assertEqual(self.client_class().get(url).status_code, 302)
        self.assertEqual(self.teacher().get(url).status_code, 403)
        self.assertEqual(self.guardian_client().get(url).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(url).status_code, 403)
        _, issuer = self.client_with("issue_document")
        self.assertEqual(issuer.get(url).status_code, 200)

    def test_issued_card_that_is_no_longer_current_still_redirects_with_the_message(self):
        self.client.get(reverse("core:document-report-card-pdf", args=[self.pub.pk]))
        doc = IssuedDocument.objects.get()
        publication.mark_stale_for_result(self.result, actor=self.admin)
        response = self.client.get(reverse("core:document-pdf", args=[doc.pk]), follow=True)
        self.assertRedirects(response, INDEX)
        self.assertContains(response, "no longer current")

    def test_invalid_student_shows_the_summary(self):
        page = html(self.client.get(CARDS, {"student": "99999"}))
        self.assertIn("Fix 1 problem before showing report cards:", page)
        self.assertIn('href="#id_student"', page)

    def test_permission_outcomes_are_unchanged(self):
        self.assertEqual(self.client_class().get(CARDS).status_code, 302)
        self.assertEqual(self.teacher().get(CARDS).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(CARDS).status_code, 403)


class DocumentPdfTests(Base, TestCase):
    def test_issued_document_pdf_headers_and_authorization(self):
        doc = bonafide.issue_bonafide(student=self.asha, purpose_key="BANK", purpose_text="", actor=self.admin)
        url = reverse("core:document-pdf", args=[doc.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertRegex(response["Content-Disposition"], r'^inline; filename="BON-[^"/]+\.pdf"$')
        self.assertEqual(IssuedDocument.objects.count(), 1)
        self.assertEqual(self.client_class().get(url).status_code, 302)
        self.assertEqual(self.teacher().get(url).status_code, 403)
        self.assertEqual(self.guardian_client().get(url).status_code, 403)


class NavigationTests(Base, TestCase):
    def labels(self, url, user=None):
        context = breadcrumb_context(resolve(url), user)
        return [c["label"] for c in context["breadcrumbs"]], context["nav_section"]

    def test_rules(self):
        self.assertEqual(self.labels(INDEX), (["Overview", "Documents"], "document-index"))
        for url, label in ((BONAFIDE, "Bonafide certificate"), (SUMMARY, "Attendance summary"),
                           (CARDS, "Report card PDFs")):
            self.assertEqual(self.labels(url), (["Overview", "Documents", label], "document-index"))

    def test_parent_crumbs_follow_the_destination_permission(self):
        user, _ = self.client_with("issue_document")
        self.assertEqual(self.labels(BONAFIDE, user)[0], ["Documents", "Bonafide certificate"])
        user, _ = self.client_with("issue_document", "view_school")
        self.assertEqual(self.labels(SUMMARY, user)[0], ["Overview", "Documents", "Attendance summary"])
        self.assertEqual(self.labels(INDEX, user)[0], ["Overview", "Documents"])
        user, _ = self.client_with("issue_document")
        self.assertEqual(self.labels(INDEX, user)[0], [])
        user, _ = self.client_with("view_school")
        self.assertEqual(self.labels(CARDS, user)[0], ["Overview", "Report card PDFs"])

    def test_pdf_routes_have_no_breadcrumb_rule(self):
        for url in (reverse("core:document-pdf", args=[1]), reverse("core:document-report-card-pdf", args=[1])):
            self.assertEqual(breadcrumb_context(resolve(url))["breadcrumbs"], [])

    def test_sidebar_highlights_documents_on_every_page_state(self):
        self.register(date(2026, 10, 7))
        pages = {
            "index": self.client.get(INDEX),
            "bonafide": self.client.get(BONAFIDE),
            "bonafide-invalid": self.client.post(BONAFIDE, self.bonafide_data(student="")),
            "summary": self.client.get(SUMMARY),
            "summary-result": self.client.get(SUMMARY, self.params()),
            "summary-invalid": self.client.get(SUMMARY, {"section": self.six_a.pk}),
            "cards": self.client.get(CARDS),
            "cards-result": self.client.get(CARDS, {"student": self.asha.pk}),
        }
        for name, response in pages.items():
            with self.subTest(page=name):
                self.assertEqual(re.findall(ACTIVE_LINK, html(response)), [INDEX])
