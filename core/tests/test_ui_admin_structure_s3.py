"""S3: Assessments & Results in the sidebar (year-scoped links) and collapsible sidebar groups."""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.academic_years import current_academic_year
from core.models import AcademicYear
from core.navigation import office_nav
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()
TODAY = datetime.date(2026, 10, 24)


def make_year(name, start, end):
    return AcademicYear.objects.create(name=name, start_date=start, end_date=end)


def links(groups):
    return {link["label"]: link for group in groups for link in group["links"]}


class CurrentAcademicYearTests(TestCase):
    def test_none_when_no_year_exists(self):
        self.assertIsNone(current_academic_year(TODAY))

    def test_prefers_the_year_containing_today_over_a_future_year(self):
        current = make_year("2026-27", datetime.date(2026, 6, 1), datetime.date(2027, 3, 31))
        make_year("2027-28", datetime.date(2027, 6, 1), datetime.date(2028, 3, 31))
        self.assertEqual(current_academic_year(TODAY), current)

    def test_falls_back_to_the_latest_year_when_none_contains_today(self):
        make_year("2024-25", datetime.date(2024, 6, 1), datetime.date(2025, 3, 31))
        latest = make_year("2025-26", datetime.date(2025, 6, 1), datetime.date(2026, 3, 31))
        self.assertEqual(current_academic_year(TODAY), latest)


class OfficeNavTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.year = make_year("2026-27", datetime.date(2026, 6, 1), datetime.date(2027, 3, 31))

    def test_group_titles_and_order(self):
        titles = [g["title"] for g in office_nav(self.superuser_client_user(), "", year=self.year)]
        self.assertEqual(
            titles,
            ["Home", "School setup", "Admissions", "Daily", "Assessments & Results", "Access and security"],
        )

    def superuser_client_user(self):
        return User.objects.get(username="root")

    def test_year_links_open_the_current_year(self):
        found = links(office_nav(self.superuser_client_user(), "", year=self.year))
        y = self.year.pk
        self.assertEqual(found["Assessments"]["url"], reverse("core:academic-year-assessments", args=[y]))
        self.assertEqual(found["Subject/Section results"]["url"],
                         reverse("core:report-subject-section-results", args=[y]))
        self.assertEqual(found["Grading scales"]["url"], reverse("core:academic-year-grading-scales", args=[y]))
        self.assertEqual(found["Stale publications"]["url"], reverse("core:publications-stale"))

    def test_year_links_are_hidden_without_a_year_but_stale_publications_stay(self):
        found = links(office_nav(self.superuser_client_user(), "", year=None))
        for label in ("Assessments", "Subject/Section results", "Grading scales"):
            self.assertNotIn(label, found)
        self.assertIn("Stale publications", found)

    def test_links_follow_the_users_permissions(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_assessment"))
        found = links(office_nav(User.objects.get(pk=user.pk), "", year=self.year))
        self.assertIn("Assessments", found)
        self.assertNotIn("Grading scales", found)
        self.assertNotIn("Subject/Section results", found)

    def test_active_group_is_open_and_badges_total(self):
        groups = office_nav(self.superuser_client_user(), "student-list", counts={
            "core:notifications-to-send": 3, "core:publications-stale": 2,
        }, year=self.year)
        by_title = {g["title"]: g for g in groups}
        self.assertTrue(by_title["Home"]["open"])
        self.assertTrue(by_title["Admissions"]["open"])
        self.assertFalse(by_title["Daily"]["open"])
        self.assertEqual(by_title["Daily"]["badge"], 3)
        self.assertEqual(by_title["Assessments & Results"]["badge"], 2)
        self.assertEqual(by_title["Admissions"]["badge"], 0)


class SidebarPageTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.year = make_year("2026-27", datetime.date(2026, 6, 1), datetime.date(2027, 3, 31))

    def active(self, response):
        return [l["label"] for g in response.context["office_nav"] for l in g["links"] if l["active"]]

    def test_year_scoped_pages_highlight_their_sidebar_link(self):
        y = self.year.pk
        for name, url, label in (
            ("assessments", reverse("core:academic-year-assessments", args=[y]), "Assessments"),
            ("grading", reverse("core:academic-year-grading-scales", args=[y]), "Grading scales"),
            ("results", reverse("core:report-subject-section-results", args=[y]), "Subject/Section results"),
        ):
            with self.subTest(page=name):
                response = self.administrator.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.active(response), [label])

    def test_sidebar_renders_collapsible_groups_open_only_where_needed(self):
        page = self.administrator.get(
            reverse("core:academic-year-assessments", args=[self.year.pk])
        ).content.decode()
        self.assertIn('<details class="erp-nav-group" open data-erp-nav-group="Assessments &amp; Results"', page)
        self.assertIn('<details class="erp-nav-group" data-erp-nav-group="Daily">', page)
        self.assertIn('<summary class="erp-nav-heading">Daily', page)
        self.assertIn(f'href="{reverse("core:academic-year-grading-scales", args=[self.year.pk])}"', page)

    def test_sidebar_has_no_year_links_before_a_year_exists(self):
        AcademicYear.objects.all().delete()
        page = self.administrator.get(reverse("core:admin-overview")).content.decode()
        self.assertNotIn(">Assessments<", page)
        self.assertIn("Stale publications", page)

    def test_teacher_and_guardian_shells_have_no_office_groups(self):
        response = self.non_admin.get(reverse("core:my-home"))
        self.assertNotContains(response, "erp-nav-group", status_code=response.status_code)
