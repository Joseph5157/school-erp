"""Teacher-clash calculation for the timetable (ADR 0021 D5, D6 R6).

The one place that answers "is a teacher scheduled into two Sections in the
same period and weekday on the same date?". The save-time check
(`ensure_no_clash`, used by the slot lifecycle methods) and the later drift
report (`find_all_clashes`) share `_pair_clashes`, so the rule is never
re-implemented in `clean()` methods, forms or views.

A slot has no stored teacher. Its teacher on a date is the holder of the
`AssessmentTeacherAssignment` for the same offering + Section effective that
day (ADR 0018). The holder's current account state (active, Teachers group) is
an authorization question and plays no part here: history and planned clashes
follow the assignment rows alone (ADR 0018 D9). Everything here works on date ranges, never on
"today's teacher".
"""

from dataclasses import dataclass
from datetime import date
from itertools import combinations

from django.core.exceptions import ValidationError
from django.db.models import Q

from core.models import (
    AcademicYear,
    AssessmentTeacherAssignment,
    TimetableSlot,
    _as_date,
)


@dataclass(frozen=True)
class Clash:
    """`teacher` is derived for both `slot` and `other` from `start` to `end` inclusive."""

    slot: TimetableSlot
    other: TimetableSlot
    teacher: object
    start: date
    end: date


def slot_last_effective_date(slot):
    """A null end date runs to the end of the Period's Academic Year (ADR 0021 D3)."""
    return _as_date(slot.end_date) or _as_date(slot.period.academic_year.end_date)


def _assignment_spans(pairs):
    """{(offering_id, section_id): [(teacher, first, last), ...]} from assignment rows."""
    if not pairs:
        return {}
    rows = (
        AssessmentTeacherAssignment.objects.filter(
            offering_id__in={offering for offering, _ in pairs},
            section_id__in={section for _, section in pairs},
        )
        .select_related("teacher", "offering__academic_year")
    )
    spans = {}
    for row in rows:
        key = (row.offering_id, row.section_id)
        if key in pairs:
            spans.setdefault(key, []).append(
                (row.teacher, _as_date(row.start_date), row.last_effective_date)
            )
    return spans


def _pair_clashes(slot, other, spans):
    """Clashes between two slots of one period + weekday in different Sections."""
    first = max(_as_date(slot.start_date), _as_date(other.start_date))
    last = min(slot_last_effective_date(slot), slot_last_effective_date(other))
    if first > last:
        return []
    clashes = []
    for teacher, a_first, a_last in spans.get((slot.offering_id, slot.section_id), ()):
        for other_teacher, b_first, b_last in spans.get((other.offering_id, other.section_id), ()):
            if teacher.pk != other_teacher.pk:
                continue
            start = max(first, a_first, b_first)
            end = min(last, a_last, b_last)
            if start <= end:
                clashes.append(Clash(slot, other, teacher, start, end))
    return clashes


def find_clashes(slot):
    """Clashes `slot` (saved or not) has with other Sections' saved slots."""
    first = _as_date(slot.start_date)
    last = slot_last_effective_date(slot)
    others = (
        TimetableSlot.objects.filter(period_id=slot.period_id, weekday=slot.weekday)
        .exclude(section_id=slot.section_id)
        .filter(start_date__lte=last)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=first))
        .select_related("period__academic_year", "section", "offering__subject")
    )
    if slot.pk is not None:
        others = others.exclude(pk=slot.pk)
    others = list(others)
    pairs = {(slot.offering_id, slot.section_id)} | {(o.offering_id, o.section_id) for o in others}
    spans = _assignment_spans(pairs)
    return [clash for other in others for clash in _pair_clashes(slot, other, spans)]


def find_all_clashes(academic_year):
    """Every clash among the saved slots of `academic_year`, once per pair of slots.

    Used for the drift report: later assignment changes can create clashes the
    save-time check could not know about.
    """
    slots = list(
        TimetableSlot.objects.filter(period__academic_year=academic_year).select_related(
            "period__academic_year", "section__class_grade", "offering__subject"
        )
    )
    spans = _assignment_spans({(s.offering_id, s.section_id) for s in slots})
    cells = {}
    for slot in slots:
        cells.setdefault((slot.period_id, slot.weekday), []).append(slot)
    clashes = []
    for cell in cells.values():
        for slot, other in combinations(cell, 2):
            if slot.section_id != other.section_id:
                clashes.extend(_pair_clashes(slot, other, spans))
    return clashes


def _teacher_name(user):
    return user.get_full_name() or user.get_username()


def ensure_no_clash(slot):
    """Raise ValidationError if saving `slot` would schedule a known teacher twice."""
    clashes = find_clashes(slot)
    if not clashes:
        return
    lines = [
        f"{_teacher_name(c.teacher)} already teaches {c.other.section} "
        f"({c.other.offering.subject.name}) in {slot.period.label} on "
        f"{slot.get_weekday_display()} from {c.start:%d %b %Y} to {c.end:%d %b %Y}."
        for c in clashes
    ]
    raise ValidationError(lines)


def todays_teacher_timetable(assignments, today, year_is_instructional):
    """Rows for the Teacher dashboard's "Today's timetable" section (ADR 0021 D10).

    `assignments` are the teacher's own current subject assignments (ADR 0018); a slot
    belongs to the teacher only through its offering + Section. `year_is_instructional`
    answers `AcademicYear.is_instructional_day(today)` for a year (and may cache it).

    Returns None when the section must be hidden: no slot is effective today in an
    Academic Year that is an instructional day today (no timetable configured, or a
    non-school day). Otherwise a list of rows, possibly empty (the "no periods for you"
    state), ordered by period sequence. Never stores or guesses a teacher, and never
    invents free periods or placeholders.
    """
    years = AcademicYear.objects.filter(
        pk__in=TimetableSlot.objects.effective_on(today).values("period__academic_year_id")
    )
    open_year_ids = {year.pk for year in years if year_is_instructional(year)}
    if not open_year_ids:
        return None
    pairs = {(row.offering_id, row.section_id) for row in assignments}
    if not pairs:
        return []
    slots = (
        TimetableSlot.objects.effective_on(today)
        .filter(
            weekday=today.weekday(),
            period__academic_year_id__in=open_year_ids,
            offering_id__in={offering for offering, _ in pairs},
            section_id__in={section for _, section in pairs},
        )
        .select_related("period", "section__class_grade", "offering__subject")
        .order_by("period__sequence", "section__class_grade__name", "section__name")
    )
    return [
        {
            "period": slot.period.label,
            "section": slot.section,
            "subject": slot.offering.subject.name,
        }
        for slot in slots
        if (slot.offering_id, slot.section_id) in pairs
    ]
