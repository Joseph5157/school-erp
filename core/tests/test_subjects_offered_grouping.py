"""Subjects offered: one collapsible group per Class/Grade, and a modal to change a Grade's order."""

import datetime
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicSubjectOffering, AcademicYear, ClassGrade
from core.tests.test_u4_3a_subject_order import OrderFixture
from core.tests.test_ui_admin_desktop_d1_2a import SchoolConfigurationListsFixture

User = get_user_model()


class ReorderFixture(OrderFixture):
    def setUp(self):
        super().setUp()
        self.order({"Telugu": 1, "English": 2, "Mathematics": 3, "Sanskrit": 4})
        self.sanskrit = AcademicSubjectOffering.objects.get(
            academic_year=self.year, class_grade=self.grade6, subject__name="Sanskrit")
        self.url = reverse("core:offering-reorder", args=[self.year.pk, self.grade6.pk])

    def positions(self):
        return list(
            AcademicSubjectOffering.objects.filter(academic_year=self.year, class_grade=self.grade6)
            .order_by("display_order").values_list("subject__name", "display_order"))

    def post_order(self, *offerings):
        return self.client.post(self.url, {"offering": [o.pk for o in offerings]})


class ReorderSavesTests(ReorderFixture, TestCase):
    def test_saves_the_submitted_order_and_returns_to_that_grade(self):
        response = self.post_order(self.sanskrit, self.maths, self.english, self.telugu)
        self.assertRedirects(
            response,
            reverse("core:academic-year-offerings", args=[self.year.pk]) + f"#grade-{self.grade6.pk}")
        self.assertEqual(self.positions(), [
            ("Sanskrit", 1), ("Mathematics", 2), ("English", 3), ("Telugu", 4)])

    def test_swapping_two_neighbours_does_not_hit_the_unique_position_rule(self):
        self.post_order(self.english, self.telugu, self.maths, self.sanskrit)
        self.assertEqual(self.positions(), [
            ("English", 1), ("Telugu", 2), ("Mathematics", 3), ("Sanskrit", 4)])

    def test_gaps_in_old_positions_are_closed(self):
        self.order({"Telugu": 5, "English": 9, "Mathematics": 2, "Sanskrit": 40})
        self.post_order(self.telugu, self.english, self.maths, self.sanskrit)
        self.assertEqual(self.positions(), [
            ("Telugu", 1), ("English", 2), ("Mathematics", 3), ("Sanskrit", 4)])

    def test_positions_near_the_field_limit_still_save(self):
        # A column limit of 32767: a shift by the current maximum would overflow here.
        self.order({"Telugu": 32767, "English": 32766, "Mathematics": 2, "Sanskrit": 1})
        self.post_order(self.telugu, self.english, self.maths, self.sanskrit)
        self.assertEqual(self.positions(), [
            ("Telugu", 1), ("English", 2), ("Mathematics", 3), ("Sanskrit", 4)])

    def test_other_grades_and_years_are_untouched(self):
        grade7 = ClassGrade.objects.create(name="Grade 7")
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=datetime.date(2027, 6, 1), end_date=datetime.date(2028, 3, 31))
        other_grade = self.offer("Telugu", grade=grade7)
        other_year = self.offer("Telugu", year=next_year)
        self.post_order(self.sanskrit, self.maths, self.english, self.telugu)
        other_grade.refresh_from_db()
        other_year.refresh_from_db()
        self.assertEqual((other_grade.display_order, other_year.display_order), (1, 1))

    def test_unchanged_order_writes_nothing_and_says_so(self):
        before = self.telugu.__class__.objects.get(pk=self.telugu.pk).updated_at
        response = self.post_order(self.telugu, self.english, self.maths, self.sanskrit)
        self.telugu.refresh_from_db()
        self.assertEqual(self.telugu.updated_at, before)
        self.assertEqual([str(m) for m in get_messages(response.wsgi_request)],
                         ["The Subject order for Grade 6 was not changed."])

    def test_a_saved_change_records_the_update_time(self):
        before = self.telugu.__class__.objects.get(pk=self.telugu.pk).updated_at
        self.post_order(self.english, self.telugu, self.maths, self.sanskrit)
        self.telugu.refresh_from_db()
        self.assertGreater(self.telugu.updated_at, before)


class ReorderRejectsTests(ReorderFixture, TestCase):
    def assert_rejected(self, data):
        before = self.positions()
        response = self.client.post(self.url, data)
        self.assertEqual(self.positions(), before)
        # Messages queue up across sub-cases because no page is rendered; the newest is this one's.
        message = list(get_messages(response.wsgi_request))[-1]
        self.assertEqual(message.level_tag, "error")
        self.assertIn("Nothing was saved", str(message))

    def test_an_incomplete_or_foreign_list_saves_nothing(self):
        foreign = self.offer("Telugu", grade=ClassGrade.objects.create(name="Grade 7"))
        cases = {
            "subject missing": [self.telugu.pk, self.english.pk, self.maths.pk],
            "subject repeated": [self.telugu.pk, self.telugu.pk, self.maths.pk, self.sanskrit.pk],
            "other grade's subject": [self.telugu.pk, self.english.pk, self.maths.pk, foreign.pk],
            "extra subject": [self.telugu.pk, self.english.pk, self.maths.pk, self.sanskrit.pk,
                              foreign.pk],
            "not a number": [self.telugu.pk, self.english.pk, self.maths.pk, "abc"],
            "empty": [],
        }
        for name, offerings in cases.items():
            with self.subTest(name):
                self.assert_rejected({"offering": offerings})

    def test_unknown_grade_or_year_is_not_found(self):
        for args in ([self.year.pk, 99999], [99999, self.grade6.pk]):
            with self.subTest(args=args):
                response = self.client.post(
                    reverse("core:offering-reorder", args=args), {"offering": [self.telugu.pk]})
                self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_view_only_user_is_refused(self):
        user = User.objects.create_user(username="offer-viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_academicsubjectoffering"))
        client = self.client_class()
        client.force_login(user)
        before = self.positions()
        response = client.post(self.url, {"offering": [
            self.english.pk, self.telugu.pk, self.maths.pk, self.sanskrit.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.positions(), before)


class ReorderAndPublishedCardsTests(ReorderFixture, TestCase):
    def test_published_card_keeps_its_order_after_a_reorder(self):
        """The modal promises this, so it is pinned through the modal's own route."""
        self.finalized_result(self.telugu, "Telugu UT1", datetime.date(2026, 7, 16))
        self.finalized_result(self.english, "English UT1", datetime.date(2026, 7, 17))
        cards = self.publish()
        before = [self.entries(card) for card in cards]
        self.assertTrue(any(before))

        self.post_order(self.sanskrit, self.maths, self.english, self.telugu)

        self.assertEqual(self.positions()[0], ("Sanskrit", 1))
        self.assertEqual([self.entries(card) for card in cards], before)


class GroupedPageTests(SchoolConfigurationListsFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.class_ten = ClassGrade.objects.create(name="Class 10")
        AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.class_ten, subject=self.english)
        AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.class_two, subject=self.english)
        self.url = reverse("core:academic-year-offerings", args=[self.year.pk])

    def page(self, client=None):
        return (client or self.administrator).get(self.url)

    def test_grades_sort_as_numbers_and_subjects_by_position(self):
        groups = self.page().context["grade_groups"]
        self.assertEqual([g["grade"].name for g in groups], ["Class 1", "Class 2", "Class 10"])
        self.assertEqual([o.subject.name for o in groups[0]["offerings"]], ["Drawing", "English"])

    def test_only_the_first_grade_starts_open(self):
        content = self.page().content.decode()
        tags = re.findall(r"<details\b[^>]*erp-offering-group[^>]*>", content)
        self.assertEqual(len(tags), 3)
        self.assertEqual([" open" in tag for tag in tags], [True, False, False])

    def test_each_group_counts_its_subjects(self):
        content = self.page().content.decode()
        self.assertIn("2 subjects", content)
        self.assertIn("1 subject<", content)

    def test_empty_year_shows_no_groups(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=datetime.date(2027, 6, 1), end_date=datetime.date(2028, 3, 31))
        response = self.administrator.get(reverse("core:academic-year-offerings", args=[other.pk]))
        self.assertEqual(response.context["grade_groups"], [])
        self.assertNotContains(response, "erp-offering-group")

    def test_order_modal_lists_the_grade_in_current_order(self):
        content = self.page().content.decode()
        action = reverse("core:offering-reorder", args=[self.year.pk, self.class_one.pk])
        form = content.split(f'action="{action}"')[1].split("</form>")[0]
        self.assertLess(
            form.index(f'name="offering" value="{self.draw_offer.pk}"'),
            form.index(f'name="offering" value="{self.eng_offer.pk}"'))
        self.assertIn("csrfmiddlewaretoken", form)
        self.assertIn("Report cards already published won", form)

    def test_a_grade_with_one_subject_has_no_order_modal(self):
        content = self.page().content.decode()
        for grade in (self.class_two, self.class_ten):
            self.assertNotIn(reverse("core:offering-reorder", args=[self.year.pk, grade.pk]), content)

    def test_view_only_user_gets_no_order_controls_or_library(self):
        viewer = self.viewer_client("view_academicsubjectoffering", "view_academicyear")
        response = self.page(viewer)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Drawing")
        for absent in ("offering-reorder", "/order/", "Change order", "Sortable"):
            self.assertNotContains(response, absent)

    def test_editor_gets_the_drag_library(self):
        self.assertContains(self.page(), "sortablejs@1.15.6")
