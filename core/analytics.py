"""Admin Overview attendance analytics (Gate A; docs/ADMIN_OVERVIEW_ANALYTICS_PLAN.md).

Read-only aggregates, no HTTP here. Every figure is built on `reports.reportable_entries()`,
so it follows the Phase 2 attendance rules (ADR 0007): only SUBMITTED registers count, no
future dates, only instructional days, and the only statuses are PRESENT and ABSENT.
A day with no submitted data is omitted, never drawn as 0%.
"""

import datetime
from dataclasses import dataclass

from django.db.models import Count, Q

from core import reports
from core.models import AcademicEnrollment, AttendanceRegister, AttendanceStatus, business_today

DEFAULT_PERIOD_DAYS = 14
# Gate B: a student is a "frequent absentee" at this many absent days in the period.
ABSENTEE_THRESHOLD_DAYS = 3
ABSENTEE_LIST_LIMIT = 10
HEATMAP_DAYS = 28
# A change smaller than this many percentage points is reported as "steady".
STEADY_BAND = 1.0


@dataclass(frozen=True)
class Period:
    start: datetime.date
    end: datetime.date

    @property
    def days(self):
        return (self.end - self.start).days + 1


def default_period(today, days=DEFAULT_PERIOD_DAYS):
    return Period(start=today - datetime.timedelta(days=days - 1), end=today)


def previous_period(period):
    """The same-length window immediately before `period` (no gap, no overlap)."""
    end = period.start - datetime.timedelta(days=1)
    return Period(start=end - datetime.timedelta(days=period.days - 1), end=end)


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


def trend_summary(period, points=None):
    """Period attendance vs the previous equivalent period, plus the best and worst day."""
    points = daily_trend(period) if points is None else points
    if not points:
        return {
            "has_data": False, "status": "no_data", "current": None, "previous": None,
            "delta": None, "peak": None, "lowest": None,
        }
    current = reports.percentage(
        sum(p["present"] for p in points), sum(p["absent"] for p in points)
    )
    previous = reports.counts(_entries(previous_period(period)))["percentage"]
    delta = None if previous is None else round(current - previous, 1)
    if delta is None:
        status = "no_comparison"
    elif delta >= STEADY_BAND:
        status = "improving"
    elif delta <= -STEADY_BAND:
        status = "worsening"
    else:
        status = "steady"
    return {
        "has_data": True,
        "status": status,
        "current": current,
        "previous": previous,
        "delta": delta,
        "delta_abs": None if delta is None else abs(delta),
        "peak": max(points, key=lambda p: (p["percentage"], -p["date"].toordinal())),
        "lowest": min(points, key=lambda p: (p["percentage"], p["date"].toordinal())),
    }


def class_comparison(period):
    """Attendance % per class for the period, lowest first. Classes with no data are left out."""
    rows = (
        _entries(period)
        .order_by()
        .values("register__class_grade_id", "register__class_grade__name")
        .annotate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        )
    )
    result = [
        {
            "class_name": row["register__class_grade__name"],
            "present": row["present"],
            "absent": row["absent"],
            "percentage": reports.percentage(row["present"], row["absent"]),
        }
        for row in rows
    ]
    result.sort(key=lambda r: (r["percentage"], r["class_name"]))
    return result


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


def trend_chart(points, *, width, height, pad=8):
    """Scale trend points into SVG coordinates (no JS, no chart library).

    x follows the calendar date; y follows the percentage over a floored axis (rounded down
    to 10 below the lowest value, capped at 100) so small changes stay visible, and the axis
    bounds are returned so the chart can label them. Returns None when there is nothing to draw.
    """
    if not points:
        return None
    low = min(p["percentage"] for p in points)
    y_min = max(0, int((low - 10) // 10 * 10))
    y_max = 100
    first, last = points[0]["date"], points[-1]["date"]
    span_days = (last - first).days
    inner_w, inner_h = width - 2 * pad, height - 2 * pad

    coords = []
    for p in points:
        x = pad + inner_w / 2 if span_days == 0 else pad + inner_w * (p["date"] - first).days / span_days
        y = pad + inner_h * (y_max - p["percentage"]) / (y_max - y_min)
        coords.append((round(x, 1), round(y, 1)))

    baseline = round(height - pad, 1)
    line = " ".join(f"{x},{y}" for x, y in coords)
    area = f"{coords[0][0]},{baseline} {line} {coords[-1][0]},{baseline}"
    return {
        "coords": coords,
        "line": line,
        "area": area,
        "dots": [
            {"x": x, "y": y, "date": p["date"], "percentage": p["percentage"]}
            for (x, y), p in zip(coords, points, strict=True)
        ],
        "y_min": y_min,
        "y_max": y_max,
        "width": width,
        "height": height,
    }


def overview_context(today=None, *, include_absentees=False):
    """Everything the Overview attendance section renders, school-wide.

    Student names are personal data, so the absentee list is only built when the caller says
    the user may view students; otherwise `absentees` is None and the section is not shown.
    """
    today = business_today() if today is None else today
    period = default_period(today)
    points = daily_trend(period)
    return {
        "absentees": frequent_absentees(period) if include_absentees else None,
        "absentee_threshold": ABSENTEE_THRESHOLD_DAYS,
        "heatmap": attendance_heatmap(today),
        "period": period,
        "period_days": period.days,
        "strip": today_strip(today),
        "points": points,
        "summary": trend_summary(period, points),
        "chart": trend_chart(points, width=320, height=120),
        "classes": class_comparison(period),
    }
