"""The admin Students list shows one card per Student on phones; wider screens keep the table.

Which of the two is visible is a Bootstrap breakpoint class, checked in a real browser at
360/390/768px; these tests pin what each card says and the links it depends on.
"""

import re
from datetime import timedelta
from html import unescape

from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicYear,
    Applicant,
    ClassGrade,
    Guardian,
    RelationshipType,
    Section,
    Student,
    StudentGuardian,
    business_today,
)
from core.tests.test_authorization import AuthorizationClientsMixin


def admit(name):
    applicant = Applicant.objects.create(full_name=name)
    applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
    return applicant.progress_to_student()


def cards_in(html):
    """The text of each card, tags removed and whitespace collapsed, keyed by the link target."""
    region = re.search(r'<ul class="erp-student-cards[^"]*"[^>]*>(.*?)</ul>', html, re.S)
    if region is None:
        return {}
    cards = {}
    for body in re.findall(r'<li class="erp-student-card">(.*?)</li>', region.group(1), re.S):
        href = re.search(r'href="([^"]+)"', body).group(1)
        text = " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())
        cards[href] = text
    return cards


class StudentCardContentTests(AuthorizationClientsMixin, TestCase):
    url = reverse("core:student-list")

    def setUp(self):
        super().setUp()
        today = business_today()
        self.year = AcademicYear.objects.create(
            name="Current", start_date=today - timedelta(days=30), end_date=today + timedelta(days=30)
        )
        self.grade = ClassGrade.objects.create(name="Grade 5")
        self.section = Section.objects.create(class_grade=self.grade, name="A")

    def card_for(self, student):
        html = self.administrator.get(self.url).content.decode()
        return cards_in(html)[reverse("core:student-detail", args=[student.pk])]

    def test_placed_student_card_shows_everything_needed_to_identify_them(self):
        student = admit("Aarav Sharma")
        Student.objects.filter(pk=student.pk).update(admission_number="ADM-1042")
        student.enroll(
            academic_year=self.year, class_grade=self.grade, section=self.section,
            start_date=self.year.start_date,
        )
        mother = Guardian.objects.create(full_name="Priya Sharma")
        father = Guardian.objects.create(full_name="Rohan Sharma")
        StudentGuardian.objects.create(student=student, guardian=mother, relationship_type=RelationshipType.MOTHER)
        StudentGuardian.objects.create(student=student, guardian=father, relationship_type=RelationshipType.FATHER)

        card = self.card_for(student)

        self.assertIn("Aarav Sharma", card)
        self.assertIn("Active", card)
        self.assertIn("ADM-1042 · Grade 5 · A", card)
        self.assertIn("Priya Sharma (Mother)", card)
        self.assertIn("Rohan Sharma (Father)", card)

    def test_student_without_class_or_guardian_says_so_instead_of_blank(self):
        card = self.card_for(admit("Meera Nair"))

        self.assertIn("Not in a class", card)
        self.assertIn("No guardian", card)

    def test_with_no_current_year_a_card_does_not_claim_the_student_is_unplaced(self):
        AcademicYear.objects.all().delete()

        card = self.card_for(admit("Meera Nair"))

        self.assertNotIn("Not in a class", card)
        self.assertIn("No current year", card)

    def test_card_list_keeps_list_semantics_for_voiceover(self):
        admit("Aarav Sharma")
        html = self.administrator.get(self.url).content.decode()

        self.assertRegex(html, r'<ul class="erp-student-cards[^"]*" role="list">')

    def test_printing_shows_the_table_not_the_cards(self):
        admit("Aarav Sharma")
        html = self.administrator.get(self.url).content.decode()

        self.assertRegex(html, r'<div class="d-none d-md-block d-print-block">\s*<div class="erp-panel">')
        self.assertRegex(html, r'<ul class="erp-student-cards d-md-none d-print-none"')
        self.assertRegex(html, r'<nav class="erp-card-sort d-md-none d-print-none"')

    def test_printing_an_empty_list_shows_one_empty_message(self):
        html = self.administrator.get(self.url, {"q": "zzz-no-match"}).content.decode()

        self.assertRegex(html, r'<div class="erp-student-cards-empty d-md-none d-print-none">')

    def test_every_student_on_the_page_gets_a_card_and_the_rest_are_on_page_two(self):
        for index in range(30):
            admit(f"Student {index:02d}")

        first = cards_in(self.administrator.get(self.url).content.decode())
        second = cards_in(self.administrator.get(self.url, {"page": 2}).content.decode())

        self.assertEqual(len(first), 25)
        self.assertEqual(len(second), 5)
        self.assertFalse(set(first) & set(second))

    def test_wider_screens_keep_the_table(self):
        admit("Aarav Sharma")
        html = self.administrator.get(self.url).content.decode()

        self.assertRegex(html, r'<div class="d-none d-md-block[^"]*">\s*<div class="erp-panel">\s*<div class="erp-table-scroll"')
        self.assertRegex(html, r'<ul class="erp-student-cards d-md-none[^"]*"')


class StudentCardSortTests(AuthorizationClientsMixin, TestCase):
    url = reverse("core:student-list")

    def setUp(self):
        super().setUp()
        admit("Ravi Rao")

    def sort_nav(self, **params):
        html = self.administrator.get(self.url, params).content.decode()
        return re.search(r'<nav class="erp-card-sort[^"]*" aria-label="Sort students">(.*?)</nav>', html, re.S).group(1)

    def test_only_columns_that_can_sort_are_offered(self):
        nav = self.sort_nav()
        self.assertIn("Name", nav)
        self.assertIn("Status", nav)
        self.assertNotIn("Class", nav)
        self.assertNotIn("Section", nav)
        self.assertNotIn("Guardian", nav)

    def test_tapping_the_current_sort_reverses_it_and_marks_the_direction(self):
        nav = self.sort_nav()
        self.assertRegex(nav, r'<a href="\?sort=-name" aria-current="true">\s*Name')
        self.assertIn("ascending", nav)

        nav = self.sort_nav(sort="-name")
        self.assertRegex(nav, r'<a href="\?sort=name" aria-current="true">\s*Name')
        self.assertIn("descending", nav)

    def test_sort_links_keep_the_active_filters(self):
        nav = self.sort_nav(q="ravi", status="ACTIVE")
        self.assertIn("q=ravi&amp;status=ACTIVE&amp;sort=status", nav)


class StudentCardEmptyStateTests(AuthorizationClientsMixin, TestCase):
    url = reverse("core:student-list")

    def phone_empty_state(self, **params):
        html = self.administrator.get(self.url, params).content.decode()
        self.assertNotIn('<ul class="erp-student-cards', html)
        self.assertNotIn('aria-label="Sort students"', html)  # nothing to sort
        return re.search(r'<div class="erp-student-cards-empty[^"]*">(.*?)</div>', html, re.S).group(1)

    def test_no_match_offers_clear_filters(self):
        admit("Aarav Sharma")
        empty = self.phone_empty_state(q="zzz-no-match")
        self.assertIn("No students match these filters.", empty)
        self.assertIn(f'href="{self.url}"', empty)
        self.assertIn("Clear filters", empty)

    def test_no_students_at_all_points_to_applicants(self):
        empty = self.phone_empty_state()
        self.assertIn("No Students found.", empty)
        self.assertIn(reverse("core:applicant-list"), empty)
