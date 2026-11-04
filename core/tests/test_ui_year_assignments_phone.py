"""Academic Year assignment pages and Terms on phones: cards below 768px, the table for wide screens and print.

Which layout shows is a Bootstrap breakpoint class, checked in a real browser; these tests pin what
each card says, which action is primary, the overview summary counts and the copy page's empty state.
"""

import re
from datetime import date
from html import unescape
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format

from core import assignments
from core.tests.test_phase5_assignment_workflows import TODAY, AssignmentFixture

CARDS_OPEN = '<ul class="erp-assign-cards d-md-none d-print-none" role="list">'
TERM_CARDS_OPEN = '<ul class="erp-term-cards d-md-none d-print-none" role="list">'
TABLE_WRAP = '<div class="d-none d-md-block d-print-block">'
CSS = Path(__file__).resolve().parents[2] / "static" / "css" / "erp.css"


def text_of(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def cards_in(page, opener=CARDS_OPEN, item='<li class="erp-assign-card', occurrence=1):
    """The HTML of each card in the occurrence-th card list on the page."""
    region = page.content.decode().split(opener)[occurrence].split("</ul>\n", 1)[0]
    return region.split(item)[1:]


class AssignmentCardTests(AssignmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.iyer, self.maths, self.six_a)

    def test_assignment_cards_show_section_subject_teacher_date_and_actions(self):
        page = self.client.get(reverse("core:academic-year-teacher-assignments", args=[self.year.pk]))
        self.assertContains(page, CARDS_OPEN)
        card = next(c for c in cards_in(page) if "Mathematics" in text_of(c))
        words = text_of(card)
        self.assertIn("Grade 6 A", words)
        self.assertIn("iyer", words)
        self.assertIn(date_format(self.year.start_date), words)
        # Reassign is the main action; End is a plain secondary link, never a button.
        self.assertRegex(card, r'<a class="btn btn-outline-primary btn-sm[^"]*" href="[^"]*">Reassign')
        end = re.search(r'<a class="([^"]*)" href="[^"]*/end/">End', card)
        self.assertIsNotNone(end)
        self.assertNotIn("btn", end.group(1))
        self.assertIn("erp-assign-secondary", end.group(1))

    def test_class_teacher_cards_show_section_teacher_date_and_end_as_secondary(self):
        page = self.client.get(reverse("core:academic-year-class-teachers", args=[self.year.pk]))
        cards = cards_in(page)
        card = next(c for c in cards if "Grade 6 A" in text_of(c))
        words = text_of(card)
        self.assertIn("rao", words)
        self.assertIn(date_format(date(2026, 6, 1)), words)
        self.assertRegex(card, r'<a class="btn btn-outline-primary btn-sm[^"]*" href="[^"]*">Replace')
        end = re.search(r'<a class="([^"]*)" href="[^"]*/end/">End', card)
        self.assertIsNotNone(end)
        self.assertIn("erp-assign-secondary", end.group(1))
        empty = next(c for c in cards if "Grade 6 B" in text_of(c))
        self.assertIn("No class teacher", text_of(empty))
        self.assertIn(">Assign", empty)
        self.assertNotIn(">End", empty)

    def test_overview_cards_flag_gaps_and_link_to_the_teacher(self):
        page = self.client.get(reverse("core:academic-year-assignments", args=[self.year.pk]))
        self.assertEqual(page.content.decode().count(CARDS_OPEN), 2)
        class_cards = cards_in(page, occurrence=1)
        self.assertIn(f'href="{reverse("core:teacher-load", args=[self.rao.pk])}"', class_cards[0])
        self.assertIn("No class teacher", text_of(class_cards[1]))
        subject_cards = cards_in(page, occurrence=2)
        self.assertIn("No teacher", text_of(next(c for c in subject_cards if " B" in text_of(c))))

    def test_cards_are_hidden_when_printing(self):
        for name in ("academic-year-teacher-assignments", "academic-year-class-teachers",
                     "academic-year-assignments", "academic-year-terms"):
            with self.subTest(page=name):
                html = self.client.get(reverse(f"core:{name}", args=[self.year.pk])).content.decode()
                self.assertIn(TABLE_WRAP, html)
                self.assertIn(' d-md-none d-print-none" role="list"', html)
                self.assertNotRegex(html, r'<ul class="erp-(?:assign|term)-cards"')

    def test_long_names_wrap_in_cards(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-assign-card-teacher[^{]*\{[^}]*overflow-wrap: anywhere")


class TermsCardTests(AssignmentFixture, TestCase):
    def test_terms_card_makes_publish_primary(self):
        page = self.client.get(reverse("core:academic-year-terms", args=[self.year.pk]))
        self.assertContains(page, TERM_CARDS_OPEN)
        card = cards_in(page, TERM_CARDS_OPEN, '<li class="erp-term-card">')[0]
        words = text_of(card)
        self.assertIn("Term 1", words)
        self.assertIn(date_format(date(2026, 6, 1)), words)
        publish = reverse("core:term-publication", args=[self.term1.pk])
        self.assertRegex(card, rf'<a class="btn btn-primary btn-sm[^"]*" href="{publish}">Publish to guardians')
        update = reverse("core:term-update", args=[self.term1.pk])
        edit = re.search(rf'<a class="([^"]*)" href="{update}">Edit', card)
        self.assertIsNotNone(edit)
        self.assertNotIn("btn-primary", edit.group(1))
        self.assertIn(">Remarks", card)


class OverviewSummaryTests(AssignmentFixture, TestCase):
    def test_overview_summary_counts(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.iyer, self.maths, self.six_a)
        self.assign(self.iyer, self.sanskrit, self.six_b)
        data = assignments.overview(self.year, TODAY)
        # Sections: 6A has a class teacher, 6B none. Slots: Maths 6A and Sanskrit 6B are held, Maths 6B is not.
        self.assertEqual(data["summary"], {
            "sections_without_class_teacher": 1,
            "offerings_without_teacher": 1,
            "active_class_teachers": 1,
            "active_subject_teachers": 1,
        })

    def test_inactive_holders_are_not_counted_as_active(self):
        self.class_teacher(self.rao, self.six_a)
        self.rao.is_active = False
        self.rao.save()
        self.assertEqual(assignments.overview(self.year, TODAY)["summary"]["active_class_teachers"], 0)

    def test_summary_shows_on_the_page_for_every_width(self):
        self.class_teacher(self.rao, self.six_a)
        page = self.client.get(reverse("core:academic-year-assignments", args=[self.year.pk]))
        self.assertContains(page, '<dl class="erp-assign-summary">')
        self.assertEqual(page.context["summary"]["sections_without_class_teacher"], 1)


class CopyPageTests(AssignmentFixture, TestCase):
    def test_copy_page_with_no_other_year_says_so(self):
        self.next_year.delete()
        page = self.client.get(reverse("core:assignment-copy", args=[self.year.pk]))
        self.assertContains(page, "No other academic year is available to copy from.")
        self.assertNotContains(page, "<select")
        self.assertNotContains(page, "Choose an Academic Year to copy from.")

    def test_copy_page_with_another_year_keeps_the_select(self):
        page = self.client.get(reverse("core:assignment-copy", args=[self.next_year.pk]))
        self.assertContains(page, "<select")
        self.assertNotContains(page, "No other academic year is available")
