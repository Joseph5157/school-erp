"""The admin Teachers list shows one card per teacher on phones and counts current-year work only.

Which of table or cards is visible is a Bootstrap breakpoint class, checked in a real browser;
these tests pin what each card says, the current-year count and the deactivation page's list.
"""

import re
from datetime import timedelta
from html import unescape

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import teacher_accounts
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    SectionClassTeacher,
    Subject,
    business_today,
)
from core.tests.test_authorization import AuthorizationClientsMixin
from core.tests.test_ui_admin_phase3d import add_teacher


def cards_in(html):
    """The text of each card, tags removed and whitespace collapsed, keyed by link target."""
    region = re.search(r'<ul class="erp-teacher-cards[^"]*"[^>]*>(.*?)</ul>', html, re.S)
    if region is None:
        return {}
    cards = {}
    for body in re.findall(r'<li class="erp-teacher-card">(.*?)</li>', region.group(1), re.S):
        href = re.search(r'href="([^"]+)"', body).group(1)
        cards[href] = " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())
    return cards


class TeacherWorkFixture(AuthorizationClientsMixin):
    def setUp(self):
        super().setUp()
        self.today = business_today()
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=self.today - timedelta(days=60),
            end_date=self.today + timedelta(days=60),
        )
        self.old_year = AcademicYear.objects.create(
            name="2024-25", start_date=self.today - timedelta(days=900),
            end_date=self.today - timedelta(days=600),
        )
        self.grade = ClassGrade.objects.create(name="Grade 6")
        self.section = Section.objects.create(class_grade=self.grade, name="A")
        self.maths = Subject.objects.create(name="Mathematics")
        self.history = Subject.objects.create(name="History")
        self.teacher, _ = add_teacher(self.admin_user, "rao.teacher")

    def offering(self, year, subject):
        offering = AcademicSubjectOffering.objects.create(
            academic_year=year, class_grade=self.grade, subject=subject
        )
        offering.set_sections([self.section])
        return offering

    def subject_row(self, year, subject, start, end=None):
        return AssessmentTeacherAssignment.objects.create(
            teacher=self.teacher, offering=self.offering(year, subject),
            section=self.section, start_date=start, end_date=end,
        )

    def class_row(self, year, start, end=None):
        return SectionClassTeacher.objects.create(
            teacher=self.teacher, academic_year=year, section=self.section,
            start_date=start, end_date=end,
        )

    def count(self):
        return teacher_accounts.teacher_queryset().get(pk=self.teacher.pk).current_assignment_count


class CurrentYearCountTests(TeacherWorkFixture, TestCase):
    def test_count_ignores_past_years_and_ended_assignments(self):
        old_start = self.old_year.start_date
        self.subject_row(self.old_year, self.maths, old_start, old_start + timedelta(days=100))
        self.class_row(self.old_year, old_start)  # past year, even though open ended
        self.subject_row(
            self.year, self.history, self.year.start_date, self.today - timedelta(days=1)
        )  # ended yesterday
        self.assertEqual(self.count(), 0)
        self.subject_row(self.year, self.maths, self.year.start_date)  # open ended
        self.class_row(self.year, self.year.start_date, self.today)  # ends today: still counts
        self.assertEqual(self.count(), 2)

    def test_count_is_zero_without_a_current_year(self):
        AcademicYear.objects.all().delete()
        self.assertEqual(self.count(), 0)


class TeacherCardTests(TeacherWorkFixture, TestCase):
    url = reverse("core:teacher-list")

    def test_list_header_names_the_year(self):
        html = self.administrator.get(self.url).content.decode()
        self.assertIn(f"Assignments ({self.year.name})", html)
        self.assertNotIn("all years", html)

    def test_list_header_without_a_year_has_no_year(self):
        AcademicYear.objects.all().delete()
        html = self.administrator.get(self.url).content.decode()
        self.assertNotIn("all years", html)
        self.assertNotIn("Assignments (", html)

    def test_card_shows_name_username_status_count_and_last_sign_in(self):
        self.teacher.first_name, self.teacher.last_name = "Asha", "Rao"
        self.teacher.save()
        self.subject_row(self.year, self.maths, self.year.start_date)
        html = self.administrator.get(self.url).content.decode()
        text = cards_in(html)[reverse("core:teacher-detail", args=[self.teacher.pk])]
        self.assertIn("Asha Rao", text)
        self.assertIn("rao.teacher", text)
        self.assertIn("Active", text)
        self.assertIn("1 assignment", text)
        self.assertNotIn("1 assignments", text)
        self.assertIn("Never signed in", text)

    def test_card_pluralises_and_shows_inactive(self):
        teacher_accounts.deactivate_teacher(user=self.teacher, reason="Left", actor=self.admin_user)
        html = self.administrator.get(self.url).content.decode()
        text = cards_in(html)[reverse("core:teacher-detail", args=[self.teacher.pk])]
        self.assertIn("Inactive", text)
        self.assertIn("0 assignments", text)

    def test_empty_result_shows_the_message_in_both_layouts(self):
        html = self.administrator.get(self.url + "?q=nomatchatall").content.decode()
        self.assertEqual(html.count("No teachers match your search or status filter."), 2)

    def test_cards_are_hidden_when_printing(self):
        html = self.administrator.get(self.url).content.decode()
        self.assertIn('<ul class="erp-teacher-cards d-md-none d-print-none" role="list">', html)
        self.assertIn('class="d-none d-md-block d-print-block"', html)

    def test_query_count_does_not_grow_with_teachers(self):
        self.administrator.get(self.url)  # warm caches

        def queries():
            with CaptureQueriesContext(connection) as captured:
                self.administrator.get(self.url)
            return len(captured)

        one = queries()
        for index in range(8):
            add_teacher(self.admin_user, f"extra.t{index}")
        self.assertEqual(queries(), one)


class DeactivatePageTests(TeacherWorkFixture, TestCase):
    def page(self):
        url = reverse("core:teacher-deactivate", args=[self.teacher.pk])
        return self.administrator.get(url).content.decode()

    def test_deactivate_page_lists_ongoing_assignments(self):
        self.subject_row(self.year, self.maths, self.year.start_date)
        self.class_row(self.year, self.year.start_date)
        self.subject_row(self.old_year, self.history, self.old_year.start_date)
        self.subject_row(
            self.year, self.history, self.year.start_date, self.today - timedelta(days=1)
        )
        html = self.page()
        self.assertIn("Mathematics", html)
        self.assertIn("Mathematics: Grade 6 - A", html)
        self.assertIn("Class teacher: Grade 6 - A", html)
        self.assertNotIn("History", html)
        self.assertIn("2 ongoing assignments", html)
        self.assertIn(reverse("core:teacher-load", args=[self.teacher.pk]), html)
        self.assertIn("View full workload", html)

    def test_deactivate_page_with_no_ongoing_assignments_says_so(self):
        self.subject_row(self.old_year, self.maths, self.old_year.start_date)
        html = self.page()
        self.assertIn("No ongoing assignments.", html)
        self.assertNotIn("Mathematics", html)
