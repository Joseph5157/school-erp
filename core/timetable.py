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

import re
from dataclasses import dataclass
from datetime import date, timedelta
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


def teacher_timetable_on(assignments, on_date, year_is_instructional):
    """Rows for the teacher's timetable on `on_date` (ADR 0021 D10).

    `assignments` are the teacher's own current subject assignments (ADR 0018); a slot
    belongs to the teacher only through its offering + Section. `year_is_instructional`
    answers `AcademicYear.is_instructional_day(on_date)` for a year (and may cache it).

    Returns None when the section must be hidden: no slot is effective on that date in an
    Academic Year that is an instructional day on that date (no timetable configured, or a
    non-school day). Otherwise a list of rows, possibly empty (the "no periods for you"
    state), ordered by period sequence. Never stores or guesses a teacher, and never
    invents free periods or placeholders.
    """
    years = AcademicYear.objects.filter(
        pk__in=TimetableSlot.objects.effective_on(on_date).values("period__academic_year_id")
    )
    open_year_ids = {year.pk for year in years if year_is_instructional(year)}
    if not open_year_ids:
        return None
    pairs = {(row.offering_id, row.section_id) for row in assignments}
    if not pairs:
        return []
    slots = (
        TimetableSlot.objects.effective_on(on_date)
        .filter(
            weekday=on_date.weekday(),
            period__academic_year_id__in=open_year_ids,
            offering_id__in={offering for offering, _ in pairs},
            section_id__in={section for _, section in pairs},
        )
        .select_related("period", "section__class_grade", "offering__subject")
        .order_by("period__sequence", "section__class_grade__display_order", "section__name")
    )
    return [
        {
            "period": slot.period.label,
            "sequence": slot.period.sequence,
            "section": slot.section,
            "subject": slot.offering.subject.name,
        }
        for slot in slots
        if (slot.offering_id, slot.section_id) in pairs
    ]


def todays_teacher_timetable(assignments, today, year_is_instructional):
    """Today's rows for the Teacher dashboard's Timetable card (ADR 0021 D10, amended 2026-11-17)."""
    return teacher_timetable_on(assignments, today, year_is_instructional)


TIMETABLE_DATE_WINDOW_DAYS = 366


def short_section_label(section):
    """Short chip/grid label for a Section: "Grade 2" + "B" -> "2-B", "Nursery" + "Rose" -> "Nur-Ros".

    Class part: the trailing number of the Class/Grade name, otherwise its first 3 characters.
    Section part: the Section name when it is 1 or 2 characters long, otherwise its first 3.
    The full name must always be shown or announced next to it; the label alone may clash.
    """
    grade = section.class_grade.name.strip()
    number = re.search(r"(\d+)$", grade)
    class_part = number.group(1) if number else grade[:3]
    name = section.name.strip()
    section_part = name if len(name) <= 2 else name[:3]
    return f"{class_part}-{section_part}"


def parse_timetable_date(raw, today):
    """Parse ?date=; anything invalid or outside today +/- 366 days is today."""
    try:
        parsed = date.fromisoformat(raw)
    except (ValueError, TypeError):
        return today
    if abs((parsed - today).days) > TIMETABLE_DATE_WINDOW_DAYS:
        return today
    return parsed


def date_strip(selected, today):
    """Mon-Sat chips from two weeks before to two weeks after selected's week."""
    monday = selected - timedelta(days=selected.weekday())
    chips = []
    previous = None
    for week in range(-2, 3):
        for offset in range(6):
            day = monday + timedelta(weeks=week, days=offset)
            chips.append(
                {
                    "date": day,
                    "weekday": day.strftime("%a"),
                    "day": day.day,
                    "is_today": day == today,
                    "is_selected": day == selected,
                    "month_start": previous is not None and day.month != previous,
                }
            )
            previous = day.month
    return chips


def _week_heading(first, last):
    """"12 – 17 Oct 2026", "28 Sep – 3 Oct 2026", "28 Dec 2026 – 2 Jan 2027"."""
    if first.year != last.year:
        return f"{first.day} {first:%b %Y} – {last.day} {last:%b %Y}"
    if first.month != last.month:
        return f"{first.day} {first:%b} – {last.day} {last:%b %Y}"
    return f"{first.day} – {last.day} {last:%b %Y}"


def teacher_week(user, any_date, today, year_is_instructional):
    """The teacher's own week, Monday to Saturday, around `any_date` (ADR 0021 D10, amended).

    Each day is judged exactly as the Day view judges it: the teacher's subject assignments
    effective ON THAT DAY (ADR 0018) and `teacher_timetable_on`. `year_is_instructional(year,
    day)` answers `AcademicYear.is_instructional_day(day)`. Saturday is left out when it is not
    a school day. A day that is not a school day carries a header label ("Holiday" when a
    timetable runs that day but the school is closed, otherwise "No school"); blank cells are
    empty lists, never "free" periods. The number of queries depends on the six days only.
    """
    from core.authorization import current_teacher_assignments

    def rows_on(day):
        assignments = list(current_teacher_assignments(user, day))
        rows = teacher_timetable_on(
            assignments, day, lambda year: year_is_instructional(year, day)
        )
        for row in rows or ():
            row["short"] = short_section_label(row["section"])
        return rows

    def key_of(days):
        sections = {}
        for day in days:
            for row in day["rows"]:
                sections.setdefault(row["section"].pk, row)
        ordered = sorted(
            sections.values(),
            key=lambda r: (r["section"].class_grade.display_order, r["section"].name),
        )
        return [{"short": r["short"], "full": str(r["section"])} for r in ordered]

    return _assemble_week(any_date, today, rows_on, year_is_instructional, key_of)


def _assemble_week(any_date, today, rows_on, year_is_instructional, key_of):
    """Shared week assembly: day headers, Saturday rule, grid, key and heading.

    `rows_on(day)` returns that day's rows (each with a "short" label) or None when no timetable
    shows that day; `key_of(days)` builds the key from the assembled days.
    """
    monday = week_monday(any_date)
    days = []
    for offset in range(6):
        day = monday + timedelta(days=offset)
        rows = rows_on(day)
        if rows is None and offset == 5:
            continue
        is_open = rows is not None
        label = ""
        if not is_open:
            # Closed only when no Academic Year holding the day is open: a school day before the
            # timetable starts is an open day with blank cells, not "No school".
            holding = AcademicYear.objects.filter(start_date__lte=day, end_date__gte=day)
            is_open = any(year_is_instructional(year, day) for year in holding)
            if not is_open:
                label = "Holiday" if holding else "No school"
        days.append(
            {
                "date": day,
                "weekday": day.strftime("%a"),
                "is_today": day == today,
                "is_school_day": is_open,
                "label": label,
                "rows": rows or [],
            }
        )

    sequences = sorted({row["sequence"] for day in days for row in day["rows"]})
    grid = [
        {
            "sequence": sequence,
            "cells": [
                {"day": day, "rows": [r for r in day["rows"] if r["sequence"] == sequence]}
                for day in days
            ],
        }
        for sequence in sequences
    ]
    return {
        "monday": monday,
        "days": days,
        "grid": grid,
        "key": key_of(days),
        "is_empty": not sequences,
        "heading": _week_heading(monday, days[-1]["date"]),
        "contains_today": week_monday(today) == monday,
    }


def short_subject_label(name):
    """Short grid label for a subject: "Mathematics" -> "Mat". Always shown beside the full name."""
    return name.strip()[:3]


def class_timetable_on(section, on_date, year_is_instructional):
    """Every period of `section` on `on_date`, with subject and teacher (read-only class view).

    Only Academic Years holding this Section's slots that day count; None when none of them is an
    instructional day. Rows follow period sequence. The teacher is the holder of the offering +
    Section assignment effective that day (ADR 0018 D9), or None.
    """
    slots_today = TimetableSlot.objects.effective_on(on_date).filter(section=section)
    years = AcademicYear.objects.filter(
        pk__in=slots_today.values("period__academic_year_id")
    )
    open_year_ids = {year.pk for year in years if year_is_instructional(year)}
    if not open_year_ids:
        return None
    slots = list(
        slots_today.filter(
            weekday=on_date.weekday(), period__academic_year_id__in=open_year_ids
        )
        .select_related("period", "offering__subject")
        .order_by("period__sequence", "pk")
    )
    teachers = {}
    if slots:
        assignments = (
            AssessmentTeacherAssignment.objects.effective_on(on_date)
            .filter(section=section, offering_id__in={s.offering_id for s in slots})
            .select_related("teacher")
            .order_by("pk")
        )
        for assignment in assignments:
            teachers.setdefault(assignment.offering_id, assignment.teacher)
    rows = []
    for slot in slots:
        teacher = teachers.get(slot.offering_id)
        subject = slot.offering.subject.name
        rows.append(
            {
                "period": slot.period.label,
                "sequence": slot.period.sequence,
                "section": section,
                "subject": subject,
                "teacher": teacher,
                "teacher_name": _teacher_name(teacher) if teacher else "No teacher assigned",
                "short": short_subject_label(subject),
            }
        )
    return rows


def class_week(section, any_date, today, year_is_instructional):
    """One class's week, Monday to Saturday, built like `teacher_week` from `class_timetable_on`."""

    def rows_on(day):
        return class_timetable_on(
            section, day, lambda year: year_is_instructional(year, day)
        )

    def key_of(days):
        subjects = {
            row["subject"]: row["short"] for day in days for row in day["rows"]
        }
        return [{"short": subjects[name], "full": name} for name in sorted(subjects)]

    return _assemble_week(any_date, today, rows_on, year_is_instructional, key_of)


def week_monday(any_date):
    """Monday of the week shown for `any_date`; a Sunday shows the coming week."""
    if any_date.weekday() == 6:
        return any_date + timedelta(days=1)
    return any_date - timedelta(days=any_date.weekday())


def timetable_picker(user, dates):
    """The class sheet's two lists for the given dates (one date for Day, the week's days for Week).

    "mine": the user's class-teacher Sections first, then the Sections they teach a subject in,
    de-duplicated, each group in (grade display order, section name) order. "grades": every
    Section with a slot effective on any of `dates`, grouped by Class/Grade in display order.
    Queries per date are fixed; nothing is queried per Section.
    """
    from core.authorization import class_teacher_assignments, current_teacher_assignments
    from core.models import Section

    def ordered(sections):
        return sorted(sections, key=lambda s: (s.class_grade.display_order, s.class_grade_id, s.name))

    class_teacher, subject, listed_ids = {}, {}, set()
    for day in dates:
        for row in class_teacher_assignments(user, day).select_related("section__class_grade"):
            class_teacher[row.section_id] = row.section
        for row in current_teacher_assignments(user, day).select_related("section__class_grade"):
            subject[row.section_id] = row.section
        listed_ids.update(
            TimetableSlot.objects.effective_on(day).values_list("section_id", flat=True)
        )
    mine = ordered(class_teacher.values())
    mine += ordered(s for pk, s in subject.items() if pk not in class_teacher)

    grades = []
    for section in ordered(Section.objects.filter(pk__in=listed_ids).select_related("class_grade")):
        if not grades or grades[-1]["grade"].pk != section.class_grade_id:
            grades.append({"grade": section.class_grade, "sections": []})
        grades[-1]["sections"].append(section)
    return {"mine": mine, "grades": grades}
