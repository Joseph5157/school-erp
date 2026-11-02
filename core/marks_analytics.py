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

from core import charts
from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    Assessment,
    ResultStatus,
    Student,
    StudentResult,
)

# A section average is hidden below this many distinct students, so a small section cannot
# reveal one student's marks.
MIN_COMPARISON_STUDENTS = 5

# Percentages come out of the database as long decimals. A score that is exactly the pass mark
# but written in different units (6 of 18 against a pass mark of 2 of 6) must not read as below.
_TIE_TOLERANCE = 1e-9

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


def _pass_comparison(results, *group_by):
    """Like with like: per group, the average percent over only the tests that have a pass mark.

    `results` are already MARKED, so tests the student was absent for are never in it. The
    student page and the Overview's attention list both read below-pass from this and
    `_is_below`, so the two cannot drift apart.
    """
    return (
        results.filter(assessment__pass_mark__isnull=False)
        .order_by()
        .values(*group_by)
        .annotate(sat=Avg("percent"), pass_percent=Avg(_PASS_PERCENT))
    )


def _is_below(sat, pass_percent):
    """Strictly below the pass mark; a tie, or no pass mark at all, is not below."""
    return pass_percent is not None and sat < pass_percent - _TIE_TOLERANCE


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

    passes = {
        row["subject_name"]: (float(row["sat"]), float(row["pass_percent"]))
        for row in _pass_comparison(own, "subject_name")
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
                below_pass=_is_below(sat, pass_percent),
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


def _join_names(names):
    """"A", "A and B", "A, B and C"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def students_needing_attention(
    term, absent_days, threshold=3, limit=10, period_label="last 14 days"
):
    """Active students below pass in 2+ subjects, or in 1 subject and absent `threshold`+ days.

    Marks come from `term`; `absent_days` ({student_id: days}) comes from the period the page is
    showing, named by `period_label`. Below-pass is the student page's rule (`_pass_comparison`),
    found for every student by one grouped query. Rows are ordered by class (natural order) and
    name, never by performance. `total` is the true count even when `limit` trims the rows.
    """
    if term is None:
        return {"rows": [], "total": 0}
    grouped = _pass_comparison(
        marked_results(term).filter(academic_enrollment__student__status=Student.Status.ACTIVE),
        "academic_enrollment__student_id",
        "subject_name",
    )
    below = {}
    for row in grouped:
        if _is_below(float(row["sat"]), float(row["pass_percent"])):
            below.setdefault(row["academic_enrollment__student_id"], []).append(row["subject_name"])
    flagged = {
        student_id: sorted(subjects)
        for student_id, subjects in below.items()
        if len(subjects) >= 2 or absent_days.get(student_id, 0) >= threshold
    }

    # The class shown is the student's current ACTIVE enrollment; no active enrollment, no row.
    current = {
        e.student_id: e
        for e in AcademicEnrollment.objects.filter(
            student_id__in=flagged,
            status=AcademicEnrollment.Status.ACTIVE,
            student__status=Student.Status.ACTIVE,
        )
        .select_related("student", "class_grade")
        .order_by("start_date", "pk")
    }
    rows = []
    for student_id, subjects in flagged.items():
        enrollment = current.get(student_id)
        if enrollment is None:
            continue
        days = absent_days.get(student_id) or None
        reason = f"Below pass in {_join_names(subjects)} ({term.name})"
        if days:
            reason += f"; absent {days} day{'' if days == 1 else 's'} ({period_label})"
        rows.append(
            {
                "student_id": student_id,
                "name": enrollment.student.full_name,
                "class_name": enrollment.class_grade.name,
                "below_subjects": subjects,
                "absent_days": days,
                "reason": reason,
            }
        )
    rows.sort(key=lambda r: (charts.natural_key(r["class_name"]), r["name"].lower(), r["student_id"]))
    return {"rows": rows[:limit], "total": len(rows)}
