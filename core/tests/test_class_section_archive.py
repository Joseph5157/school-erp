"""Archiving a Class/Grade or Section (ADR 0025).

An archived record cannot be picked for anything new, while everything already recorded
against it stays reachable. It cannot be archived while it is in current use.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import assignments, imports
from core import forms as core_forms
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    ClassGrade,
    GradingScale,
    Section,
    SectionClassTeacher,
    Student,
    Subject,
    TimetablePeriod,
    TimetableSlot,
    business_today,
)

User = get_user_model()


class ArchiveFixture:
    def setUp(self):
        super().setUp()
        self.today = business_today()
        self.year = AcademicYear.objects.create(
            name="Current",
            start_date=self.today - timedelta(days=30),
            end_date=self.today + timedelta(days=200),
        )
        self.past_year = AcademicYear.objects.create(
            name="Past",
            start_date=self.today - timedelta(days=400),
            end_date=self.today - timedelta(days=100),
        )
        self.term = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=self.year.start_date,
            end_date=self.year.end_date, display_order=1,
        )
        self.grade = ClassGrade.objects.create(name="Grade 1")
        self.other_grade = ClassGrade.objects.create(name="Grade 2")
        self.section = Section.objects.create(class_grade=self.grade, name="A")
        self.neighbour = Section.objects.create(class_grade=self.grade, name="B")
        self.subject = Subject.objects.create(name="Mathematics")
        self.offering = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade, subject=self.subject
        )
        self.admin = User.objects.create_user("administrator", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(self.admin)
        self.teacher = User.objects.create_user("teacher", password="pass-12345")
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))

    def student(self, name="Asha Rao", *, section=None, year=None, start=None):
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name=name),
            full_name=name,
        )
        year = year or self.year
        student.enroll(
            academic_year=year, class_grade=self.grade, section=section or self.section,
            start_date=start or year.start_date,
        )
        return student

    def class_teacher(self, *, year=None, end_date=None):
        year = year or self.year
        return SectionClassTeacher.objects.create(
            teacher=self.teacher, academic_year=year, section=self.section,
            start_date=year.start_date, end_date=end_date,
        )

    def subject_teacher(self, *, end_date=None):
        return AssessmentTeacherAssignment.objects.create(
            teacher=self.teacher, offering=self.offering, section=self.section,
            start_date=self.year.start_date, end_date=end_date,
        )

    def slot(self, *, end_date=None):
        period = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        return TimetableSlot.objects.create(
            period=period, weekday=0, section=self.section, offering=self.offering,
            start_date=self.year.start_date, end_date=end_date,
        )

    def archive_section(self, section=None):
        section = section or self.section
        return self.client.post(reverse("core:section-archive", args=[section.pk]))

    def archive_grade(self, grade=None):
        grade = grade or self.grade
        return self.client.post(reverse("core:class-grade-archive", args=[grade.pk]))

    def assert_section_archived(self, section=None, archived=True):
        section = section or self.section
        section.refresh_from_db()
        self.assertEqual(section.archived_at is not None, archived)


class ArchiveSectionTests(ArchiveFixture, TestCase):
    def test_confirm_page_saves_nothing_and_explains_the_effect(self):
        response = self.client.get(reverse("core:section-archive", args=[self.section.pk]))
        self.assertContains(response, "cannot be picked for anything new")
        self.assertContains(response, '<p class="erp-page-purpose">Grade 1</p>')
        self.assert_section_archived(archived=False)

    def test_archive_records_when_and_who(self):
        response = self.archive_section()
        self.assertRedirects(
            response, reverse("core:class-grade-detail", args=[self.grade.pk]),
            fetch_redirect_response=False,
        )
        self.section.refresh_from_db()
        self.assertIsNotNone(self.section.archived_at)
        self.assertEqual(self.section.archived_by, self.admin)

    def test_archive_leaves_the_other_section_alone(self):
        self.archive_section()
        self.assert_section_archived(self.neighbour, archived=False)

    def test_student_placed_here_blocks_and_is_named(self):
        self.student()
        response = self.archive_section()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 student")
        self.assert_section_archived(archived=False)

    def test_blocked_page_offers_no_archive_button(self):
        self.student()
        response = self.client.get(reverse("core:section-archive", args=[self.section.pk]))
        self.assertNotContains(response, 'name="confirm_archive"')

    def test_current_class_teacher_blocks(self):
        self.class_teacher()
        self.assertContains(self.archive_section(), "class teacher")
        self.assert_section_archived(archived=False)

    def test_current_subject_teacher_blocks(self):
        self.subject_teacher()
        self.assertContains(self.archive_section(), "subject teacher")
        self.assert_section_archived(archived=False)

    def test_current_timetable_slot_blocks(self):
        self.slot()
        self.assertContains(self.archive_section(), "timetable")
        self.assert_section_archived(archived=False)

    def test_placement_in_an_ended_year_does_not_block(self):
        self.student(year=self.past_year)
        self.archive_section()
        self.assert_section_archived()

    def test_placement_that_finished_this_year_does_not_block(self):
        student = self.student()
        student.enroll(
            academic_year=self.year, class_grade=self.grade, section=self.neighbour,
            start_date=self.today, access_decisions={},
        )
        self.archive_section()
        self.assert_section_archived()

    def test_assignments_already_ended_do_not_block(self):
        yesterday = self.today - timedelta(days=1)
        self.class_teacher(end_date=yesterday)
        self.subject_teacher(end_date=yesterday)
        self.slot(end_date=yesterday)
        self.archive_section()
        self.assert_section_archived()

    def test_archiving_twice_keeps_the_first_record(self):
        self.archive_section()
        self.section.refresh_from_db()
        first = self.section.archived_at
        self.archive_section()
        self.section.refresh_from_db()
        self.assertEqual(self.section.archived_at, first)


class ArchiveClassTests(ArchiveFixture, TestCase):
    def test_archiving_a_class_also_archives_its_sections(self):
        self.archive_grade()
        self.grade.refresh_from_db()
        self.assertIsNotNone(self.grade.archived_at)
        self.assert_section_archived()
        self.assert_section_archived(self.neighbour)

    def test_one_busy_section_blocks_the_whole_class(self):
        self.student(section=self.neighbour)
        response = self.archive_grade()
        self.assertContains(response, "1 student")
        self.grade.refresh_from_db()
        self.assertIsNone(self.grade.archived_at)
        self.assert_section_archived(archived=False)

    def test_other_classes_are_untouched(self):
        self.archive_grade()
        self.other_grade.refresh_from_db()
        self.assertIsNone(self.other_grade.archived_at)

    def test_archived_class_cannot_take_a_new_section(self):
        self.archive_grade()
        url = reverse("core:section-create", args=[self.grade.pk])
        self.client.post(url, {"name": "C"})
        self.assertFalse(Section.objects.filter(class_grade=self.grade, name="C").exists())


class RestoreTests(ArchiveFixture, TestCase):
    def restore_section(self, section=None):
        section = section or self.section
        return self.client.post(reverse("core:section-restore", args=[section.pk]))

    def restore_grade(self):
        return self.client.post(reverse("core:class-grade-restore", args=[self.grade.pk]))

    def test_restore_section_clears_the_archive_record(self):
        self.archive_section()
        self.restore_section()
        self.section.refresh_from_db()
        self.assertIsNone(self.section.archived_at)
        self.assertIsNone(self.section.archived_by)

    def test_section_cannot_be_restored_into_an_archived_class(self):
        self.archive_grade()
        self.restore_section()
        self.assert_section_archived()

    def test_restoring_a_class_restores_the_sections_archived_with_it(self):
        self.archive_grade()
        self.restore_grade()
        self.grade.refresh_from_db()
        self.assertIsNone(self.grade.archived_at)
        self.assert_section_archived(archived=False)
        self.assert_section_archived(self.neighbour, archived=False)

    def test_restoring_a_class_leaves_a_section_archived_earlier(self):
        self.archive_section()
        self.archive_grade()
        self.restore_grade()
        self.assert_section_archived()
        self.assert_section_archived(self.neighbour, archived=False)

    def test_restore_needs_a_post(self):
        self.archive_section()
        response = self.client.get(reverse("core:section-restore", args=[self.section.pk]))
        self.assertEqual(response.status_code, 405)
        self.assert_section_archived()


class PermissionTests(ArchiveFixture, TestCase):
    def setUp(self):
        super().setUp()
        viewer = User.objects.create_user("viewer", password="pass-12345")
        viewer.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_classgrade", "view_section"])
        )
        self.viewer = self.client_class()
        self.viewer.force_login(viewer)

    def test_viewer_cannot_archive_or_restore(self):
        self.assertEqual(
            self.viewer.post(reverse("core:section-archive", args=[self.section.pk])).status_code, 403
        )
        self.assertEqual(
            self.viewer.post(reverse("core:class-grade-archive", args=[self.grade.pk])).status_code, 403
        )
        self.archive_section()
        self.assertEqual(
            self.viewer.post(reverse("core:section-restore", args=[self.section.pk])).status_code, 403
        )
        self.assert_section_archived()

    def test_viewer_sees_no_archive_links(self):
        response = self.viewer.get(reverse("core:class-grade-detail", args=[self.grade.pk]))
        self.assertNotContains(response, reverse("core:section-archive", args=[self.section.pk]))
        self.assertNotContains(response, reverse("core:class-grade-archive", args=[self.grade.pk]))

    def test_administrator_sees_archive_links(self):
        response = self.client.get(reverse("core:class-grade-detail", args=[self.grade.pk]))
        self.assertContains(response, reverse("core:section-archive", args=[self.section.pk]))
        self.assertContains(response, reverse("core:class-grade-archive", args=[self.grade.pk]))


class PagesTests(ArchiveFixture, TestCase):
    def test_class_page_groups_archived_sections_with_a_restore_button(self):
        self.archive_section()
        response = self.client.get(reverse("core:class-grade-detail", args=[self.grade.pk]))
        self.assertContains(response, "Archived sections")
        self.assertContains(response, reverse("core:section-restore", args=[self.section.pk]))
        self.assertNotContains(response, reverse("core:section-archive", args=[self.section.pk]))

    def test_class_list_groups_archived_classes_and_counts_active_sections(self):
        self.archive_section()
        self.archive_grade(self.other_grade)
        response = self.client.get(reverse("core:class-grade-list"))
        self.assertEqual([g.name for g in response.context["class_grades"]], ["Grade 1"])
        self.assertEqual([g.name for g in response.context["archived_classes"]], ["Grade 2"])
        self.assertEqual(response.context["class_grades"][0].sections.active().count(), 1)
        self.assertContains(response, "Archived classes")

    def test_reordering_active_classes_still_works_with_one_archived(self):
        third = ClassGrade.objects.create(name="Grade 3")
        self.archive_grade(self.other_grade)
        self.client.post(
            reverse("core:class-grade-reorder"), {"class_grade": [third.pk, self.grade.pk]}
        )
        third.refresh_from_db()
        self.grade.refresh_from_db()
        self.assertLess(third.display_order, self.grade.display_order)

    def test_archived_section_stays_on_a_past_placement(self):
        student = self.student(year=self.past_year)
        self.archive_grade()
        response = self.client.get(reverse("core:student-detail", args=[student.pk]))
        self.assertContains(response, "Grade 1")

    def test_archived_class_page_still_opens_and_says_so(self):
        self.archive_grade()
        response = self.client.get(reverse("core:class-grade-detail", args=[self.grade.pk]))
        self.assertContains(response, "Archived")
        self.assertContains(response, reverse("core:class-grade-restore", args=[self.grade.pk]))
        self.assertNotContains(response, reverse("core:section-create", args=[self.grade.pk]))

    def test_timetable_list_leaves_out_archived_sections(self):
        self.archive_section()
        response = self.client.get(reverse("core:timetable-sections", args=[self.year.pk]))
        self.assertEqual(list(response.context["sections"]), [self.neighbour])

    def test_class_teacher_page_leaves_out_an_archived_section_without_history(self):
        self.archive_section()
        response = self.client.get(reverse("core:academic-year-class-teachers", args=[self.year.pk]))
        self.assertEqual([row["section"] for row in response.context["sections"]], [self.neighbour])

    def test_assignment_overview_reports_no_gap_for_an_archived_section(self):
        self.archive_section()
        overview = assignments.overview(self.year, self.today)
        self.assertEqual([row["section"] for row in overview["class_rows"]], [self.neighbour])
        self.assertEqual([row["section"] for row in overview["subject_rows"]], [self.neighbour])

    def test_assignment_overview_leaves_out_an_archived_linked_section(self):
        self.offering.set_sections([self.section, self.neighbour])
        self.archive_section()
        overview = assignments.overview(self.year, self.today)
        self.assertEqual([row["section"] for row in overview["subject_rows"]], [self.neighbour])


class PickListTests(ArchiveFixture, TestCase):
    """New work offers only active records."""

    def setUp(self):
        super().setUp()
        self.archive_section()
        self.archive_grade(self.other_grade)

    def assert_offers_active_sections_only(self, queryset):
        self.assertIn(self.neighbour, queryset)
        self.assertNotIn(self.section, queryset)

    def assert_offers_active_classes_only(self, queryset):
        self.assertIn(self.grade, queryset)
        self.assertNotIn(self.other_grade, queryset)

    def test_placing_a_student(self):
        form = core_forms.AcademicEnrollmentForm()
        self.assert_offers_active_classes_only(form.fields["class_grade"].queryset)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_opening_a_register(self):
        form = core_forms.AttendanceRegisterForm()
        self.assert_offers_active_classes_only(form.fields["class_grade"].queryset)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_offering_a_subject(self):
        form = core_forms.SubjectOfferingForm(academic_year=self.year)
        self.assert_offers_active_classes_only(form.fields["class_grade"].queryset)
        self.assert_offers_active_sections_only(form.fields["sections"].queryset)

    def test_assigning_a_class_teacher(self):
        form = core_forms.ClassTeacherAssignForm(academic_year=self.year)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_assigning_a_subject_teacher(self):
        form = core_forms.TeacherAssignmentForm(academic_year=self.year)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_grading_scale(self):
        form = core_forms.GradingScaleForm(academic_year=self.year)
        self.assert_offers_active_classes_only(form.fields["class_grades"].queryset)

    def test_new_assessment(self):
        form = core_forms.AssessmentForm(academic_year=self.year)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_announcement(self):
        form = core_forms.AnnouncementForm()
        self.assert_offers_active_classes_only(form.fields["class_grade"].queryset)
        self.assert_offers_active_sections_only(form.fields["section"].queryset)

    def test_a_posted_archived_section_is_refused(self):
        form = core_forms.AcademicEnrollmentForm(
            {"academic_year": self.year.pk, "class_grade": self.grade.pk,
             "section": self.section.pk, "start_date": self.today.isoformat()}
        )
        self.assertIn("section", form.errors)


class EditingOldRecordsTests(ArchiveFixture, TestCase):
    """An old record keeps showing what it already uses, so editing cannot silently drop it."""

    def test_editing_an_assessment_keeps_its_archived_section(self):
        assessment = Assessment.objects.create(
            term=self.term, offering=self.offering, section=self.section, name="Unit 1",
            assessment_date=self.today, maximum_marks=20,
        )
        self.archive_section()
        form = core_forms.AssessmentForm(instance=assessment)
        self.assertIn(self.section, form.fields["section"].queryset)
        self.assertIn(self.neighbour, form.fields["section"].queryset)

    def test_editing_an_offering_keeps_its_archived_section(self):
        self.offering.set_sections([self.section])
        self.archive_section()
        form = core_forms.SubjectOfferingForm(academic_year=self.year, offering=self.offering)
        self.assertIn(self.section, form.fields["sections"].queryset)

    def test_editing_an_offering_hides_an_unrelated_archived_section(self):
        self.offering.set_sections([self.neighbour])
        self.archive_section()
        form = core_forms.SubjectOfferingForm(academic_year=self.year, offering=self.offering)
        self.assertNotIn(self.section, form.fields["sections"].queryset)

    def test_editing_a_scale_keeps_its_archived_class(self):
        scale = GradingScale.objects.create(academic_year=self.year, name="Scale")
        scale.set_class_grades([self.other_grade])
        self.archive_grade(self.other_grade)
        form = core_forms.GradingScaleForm(academic_year=self.year, scale=scale)
        self.assertIn(self.other_grade, form.fields["class_grades"].queryset)


class HistoryFiltersTests(ArchiveFixture, TestCase):
    """Looking things up still reaches archived records."""

    def setUp(self):
        super().setUp()
        self.archive_section()

    def test_filters_still_offer_archived_sections(self):
        for form in (
            core_forms.AssessmentFilterForm(academic_year=self.year),
            core_forms.AttendanceRegisterFilterForm(),
            core_forms.MonthlySectionSummaryForm(),
            core_forms.AttendanceSummaryForm(),
        ):
            with self.subTest(form=type(form).__name__):
                self.assertIn(self.section, form.fields["section"].queryset)


class ModelGuardTests(ArchiveFixture, TestCase):
    """Any path that validates a new record is refused, not only the forms."""

    def setUp(self):
        super().setUp()
        self.existing = self.student(year=self.past_year)
        self.archive_section()
        self.section.refresh_from_db()

    def assert_refused(self, record):
        with self.assertRaisesMessage(ValidationError, "archived"):
            record.full_clean()

    def test_enrolling_through_the_model_is_refused(self):
        student = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="New One"),
            full_name="New One",
        )
        with self.assertRaisesMessage(ValidationError, "archived"):
            student.enroll(
                academic_year=self.year, class_grade=self.grade, section=self.section,
                start_date=self.today,
            )

    def test_new_register_is_refused(self):
        self.assert_refused(AttendanceRegister(
            academic_year=self.year, class_grade=self.grade, section=self.section, date=self.today
        ))

    def test_new_class_teacher_is_refused(self):
        self.assert_refused(SectionClassTeacher(
            teacher=self.teacher, academic_year=self.year, section=self.section,
            start_date=self.today,
        ))

    def test_new_subject_teacher_is_refused(self):
        self.assert_refused(AssessmentTeacherAssignment(
            teacher=self.teacher, offering=self.offering, section=self.section,
            start_date=self.today,
        ))

    def test_new_assessment_is_refused(self):
        self.assert_refused(Assessment(
            term=self.term, offering=self.offering, section=self.section, name="Unit",
            assessment_date=self.today, maximum_marks=20,
        ))

    def test_new_timetable_slot_is_refused(self):
        period = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.assert_refused(TimetableSlot(
            period=period, weekday=0, section=self.section, offering=self.offering,
            start_date=self.today,
        ))

    def test_an_existing_record_can_still_be_validated(self):
        enrollment = self.existing.enrollments.get()
        enrollment.full_clean()


class DatabaseRuleTests(ArchiveFixture, TestCase):
    def test_archive_record_must_be_complete(self):
        for model, record in ((Section, self.section), (ClassGrade, self.grade)):
            with self.subTest(model=model.__name__), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    model.objects.filter(pk=record.pk).update(archived_at=timezone.now())


class CopyFromLastYearTests(ArchiveFixture, TestCase):
    def test_copy_skips_an_archived_section_and_says_why(self):
        self.class_teacher(year=self.past_year, end_date=None)
        self.archive_section()
        plan = assignments.plan_copy(self.past_year, self.year)
        self.assertEqual(plan["copies"], [])
        self.assertIn("archived", plan["skips"][0].reason)


class ImportTests(ArchiveFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.archive_section()

    def messages(self, sheets):
        _plan, issues = imports.validate(sheets, self.year, self.today)
        return [issue.message for issue in issues if issue.level == "ERROR"]

    def test_classes_sheet_naming_an_archived_section_is_an_error(self):
        errors = self.messages({imports.SHEET_CLASSES: [(2, {"class": "Grade 1", "section": "a"})]})
        self.assertTrue(any("archived" in message for message in errors), errors)

    def test_classes_sheet_naming_an_archived_class_is_an_error(self):
        self.archive_grade(self.other_grade)
        errors = self.messages({imports.SHEET_CLASSES: [(2, {"class": "Grade 2", "section": "Z"})]})
        self.assertTrue(any("archived" in message for message in errors), errors)

    def test_students_sheet_naming_an_archived_section_is_an_error(self):
        errors = self.messages({imports.SHEET_STUDENTS: [
            (2, {"full_name": "New One", "class": "Grade 1", "section": "A"})
        ]})
        self.assertTrue(any("archived" in message for message in errors), errors)
