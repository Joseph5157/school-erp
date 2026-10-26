"""Add terms, marks and published Term 1 report cards to a seed_school_demo school.

Everything goes through the domain workflows: the assigned teacher enters each
result, the administrator finalizes the assessment and publishes the Term, so
the data obeys the same rules as real use. It also completes today's attendance
registers (except one Section, left untaken for the Overview) so the dashboard
does not open on a wall of missing registers.

Not re-runnable: it refuses to run when any Term already exists.
"""

import datetime
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import publication
from core.management.commands.seed_demo import ABSENCE_NOTES, DEMO_ADMIN_USERNAME
from core.models import (
    AcademicTerm,
    AcademicYear,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    GradeBoundary,
    GradingScale,
    ResultStatus,
    Section,
    SectionClassTeacher,
    TermRemark,
    business_today,
)

GRADE_BANDS = [("A1", 90), ("A2", 80), ("B1", 70), ("B2", 60), ("C", 50), ("D", 35), ("E", 0)]
ABSENCE_RATE = 0.02

REMARKS = {
    "high": [
        "Excellent term. Keeps a very high standard and helps classmates.",
        "Outstanding effort and consistent results across all subjects.",
    ],
    "good": [
        "Good progress this term. Can do even better with a little more revision.",
        "Works steadily and participates well in class.",
    ],
    "mid": [
        "Satisfactory term. Regular practice at home will help.",
        "Is improving; needs to focus on written work.",
    ],
    "low": [
        "Needs extra support in some subjects. Please revise daily at home.",
        "Must attend remedial classes and practise regularly.",
    ],
}


def round_half(value):
    return (Decimal(str(value)) * 2).quantize(Decimal("1")) / 2


class Command(BaseCommand):
    help = "Add Term 1 marks, grades, remarks and published report cards to the demo school."

    def add_arguments(self, parser):
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("Set DJANGO_DEBUG=True or pass --allow-non-debug.")
        if AcademicTerm.objects.exists():
            raise CommandError("Terms already exist; this only runs on a school without Terms.")
        self.admin = get_user_model().objects.get(username=DEMO_ADMIN_USERNAME)
        self.year = AcademicYear.objects.get()
        self.today = business_today()
        self.rng = random.Random(7)

        with transaction.atomic():
            term1 = self._terms()
            self._grading_scale()
            assessments = self._assessments(term1)
            self._enter_and_finalize(assessments)
            self._remarks(term1)
            published = self._publish(term1)
            filled = self._complete_today_attendance()
        self.stdout.write(self.style.SUCCESS("Demo results created."))
        self.stdout.write(
            f"  {len(assessments)} assessments finalized, {published} report cards published, "
            f"{filled} attendance registers completed for today."
        )

    # -- terms and grading -------------------------------------------------

    def _terms(self):
        start = self.year.start_date
        term1 = AcademicTerm(
            academic_year=self.year, name="Term 1", display_order=1,
            start_date=start, end_date=start + datetime.timedelta(days=121),
        )
        term1.full_clean()
        term1.save()
        term2 = AcademicTerm(
            academic_year=self.year, name="Term 2", display_order=2,
            start_date=term1.end_date + datetime.timedelta(days=1), end_date=self.year.end_date,
        )
        term2.full_clean()
        term2.save()
        return term1

    def _grading_scale(self):
        scale = GradingScale.objects.create(academic_year=self.year, name="Standard grading")
        GradeBoundary.objects.bulk_create(
            GradeBoundary(scale=scale, label=label, min_percentage=Decimal(minimum))
            for label, minimum in GRADE_BANDS
        )
        scale.set_class_grades(ClassGrade.objects.all())

    # -- assessments and marks ---------------------------------------------

    def _assessments(self, term):
        plan = [
            ("Unit Test 1", term.start_date + datetime.timedelta(days=50), 25, 9),
            ("Half-Yearly Exam", term.start_date + datetime.timedelta(days=105), 100, 35),
        ]
        assessments = []
        assignments = AssessmentTeacherAssignment.objects.select_related(
            "teacher", "offering__subject", "offering__class_grade", "section"
        ).order_by("offering__class_grade__name", "section__name", "offering__display_order")
        for assignment in assignments:
            for name, when, maximum, pass_mark in plan:
                while when.weekday() >= 5:  # land on a weekday
                    when += datetime.timedelta(days=1)
                if when > self.today:
                    continue
                assessment = Assessment(
                    term=term, offering=assignment.offering, section=assignment.section,
                    name=name, assessment_date=when, maximum_marks=Decimal(maximum),
                    pass_mark=Decimal(pass_mark),
                )
                assessment.full_clean()
                assessment.save()
                assessments.append((assessment, assignment.teacher))
        return assessments

    def _enter_and_finalize(self, assessments):
        ability = {}
        for assessment, teacher in assessments:
            for enrollment in assessment.roster():
                sid = enrollment.student_id
                if sid not in ability:
                    ability[sid] = min(0.97, max(0.22, self.rng.gauss(0.70, 0.16)))
                if self.rng.random() < ABSENCE_RATE:
                    assessment.save_draft_result(
                        enrollment=enrollment, status=ResultStatus.ABSENT, actor=teacher
                    )
                    continue
                fraction = ability[sid] + self.rng.uniform(-0.07, 0.07)
                fraction = min(1.0, max(0.05, fraction))
                score = min(
                    assessment.maximum_marks,
                    round_half(Decimal(str(fraction)) * assessment.maximum_marks),
                )
                assessment.save_draft_result(
                    enrollment=enrollment, status=ResultStatus.MARKED, score=score, actor=teacher
                )
            assessment.finalize(actor=self.admin)
        self.ability = ability

    # -- remarks, publication, attendance ----------------------------------

    def _remarks(self, term):
        class_teachers = {
            c.section_id: c.teacher
            for c in SectionClassTeacher.objects.filter(academic_year=self.year)
        }
        for section in Section.objects.all():
            teacher = class_teachers[section.pk]
            for student in term.section_rosters([section])[section.pk]:
                score = self.ability.get(student.pk, 0.7)
                band = "high" if score >= 0.85 else "good" if score >= 0.72 else (
                    "mid" if score >= 0.58 else "low"
                )
                TermRemark.objects.create(
                    term=term, student=student, written_by=teacher,
                    remark=self.rng.choice(REMARKS[band]),
                )

    def _publish(self, term):
        total = 0
        for section in Section.objects.all():
            plan = publication.plan_publication(term, section)
            if not plan["selected"]:
                continue
            created = publication.confirm_publication(
                term=term, section=section, include=(), token=plan["token"], actor=self.admin
            )
            total += len(created)
        return total

    def _complete_today_attendance(self):
        """Submit today's missing registers, leaving the last Section untaken."""
        if not self.year.is_instructional_day(self.today):
            return 0
        sections = list(
            Section.objects.select_related("class_grade").order_by("class_grade_id", "name")
        )
        untaken = sections[-1]
        done = 0
        for section in sections:
            if section.pk == untaken.pk:
                continue
            register = AttendanceRegister.objects.filter(
                academic_year=self.year, section=section, date=self.today
            ).first()
            if register is not None and register.status == "SUBMITTED":
                continue
            if register is None:
                register = AttendanceRegister(
                    academic_year=self.year, class_grade=section.class_grade,
                    section=section, date=self.today,
                )
                register.full_clean()
                register.save()
            captured = set(register.entries.values_list("academic_enrollment_id", flat=True))
            for enrollment in register.eligible_enrollments():
                if enrollment.pk in captured:
                    continue
                if self.rng.random() < 0.06:
                    register.capture(
                        enrollment=enrollment, status=AttendanceStatus.ABSENT,
                        absence_note=self.rng.choice(ABSENCE_NOTES),
                    )
                else:
                    register.capture(enrollment=enrollment, status=AttendanceStatus.PRESENT)
            register.submit(actor=self.admin)
            done += 1
        return done
