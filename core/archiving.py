"""Archive and restore Classes/Grades and Sections (ADR 0025).

An archived record cannot be picked for anything new. Everything already recorded against
it stays as it is. Invariant: an archived Class/Grade has only archived Sections.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import (
    AcademicEnrollment,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    SectionClassTeacher,
    TimetableSlot,
    business_today,
)


def _count(number, singular, plural, tail):
    return f"{number} {singular if number == 1 else plural} {tail}"


def _still_running(today):
    return Q(end_date__isnull=True) | Q(end_date__gte=today)


def blockers(record):
    """Why `record` cannot be archived yet: what must move first. Empty when it can."""
    if isinstance(record, ClassGrade):
        sections = Section.objects.filter(class_grade=record)
    else:
        sections = Section.objects.filter(pk=record.pk)
    today = business_today()
    students = (
        AcademicEnrollment.objects.filter(
            section__in=sections,
            status=AcademicEnrollment.Status.ACTIVE,
            academic_year__end_date__gte=today,
        )
        .values("student_id")
        .distinct()
        .count()
    )
    class_teachers = SectionClassTeacher.objects.filter(
        _still_running(today), section__in=sections, academic_year__end_date__gte=today
    ).count()
    subject_teachers = AssessmentTeacherAssignment.objects.filter(
        _still_running(today), section__in=sections, offering__academic_year__end_date__gte=today
    ).count()
    slots = TimetableSlot.objects.filter(
        _still_running(today), section__in=sections, period__academic_year__end_date__gte=today
    ).count()
    reasons = []
    if students:
        reasons.append(_count(students, "student is", "students are", "placed here this year."))
    if class_teachers:
        reasons.append(
            _count(class_teachers, "class teacher assignment is", "class teacher assignments are",
                   "still running.")
        )
    if subject_teachers:
        reasons.append(
            _count(subject_teachers, "subject teacher assignment is",
                   "subject teacher assignments are", "still running.")
        )
    if slots:
        reasons.append(_count(slots, "timetable slot is", "timetable slots are", "still running."))
    return reasons


def _lock_grade(class_grade):
    """Lock the Class/Grade, then its Sections, so archive and restore run one at a time."""
    locked = ClassGrade.objects.select_for_update().get(pk=class_grade.pk)
    list(Section.objects.select_for_update().filter(class_grade=locked).values_list("pk"))
    return locked


def _stamp(queryset, archived_at, actor):
    queryset.update(archived_at=archived_at, archived_by=actor, updated_at=timezone.now())


def archive_section(section, actor):
    with transaction.atomic():
        _lock_grade(section.class_grade)
        section = Section.objects.get(pk=section.pk)
        if section.archived_at is not None:
            return
        reasons = blockers(section)
        if reasons:
            raise ValidationError(reasons)
        _stamp(Section.objects.filter(pk=section.pk), timezone.now(), actor)


def archive_class(class_grade, actor):
    """Archive the Class/Grade and every active Section, at one moment, or nothing."""
    with transaction.atomic():
        class_grade = _lock_grade(class_grade)
        if class_grade.archived_at is not None:
            return
        reasons = blockers(class_grade)
        if reasons:
            raise ValidationError(reasons)
        now = timezone.now()
        _stamp(Section.objects.active().filter(class_grade=class_grade), now, actor)
        _stamp(ClassGrade.objects.filter(pk=class_grade.pk), now, actor)


def restore_section(section):
    with transaction.atomic():
        class_grade = _lock_grade(section.class_grade)
        if class_grade.archived_at is not None:
            raise ValidationError(f"Restore {class_grade} first; this Section belongs to it.")
        _stamp(Section.objects.filter(pk=section.pk), None, None)


def restore_class(class_grade):
    """Restore the Class/Grade and the Sections archived with it; earlier ones stay archived."""
    with transaction.atomic():
        class_grade = _lock_grade(class_grade)
        if class_grade.archived_at is None:
            return
        _stamp(
            Section.objects.filter(class_grade=class_grade, archived_at=class_grade.archived_at),
            None,
            None,
        )
        _stamp(ClassGrade.objects.filter(pk=class_grade.pk), None, None)
