"""Renaming a Class/Grade or Section, so a spelling mistake can be corrected.

These are reusable records, so a rename shows everywhere they appear. The record's
identity, position and parent stay as they were.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import ClassGrade, Section
from core.tests.test_authorization import AuthorizationClientsMixin


def client_with(client_class, *codenames):
    user = get_user_model().objects.create_user("limited", password="pass-12345")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = client_class()
    client.force_login(user)
    return client


class ClassGradeRenameTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.first = ClassGrade.objects.create(name="Nursery")
        self.grade = ClassGrade.objects.create(name="Grdae 1")
        self.url = reverse("core:class-grade-rename", args=[self.grade.pk])
        self.detail = reverse("core:class-grade-detail", args=[self.grade.pk])

    def test_page_shows_the_current_name_and_what_a_rename_affects(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, 'value="Grdae 1"')
        self.assertContains(response, "including past years")
        self.assertContains(response, "keep the old name")

    def test_rename_changes_the_name_and_returns_to_the_class(self):
        response = self.administrator.post(self.url, {"name": "Grade 1"})
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.name, "Grade 1")

    def test_rename_keeps_the_position_in_the_list(self):
        before = self.grade.display_order
        self.administrator.post(self.url, {"name": "Grade 1"})
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.display_order, before)

    def test_name_already_in_use_is_refused(self):
        response = self.administrator.post(self.url, {"name": "Nursery"})
        self.assertEqual(response.status_code, 200)
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.name, "Grdae 1")

    def test_refused_rename_still_titles_the_page_with_the_saved_name(self):
        response = self.administrator.post(self.url, {"name": "Nursery"})
        self.assertContains(response, "Rename Grdae 1")

    def test_capitals_alone_can_be_corrected(self):
        grade = ClassGrade.objects.create(name="ukg")
        url = reverse("core:class-grade-rename", args=[grade.pk])
        self.administrator.post(url, {"name": "UKG"})
        grade.refresh_from_db()
        self.assertEqual(grade.name, "UKG")

    def test_blank_name_is_refused(self):
        self.assertEqual(self.administrator.post(self.url, {"name": " "}).status_code, 200)
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.name, "Grdae 1")

    def test_saving_the_same_name_does_not_claim_a_rename(self):
        updated_at = self.grade.updated_at
        response = self.administrator.post(self.url, {"name": "Grdae 1"}, follow=True)
        self.assertContains(response, "name was not changed")
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.updated_at, updated_at)

    def test_viewing_only_cannot_rename_or_see_the_button(self):
        client = client_with(self.client_class, "view_classgrade")
        self.assertEqual(client.post(self.url, {"name": "Grade 1"}).status_code, 403)
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.name, "Grdae 1")
        self.assertNotContains(client.get(self.detail), self.url)

    def test_administrator_sees_the_rename_button(self):
        self.assertContains(self.administrator.get(self.detail), self.url)

    def test_unknown_class_is_not_found(self):
        url = reverse("core:class-grade-rename", args=[self.grade.pk + 999])
        self.assertEqual(self.administrator.get(url).status_code, 404)


class SectionRenameTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.grade = ClassGrade.objects.create(name="Grade 1")
        self.other_grade = ClassGrade.objects.create(name="Grade 2")
        self.section = Section.objects.create(class_grade=self.grade, name="Mornign")
        self.neighbour = Section.objects.create(class_grade=self.grade, name="B")
        self.url = reverse("core:section-rename", args=[self.section.pk])
        self.detail = reverse("core:class-grade-detail", args=[self.grade.pk])

    def test_page_names_the_class_the_section_belongs_to(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, 'value="Mornign"')
        self.assertContains(response, "Grade 1")

    def test_rename_changes_the_name_and_keeps_the_class(self):
        response = self.administrator.post(self.url, {"name": "Morning"})
        self.assertRedirects(response, self.detail, fetch_redirect_response=False)
        self.section.refresh_from_db()
        self.assertEqual(self.section.name, "Morning")
        self.assertEqual(self.section.class_grade, self.grade)

    def test_a_posted_class_cannot_move_the_section(self):
        self.administrator.post(self.url, {"name": "Morning", "class_grade": self.other_grade.pk})
        self.section.refresh_from_db()
        self.assertEqual(self.section.class_grade, self.grade)

    def test_name_used_in_the_same_class_is_refused(self):
        response = self.administrator.post(self.url, {"name": "B"})
        self.assertContains(response, "already exists")
        self.section.refresh_from_db()
        self.assertEqual(self.section.name, "Mornign")

    def test_name_used_only_in_another_class_is_allowed(self):
        Section.objects.create(class_grade=self.other_grade, name="Morning")
        self.administrator.post(self.url, {"name": "Morning"})
        self.section.refresh_from_db()
        self.assertEqual(self.section.name, "Morning")

    def test_refused_rename_still_titles_the_page_with_the_saved_name(self):
        self.assertContains(self.administrator.post(self.url, {"name": "B"}), "Rename Mornign")

    def test_viewing_only_cannot_rename_or_see_the_link(self):
        client = client_with(self.client_class, "view_classgrade", "view_section")
        self.assertEqual(client.post(self.url, {"name": "Morning"}).status_code, 403)
        self.assertNotContains(client.get(self.detail), self.url)

    def test_administrator_sees_a_link_that_names_the_section(self):
        response = self.administrator.get(self.detail)
        self.assertContains(response, self.url)
        self.assertContains(response, "Rename<span class=\"visually-hidden\"> section Mornign")

    def test_unknown_section_is_not_found(self):
        url = reverse("core:section-rename", args=[self.section.pk + 999])
        self.assertEqual(self.administrator.get(url).status_code, 404)
