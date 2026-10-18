# 0021. Timetable periods and weekly slots

## Status

Accepted (2026-10-18, Teacher Dashboard gate TDB-3) — FROZEN. Design only: nothing in this ADR is
implemented yet. Implementation is gate TDB-4 (office setup) and TDB-5 (Teacher dashboard).

Extends ADR 0018 (it covers the "timetable periods" item that ADR 0018 lists as not covered) and
builds on ADR 0008 and ADR 0011. It changes no frozen decision; the historical statements in
other documents that timetable was out of scope for Phases 1 to 7 stay true for those phases. The
product documents record that a narrow timetable capability is now in scope (see D11).

## Context

The Teacher dashboard (`docs/superpowers/specs/2026-10-18-ui-tdb-0-teacher-dashboard-design.md`)
wants a "Today's timetable" block, period-first, not clock-time-first:

```
P1  Grade 6-A · Mathematics
P2  Grade 7-B · Mathematics
P3  Grade 8-A · Science
```

What the repo has today (inspected at `c2ad38c`):

- `AcademicYear` with a weekly pattern (`saturdays_instructional`) and `SchoolCalendarDay`
  exceptions; `AcademicYear.is_instructional_day(date)` is the single answer to "is a school day"
  (ADR 0008).
- `Section` (a Class/Grade + name) and `AcademicSubjectOffering` (Academic Year + Class/Grade +
  Subject, optionally limited to Sections; `for_section(year, section)` says which offerings apply
  to a Section).
- `AssessmentTeacherAssignment` (ADR 0010, 0018): effective-dated, one teacher per offering +
  Section at a time, application-enforced non-overlap, end-never-delete once started.
  `SectionClassTeacher` (ADR 0011) follows the same pattern.
- Authorization is assignment-based and centralised in `core.authorization`; teachers hold no
  model permissions (ADR 0011 D11); office screens use model permissions held by the
  "School Administrators" group.
- No Period, Slot or Timetable model exists. ADR 0018 states assignments are "not a timetable,
  workload, substitution or HR record".

## Decision

### D1 Scope: teaching periods and weekly slots only

Two new models, `TimetablePeriod` and `TimetableSlot`. A slot says *which Subject offering is
taught to which Section in which Period on which weekday, for a dated range*. It does not say who
teaches it (D5).

### D2 Period definition

`TimetablePeriod` belongs to one Academic Year. A year's periods are an ordered list. It has only:

| Field | Rule |
|---|---|
| `academic_year` | FK, PROTECT |
| `sequence` | positive integer, the stable ordering (1, 2, 3 ...). Unique per year |
| `label` | short human text, default `P<sequence>` ("P1"). Unique per year |

(plus the usual created/updated timestamps)

- **Ordering is by `sequence`**, never by clock time. The label can be renamed without moving the
  period.
- **No clock times.** The period carries no start or end time. The Teacher dashboard is
  period-first and no feature needs bell times. If a school later needs them, adding them is a
  small migration then.
- **Breaks and lunch are not periods.** A period is a teaching period. A school with a lunch
  break between its fourth and fifth teaching periods simply has `sequence` 1-8 with no break row.
  No "period type" field is added.
- A period with slots cannot be deleted (PROTECT). Its `label` and `sequence` may still be
  changed, subject to the uniqueness rules; gaps in the sequence are allowed.
- Periods are per Academic Year so a changed period structure in a later year never rewrites the
  earlier year. Setting up the next year's periods is manual in TDB-4 (D8: year copy deferred).

### D3 Weekly slot

`TimetableSlot` is one scheduled teaching slot.

| Field | Rule |
|---|---|
| `period` | FK `TimetablePeriod`, PROTECT. The Academic Year comes from here |
| `weekday` | 0-5 (Monday-Saturday, Python `weekday()`) |
| `section` | FK `Section`, PROTECT |
| `offering` | FK `AcademicSubjectOffering`, PROTECT (reused; no new Class/Subject relationship) |
| `start_date` | first effective date, inclusive |
| `end_date` | optional last effective date, inclusive. Null means the end of the Academic Year; it never carries into the next year |
| timestamps | `created_at`, `updated_at` |

Database constraints (portable to SQLite and PostgreSQL): end not before start; weekday between 0
and 5; unique `(period, weekday, section, start_date)`.

### D4 One weekly pattern, effective-dated per slot

The schedule is a weekly pattern per Academic Year, and each slot row is **effective-dated**, using
the same convention as ADR 0011 and ADR 0018 (`start_date` / optional `end_date`, inclusive;
`TimetableSlotQuerySet.effective_on(date)`). There is no timetable-version header model.

- Changing a slot ends the current row on the day before the change and creates a new row in one
  transaction. Nothing is overwritten. A mid-year revision for one Section changes only that
  Section's rows.
- **A slot that has taken effect is ended, never deleted.** A row is historically relevant once
  its `start_date` is on or before the school-local business date (ADR 0018 D5). A row that has
  not yet taken effect may be deleted.
- Rejected: a single mutable pattern per year (it loses "what was scheduled on 5 October" at the
  first edit) and a school-wide timetable-version header (it forces a full copy for a one-Section
  change and adds a model).

### D5 The teacher is derived from the existing assignment, never stored

**A slot has no teacher column, now or later.** For a slot on date `d`, the teacher is the holder
of the `AssessmentTeacherAssignment` for the same `offering` + `section` effective on `d` (at most
one, ADR 0018 D2). No assignment effective on `d` means the slot has no teacher that day.

- ADR 0018 makes the dated assignment the single source of who may act for an offering + Section.
  A stored `teacher` on the slot would be a second source of truth that drifts at every
  hand-over.
- History stays reconstructible from two dated sources: the slot effective on `d` and the
  assignment effective on `d`.
- Hand-overs, ended assignments and loss of teacher status (ADR 0018 D9) flow through with no
  extra code, because `current_teacher_assignments` already handles them.

Cost, accepted: "a teacher in two Sections in the same period" cannot be a database constraint,
because the teacher is derived and assignments change. D6 R6 covers it.

### D6 Integrity rules

Enforced in the timetable model methods under a lock on the Section (as ADR 0011 locks), except
where marked database.

| # | Rule | Enforced |
|---|---|---|
| R1 | The slot's offering belongs to the same Academic Year as its period | application |
| R2 | The offering applies to the Section (`AcademicSubjectOffering.objects.for_section(year, section)`): same Class/Grade, and either no Section limit or this Section listed | application |
| R3 | Both dates fall inside the Academic Year; end not before start | application + database (end check) |
| R4 | A Section has at most one teaching slot per period and weekday on any date: date ranges for the same `(period, weekday, section)` may not overlap | application (the same known boundary as ADR 0011/0018; the unique start-date constraint is the database backstop) |
| R5 | Saturday (weekday 5) slots need an Academic Year with `saturdays_instructional` | application |
| R6 | A teacher cannot be scheduled into two Sections in the same period and weekday on the same date | application at save, plus a conflicts report |
| R7 | The offering's Section scope cannot drop a Section that has any slot, current or historical (extends ADR 0018 D10) | application (`set_sections`) |
| R8 | A slot with no effective assignment is allowed (planning ahead) but is listed as "no teacher" in the office screen and appears on no teacher's dashboard | report |

**R6 invariant.** For any date `d`, period `p` and weekday `w`, no teacher is the derived teacher
(D5) of two different slots effective on `d` for `(p, w)`. A save that would, given the
assignments known at save time (current and already-planned future rows), is **blocked**. The
conflicts report lists clashes that arise later, for example when an assignment change gives one
teacher two Sections in the same period. This is a drift report, not a second enforcement path.

**One place for the calculation.** The clash calculation lives in a single timetable query/service
helper (for example `core/timetable.py`) used by both the save-time check and the report. It is
not re-implemented in `clean()` methods, forms or views. TDB-4 defines and tests that helper;
this ADR fixes only the invariant.

### D7 Relationship to ADR 0018 and authorization

**A timetable grants nothing.** No authorization helper consults `TimetablePeriod` or
`TimetableSlot`. Marks entry, the working gradebook, My students, attendance and results scope are
decided exactly as today by `current_teacher_assignments` / `class_teacher_assignments`. The
slot-to-teacher link is read-only derivation for display. Removing the whole timetable would
change no permission. TDB-4 tests must assert this: a teacher with a slot but no assignment gets
no access and no dashboard row; a teacher with an assignment but no slot keeps full access.

### D8 Exceptions and out-of-scope features

| Feature | Decision |
|---|---|
| Temporary substitutions / cover teachers | **Deferred.** Needs its own ADR: a dated override per slot occurrence, with no authorization effect (same rule as D7). ADR 0018 already lists it as not covered |
| Special timetable days (for example a working Saturday or Sunday following another day's pattern) | **Deferred.** On such a day the dashboard shows only slots whose own weekday matches; it never guesses a substitute pattern. No recurring Sunday scheduling is added for exceptional Sundays |
| Exam schedules | **Deferred.** Assessments have their own dates (ADR 0009); an exam timetable is not the teaching timetable |
| Holidays / non-instructional days | **In scope by reuse, no new data.** Slots are never consulted on a day where `AcademicYear.is_instructional_day(date)` is false |
| Rooms | **Deferred.** No room model or field |
| Double periods | **In scope by use:** two consecutive periods are two slots |
| Electives, split groups, several subjects in one period for one Section | **Deferred.** R4 allows one teaching slot per Section per period and weekday; no group or elective concept is invented now |
| Year copy of periods and slots | **Deferred** until real use shows what a copy should do |
| Period-level student attendance, teacher attendance | **Out of scope** (ADR 0007, 0012 unchanged) |
| Student or guardian timetable views | **Out of scope** |

### D9 Permissions and workflow

Periods and slots are configured by authorised office users, not teachers. Django creates the
standard `view`, `add`, `change` and `delete` permissions for each of the two models when they are
added (eight generated permissions, no custom permissions). TDB-4 adds a data migration that grants
those eight generated permissions to the "School Administrators" group, following migrations
0002, 0005 and 0007. Teachers get no timetable permission (ADR 0011 D11); they only see their own
rows on the dashboard, derived through their own assignments. No staff or HR record is introduced
(ADR 0011 D12).

### D10 How the Teacher dashboard obtains today's timetable (for TDB-5)

1. `today = business_today()`; `weekday = today.weekday()`.
2. Take the teacher's current assignments, `current_teacher_assignments(user, today)`, which
   `my_home` already loads, as the set of `(offering_id, section_id)` pairs. A teacher with none
   gets no rows.
3. Query `TimetableSlot.objects.effective_on(today).filter(weekday=weekday)` limited to those pairs,
   `select_related("period", "section__class_grade", "offering__subject")`, ordered by
   `period__sequence`. Constant query count; no per-row queries.
4. Rows whose Academic Year is not an instructional day today
   (`year.is_instructional_day(today)`, cached per year as `my_home` already does) are dropped.
5. Render `P1  Grade 6 - A · Mathematics` using the period label, `str(section)` and the subject
   name. Rows are plain text (no Section + Subject destination exists, TDB-2). No times.
6. **No fake rows.** No "free period" rows, no inferred gaps, no placeholders. Only stored slots
   for the signed-in teacher appear.
7. **Visibility of the section:**
   - instructional day, a timetable exists, and the teacher has at least one row: show the rows;
   - instructional day, a timetable exists, and the teacher has no row: show the single line
     "No periods scheduled for you today.";
   - no timetable configured: hide the section;
   - non-instructional day: hide the section (the header already says "Not a school day").
   "A timetable exists" means at least one slot is effective on `today` for an Academic Year that
   is an instructional day today.
8. Placement stays "immediately after Today overview" (TDB-0).

### D11 Product scope

This ADR brings a **narrow** timetable capability into scope: office configuration of periods and
weekly slots, and the signed-in teacher's own periods on the Teacher "Today" dashboard. Student and
guardian timetables, substitutions, special timetable days, exams, rooms, electives and year copy
remain out of scope or deferred as listed in D8. `docs/PRODUCT.md`, `docs/REQUIREMENTS.md` and
`docs/DOMAIN_MODEL.md` record this while keeping their earlier statements for the phases they
describe.

## Models (summary, not yet implemented)

```
TimetablePeriod(academic_year FK PROTECT, sequence uint, label char(20), timestamps)
  unique (academic_year, sequence); unique (academic_year, label)

TimetableSlot(period FK PROTECT, weekday smallint, section FK PROTECT,
              offering FK PROTECT, start_date, end_date null, timestamps)
  unique (period, weekday, section, start_date)
  check weekday between 0 and 5
  check end_date null or end_date >= start_date
  QuerySet.effective_on(date)  # null end_date runs to period.academic_year.end_date
```

## Gate TDB-4: timetable office setup

Includes a migration and the office workflow. Nothing teacher-facing changes in TDB-4.

- Models, queryset, migration; a data migration granting the eight Django-generated permissions
  (view, add, change, delete for both models) to "School Administrators".
- Model methods: create slot / end slot / change slot (end + create) under a Section lock,
  enforcing R1-R7 and the deletion rule of D4 (future rows deletable, started rows ended).
  `set_sections` extended for R7.
- **One timetable helper** (D6) that computes teacher clashes, used by save-time blocking and by
  the report.
- Office screens (administrator-only, model permissions, office navigation entry "Timetable"):
  - per Academic Year: Periods list with add, edit and delete (delete blocked while slots exist);
  - per Academic Year and Section: weekly grid of periods by Monday-Saturday, with add slot,
    change (end + new), end, and delete (future rows only);
  - a report of slots with no current teacher and of teacher clashes. It does not report Sections
    that have an offering but no slot, because that would imply a required-hours rule that does
    not exist.
- Tests: every integrity rule R1-R7 (valid and invalid), `effective_on` including null end,
  end-never-delete, deletion of future rows only, the clash helper (save-time block and drift
  report), permissions (office user allowed; teacher and anonymous refused), the D7 independence
  assertions, an ADR 0018 hand-over leaving slots intact and moving the derived teacher, and the
  query count of the grid.
- Docs: update `DOMAIN_MODEL.md` with the model summary when it ships.

TDB-5 (dashboard integration) follows D10 and adds no model.

## Resolved decisions (2026-10-18 review)

1. A narrow timetable capability is in scope (D11).
2. No period times (D2).
3. Started slots are ended, never deleted; future slots may be deleted (D4).
4. Per-slot effective dating; no version header (D4).
5. Teacher is derived, never stored (D5).
6. Year copy is deferred (D8).
7. Known teacher clashes are blocked at save; the report covers later drift (D6).
8. Electives and split groups are deferred (D8).
9. Dashboard empty and hidden behaviour as in D10 step 7.
10. Recurring weekdays are Monday-Saturday (D3).

## Consequences

- One new concept (period + slot) with two small tables; no duplication of Class/Subject/teacher
  data. The existing assignment screens remain the only place a teacher is attached to an
  offering + Section.
- A timetable can be wrong without being unsafe: an inconsistent timetable never changes who may
  enter marks or take attendance.
- Overlap checks are application-level and can be bypassed by raw SQL or bulk updates, the same
  boundary ADR 0011 and 0018 accept. The conflicts report is the safety net for teacher clashes.
- A Section taught by a substitute shows its regular teacher's slot until substitutions get their
  own ADR.

## Related

ADR 0008 (calendar), ADR 0009 (offerings), ADR 0010, ADR 0011 (D3, D11, D12), ADR 0018 (D1, D2,
D5, D9, D10), `docs/superpowers/specs/2026-10-18-ui-tdb-0-teacher-dashboard-design.md`.
