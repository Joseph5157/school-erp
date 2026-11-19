"""Admin Overview attendance analytics (Gate A; docs/ADMIN_OVERVIEW_ANALYTICS_PLAN.md).

Read-only aggregates, no HTTP here. Every figure is built on `reports.reportable_entries()`,
so it follows the Phase 2 attendance rules (ADR 0007): only SUBMITTED registers count, no
future dates, only instructional days, and the only statuses are PRESENT and ABSENT.
A day with no submitted data is omitted, never drawn as 0%.
"""

import datetime
from dataclasses import dataclass

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.urls import reverse

from core import charts, marks_analytics, reports
from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    AttendanceRegister,
    AttendanceStatus,
)

# Attendance under this percentage is "low": the gauge turns red and a class column is flagged.
ATTENDANCE_TARGET_PERCENT = 80
# Gate B: a student is a "frequent absentee" at this many absent days in the period.
ABSENTEE_THRESHOLD_DAYS = 3
ABSENTEE_LIST_LIMIT = 10
HEATMAP_DAYS = 28


@dataclass(frozen=True)
class Period:
    start: datetime.date
    end: datetime.date

    @property
    def days(self):
        return (self.end - self.start).days + 1


def current_term(today):
    """The term running today, or None (between terms, or no terms configured)."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today, end_date__gte=today)
        .order_by("start_date")
        .first()
    )


def _entries(period):
    return reports.reportable_entries().filter(
        register__date__gte=period.start, register__date__lte=period.end
    )


def today_strip(today):
    """Present/absent students today plus how many expected registers are submitted."""
    totals = reports.counts(reports.reportable_entries().filter(register__date=today))
    expected = reports.expected_registers(today, today)
    submitted = 0
    if expected:
        submitted = AttendanceRegister.objects.filter(
            date=today,
            status=AttendanceRegister.Status.SUBMITTED,
            section_id__in={section_id for _, section_id, _ in expected},
        ).count()
    return {
        "present": totals["present"],
        "absent": totals["absent"],
        "expected": len(expected),
        "submitted": submitted,
        "not_taken": len(expected) - submitted,
    }


def daily_trend(period):
    """One point per instructional day that has submitted attendance, oldest first."""
    rows = (
        _entries(period)
        .order_by()
        .values("register__date")
        .annotate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        )
        .order_by("register__date")
    )
    return [
        {
            "date": row["register__date"],
            "present": row["present"],
            "absent": row["absent"],
            "percentage": reports.percentage(row["present"], row["absent"]),
        }
        for row in rows
    ]


def class_comparison(period):
    """Attendance % per class for the period, lowest first. Classes with no data are left out."""
    rows = (
        _entries(period)
        .order_by()
        .values(
            "register__class_grade_id",
            "register__class_grade__name",
            "register__class_grade__display_order",
        )
        .annotate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        )
    )
    result = [
        {
            "class_grade_id": row["register__class_grade_id"],
            "class_name": row["register__class_grade__name"],
            "class_order": row["register__class_grade__display_order"],
            "present": row["present"],
            "absent": row["absent"],
            "percentage": reports.percentage(row["present"], row["absent"]),
        }
        for row in rows
    ]
    for row in result:
        row["display"] = charts.percent_display(row["percentage"], ATTENDANCE_TARGET_PERCENT)
    result.sort(key=lambda r: (r["percentage"], r["class_name"]))
    return result


def student_attendance_by_month(student, year, today):
    """One student's attendance per calendar month of `year`, up to `today`, in one query.

    Built on `reports.reportable_entries()`, so only SUBMITTED registers on instructional days
    count. A month with no such day is left out, never drawn as 0%.
    """
    rows = (
        reports.reportable_entries()
        .filter(
            academic_enrollment__student=student,
            academic_enrollment__academic_year=year,
            register__date__lte=today,
        )
        .order_by()
        .annotate(month=TruncMonth("register__date"))
        .values("month")
        .annotate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        )
        .order_by("month")
    )
    return [
        {
            "month": row["month"],
            "label": row["month"].strftime("%b"),
            "present": row["present"],
            "absent": row["absent"],
            "percentage": reports.percentage(row["present"], row["absent"]),
        }
        for row in rows
        if row["present"] + row["absent"]
    ]


def _class_row(row, with_link):
    return {
        "label": row["class_name"],
        "value": row["percentage"],
        "display": f"{charts.percent_display(row['percentage'], ATTENDANCE_TARGET_PERCENT)}%",
        "low": row["percentage"] < ATTENDANCE_TARGET_PERCENT,
        "url": (
            reverse("core:class-grade-detail", args=[row["class_grade_id"]]) if with_link else None
        ),
    }


def frequent_absentees(period, threshold=ABSENTEE_THRESHOLD_DAYS, limit=ABSENTEE_LIST_LIMIT):
    """Students absent on at least `threshold` reportable days in the period, most absent first.

    Returns `{"rows": [...], "total": n}`; `total` is the true count even when `limit` trims
    the rows. The class shown is the student's current ACTIVE enrollment. Constant queries.
    """
    grouped = (
        _entries(period)
        .filter(status=AttendanceStatus.ABSENT)
        .order_by()
        .values("academic_enrollment__student_id", "academic_enrollment__student__full_name")
        .annotate(absent_days=Count("id"))
        .filter(absent_days__gte=threshold)
        .order_by("-absent_days", "academic_enrollment__student__full_name")
    )
    total = grouped.count()
    page = list(grouped[:limit])
    class_by_student = {
        e.student_id: e.class_grade.name
        for e in AcademicEnrollment.objects.filter(
            student_id__in=[r["academic_enrollment__student_id"] for r in page],
            status=AcademicEnrollment.Status.ACTIVE,
        ).select_related("class_grade")
    }
    rows = [
        {
            "student_id": r["academic_enrollment__student_id"],
            "name": r["academic_enrollment__student__full_name"],
            "absent_days": r["absent_days"],
            "class_name": class_by_student.get(r["academic_enrollment__student_id"], ""),
        }
        for r in page
    ]
    return {"rows": rows, "total": total}


def absent_day_counts(period):
    """{student_id: reportable days absent in the period}, from one grouped query."""
    return {
        row["academic_enrollment__student_id"]: row["days"]
        for row in _entries(period)
        .filter(status=AttendanceStatus.ABSENT)
        .order_by()
        .values("academic_enrollment__student_id")
        .annotate(days=Count("id"))
    }


def _heat_tier(percentage):
    if percentage >= 95:
        return "t4"
    if percentage >= 90:
        return "t3"
    if percentage >= 80:
        return "t2"
    return "t1"


def attendance_heatmap(today, days=HEATMAP_DAYS):
    """Calendar grid of whole Monday-Sunday weeks covering the `days` up to `today`.

    Each cell is one of: `data` (submitted attendance, with a tier), `no_data` (a school day
    with nothing submitted - never shown as 0%), `not_school` (not an instructional day), or
    `outside` (before the window or in the future, padding the week).
    """
    start = today - datetime.timedelta(days=days - 1)
    grid_start = start - datetime.timedelta(days=start.weekday())
    grid_end = today + datetime.timedelta(days=6 - today.weekday())
    points = {p["date"]: p for p in daily_trend(Period(start=start, end=today))}
    school_days = {on_date for on_date, _section, _year in reports.expected_registers(start, today)}

    weeks, week = [], []
    day = grid_start
    while day <= grid_end:
        cell = {"date": day, "tier": None, "percentage": None}
        if day < start or day > today:
            cell["state"] = "outside"
        elif day in points:
            cell["state"] = "data"
            cell["percentage"] = points[day]["percentage"]
            cell["tier"] = _heat_tier(points[day]["percentage"])
        elif day in school_days:
            cell["state"] = "no_data"
        else:
            cell["state"] = "not_school"
        week.append(cell)
        if len(week) == 7:
            weeks.append(week)
            week = []
        day += datetime.timedelta(days=1)
    return weeks


def _subject_rows(term):
    """Rows for the horizontal bars: each subject's average, lowest first. Never `low` (red is
    only for attendance under target)."""
    return [
        {
            "label": row["subject_name"],
            "value": row["average"],
            "display": f"{charts.percent_display(row['average'])}%",
            "low": False,
        }
        for row in marks_analytics.subject_averages(term)
    ]



TAB_PERIOD_LABEL = "this month"


def month_to_date(today):
    """The calendar month so far: the 1st to `today`."""
    return Period(today.replace(day=1), today)


def attendance_tab_context(today, *, include_absentees):
    """The admin home Attendance tab: the 4-week heatmap and this month's frequent absentees.

    Absentee names are student data plus attendance, so the caller decides (`include_absentees`);
    without it `absentees` is None and no names are queried.
    """
    heatmap = attendance_heatmap(today)
    return {
        "heatmap": heatmap,
        "has_data": any(cell["state"] == "data" for week in heatmap for cell in week),
        "absentees": frequent_absentees(month_to_date(today)) if include_absentees else None,
        "absentee_threshold": ABSENTEE_THRESHOLD_DAYS,
        "label": TAB_PERIOD_LABEL,
    }


def academics_tab_context(today, *, include_marks, include_attention):
    """The admin home Academics tab: subject averages and students needing attention.

    Marks come from the reporting term, absences from this month. Results are never queried
    unless the caller may see them (`include_marks`, or `include_attention`, which needs results,
    students and attendance); `attention` is None without `include_attention`.
    """
    term = marks_analytics.reporting_term(today) if include_marks or include_attention else None
    label = marks_analytics.term_label(term, today) if term else None
    attention = None
    if include_attention:
        attention = marks_analytics.students_needing_attention(
            term,
            absent_day_counts(month_to_date(today)) if term else {},  # no term, nobody to check
            threshold=ABSENTEE_THRESHOLD_DAYS,
            period_label=TAB_PERIOD_LABEL,
            term_label=label,
        )
    return {
        "show_marks": include_marks,
        "term": term,
        "term_label": label,
        "subjects": _subject_rows(term) if term and include_marks else [],
        "attention": attention,
    }
