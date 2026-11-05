"""Task 18: wording from the admin audits. Labels and help text only; stored values are unchanged."""

import datetime

from django.test import TestCase
from django.urls import reverse

from core.forms import AnnouncementForm
from core.models import AcademicTerm, AcademicYear, Applicant, ClassGrade, School, Student, Subject
from core.tests.test_authorization import AuthorizationClientsMixin


class WordingTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.school = School.objects.create(name="Greenwood High")
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 3, 31)
        )

    def page(self, name, *args):
        response = self.administrator.get(reverse(name, args=args))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_school_form_describes_whatsapp_preparation_without_jargon(self):
        page = self.page("core:school-update")
        self.assertIn("Prepare WhatsApp messages for office staff to send", page)
        self.assertNotIn("(ASSIST)", page)
        self.assertIn("It does not send WhatsApp messages automatically.", page)
        self.assertIn("Office staff review the message and record whether it was sent or skipped.", page)
        # The stored value is not renamed.
        self.assertIn('value="ASSIST"', page)

    def test_school_page_describes_whatsapp_preparation_without_jargon(self):
        School.objects.filter(pk=self.school.pk).update(
            notification_channel=School.NotificationMode.ASSIST
        )
        page = self.page("core:school-detail")
        self.assertIn("Prepare WhatsApp messages for office staff to send", page)
        self.assertNotIn("(ASSIST)", page)

    def test_edit_term_page_uses_sentence_case(self):
        term = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=self.year.start_date,
            end_date=self.year.end_date, display_order=1,
        )
        page = self.page("core:term-update", term.pk)
        self.assertIn("Edit term", page)
        self.assertNotIn("Edit Term", page)

    def test_school_form_note_says_when_changes_take_effect(self):
        self.assertIn(
            "Changes appear in the Admin header, future messages and newly issued documents. "
            "Previously issued documents keep their original school details.",
            self.page("core:school-update"),
        )

    def test_timetable_issues_states_its_scope(self):
        self.assertIn(
            "This report checks teacher clashes and scheduled slots without teachers. "
            "It does not assess timetable completeness or required subject hours.",
            self.page("core:timetable-issues", self.year.pk),
        )

    def test_subject_edit_explains_what_inactive_means(self):
        subject = Subject.objects.create(name="English", code="ENG")
        copy = ("Existing offerings, assignments and finalized results remain on record. "
                "An inactive subject cannot be added to a new offering.")
        self.assertIn(copy, self.page("core:subject-update", subject.pk))
        self.assertNotIn(copy, self.page("core:subject-create"))

    def test_class_and_section_forms_give_examples(self):
        grade = ClassGrade.objects.create(name="Grade 1")
        self.assertIn("Examples: Nursery, LKG, Grade 1.", self.page("core:class-grade-create"))
        self.assertIn("Examples: A, B, Morning.", self.page("core:section-create", grade.pk))

    def test_sentence_case_labels(self):
        grade = ClassGrade.objects.create(name="Grade 1")
        applicant = Applicant.objects.create(admission_status="ACCEPTED", full_name="Asha Rao")
        student = Student.objects.create(applicant=applicant, full_name="Asha Rao")
        # A progressed Applicant no longer offers Associate guardian, so these use a pending one.
        pending = Applicant.objects.create(full_name="Ravi Iyer")
        pages = {
            "core:term-create": ((self.year.pk,), ["Add term"], ["Add Term"]),
            "core:subject-create": ((), ["Add subject"], ["Add Subject"]),
            "core:subject-list": ((), ["Add subject", "No subjects yet"], ["Add Subject", "No Subjects yet"]),
            "core:applicant-detail": ((pending.pk,), ["Associate guardian"], ["Associate Guardian"]),
            "core:applicant-guardian-create": (
                (pending.pk,), ["Associate guardian"], ["Associate Guardian"]),
            "core:student-detail": ((student.pk,), ["Associate guardian"], ["Associate Guardian"]),
            "core:student-guardian-add": ((student.pk,), ["Associate guardian"], ["Associate Guardian"]),
            "core:class-grade-create": ((), ["Create class/grade"], ["Create Class/Grade"]),
            "core:class-grade-list": ((), ["Create class/grade"], ["Create Class/Grade"]),
            "core:class-grade-detail": ((grade.pk,), ["Create section"], ["Create Section"]),
            "core:section-create": ((grade.pk,), ["Create section"], ["Create Section"]),
        }
        for name, (args, wanted, unwanted) in pages.items():
            with self.subTest(page=name):
                page = self.page(name, *args)
                for text in wanted:
                    self.assertIn(text, page)
                for text in unwanted:
                    self.assertNotIn(text, page)

    def test_empty_applicant_list_is_sentence_case(self):
        page = self.page("core:applicant-list")
        self.assertIn("No applicants yet.", page)
        self.assertNotIn("No Applicants yet", page)

    def test_sentence_case_in_breadcrumbs(self):
        grade = ClassGrade.objects.create(name="Grade 1")
        subject = Subject.objects.create(name="English", code="ENG")
        for name, args, text in [
            ("core:term-create", (self.year.pk,), "Add term"),
            ("core:class-grade-create", (), "Create class/grade"),
            ("core:section-create", (grade.pk,), "Create section"),
            ("core:subject-create", (), "Add subject"),
            ("core:subject-update", (subject.pk,), "Edit subject"),
        ]:
            with self.subTest(page=name):
                self.assertIn(f'aria-current="page">{text}</li>', self.page(name, *args))

    def test_announcement_form_counters_use_the_form_limits(self):
        page = self.page("core:announcement-create")
        title_max = AnnouncementForm.base_fields["title"].max_length
        body_max = AnnouncementForm.base_fields["body"].max_length
        self.assertIn(f'data-erp-counter-max="{title_max}"', page)
        self.assertIn(f'data-erp-counter-max="{body_max}"', page)
        self.assertIn(f'0 / {title_max}', page)
        self.assertIn(f'0 / {body_max}', page)
        self.assertEqual(page.count("data-erp-counter-for="), 2)
