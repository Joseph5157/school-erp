# Academic Year Rollover Plan

## Status

**Queued for Rollover 0 ADR / decision freeze. No rollover domain implementation until Gate 0 is approved.**

This is a future domain feature and should begin with an ADR/decision-freeze gate before code.

## Purpose

At the end of one Academic Year, administrators need a safe bulk workflow to review every currently enrolled Student and decide what happens in the next Academic Year.

The current `AcademicEnrollment` model already provides the correct historical foundation. Rollover must create new placement history; it must never rewrite old enrollment history.

## Outcomes

Each source enrollment receives one explicit outcome:

- **PROMOTE** — create a new enrollment in a higher/different Grade for the target Academic Year.
- **REPEAT** — create a new enrollment in the same Grade for the target Academic Year; Section may remain the same or change.
- **GRADUATE** — complete schooling; no target enrollment.
- **LEAVE** — Student leaves/transfers out; no target enrollment.
- **HOLD** — no target enrollment yet; administrator will decide later.

Do not reduce rollover to pass/fail.

## Promotion policy

Do **not** derive promotion automatically from marks.

Results, report cards, and attendance may be shown as context, but the administrator makes the explicit rollover decision. Different schools may use different promotion rules, supplementary examinations, attendance criteria, or principal discretion.

## Section mapping

The system must not infer progression from Grade names.

Administrators define default mappings, for example:

- Grade 1-A -> Grade 2-A
- Grade 1-B -> Grade 2-B
- Grade 6-A -> Grade 7-A

These defaults prefill Student decisions. Administrators change only exceptions.

## Prepare now, apply later

A rollover may be prepared before the target Academic Year starts.

Lifecycle:

- **DRAFT**
- **READY**
- **APPLIED**
- **CANCELLED**

Preparing a rollover must not create future ACTIVE `AcademicEnrollment` rows.

The batch is applied only on or after the target Academic Year's start date.

## Enrollment history rule

Rollover uses a dedicated domain service, not a naive loop over the current `Student.enroll()` transfer workflow.

For rollover:

- close the source enrollment on the **source Academic Year's end date**;
- create the target enrollment on the **target Academic Year's start date**.

Vacation gaps are valid and should not be filled by extending the old year.

Example:

- 2026-27 Grade 6-A: COMPLETED on 30 Apr 2027
- 2027-28 Grade 7-A: ACTIVE from 01 Jun 2027

Historical attendance, results, report cards, roll numbers, and teacher access remain tied to the original enrollment/year.

## Roll numbers

Do not copy or generate roll numbers automatically.

The target enrollment starts without a roll number unless the school explicitly assigns one through the normal workflow.

## Guardian access

Rollover must integrate with the existing guardian-access review rules.

Recommended defaults:

- PROMOTE -> retain
- REPEAT -> retain
- HOLD -> retain
- GRADUATE -> revoke
- LEAVE -> revoke

The review screen should make the consequence explicit and allow justified exceptions where existing guardian-access rules permit them.

## Student lifecycle

For GRADUATE and LEAVE:

- complete the source enrollment;
- create no target enrollment;
- transition Student to INACTIVE using the existing audited lifecycle mechanism;
- record a clear rollover reason.

For HOLD:

- Student remains ACTIVE;
- there is no current AcademicEnrollment after the old year closes;
- surface the Student in a **Needs placement** list until resolved.

## Teachers and timetable

Student rollover must **not** copy:

- class-teacher assignments
- subject-teacher assignments
- timetable slots
- assessments
- subject offerings
- Academic Terms

Those belong to the target Academic Year's own configuration.

## Proposed data model

### AcademicYearRollover

- source_academic_year
- target_academic_year
- status: DRAFT / READY / APPLIED / CANCELLED
- created_by
- created_at
- reviewed_at
- applied_by
- applied_at

### AcademicYearRolloverDecision

- rollover
- source_academic_enrollment
- decision: PROMOTE / REPEAT / GRADUATE / LEAVE / HOLD
- target_class_grade, optional
- target_section, optional
- created_enrollment, optional
- note, optional

Rules:

- PROMOTE and REPEAT require a target placement.
- GRADUATE, LEAVE and HOLD must not have a target placement.
- APPLIED decisions are historical/auditable and not freely editable.

## Stale-plan protection

A rollover prepared earlier must be revalidated before it becomes READY and again before APPLY.

Detect at least:

- Students added after the plan was prepared
- source placement changes
- source Students becoming inactive
- duplicate/overlapping target placement
- target Section/Class mismatch
- target Academic Year changes relevant to validity

If the source roster changed, require review rather than silently skipping or overwriting Students.

## Administrator workflow

Desktop-first workflow:

1. **Start rollover**
   - select source Academic Year
   - select target Academic Year
   - show source Student count

2. **Map Sections**
   - define source Section -> default target Section

3. **Review Students**
   - roster grouped by source Section
   - prefilled Promote decisions where mapping exists
   - bulk action per Section
   - individual exceptions

4. **Review summary**
   - Promote count
   - Repeat count
   - Graduate count
   - Leave count
   - Hold count
   - validation warnings

5. **Mark READY**
   - only when every source Student has a valid decision

6. **Apply**
   - available on/after target Academic Year start date
   - show final destructive/irreversible summary

7. **Completion**
   - show created enrollments and unresolved HOLD Students
   - provide link to new-year Student list / Needs placement list

## Transactional application

Applying a rollover must validate the entire batch first and execute atomically.

Conceptually:

1. lock/re-read source records
2. revalidate the rollover
3. close source enrollments
4. create target enrollments for Promote/Repeat
5. apply Student lifecycle transitions for Graduate/Leave
6. apply guardian-access decisions
7. mark rollover APPLIED

If any item fails, roll back the entire batch.

Application must be idempotent: an APPLIED rollover cannot be applied again.

## Explicitly out of scope for v1

Do not add:

- automatic promotion based on marks
- school-specific pass/fail engines
- supplementary-exam automation
- automatic roll-number generation
- automatic teacher reassignment
- automatic subject/timetable copying
- automatic Section creation
- Guardian notifications
- Excel rollover import
- background scheduled application

## Implementation gates

### Rollover 0 — Decision freeze

- ADR
- requirements
- domain rules
- acceptance scenarios
- no code

### Rollover 1 — Domain foundation

- rollover + decision models
- validation
- stale-plan detection
- transactional application service
- lifecycle and guardian-access integration

### Rollover 2 — Administrator workflow

- start
- Section mapping
- Student decisions
- review
- ready
- apply
- completion
- desktop-first UI

### Rollover 3 — Hardening

Cross-phase tests for:

- enrollment history
- attendance preservation
- results/report-card preservation
- roll numbers
- guardian access
- teacher authorization
- concurrency
- idempotency
- PostgreSQL integrity
- browser acceptance

## Definition-of-done scenario

For one promoted Student:

Before:

- 2026-27 Grade 6-A, ACTIVE, Roll 18
- attendance/results/report cards preserved
- Guardian access active

After:

- 2026-27 Grade 6-A, COMPLETED, Roll 18 retained historically
- 2027-28 Grade 7-A, ACTIVE, no roll number yet
- old attendance unchanged
- old results unchanged
- old report cards unchanged
- Guardian access retained
- target-year teacher access determined only by target-year assignments

Equivalent acceptance scenarios are required for Repeat, Graduate, Leave and Hold.
