"""Admin Overview attendance analytics (Gate A; docs/ADMIN_OVERVIEW_ANALYTICS_PLAN.md).

Read-only aggregates, no HTTP here. Every figure is built on `reports.reportable_entries()`,
so it follows the Phase 2 attendance rules (ADR 0007): only SUBMITTED registers count, no
future dates, only instructional days, and the only statuses are PRESENT and ABSENT.
A day with no submitted data is omitted, never drawn as 0%.
"""

import datetime
import re
from dataclasses import dataclass

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q
from django.urls import reverse

from core import charts, marks_analytics, reports
from core.charts import shares
from core.models import (
    AcademicEnrollment,
    AcademicTerm,
    Assessment,
    AttendanceRegister,
    AttendanceStatus,
    ResultStatus,
    Student,
    StudentResult,
    TermPublication,
    business_today,
)

# Attendance under this percentage is "low": the gauge turns red and a class column is flagged.
ATTENDANCE_TARGET_PERCENT = 80
DEFAULT_PERIOD_DAYS = 14
# Gate C: the longest custom range accepted, so a typo cannot ask for decades of registers.
MAX_CUSTOM_DAYS = 366
# Gate C: score bands, highest first, as (minimum percentage, label).
MARK_BANDS = ((80, "80% and above"), (60, "60–79%"), (40, "40–59%"), (0, "Below 40%"))
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


def current_term(today):
    """The term running today, or None (between terms, or no terms configured)."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today, end_date__gte=today)
        .order_by("start_date")
        .first()
    )


def _parse_date(value):
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _custom_label(start, end, today):
    if start.year == end.year == today.year:
        return f"{start.day} {start:%b} – {end.day} {end:%b}"
    return f"{start.day} {start:%b %Y} – {end.day} {end:%b %Y}"


def resolve_period(params, today):
    """Turn the Overview's GET params into one safe Period.

    `period` is 14d (default), month, term or custom (`from` / `to`, ISO dates). Anything
    unusable falls back to the default 14 days; a bad *custom* or *term* request also carries a
    `notice` so the page can say why. The end is never after today.
    """
    term = current_term(today)
    default = default_period(today)
    key = params.get("period") or "14d"
    raw_from, raw_to = params.get("from") or "", params.get("to") or ""
    choice = {
        "key": "14d",
        "period": default,
        "label": f"last {default.days} days",
        "notice": None,
        "term": term,
        "custom_from": raw_from if key == "custom" else "",
        "custom_to": raw_to if key == "custom" else "",
    }

    def fall_back(reason):
        choice["notice"] = f"{reason} Showing the last {DEFAULT_PERIOD_DAYS} days instead."
        return choice

    def use(chosen_key, period, label):
        choice.update(key=chosen_key, period=period, label=label)
        return choice

    if key == "month":
        return use("month", Period(start=today.replace(day=1), end=today), "this month")
    if key == "term":
        if term is None:
            return fall_back("No term is running today.")
        return use("term", Period(start=term.start_date, end=min(term.end_date, today)), term.name)
    if key == "custom":
        start, end = _parse_date(raw_from), _parse_date(raw_to)
        if start is None or end is None:
            return fall_back("Choose both dates.")
        if start > today:
            return fall_back("The start date is in the future.")
        if start > end:
            return fall_back("The start date must be on or before the end date.")
        end = min(end, today)
        if (end - start).days + 1 > MAX_CUSTOM_DAYS:
            return fall_back("Choose a range of at most one year.")
        return use("custom", Period(start=start, end=end), _custom_label(start, end, today))
    return choice


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
            "class_grade_id": row["register__class_grade_id"],
            "class_name": row["register__class_grade__name"],
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


def term_attendance(today):
    """Attendance for the term running today, for the gauge. None when no term runs or no data."""
    term = current_term(today)
    if term is None:
        return None
    totals = reports.counts(_entries(Period(start=term.start_date, end=min(term.end_date, today))))
    if totals["percentage"] is None:
        return None
    # The unrounded figure: the gauge turns red and says "met" on it, and shows a rounded display.
    percent = totals["percentage"]
    return {
        "term": term,
        "percent": percent,
        "chart": charts.gauge(percent, ATTENDANCE_TARGET_PERCENT),
    }


def ring_term(today):
    """The most recently started term: the running one, or the one that just ended."""
    return (
        AcademicTerm.objects.filter(start_date__lte=today)
        .order_by("-start_date", "-display_order")
        .first()
    )


def completion_rings(today, *, can_view_results, can_view_publications,
                     missing_attendance_url, strip=None):
    """The "still to finish" rings, each `{key, label, term_name, chart, url}`.

    Registers today shows whenever a school day expects registers; `missing_attendance_url` is
    the report's bare URL and the ring links to it for today. Marks entered and Results
    published use `ring_term` and always name that term in the label; they appear only for
    viewers allowed to see that data. Results published counts students who are ACTIVE and
    enrolled in the term, once each, with a PUBLISHED result. A correction marks a publication
    STALE in the database (`publication._mark_stale`), so counting PUBLISHED does not
    overcount. Constant queries however many students or classes exist.
    """
    strip = today_strip(today) if strip is None else strip
    rings = []
    registers = charts.ring(strip["submitted"], strip["expected"])
    if registers is not None:
        rings.append(
            {
                "key": "registers",
                "label": "Registers today",
                "term_name": "",
                "chart": registers,
                "url": (
                    f"{missing_attendance_url}?start={today:%Y-%m-%d}&end={today:%Y-%m-%d}"
                    if missing_attendance_url
                    else None
                ),
            }
        )
    term = ring_term(today)
    if term is None:
        return rings
    if can_view_results:
        totals = Assessment.objects.filter(term=term, assessment_date__lte=today).aggregate(
            total=Count("id"),
            finalized=Count("id", filter=Q(status=Assessment.Status.FINALIZED)),
        )
        chart = charts.ring(totals["finalized"], totals["total"])
        if chart is not None:
            rings.append(
                {
                    "key": "marks",
                    "label": f"Marks entered, {term.name}",
                    "term_name": term.name,
                    "chart": chart,
                    "url": None,
                }
            )
    if can_view_publications:
        enrolled_ids = (
            AcademicEnrollment.objects.filter(
                academic_year_id=term.academic_year_id,
                start_date__lte=term.end_date,
                student__status=Student.Status.ACTIVE,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=term.start_date))
            .values("student_id")
        )
        enrolled = enrolled_ids.distinct().count()
        published = (
            TermPublication.objects.filter(
                term=term,
                status=TermPublication.Status.PUBLISHED,
                student_id__in=enrolled_ids,
            )
            .values("student_id")
            .distinct()
            .count()
        )
        chart = charts.ring(published, enrolled)
        if chart is not None:
            rings.append(
                {
                    "key": "published",
                    "label": f"Results published, {term.name}",
                    "term_name": term.name,
                    "chart": chart,
                    "url": None,
                }
            )
    return rings


def _natural_key(name):
    """Sort "Grade 2" before "Grade 10"."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


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


def marks_snapshot(today):
    """Score bands for the reporting term (`marks_analytics.reporting_term`).

    Only FINALIZED assessments count. A score is turned into a percentage of its own
    assessment's maximum, so tests out of different totals compare fairly. An ABSENT result is
    never a zero: it is left out of every average and band and only reported as a count.
    Returns None when no started term has any finalized marked result.
    """
    term = marks_analytics.reporting_term(today)
    if term is None:
        return None
    percent = ExpressionWrapper(
        F("score") * 100 / F("assessment__maximum_marks"),
        output_field=DecimalField(max_digits=9, decimal_places=4),
    )
    results = StudentResult.objects.filter(
        assessment__term=term, assessment__status=Assessment.Status.FINALIZED
    ).annotate(percent=percent)
    minimums = [minimum for minimum, _ in MARK_BANDS]
    aggregate = results.aggregate(
        absent=Count("id", filter=Q(status=ResultStatus.ABSENT)),
        **{
            f"band_{i}": Count(
                "id",
                filter=Q(status=ResultStatus.MARKED, percent__gte=minimum)
                & (Q(percent__lt=minimums[i - 1]) if i else Q()),
            )
            for i, minimum in enumerate(minimums)
        },
    )
    counts = [aggregate[f"band_{i}"] for i in range(len(MARK_BANDS))]
    band_shares = shares(counts)
    return {
        "term": term,
        "bands": [
            {"label": label, "count": count, "share": share}
            for (_, label), count, share in zip(MARK_BANDS, counts, band_shares, strict=True)
        ],
        # Columns show the count; the height is the band's share of all marked results.
        "band_columns": charts.columns(
            [
                {"label": label, "value": share, "display": str(count), "low": False}
                for (_, label), count, share in zip(MARK_BANDS, counts, band_shares, strict=True)
            ]
        ),
        "total": sum(counts),
        "absent": aggregate["absent"],
    }


def overview_context(
    today=None,
    *,
    include_absentees=False,
    include_marks=False,
    include_publications=False,
    include_class_links=False,
    missing_attendance_url=None,
    params=None,
):
    """Everything the Overview analytics render, school-wide.

    Student names are personal data, so the absentee list is only built when the caller says
    the user may view students; otherwise `absentees` is None and the section is not shown.
    Marks are only built for callers who may view results. `params` (the GET query) picks the
    attendance period; the heatmap, today strip and marks snapshot are independent of it.
    Class columns and bars link to the class page only when `include_class_links` says the
    viewer may open it; the registers ring links to the report only when a URL is given.
    """
    today = business_today() if today is None else today
    marks = marks_snapshot(today) if include_marks else None
    choice = resolve_period(params or {}, today)
    period = choice["period"]
    points = daily_trend(period)
    strip = today_strip(today)
    classes = class_comparison(period)
    term_gauge = term_attendance(today)
    return {
        "choice": choice["key"],
        "label": choice["label"],
        "notice": choice["notice"],
        "term": choice["term"],
        "custom_from": choice["custom_from"],
        "custom_to": choice["custom_to"],
        "show_marks": include_marks,
        "marks": marks,
        "marks_subjects": _subject_rows(marks["term"]) if marks else [],
        "today": today,
        "absentees": frequent_absentees(period) if include_absentees else None,
        "absentee_threshold": ABSENTEE_THRESHOLD_DAYS,
        "heatmap": attendance_heatmap(today),
        "period": period,
        "period_days": period.days,
        "strip": strip,
        "attendance_target": ATTENDANCE_TARGET_PERCENT,
        "gauge": term_gauge["chart"] if term_gauge else None,
        "donut": charts.donut([("Present", strip["present"]), ("Absent", strip["absent"])]),
        "rings": completion_rings(
            today,
            can_view_results=include_marks,
            can_view_publications=include_publications,
            missing_attendance_url=missing_attendance_url,
            strip=strip,
        ),
        "class_columns": charts.columns(
            [
                _class_row(row, include_class_links)
                for row in sorted(classes, key=lambda r: _natural_key(r["class_name"]))
            ]
        ),
        "class_bars_phone": [_class_row(row, include_class_links) for row in classes[:5]],
        "class_bars_rest": [
            _class_row(row, include_class_links)
            for row in sorted(classes[5:], key=lambda r: _natural_key(r["class_name"]))
        ],
        "class_links": include_class_links,
        "points": points,
        "summary": trend_summary(period, points),
        "chart": trend_chart(points, width=320, height=120),
        # Desktop draws its own, wider and flatter chart; scaling the phone one up made it huge.
        "chart_wide": trend_chart(points, width=720, height=200),
        "classes": classes,
    }
