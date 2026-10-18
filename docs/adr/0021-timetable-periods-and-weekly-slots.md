# 0021. Timetable periods and weekly slots

## Status

**Proposed** (2026-10-18, Teacher Dashboard gate TDB-3). Design only: nothing in this ADR is
implemented. It becomes Accepted when the open decisions below are answered and the ADR is
approved; implementation is gate TDB-4 (office setup) and TDB-5 (Teacher dashboard).

Extends ADR 0018 (it fills in "Not covered: timetable periods") and ADR 0011/0008. It changes no
frozen decision. It does bring a feature into scope that `docs/PRODUCT.md`,
`docs/REQUIREMENTS.md` and `docs/DOMAIN_MODEL.md` currently list as "timetable later" or out of
scope for Phases 1 to 7; see Open decision 1.

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

`TimetablePeriod` belongs to one Academic Year. A year's periods are an ordered list.

| Field | Rule |
|---|---|
| `academic_year` | FK, PROTECT |
| `sequence` | positive integer, the stable ordering (1, 2, 3 ...). Unique per year |
| `label` | short human text, default `P<sequence>` ("P1"). Unique per year |
| `start_time`, `end_time` | optional, both or neither, end after start. Not used for any rule or for ordering (see below) |

- **Ordering is by `sequence`**, never by clock time. The label can be renamed without moving the
  period; `sequence` is what a slot sorts by.
- **Optional times are stored but unused.** They exist only so a later release can show "P3,
  10:30" without a second migration. The Teacher dashboard stays period-first and, in TDB-5,
  displays no times. Overlapping times between periods of a year are rejected when both are set.
  See Open decision 2.
- **Breaks and lunch are not periods.** A period is a teaching period. A school with a lunch
  break between its fourth and fifth teaching periods simply has `sequence` 1-8 with no break row;
  if times are filled in, the gap is visible there. No "period type" field is added.
- A period with slots cannot be deleted (PROTECT). Its `label` and `sequence` may still be
  changed, subject to the uniqueness rules; gaps in the sequence are allowed.
- Periods are per Academic Year so a changed bell schedule in a later year never rewrites the
  earlier year. Setting up the next year's periods is manual in TDB-4; a copy action is deferred
  (Open decision 6).

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
`TimetableSlotQuerySet.effective_on(date)`).

- Changing a slot ends the current row on the day before the change and creates a new row in one
  transaction. Nothing is overwritten. A mid-year timetable revision for one Section changes only
  that Section's rows.
- A row is historically relevant once its `start_date` is on or before the school-local business
  date. It is then ended, never deleted. A row that has not yet taken effect may be deleted. This
  is ADR 0018 D5 applied to slots. See Open decision 3 (nothing depends on a slot, so a looser
  rule is possible).
- Simpler alternatives considered and rejected: a single mutable pattern per year loses "what was
  scheduled on 5 October" the first time it is edited; a timetable-version header model (one
  school-wide version active per date) makes whole-school term changes easy but forces a full copy
  for a one-Section change and adds a third model (Open decision 4).

### D5 The teacher is derived from the existing assignment, not stored

**A slot has no teacher column.** For a slot on date `d`, the teacher is the holder of the
`AssessmentTeacherAssignment` for the same `offering` + `section` effective on `d` (at most one,
ADR 0018 D2). No assignment effective on `d` means the slot has no teacher that day.

Reasons:

- ADR 0018 makes the dated assignment the single source of who may act for an offering + Section.
  A stored `teacher` on the slot would be a second source of truth that drifts at every
  hand-over (the new teacher inherits the offering but not the slot; the old teacher keeps a slot
  they no longer teach).
- It keeps history reconstructible from two dated sources: slot effective on `d` and assignment
  effective on `d` answer "who was scheduled for P2 on 5 October".
- Hand-overs, ended assignments and loss of teacher status (ADR 0018 D9) flow through with no
  extra code, because `current_teacher_assignments` already handles them.

Cost, accepted: "teacher scheduled in two Sections in the same period" cannot be a database
constraint, because the teacher is derived and assignments change. It is checked in the
application (D6 R6) and by a report. The brief listed Teacher as part of the minimum slot data;
this ADR satisfies that by derivation. The alternative of a stored teacher validated against the
assignment is Open decision 5.

### D6 Integrity rules

Enforced in `clean()` and in the model's create/end methods under a lock on the Section (as ADR
0011 locks), except where marked database.

| # | Rule | Enforced |
|---|---|---|
| R1 | The slot's offering belongs to the same Academic Year as its period | application |
| R2 | The offering applies to the Section (`AcademicSubjectOffering.objects.for_section(year, section)`): same Class/Grade, and either no Section limit or this Section listed. "Subject actually offered to that Section/year" | application |
| R3 | Both dates fall inside the Academic Year; end not before start | application + database (end check) |
| R4 | A Section has at most one teaching slot per period and weekday on any date: ranges for the same `(period, weekday, section)` may not overlap | application (known boundary as in ADR 0011/0018; the unique start-date constraint is the database backstop) |
| R5 | Saturday (weekday 5) slots need an Academic Year with `saturdays_instructional` | application |
| R6 | A teacher cannot be scheduled into two Sections in the same period and weekday: no other slot with the same `(period, weekday)` and an overlapping date range may have the same assignee, derived through D5, for any assignment range that overlaps | application at save, plus a conflicts report because a later reassignment can create a clash without touching the slots |
| R7 | The offering's Section scope cannot drop a Section that has any slot, current or historical (extends ADR 0018 D10) | application (`set_sections`) |
| R8 | A slot with no effective assignment is allowed (planning ahead) but is listed as "no teacher" in the office screen and appears on no teacher's dashboard | report |

R6 is the only rule that needs the assignment table; it blocks a save that is already in conflict
and the report catches drift afterwards. Block-versus-warn is Open decision 7.

### D7 Relationship to ADR 0018 and authorization

**A timetable grants nothing.** No authorization helper consults `TimetablePeriod` or
`TimetableSlot`. Marks entry, the working gradebook, My students, attendance and results scope are
decided exactly as today by `current_teacher_assignments` / `class_teacher_assignments`. The
slot-to-teacher link is read-only derivation for display. Removing the whole timetable would
change no permission. Tests in TDB-4 must assert this (a teacher with a slot but no assignment
gets no access and no dashboard row; a teacher with an assignment but no slot keeps full access).

### D8 Exceptions and out-of-scope features

| Feature | Decision |
|---|---|
| Temporary substitutions / cover teachers | **Deferred.** Needs its own ADR: a dated override per slot occurrence, with no authorization effect (same rule as D7). ADR 0018 already lists it as not covered |
| Special timetable days (for example a working Saturday following Monday's pattern) | **Deferred.** On such a day the dashboard shows only slots whose own weekday matches; it never guesses a substitute pattern |
| Exam schedules | **Deferred.** Assessments have their own dates (ADR 0009); an exam timetable is not the teaching timetable |
| Holidays / non-instructional days | **In scope by reuse, no new data.** Slots are never consulted on a day where `AcademicYear.is_instructional_day(date)` is false; no exception rows are added to the timetable |
| Rooms | **Deferred.** No room model or field |
| Double periods | **In scope by use:** two consecutive periods are two slots |
| Several subjects in one period for one Section (electives, split groups, labs) | **Out of scope** by R4. Recorded as a known limitation (Open decision 8) |
| Teacher attendance / period-level student attendance | **Out of scope** (ADR 0007, 0012 unchanged) |
| Student or guardian timetable views | **Out of scope** |
| Year copy of periods and slots | **Deferred** (Open decision 6) |

### D9 Permissions and workflow

Periods and slots are configured by authorised office users, not teachers. TDB-4 adds the four
standard model permissions for each of `TimetablePeriod` and `TimetableSlot` (view, add, change,
delete) and grants them to the "School Administrators" group in a data migration, following
migrations 0002, 0005 and 0007. Teachers get no timetable permission (ADR 0011 D11); they only
see their own rows on the dashboard, derived through their own assignments. No staff or HR record
is introduced (ADR 0011 D12).

### D10 How the Teacher dashboard obtains today's timetable (for TDB-5)

1. `today = business_today()`; `weekday = today.weekday()`.
2. Take the teacher's current assignments, `current_teacher_assignments(user, today)`, which
   `my_home` already loads, as the set of `(offering_id, section_id)` pairs. A teacher with none
   gets no rows.
3. Query `TimetableSlot.objects.effective_on(today).filter(weekday=weekday)` limited to those pairs,
   `select_related("period", "section__class_grade", "offering__subject")`, ordered by
   `period__sequence`. Constant query count; no per-row queries.
4. Drop rows whose Academic Year is not an instructional day today
   (`year.is_instructional_day(today)`, cached per year as `my_home` already does).
5. Render `P1  Grade 6 - A · Mathematics` using the period label, `str(section)` and the subject
   name. Rows are plain text (no Section + Subject destination exists, TDB-2). No times in TDB-5.
6. **No fake rows.** No "free period" rows, no inferred gaps, no placeholders. Only stored slots
   for the signed-in teacher appear.
7. Visibility of the section: shown when the teacher has at least one row today. If the teacher has
   none, show one plain line, "No periods scheduled for you today.", only when the school has a
   timetable in effect today (at least one slot effective on `today`); when no timetable is
   configured at all, the section is hidden entirely. This keeps the dashboard truthful in a school
   that has not set the timetable up (Open decision 9 for the wording and rule).
8. Placement stays "immediately after Today overview" (TDB-0).

## Proposed models (summary, not implemented)

```
TimetablePeriod(academic_year FK PROTECT, sequence uint, label char(20),
                start_time null, end_time null, timestamps)
  unique (academic_year, sequence); unique (academic_year, label)
  check (start_time null and end_time null) or (both set and end_time > start_time)

TimetableSlot(period FK PROTECT, weekday smallint, section FK PROTECT,
              offering FK PROTECT, start_date, end_date null, timestamps)
  unique (period, weekday, section, start_date)
  check weekday between 0 and 5
  check end_date null or end_date >= start_date
  QuerySet.effective_on(date)  # null end_date runs to period.academic_year.end_date
```

## Proposed gate TDB-4: timetable office setup

Includes a migration and the office workflow. Nothing teacher-facing changes in TDB-4.

- Models, queryset, migration; data migration granting the eight permissions to "School
  Administrators".
- Model methods: create slot / end slot / change slot (end + create) under a Section lock, with
  R1-R7 and the deletion rule of D4. `set_sections` extended for R7.
- Office screens (administrator-only, model permissions, office navigation entry "Timetable"):
  - per Academic Year: Periods list with add, edit, delete (blocked while slots exist);
  - per Academic Year and Section: weekly grid of periods by Monday-Saturday, with add slot,
    change (end + new), end, and delete (future rows only);
  - a report of slots with no current teacher and of teacher clashes (R6). It does not report
    Sections that have an offering but no slot, because that would imply a required-hours rule
    that does not exist.
- Tests: every integrity rule R1-R7 (valid and invalid), effective-dating (`effective_on`,
  null end), end-never-delete, deletion of future rows, permissions (office user allowed, teacher
  and anonymous refused), the D7 independence assertions, ADR 0018 hand-over leaves slots intact
  and moves the derived teacher, query count of the grid.
- Docs: flip this ADR to Accepted, update `DOMAIN_MODEL.md`, `REQUIREMENTS.md`, `PRODUCT.md`
  scope lines, and the ADR 0018 "Not covered" note by reference.

TDB-5 (dashboard integration) follows D10 and adds no model.

## Open decisions (need review; not guessed here)

1. **Product scope.** Existing product docs list timetable as later / out of scope. Confirm it is
   now in scope for this release.
2. **Optional period times now or later.** Recommended: store nullable times now (cheap, avoids a
   later migration) and use them nowhere. Alternative: leave them out until a screen needs them.
3. **Deleting started slots.** Recommended: follow ADR 0018 D5 (end, never delete, once
   started). Nothing depends on a slot, so a looser rule (delete allowed) is possible but rewrites
   what the dashboard showed.
4. **Dating model.** Recommended: effective-date each slot. Alternative: one school-wide
   timetable-version header per date range (easier whole-school term changes, harder per-Section
   changes, one more model).
5. **Derived versus stored teacher.** Recommended: derived (D5). Alternative: store `teacher` on
   the slot, validated against the effective assignment at save, with a drift report; this
   duplicates ADR 0018's source of truth.
6. **Year copy.** Whether TDB-4 includes a preview-first "copy periods and slots from the previous
   year" (as ADR 0011 D13 for assignments) or it is later work. Recommended: later.
7. **R6 teacher clash: block or warn.** Recommended: block the save when it is already a
   conflict, and report later drift.
8. **Electives and split groups.** R4 forbids two slots for one Section in one period. If the
   school runs electives in the same period, the model needs a group concept; recommended: not
   now.
9. **Dashboard empty line.** Wording and rule in D10 step 7 ("No periods scheduled for you today."
   only when a timetable is in effect, otherwise hide) need confirmation.
10. **Weekday set.** Monday-Saturday is proposed. If Sunday or a configurable week is needed,
    say so before TDB-4.

## Consequences

- One new concept (period + slot) with two small tables; no duplication of Class/Subject/teacher
  data. The existing assignment screens remain the only place a teacher is attached to an
  offering + Section.
- A timetable can be wrong without being unsafe: an inconsistent timetable never changes who may
  enter marks or take attendance.
- Teacher clash checking is application-level and can be bypassed by raw SQL or bulk updates, the
  same boundary ADR 0011 and 0018 accept. The conflicts report is the safety net.
- Teachers whose Section is taught by a substitute see nothing until substitutions get their own
  ADR.

## Related

ADR 0008 (calendar), ADR 0009 (offerings), ADR 0010, ADR 0011 (D3, D11, D12), ADR 0018 (D1, D2,
D5, D9, D10), `docs/superpowers/specs/2026-10-18-ui-tdb-0-teacher-dashboard-design.md`.
