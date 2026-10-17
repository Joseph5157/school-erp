"""Phase 4 Gate 2: assessment teacher assignment and scoped authorization (ADR 0010)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.authorization import can_enter_results, current_teacher_assignments, is_teacher
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    Subject,
)

User = get_user_model()


class TeacherFixture:
    def build(self):
        self.teachers = Group.objects.get(name=TEACHERS_GROUP_NAME)
        self.admins = Group.objects.get(name="School Administrators")
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        self.grade6 = ClassGrade.objects.create(name="Grade 6")
        self.grade7 = ClassGrade.objects.create(name="Grade 7")
        self.six_a = Section.objects.create(class_grade=self.grade6, name="A")
        self.six_b = Section.objects.create(class_grade=self.grade6, name="B")
        self.seven_a = Section.objects.create(class_grade=self.grade7, name="A")
        self.maths = AcademicSubjectOffering.objects.create(
            academic_year=self.year,
            class_grade=self.grade6,
            subject=Subject.objects.create(name="Mathematics"),
        )
        self.sanskrit = AcademicSubjectOffering.objects.create(
            academic_year=self.year,
            class_grade=self.grade6,
            subject=Subject.objects.create(name="Sanskrit"),
        )
        self.sanskrit.set_sections([self.six_b])
        self.rao = self.user("rao", self.teachers)
        self.iyer = self.user("iyer", self.teachers)

    def user(self, username, *groups, **extra):
        user = User.objects.create_user(username=username, password="pass-12345", **extra)
        user.groups.add(*groups)
        return user

    def assign(self, teacher, offering, section):
        assignment = AssessmentTeacherAssignment(
            teacher=teacher, offering=offering, section=section,
            start_date=self.year.start_date,
        )
        assignment.full_clean()
        assignment.save()
        return assignment


class TeacherIdentityTests(TeacherFixture, TestCase):
    def setUp(self):
        self.build()

    def test_teachers_group_exists_without_model_permissions(self):
        self.assertEqual(self.teachers.permissions.count(), 0)

    def test_is_teacher(self):
        self.assertTrue(is_teacher(self.rao))
        self.assertFalse(is_teacher(self.user("clerk")))
        self.assertFalse(is_teacher(self.user("admin", self.admins)))
        self.assertFalse(is_teacher(AnonymousUser()))
        self.assertFalse(is_teacher(None))
        self.rao.is_active = False
        self.rao.save()
        self.assertFalse(is_teacher(self.rao))


class AssignmentRuleTests(TeacherFixture, TestCase):
    def setUp(self):
        self.build()

    def test_valid_assignment(self):
        assignment = self.assign(self.rao, self.maths, self.six_a)
        self.assertEqual(str(assignment.section), "Grade 6 - A")

    def test_teacher_must_be_active_member_of_teachers_group(self):
        for user in (
            self.user("clerk"),
            self.user("admin", self.admins),
            self.user("gone", self.teachers, is_active=False),
        ):
            with self.subTest(user=user.username), self.assertRaises(ValidationError) as ctx:
                self.assign(user, self.maths, self.six_a)
            self.assertIn("teacher", ctx.exception.message_dict)

    def test_section_must_take_the_offering(self):
        for offering, section in (
            (self.maths, self.seven_a),  # other Grade
            (self.sanskrit, self.six_a),  # not in restricted scope
        ):
            with self.subTest(section=str(section)), self.assertRaises(ValidationError) as ctx:
                self.assign(self.rao, offering, section)
            self.assertIn("section", ctx.exception.message_dict)
        self.assign(self.rao, self.sanskrit, self.six_b)

    def test_one_teacher_per_offering_and_section(self):
        self.assign(self.rao, self.maths, self.six_a)
        with self.assertRaises(ValidationError):
            self.assign(self.iyer, self.maths, self.six_a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentTeacherAssignment.objects.create(
                teacher=self.iyer, offering=self.maths, section=self.six_a,
                start_date=self.year.start_date,
            )
        self.assign(self.iyer, self.maths, self.six_b)  # other Section is fine
        self.assign(self.rao, self.sanskrit, self.six_b)  # one teacher, several duties

    def test_offering_scope_cannot_drop_an_assigned_section(self):
        self.assign(self.rao, self.sanskrit, self.six_b)
        with self.assertRaises(ValidationError):
            self.sanskrit.set_sections([self.six_a])
        self.assertEqual(list(self.sanskrit.sections), [self.six_b])
        self.sanskrit.set_sections([self.six_a, self.six_b])  # adding is fine
        self.sanskrit.set_sections([])  # widening to all Sections is fine

    def test_history_protection(self):
        self.assign(self.rao, self.maths, self.six_a)
        for obj in (self.rao, self.maths, self.six_a):
            with self.subTest(obj=str(obj)), self.assertRaises(ProtectedError), (
                transaction.atomic()
            ):
                obj.delete()


class ScopedAuthorizationTests(TeacherFixture, TestCase):
    def setUp(self):
        self.build()
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.assign(self.iyer, self.maths, self.six_b)

    def test_assigned_teacher_may_enter_results(self):
        self.assertTrue(can_enter_results(self.rao, self.maths, self.six_a))
        self.assertTrue(can_enter_results(self.rao, self.sanskrit, self.six_b))

    def test_other_subject_section_or_teacher_may_not(self):
        self.assertFalse(can_enter_results(self.rao, self.maths, self.six_b))
        self.assertFalse(can_enter_results(self.iyer, self.maths, self.six_a))
        self.assertFalse(can_enter_results(self.iyer, self.sanskrit, self.six_b))

    def test_administrators_and_superusers_are_not_result_entering_teachers(self):
        admin = self.user("admin", self.admins)
        root = User.objects.create_superuser("root", "r@example.com", "pass-12345")
        for user in (admin, root, AnonymousUser()):
            with self.subTest(user=str(user)):
                self.assertFalse(can_enter_results(user, self.maths, self.six_a))

    def test_leaving_group_or_deactivation_revokes_access_immediately(self):
        self.rao.groups.remove(self.teachers)
        self.assertFalse(can_enter_results(self.rao, self.maths, self.six_a))
        self.rao.groups.add(self.teachers)
        self.assertTrue(can_enter_results(self.rao, self.maths, self.six_a))
        self.rao.is_active = False
        self.rao.save()
        self.assertFalse(can_enter_results(self.rao, self.maths, self.six_a))
        self.assertFalse(current_teacher_assignments(self.rao).exists())

    def test_teacher_assignments_lists_only_own_duties(self):
        duties = {
            (a.offering.subject.name, a.section.name)
            for a in current_teacher_assignments(self.rao)
        }
        self.assertEqual(duties, {("Mathematics", "A"), ("Sanskrit", "B")})


class TeacherAssignmentViewTests(TeacherFixture, TestCase):
    def setUp(self):
        self.build()
        self.user("admin", self.admins)
        self.client.login(username="admin", password="pass-12345")
        self.teacher_client = self.client_class()
        self.teacher_client.login(username="rao", password="pass-12345")
        self.list_url = reverse("core:academic-year-teacher-assignments", args=[self.year.pk])
        self.add_url = reverse("core:teacher-assignment-create", args=[self.year.pk])

    def test_admin_assigns_lists_and_removes(self):
        response = self.client.post(
            self.add_url,
            {"teacher": self.rao.pk, "offering": self.maths.pk, "section": self.six_a.pk,
             "start_date": "2026-06-01"},
        )
        self.assertRedirects(response, self.list_url)
        listing = self.client.get(self.list_url)
        self.assertContains(listing, "rao")
        self.assertContains(listing, "Mathematics")
        assignment = AssessmentTeacherAssignment.objects.get()
        remove_url = reverse("core:teacher-assignment-delete", args=[assignment.pk])
        self.client.get(remove_url)  # GET never deletes
        self.assertTrue(AssessmentTeacherAssignment.objects.exists())
        # A row that has taken effect is ended, never deleted (ADR 0018 D5).
        self.assertRedirects(self.client.post(remove_url), self.list_url)
        self.assertTrue(AssessmentTeacherAssignment.objects.exists())
        AssessmentTeacherAssignment.objects.filter(pk=assignment.pk).update(
            start_date=self.year.end_date
        )
        self.assertRedirects(self.client.post(remove_url), self.list_url)
        self.assertFalse(AssessmentTeacherAssignment.objects.exists())

    def test_form_only_offers_active_teachers_and_this_years_offerings(self):
        self.user("clerk")
        self.user("gone", self.teachers, is_active=False)
        other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        AcademicSubjectOffering.objects.create(
            academic_year=other_year, class_grade=self.grade6, subject=self.maths.subject
        )
        form = self.client.get(self.add_url).context["form"]
        self.assertEqual(
            sorted(u.username for u in form.fields["teacher"].queryset), ["iyer", "rao"]
        )
        self.assertEqual(
            set(form.fields["offering"].queryset), {self.maths, self.sanskrit}
        )

    def test_rejects_wrong_section_and_duplicate(self):
        bad = self.client.post(
            self.add_url,
            {"teacher": self.rao.pk, "offering": self.sanskrit.pk, "section": self.six_a.pk},
        )
        self.assertContains(bad, "does not take this Subject offering")
        self.client.post(
            self.add_url,
            {"teacher": self.rao.pk, "offering": self.maths.pk, "section": self.six_a.pk,
             "start_date": "2026-06-01"},
        )
        duplicate = self.client.post(
            self.add_url,
            {"teacher": self.iyer.pk, "offering": self.maths.pk, "section": self.six_a.pk,
             "start_date": "2026-06-01"},
        )
        self.assertContains(duplicate, "overlap")
        self.assertEqual(AssessmentTeacherAssignment.objects.count(), 1)

    def test_teacher_cannot_manage_assignments(self):
        self.assign(self.iyer, self.maths, self.six_b)
        assignment = AssessmentTeacherAssignment.objects.get()
        for method, url, data in (
            ("get", self.list_url, {}),
            ("post", self.add_url, {"teacher": self.rao.pk, "offering": self.maths.pk,
                                    "section": self.six_a.pk, "start_date": "2026-06-01"}),
            ("post", reverse("core:teacher-assignment-delete", args=[assignment.pk]), {}),
        ):
            with self.subTest(url=url):
                response = getattr(self.teacher_client, method)(url, data)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(AssessmentTeacherAssignment.objects.count(), 1)

    def test_teacher_login_reaches_no_admin_page(self):
        for name in ("core:student-list", "core:attendance-register-list", "core:subject-list"):
            with self.subTest(page=name):
                self.assertEqual(self.teacher_client.get(reverse(name)).status_code, 403)
