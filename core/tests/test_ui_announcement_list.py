"""Announcements list: search, filters, paging and phone cards (admin mobile audits, task 8)."""

import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import announcements
from core.models import ClassGrade, Section
from core.tests.test_phase7_announcements import CLASS, SECTION
from core.tests.test_ui_admin_phase3b import PreviewFixture

LIST = reverse("core:announcement-list")
FILTERED_EMPTY = "No notices match your search or filters."


def html(response):
    return response.content.decode()


def table_part(page):
    start = page.index('<div class="d-none d-md-block d-print-block">')
    return page[start:page.index('<ul class="erp-announcement-cards', start)]


def cards_part(page):
    start = page.index('<ul class="erp-announcement-cards')
    return page[start:page.index("</ul>", start)]


class ListTests(PreviewFixture, TestCase):
    def get(self, **params):
        return self.administrator.get(LIST, params)

    def test_more_than_100_notices_are_reachable(self):
        for number in range(101):
            self.notice(title=f"Notice {number:03d}")
        page = html(self.get(page=5))
        self.assertIn("Notice 000", page)
        self.assertNotIn("Notice 100", page)
        self.assertIn("Showing 101–101 of 101", page)

    def test_search_matches_title_and_body(self):
        self.notice(title="Sports Day", body="Bring water.")
        self.notice(title="Fees", body="Pay by the sports office.")
        self.notice(title="Holiday", body="School is closed.")
        page = html(self.get(q="sports"))
        self.assertIn("Sports Day", page)
        self.assertIn(">Fees<", page)
        self.assertNotIn("Holiday", page)

    def test_status_filter(self):
        self.notice(title="Still live")
        gone = self.notice(title="Taken back")
        announcements.withdraw(gone, actor=self.admin, reason="Wrong date")
        live = html(self.get(status="live"))
        self.assertIn("Still live", live)
        self.assertNotIn("Taken back", live)
        withdrawn = html(self.get(status="withdrawn"))
        self.assertIn("Taken back", withdrawn)
        self.assertNotIn("Still live", withdrawn)

    def test_audience_filter(self):
        self.notice(title="For everyone")
        self.notice(CLASS, class_grade=self.grade6, title="For grade six")
        page = html(self.get(audience="CLASS"))
        self.assertIn("For grade six", page)
        self.assertNotIn("For everyone", page)
        self.assertIn("Whole school", html(self.get()))

    def test_filter_survives_paging(self):
        for number in range(30):
            self.notice(title=f"Sports {number:02d}")
        self.notice(title="Other")
        page = html(self.get(q="sports", status="live"))
        self.assertIn("q=sports", page)
        self.assertRegex(page, r'href="\?[^"]*status=live[^"]*page=2"')
        second = html(self.get(q="sports", status="live", page=2))
        self.assertIn("Sports 00", second)
        self.assertNotIn(FILTERED_EMPTY, second)
        self.assertIn('value="sports"', second)
        self.assertIn('<option value="live" selected>', second)
        nothing = html(self.get(q="zzz", status="live", page=2))
        self.assertIn(FILTERED_EMPTY, nothing)

    def test_bad_filter_value_is_ignored(self):
        self.notice(title="Sports Day")
        for params in ({"status": "nonsense"}, {"audience": "x"}, {"sort": "bogus"}, {"page": "abc"},
                       {"page": "99"}):
            response = self.get(**params)
            self.assertEqual(response.status_code, 200, params)
            self.assertIn("Sports Day", html(response), params)
        self.assertNotIn(FILTERED_EMPTY, html(self.get(status="nonsense")))

    def test_filtered_empty_message(self):
        self.notice(title="Sports Day")
        page = html(self.get(q="zzz"))
        self.assertEqual(page.count(FILTERED_EMPTY), 2)  # table row and phone list
        self.assertIn(f'<a class="btn btn-outline-secondary btn-sm mt-2" href="{LIST}">Clear filters</a>', page)
        self.assertNotIn("No notices yet.", page)

    def test_true_empty_message_is_unchanged(self):
        page = html(self.get())
        self.assertIn("No notices yet.", page)
        self.assertNotIn(FILTERED_EMPTY, page)
        create = reverse("core:announcement-create")
        self.assertIn(f'<a class="btn btn-outline-primary btn-sm mt-2" href="{create}">Publish a notice</a>', page)

    def test_card_shows_title_date_audience_status(self):
        live = self.notice(CLASS, class_grade=self.grade6, title="Sports Day")
        gone = self.notice(SECTION, section=self.six_b, title="Old news")
        announcements.withdraw(gone, actor=self.admin, reason="Wrong date")
        cards = cards_part(html(self.get()))
        self.assertIn('role="list"', cards)
        self.assertEqual(cards.count('<li class="erp-announcement-card">'), 2)
        self.assertRegex(cards, rf'<a class="erp-announcement-card-title" href="{reverse("core:announcement-detail", args=[live.pk])}">Sports Day</a>')
        self.assertIn("Grade 6", cards)
        self.assertRegex(cards, r"\d{1,2} \w{3} \d{4}")
        self.assertIn("Live", cards)
        self.assertIn("Withdrawn", cards)

    def test_cards_are_hidden_when_printing(self):
        self.notice(title="Sports Day")
        page = html(self.get())
        self.assertIn('<div class="d-none d-md-block d-print-block">', page)
        self.assertRegex(page, r'<ul class="erp-announcement-cards d-md-none d-print-none" role="list">')
        self.assertIn("Sports Day", table_part(page))

    def test_query_count_does_not_grow_with_notices(self):
        self.notice(title="One")
        with CaptureQueriesContext(connection) as few:
            self.get()
        for number in range(10):
            self.notice(CLASS, class_grade=self.grade6, title=f"More {number}")
            self.notice(SECTION, section=self.six_b, title=f"Section {number}")
        with CaptureQueriesContext(connection) as many:
            self.get()
        self.assertEqual(len(many), len(few))


class AudienceSortTests(PreviewFixture, TestCase):
    """Grades sort by their stored position, not their name (Grade 10 would come before Grade 2)."""

    def setUp(self):
        super().setUp()
        self.grade2 = ClassGrade.objects.create(name="Grade 2", display_order=40)
        self.grade10 = ClassGrade.objects.create(name="Grade 10", display_order=50)
        self.two_a = Section.objects.create(class_grade=self.grade2, name="A")
        self.ten_a = Section.objects.create(class_grade=self.grade10, name="A")

    def titles(self, sort, audience):
        page = html(self.administrator.get(LIST, {"sort": sort, "audience": audience}))
        return re.findall(r'<th scope="row"[^>]*><a class="erp-row-link" href="[^"]+">([^<]+)</a></th>', table_part(page))

    def test_class_notices_sort_by_grade_position(self):
        self.notice(CLASS, class_grade=self.grade10, title="Ten")
        self.notice(CLASS, class_grade=self.grade2, title="Two")
        self.assertEqual(self.titles("audience", "CLASS"), ["Two", "Ten"])
        self.assertEqual(self.titles("-audience", "CLASS"), ["Ten", "Two"])

    def test_section_notices_sort_by_their_grade_position(self):
        self.notice(SECTION, section=self.ten_a, title="Ten A")
        self.notice(SECTION, section=self.two_a, title="Two A")
        self.assertEqual(self.titles("audience", "SECTION"), ["Two A", "Ten A"])
        self.assertEqual(self.titles("-audience", "SECTION"), ["Ten A", "Two A"])
