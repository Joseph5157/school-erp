"""Subject scores for charts (ADR 0022). Display-only; nothing here is stored.

Only FINALIZED assessments and MARKED results count. A score is a percentage of its own
assessment's maximum. ABSENT is never a zero. A score of exactly 0 is real, so no code here
tests a score for truthiness. This module must not import `core.analytics`, which imports it.
"""

from dataclasses import dataclass

from django.db.models import (
    Avg,
    Case,
    Count,
    DecimalField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    When,
)

from core.models import AcademicTerm, Assessment, ResultStatus, StudentResult

# A section average is hidden below this many distinct students, so a small section cannot
# reveal one student's marks.
MIN_COMPARISON_STUDENTS = 5

_PERCENT = ExpressionWrapper(
    F("score") * 100 / F("assessment__maximum_marks"),
    output_field=DecimalField(max_digits=9, decimal_places=4),
)
_PASS_PERCENT = ExpressionWrapper(
    F("assessment__pass_mark") * 100 / F("assessment__maximum_marks"),
    output_field=DecimalField(max_digits=9, decimal_places=4),
)


@dataclass(frozen=True)
class SubjectScore:
    subject_name: str
    score: float
    pass_percent: float | None
    below_pass: bool
    section_average: float | None


def _counted_results(**extra):
    """FINALIZED + MARKED results, optionally narrowed further."""
    return StudentResult.objects.filter(
        assessment__status=Assessment.Status.FINALIZED, status=ResultStatus.MARKED, **extra
    )


def reporting_term(today):
    """The running term if it has finalized MARKED results, else the latest started one that does."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today)
        .filter(Exists(_counted_results(assessment__term=OuterRef("pk"))))
        .order_by(
            Case(When(end_date__gte=today, then=0), default=1, output_field=IntegerField()),
            "-start_date",
            "-display_order",
        )
        .first()
    )


def marked_results(term, scope=None):
    """The term's FINALIZED + MARKED results with `percent` and `subject_name` annotated."""
    return (
        _counted_results(assessment__term=term)
        .filter(Q() if scope is None else scope)
        .annotate(
            percent=_PERCENT,
            subject_name=Assessment.subject_display_expression("assessment__"),
        )
    )


def subject_averages(term):
    """Each subject's average percent across the term, lowest first (ties by name)."""
    rows = (
        marked_results(term)
        .order_by()
        .values("subject_name")
        .annotate(average=Avg("percent"), results=Count("id"))
    )
    return sorted(
        (
            {
                "subject_name": row["subject_name"],
                "average": round(float(row["average"]), 1),
                "results": row["results"],
            }
            for row in rows
        ),
        key=lambda r: (r["average"], r["subject_name"]),
    )


def student_subject_scores(student, term, scope=None):
    """One `SubjectScore` per subject the student has marks in, in subject name order."""
    own = marked_results(term, scope).filter(academic_enrollment__student=student).order_by()
    scores = {
        row["subject_name"]: float(row["score"])
        for row in own.values("subject_name").annotate(score=Avg("percent"))
    }
    if not scores:
        return []

    # Like with like: only the tests this student sat that have a pass mark.
    pass_rows = (
        own.filter(assessment__pass_mark__isnull=False)
        .values("subject_name")
        .annotate(sat=Avg("percent"), pass_percent=Avg(_PASS_PERCENT))
    )
    passes = {
        row["subject_name"]: (float(row["sat"]), float(row["pass_percent"])) for row in pass_rows
    }

    section_averages = {}
    enrollment = term.enrollment_for(student)
    if enrollment is not None:
        section_rows = (
            marked_results(term, scope)
            .filter(assessment__section_id=enrollment.section_id)
            .order_by()
            .values("subject_name")
            .annotate(
                average=Avg("percent"),
                students=Count("academic_enrollment__student_id", distinct=True),
            )
        )
        section_averages = {
            row["subject_name"]: float(row["average"])
            for row in section_rows
            if row["students"] >= MIN_COMPARISON_STUDENTS
        }

    result = []
    for name in sorted(scores):
        sat, pass_percent = passes.get(name, (None, None))
        result.append(
            SubjectScore(
                subject_name=name,
                score=scores[name],
                pass_percent=pass_percent,
                below_pass=pass_percent is not None and sat < pass_percent,
                section_average=section_averages.get(name),
            )
        )
    return result


def terms_with_results(student):
    """Terms in which the student has finalized MARKED results, newest first."""
    return list(
        AcademicTerm.objects.filter(
            Exists(
                _counted_results(
                    assessment__term=OuterRef("pk"), academic_enrollment__student=student
                )
            )
        ).order_by("-start_date", "-display_order")
    )
