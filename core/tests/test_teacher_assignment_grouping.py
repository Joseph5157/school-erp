"""Teacher profile and workload page: assignments grouped by subject and dates, clearer headings."""

import re
from datetime import date
from html import unescape

from django.test import TestCase
from django.urls import reverse

from core.models import AcademicSubjectOffering, ClassGrade, Section, SectionClassTeacher
from core.teacher_accounts import group_assignments
from core.tests.test_phase5_assignment_workflows import AssignmentFixture


def text_of(html, sep=" "):
    return " ".join(unescape(re.sub(r"<[^>]+>", sep, html)).split())


class GroupingTests(AssignmentFixture, TestCase):
    def rows(self, teacher=None):
        from core.models import AssessmentTeacherAssignment

        return list(
            AssessmentTeacherAssignment.objects.filter(teacher=teacher or self.rao)
            .select_related("offering__academic_year", "offering__subject", "section__class_grade")
        )

    def test_same_subject_and_dates_combine(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        (group,) = group_assignments(self.rows())
        self.assertEqual(group["subject"], "Mathematics")
        self.assertEqual(group["year"], self.year)
        (grade,) = group["grades"]
        self.assertEqual(grade["grade"], self.grade6)
        self.assertEqual([s.name for s in grade["sections"]], ["A", "B"])

    def test_different_dates_stay_separate(self):
        self.assign(self.rao, self.maths, self.six_a)
        later = self.assign(self.rao, self.maths, self.six_b)
        later.start_date = date(2026, 8, 1)
        later.save()
        groups = group_assignments(self.rows())
        self.assertEqual(len(groups), 2)
        self.assertEqual({g["start"] for g in groups}, {self.year.start_date, date(2026, 8, 1)})

    def test_grades_follow_display_order(self):
        grade2 = ClassGrade.objects.create(name="Zeta grade")
        # Move Grade 6 behind a grade whose name sorts last: order is stored, never by name.
        ClassGrade.objects.filter(pk=self.grade6.pk).update(display_order=50)
        ClassGrade.objects.filter(pk=grade2.pk).update(display_order=2)
        other = Section.objects.create(class_grade=grade2, name="A")
        offering = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=grade2, subject=self.maths_subject
        )
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, offering, other)
        (group,) = group_assignments(self.rows())
        self.assertEqual([g["grade"].name for g in group["grades"]], ["Zeta grade", "Grade 6"])

    def test_class_teacher_is_a_separate_block(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        class_groups = group_assignments(SectionClassTeacher.objects.filter(teacher=self.rao))
        self.assertEqual(len(class_groups), 1)
        self.assertIsNone(class_groups[0]["subject"])
        page = self.client.get(reverse("core:teacher-load", args=[self.rao.pk])).content.decode()
        self.assertLess(page.index("<h3 class=\"h6\">Class teacher"), page.index("<h3 class=\"h6\">Subjects"))
        self.assertEqual(page.count("<h3"), 2)


class WorkloadPageTests(AssignmentFixture, TestCase):
    def load(self):
        response = self.client.get(reverse("core:teacher-load", args=[self.rao.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_workload_title_is_teacher_workload(self):
        page = self.load()
        self.assertEqual(page.count("<h1"), 1)
        self.assertRegex(page, r'<h1 class="erp-page-title">Teacher workload</h1>')
        start = page.index('<header class="erp-page-header">')
        header = page[start:page.index("</header>", start)]
        words = text_of(header)
        self.assertIn(self.rao.get_full_name() or self.rao.username, words)
        self.assertIn(self.rao.username, words)
        self.assertIn("Active teacher", words)
        self.assertLess(words.index("Teacher workload"), words.index(self.rao.username))

    def test_open_ended_reads_ongoing(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        page = self.load()
        self.assertIn("Ongoing", page)
        self.assertNotIn("open", text_of(page[page.index("<main"):]).replace("Open menu", ""))

    def test_workload_links_to_academic_years(self):
        page = self.load()
        self.assertIn("Assignments are managed from Academic Years.", text_of(page, sep=""))
        self.assertIn(f'href="{reverse("core:academic-year-list")}"', page)

    def test_grouped_rows_show_grade_and_sections_once(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        page = self.load()
        self.assertEqual(text_of(page).count("Mathematics"), 1)
        self.assertIn("Grade 6: A, B", text_of(page))

    def test_long_name_line_is_scoped_for_wrapping(self):
        self.rao.first_name = "x" * 60
        self.rao.save()
        page = self.load()
        self.assertIn('class="erp-teacher-page"', page)
        self.assertIn("x" * 60, page)


class ProfileTests(AssignmentFixture, TestCase):
    def profile(self):
        return self.client.get(reverse("core:teacher-detail", args=[self.rao.pk])).content.decode()

    def test_profile_groups_the_same_way(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        self.class_teacher(self.rao, self.six_a)
        words = text_of(self.profile())
        self.assertEqual(words.count("Mathematics"), 1)
        self.assertIn("Grade 6: A, B", words)
        self.assertIn("Ongoing", words)

    def test_deactivate_is_separated_from_routine_actions(self):
        page = self.profile()
        zone = re.search(r'<div class="erp-danger-zone[^"]*">(.*?)</div>', page, re.S)
        self.assertIsNotNone(zone)
        self.assertIn("Deactivate", zone.group(1))
        self.assertNotIn("Reset password", zone.group(1))
        self.assertLess(page.index("Change username"), page.index('class="erp-danger-zone'))

    def test_account_values_wrap(self):
        self.assertIn('<dl class="row mb-0 erp-teacher-account">', self.profile())
