"""Admin home Academics tab data. Read-only; no HTTP here.

Marks rules (shared with `marks_analytics`): only FINALIZED assessments and MARKED results count
in averages; ABSENT is never a zero and a score of exactly 0 is real. "Results to finish" is the
exception that looks at work not yet official: DRAFT assessments of the work term, and students
whose FINALIZED results (MARKED or ABSENT) have no current term publication.
"""
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse

from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    Assessment,
    Section,
    Student,
    StudentResult,
    TermPublication,
)


def work_term(today):
    """The term being worked on: the running one, else the latest one that has started."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today)
        .select_related("academic_year")
        .order_by("-start_date", "-display_order")
        .first()
    )


def _roster():
    """Enrollments in an assessment's year, grade and section, effective on its date."""
    return AcademicEnrollment.objects.filter(
        academic_year_id=OuterRef("offering__academic_year_id"),
        class_grade_id=OuterRef("offering__class_grade_id"),
        section_id=OuterRef("section_id"),
        start_date__lte=OuterRef("assessment_date"),
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=OuterRef("assessment_date")))


def _drafts(term, today):
    """The term's counted DRAFT assessments, annotated with `has_roster` and `has_unmarked`."""
    unmarked = _roster().exclude(
        Exists(
            StudentResult.objects.filter(
                assessment_id=OuterRef(OuterRef("pk")), academic_enrollment_id=OuterRef("pk")
            )
        )
    )
    return (
        Assessment.objects.filter(
            term=term, status=Assessment.Status.DRAFT, assessment_date__lte=today
        )
        .select_related("offering__subject", "offering__class_grade", "section")
        .annotate(has_roster=Exists(_roster()), has_unmarked=Exists(unmarked))
        .order_by("assessment_date", "name", "pk")
    )


def _unpublished(term):
    """(student count, {section_id: count}) for ACTIVE students with finalized results, unpublished."""
    pairs = (
        StudentResult.objects.filter(
            assessment__term=term,
            assessment__status=Assessment.Status.FINALIZED,
            academic_enrollment__student__status=Student.Status.ACTIVE,
        )
        .exclude(
            Exists(
                TermPublication.objects.filter(
                    term=term,
                    student_id=OuterRef("academic_enrollment__student_id"),
                    status__in=TermPublication.CURRENT_STATUSES,
                )
            )
        )
        .order_by("academic_enrollment__student_id", "academic_enrollment__section_id")
        .values_list("academic_enrollment__student_id", "academic_enrollment__section_id")
        .distinct()
    )
    section_of = {}
    for student_id, section_id in pairs:
        section_of.setdefault(student_id, section_id)
    counts = {}
    for section_id in section_of.values():
        counts[section_id] = counts.get(section_id, 0) + 1
    return len(section_of), counts


def results_to_finish(today, *, publish_rows):
    """Marking in progress, ready to finalize, and finalized-but-unpublished, for the work term."""
    term = work_term(today)
    if term is None:
        return None
    ready, in_progress = [], 0
    for a in _drafts(term, today):
        if a.has_roster and not a.has_unmarked:
            ready.append(
                {
                    "name": a.name,
                    "class_name": a.offering.class_grade.name,
                    "section_name": a.section.name,
                    "subject": a.offering.subject.name,
                    "url": reverse("core:assessment-detail", args=[a.pk]),
                }
            )
        else:
            in_progress += 1
    students, counts = _unpublished(term)
    rows = []
    if publish_rows and counts:
        publish_url = reverse("core:term-publication", args=[term.pk])
        sections = Section.objects.filter(pk__in=counts).select_related("class_grade")
        for s in sorted(sections, key=lambda s: (s.class_grade.display_order, s.name, s.pk)):
            rows.append(
                {
                    "section_id": s.pk,
                    "class_name": s.class_grade.name,
                    "section_name": s.name,
                    "students": counts[s.pk],
                    "url": f"{publish_url}?section={s.pk}",
                }
            )
    in_progress_url = (
        reverse("core:academic-year-assessments", args=[term.academic_year_id])
        + f"?term={term.pk}&status=DRAFT"
    )
    return {
        "term": term,
        "term_name": term.name,
        "in_progress": in_progress,
        "in_progress_url": in_progress_url,
        "ready": ready,
        "unpublished_students": students,
        "unpublished_sections": rows,
    }
