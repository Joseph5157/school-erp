"""Modern web audits 12 (A11Y-03) and 14 (DP-01, DP-02): repeated row actions name their row,
and the Student and Class detail tables carry captions, column scopes and row headers."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Guardian, StudentGuardian
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin

VH = '<span class="visually-hidden">'


def tables(page):
    return re.findall(r"<table.*?</table>", page, re.S)


class StudentDetailTests(AuthorizationClientsMixin, Phase4Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.build_phase4()
        self.student, self.enrollment = self.make_student("Asha Rao")
        guardian = Guardian.objects.create(full_name="Meena Rao")
        StudentGuardian.objects.create(student=self.student, guardian=guardian, relationship_type="MOTHER")
        self.page = self.administrator.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()

    def test_every_student_table_has_a_caption_and_scoped_headers(self):
        found = tables(self.page)
        captions = [re.search(r'<caption class="visually-hidden">([^<]+)</caption>', t) for t in found]
        self.assertEqual([c.group(1) for c in captions if c], ["Status history", "Enrollment history", "Guardians"])
        for table in found:
            head = table.split("</thead>", 1)[0]
            self.assertNotRegex(head, r"<th>|<th></th>")
            self.assertIn('scope="col"', head)

    def test_rows_start_with_a_row_header(self):
        self.assertIn(f'<th scope="row">{self.enrollment.academic_year}</th>', self.page)
        self.assertRegex(self.page, r'<th scope="row"><a href="[^"]+">Meena Rao</a></th>')

    def test_actions_column_has_a_name(self):
        guardians = [t for t in tables(self.page) if ">Guardians</caption>" in t][0]
        self.assertIn(f'<th scope="col">{VH}Actions</span></th>', guardians)

    def test_desktop_edit_and_relationship_links_name_their_row(self):
        self.assertIn(f">Edit{VH} admission number</span></a>", self.page)
        enrollments = [t for t in tables(self.page) if ">Enrollment history</caption>" in t][0]
        self.assertIn(f">Edit{VH} roll number, {self.enrollment.academic_year}</span></a>", enrollments)
        self.assertIn(f">Change relationship{VH} with Meena Rao</span></a>", self.page)
        self.assertNotRegex(self.page, r">(Edit|Change relationship)</a>")


class TemplateNameTests(SimpleTestCase):
    """Pages whose fixtures are heavy: check the template text directly."""

    def read(self, name):
        return Path(settings.BASE_DIR, "core", "templates", "core", name).read_text(encoding="utf-8")

    def test_calendar_actions_name_the_date(self):
        page = self.read("academic_year_calendar.html")
        self.assertIn(f">Edit label{VH} for {{{{ day.date }}}}</span></a>", page)
        self.assertIn(f">Remove{VH} {{{{ day.date }}}}</span></a>", page)

    def test_teacher_assignment_actions_name_the_assignment(self):
        page = self.read("teacher_assignments.html")
        self.assertNotRegex(page, r">(End|Delete planned|Reassign)</(a|button)>")
        self.assertEqual(page.count(f"Delete planned{VH} assignment of "), 2)

    def test_class_sections_table_has_a_caption(self):
        self.assertIn('<caption class="visually-hidden">Sections of {{ class_grade.name }}</caption>',
                      self.read("class_grade_detail.html"))

    def test_retry_button_names_the_student(self):
        js = Path(settings.BASE_DIR, "static", "js", "erp.js").read_text(encoding="utf-8")
        self.assertIn('who.textContent = " saving " + nameOf(row);', js)
        self.assertIn("retry.appendChild(who);", js)
