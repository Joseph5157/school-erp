"""Phase 2 attendance reporting semantics (ADR 0007, Gate 7).

Every report and percentage in Phase 2 uses the same definition of
*reportable* attendance, provided by `reportable_entries()`:

- the entry's register is SUBMITTED (missing and DRAFT registers never count);
- the register date is not in the future (school-local business date);
- the register date is instructional in its Academic Year's school calendar
  (weekly pattern plus SchoolCalendarDay exceptions, ADR 0008);
- the register date lies within the entry enrollment's effective range.

Values are the current accepted statuses, i.e. after corrections.

Percentage = PRESENT / (PRESENT + ABSENT) * 100 over reportable entries, or
None when there is nothing reportable.
"""

import calendar
import datetime
from collections import defaultdict

from django.db.models import Count, Exists, F, OuterRef, Q

from core.models import (
    AcademicEnrollment,
    AcademicYear,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    SchoolCalendarDay,
    Section,
    business_today,
)


def _calendar_exception(is_instructional, prefix):
    return Exists(
        SchoolCalendarDay.objects.filter(
            academic_year_id=OuterRef(f"{prefix}academic_year_id"),
            date=OuterRef(f"{prefix}date"),
            is_instructional=is_instructional,
        )
    )


def instructional_q(prefix=""):
    """A Q matching rows whose `<prefix>date` is instructional in its year.

    `prefix` is the path to an AttendanceRegister ("" for registers,
    "register__" for entries).
    """
    sunday = Q(**{f"{prefix}date__week_day": 1})
    saturday_off = Q(
        **{
            f"{prefix}date__week_day": 7,
            f"{prefix}academic_year__saturdays_instructional": False,
        }
    )
    extra_day = _calendar_exception(True, prefix)
    holiday = _calendar_exception(False, prefix)
    return extra_day | (~holiday & ~sunday & ~saturday_off)


def reportable_entries(queryset=None):
    """Entries that count for Phase 2 reports and percentages."""
    queryset = AttendanceEntry.objects.all() if queryset is None else queryset
    return queryset.filter(
        instructional_q("register__"),
        register__status=AttendanceRegister.Status.SUBMITTED,
        register__date__lte=business_today(),
        academic_enrollment__start_date__lte=F("register__date"),
    ).filter(
        Q(academic_enrollment__end_date__isnull=True)
        | Q(academic_enrollment__end_date__gte=F("register__date"))
    )


def percentage(present, absent):
    total = present + absent
    if total == 0:
        return None
    return round(present * 100 / total, 1)


def counts(entries):
    """Present/absent/total/percentage over already-reportable entries."""
    by_status = {
        row["status"]: row["n"]
        for row in entries.order_by().values("status").annotate(n=Count("id"))
    }
    present = by_status.get(AttendanceStatus.PRESENT, 0)
    absent = by_status.get(AttendanceStatus.ABSENT, 0)
    return {
        "present": present,
        "absent": absent,
        "total": present + absent,
        "percentage": percentage(present, absent),
    }


def student_summary(student, start=None, end=None):
    entries = reportable_entries(
        AttendanceEntry.objects.filter(academic_enrollment__student=student)
    )
    if start is not None:
        entries = entries.filter(register__date__gte=start)
    if end is not None:
        entries = entries.filter(register__date__lte=end)
    return counts(entries)


def daily_absentees(on_date):
    """Report 2: reportable ABSENT entries on a date, by Section then name."""
    return (
        reportable_entries()
        .filter(register__date=on_date, status=AttendanceStatus.ABSENT)
        .select_related(
            "academic_enrollment__student",
            "register__section__class_grade",
            "register__academic_year",
        )
        .order_by(
            "register__section__class_grade__name",
            "register__section__name",
            "academic_enrollment__student__full_name",
        )
    )


class _YearCalendar:
    """In-memory instructional-day lookup for one Academic Year (no per-day queries)."""

    def __init__(self, academic_year, exceptions):
        self.year = academic_year
        self.exceptions = exceptions

    def is_instructional(self, on_date):
        if not self.year.contains(on_date):
            return False
        if on_date in self.exceptions:
            return self.exceptions[on_date]
        return self.year.default_is_instructional(on_date)


def _year_calendars(start, end):
    years = list(AcademicYear.objects.filter(start_date__lte=end, end_date__gte=start))
    exceptions = defaultdict(dict)
    for day in SchoolCalendarDay.objects.filter(
        academic_year__in=years, date__gte=start, date__lte=end
    ):
        exceptions[day.academic_year_id][day.date] = day.is_instructional
    return [_YearCalendar(year, exceptions[year.pk]) for year in years]


def _dates(start, end):
    day = start
    while day <= end:
        yield day
        day += datetime.timedelta(days=1)


def expected_registers(start, end, section=None):
    """Instructional (date, Section) pairs on which attendance is expected.

    Expected = an instructional date in an Academic Year, not in the future,
    on which the Section has at least one enrollment of that year effective.
    Sections with nobody enrolled that day are not expected (their register
    could not be submitted). Returns a set of (date, section_id, year_id).
    """
    end = min(end, business_today())
    if start > end:
        return set()
    expected = set()
    for year_calendar in _year_calendars(start, end):
        year = year_calendar.year
        enrollments = AcademicEnrollment.objects.filter(
            academic_year=year, start_date__lte=end
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
        if section is not None:
            enrollments = enrollments.filter(section=section)
        spans = list(enrollments.values_list("section_id", "start_date", "end_date"))
        if not spans:
            continue
        for on_date in _dates(max(start, year.start_date), min(end, year.end_date)):
            if not year_calendar.is_instructional(on_date):
                continue
            for section_id, span_start, span_end in spans:
                if span_start <= on_date and (span_end is None or on_date <= span_end):
                    expected.add((on_date, section_id, year.pk))
    return expected


def missing_attendance(start, end, section=None):
    """Report 5: expected Section/dates whose register is missing or DRAFT.

    Non-instructional dates are never listed. Returns dicts sorted by date
    then Section, each with `state` NOT_TAKEN or DRAFT and the register (or
    None).
    """
    expected = expected_registers(start, end, section=section)
    if not expected:
        return []
    registers = {
        (register.date, register.section_id): register
        for register in AttendanceRegister.objects.filter(
            date__gte=start, date__lte=end, section_id__in={s for _, s, _ in expected}
        )
    }
    sections = Section.objects.select_related("class_grade").in_bulk(
        {section_id for _, section_id, _ in expected}
    )
    rows = []
    for on_date, section_id, _year_id in expected:
        register = registers.get((on_date, section_id))
        if register is not None and register.is_submitted:
            continue
        state = (
            AttendanceRegister.AttendanceState.DRAFT
            if register is not None
            else AttendanceRegister.AttendanceState.NOT_TAKEN
        )
        rows.append(
            {
                "date": on_date,
                "section": sections[section_id],
                "state": state,
                "register": register,
            }
        )
    rows.sort(key=lambda row: (row["date"], str(row["section"])))
    return rows


def month_bounds(year, month):
    last = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last)


def monthly_section_summary(section, year, month):
    """Report 6: per-Student counts and percentage for a Section in a month.

    Students are those with an enrollment in the Section effective on any
    day of the month; counts use only reportable entries recorded in that
    Section. Also returns register-level totals for the month.
    """
    start, end = month_bounds(year, month)
    return section_summary(section, start, end)


def section_summary(section, start, end):
    """Report 6 over any inclusive date window (used by month and by Phase 5
    teacher views limited to a class teacher's assignment dates)."""
    entries = reportable_entries(
        AttendanceEntry.objects.filter(
            register__section=section, register__date__gte=start, register__date__lte=end
        )
    )
    per_student = defaultdict(lambda: {"present": 0, "absent": 0})
    for student_id, status, n in (
        entries.order_by()
        .values_list("academic_enrollment__student_id", "status")
        .annotate(n=Count("id"))
    ):
        key = "present" if status == AttendanceStatus.PRESENT else "absent"
        per_student[student_id][key] += n

    enrollments = (
        AcademicEnrollment.objects.filter(section=section, start_date__lte=end)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
        .select_related("student")
        .order_by("student__full_name", "start_date")
    )
    rows = []
    seen = set()
    for enrollment in enrollments:
        student = enrollment.student
        if student.pk in seen:
            continue
        seen.add(student.pk)
        tally = per_student.get(student.pk, {"present": 0, "absent": 0})
        rows.append(
            {
                "student": student,
                "present": tally["present"],
                "absent": tally["absent"],
                "percentage": percentage(tally["present"], tally["absent"]),
            }
        )

    expected_days = {d for d, _, _ in expected_registers(start, end, section=section)}
    submitted_days = set(
        AttendanceRegister.objects.filter(
            section=section,
            date__gte=start,
            date__lte=end,
            status=AttendanceRegister.Status.SUBMITTED,
        ).values_list("date", flat=True)
    )
    totals = counts(entries)
    totals.update(
        {
            "expected_days": len(expected_days),
            "submitted_days": len(expected_days & submitted_days),
            "missing_days": len(expected_days - submitted_days),
        }
    )
    return {"start": start, "end": end, "rows": rows, "totals": totals}
