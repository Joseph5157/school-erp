"""Shared Phase 4 test fixtures."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    Assessment,
    AssessmentTeacherAssignment,
    ClassGrade,
    GradeBoundary,
    GradingScale,
    Section,
    Student,
    Subject,
)

User = get_user_model()


class Phase4Fixture:
    """Year 2026-27 with Term 1 (Jun-Sep) and Term 2 (Oct-Dec), Grade 6 A/B,
    Mathematics (all Sections) and Sanskrit (6B only), teachers Rao and Iyer."""

    def build_phase4(self):
        self.admins = Group.objects.get(name="School Administrators")
        self.teachers = Group.objects.get(name=TEACHERS_GROUP_NAME)
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        self.term1 = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 6, 1),
            end_date=date(2026, 9, 30), display_order=1,
        )
        self.term2 = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 2", start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31), display_order=2,
        )
        self.grade6 = ClassGrade.objects.create(name="Grade 6")
        self.six_a = Section.objects.create(class_grade=self.grade6, name="A")
        self.six_b = Section.objects.create(class_grade=self.grade6, name="B")
        self.maths_subject = Subject.objects.create(name="Mathematics")
        self.maths = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6, subject=self.maths_subject
        )
        self.sanskrit = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Sanskrit"),
        )
        self.sanskrit.set_sections([self.six_b])
        self.admin = self.make_user("admin", self.admins)
        self.rao = self.make_user("rao", self.teachers)
        self.iyer = self.make_user("iyer", self.teachers)

    def make_user(self, username, *groups, **extra):
        user = User.objects.create_user(username=username, password="pass-12345", **extra)
        user.groups.add(*groups)
        return user

    def make_assessment(self, offering=None, section=None, term=None, name="Unit Test 1",
                        on=date(2026, 7, 15), maximum="20", pass_mark=None):
        assessment = Assessment(
            term=term or self.term1,
            offering=offering or self.maths,
            section=section or self.six_a,
            name=name,
            assessment_date=on,
            maximum_marks=Decimal(maximum),
            pass_mark=Decimal(pass_mark) if pass_mark is not None else None,
        )
        assessment.full_clean()
        assessment.save()
        return assessment

    def make_student(self, name, section=None, start=date(2026, 6, 1)):
        student = Student.objects.create(
            applicant=Applicant.objects.create(
                admission_status="ACCEPTED", full_name=name
            ), full_name=name
        )
        enrollment = student.enroll(
            academic_year=self.year,
            class_grade=self.grade6,
            section=section or self.six_a,
            start_date=start,
        )
        return student, enrollment

    def assign(self, teacher, offering, section):
        return AssessmentTeacherAssignment.objects.create(
            teacher=teacher, offering=offering, section=section,
            start_date=self.year.start_date,
        )

    def force_finalize(self, assessment):
        """Mark finalized directly (bypassing the workflow) for lock tests."""
        from django.utils import timezone

        Assessment.objects.filter(pk=assessment.pk).update(
            status=Assessment.Status.FINALIZED, finalized_by=self.admin,
            finalized_at=timezone.now(), subject_label=assessment.offering.subject.name,
        )
        assessment.refresh_from_db()

    def make_scale(self, bands=((90, "A"), (75, "B"), (50, "C"), (0, "D"))):
        scale = GradingScale.objects.create(academic_year=self.year, name="Standard")
        for minimum, label in bands:
            GradeBoundary.objects.create(scale=scale, label=label, min_percentage=minimum)
        scale.set_class_grades([self.grade6])
        return scale
