"""U4-3B: Guardian report-card list and assessment-first report card (snapshot only)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core import publication
from core.models import Assessment, ResultStatus, StudentResult
from core.portal import report_card_groups
from core.tests.test_u4_3a_subject_order import OrderFixture


def entry(label, on, order, subject="Maths"):
    return SimpleNamespace(
        assessment_label=label, assessment_date=on, display_order=order, subject_label=subject)


class GroupingHelperTests(SimpleTestCase):
    def test_latest_assessment_first_and_frozen_order_inside(self):
        rows = [
            entry("UT1", date(2026, 7, 15), 2, "Maths"),
            entry("UT2", date(2026, 8, 10), 3, "Telugu"),
            entry("UT1", date(2026, 7, 15), 0, "Telugu"),
            entry("UT2", date(2026, 8, 10), 1, "Maths"),
        ]
        groups = report_card_groups(rows)
        self.assertEqual([(g["label"], g["date"]) for g in groups],
                         [("UT2", date(2026, 8, 10)), ("UT1", date(2026, 7, 15))])
        self.assertEqual([r.subject_label for r in groups[0]["entries"]], ["Maths", "Telugu"])
        self.assertEqual([r.subject_label for r in groups[1]["entries"]], ["Telugu", "Maths"])

    def test_same_date_groups_are_ordered_by_frozen_order_not_name(self):
        rows = [entry("B quiz", date(2026, 8, 1), 5), entry("A quiz", date(2026, 8, 1), 9)]
        self.assertEqual([g["label"] for g in report_card_groups(rows)], ["B quiz", "A quiz"])

    def test_same_label_on_different_dates_is_one_group_with_the_latest_date(self):
        rows = [
            entry("Mid Term", date(2026, 9, 12), 2, "Mathematics"),
            entry("Mid Term", date(2026, 9, 10), 0, "Telugu"),
            entry("Mid Term", date(2026, 9, 11), 1, "English"),
        ]
        groups = report_card_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual((groups[0]["label"], groups[0]["date"]), ("Mid Term", date(2026, 9, 12)))
        self.assertEqual([r.subject_label for r in groups[0]["entries"]],
                         ["Telugu", "English", "Mathematics"])

    def test_groups_are_ordered_by_their_latest_contained_date(self):
        rows = [
            entry("UT1", date(2026, 7, 15), 0, "Telugu"),
            entry("UT1", date(2026, 9, 20), 1, "English"),  # pushes UT1 after Mid Term
            entry("Mid Term", date(2026, 9, 12), 2, "Telugu"),
        ]
        self.assertEqual([(g["label"], g["date"]) for g in report_card_groups(rows)],
                         [("UT1", date(2026, 9, 20)), ("Mid Term", date(2026, 9, 12))])

    def test_different_exact_labels_on_the_same_date_stay_separate(self):
        rows = [entry("Unit Test 1", date(2026, 8, 1), 0),
                entry("Unit test 1", date(2026, 8, 1), 1),   # not normalised
                entry("Unit Test 1 ", date(2026, 8, 1), 2)]  # not trimmed
        self.assertEqual(len(report_card_groups(rows)), 3)

    def test_groups_carry_no_derived_values(self):
        group = report_card_groups([entry("UT1", date(2026, 7, 15), 0)])[0]
        self.assertEqual(set(group), {"date", "label", "entries"})
        self.assertEqual(report_card_groups([]), [])


class CardFixture(OrderFixture):
    def setUp(self):
        super().setUp()
        # School order: Telugu, English, Mathematics (alphabetical would differ).
        self.order({"Telugu": 1, "English": 2, "Mathematics": 3})
        self.make_results()

    def add_result(self, offering, name, on, status=ResultStatus.MARKED, term=None):
        assessment = self.make_assessment(
            offering=offering, section=self.six_a, term=term, name=name, on=on, pass_mark="8")
        StudentResult.objects.create(
            assessment=assessment, academic_enrollment=self.asha_e, status=status,
            score=Decimal("10") if status == ResultStatus.MARKED else None,
            entered_by=self.rao)
        self.force_finalize(assessment)

    def make_results(self):
        # UT1 (15 Jul) already has Mathematics (15/20, no pass mark) from the base fixture.
        self.add_result(self.telugu, "UT1", date(2026, 7, 15))
        self.add_result(self.english, "UT1", date(2026, 7, 15))
        self.add_result(self.maths, "UT2", date(2026, 8, 10))
        self.add_result(self.telugu, "UT2", date(2026, 8, 10), status=ResultStatus.ABSENT)
        self.add_result(self.english, "UT2", date(2026, 8, 10))

    def asha_card(self, created=None):
        created = created if created is not None else self.publish()
        return next(p for p in created if p.student == self.asha)

    def card_url(self, card, grant=None):
        return reverse("portal:report-card", args=[(grant or self.asha_grant).public_id,
                                                   card.public_id])

    def list_url(self, grant=None):
        return reverse("portal:report-cards", args=[(grant or self.asha_grant).public_id])


class ReportCardListTests(CardFixture, TestCase):
    def publish_term2(self):
        self.add_result(self.maths, "Oct test", date(2026, 10, 5), term=self.term2)
        plan = publication.plan_publication(self.term2, self.six_a, ())
        return publication.confirm_publication(
            term=self.term2, section=self.six_a, include=(), token=plan["token"],
            actor=self.admin)

    def test_cards_are_newest_first_with_available_metadata(self):
        first = self.asha_card()
        second = self.asha_card(self.publish_term2())
        page = self.portal.get(self.list_url())
        self.assertEqual([p.pk for p in page.context["publications"]], [second.pk, first.pk])
        html = page.content.decode()
        self.assertLess(html.index("Term 2"), html.index("Term 1"))
        for text in ("2026-27", "Grade 6, Section A", "Published ", "View report card"):
            self.assertContains(page, text)
        self.assertContains(page, f'href="{self.card_url(first)}"')
        self.assertContains(page, f'href="{self.card_url(second)}"')

    def test_empty_state_is_honest(self):
        page = self.portal.get(self.list_url())
        self.assertContains(page, "No report cards have been published yet.")
        self.assertNotContains(page, "erp-rc-card")

    def test_only_currently_visible_snapshots_are_listed(self):
        card = self.asha_card()
        result = StudentResult.objects.filter(academic_enrollment=self.asha_e).first()
        publication.mark_stale_for_result(result, actor=self.admin)
        page = self.portal.get(self.list_url())
        self.assertEqual(page.context["publications"], [])
        self.assertEqual(self.portal.get(self.card_url(card)).status_code, 404)

    def test_other_students_cards_stay_inaccessible(self):
        created = self.publish()
        bina_card = next(p for p in created if p.student == self.bina)
        self.assertEqual(self.portal.get(self.list_url(self.bina_grant)).status_code, 404)
        self.assertEqual(self.portal.get(self.card_url(bina_card)).status_code, 404)
        self.assertEqual(
            self.portal.get(self.card_url(bina_card, self.bina_grant)).status_code, 404)


class ReportCardDetailTests(CardFixture, TestCase):
    def page(self, card=None):
        return self.portal.get(self.card_url(card or self.asha_card()))

    def test_assessments_latest_first_subjects_in_frozen_school_order(self):
        page = self.page()
        groups = page.context["groups"]
        self.assertEqual([g["label"] for g in groups], ["UT2", "UT1"])
        for group in groups:
            self.assertEqual([e.subject_label for e in group["entries"]],
                             ["Telugu", "English", "Mathematics"])
        html = page.content.decode()
        self.assertLess(html.index('id="rc-assessment-1"'), html.index('id="rc-assessment-2"'))

    def test_one_named_assessment_held_on_different_dates_renders_as_one_block(self):
        self.add_result(self.telugu, "Mid Term", date(2026, 9, 10))
        self.add_result(self.english, "Mid Term", date(2026, 9, 11))
        self.add_result(self.maths, "Mid Term", date(2026, 9, 12))
        page = self.page()
        groups = page.context["groups"]
        self.assertEqual([g["label"] for g in groups], ["Mid Term", "UT2", "UT1"])
        self.assertEqual(groups[0]["date"], date(2026, 9, 12))
        self.assertEqual([e.subject_label for e in groups[0]["entries"]],
                         ["Telugu", "English", "Mathematics"])
        self.assertContains(
            page, '<h2 id="rc-assessment-1" class="erp-rc-group-title">Mid Term</h2>')
        self.assertContains(page, '<p class="erp-rc-group-date">12 Sep 2026</p>', count=1)
        self.assertContains(page, ">Mid Term</h2>", count=1)

    def test_released_card_ignores_later_offering_order_changes(self):
        card = self.asha_card()
        before = [[e.subject_label for e in g["entries"]]
                  for g in self.page(card).context["groups"]]
        self.order({"Mathematics": 1, "English": 2, "Telugu": 3})
        after = [[e.subject_label for e in g["entries"]]
                 for g in self.page(card).context["groups"]]
        self.assertEqual(after, before)

    def test_values_come_from_the_snapshot_exactly(self):
        page = self.page()
        for text in ("10.00 / 20.00", "50.00%", "15.00 / 20.00", "75.00%", "Absent"):
            self.assertContains(page, text)
        self.assertContains(page, "<dt>Result</dt><dd>Pass</dd>")

    def test_absent_row_has_no_percentage(self):
        page = self.page()
        absent = next(e for e in page.context["entries"] if e.status == "ABSENT")
        self.assertIsNone(absent.percentage)
        html = page.content.decode()
        start = html.index('<h3 class="erp-rc-subject-name">Telugu</h3>')
        block = html[start:html.index("</li>", start)]
        self.assertIn("<dd>Absent</dd>", block)
        self.assertNotIn("Percentage", block)

    def test_not_graded_fallback_without_a_scale(self):
        self.assertContains(self.page(), "<dt>Grade</dt><dd>Not graded</dd>")

    def test_real_grades_replace_the_fallback_when_a_scale_was_frozen(self):
        bands = [["90", "A"], ["75", "B"], ["50", "C"], ["0", "D"]]
        Assessment.objects.filter(status=Assessment.Status.FINALIZED).update(
            grading_snapshot={"scale": "Standard", "bands": bands})
        page = self.page()
        self.assertContains(page, "<dd>B</dd>")  # 75%
        self.assertContains(page, "<dd>C</dd>")  # 50%

    def test_partial_notice_and_remark(self):
        self.make_assessment(name="UT3", on=date(2026, 9, 1))  # DRAFT, so incomplete
        created = self.publish(include=[self.asha.pk])
        page = self.page(self.asha_card(created))
        self.assertContains(page, "Some results for this Term are not yet published.")
        self.assertContains(page, "Steady progress.")
        self.assertContains(page, "Class teacher's remark")

    def test_pdf_action_points_at_this_publication_with_an_accessible_name(self):
        card = self.asha_card()
        page = self.page(card)
        pdf = reverse("portal:report-card-pdf", args=[self.asha_grant.public_id, card.public_id])
        self.assertContains(page, f'href="{pdf}"')
        self.assertContains(page, "Download PDF: Term 1 report card for Asha Rao")

    def test_no_totals_averages_ranks_or_weighting_are_introduced(self):
        page = self.page()
        for group in page.context["groups"]:
            self.assertEqual(set(group), {"date", "label", "entries"})
        html = page.content.decode()
        for forbidden in ("Total", "Average", "Rank", "Weighted", "Overall"):
            self.assertNotIn(forbidden, html)
        self.assertContains(
            page, "Each assessment is shown separately; there are no totals, weighting or ranks.")

    def test_phone_blocks_and_desktop_tables_share_one_semantic_structure(self):
        page = self.page()
        html = page.content.decode()
        self.assertEqual(html.count('class="erp-rc-subjects d-lg-none"'), 2)
        self.assertEqual(html.count('class="erp-rc-table d-none d-lg-table"'), 2)
        self.assertEqual(html.count('<th scope="col">Subject</th>'), 2)
        self.assertEqual(html.count('<caption class="visually-hidden">'), 2)
        self.assertContains(page, '<h2 id="rc-assessment-1" class="erp-rc-group-title">UT2</h2>')
        self.assertContains(page, '<h3 class="erp-rc-subject-name">Telugu</h3>')
        self.assertContains(page, "<dt>Result</dt><dd>Pass</dd>")  # spelled out, not colour
