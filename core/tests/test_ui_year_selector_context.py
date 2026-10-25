"""UI-04: year switch helper and the year-selector context for the office header."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import URLPattern, URLResolver, get_resolver, resolve, reverse

from core.academic_years import (
    YEAR_SCOPED_ALLOW_LIST,
    YEAR_SCOPED_SECTION_PAGES,
    year_switch_url,
)
from core.models import TEACHERS_GROUP_NAME, AcademicYear, business_today
from core.tests.test_phase6_access_boundary import BoundaryFixture

User = get_user_model()
YEAR_PREFIX = "academic-years/<int:pk>/"

# Year-scoped URLs deliberately NOT in the allow-list: {"core:url-name": "one-line reason"}.
# Empty today: every academic-years/<int:pk>/ route is allow-listed or a section-level page.
EXCLUDED = {}


def _year_scoped_view_names():
    """Namespaced names of every core route under the academic-years/<int:pk>/ prefix."""
    found = set()

    def walk(patterns, prefix, namespace):
        for p in patterns:
            route = prefix + str(p.pattern)
            if isinstance(p, URLResolver):
                walk(p.url_patterns, route, p.namespace or namespace)
            elif isinstance(p, URLPattern) and namespace == "core" and route.startswith(YEAR_PREFIX):
                found.add(f"core:{p.name}")

    walk(get_resolver().url_patterns, "", None)
    return found


class YearScopedUrlCoverageTests(TestCase):
    def test_every_year_scoped_url_has_a_decision(self):
        names = _year_scoped_view_names()
        self.assertGreater(len(names), 20)  # the walk really found the routes
        decided = YEAR_SCOPED_ALLOW_LIST | set(YEAR_SCOPED_SECTION_PAGES) | set(EXCLUDED)
        self.assertEqual(sorted(names - decided), [], "new year-scoped URL needs a decision")

    def test_decided_names_are_real_year_scoped_routes(self):
        names = _year_scoped_view_names()
        self.assertEqual(sorted(YEAR_SCOPED_ALLOW_LIST - names), [])
        self.assertEqual(sorted(set(YEAR_SCOPED_SECTION_PAGES) - names), [])
        self.assertEqual(sorted(set(EXCLUDED) - names), [])

    def test_allow_listed_urls_only_need_the_year_pk(self):
        for name in sorted(YEAR_SCOPED_ALLOW_LIST):
            with self.subTest(name=name):
                self.assertTrue(reverse(name, kwargs={"pk": 1}))


class YearSwitchUrlTests(TestCase):
    def setUp(self):
        self.old = AcademicYear.objects.create(
            name="2025-2026", start_date="2025-06-01", end_date="2026-04-30"
        )
        self.new = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )

    def test_allow_listed_page_keeps_its_name_and_swaps_the_pk(self):
        match = resolve(reverse("core:academic-year-assessments", kwargs={"pk": self.new.pk}))
        self.assertEqual(
            year_switch_url(match, self.old),
            reverse("core:academic-year-assessments", kwargs={"pk": self.old.pk}),
        )

    def test_section_level_timetable_pages_open_the_years_sections_list(self):
        sections = reverse("core:timetable-sections", kwargs={"pk": self.old.pk})
        grid = resolve(reverse("core:timetable-grid", kwargs={"pk": self.new.pk, "section_pk": 7}))
        self.assertEqual(year_switch_url(grid, self.old), sections)
        slot = resolve(
            reverse(
                "core:timetable-slot-create",
                kwargs={"pk": self.new.pk, "section_pk": 7, "period_pk": 3, "weekday": 2},
            )
        )
        self.assertEqual(year_switch_url(slot, self.old), sections)

    def test_child_object_year_independent_and_missing_match_fall_back_to_the_list(self):
        listing = reverse("core:academic-year-list")
        for path in (
            reverse("core:assessment-detail", kwargs={"pk": 5}),
            reverse("core:grading-scale-detail", kwargs={"pk": 5}),
            reverse("core:term-update", kwargs={"pk": 5}),
            reverse("core:school-detail"),
            listing,
        ):
            with self.subTest(path=path):
                self.assertEqual(year_switch_url(resolve(path), self.old), listing)
        self.assertEqual(year_switch_url(None, self.old), listing)

    def test_query_string_is_dropped(self):
        path = reverse("core:academic-year-terms", kwargs={"pk": self.new.pk}) + "?x=1"
        self.assertNotIn("?", year_switch_url(resolve(path.split("?")[0]), self.old))


class AdminYearChoicesContextTests(TestCase):
    def setUp(self):
        today = business_today()
        self.past = AcademicYear.objects.create(
            name="2025-2026",
            start_date=today - timedelta(days=500),
            end_date=today - timedelta(days=200),
        )
        self.current = AcademicYear.objects.create(
            name="2026-2027",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
        )
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(self.admin)

    def ctx(self, url):
        return self.client.get(url).context

    def test_lists_years_newest_first_with_current_selected_off_a_year_page(self):
        c = self.ctx(reverse("core:academic-year-list"))
        self.assertEqual([y["name"] for y in c["year_choices"]], ["2026-2027", "2025-2026"])
        self.assertEqual([y["selected"] for y in c["year_choices"]], [True, False])
        listing = reverse("core:academic-year-list")
        self.assertEqual([y["url"] for y in c["year_choices"]], [listing, listing])
        self.assertFalse(c["year_is_scoped_page"])
        self.assertEqual(c["viewing_year_name"], "")
        self.assertTrue(c["viewing_year_is_current"])

    def test_year_page_selects_the_viewed_year_and_links_to_the_same_page(self):
        c = self.ctx(reverse("core:academic-year-terms", kwargs={"pk": self.past.pk}))
        self.assertEqual([y["name"] for y in c["year_choices"] if y["selected"]], ["2025-2026"])
        self.assertEqual(
            [y["url"] for y in c["year_choices"]],
            [
                reverse("core:academic-year-terms", kwargs={"pk": self.current.pk}),
                reverse("core:academic-year-terms", kwargs={"pk": self.past.pk}),
            ],
        )
        self.assertTrue(c["year_is_scoped_page"])

    def test_viewing_flag_false_for_past_year_true_for_current(self):
        past = self.ctx(reverse("core:academic-year-terms", kwargs={"pk": self.past.pk}))
        self.assertFalse(past["viewing_year_is_current"])
        self.assertEqual(past["viewing_year_name"], "2025-2026")
        now = self.ctx(reverse("core:academic-year-terms", kwargs={"pk": self.current.pk}))
        self.assertTrue(now["viewing_year_is_current"])
        self.assertEqual(now["viewing_year_name"], "2026-2027")

    def test_no_years_gives_empty_values(self):
        AcademicYear.objects.all().delete()
        c = self.ctx(reverse("core:academic-year-list"))
        self.assertEqual(c["year_choices"], [])
        self.assertEqual(c["viewing_year_name"], "")
        self.assertTrue(c["viewing_year_is_current"])
        self.assertFalse(c["year_is_scoped_page"])

    def test_at_most_one_extra_academic_year_query(self):
        with CaptureQueriesContext(connection) as before:
            self.client.get(reverse("core:academic-year-list"))
        with mock.patch("core.context_processors._year_selector", return_value={}):
            with CaptureQueriesContext(connection) as without:
                self.client.get(reverse("core:academic-year-list"))
        self.assertEqual(len(before.captured_queries) - len(without.captured_queries), 1)


class OtherUsersGetNoYearChoicesTests(BoundaryFixture, TestCase):
    def assert_no_selector(self, response):
        self.assertEqual(response.context["year_choices"], [])
        self.assertEqual(response.context["viewing_year_name"], "")
        self.assertTrue(response.context["viewing_year_is_current"])
        self.assertFalse(response.context["year_is_scoped_page"])

    def test_anonymous_guardian_and_teacher_get_nothing_and_no_selector_work(self):
        teacher = User.objects.create_user(username="rao-t", password="pass-12345")
        teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        teacher_client = self.client_class()
        teacher_client.force_login(teacher)
        cases = (
            ("anonymous", self.client_class(), reverse("login")),
            ("guardian", self.guardian_client(), reverse("portal:home")),
            ("teacher", teacher_client, reverse("core:my-home")),
        )
        with mock.patch("core.context_processors._year_selector") as selector:
            for label, client, url in cases:
                with self.subTest(user=label):
                    self.assert_no_selector(client.get(url))
            selector.assert_not_called()

    def test_anonymous_login_runs_no_academic_year_query(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client_class().get(reverse("login"))
        sql = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        self.assertNotIn("core_academicyear", sql)
