"""UI-D1-5A: grading scales list, detail, band management presentation, create/edit forms.

Presentation only. These tests pin the page structure, permission-gated controls, that every
POST keeps its URL and fields, the band wording, the status badge text and the permission-aware
breadcrumbs (including that no breadcrumb reuses one model's pk for another model's route).
Grading calculations are covered by test_phase4_grading and are not retested here.
"""

import re
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core.breadcrumbs import breadcrumb_context
from core.models import AcademicYear, ClassGrade, GradeBoundary, GradingScale

User = get_user_model()

BANDS = [(80, "A"), (50, "B"), (0, "C")]


class ScaleFixture:
    def build(self):
        # Filler years first so that scale pks and year pks differ in every test.
        for index in range(3):
            AcademicYear.objects.create(
                name=f"Filler {index}",
                start_date=date(2020 + index, 6, 1),
                end_date=date(2021 + index, 3, 31),
            )
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        self.grade6 = ClassGrade.objects.create(name="Grade 6")
        self.grade7 = ClassGrade.objects.create(name="Grade 7")
        self.complete = self.scale("Standard", BANDS, [self.grade6])
        self.incomplete = self.scale("Draft scale", [(40, "Pass")], [self.grade7])
        self.empty = self.scale("Empty scale", [], [])
        admin = User.objects.create_user(username="admin", password="pass-12345")
        admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.list_url = reverse("core:academic-year-grading-scales", args=[self.year.pk])
        self.detail_url = reverse("core:grading-scale-detail", args=[self.complete.pk])

    def scale(self, name, bands, grades):
        scale = GradingScale.objects.create(academic_year=self.year, name=name)
        for minimum, label in bands:
            band = GradeBoundary(scale=scale, label=label, min_percentage=Decimal(minimum))
            band.full_clean()
            band.save()
        scale.set_class_grades(grades)
        return scale

    def client_with(self, *codenames):
        self._users = getattr(self, "_users", 0) + 1
        user = User.objects.create_user(username=f"u{self._users}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client


def html(response):
    return response.content.decode()


class ListPageTests(ScaleFixture, TestCase):
    def setUp(self):
        self.build()

    def test_header_table_and_badges(self):
        page = html(self.client.get(self.list_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Grading scales</h1>', page)
        self.assertIn("2026-27", page)
        self.assertIn('role="region" aria-label="Grading scales for 2026-27" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertIn('<th scope="col">Grade bands</th>', page)
        # Status is text in a badge, never colour alone.
        self.assertRegex(page, r"erp-status--finalized[^>]*><span[^>]*>Status: </span>Complete")
        self.assertRegex(page, r"erp-status--pending[^>]*><span[^>]*>Status: </span>Needs a band from 0%")
        self.assertIn("A &ge; 80.00%", page)
        self.assertIn(reverse("core:grading-scale-detail", args=[self.complete.pk]), page)

    def test_scale_with_no_bands_or_grades_shows_dashes(self):
        row = re.search(r"Empty scale.*?</tr>", html(self.client.get(self.list_url)), re.S).group(0)
        self.assertEqual(row.count("&mdash;"), 2)

    def test_empty_year(self):
        GradingScale.objects.all().delete()
        self.assertContains(self.client.get(self.list_url), "No grading scales yet.")

    def test_add_link_is_gated(self):
        create = reverse("core:grading-scale-create", args=[self.year.pk])
        self.assertContains(self.client.get(self.list_url), f'href="{create}"')
        _, viewer = self.client_with("view_gradingscale")
        page = html(viewer.get(self.list_url))
        self.assertNotIn(create, page)
        self.assertIn(self.complete.name, page)

    def test_context_is_unchanged(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.context["academic_year"], self.year)
        self.assertEqual(len(response.context["scales"]), 3)


class DetailPageTests(ScaleFixture, TestCase):
    def setUp(self):
        self.build()

    def test_header_and_band_table(self):
        page = html(self.client.get(self.detail_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Standard</h1>', page)
        self.assertIn(reverse("core:academic-year-grading-scales", args=[self.year.pk]), page)
        self.assertIn('aria-label="Grade bands for Standard"', page)
        self.assertIn('<th scope="col" class="erp-num">From</th>', page)
        self.assertIn("Applies to: Grade 6.", page)
        self.assertRegex(page, r"erp-status--finalized[^>]*><span[^>]*>Status: </span>Complete")
        self.assertNotIn("Add a band starting at 0%", page)

    def test_band_order_and_wording_are_kept(self):
        page = html(self.client.get(self.detail_url))
        self.assertIn("highest starting point at or below it", page)
        self.assertIn("Finalized assessments keep the bands they were finalized with", page)
        self.assertEqual(
            re.findall(r'<th scope="row" class="fw-semibold">(\w+)</th>', page),
            [b.label for b in self.complete.boundaries.all()],
        )

    def test_incomplete_scale_explains_what_is_missing(self):
        page = html(self.client.get(reverse("core:grading-scale-detail", args=[self.incomplete.pk])))
        self.assertIn("Add a band starting at 0%", page)
        self.assertRegex(page, r"erp-status--pending[^>]*><span[^>]*>Status: </span>Needs a band from 0%")

    def test_remove_keeps_post_and_adds_consequence_text(self):
        band = self.complete.boundaries.get(label="B")
        page = html(self.client.get(self.detail_url))
        remove = reverse("core:grade-boundary-delete", args=[band.pk])
        self.assertIn(f'method="post" action="{remove}"', page)
        self.assertIn("csrfmiddlewaretoken", page)
        self.assertIn("Remove takes effect at once and is not confirmed first", page)
        self.assertIn("band B from 50.00%", page)
        self.client.get(remove)  # GET never deletes
        self.assertTrue(GradeBoundary.objects.filter(pk=band.pk).exists())
        self.client.post(remove)
        self.assertFalse(GradeBoundary.objects.filter(pk=band.pk).exists())

    def test_add_band_form_posts_to_the_same_url_with_the_same_fields(self):
        page = html(self.client.get(self.detail_url))
        add = reverse("core:grade-boundary-create", args=[self.complete.pk])
        self.assertIn(f'action="{add}"', page)
        self.assertIn('name="min_percentage"', page)
        self.assertIn('name="label"', page)
        self.assertIn('for="id_min_percentage"', page)
        self.assertIn('for="id_label"', page)
        self.client.post(add, {"min_percentage": "65", "label": "B+"})
        self.assertEqual(self.complete.grade_for(70), "B+")

    def test_controls_are_gated_by_permission(self):
        edit = reverse("core:grading-scale-update", args=[self.complete.pk])
        add = reverse("core:grade-boundary-create", args=[self.complete.pk])
        _, viewer = self.client_with("view_gradingscale")
        page = html(viewer.get(self.detail_url))
        self.assertNotIn(edit, page)
        self.assertNotIn(add, page)
        self.assertNotIn("grade-boundary", page)
        self.assertNotIn("Remove", page)
        self.assertIn("Standard", page)
        for codename, needle in (
            ("change_gradingscale", edit),
            ("add_gradeboundary", add),
            ("delete_gradeboundary", "Remove"),
        ):
            _, client = self.client_with("view_gradingscale", codename)
            self.assertIn(needle, html(client.get(self.detail_url)), codename)

    def test_context_is_unchanged(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.context["scale"], self.complete)
        self.assertEqual(list(response.context["boundaries"]), list(self.complete.boundaries.all()))
        self.assertIn("boundary_form", response.context)


class FormPageTests(ScaleFixture, TestCase):
    def setUp(self):
        self.build()
        self.create_url = reverse("core:grading-scale-create", args=[self.year.pk])
        self.update_url = reverse("core:grading-scale-update", args=[self.complete.pk])

    def test_create_form_structure(self):
        page = html(self.client.get(self.create_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Add grading scale</h1>', page)
        self.assertIn("erp-required-legend", page)
        self.assertIn('for="id_name"', page)
        self.assertIn("<legend", page)
        self.assertIn('name="class_grades"', page)
        self.assertIn(f'value="{self.grade7.pk}"', page)
        self.assertIn(f'href="{self.list_url}"', page)  # Cancel

    def test_edit_form_prefills_and_cancels_to_the_list(self):
        page = html(self.client.get(self.update_url))
        self.assertIn('class="erp-page-title">Edit grading scale</h1>', page)
        self.assertIn('value="Standard"', page)
        self.assertRegex(page, r'value="%d"[^>]*checked' % self.grade6.pk)
        self.assertIn(f'href="{self.list_url}"', page)

    def test_blank_name_shows_summary_and_associated_error(self):
        response = self.client.post(self.create_url, {"name": "", "class_grades": []})
        page = html(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertIn('href="#id_name"', page)
        self.assertIn('id="id_name_error"', page)
        self.assertIn('aria-describedby="id_name_error"', page)
        self.assertIn('aria-invalid="true"', page)
        self.assertEqual(GradingScale.objects.count(), 3)

    def test_grade_already_taken_error_is_shown(self):
        page = html(self.client.post(self.create_url, {"name": "Second", "class_grades": [self.grade6.pk]}))
        self.assertIn("already uses Standard", page)
        self.assertEqual(GradingScale.objects.count(), 3)

    def test_duplicate_name_error_is_shown_and_summary_links_to_it(self):
        page = html(self.client.post(self.create_url, {"name": "Standard"}))
        self.assertIn("Another scale in this Academic Year has this name.", page)
        self.assertIn('href="#id_name"', page)

    def test_posts_still_save_and_redirect(self):
        response = self.client.post(self.create_url, {"name": "New", "class_grades": []})
        scale = GradingScale.objects.get(name="New")
        self.assertRedirects(response, reverse("core:grading-scale-detail", args=[scale.pk]))
        response = self.client.post(self.update_url, {"name": "Standard 2", "class_grades": [self.grade6.pk]})
        self.assertRedirects(response, self.detail_url)
        self.complete.refresh_from_db()
        self.assertEqual(self.complete.name, "Standard 2")


class AccessTests(ScaleFixture, TestCase):
    def setUp(self):
        self.build()

    def test_routes_keep_their_permission_outcomes(self):
        teacher = User.objects.create_user(username="rao", password="pass-12345")
        teacher.groups.add(Group.objects.get(name="Teachers"))
        teacher_client = self.client_class()
        teacher_client.login(username="rao", password="pass-12345")
        anonymous = self.client_class()
        urls = [
            self.list_url,
            self.detail_url,
            reverse("core:grading-scale-create", args=[self.year.pk]),
            reverse("core:grading-scale-update", args=[self.complete.pk]),
        ]
        for url in urls:
            self.assertEqual(teacher_client.get(url).status_code, 403, url)
            self.assertEqual(anonymous.get(url).status_code, 302, url)
            self.assertEqual(self.client.get(url).status_code, 200, url)
        _, viewer = self.client_with("view_gradingscale")
        self.assertEqual(viewer.get(urls[2]).status_code, 403)
        self.assertEqual(viewer.get(urls[3]).status_code, 403)


class BreadcrumbTests(ScaleFixture, TestCase):
    def setUp(self):
        self.build()

    def trail(self, url, user=None):
        return breadcrumb_context(resolve(url), user)

    def labels(self, context):
        return [c["label"] for c in context["breadcrumbs"]]

    def test_ids_are_distinct_in_this_fixture(self):
        self.assertNotEqual(self.year.pk, self.complete.pk)

    def test_list_trail(self):
        context = self.trail(self.list_url)
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Grading scales"])
        self.assertEqual(context["nav_section"], "academic-year-grading-scales")

    def test_create_links_back_to_the_year_scale_list_with_the_year_pk(self):
        context = self.trail(reverse("core:grading-scale-create", args=[self.year.pk]))
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Grading scales", "Add grading scale"])
        self.assertEqual(context["breadcrumbs"][2]["url"], self.list_url)

    def test_detail_and_edit_never_reuse_the_scale_pk_as_a_year_pk(self):
        for url, last in (
            (self.detail_url, "Grading scale"),
            (reverse("core:grading-scale-update", args=[self.complete.pk]), "Edit grading scale"),
        ):
            context = self.trail(url)
            self.assertEqual(self.labels(context), ["Overview", "Academic Years", last])
            wrong = reverse("core:academic-year-grading-scales", args=[self.complete.pk])
            self.assertNotIn(wrong, [c["url"] for c in context["breadcrumbs"]])

    def test_rendered_detail_page_links_back_with_the_year_id(self):
        page = html(self.client.get(self.detail_url))
        self.assertIn(f'href="{self.list_url}"', page)
        wrong = reverse("core:academic-year-grading-scales", args=[self.complete.pk])
        self.assertNotIn(f'href="{wrong}"', page)

    def test_parent_crumbs_follow_the_destination_permission(self):
        create = reverse("core:grading-scale-create", args=[self.year.pk])
        user, _ = self.client_with("view_school", "add_gradingscale")
        self.assertEqual(self.labels(self.trail(create, user)), ["Overview", "Add grading scale"])
        user, _ = self.client_with("view_school", "add_gradingscale", "view_academicyear")
        self.assertEqual(self.labels(self.trail(create, user)),
                         ["Overview", "Academic Years", "Add grading scale"])
        user, _ = self.client_with(
            "view_school", "add_gradingscale", "view_academicyear", "view_gradingscale"
        )
        self.assertEqual(
            self.labels(self.trail(create, user)),
            ["Overview", "Academic Years", "Grading scales", "Add grading scale"],
        )

    def test_overview_crumb_requires_view_school(self):
        user, _ = self.client_with("view_gradingscale", "view_academicyear")
        self.assertEqual(self.labels(self.trail(self.list_url, user)), ["Academic Years", "Grading scales"])
        user, _ = self.client_with("view_gradingscale")
        self.assertEqual(self.trail(self.list_url, user)["breadcrumbs"], [])
