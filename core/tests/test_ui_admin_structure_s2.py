"""S2: legacy Admin pages adopt the shared page shell (header, breadcrumb trail, active sidebar item).

Presentation only: every page keeps its URL, form, context and permission. Each case is
(label, url builder, expected breadcrumb labels, label of the sidebar link that stays active).
"""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core import guardian_accounts as ga
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    AssessmentTeacherAssignment,
    ClassGrade,
    Guardian,
    GuardianAccount,
    School,
    SchoolCalendarDay,
    Section,
    SectionClassTeacher,
    Student,
    Subject,
    TimetablePeriod,
)
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()


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
        self.offering.set_sections([self.section])
        self.teacher = User.objects.create_user(username="iyer", password="pass-12345")
        self.teacher.groups.add(Group.objects.get_or_create(name=TEACHERS_GROUP_NAME)[0])
        self.class_assignment = SectionClassTeacher.assign(
            teacher=self.teacher, academic_year=self.year, section=self.section,
            start_date=datetime.date(2026, 6, 1),
        )
        self.subject_assignment = AssessmentTeacherAssignment.objects.create(
            teacher=self.teacher, offering=self.offering, section=self.section,
            start_date=datetime.date(2026, 6, 1),
        )
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345")
        self.account, _ = ga.create_guardian_account(
            guardian=self.guardian, username="meena.rao",
            method=GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS,
            note="Aadhaar card seen by office", actor=self.admin_user,
        )
        self.student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Asha Rao"),
            full_name="Asha Rao",
        )
        self.period = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.day = SchoolCalendarDay.objects.create(
            academic_year=self.year, date=datetime.date(2026, 8, 15), is_instructional=False, label="Holiday"
        )

    def cases(self):
        y, t, d = self.year.pk, self.term.pk, self.day.pk
        c, sub, o = self.class_grade.pk, self.subject.pk, self.offering.pk
        ca, sa, tp = self.class_assignment.pk, self.subject_assignment.pk, self.teacher.pk
        acc, stu, per = self.account.pk, self.student.pk, self.period.pk
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
            # batch 3: assignments and year-scoped lists
            ("terms-list", reverse("core:academic-year-terms", args=[y]),
             ["Overview", "Academic Years", "Terms"], "Academic Years"),
            ("offerings-list", reverse("core:academic-year-offerings", args=[y]),
             ["Overview", "Academic Years", "Subjects offered"], "Academic Years"),
            ("class-teachers-list", reverse("core:academic-year-class-teachers", args=[y]),
             ["Overview", "Academic Years", "Class teachers"], "Academic Years"),
            ("subject-teachers-list", reverse("core:academic-year-teacher-assignments", args=[y]),
             ["Overview", "Academic Years", "Subject teachers"], "Academic Years"),
            ("assignment-overview", reverse("core:academic-year-assignments", args=[y]),
             ["Overview", "Academic Years", "Assignment overview"], "Academic Years"),
            ("class-teacher-assign", reverse("core:class-teacher-assign", args=[y]),
             ["Overview", "Academic Years", "Class teachers", "Assign class teacher"], "Academic Years"),
            ("class-teacher-end", reverse("core:class-teacher-end", args=[ca]),
             ["Overview", "Academic Years", "End class teacher assignment"], "Academic Years"),
            ("teacher-assignment-create", reverse("core:teacher-assignment-create", args=[y]),
             ["Overview", "Academic Years", "Subject teachers", "Assign a teacher"], "Academic Years"),
            ("teacher-assignment-end", reverse("core:teacher-assignment-end", args=[sa]),
             ["Overview", "Academic Years", "End teacher assignment"], "Academic Years"),
            ("assignment-copy", reverse("core:assignment-copy", args=[y]),
             ["Overview", "Academic Years", "Assignment overview", "Copy assignments"], "Academic Years"),
            ("teacher-load", reverse("core:teacher-load", args=[tp]),
             ["Overview", "Teachers", "Teacher", "Workload"], "Teachers"),
            # batch 4: account confirms and identifiers; batch 5: deletes
            ("teacher-reset-password", reverse("core:teacher-reset-password", args=[tp]),
             ["Overview", "Teachers", "Teacher", "Reset password"], "Teachers"),
            ("teacher-reactivate", reverse("core:teacher-reactivate", args=[tp]),
             ["Overview", "Teachers", "Teacher", "Reactivate"], "Teachers"),
            ("guardian-account-reset-password", reverse("core:guardian-account-reset-password", args=[acc]),
             ["Overview", "Guardians", "Reset password"], "Guardians"),
            ("guardian-account-username", reverse("core:guardian-account-username", args=[acc]),
             ["Overview", "Guardians", "Change username"], "Guardians"),
            ("guardian-account-revoke", reverse("core:guardian-account-revoke", args=[acc]),
             ["Overview", "Guardians", "Revoke account"], "Guardians"),
            ("student-admission-number", reverse("core:student-admission-number", args=[stu]),
             ["Overview", "Students", "Student", "Admission number"], "Students"),
            ("timetable-period-delete", reverse("core:timetable-period-delete", args=[per]),
             ["Overview", "Timetable", "Delete period"], "Timetable"),
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
                     "section-create", "subject-create", "subject-update", "offering-create", "offering-update",
                     "class-teacher-assign", "class-teacher-end", "teacher-assignment-create",
                     "teacher-assignment-end", "guardian-account-username"):
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
        self.assertIn('<button type="submit" class="btn btn-outline-secondary">Check</button>', page)

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
