"""The admin Attendance register list shows one card per register on phones.

Which of table or cards is visible is a Bootstrap breakpoint class, checked in a real browser;
these tests pin what each card says, the roster counts, and the status and today filters.
"""

import re
from datetime import date
from html import unescape

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import AcademicEnrollment, AttendanceRegister, AttendanceStatus, business_today
from core.tests.phase4_fixtures import Phase4Fixture


def cards_in(html):
    """Card text, whitespace collapsed, keyed by the link target."""
    region = re.search(r'<ul class="erp-register-cards[^"]*"[^>]*>(.*?)</ul>', html, re.S)
    if region is None:
        return {}
    cards = {}
    for body in re.findall(r'<li class="erp-register-card">(.*?)</li>', region.group(1), re.S):
        href = re.search(r'href="([^"]+)"', body).group(1)
        cards[href] = " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())
    return cards


class RegisterCardFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.url = reverse("core:attendance-register-list")
        self.client.login(username="admin", password="pass-12345")

    def register(self, on_date, section=None, *, marked=(), submit=False):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            section=section or self.six_a, date=on_date,
        )
        for enrollment in marked:
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.PRESENT)
        if submit:
            register.submit(actor=self.admin)
        return register

    def card(self, register, **params):
        html = self.client.get(self.url, params).content.decode()
        return cards_in(html).get(reverse("core:attendance-register-detail", args=[register.pk]))


class RosterCountTests(RegisterCardFixture, TestCase):
    def setUp(self):
        self.build()

    def test_roster_count_matches_eligible_enrollments(self):
        _, stays = self.make_student("Stays")
        student, moves = self.make_student("Moves")
        student.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_b,
            start_date=date(2026, 7, 10),
        )
        self.make_student("Joins", start=date(2026, 7, 8))
        early = self.register(date(2026, 7, 6), marked=[stays, moves])
        middle = self.register(date(2026, 7, 9))
        late = self.register(date(2026, 7, 20))
        other = self.register(date(2026, 7, 20), section=self.six_b)
        by_pk = {r.pk: r for r in self.client.get(self.url).context["registers"]}
        registers = (early, middle, late, other)
        for register in registers:
            self.assertEqual(
                by_pk[register.pk].roster_count, register.eligible_enrollments().count(),
                register.date,
            )
        self.assertEqual([by_pk[r.pk].roster_count for r in registers], [2, 3, 2, 1])
        self.assertEqual(by_pk[early.pk].marked_count, 2)

    def test_marked_count_ignores_entries_that_are_no_longer_on_the_roster(self):
        _, asha = self.make_student("Asha")
        register = self.register(date(2026, 7, 6), marked=[asha])
        AcademicEnrollment.objects.filter(pk=asha.pk).update(
            end_date=date(2026, 7, 1), status="COMPLETED"
        )
        row = next(r for r in self.client.get(self.url).context["registers"] if r.pk == register.pk)
        self.assertEqual((row.roster_count, row.marked_count), (0, 0))
        self.assertEqual(row.entry_count, 1)


class CardContentTests(RegisterCardFixture, TestCase):
    def setUp(self):
        self.build()
        self.enrollments = [self.make_student(f"Student {n}")[1] for n in range(6)]

    def test_draft_card_says_marked_x_of_y_and_unmarked(self):
        register = self.register(date(2026, 7, 6), marked=self.enrollments[:4])
        text = self.card(register)
        self.assertIn("Marked 4 of 6 · 2 unmarked", text)
        self.assertIn("Draft", text)
        self.assertIn("Grade 6", text)

    def test_submitted_card_says_submitted_x_of_y(self):
        register = self.register(date(2026, 7, 6), marked=self.enrollments, submit=True)
        text = self.card(register)
        self.assertIn("Submitted · 6 of 6", text)
        self.assertNotIn("unmarked", text)

    def test_cards_are_hidden_when_printing(self):
        self.register(date(2026, 7, 6))
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r'<div class="d-none d-md-block d-print-block">\s*<div class="erp-panel">')
        self.assertRegex(html, r'<ul class="erp-register-cards d-md-none d-print-none" role="list"')

    def test_empty_list_shows_one_message_per_view(self):
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r'<div class="erp-register-cards-empty d-md-none d-print-none">')
        self.assertEqual(html.count("No attendance registers yet."), 2)

    def test_query_count_does_not_grow_with_registers(self):
        self.register(date(2026, 7, 6))
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for day in range(7, 20):
            self.register(date(2026, 7, day), marked=self.enrollments[:2])
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))


class FilterTests(RegisterCardFixture, TestCase):
    def setUp(self):
        self.build()
        _, asha = self.make_student("Asha")
        self.draft = self.register(date(2026, 7, 6))
        self.done = self.register(date(2026, 7, 7), marked=[asha], submit=True)

    def pks(self, **params):
        return {r.pk for r in self.client.get(self.url, params).context["registers"]}

    def test_status_filter(self):
        self.assertEqual(self.pks(status="DRAFT"), {self.draft.pk})
        self.assertEqual(self.pks(status="SUBMITTED"), {self.done.pk})
        self.assertEqual(self.pks(), {self.draft.pk, self.done.pk})

    def test_today_link(self):
        todays = self.register(business_today())
        html = self.client.get(self.url).content.decode()
        self.assertIn('href="?today=1"', html)
        self.assertEqual(self.pks(today="1"), {todays.pk})

    def test_filter_with_no_matches_says_so(self):
        html = self.client.get(self.url, {"today": "1"}).content.decode()
        self.assertEqual(html.count("No attendance registers match these filters."), 2)
        self.assertNotIn("No attendance registers yet.", html)

    def test_bad_filter_value_is_ignored(self):
        for params in ({"status": "bogus"}, {"today": "zzz"}, {"status": "bogus", "page": "x"}):
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                {r.pk for r in response.context["registers"]}, {self.draft.pk, self.done.pk}
            )

    def test_filter_survives_paging(self):
        for day in range(1, 29):
            self.register(date(2026, 8, day))
        first = self.client.get(self.url, {"status": "DRAFT"})
        self.assertEqual(len(first.context["registers"]), 25)
        self.assertIn("status=DRAFT", first.context["table"].next_url)
        second = self.client.get(self.url, {"status": "DRAFT", "page": 2})
        self.assertEqual(len(second.context["registers"]), 4)
        html = second.content.decode()
        self.assertIn('<option value="DRAFT" selected>', html)
        self.assertNotIn("No attendance registers", html)
        beyond = self.client.get(self.url, {"status": "SUBMITTED", "page": 2})
        self.assertEqual(beyond.status_code, 200)
        self.assertEqual({r.pk for r in beyond.context["registers"]}, {self.done.pk})
