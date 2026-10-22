"""UI-D1-2A: school configuration lists adopt the shared panel; data, order and access unchanged."""

import datetime
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicSubjectOfferingSection,
    AcademicTerm,
    AcademicYear,
    ClassGrade,
    Section,
    Subject,
)
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()


class SchoolConfigurationListsFixture(AuthorizationClientsMixin):
    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 3, 31)
        )
        self.class_two = ClassGrade.objects.create(name="Class 2")
        self.class_one = ClassGrade.objects.create(name="Class 1")
        self.one_a = Section.objects.create(class_grade=self.class_one, name="A")
        self.one_b = Section.objects.create(class_grade=self.class_one, name="B")
        self.english = Subject.objects.create(name="English", code="ENG")
        self.drawing = Subject.objects.create(name="Drawing", code="")
        self.sanskrit = Subject.objects.create(name="Sanskrit", code="SAN", is_active=False)
        # Created out of display order on purpose: the page must keep the model's ordering.
        self.term_two = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 2", display_order=2,
            start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 1, 15),
        )
        self.term_one = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", display_order=1,
            start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2026, 9, 30),
        )
        self.eng_offer = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.class_one, subject=self.english, display_order=2)
        self.draw_offer = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.class_one, subject=self.drawing, display_order=1)
        AcademicSubjectOfferingSection.objects.create(offering=self.draw_offer, section=self.one_a)

    def viewer_client(self, *codenames):
        user = User.objects.create_user(username="cfg-viewer", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="cfg-viewer", password="pass-12345")
        return client

    def urls(self):
        return {
            "classes": reverse("core:class-grade-list"),
            "subjects": reverse("core:subject-list"),
            "terms": reverse("core:academic-year-terms", args=[self.year.pk]),
            "offerings": reverse("core:academic-year-offerings", args=[self.year.pk]),
        }


class SharedPatternTests(SchoolConfigurationListsFixture, TestCase):
    def test_every_page_uses_header_panel_and_labelled_scroll_region(self):
        labels = {"classes": "Classes/Grades", "subjects": "Subjects", "terms": "Terms",
                  "offerings": "Subjects offered"}
        for key, url in self.urls().items():
            with self.subTest(page=key):
                content = self.administrator.get(url).content.decode()
                self.assertIn('class="erp-page-header"', content)
                self.assertIn("School setup", content)
                self.assertEqual(content.count("<h1"), 1)
                self.assertIn('class="erp-panel"', content)
                self.assertIn(f'role="region" aria-label="{labels[key]}" tabindex="0"', content)
                self.assertNotIn("<th>", content.split("<main")[1])  # every header is scope="col"
                self.assertIn('scope="col"', content)

    def test_primary_actions_sit_in_the_header_with_existing_targets(self):
        pages = {
            "classes": (reverse("core:class-grade-create"), "Create Class/Grade"),
            "subjects": (reverse("core:subject-create"), "Add Subject"),
            "terms": (reverse("core:term-create", args=[self.year.pk]), "Add Term"),
            "offerings": (reverse("core:offering-create", args=[self.year.pk]), "Offer a Subject"),
        }
        urls = self.urls()
        for key, (target, label) in pages.items():
            with self.subTest(page=key):
                content = self.administrator.get(urls[key]).content.decode()
                header = content.split('class="erp-page-header-actions"')[1].split("</div>")[0]
                self.assertIn(f'href="{target}">{label}</a>', header)

    def test_view_only_user_sees_data_but_no_write_actions(self):
        viewer = self.viewer_client("view_classgrade", "view_subject", "view_academicterm",
                                    "view_academicsubjectoffering", "view_section", "view_academicyear")
        for key, url in self.urls().items():
            with self.subTest(page=key):
                response = viewer.get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertNotIn("erp-page-header-actions", content)
                for write in ("-create", "/edit/", "term-publication", "remarks", "Publish to guardians"):
                    self.assertNotIn(write, content.split("<main")[1])
        self.assertContains(viewer.get(self.urls()["terms"]), "Term 1")
        self.assertContains(viewer.get(self.urls()["subjects"]), "English")


class ClassGradeListTests(SchoolConfigurationListsFixture, TestCase):
    def test_rows_keep_model_order_detail_links_and_real_section_counts(self):
        content = self.administrator.get(self.urls()["classes"]).content.decode()
        self.assertLess(content.index("Class 1"), content.index("Class 2"))
        self.assertIn(f'href="{reverse("core:class-grade-detail", args=[self.class_one.pk])}"', content)
        self.assertRegex(content, r"Class 1</a></td>\s*<td class=\"text-nowrap\">2</td>")
        self.assertRegex(content, r"Class 2</a></td>\s*<td class=\"text-nowrap\">0</td>")


class SubjectListTests(SchoolConfigurationListsFixture, TestCase):
    def test_status_is_text_not_colour_only_and_blank_codes_are_announced(self):
        content = self.administrator.get(self.urls()["subjects"]).content.decode()
        self.assertEqual(len(re.findall(r"Status: </span>Active", content)), 2)
        self.assertEqual(len(re.findall(r"Status: </span>Inactive", content)), 1)
        self.assertIn('<span class="visually-hidden">No code</span>', content)
        self.assertLess(content.index("Drawing"), content.index("English"))  # name order kept

    def test_edit_link_is_named_and_points_at_the_existing_route(self):
        content = self.administrator.get(self.urls()["subjects"]).content.decode()
        self.assertIn(f'href="{reverse("core:subject-update", args=[self.english.pk])}">Edit'
                      '<span class="visually-hidden"> English</span>', content)


class TermListTests(SchoolConfigurationListsFixture, TestCase):
    def test_terms_stay_in_explicit_order_with_whole_date_tokens(self):
        content = self.administrator.get(self.urls()["terms"]).content.decode()
        self.assertLess(content.index("Term 1"), content.index("Term 2"))
        self.assertIn('<td class="text-nowrap">1 Jun 2026</td>', content)
        self.assertIn('<td class="text-nowrap">30 Sep 2026</td>', content)
        self.assertNotIn("Published", content)  # no invented publication status

    def test_row_actions_are_gated_and_name_their_term(self):
        content = self.administrator.get(self.urls()["terms"]).content.decode()
        self.assertIn(reverse("core:term-update", args=[self.term_one.pk]), content)
        self.assertIn(reverse("core:term-publication", args=[self.term_one.pk]), content)
        self.assertIn(reverse("core:term-remarks", args=[self.term_one.pk]), content)
        self.assertIn('Remarks<span class="visually-hidden">: Term 1</span>', content)

    def test_publication_only_user_gets_only_that_link(self):
        client = self.viewer_client("view_academicterm", "view_termpublication", "view_academicyear")
        content = client.get(self.urls()["terms"]).content.decode()
        self.assertIn(reverse("core:term-publication", args=[self.term_one.pk]), content)
        self.assertNotIn(reverse("core:term-update", args=[self.term_one.pk]), content)
        self.assertNotIn(reverse("core:term-remarks", args=[self.term_one.pk]), content)


class OfferingListTests(SchoolConfigurationListsFixture, TestCase):
    def test_report_card_order_and_section_scope_are_unchanged(self):
        content = self.administrator.get(self.urls()["offerings"]).content.decode()
        # Same class: display_order 1 (Drawing) before 2 (English), not creation order.
        self.assertLess(content.index("Drawing"), content.index("English (ENG)"))
        self.assertIn('<td class="text-nowrap">1</td>', content)
        self.assertIn('<span class="text-nowrap">A</span>', content)   # Drawing: Section A only
        self.assertIn('<span class="text-nowrap">All Sections</span>', content)  # English: all
        self.assertIn(reverse("core:offering-update", args=[self.eng_offer.pk]), content)

    def test_empty_year_keeps_its_message(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=datetime.date(2027, 6, 1), end_date=datetime.date(2028, 3, 31))
        response = self.administrator.get(reverse("core:academic-year-offerings", args=[other.pk]))
        self.assertContains(response, "No Subjects offered in this Academic Year yet.")

    def test_lookup_is_a_labelled_get_form_and_still_answers(self):
        url = self.urls()["offerings"]
        content = self.administrator.get(url).content.decode()
        self.assertIn('<form method="get" class="erp-toolbar erp-toolbar--inline" '
                      'aria-labelledby="offered-lookup-title">', content)
        self.assertIn('id="offered-lookup-title"', content)
        self.assertIn('<label for="id_section">', content)
        self.assertIn('<label for="id_term">', content)
        answered = self.administrator.get(url, {"section": self.one_b.pk, "term": self.term_one.pk})
        self.assertContains(answered, "<li>English (ENG)</li>", html=False)
        self.assertNotContains(answered, "<li>Drawing</li>")  # Drawing is Section A only

    def test_lookup_shows_validation_errors_without_javascript(self):
        response = self.administrator.get(self.urls()["offerings"], {"section": ""})
        self.assertContains(response, "This field is required.")


class StylesheetTests(TestCase):
    def test_offerings_floor_widths_exist(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css[css.index("UI-D1-2A: school configuration lists"):]
        self.assertIn(".erp-offerings-table td:nth-child(3) { min-width: 14rem; }", block)
