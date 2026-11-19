"""Admin home Academics tab data. Read-only; no HTTP here.

Marks rules (shared with `marks_analytics`): only FINALIZED assessments and MARKED results count
in averages; ABSENT is never a zero and a score of exactly 0 is real. "Results to finish" is the
exception that looks at work not yet official: DRAFT assessments of the work term, and students
whose FINALIZED results (MARKED or ABSENT) have no current term publication.
"""
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse

from core import analytics, charts, marks_analytics
from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    Assessment,
    Section,
    Student,
    StudentResult,
    TermPublication,
    grade_from_bands,
)

# A drop in a student's average of this many points since the previous term puts them at risk.
FALLING_POINTS = 10
IMPROVER_LIMIT = 5


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


def change_words(change):
    """A change in points, in words: "Up 3 points", "Down 1.5 points", "No change"."""
    if round(change, 1) == 0:
        return "No change"
    return ("Up " if change > 0 else "Down ") + marks_analytics.points_text(change)


def class_marks(term):
    """Per class: average, pass rate and grade spread for the term's counted results.

    Two queries: the results, then the frozen grading snapshots of their assessments.
    """
    results = list(
        marks_analytics.marked_results(term)
        .annotate(pass_percent=marks_analytics._PASS_PERCENT)
        .values_list(
            "percent",
            "pass_percent",
            "assessment_id",
            "assessment__offering__class_grade_id",
            "assessment__offering__class_grade__name",
            "assessment__offering__class_grade__display_order",
        )
    )
    snapshots = dict(
        Assessment.objects.filter(pk__in={r[2] for r in results}).values_list(
            "pk", "grading_snapshot"
        )
    )
    classes = {}
    for percent, pass_percent, assessment_id, grade_id, name, order in results:
        c = classes.setdefault(
            grade_id,
            {"name": name, "order": order, "percents": [], "judged": 0, "passed": 0,
             "minimums": {}, "counts": {}},
        )
        c["percents"].append(float(percent))
        if pass_percent is not None:
            c["judged"] += 1
            c["passed"] += percent >= pass_percent
        bands = (snapshots.get(assessment_id) or {}).get("bands")
        if bands:
            for minimum, label in bands:
                minimum = float(minimum)
                if label not in c["minimums"] or minimum > c["minimums"][label]:
                    c["minimums"][label] = minimum
            label = grade_from_bands(bands, percent)
            if label is not None:
                c["counts"][label] = c["counts"].get(label, 0) + 1
    rows = []
    ordered_classes = sorted(classes.items(), key=lambda kv: (kv[1]["order"], kv[1]["name"], kv[0]))
    for grade_id, c in ordered_classes:
        ordered = sorted(c["counts"], key=lambda label: -c["minimums"][label])
        grades = [{"label": label, "count": c["counts"][label]} for label in ordered]
        rows.append(
            {
                "class_grade_id": grade_id,
                "class_name": c["name"],
                "average": round(sum(c["percents"]) / len(c["percents"]), 1),
                "pass_rate": round(c["passed"] * 100 / c["judged"], 1) if c["judged"] else None,
                "grades": grades,
                "grades_display": " · ".join(f"{g['label']} {g['count']}" for g in grades),
            }
        )
    return rows


def class_mark_extremes(rows, *, with_links):
    """The best and worst classes by average mark, or None under four classes."""
    split = analytics.split_extremes(sorted(rows, key=lambda r: (r["average"], r["class_name"])))
    if split is None:
        return None

    def bar(r):
        return {
            "label": r["class_name"],
            "value": r["average"],
            "display": f"{charts.percent_display(r['average'])}%",
            "low": False,
            "url": (
                reverse("core:class-grade-detail", args=[r["class_grade_id"]])
                if with_links
                else None
            ),
        }

    best, worst = split
    return {"best": [bar(r) for r in best], "worst": [bar(r) for r in worst]}


def subject_changes(term, previous):
    """Subject bars, lowest average first, each with its change in points since `previous`."""
    before = (
        {r["subject_name"]: r["average"] for r in marks_analytics.subject_averages(previous)}
        if previous is not None
        else {}
    )
    rows = []
    for r in marks_analytics.subject_averages(term):
        change = (
            round(r["average"] - before[r["subject_name"]], 1)
            if r["subject_name"] in before
            else None
        )
        rows.append(
            {
                "label": r["subject_name"],
                "value": r["average"],
                "display": f"{charts.percent_display(r['average'])}%",
                "low": False,
                "change": change,
                "note": change_words(change) if change is not None else "",
            }
        )
    return rows


def top_improvers(changes, limit=IMPROVER_LIMIT):
    """The students whose average rose most, from `marks_analytics.student_average_changes`.

    Only a rise counts. Active students with an active enrollment, shown in the class of that
    enrollment; largest rise first, then name. One query for names and classes.
    """
    risers = {sid: c for sid, c in changes.items() if c["change"] > 0}
    current = {
        e.student_id: e
        for e in AcademicEnrollment.objects.filter(
            student_id__in=risers,
            status=AcademicEnrollment.Status.ACTIVE,
            student__status=Student.Status.ACTIVE,
        )
        .select_related("student", "class_grade")
        .order_by("start_date", "pk")
    }
    rows = [
        {
            "student_id": sid,
            "name": e.student.full_name,
            "class_name": e.class_grade.name,
            "change": risers[sid]["change"],
            "display": (
                f"{change_words(risers[sid]['change'])} "
                f"({charts.percent_display(risers[sid]['last'])}% \u2192 "
                f"{charts.percent_display(risers[sid]['this'])}%)"
            ),
        }
        for sid, e in current.items()
    ]
    rows.sort(key=lambda r: (-r["change"], r["name"].lower(), r["student_id"]))
    return rows[:limit]


def academics_tab_context(
    today, *, include_progress, publish_rows, include_marks, include_attention,
    include_improvers, class_links,
):
    """The admin home Academics tab. Nothing is queried for a card the viewer may not see.

    Results to finish uses the work term; the marks cards use the reporting term (the latest with
    finalized results) and compare with the term before it. Absent days are this month's.
    """
    needs_marks = include_marks or include_attention or include_improvers
    term = marks_analytics.reporting_term(today) if needs_marks else None
    label = marks_analytics.term_label(term, today) if term else None
    previous = marks_analytics.previous_term(term) if term else None
    previous_label = marks_analytics.term_label(previous, today) if previous else None
    changes = (
        marks_analytics.student_average_changes(term, previous)
        if previous and (include_attention or include_improvers)
        else {}
    )
    classes = class_marks(term) if term and include_marks else []
    attention = None
    if include_attention:
        attention = marks_analytics.students_needing_attention(
            term,
            analytics.absent_day_counts(analytics.month_to_date(today)) if term else {},
            threshold=analytics.ABSENTEE_THRESHOLD_DAYS,
            period_label=analytics.TAB_PERIOD_LABEL,
            term_label=label,
            falling={
                student_id: c["change"]
                for student_id, c in changes.items()
                if c["change"] <= -FALLING_POINTS
            },
            falling_label=previous_label,
        )
    return {
        "progress": results_to_finish(today, publish_rows=publish_rows) if include_progress else None,
        "term": term,
        "term_label": label,
        "previous": previous,
        "previous_label": previous_label,
        "show_marks": include_marks,
        "classes": classes,
        "extremes": class_mark_extremes(classes, with_links=class_links) if include_marks else None,
        "subjects": subject_changes(term, previous) if term and include_marks else [],
        "attention": attention,
        "improvers": top_improvers(changes) if include_improvers else None,
        "class_links": class_links,
    }
