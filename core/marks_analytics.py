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
    business_today,
)

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
    """Strictly below the pass mark; a tie, or no pass mark at all, is not below.

    The averages are exact to 16+ digits in the database and are compared as floats, which
    collapses the last-digit rounding noise: across 1,492 random true ties with mixed
    maximums none compared as below, so no tolerance is needed.
    """
    return pass_percent is not None and sat < pass_percent


def reporting_term(today):
    """The running term if it has finalized MARKED results, else the latest started one that does."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today)
        .select_related("academic_year")
        .filter(Exists(_counted_results(assessment__term=OuterRef("pk"))))
        .order_by(
            Case(When(end_date__gte=today, then=0), default=1, output_field=IntegerField()),
            "-start_date",
            "-display_order",
        )
        .first()
    )


def term_label(term, today):
    """The term's name, with its year added when it is not from the year running today.

    The reporting term falls back to the latest started term, which may belong to an earlier year;
    the cards then say "Term 3, 2025-26" so nobody reads old marks as this year's. `term` must
    come from `reporting_term` (its year is already loaded).
    """
    if term.academic_year.contains(today):
        return term.name
    return f"{term.name}, {term.academic_year.name}"


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


def student_subject_scores(student, term, scope=None, include_comparison=True):
    """One `SubjectScore` per subject the student has marks in, in subject name order.

    The order ignores case ("art" before "Biology"), like the report card's database sort for
    ordinary names. `include_comparison=False` skips the section average query entirely.
    """
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
    if include_comparison and enrollment is not None:
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
    for name in sorted(scores, key=lambda n: (n.casefold(), n)):
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


def terms_with_results(student, scope=None, today=None):
    """Terms that have started and hold the student's finalized MARKED results, newest first.

    `scope` (a Q on StudentResult) narrows which results count, for a teacher who may see only
    some of them. A term that has not started is never offered, as `reporting_term` never picks one.
    """
    today = business_today() if today is None else today
    return list(
        AcademicTerm.objects.filter(
            Exists(
                _counted_results(
                    assessment__term=OuterRef("pk"), academic_enrollment__student=student
                ).filter(Q() if scope is None else scope)
            ),
            start_date__lte=today,
        )
        .select_related("academic_year")
        .order_by("-start_date", "-display_order")
    )


RADAR_LABEL_CHARS = 10  # about 62px of room beside the radar at 280px wide, at 11px text


def _short_label(name):
    """A radar axis label that fits beside the chart; the full name stays in the bullet chart."""
    if len(name) <= RADAR_LABEL_CHARS:
        return name
    return name[: RADAR_LABEL_CHARS - 1].rstrip() + "\u2026"


def _bullet_row(score):
    display = charts.percent_display(score.score, score.pass_percent)
    pass_display = None if score.pass_percent is None else charts.percent_display(score.pass_percent)
    average_display = (
        None if score.section_average is None else charts.percent_display(score.section_average)
    )
    summary = f"{score.subject_name}: {display}%"
    if score.below_pass:
        summary += f", below the pass mark of {pass_display}%"
    elif pass_display is not None:
        summary += f", pass mark {pass_display}%"
    if average_display is not None:
        summary += f", section average {average_display}%"
    return {
        "score": score,
        "bullet": charts.bullet(score.score, score.pass_percent, score.section_average),
        "display": display,
        "pass_display": pass_display,
        "average_display": average_display,
        "summary": summary,
    }


def student_progress_context(student, term_id, scope=None, include_comparison=True):
    """Everything the student page's Progress section draws, for one term.

    `term_id` is the raw `?term=` text; anything that is not one of the student's own terms with
    results falls back to the newest, so another student's term is never reachable.
    """
    today = business_today()
    terms = terms_with_results(student, scope, today)
    term = next((t for t in terms if str(t.pk) == str(term_id).strip()), None) if term_id else None
    term = term or (terms[0] if terms else None)
    context = {
        "term": term,
        "terms": terms,
        "term_choices": [
            {"id": t.pk, "label": term_label(t, today), "selected": t == term} for t in terms
        ],
        "term_name": None if term is None else term_label(term, today),
        "scores": [],
        "bullets": [],
        "radar": None,
        "radar_note": None,
        "has_section_average": False,
        "has_pass_band": False,
    }
    if term is None:
        return context
    scores = student_subject_scores(student, term, scope, include_comparison)
    context["scores"] = scores
    context["bullets"] = [_bullet_row(score) for score in scores]
    context["has_pass_band"] = any(s.pass_percent is not None for s in scores)
    context["has_section_average"] = any(s.section_average is not None for s in scores)
    if len(scores) < 3:
        context["radar_note"] = "A radar chart needs at least 3 subjects; the bars show each one."
    elif len(scores) > 8:
        context["radar_note"] = "With more than 8 subjects a radar chart is too crowded; the bars show each one."
    else:
        outlines = [
            {"key": "student", "label": student.full_name, "values": [s.score for s in scores]}
        ]
        # The section outline only when every axis has an average: a small section hides its own.
        if all(s.section_average is not None for s in scores):
            outlines.append(
                {"key": "section", "label": "Section average",
                 "values": [s.section_average for s in scores]}
            )
        radar = charts.radar([_short_label(s.subject_name) for s in scores], outlines)
        for label, score in zip(radar["labels"], scores, strict=True):
            label["full"] = score.subject_name
        context["radar"] = radar
        context["radar_values"] = [
            {"name": s.subject_name, "student": charts.percent_display(s.score),
             "average": None if s.section_average is None else charts.percent_display(s.section_average)}
            for s in scores
        ]
    return context


def _join_names(names):
    """"A", "A and B", "A, B and C"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def students_needing_attention(
    term, absent_days, threshold=3, limit=10, *, period_label, term_label=None
):
    """Active students below pass in 2+ subjects, or in 1 subject and absent `threshold`+ days.

    Marks come from `term`; `absent_days` ({student_id: days}) comes from the period the page is
    showing, named by `period_label`. Below-pass is the student page's rule (`_pass_comparison`),
    found for every student by one grouped query. Rows are ordered by class (natural order) and
    name, never by performance. `rows` is the first `limit` of them and `rest` the others, in the
    same order, so a long list can be folded without hiding the senior classes; `total` counts both.
    `term_label` names the term in each reason (default: its name).
    `has_pass_marks` says whether any finalized test in the term has a pass mark, so an empty
    list can be told apart from "nobody could be checked".
    """
    if term is None:
        return {"rows": [], "rest": [], "total": 0, "has_pass_marks": False}
    has_pass_marks = (
        marked_results(term).filter(assessment__pass_mark__isnull=False).order_by().exists()
    )
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
        reason = f"Below pass in {_join_names(subjects)} ({term_label or term.name})"
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
    return {
        "rows": rows[:limit],
        "rest": rows[limit:],
        "total": len(rows),
        "has_pass_marks": has_pass_marks,
    }
