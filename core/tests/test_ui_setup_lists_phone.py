"""Subjects and Timetable lists show cards on phones; wider screens keep the tables.

Which of the two is visible is a Bootstrap breakpoint class, checked in a real browser;
these tests pin what each card says and which links it carries.
"""

import re
from datetime import date
from html import unescape

from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    ClassGrade,
    Section,
    Subject,
    TimetablePeriod,
    TimetableSlot,
)
from core.tests.phase4_fixtures import Phase4Fixture


def cards(html):
    region = re.search(r'<ul class="erp-setup-cards[^"]*"[^>]*>(.*?)\n</ul>', html, re.S)
    if region is None:
        return []
    return re.findall(r'<li class="erp-setup-card">(.*?)</li>', region.group(1), re.S)


def text_of(card):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", card)).split())


class SetupListsPhoneTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.force_login(self.admin)

    def make_period(self, sequence, label):
        return TimetablePeriod.objects.create(
            academic_year=self.year, sequence=sequence, label=label
        )

    def test_subject_card_shows_name_code_status_edit(self):
        Subject.objects.create(name="Zoology", code="ZOO", is_active=False)
        html = self.client.get(reverse("core:subject-list")).content.decode()
        card = next(text_of(c) for c in cards(html) if "Zoology" in c)
        self.assertIn("Code ZOO", card)
        self.assertIn("Inactive", card)
        self.assertIn("Edit Zoology", card)
        self.assertIn('class="d-none d-md-block d-print-block"', html)
        self.assertIn('role="list"', html)

    def test_subject_list_stays_alphabetical(self):
        Subject.objects.create(name="Art")
        names = [s.name for s in self.client.get(reverse("core:subject-list")).context["subjects"]]
        self.assertEqual(names, sorted(names))

    def test_timetable_index_links_are_separate_on_phones(self):
        html = self.client.get(reverse("core:timetable-index")).content.decode()
        card = next(c for c in cards(html) if "2026-27" in c)
        for name in ("timetable-periods", "timetable-sections", "timetable-issues"):
            self.assertEqual(
                len(re.findall(rf'<a [^>]*href="{reverse("core:" + name, args=[self.year.pk])}"', card)),
                1,
                name,
            )
        self.assertIn("0 periods", text_of(card))

    def test_section_card_says_grade_section_and_open_timetable(self):
        html = self.client.get(reverse("core:timetable-sections", args=[self.year.pk])).content.decode()
        found = [text_of(c) for c in cards(html)]
        self.assertTrue(found)
        self.assertTrue(any("Grade 6" in c and "Section A" in c and "Open timetable" in c for c in found))
        grid = reverse("core:timetable-grid", args=[self.year.pk, self.six_a.pk])
        self.assertIn(f'href="{grid}"', html)

    def test_sections_stay_in_grade_position_order(self):
        # Named so it sorts first alphabetically, positioned after Grade 6.
        late = ClassGrade.objects.create(name="Aardvark", display_order=99)
        z = Section.objects.create(class_grade=late, name="A")
        early = late
        AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=early, subject=self.maths_subject
        )
        response = self.client.get(reverse("core:timetable-sections", args=[self.year.pk]))
        self.assertEqual(list(response.context["sections"])[-1], z)

    def test_used_period_shows_in_use_and_no_delete_link(self):
        used = self.make_period(1, "P1")
        TimetableSlot.create(
            period=used, weekday=0, section=self.six_a, offering=self.maths,
            start_date=date(2026, 6, 1),
        )
        html = self.client.get(reverse("core:timetable-periods", args=[self.year.pk])).content.decode()
        self.assertIn("In use", html)
        self.assertNotIn(reverse("core:timetable-period-delete", args=[used.pk]), html)
        self.assertIn(reverse("core:timetable-period-update", args=[used.pk]), html)
        self.assertIn("In use", text_of(cards(html)[0]))

    def test_unused_period_shows_delete(self):
        free = self.make_period(1, "P1")
        html = self.client.get(reverse("core:timetable-periods", args=[self.year.pk])).content.decode()
        self.assertNotIn("In use", html)
        self.assertEqual(html.count(reverse("core:timetable-period-delete", args=[free.pk])), 2)

    def test_deleting_a_used_period_is_still_refused(self):
        used = self.make_period(1, "P1")
        TimetableSlot.create(
            period=used, weekday=0, section=self.six_a, offering=self.maths,
            start_date=date(2026, 6, 1),
        )
        response = self.client.post(
            reverse("core:timetable-period-delete", args=[used.pk]), follow=True
        )
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(TimetablePeriod.objects.filter(pk=used.pk).exists())

    def test_empty_states_say_what_to_do(self):
        html = self.client.get(reverse("core:timetable-periods", args=[self.year.pk])).content.decode()
        self.assertIn("erp-setup-cards-empty", html)
        self.assertIn("No periods yet.", html)
