"""Phase 5 Gate 7: administrator teacher-assignment workflows (ADR 0011 D13, D14).

- `overview(year, on_date)`: every Section's class teacher and every
  offering/Section's subject teacher for one Academic Year, with gaps and
  assignments held by logins that are no longer active teachers.
- `plan_copy(source, target)` / `apply_copy(...)`: a conservative,
  preview-first copy of the previous year's assignments. A row is copied
  only when its equivalent is exact and unique; nothing is guessed, and
  every skipped row is reported with its reason. Confirming twice creates
  nothing new.
"""

import hashlib
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicSubjectOffering,
    AssessmentTeacherAssignment,
    Section,
    SectionClassTeacher,
)


def active_teacher_ids():
    return set(
        get_user_model()
        .objects.filter(groups__name=TEACHERS_GROUP_NAME, is_active=True)
        .values_list("pk", flat=True)
    )


def _offering_sections(offerings, sections_by_grade):
    """(offering, section) slots: linked Sections, or all of the Grade's Sections."""
    for offering in offerings:
        linked = [link.section for link in offering.section_links.all()]
        for section in linked or sections_by_grade.get(offering.class_grade_id, []):
            yield offering, section


def overview(academic_year, on_date):
    """Class teacher and subject teacher coverage for one Academic Year.

    `on_date` decides which class teacher row is "current" (clamped into the
    year). A slot is flagged when it has no holder, or when its holder is no
    longer an active Teachers-group login (ADR 0011 D14) - such rows are
    never changed automatically.
    """
    on_date = min(max(on_date, academic_year.start_date), academic_year.end_date)
    teachers = active_teacher_ids()
    sections = list(Section.objects.select_related("class_grade").order_by(
        "class_grade__name", "name"
    ))
    sections_by_grade = {}
    for section in sections:
        sections_by_grade.setdefault(section.class_grade_id, []).append(section)

    current = {
        row.section_id: row
        for row in SectionClassTeacher.objects.filter(academic_year=academic_year)
        .effective_on(on_date)
        .select_related("teacher")
    }
    class_rows = []
    for section in sections:
        row = current.get(section.pk)
        class_rows.append(
            {
                "section": section,
                "assignment": row,
                "gap": row is None,
                "inactive": row is not None and row.teacher_id not in teachers,
            }
        )

    holders = {
        (a.offering_id, a.section_id): a
        for a in AssessmentTeacherAssignment.objects.filter(
            offering__academic_year=academic_year
        ).select_related("teacher")
    }
    offerings = (
        AcademicSubjectOffering.objects.filter(academic_year=academic_year)
        .select_related("class_grade", "subject")
        .prefetch_related("section_links__section__class_grade")
        .order_by("class_grade__name", "subject__name")
    )
    subject_rows = []
    for offering, section in _offering_sections(offerings, sections_by_grade):
        assignment = holders.get((offering.pk, section.pk))
        subject_rows.append(
            {
                "offering": offering,
                "section": section,
                "assignment": assignment,
                "gap": assignment is None,
                "inactive": assignment is not None and assignment.teacher_id not in teachers,
            }
        )
    return {
        "on_date": on_date,
        "class_rows": class_rows,
        "subject_rows": subject_rows,
        "class_gaps": sum(1 for row in class_rows if row["gap"]),
        "subject_gaps": sum(1 for row in subject_rows if row["gap"]),
        "inactive": sum(1 for row in class_rows + subject_rows if row["inactive"]),
    }


def teacher_load(user):
    """Every class and subject teacher assignment a login holds, by year."""
    class_rows = (
        SectionClassTeacher.objects.filter(teacher=user)
        .select_related("academic_year", "section__class_grade")
        .order_by("-academic_year__start_date", "section__class_grade__name", "start_date")
    )
    subject_rows = (
        AssessmentTeacherAssignment.objects.filter(teacher=user)
        .select_related("offering__academic_year", "offering__subject", "section__class_grade")
        .order_by("-offering__academic_year__start_date", "offering__subject__name")
    )
    years = {}
    for row in class_rows:
        years.setdefault(row.academic_year, {"class": [], "subject": []})["class"].append(row)
    for row in subject_rows:
        years.setdefault(row.offering.academic_year, {"class": [], "subject": []})[
            "subject"
        ].append(row)
    return sorted(years.items(), key=lambda item: item[0].start_date, reverse=True)


# --- copy previous year's assignments -----------------------------------------


@dataclass(frozen=True)
class PlannedCopy:
    kind: str  # "class" or "subject"
    teacher_id: int
    section_id: int
    offering_id: int | None = None
    label: str = field(default="", compare=False)

    def key(self):
        return f"{self.kind}:{self.teacher_id}:{self.section_id}:{self.offering_id}"


@dataclass(frozen=True)
class Skip:
    label: str
    reason: str


def plan_copy(source, target):
    """What copying `source` year's assignments into `target` would do.

    Class teachers: the class teacher effective on the source year's last
    day, for the same Section, starting on the target year's first day.
    Subject teachers: the same Subject offered for the same Class/Grade in
    the target year (an exact, unique match), for the same Section, if the
    target offering applies to it. Skipped, with a reason: inactive or
    non-teacher logins, missing or ambiguous equivalents, and targets that
    already have an assignment.
    """
    if source.pk == target.pk:
        raise ValidationError("Choose a different Academic Year to copy from.")
    teachers = active_teacher_ids()
    copies, skips = [], []

    taken_sections = set(
        SectionClassTeacher.objects.filter(academic_year=target).values_list(
            "section_id", flat=True
        )
    )
    source_rows = list(
        SectionClassTeacher.objects.filter(academic_year=source)
        .select_related("teacher", "section__class_grade")
        .order_by("section__class_grade__name", "section__name", "start_date")
    )
    effective_at_end = {
        row.section_id: row for row in source_rows if row.is_effective_on(source.end_date)
    }
    for row in source_rows:
        label = f"Class teacher {row.section}: {_name(row.teacher)}"
        if effective_at_end.get(row.section_id) is not row:
            skips.append(Skip(label, "Not the class teacher at the end of the source year."))
        elif row.teacher_id not in teachers:
            skips.append(Skip(label, "Login is inactive or not in the Teachers group."))
        elif row.section_id in taken_sections:
            skips.append(
                Skip(label, "This Section already has a class teacher in the target year.")
            )
        else:
            copies.append(PlannedCopy("class", row.teacher_id, row.section_id, None, label))

    target_offerings = {}
    for offering in AcademicSubjectOffering.objects.filter(academic_year=target):
        target_offerings.setdefault((offering.class_grade_id, offering.subject_id), []).append(
            offering
        )
    taken_slots = set(
        AssessmentTeacherAssignment.objects.filter(offering__academic_year=target).values_list(
            "offering_id", "section_id"
        )
    )
    for assignment in (
        AssessmentTeacherAssignment.objects.filter(offering__academic_year=source)
        .select_related("teacher", "offering__subject", "offering__class_grade",
                        "section__class_grade")
        .order_by("offering__class_grade__name", "offering__subject__name", "section__name")
    ):
        label = (
            f"{assignment.offering.subject.name} {assignment.section}: "
            f"{_name(assignment.teacher)}"
        )
        matches = target_offerings.get(
            (assignment.offering.class_grade_id, assignment.offering.subject_id), []
        )
        if assignment.teacher_id not in teachers:
            skips.append(Skip(label, "Login is inactive or not in the Teachers group."))
        elif not matches:
            skips.append(Skip(label, "This Subject is not offered for this Class/Grade in the "
                                     "target year."))
        elif len(matches) > 1:
            skips.append(Skip(label, "More than one matching Subject offering; not guessing."))
        elif not matches[0].applies_to(assignment.section):
            skips.append(Skip(label, "The Section does not take this Subject in the target year."))
        elif (matches[0].pk, assignment.section_id) in taken_slots:
            skips.append(Skip(label, "This Subject and Section already have a teacher in the "
                                     "target year."))
        else:
            copies.append(
                PlannedCopy("subject", assignment.teacher_id, assignment.section_id,
                            matches[0].pk, label)
            )
    return {"copies": copies, "skips": skips, "token": _token(copies)}


def apply_copy(source, target, token):
    """Create exactly the previewed copies, or nothing.

    The plan is recomputed inside a transaction; if it no longer matches the
    previewed `token`, nothing is written and a ValidationError asks the
    administrator to review the new preview. Returns the number created.
    """
    with transaction.atomic():
        # Serialize with class teacher hand-overs, which lock the Section.
        list(Section.objects.select_for_update().values_list("pk", flat=True))
        plan = plan_copy(source, target)
        if plan["token"] != token:
            raise ValidationError(
                "Assignments changed since the preview. Review the new preview and confirm again."
            )
        User = get_user_model()
        for item in plan["copies"]:
            teacher = User.objects.get(pk=item.teacher_id)
            section = Section.objects.get(pk=item.section_id)
            if item.kind == "class":
                row = SectionClassTeacher(
                    teacher=teacher, academic_year=target, section=section,
                    start_date=target.start_date,
                )
            else:
                row = AssessmentTeacherAssignment(
                    teacher=teacher,
                    offering=AcademicSubjectOffering.objects.get(pk=item.offering_id),
                    section=section,
                )
            row.full_clean()
            try:
                with transaction.atomic():
                    row.save()
            except IntegrityError as error:
                raise ValidationError(
                    "Assignments changed while copying; nothing was copied. Try again."
                ) from error
        return len(plan["copies"])


def _token(copies):
    joined = "|".join(sorted(item.key() for item in copies))
    return hashlib.sha256(joined.encode()).hexdigest()


def _name(user):
    return user.get_full_name() or user.username
