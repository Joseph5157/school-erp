# Phase 2 Attendance — Gate-by-Gate Reconciliation Implementation Plan

## Status

Approved planning document for reconciling the current Phase 2 implementation on `main`.

Planning baseline:
- Phase 1 complete tag/commit: `phase-1-complete` / `6cad8fb`
- current Phase 2 implementation commit at plan creation: `6c2b50595a262e41aa8af9f911380b0908c5b6df`
- current implementation is not considered Phase 2 complete
- do not create a `phase-2-complete` tag until every gate in this plan passes

## Why reconciliation is required

The current implementation contains useful attendance work, but it diverges from the attendance decisions approved after bounded research.

Important current divergences include:
- AcademicEnrollment has no effective start/end dates.
- Attendance roster eligibility uses currently ACTIVE enrollment instead of enrollment effective on the attendance date.
- No minimal school calendar exists.
- Attendance statuses currently include PRESENT, ABSENT, LATE, EXCUSED instead of the approved Phase 2 minimum PRESENT/ABSENT.
- AttendanceRegister has no DRAFT/SUBMITTED lifecycle or submission actor/time.
- Missing attendance is therefore not represented with the approved semantics.
- The currently accepted ADR 0005 documents several of those older decisions and must be superseded explicitly before code reconciliation.

This plan deliberately preserves useful existing code where it fits. It is not a request to rewrite Phase 2 from scratch.

## Source-of-truth rule

For implementation work, follow this order:
1. Accepted ADRs
2. Approved REQUIREMENTS.md and DOMAIN_MODEL.md
3. ARCHITECTURE.md
4. This plan
5. Existing implementation

Because current ADR 0005 conflicts with the approved target, Gate 0 must update the source of truth first.

## Working method for every gate

For each gate:
1. Read the relevant requirements, ADRs, models, migrations, forms, views, templates, and tests before changing code.
2. Implement only the gate's scope.
3. Add/update focused tests for the gate.
4. Run targeted tests first.
5. Run the full Django test suite.
6. Run `python manage.py check`.
7. Run Ruff.
8. Review migrations and changed files.
9. Commit the gate separately.
10. Stop and report results before beginning the next gate.

Do not combine gates unless this plan explicitly says they may be combined.

---

# Gate 0 — Reconcile and freeze the source of truth

## Goal

Make repository documentation match the approved Phase 2 attendance decisions before changing implementation behavior.

## Required documentation changes

Do not silently rewrite accepted ADR 0005. Preserve it as historical evidence and supersede it.

Create:

### ADR 0006 — Academic Enrollment effective dating

Freeze:
- AcademicEnrollment has an effective `start_date`.
- ACTIVE enrollment has no effective `end_date`.
- COMPLETED enrollment has an effective `end_date`.
- audit timestamps are not effective dates.
- effective enrollment periods for the same Student must not overlap.
- transfers preserve former enrollment and create the later placement.
- date-sensitive operational records use the enrollment effective on the business date.

### ADR 0007 — Phase 2 attendance model

State that it **supersedes ADR 0005 for Phase 2 attendance decisions**.

Freeze:
- daily attendance only
- Section/date register
- roster from date-effective AcademicEnrollment
- AttendanceEntry references the applicable AcademicEnrollment
- statuses only PRESENT and ABSENT
- ABSENT may have an optional note
- minimal Academic-Year-aware school calendar
- working Saturdays / exceptional instructional dates supported
- register lifecycle DRAFT → SUBMITTED
- complete roster required before submission
- missing/unsubmitted attendance is not ABSENT
- no future attendance
- audited admin corrections
- Phase 2 mutations remain administrator-only
- teacher attendance remains Phase 5
- percentage = PRESENT / (PRESENT + ABSENT) over submitted eligible attendance only

Update:
- `docs/REQUIREMENTS.md`
- `docs/DOMAIN_MODEL.md`
- `docs/ROADMAP.md`

Mark Phase 2 as **in reconciliation/implementation**, not complete.

## Gate 0 acceptance

- ADR 0006 exists and is Accepted.
- ADR 0007 exists and is Accepted and explicitly supersedes ADR 0005.
- Requirements/domain/roadmap agree with ADR 0006/0007.
- No code or migration changes in this gate.

## Recommended commit

`docs: reconcile phase 2 attendance decisions`

STOP after Gate 0 and review.

---

# Gate 1 — Effective-date AcademicEnrollment foundation

## Goal

Make historical placement reliably queryable by business date before attendance depends on it.

## Model target

Add to `AcademicEnrollment`:
- `start_date` — required after safe migration/backfill
- `end_date` — nullable

Semantics:
- ACTIVE → `end_date IS NULL`
- COMPLETED → `end_date IS NOT NULL`
- `end_date >= start_date`
- effective periods for one Student must not overlap
- existing one-ACTIVE-enrollment rule remains
- Section must still belong to Class/Grade

## Migration safety

Before choosing a migration:
- inspect whether repository/dev database data must be preserved
- do not use `created_at` or `updated_at` as guessed effective dates
- do not invent arbitrary dates for existing meaningful data

If existing rows require backfill and the correct business dates are unknown:
- use a staged nullable migration or explicit data-entry/backfill step
- make the field required only after data can satisfy the invariant

For tests/fixtures:
- create explicit effective dates going forward

## Domain behavior

Refactor enrollment/transfer workflow so callers provide an effective start date.

When moving a Student:
- reject an effective date that produces overlap or invalid chronology
- close the previous ACTIVE enrollment with the day before the new placement begins, if the product rule is date-exclusive for the new start
- create the new ACTIVE enrollment from the new effective date
- preserve prior placement

Do not infer transfer dates from `timezone.now()` or audit timestamps.

Provide one clear date lookup/query path for:
> Which AcademicEnrollment was effective for this Student on date D?

## Tests

At minimum:
- valid ACTIVE dated enrollment
- ACTIVE with end_date rejected
- COMPLETED without end_date rejected
- end before start rejected
- exact boundary behavior
- overlapping periods rejected
- non-overlapping historical + active allowed
- transfer preserves old enrollment and dates
- historical lookup returns old Section before transfer
- historical lookup returns new Section on/after transfer
- authorization for enrollment mutation remains correct
- existing Phase 1 enrollment tests updated without weakening earlier guarantees

## Gate 1 acceptance

- all effective-date invariants are enforced at the strongest reasonable layer
- historical lookup by date works
- all tests/checks/Ruff pass
- no Attendance behavior is changed yet except test fixture compatibility

## Recommended commit

`feat: add effective-dated academic enrollment`

STOP after Gate 1 and review.

---

# Gate 2 — Minimal school calendar

## Goal

Define whether attendance is expected on a particular Academic Year date.

## Model target

Introduce a minimal model such as `SchoolCalendarDay` with:
- `academic_year`
- `date`
- instructional/non-instructional state
- optional short label/reason

Required rules:
- unique `(academic_year, date)`
- date must fall within AcademicYear bounds
- supports ordinary instructional days
- supports holidays/closures
- supports working Saturdays or other exceptional instructional dates

Do not build:
- timetable
- period schedule
- event management
- recurring calendar engine
- teacher schedule

## UI/admin workflow

Provide a simple administrator workflow to create/view/change calendar dates.

Keep it operationally simple.

## Tests

- instructional date
- non-instructional/holiday date
- working Saturday
- duplicate AcademicYear/date rejected
- outside-Academic-Year date rejected
- unauthorized mutation rejected
- protected historical references are not casually hard-deleted

## Gate 2 acceptance

Calendar can answer reliably:
> Is attendance expected on date D for Academic Year Y?

Full suite/check/Ruff pass.

## Recommended commit

`feat: add school calendar foundation`

STOP after Gate 2 and review.

---

# Gate 3 — Reconcile attendance core schema

## Goal

Bring the existing attendance persistence model into alignment with ADR 0007 without yet completing all UI/reporting behavior.

## Attendance statuses

Change Phase 2 choices to exactly:
- PRESENT
- ABSENT

Remove LATE and EXCUSED from normal Phase 2 behavior.

Because the current implementation may contain migration/data implications:
- inspect existing data before migration
- do not silently coerce meaningful LATE/EXCUSED records
- if test/dev-only and disposable, document that fact
- otherwise provide an explicit reconciliation strategy

Add optional absence note on AttendanceEntry if not already present.

## AttendanceRegister

Keep useful existing Section/date register work, but add:
- status: DRAFT / SUBMITTED
- submitted_by nullable until submission
- submitted_at nullable until submission

Remove redundant persisted context only if safe and clearly justified. If `academic_year` / `class_grade` remain on the register, validate they cannot contradict Section/date/calendar/enrollment context.

Required uniqueness:
- at most one register per Section/date

## AttendanceEntry

Keep:
- register
- academic_enrollment
- current accepted status

Required:
- unique register/enrollment
- enrollment must be effective on register date
- enrollment Section must match register Section
- appropriate Academic Year must match date/register context

## Correction history

Preserve the useful existing correction audit design:
- previous status
- new status
- actor
- timestamp

A reason may remain required if already implemented and tested; this is acceptable as a stricter operational rule unless it creates a demonstrated problem.

## Tests

- choices exactly PRESENT/ABSENT
- invalid status rejected
- unique Section/date
- unique register/enrollment
- wrong Section enrollment rejected
- enrollment not effective on register date rejected
- correct historical enrollment accepted
- correction audit still works
- delete protection remains appropriate

## Gate 3 acceptance

Schema and domain constraints align with ADR 0007.

Do not yet claim missing-attendance semantics complete until Gate 4 submission lifecycle is implemented.

## Recommended commit

`refactor: align attendance core with phase 2 decisions`

STOP after Gate 3 and review.

---

# Gate 4 — DRAFT/SUBMITTED register workflow and date-valid roster

## Goal

Implement the actual operational meaning of taking attendance.

## Roster

Replace ACTIVE-only roster logic.

For register date D, roster must come from AcademicEnrollments whose effective range contains D and whose Section matches the register Section.

A later transfer must never remove the Student from an earlier historical roster.

## Register lifecycle

DRAFT:
- may be incomplete
- may be edited by authorized administrator
- represents attendance started but not finalized

SUBMITTED:
- complete effective roster required
- every eligible enrollment has exactly one PRESENT/ABSENT entry
- records `submitted_by`
- records `submitted_at`

Submission must be rejected when:
- register date is in the future
- calendar date is non-instructional
- roster is incomplete
- an entry references an ineligible enrollment

Define clearly what happens when the effective roster is empty; test the selected behavior.

## Missing attendance semantics

- no register = attendance NOT TAKEN
- DRAFT = attendance started/incomplete
- SUBMITTED = attendance officially taken
- no missing entry may be interpreted as ABSENT

## Tests

- historical roster before transfer
- new roster after transfer
- no register semantics
- DRAFT incomplete accepted
- incomplete SUBMITTED rejected
- complete SUBMITTED accepted
- submission actor/time captured
- future date rejected
- non-instructional date rejected
- working Saturday accepted when instructional
- unauthorized submit rejected

## Gate 4 acceptance

The system can reliably distinguish not taken, draft, present, absent, and submitted attendance.

## Recommended commit

`feat: add attendance register submission workflow`

STOP after Gate 4 and review.

---

# Gate 5 — Reconcile administrative capture UI

## Goal

Adapt the existing attendance UI to the corrected domain rules.

## Workflow

Administrator:
1. selects/opens Section + date
2. system validates calendar date
3. system displays date-effective roster
4. marks each Student PRESENT or ABSENT
5. optionally adds absence note
6. saves DRAFT or submits
7. sees clear register status

A bulk "mark all present" convenience is allowed if:
- it is only UI convenience
- submission still persists explicit status for every roster member
- it never means a missing register is treated as present

## UI rules

- remove LATE/EXCUSED controls
- clearly label DRAFT/SUBMITTED
- submitted register editing routes through the approved correction workflow rather than silently replacing history
- retain server-rendered Django Templates + Bootstrap + minimal JS

## Tests

- authorized admin capture
- correct date-effective roster rendered
- save draft
- submit
- validation messages
- absence note
- invalid/future/closed date behavior
- unauthorized access

## Gate 5 acceptance

The everyday admin capture workflow matches the domain and all tests/checks pass.

## Recommended commit

`feat: reconcile admin attendance capture`

STOP after Gate 5 and review.

---

# Gate 6 — Correction workflow hardening

## Goal

Keep the useful existing audit trail while making it fit submitted-register semantics.

## Rules

- only authorized administrator can correct submitted attendance
- correction changes accepted AttendanceEntry status
- immutable correction row records previous/new status, actor, timestamp, and current required reason if retained
- correction must not change AcademicEnrollment or register historical context
- repeated corrections preserve the full sequence
- correction only permits Phase 2 status choices

Decide explicitly whether DRAFT entries use normal editing rather than correction records; preferred rule:
- DRAFT: normal edits
- SUBMITTED: audited correction

## Tests

- DRAFT edit does not create correction unless deliberately designed otherwise
- submitted correction creates history
- repeated correction history
- invalid/no-op correction rejected
- unauthorized correction rejected
- reports use current accepted value
- historical context unchanged

## Gate 6 acceptance

Corrections are operationally simple and historically auditable.

## Recommended commit

`feat: harden audited attendance corrections`

STOP after Gate 6 and review.

---

# Gate 7 — Reporting and percentage semantics

## Goal

Make reports trustworthy under calendar, submission, correction, and transfer rules.

## Required Phase 2 reports

1. Daily Section register
2. Daily absent-student list
3. Student attendance history
4. Student attendance percentage
5. Missing-attendance report
6. Monthly Class/Section summary

## Percentage

Use only submitted eligible entries:

`PRESENT / (PRESENT + ABSENT) * 100`

Exclude:
- future dates
- non-instructional dates
- dates outside the relevant effective enrollment
- missing registers
- DRAFT/unsubmitted registers

Use current accepted status after corrections.

## Missing report

Must identify instructional Section/date combinations where:
- no register exists, or
- register remains DRAFT

Do not show non-instructional dates as missing.

If identifying all expected Section/date combinations requires a rule not currently represented by the domain, stop and document the gap rather than inventing a new year-scoped Section offering model. Use the simplest report consistent with existing Class/Section semantics.

## Transfer reporting

Student history should remain continuous, but each entry retains the Section/enrollment context that was true on that date.

## Tests

- all-present/absent percentage cases
- missing register excluded
- DRAFT excluded
- holiday excluded
- working Saturday included
- before/after transfer historical context
- correction changes current report value without erasing audit
- monthly summary
- absent list includes only submitted ABSENT
- authorization

## Gate 7 acceptance

All six reports obey the same business semantics.

## Recommended commit

`feat: reconcile attendance reporting`

STOP after Gate 7 and review.

---

# Gate 8 — Phase 2 integration hardening

## Goal

Run the same style of dedicated closeout that succeeded in Phase 1.

## End-to-end acceptance journey

Verify in one coherent automated journey:

Academic Year
→ calendar with instructional day, holiday, working Saturday
→ Student with effective-dated enrollment in Section A
→ create/open Section A attendance
→ date-effective roster includes Student
→ save incomplete DRAFT
→ mark PRESENT/ABSENT
→ submit complete register
→ reports show correct result
→ correct submitted status and preserve audit
→ transfer Student to Section B effective on a specified date
→ old attendance remains under Section A
→ later Section B roster includes Student
→ leave one instructional register missing or DRAFT
→ missing-attendance reporting identifies it
→ missing attendance does not lower Student percentage
→ holiday does not appear as missing

## Hardening checks

- model validation
- database constraints where feasible
- transaction safety for multi-write operations
- authorization on every mutation and protected read
- duplicate/conflict paths
- direct ORM regression tests for critical database invariants
- delete protection/history preservation
- no N+1 behavior in obvious report/list paths
- migration review
- `python manage.py check`
- full test suite
- Ruff
- manual changed-file review against ADR 0006/0007 and requirements

## Gate 8 acceptance

No known divergence from the approved Phase 2 source of truth.

## Recommended commit

`test: complete phase 2 attendance integration hardening`

STOP after Gate 8 and review.

---

# Gate 9 — Documentation closeout and Phase 2 tag

## Goal

Mark completion only after Gate 8 passes.

Update:
- README project status
- ROADMAP Phase 2 status: complete
- any implementation-relevant documentation that changed during reconciliation

Verify:
- main contains all gate commits
- tests/check/Ruff clean
- migrations reviewed
- no unresolved OPEN item blocks the accepted Phase 2 scope

Then create and push:

`phase-2-complete`

Do not reuse or move the `phase-1-complete` tag.

## Recommended commit

`docs: complete phase 2 attendance`

Then annotated tag:
`phase-2-complete`

---

# Explicit stop-and-return-to-planning conditions

Stop the coding agent and return to domain planning if implementation discovers a real need for:
- simultaneous overlapping academic placements
- period/subject attendance
- timetable
- Teacher/Class assignment in Phase 2
- Leave approval / future planned absence
- LATE, HALF_DAY, EXCUSED or other new attendance statuses
- a different percentage policy
- year-scoped Section offerings
- automatic lock windows/approval chains
- multi-school behavior

These are domain changes and must not be solved ad hoc inside a gate.

# Completion rule

Phase 2 is complete only when every gate is accepted in order and the final hardening journey proves:
- date-correct historical placement
- calendar-correct attendance eligibility
- explicit submission semantics
- no missing=absent ambiguity
- audited corrections
- trustworthy reports
- enforced authorization
