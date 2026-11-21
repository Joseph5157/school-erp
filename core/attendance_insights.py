"""Consecutive-absence runs: "absent N school days in a row" (Option A2, ADR 0026).

One shared definition for the administrator report and the class-teacher card.

For a student, an *eligible day* is an instructional day of the enrollment's academic year
(ADR 0008), on or before the business date, on which the student has an effective enrollment
in that year. Its status is ABSENT or PRESENT when a SUBMITTED register holds an entry for that
enrollment (the `reports.reportable_entries` rule), and UNKNOWN otherwise (no register, a DRAFT,
or a submitted register without the student's entry).

The run is counted backwards from the *anchor*, the latest eligible day on or before today.
Today alone gets a grace: if today is UNKNOWN (not taken yet), the anchor moves to the previous
eligible day. Non-instructional days are skipped. ABSENT adds a day; PRESENT, UNKNOWN, a day
with no enrollment, the year start and the teacher's scope start stop the count. At most
`lookback` days are counted; past that boundary the next earlier day, found from the calendar,
enrollments and scope alone, decides whether "30+" is shown.

Computed on every request from current entries and the current calendar, so a correction or a
new holiday changes the next result. Never cache it.
"""

from collections import defaultdict
from datetime import timedelta

from django.db import models
from django.db.models import Count, Exists, Min, OuterRef, Q

from core import reports
from core.authorization import class_teacher_assignments
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    AttendanceEntry,
    AttendanceStatus,
    SectionClassTeacher,
)

DEFAULT_THRESHOLD = 3  # OD-2, the same as dashboard.ABSENTEE_THRESHOLD_DAYS
THRESHOLD_CHOICES = (3, 5, 10)
LOOKBACK_DAYS = 30


class StopReason(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    UNKNOWN = "UNKNOWN", "Attendance not taken"
    ENROLLMENT_GAP = "ENROLLMENT_GAP", "Not enrolled"
    YEAR_START = "YEAR_START", "Start of the academic year"
    LOOKBACK_LIMIT = "LOOKBACK_LIMIT", "Lookback limit"
    SCOPE_START = "SCOPE_START", "Start of the class teacher's assignment"


AT_LEAST_REASONS = {StopReason.UNKNOWN, StopReason.LOOKBACK_LIMIT, StopReason.SCOPE_START}


def _window_start(calendars, today, lookback):
    """The earliest date any run can reach, with its boundary day and today's grace.

    A run visits at most `lookback` eligible days after skipping today, then looks at one more
    day to decide the boundary: `lookback + 2` instructional days per year at most.
    """
    earliest = today
    for calendar in calendars:
        found, day = 0, today
        while day >= calendar.year.start_date and found < lookback + 2:
            if calendar.is_instructional(day):
                found += 1
                earliest = min(earliest, day)
            day -= timedelta(days=1)
    return earliest


def absence_runs(enrollments, today, *, threshold, lookback=LOOKBACK_DAYS, scope_start=None):
    """Current absence runs of at least `threshold` school days for `enrollments`.

    `enrollments` is a queryset of AcademicEnrollments effective `today` (the viewer's scope).
    `scope_start` maps an enrollment id to its earliest visible date (the teacher view). Returns
    dicts sorted by `days` (highest first), then name. A fixed number of queries whatever the
    number of students.
    """
    first_start = AcademicYear.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).aggregate(first=Min("start_date"))["first"]
    if first_start is None:
        return []
    calendars = {
        calendar.year.pk: calendar
        for calendar in reports._year_calendars(first_start, today)
        if calendar.year.contains(today)
    }
    window_start = _window_start(calendars.values(), today, lookback)

    # Only students with `threshold` reportable absences in the window can reach it.
    candidates = (
        reports.reportable_entries(
            AttendanceEntry.objects.filter(
                status=AttendanceStatus.ABSENT,
                register__date__gte=window_start,
                register__date__lte=today,
                academic_enrollment__student_id__in=enrollments.values("student_id"),
            )
        )
        .order_by()
        .values("academic_enrollment__student_id")
        .annotate(n=Count("id"))
        .filter(n__gte=threshold)
        .values("academic_enrollment__student_id")
    )
    chains = defaultdict(list)
    scoped = {}
    for enrollment in (
        AcademicEnrollment.objects.filter(
            student_id__in=candidates, start_date__lte=today, academic_year_id__in=list(calendars)
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=window_start))
        .annotate(in_scope=Exists(enrollments.filter(pk=OuterRef("pk"))))
        .select_related("student", "class_grade", "section")
    ):
        chains[(enrollment.student_id, enrollment.academic_year_id)].append(enrollment)
        if enrollment.in_scope:
            scoped[enrollment.student_id] = enrollment
    if not scoped:
        return []

    enrollment_ids = [enrollment.pk for chain in chains.values() for enrollment in chain]
    statuses = {
        (enrollment_id, on_date): status
        for enrollment_id, on_date, status in reports.reportable_entries(
            AttendanceEntry.objects.filter(
                academic_enrollment_id__in=enrollment_ids,
                register__date__gte=window_start,
                register__date__lte=today,
            )
        ).values_list("academic_enrollment_id", "register__date", "status")
    }

    scope_start = scope_start or {}
    results = []
    for student_id, enrollment in scoped.items():
        chain = chains[(student_id, enrollment.academic_year_id)]
        run = _count_run(
            chain, calendars[enrollment.academic_year_id], statuses, today,
            lookback=lookback, scope_from=scope_start.get(enrollment.pk),
        )
        if run["days"] < threshold:
            continue
        run.update(
            student_id=student_id,
            name=enrollment.student.full_name,
            class_name=enrollment.class_grade.name,
            section_name=enrollment.section.name,
        )
        results.append(run)
    results.sort(key=lambda r: (-r["days"], r["name"].casefold(), r["student_id"]))
    return results


def _count_run(chain, calendar, statuses, today, *, lookback, scope_from):
    """Count one student's current run within one academic year (spec 5.1)."""

    def enrollment_on(on_date):
        for enrollment in chain:
            if enrollment.start_date <= on_date and (
                enrollment.end_date is None or on_date <= enrollment.end_date
            ):
                return enrollment
        return None

    days, first_date, last_date, as_of, unknown_date = 0, None, None, None, None
    stopped_by = None
    day = today
    year_start = calendar.year.start_date
    while stopped_by is None:
        while day >= year_start and not calendar.is_instructional(day):
            day -= timedelta(days=1)
        if day < year_start:
            stopped_by = StopReason.YEAR_START
            break
        enrollment = enrollment_on(day)
        if enrollment is None:
            stopped_by = StopReason.ENROLLMENT_GAP
        elif scope_from is not None and day < scope_from:
            stopped_by = StopReason.SCOPE_START
        elif days == lookback:
            stopped_by = StopReason.LOOKBACK_LIMIT
        else:
            status = statuses.get((enrollment.pk, day))
            if status is None and day == today:
                pass  # today's register is not taken yet: the today-only grace
            else:
                as_of = as_of or day
                if status is None:
                    stopped_by, unknown_date = StopReason.UNKNOWN, day
                elif status == AttendanceStatus.PRESENT:
                    stopped_by = StopReason.PRESENT
                else:
                    days += 1
                    last_date = last_date or day
                    first_date = day
        day -= timedelta(days=1)
    return {
        "days": days,
        "first_date": first_date,
        "last_date": last_date,
        "as_of": as_of,
        "stopped_by": stopped_by,
        "at_least": stopped_by in AT_LEAST_REASONS,
        "unknown_date": unknown_date,
    }


def class_teacher_absence_runs(user, today, *, threshold=DEFAULT_THRESHOLD):
    """Runs for the class teacher's own Sections and years today (spec 5.4).

    A Section that is ambiguous today contributes nothing (Security Gate 3A): it has more than
    one effective class teacher assignment across all years, or enrollments effective today in
    more than one year. Each run is clipped to the later of the enrollment start and the
    assignment start (ADR 0012 D9), so a teacher never sees days before their assignment.
    """
    duties = list(
        class_teacher_assignments(user, today).values_list(
            "section_id", "academic_year_id", "start_date"
        )
    )
    if not duties:
        return []
    section_ids = {section_id for section_id, _, _ in duties}
    shared = {
        row["section_id"]
        for row in SectionClassTeacher.objects.filter(section_id__in=section_ids)
        .effective_on(today)
        .order_by()
        .values("section_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    }
    mixed_years = {
        row["section_id"]
        for row in AcademicEnrollment.objects.effective_on(today)
        .filter(section_id__in=section_ids)
        .order_by()
        .values("section_id")
        .annotate(n=Count("academic_year_id", distinct=True))
        .filter(n__gt=1)
    }
    duty_start = {
        (section_id, year_id): start
        for section_id, year_id, start in duties
        if section_id not in shared and section_id not in mixed_years
    }
    if not duty_start:
        return []
    scope = Q(pk__in=[])
    for section_id, year_id in duty_start:
        scope |= Q(section_id=section_id, academic_year_id=year_id)
    scope_start = {}
    ids = []
    for pk, section_id, year_id, start in (
        AcademicEnrollment.objects.effective_on(today)
        .filter(scope)
        .values_list("pk", "section_id", "academic_year_id", "start_date")
    ):
        ids.append(pk)
        scope_start[pk] = max(start, duty_start[(section_id, year_id)])
    if not ids:
        return []
    return absence_runs(
        AcademicEnrollment.objects.filter(pk__in=ids), today, threshold=threshold,
        scope_start=scope_start,
    )
