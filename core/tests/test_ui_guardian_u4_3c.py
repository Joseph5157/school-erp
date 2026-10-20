"""U4-3C: Guardian report-card acceptance and regression (verification only, no new behaviour)."""

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import publication
from core.models import GuardianAccount, IssuedDocument, StudentResult, Subject
from core.tests.test_ui_guardian_u4_3b import CardFixture


class AcceptanceFixture(CardFixture):
    def pdf_url(self, card, grant=None):
        return reverse("portal:report-card-pdf",
                       args=[(grant or self.asha_grant).public_id, card.public_id])

    def all_urls(self, card):
        return [self.list_url(), self.card_url(card), self.pdf_url(card)]

    def second_term_card(self, extra=0):
        """Publish Term 2 with `extra` additional finalized assessments (more snapshot rows)."""
        self.add_result(self.maths, "Oct test", date(2026, 10, 5), term=self.term2)
        for number in range(extra):
            for offering in (self.telugu, self.english, self.maths):
                self.add_result(offering, f"Oct quiz {number}", date(2026, 10, 6 + number),
                                term=self.term2)
        plan = publication.plan_publication(self.term2, self.six_a, ())
        created = publication.confirm_publication(
            term=self.term2, section=self.six_a, include=(), token=plan["token"],
            actor=self.admin)
        return self.asha_card(created)

    def snapshot_view(self, card):
        """Everything a guardian can read on the card, as plain data."""
        page = self.portal.get(self.card_url(card))
        return [(g["label"], g["date"], [(e.subject_label, e.status, e.score, e.percentage,
                                          e.grade_label, e.pass_fail_label)
                                         for e in g["entries"]])
                for g in page.context["groups"]]


class VisibilityAndAuthorizationTests(AcceptanceFixture, TestCase):
    def assert_all_404(self, card):
        for url in (self.card_url(card), self.pdf_url(card)):
            with self.subTest(url=url):
                self.assertEqual(self.portal.get(url).status_code, 404)

    def test_anonymous_visitors_are_sent_to_login_for_every_report_card_url(self):
        card = self.asha_card()
        anonymous = self.client_class()
        for url in self.all_urls(card):
            with self.subTest(url=url):
                response = anonymous.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"])

    def test_empty_state_before_anything_is_published(self):
        page = self.portal.get(self.list_url())
        self.assertContains(page, "No report cards have been published yet.")
        self.assertEqual(page.context["publications"], [])

    def test_stale_publication_is_hidden_from_list_card_and_pdf(self):
        card = self.asha_card()
        result = StudentResult.objects.filter(academic_enrollment=self.asha_e).first()
        publication.mark_stale_for_result(result, actor=self.admin)
        self.assertEqual(self.portal.get(self.list_url()).context["publications"], [])
        self.assert_all_404(card)

    def test_withdrawn_publication_is_hidden_from_list_card_and_pdf(self):
        card = self.asha_card()
        publication.withdraw(card, actor=self.admin, reason="Published by mistake")
        page = self.portal.get(self.list_url())
        self.assertEqual(page.context["publications"], [])
        self.assertContains(page, "No report cards have been published yet.")
        self.assert_all_404(card)

    def test_under_review_child_exposes_no_report_card_content(self):
        card = self.asha_card()
        self.today = date(2027, 4, 5)  # after the academic year: guardian access under review
        for url in self.all_urls(card):
            with self.subTest(url=url):
                self.assertEqual(self.portal.get(url).status_code, 404)
        home = self.portal.get("/guardian/").content.decode()
        self.assertIn("access under review by the school", home)
        for leaked in (str(card.public_id), "Term 1", "UT1", "10.00 / 20.00"):
            self.assertNotIn(leaked, home)

    def test_another_guardian_cannot_open_this_childs_report_card_or_pdf(self):
        card = self.asha_card()
        account = GuardianAccount.objects.get(guardian=self.other)
        account.user.set_password("pw-other-123")
        account.user.must_change_password = False
        account.user.save()
        other = self.client_class()
        self.assertTrue(other.login(username="other.parent", password="pw-other-123"))
        for url in self.all_urls(card):
            with self.subTest(url=url):
                self.assertEqual(other.get(url).status_code, 404)

    def test_a_card_id_never_works_under_another_childs_grant(self):
        created = self.publish()
        bina_card = next(p for p in created if p.student == self.bina)
        asha_card = self.asha_card(created)
        for url in (self.card_url(bina_card), self.pdf_url(bina_card),
                    self.card_url(asha_card, self.bina_grant),
                    self.pdf_url(asha_card, self.bina_grant)):
            with self.subTest(url=url):
                self.assertEqual(self.portal.get(url).status_code, 404)

    def test_report_card_pages_are_read_only(self):
        card = self.asha_card()
        for url in (self.list_url(), self.card_url(card)):
            with self.subTest(url=url):
                self.assertEqual(self.portal.post(url).status_code, 405)


class PdfTests(AcceptanceFixture, TestCase):
    def test_link_targets_this_publication_and_the_download_is_that_publication(self):
        first = self.asha_card()
        second = self.second_term_card()
        for card in (first, second):
            with self.subTest(card=card.term_label):
                page = self.portal.get(self.card_url(card))
                self.assertContains(page, f'href="{self.pdf_url(card)}"')
                response = self.portal.get(self.pdf_url(card))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF"))
                self.assertEqual(IssuedDocument.objects.get(publication=card).publication, card)
        self.assertEqual(IssuedDocument.objects.count(), 2)

    def test_downloading_twice_reprints_the_same_issued_document(self):
        card = self.asha_card()
        self.portal.get(self.pdf_url(card))
        self.portal.get(self.pdf_url(card))
        self.assertEqual(IssuedDocument.objects.filter(publication=card).count(), 1)


class SnapshotStabilityTests(AcceptanceFixture, TestCase):
    def test_published_card_is_unchanged_by_live_configuration_changes(self):
        card = self.asha_card()
        before = self.snapshot_view(card)
        self.assertEqual([g[0] for g in before], ["UT2", "UT1"])  # latest first
        self.order({"Mathematics": 1, "English": 2, "Telugu": 3})
        Subject.objects.filter(name="Telugu").update(name="Telugu (Second Language)")
        self.assertEqual(self.snapshot_view(card), before)
        page = self.portal.get(self.card_url(card))
        self.assertNotContains(page, "Second Language")

    def test_page_has_no_totals_averages_ranks_or_weighting_after_two_publications(self):
        first, second = self.asha_card(), self.second_term_card()
        for card in (first, second):
            html = self.portal.get(self.card_url(card)).content.decode()
            for forbidden in ("Total", "Average", "Rank", "Weighted", "Overall", "Mean"):
                with self.subTest(card=card.term_label, word=forbidden):
                    self.assertNotIn(forbidden, html)


class QueryCountTests(AcceptanceFixture, TestCase):
    CEILING = 30

    def count(self, url):
        self.portal.get(url)  # warm up (session, caches)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.portal.get(url).status_code, 200)
        return len(queries.captured_queries)

    def test_card_page_query_count_does_not_grow_with_snapshot_entries(self):
        small = self.asha_card()
        large = self.second_term_card(extra=4)
        self.assertGreater(large.entries.count(), 2 * small.entries.count())
        small_count = self.count(self.card_url(small))
        large_count = self.count(self.card_url(large))
        self.assertEqual(small_count, large_count)
        self.assertLessEqual(large_count, self.CEILING)

    def test_list_query_count_does_not_grow_with_the_number_of_cards(self):
        self.asha_card()
        one = self.count(self.list_url())
        self.second_term_card(extra=2)
        two = self.count(self.list_url())
        self.assertEqual(one, two)
        self.assertLessEqual(two, self.CEILING)
