"""Security Gate 4B: marks need `view_studentresult` wherever they are shown.

The assessment page keeps the roster under `view_assessment`; the publication preview and
detail keep their workflow under `view_termpublication`. Scores, grades, percentages,
pass/fail, who entered them and the remark need `view_studentresult`, are withheld from the
page context and honoured directly or through a group.
"""

from django.test import TestCase
from django.urls import reverse

from core.models import TermPublication
from core.tests.gate4b_support import holders
from core.tests.test_phase6_publication import PublicationFixture

VIEW_ASSESSMENT = "core.view_assessment"
VIEW_PUBLICATION = "core.view_termpublication"
VIEW_RESULT = "core.view_studentresult"
SCORE_ASHA = "15.00 / 20.00"
SCORE_BINA = "11.00 / 20.00"
PREVIEW_ASHA = "15.00/20.00"  # the publication preview prints scores without spaces
PREVIEW_BINA = "11.00/20.00"
REMARK = "Steady progress."


class AssessmentDetailTests(PublicationFixture, TestCase):
    def url(self):
        return reverse("core:assessment-detail", args=[self.ut1.pk])

    def test_results_need_view_studentresult_but_the_roster_stays(self):
        for how, client in holders(self.client_class, VIEW_ASSESSMENT):
            with self.subTest(how=how):
                page = client.get(self.url())
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Asha Rao")
                self.assertContains(page, "Bina Other")
                self.assertNotContains(page, SCORE_ASHA)
                self.assertNotContains(page, SCORE_BINA)
                # Withheld from the context, not just the HTML.
                self.assertTrue(all(result is None for _, result in page.context["rows"]))
                self.assertEqual(list(page.context["ineligible_results"]), [])

    def test_holders_of_view_studentresult_see_the_results(self):
        for how, client in holders(self.client_class, VIEW_ASSESSMENT, VIEW_RESULT):
            with self.subTest(how=how):
                page = client.get(self.url())
                self.assertContains(page, SCORE_ASHA)
                self.assertContains(page, SCORE_BINA)
                self.assertTrue(any(result is not None for _, result in page.context["rows"]))

    def test_the_result_sheet_route_still_needs_view_studentresult(self):
        for how, client in holders(self.client_class, VIEW_ASSESSMENT):
            with self.subTest(how=how):
                sheet = reverse("core:report-result-sheet", args=[self.ut1.pk])
                self.assertEqual(client.get(sheet).status_code, 403)


class TermPublicationPreviewTests(PublicationFixture, TestCase):
    def url(self):
        return reverse("core:term-publication", args=[self.term1.pk])

    def test_marks_and_remarks_need_view_studentresult(self):
        for how, client in holders(self.client_class, VIEW_PUBLICATION):
            with self.subTest(how=how):
                page = client.get(self.url(), {"section": self.six_a.pk})
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Asha Rao")  # the workflow lists who is covered
                for score in (SCORE_ASHA, SCORE_BINA, PREVIEW_ASHA, PREVIEW_BINA):
                    self.assertNotContains(page, score)
                self.assertNotContains(page, REMARK)
                for row in page.context["plan"]["rows"]:
                    self.assertEqual(row["content"]["entries"], [])
                    self.assertIsNone(row["content"]["remark"])

    def test_holders_of_view_studentresult_see_them(self):
        for how, client in holders(self.client_class, VIEW_PUBLICATION, VIEW_RESULT):
            with self.subTest(how=how):
                page = client.get(self.url(), {"section": self.six_a.pk})
                self.assertContains(page, PREVIEW_ASHA)
                self.assertContains(page, PREVIEW_BINA)
                self.assertContains(page, REMARK)

    def test_the_publish_token_still_works_for_a_publisher_without_marks_access(self):
        """Hiding marks must not change what is published or invalidate the confirm token."""
        full = self.plan()["token"]
        for how, client in holders(self.client_class, VIEW_PUBLICATION):
            with self.subTest(how=how):
                page = client.get(self.url(), {"section": self.six_a.pk})
                self.assertEqual(page.context["plan"]["token"], full)


class PublicationDetailTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.pub = next(p for p in self.publish() if p.student == self.asha)

    def url(self):
        return reverse("core:publication-detail", args=[self.pub.pk])

    def test_marks_and_remark_need_view_studentresult(self):
        for how, client in holders(self.client_class, VIEW_PUBLICATION):
            with self.subTest(how=how):
                page = client.get(self.url())
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Asha Rao")
                self.assertNotContains(page, SCORE_ASHA)
                self.assertNotContains(page, REMARK)
                self.assertEqual(list(page.context["entries"]), [])

    def test_holders_of_view_studentresult_see_them(self):
        for how, client in holders(self.client_class, VIEW_PUBLICATION, VIEW_RESULT):
            with self.subTest(how=how):
                page = client.get(self.url())
                self.assertContains(page, SCORE_ASHA)
                self.assertContains(page, REMARK)
                self.assertTrue(list(page.context["entries"]))

    def test_the_stale_list_stays_metadata_only(self):
        for how, client in holders(self.client_class, VIEW_PUBLICATION):
            with self.subTest(how=how):
                page = client.get(reverse("core:publications-stale"))
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, SCORE_ASHA)
        self.assertTrue(TermPublication.objects.filter(pk=self.pub.pk).exists())
