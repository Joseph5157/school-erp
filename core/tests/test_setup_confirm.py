"""Removing a calendar exception or the school logo asks first (admin mobile audit, task 4)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core import school_logo
from core.models import (
    AcademicYear,
    AttendanceRegister,
    ClassGrade,
    School,
    SchoolCalendarDay,
    SchoolLogo,
    Section,
)
from core.tests.test_school_logo import image_bytes

User = get_user_model()

LOGO_COPY = (
    "The school name will appear as text in the header and on future documents.",
    "Previously issued documents will not change.",
)


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(self.admin)
        self.school = School.objects.create(name="Sri Vidya School")
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.calendar_url = reverse("core:academic-year-calendar", args=[self.year.pk])
        self.detail_url = reverse("core:school-detail")
        self.logo_url = reverse("core:school-logo-remove")

    def holiday(self, on=date(2026, 8, 17), label="Heavy rain", instructional=False):
        return SchoolCalendarDay.objects.create(
            academic_year=self.year, date=on, is_instructional=instructional, label=label
        )

    def delete_url(self, day):
        return reverse("core:calendar-day-delete", args=[day.pk])

    def add_logo(self):
        school_logo.replace_logo(self.school, image_bytes("PNG"), actor=self.admin)


class CalendarExceptionConfirmTests(Base):
    def test_calendar_page_links_to_confirm_page_without_inline_form(self):
        day = self.holiday()
        page = self.client.get(self.calendar_url)
        self.assertContains(page, f'href="{self.delete_url(day)}"')
        self.assertNotContains(page, f'action="{self.delete_url(day)}"')

    def test_calendar_page_shows_date_label_and_resulting_status(self):
        # Monday holiday: removing it returns the date to an instructional day.
        day = self.holiday()
        page = self.client.get(self.delete_url(day))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Heavy rain")
        self.assertContains(page, "17 August 2026")
        self.assertContains(page, "an instructional day")
        self.assertContains(page, "Remove exception")
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    def test_page_states_status_the_weekly_pattern_gives(self):
        # Saturday extra day (Saturdays off): removing it makes it not instructional.
        day = self.holiday(on=date(2026, 8, 22), label="Make-up", instructional=True)
        page = self.client.get(self.delete_url(day))
        self.assertContains(page, "not an instructional day")

    def test_calendar_post_removes(self):
        day = self.holiday()
        response = self.client.post(self.delete_url(day), follow=True)
        self.assertRedirects(response, self.calendar_url)
        self.assertContains(response, "Calendar exception removed.")
        self.assertFalse(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    def test_second_post_changes_nothing(self):
        day = self.holiday()
        other = self.holiday(on=date(2026, 8, 18), label="Other")
        self.client.post(self.delete_url(day))
        response = self.client.post(self.delete_url(day))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(SchoolCalendarDay.objects.all()), [other])

    def test_calendar_delete_error_is_shown(self):
        day = self.holiday(on=date(2026, 8, 22), label="Make-up", instructional=True)
        class_grade = ClassGrade.objects.create(name="Grade 1")
        section = Section.objects.create(class_grade=class_grade, name="A")
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=class_grade, section=section, date=day.date
        )
        response = self.client.post(self.delete_url(day), follow=True)
        self.assertRedirects(response, self.calendar_url)
        self.assertContains(response, "cannot be removed")
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    def test_get_redirects_with_message_when_attendance_blocks_removal(self):
        day = self.holiday(on=date(2026, 8, 22), label="Make-up", instructional=True)
        class_grade = ClassGrade.objects.create(name="Grade 1")
        section = Section.objects.create(class_grade=class_grade, name="A")
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=class_grade, section=section, date=day.date
        )
        response = self.client.get(self.delete_url(day), follow=True)
        self.assertRedirects(response, self.calendar_url)
        self.assertContains(response, "cannot be removed")
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())


class LogoConfirmTests(Base):
    def test_detail_links_to_confirm_page_without_inline_form(self):
        self.add_logo()
        page = self.client.get(self.detail_url)
        self.assertContains(page, f'href="{self.logo_url}"')
        self.assertNotContains(page, f'action="{self.logo_url}"')

    def test_logo_page_shows_consequences(self):
        self.add_logo()
        page = self.client.get(self.logo_url)
        self.assertEqual(page.status_code, 200)
        for line in LOGO_COPY:
            self.assertContains(page, line)
        self.assertContains(page, "Remove logo")

    def test_logo_get_keeps_logo(self):
        self.add_logo()
        self.client.get(self.logo_url)
        self.assertIsNotNone(SchoolLogo.current_for(self.school))
        self.assertEqual(SchoolLogo.objects.count(), 1)

    def test_logo_post_removes(self):
        self.add_logo()
        response = self.client.post(self.logo_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "School logo removed.")
        self.assertIsNone(SchoolLogo.current_for(self.school))

    def test_logo_page_redirects_when_no_logo(self):
        response = self.client.get(self.logo_url, follow=True)
        self.assertRedirects(response, self.detail_url)
        self.assertContains(response, "no logo to remove")
        self.assertEqual(SchoolLogo.objects.count(), 0)


class PermissionTests(Base):
    def test_view_only_user_is_forbidden(self):
        day = self.holiday()
        self.add_logo()
        viewer = User.objects.create_user(username="viewer", password="pass-12345")
        viewer.user_permissions.add(
            Permission.objects.get(codename="view_school"),
            Permission.objects.get(codename="view_schoolcalendarday"),
        )
        client = self.client_class()
        client.force_login(viewer)
        for url in (self.delete_url(day), self.logo_url):
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(client, method)(url).status_code, 403)
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())
        self.assertIsNotNone(SchoolLogo.current_for(self.school))
