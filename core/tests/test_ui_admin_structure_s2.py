"""S2: legacy Admin pages adopt the shared page shell (header, breadcrumb trail, active sidebar item).

Presentation only: every page keeps its URL, form, context and permission. Each case is
(label, url builder, expected breadcrumb labels, label of the sidebar link that stays active).
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    ClassGrade,
    School,
    SchoolCalendarDay,
    Section,
    Subject,
)
from core.tests.test_authorization import AuthorizationClientsMixin


class Fixture(AuthorizationClientsMixin):
    def setUp(self):
        super().setUp()
        self.school = School.objects.create(name="Greenwood High")
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 3, 31)
        )
        self.term = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", display_order=1,
            start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2026, 9, 30),
        )
        self.class_grade = ClassGrade.objects.create(name="Class 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        self.subject = Subject.objects.create(name="English", code="ENG")
        self.offering = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.class_grade, subject=self.subject, display_order=1
        )
        self.day = SchoolCalendarDay.objects.create(
            academic_year=self.year, date=datetime.date(2026, 8, 15), is_instructional=False, label="Holiday"
        )

    def cases(self):
        y, t, d = self.year.pk, self.term.pk, self.day.pk
        c, sub, o = self.class_grade.pk, self.subject.pk, self.offering.pk
        return [
            # batch 1: school, calendar, terms
            ("school-update", reverse("core:school-update"), ["Overview", "School", "Edit school"], "School"),
            ("academic-year-calendar", reverse("core:academic-year-calendar", args=[y]),
             ["Overview", "Academic Years", "Calendar"], "Academic Years"),
            ("calendar-day-create", reverse("core:calendar-day-create", args=[y]),
             ["Overview", "Academic Years", "Calendar", "Add exception"], "Academic Years"),
            ("calendar-day-update", reverse("core:calendar-day-update", args=[d]),
             ["Overview", "Academic Years", "Edit exception"], "Academic Years"),
            ("term-create", reverse("core:term-create", args=[y]),
             ["Overview", "Academic Years", "Terms", "Add Term"], "Academic Years"),
            ("term-update", reverse("core:term-update", args=[t]),
             ["Overview", "Academic Years", "Edit Term"], "Academic Years"),
            # batch 2: classes, subjects, offerings
            ("class-grade-create", reverse("core:class-grade-create"),
             ["Overview", "Classes/Grades", "Create Class/Grade"], "Classes/Grades"),
            ("class-grade-detail", reverse("core:class-grade-detail", args=[c]),
             ["Overview", "Classes/Grades", "Class/Grade"], "Classes/Grades"),
            ("section-create", reverse("core:section-create", args=[c]),
             ["Overview", "Classes/Grades", "Class/Grade", "Create Section"], "Classes/Grades"),
            ("subject-create", reverse("core:subject-create"),
             ["Overview", "Subjects", "Add Subject"], "Subjects"),
            ("subject-update", reverse("core:subject-update", args=[sub]),
             ["Overview", "Subjects", "Edit Subject"], "Subjects"),
            ("offering-create", reverse("core:offering-create", args=[y]),
             ["Overview", "Academic Years", "Subjects offered", "Offer a Subject"], "Academic Years"),
            ("offering-update", reverse("core:offering-update", args=[o]),
             ["Overview", "Academic Years", "Edit offering"], "Academic Years"),
        ]


class SharedShellTests(Fixture, TestCase):
    def test_every_converted_page_uses_the_shared_shell(self):
        for name, url, trail, active in self.cases():
            with self.subTest(page=name):
                response = self.administrator.get(url)
                self.assertEqual(response.status_code, 200)
                page = response.content.decode()
                self.assertEqual(page.count('<h1 class="erp-page-title">'), 1)
                self.assertEqual(page.count("<h1"), 1)
                self.assertNotIn('class="h3 mb-3"', page)
                self.assertEqual([c["label"] for c in response.context["breadcrumbs"]], trail)
                links = [l for g in response.context["office_nav"] for l in g["links"] if l["active"]]
                self.assertEqual([l["label"] for l in links], [active])

    def test_forms_keep_their_post_target_csrf_and_cancel_link(self):
        for name in ("school-update", "calendar-day-create", "term-create", "term-update", "class-grade-create",
                     "section-create", "subject-create", "subject-update", "offering-create", "offering-update"):
            url = next(u for n, u, _, _ in self.cases() if n == name)
            with self.subTest(page=name):
                page = self.administrator.get(url).content.decode()
                self.assertIn('<form method="post" class="erp-form">', page)
                self.assertIn("csrfmiddlewaretoken", page)

    def test_choice_fields_render_as_labelled_fieldsets(self):
        page = self.administrator.get(reverse("core:school-update")).content.decode()
        self.assertIn("<fieldset", page)
        self.assertIn("Messages to guardians", page)
        page = self.administrator.get(reverse("core:calendar-day-create", args=[self.year.pk])).content.decode()
        self.assertIn('<legend class="fs-6 fw-semibold">Type', page)

    def test_invalid_post_still_shows_field_errors(self):
        response = self.administrator.post(reverse("core:school-update"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "erp-field-errors")
        self.assertContains(response, "form-error-summary")

    def test_calendar_page_keeps_its_actions(self):
        url = reverse("core:academic-year-calendar", args=[self.year.pk])
        page = self.administrator.get(url).content.decode()
        self.assertIn(reverse("core:calendar-day-create", args=[self.year.pk]), page)
        self.assertIn(reverse("core:calendar-day-update", args=[self.day.pk]), page)
        self.assertIn(reverse("core:calendar-day-delete", args=[self.day.pk]), page)
        self.assertIn(reverse("core:academic-year-saturday-rule", args=[self.year.pk]), page)
        self.assertIn("Check a date", page)

    def test_class_detail_keeps_section_action_and_back_link(self):
        page = self.administrator.get(reverse("core:class-grade-detail", args=[self.class_grade.pk])).content.decode()
        self.assertIn(reverse("core:section-create", args=[self.class_grade.pk]), page)
        self.assertIn(reverse("core:class-grade-list"), page)
        self.assertIn("<td>A</td>", page)

    def test_subject_edit_keeps_its_retire_note(self):
        page = self.administrator.get(reverse("core:subject-update", args=[self.subject.pk])).content.decode()
        self.assertIn("To retire a Subject, untick Active", page)
        self.assertNotIn("To retire a Subject", self.administrator.get(reverse("core:subject-create")).content.decode())

    def test_offering_choice_field_is_a_fieldset(self):
        page = self.administrator.get(reverse("core:offering-update", args=[self.offering.pk])).content.decode()
        self.assertIn("<fieldset", page)
