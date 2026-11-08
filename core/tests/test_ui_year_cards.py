import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear
from core.tests.test_authorization import AuthorizationClientsMixin

CARDS_OPEN = '<ul class="erp-year-cards d-print-none" role="list">'


class AcademicYearPhoneCardTests(AuthorizationClientsMixin, TestCase):
    """On screen each Academic Year is a card with its pages as menu rows; the table is for printing."""

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 3, 31)
        )
        self.url = reverse("core:academic-year-list")

    def cards(self, client=None):
        content = (client or self.administrator).get(self.url).content.decode()
        return content.split(CARDS_OPEN)[1]

    def test_table_is_for_print_and_cards_are_for_every_screen(self):
        page = self.administrator.get(self.url)
        self.assertContains(page, '<div class="d-none d-print-block">')
        self.assertContains(page, CARDS_OPEN)

    def test_card_shows_the_year_its_dates_and_saturdays(self):
        cards = self.cards()
        self.assertIn('<h2 class="erp-year-card-name">2026-27</h2>', cards)
        self.assertIn("1 Jun 2026 – 31 Mar 2027", cards)
        self.assertIn("Saturdays: Off", cards)

    def test_card_says_when_saturdays_are_instructional(self):
        self.year.saturdays_instructional = True
        self.year.save()
        self.assertIn("Saturdays: Instructional", self.cards())

    def test_card_has_every_year_page_link(self):
        cards = self.cards()
        for name in (
            "academic-year-calendar",
            "academic-year-terms",
            "academic-year-offerings",
            "academic-year-class-teachers",
            "academic-year-teacher-assignments",
            "academic-year-assignments",
            "academic-year-assessments",
            "academic-year-grading-scales",
        ):
            with self.subTest(page=name):
                self.assertIn(f'href="{reverse(f"core:{name}", args=[self.year.pk])}"', cards)

    def test_every_year_gets_its_own_card(self):
        AcademicYear.objects.create(
            name="2027-28", start_date=datetime.date(2027, 6, 1), end_date=datetime.date(2028, 3, 31)
        )
        page = self.administrator.get(self.url).content.decode()
        self.assertEqual(page.count('<li class="erp-year-card">'), 2)

    def test_card_links_follow_the_viewers_permissions(self):
        user = get_user_model().objects.create_user(username="terms-only", password="pass-12345")
        user.user_permissions.add(
            Permission.objects.get(codename="view_academicyear"),
            Permission.objects.get(codename="view_academicterm"),
        )
        client = self.client_class()
        client.login(username="terms-only", password="pass-12345")
        cards = self.cards(client)
        self.assertIn(f'href="{reverse("core:academic-year-terms", args=[self.year.pk])}"', cards)
        self.assertNotIn(f'href="{reverse("core:academic-year-calendar", args=[self.year.pk])}"', cards)

    def test_no_years_shows_the_empty_message_instead_of_cards(self):
        AcademicYear.objects.all().delete()
        page = self.administrator.get(self.url)
        self.assertContains(page, '<div class="erp-year-cards-empty d-print-none">')
        self.assertNotContains(page, '<ul class="erp-year-cards')
        self.assertContains(page, "No Academic Years yet.", count=2)

    def test_stylesheet_makes_card_links_easy_to_tap(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-link-list--menu .erp-link-row { min-height: 3.5rem; align-items: center; }", css)
