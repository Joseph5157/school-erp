"""Classes/Grades sort by a stored position, so Grade 10 follows Grade 9 and Nursery can come first."""

import pathlib
import re
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from core import imports
from core.forms import AnnouncementForm
from core.models import ClassGrade, Section

User = get_user_model()
CORE = pathlib.Path(__file__).resolve().parent.parent


def names(queryset):
    return [grade.name for grade in queryset]


class PositionTests(TestCase):
    def test_a_new_grade_goes_last(self):
        first = ClassGrade.objects.create(name="Grade 1")
        second = ClassGrade.objects.create(name="Grade 2")
        self.assertEqual((first.display_order, second.display_order), (1, 2))

    def test_an_explicit_position_is_kept(self):
        self.assertEqual(ClassGrade.objects.create(name="LKG", display_order=7).display_order, 7)

    def test_saving_again_does_not_move_a_grade(self):
        grade = ClassGrade.objects.create(name="Grade 1")
        ClassGrade.objects.create(name="Grade 2")
        grade.name = "Class 1"
        grade.save()
        self.assertEqual(grade.display_order, 1)

    def test_default_order_follows_position_not_name(self):
        for name in ("Nursery", "Grade 2", "Grade 10"):
            ClassGrade.objects.create(name=name)
        self.assertEqual(names(ClassGrade.objects.all()), ["Nursery", "Grade 2", "Grade 10"])

    def test_sections_follow_their_grade_position(self):
        two = ClassGrade.objects.create(name="Grade 2")
        ten = ClassGrade.objects.create(name="Grade 10")
        Section.objects.create(class_grade=ten, name="A")
        Section.objects.create(class_grade=two, name="B")
        self.assertEqual(
            [(s.class_grade.name, s.name) for s in Section.objects.all()],
            [("Grade 2", "B"), ("Grade 10", "A")],
        )

    def test_two_grades_cannot_share_a_position(self):
        ClassGrade.objects.create(name="Grade 1", display_order=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassGrade.objects.create(name="Grade 2", display_order=1)

    def test_position_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassGrade.objects.create(name="Grade 1", display_order=0)


class ReorderTests(TestCase):
    def setUp(self):
        self.a = ClassGrade.objects.create(name="A")
        self.b = ClassGrade.objects.create(name="B")
        self.c = ClassGrade.objects.create(name="C")

    def test_renumbers_in_the_given_order(self):
        self.assertTrue(ClassGrade.reorder([self.c.pk, self.a.pk, self.b.pk]))
        self.assertEqual(
            list(ClassGrade.objects.values_list("name", "display_order")),
            [("C", 1), ("A", 2), ("B", 3)],
        )

    def test_swapping_neighbours_does_not_hit_the_unique_rule(self):
        self.assertTrue(ClassGrade.reorder([self.b.pk, self.a.pk, self.c.pk]))
        self.assertEqual(names(ClassGrade.objects.all()), ["B", "A", "C"])

    def test_same_order_changes_nothing(self):
        self.assertFalse(ClassGrade.reorder([self.a.pk, self.b.pk, self.c.pk]))

    def test_an_incomplete_list_saves_nothing(self):
        for submitted in ([self.a.pk, self.b.pk], [self.a.pk, self.a.pk, self.b.pk]):
            with self.subTest(submitted=submitted), self.assertRaises(ValidationError):
                ClassGrade.reorder(submitted)
        self.assertEqual(names(ClassGrade.objects.all()), ["A", "B", "C"])


class ClassListScreenTests(TestCase):
    def setUp(self):
        self.two = ClassGrade.objects.create(name="Grade 2")
        self.ten = ClassGrade.objects.create(name="Grade 10")
        self.list_url = reverse("core:class-grade-list")
        self.url = reverse("core:class-grade-reorder")

    def login(self, *codenames):
        user = User.objects.create_user(username="order-user", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        self.client.force_login(user)

    def test_list_shows_grades_by_position(self):
        self.login("view_classgrade")
        content = self.client.get(self.list_url).content.decode()
        self.assertLess(content.index(">Grade 2<"), content.index(">Grade 10<"))

    def test_order_controls_need_the_change_permission(self):
        self.login("view_classgrade")
        self.assertNotContains(self.client.get(self.list_url), "data-erp-reorder")

    def test_order_controls_start_hidden_and_name_every_grade(self):
        self.login("view_classgrade", "change_classgrade")
        content = self.client.get(self.list_url).content.decode()
        self.assertIn("data-erp-reorder", content)
        self.assertRegex(content, r'data-bs-target="#class-order"\s+hidden')
        self.assertIn('aria-label="Move Grade 10 up"', content)
        self.assertEqual(
            re.findall(r'name="class_grade" value="(\d+)"', content),
            [str(self.two.pk), str(self.ten.pk)],
        )

    def test_one_grade_has_nothing_to_order(self):
        self.ten.delete()
        self.login("view_classgrade", "change_classgrade")
        self.assertNotContains(self.client.get(self.list_url), "data-erp-reorder")

    def test_saving_a_new_order(self):
        self.login("view_classgrade", "change_classgrade")
        response = self.client.post(self.url, {"class_grade": [self.ten.pk, self.two.pk]})
        self.assertRedirects(response, self.list_url)
        self.assertEqual(names(ClassGrade.objects.all()), ["Grade 10", "Grade 2"])

    def test_a_list_changed_elsewhere_saves_nothing_and_says_so(self):
        self.login("view_classgrade", "change_classgrade")
        response = self.client.post(self.url, {"class_grade": [self.ten.pk]})
        self.assertEqual(names(ClassGrade.objects.all()), ["Grade 2", "Grade 10"])
        self.assertIn("Nothing was saved", str(list(get_messages(response.wsgi_request))[0]))

    def test_saving_needs_the_change_permission(self):
        self.login("view_classgrade")
        response = self.client.post(self.url, {"class_grade": [self.ten.pk, self.two.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(names(ClassGrade.objects.all()), ["Grade 2", "Grade 10"])

    def test_saving_is_post_only(self):
        self.login("view_classgrade", "change_classgrade")
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_create_form_places_the_new_grade_last(self):
        self.login("view_classgrade", "add_classgrade")
        self.client.post(reverse("core:class-grade-create"), {"name": "Grade 11"})
        self.assertEqual(ClassGrade.objects.get(name="Grade 11").display_order, 3)


class EveryPageFollowsThePositionTests(TestCase):
    def test_announcement_selectors(self):
        two = ClassGrade.objects.create(name="Grade 2")
        ten = ClassGrade.objects.create(name="Grade 10")
        Section.objects.create(class_grade=ten, name="A")
        Section.objects.create(class_grade=two, name="A")
        form = AnnouncementForm()
        self.assertEqual(names(form.fields["class_grade"].queryset), ["Grade 2", "Grade 10"])
        self.assertEqual(
            [s.class_grade.name for s in form.fields["section"].queryset], ["Grade 2", "Grade 10"]
        )

    def test_no_app_code_sorts_grades_by_name(self):
        by_name = re.compile(r'order_by\([^)]*class_grade__name|ClassGrade\.objects\.order_by\("name"')
        offenders = [path.name for path in CORE.glob("*.py") if by_name.search(path.read_text("utf-8"))]
        self.assertEqual(offenders, [])

    def test_imported_grades_are_added_in_natural_order(self):
        classes = {}
        imports._create_missing_classes(["Grade 10", "Grade 2"], classes)
        self.assertEqual(names(ClassGrade.objects.all()), ["Grade 2", "Grade 10"])
        self.assertEqual(len(classes), 2)


@skipUnless(connection.vendor == "postgresql", "Flushing core tables is guarded on SQLite.")
class BackfillMigrationTests(TransactionTestCase):
    BEFORE = [("core", "0084_english_student_names")]
    AFTER = [("core", "0087_classgrade_display_order_constraints")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_existing_grades_get_academic_order(self):
        apps = self._migrate(self.BEFORE)
        grade = apps.get_model("core", "ClassGrade")
        for name in ("Grade 10", "Grade 2", "UKG", "Grade 1", "Nursery", "LKG", "Commerce"):
            grade.objects.create(name=name)
        apps = self._migrate(self.AFTER)
        rows = apps.get_model("core", "ClassGrade").objects.order_by("display_order")
        self.assertEqual(
            list(rows.values_list("name", "display_order")),
            [
                ("Nursery", 1), ("LKG", 2), ("UKG", 3), ("Commerce", 4),
                ("Grade 1", 5), ("Grade 2", 6), ("Grade 10", 7),
            ],
        )
