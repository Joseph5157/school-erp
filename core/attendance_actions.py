"""Who acts on a missing register, and what the next step is (Option A1).

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 4. Read-only; no HTTP.

`resolve_missing` adds, to each `reports.missing_attendance` row, who is responsible (the class
teacher or the office), any configuration problem, and whether a "Take register" link may be
offered at all. Whether the viewer may follow a link is a template decision, by the permission
of the page it opens. Nothing here grants a power: teachers still take today's register only
(ADR 0012 D5), and administrators keep the Phase 2 workflow.

Rules, first match wins:

1. ARCHIVED_SECTION - the Section or its Class/Grade is archived (ADR 0025). No register link,
   because a new register cannot use an archived Section.
2. OVERLAPPING_YEARS - the Section is expected in more than one academic year that date, or has
   more than one effective class teacher assignment across years (Security Gate 3A). Only one
   register can exist per Section and date, so the cohort is ambiguous; no register link.
3. NO_CLASS_TEACHER - no assignment effective that date for the row's own year.
4. TEACHER_CANNOT_TAKE - the assigned login is inactive or not in the Teachers group (ADR 0011
   D14).
5. A past date belongs to the office (ADR 0012 D5); the teacher is context only.
6. Otherwise today's row is the class teacher's.

Constant queries: assignments for every Section in the rows, Teachers-group membership, and,
only when a row overlaps, one lookup of the academic years whose names label the review links.
"""

from collections import defaultdict
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.urls import reverse

from core.models import TEACHERS_GROUP_NAME, AcademicYear, SectionClassTeacher


class Owner(models.TextChoices):
    TEACHER = "TEACHER", "Class teacher"
    OFFICE = "OFFICE", "Office"


class Problem(models.TextChoices):
    ARCHIVED_SECTION = "ARCHIVED_SECTION", "This section is archived"
    OVERLAPPING_YEARS = "OVERLAPPING_YEARS", "Two academic years overlap for this section"
    NO_CLASS_TEACHER = "NO_CLASS_TEACHER", "No class teacher assigned"
    TEACHER_CANNOT_TAKE = "TEACHER_CANNOT_TAKE", "Class teacher can't sign in as a teacher"


def _is_archived(section):
    return section.archived_at is not None or section.class_grade.archived_at is not None


def _effective(assignment, on_date):
    """SectionClassTeacherQuerySet.effective_on, in memory: an open-ended assignment runs to the
    end of its own academic year."""
    last = assignment.end_date or assignment.academic_year.end_date
    return assignment.start_date <= on_date <= last


def _assignments(rows):
    """{section_id: [assignment, ...]} covering every row's date, across all academic years."""
    dates = [row["date"] for row in rows]
    first, last = min(dates), max(dates)
    queryset = (
        SectionClassTeacher.objects.filter(
            section_id__in={row["section"].pk for row in rows}, start_date__lte=last
        )
        .filter(
            Q(end_date__gte=first) | Q(end_date__isnull=True, academic_year__end_date__gte=first)
        )
        .select_related("teacher", "academic_year")
    )
    by_section = defaultdict(list)
    for assignment in queryset:
        by_section[assignment.section_id].append(assignment)
    return by_section


def _valid_teacher_ids(teacher_ids):
    """Active logins in the Teachers group, from one query (no per-user lookups)."""
    return set(
        get_user_model()
        .objects.filter(pk__in=teacher_ids, is_active=True, groups__name=TEACHERS_GROUP_NAME)
        .values_list("pk", flat=True)
    )


def _take_url(row):
    query = urlencode({
        "academic_year": row["academic_year_id"],
        "class_grade": row["section"].class_grade_id,
        "section": row["section"].pk,
        "date": row["date"].isoformat(),
    })
    return f"{reverse('core:attendance-register-create')}?{query}"


def _decide(row, effective, own, valid_ids, today):
    """(problem, owner, can_take, review year ids) for one row; rules in the module docstring."""
    expected_years = row["expected_academic_year_ids"]
    if _is_archived(row["section"]):
        return Problem.ARCHIVED_SECTION, Owner.OFFICE, False, []
    if len(expected_years) > 1 or len(effective) > 1:
        years = expected_years if len(expected_years) > 1 else sorted(
            {a.academic_year_id for a in effective}
        )
        return Problem.OVERLAPPING_YEARS, Owner.OFFICE, False, list(years)
    if own is None:
        return Problem.NO_CLASS_TEACHER, Owner.OFFICE, True, [row["academic_year_id"]]
    if own.teacher_id not in valid_ids:
        return Problem.TEACHER_CANNOT_TAKE, Owner.OFFICE, True, [row["academic_year_id"]]
    if row["date"] < today:
        return None, Owner.OFFICE, True, []
    return None, Owner.TEACHER, True, []


def resolve_missing(rows, today):
    """Add `owner`, `teacher`, `problem`, `problem_label`, `can_take`, `take_url` and
    `review_years` to each `reports.missing_attendance` row, and return the rows.

    `review_years` is a list of `{"id", "name"}` for the "Review class teacher" links; `name` is
    filled only for an overlap, where the links must say which year each one opens.
    """
    if not rows:
        return rows
    by_section = _assignments(rows)
    valid_ids = _valid_teacher_ids(
        {a.teacher_id for assignments in by_section.values() for a in assignments}
    )
    overlapping = []
    for row in rows:
        effective = [a for a in by_section.get(row["section"].pk, ()) if _effective(a, row["date"])]
        own = next((a for a in effective if a.academic_year_id == row["academic_year_id"]), None)
        problem, owner, can_take, year_ids = _decide(row, effective, own, valid_ids, today)
        row.update(
            teacher=own.teacher if own else None,
            problem=problem,
            problem_label=problem.label if problem else "",
            owner=owner,
            can_take=can_take,
            take_url=_take_url(row) if can_take else "",
            review_years=[{"id": year_id, "name": ""} for year_id in year_ids],
        )
        if problem == Problem.OVERLAPPING_YEARS:
            overlapping.append(row)
    if overlapping:
        names = dict(
            AcademicYear.objects.filter(
                pk__in={year["id"] for row in overlapping for year in row["review_years"]}
            ).values_list("pk", "name")
        )
        for row in overlapping:
            for year in row["review_years"]:
                year["name"] = names.get(year["id"], "")
    return rows
