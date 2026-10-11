"""Phase 5 Gate 1: dated class teacher assignment (ADR 0011 D1-D3, D14)."""

from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.authorization import (
    class_teacher_assignments,
    class_teacher_on,
    class_teacher_sections,
)
from core.models import AttendanceRegister, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)
today_patch = mock.patch("core.models.business_today", new=lambda: TODAY)
view_today_patch = mock.patch("core.views.business_today", new=lambda: TODAY)


class ClassTeacherFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()

    def assign_ct(self, teacher, section, start, year=None):
        return SectionClassTeacher.assign(
            teacher=teacher, academic_year=year or self.year, section=section, start_date=start
        )


@today_patch
class SectionClassTeacherModelTests(ClassTeacherFixture, TestCase):
    def test_assign_creates_open_ended_row(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        self.assertIsNone(row.end_date)
        self.assertTrue(row.is_effective_on(date(2027, 3, 31)))
        self.assertFalse(row.is_effective_on(date(2026, 5, 31)))

    def test_replacement_ends_previous_row_the_day_before(self):
        old = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        new = self.assign_ct(self.iyer, self.six_a, date(2026, 11, 1))
        old.refresh_from_db()
        self.assertEqual(old.end_date, date(2026, 10, 31))
        self.assertIsNone(new.end_date)
        self.assertEqual(SectionClassTeacher.objects.count(), 2)
        self.assertEqual(
            list(SectionClassTeacher.objects.effective_on(date(2026, 7, 1))), [old]
        )
        self.assertEqual(
            list(SectionClassTeacher.objects.effective_on(date(2026, 12, 1))), [new]
        )

    def test_overlap_with_later_row_is_rejected(self):
        self.assign_ct(self.rao, self.six_a, date(2026, 11, 1))
        with self.assertRaises(ValidationError):
            self.assign_ct(self.iyer, self.six_a, date(2026, 6, 1))
        self.assertEqual(SectionClassTeacher.objects.count(), 1)

    def test_same_start_date_is_rejected(self):
        self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        with self.assertRaises(ValidationError):
            self.assign_ct(self.iyer, self.six_a, date(2026, 6, 1))

    def test_other_sections_are_independent_and_one_teacher_may_hold_several(self):
        self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        self.assign_ct(self.rao, self.six_b, date(2026, 6, 1))
        self.assertEqual(SectionClassTeacher.objects.filter(teacher=self.rao).count(), 2)

    def test_dates_must_fall_in_academic_year(self):
        with self.assertRaises(ValidationError):
            self.assign_ct(self.rao, self.six_a, date(2026, 5, 31))
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        with self.assertRaises(ValidationError):
            row.end(date(2027, 4, 1))

    def test_teacher_must_be_active_teachers_group_login(self):
        outsider = self.make_user("outsider")
        with self.assertRaises(ValidationError):
            self.assign_ct(outsider, self.six_a, date(2026, 6, 1))
        self.iyer.is_active = False
        self.iyer.save()
        with self.assertRaises(ValidationError):
            self.assign_ct(self.iyer, self.six_a, date(2026, 6, 1))

    def test_end_cannot_extend_or_precede_start(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        row.end(date(2026, 9, 30))
        with self.assertRaises(ValidationError):
            row.end(date(2026, 10, 31))
        with self.assertRaises(ValidationError):
            row.end(date(2026, 5, 31))

    def test_end_cannot_cut_off_dependent_registers(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 7, 6), status=AttendanceRegister.Status.SUBMITTED,
            submitted_by=self.rao, submitted_at="2026-07-06T10:00:00+05:30",
        )
        with self.assertRaises(ValidationError):
            row.end(date(2026, 7, 1))
        row.end(date(2026, 7, 6))
        row.refresh_from_db()
        self.assertEqual(row.end_date, date(2026, 7, 6))

    def test_effective_row_cannot_be_deleted(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        self.assertTrue(row.is_historically_relevant)
        with self.assertRaises(ValidationError):
            row.delete()
        self.assertTrue(SectionClassTeacher.objects.filter(pk=row.pk).exists())

    def test_planned_row_without_dependents_can_be_deleted(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 11, 1))
        self.assertFalse(row.is_historically_relevant)
        row.delete()
        self.assertFalse(SectionClassTeacher.objects.exists())

    def test_database_rejects_end_before_start(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            SectionClassTeacher.objects.filter(pk=row.pk).update(end_date=date(2026, 5, 1))


@today_patch
class ClassTeacherHelperTests(ClassTeacherFixture, TestCase):
    def test_helpers_follow_dates(self):
        self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        self.assign_ct(self.iyer, self.six_a, date(2026, 11, 1))
        self.assertTrue(class_teacher_on(self.rao, self.six_a, date(2026, 10, 31)))
        self.assertFalse(class_teacher_on(self.rao, self.six_a, date(2026, 11, 1)))
        self.assertTrue(class_teacher_on(self.iyer, self.six_a, date(2026, 11, 1)))
        self.assertEqual(list(class_teacher_sections(self.rao, TODAY)), [self.six_a])
        self.assertEqual(list(class_teacher_sections(self.iyer, TODAY)), [])

    def test_losing_teacher_status_removes_access_but_keeps_rows(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        self.rao.groups.remove(self.teachers)
        self.assertFalse(class_teacher_on(self.rao, self.six_a, TODAY))
        self.assertFalse(class_teacher_assignments(self.rao).exists())
        self.rao.groups.add(self.teachers)
        self.rao.is_active = False
        self.rao.save()
        self.assertFalse(class_teacher_on(self.rao, self.six_a, TODAY))
        row.refresh_from_db()
        self.assertIsNone(row.end_date)
        self.assertEqual(SectionClassTeacher.objects.count(), 1)

    def test_administrator_is_not_a_class_teacher(self):
        self.assertFalse(class_teacher_on(self.admin, self.six_a, TODAY))


@today_patch
@view_today_patch
class ClassTeacherViewTests(ClassTeacherFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.list_url = reverse("core:academic-year-class-teachers", args=[self.year.pk])
        self.assign_url = reverse("core:class-teacher-assign", args=[self.year.pk])

    def test_list_shows_every_section_and_current_teacher(self):
        self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        response = self.client.get(self.list_url)
        rows = {row["section"]: row for row in response.context["sections"]}
        self.assertEqual(rows[self.six_a]["current"].teacher, self.rao)
        self.assertIsNone(rows[self.six_b]["current"])
        self.assertContains(response, "Replace")

    def test_assign_and_replace_through_views(self):
        self.client.post(self.assign_url, {"section": self.six_a.pk, "teacher": self.rao.pk,
                                           "start_date": "2026-06-01"})
        response = self.client.post(self.assign_url, {"section": self.six_a.pk,
                                                      "teacher": self.iyer.pk,
                                                      "start_date": "2026-10-10"})
        self.assertRedirects(response, self.list_url)
        old, new = SectionClassTeacher.objects.order_by("start_date")
        self.assertEqual((old.end_date, new.teacher), (date(2026, 10, 9), self.iyer))

    def test_assign_form_defaults_to_today_and_rejects_overlap(self):
        response = self.client.get(self.assign_url)
        self.assertEqual(response.context["form"].initial["start_date"], TODAY)
        self.assign_ct(self.rao, self.six_a, date(2026, 11, 1))
        response = self.client.post(self.assign_url, {"section": self.six_a.pk,
                                                      "teacher": self.iyer.pk,
                                                      "start_date": "2026-06-01"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlap")

    def test_teacher_choices_are_active_teachers_only(self):
        self.make_user("plain")
        choices = self.client.get(self.assign_url).context["form"].fields["teacher"].queryset
        self.assertEqual(set(choices), {self.rao, self.iyer})

    def test_end_view(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        url = reverse("core:class-teacher-end", args=[row.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.client.post(url, {"end_date": "2026-12-31"}), self.list_url)
        row.refresh_from_db()
        self.assertEqual(row.end_date, date(2026, 12, 31))

    def test_delete_view_refuses_effective_rows(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        planned = self.assign_ct(self.iyer, self.six_b, date(2026, 11, 1))
        response = self.client.post(
            reverse("core:class-teacher-delete", args=[row.pk]), follow=True
        )
        self.assertContains(response, "end it instead of deleting it")
        self.assertTrue(SectionClassTeacher.objects.filter(pk=row.pk).exists())
        self.client.post(reverse("core:class-teacher-delete", args=[planned.pk]))
        self.assertFalse(SectionClassTeacher.objects.filter(pk=planned.pk).exists())
        self.assertNotContains(self.client.get(self.list_url), "Delete planned")

    def test_teachers_and_plain_users_are_forbidden(self):
        row = self.assign_ct(self.rao, self.six_a, date(2026, 6, 1))
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        for url in (self.list_url, self.assign_url,
                    reverse("core:class-teacher-end", args=[row.pk]),
                    reverse("core:class-teacher-delete", args=[row.pk])):
            with self.subTest(url=url):
                self.assertEqual(teacher.get(url).status_code, 403)
                self.assertEqual(teacher.post(url).status_code, 403)

    def test_year_list_links_to_class_teachers(self):
        self.assertContains(self.client.get(reverse("core:academic-year-list")), self.list_url)
