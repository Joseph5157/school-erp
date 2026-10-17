# 0018. Effective-dated subject teacher assignments

## Status

Proposed (2026-10-17, completed-scope repair R10) — becomes FROZEN when the
R10 pull request is merged.

Amends ADR 0010 (undated, single-row assignment) and makes ADR 0012 D9
executable for subject teachers. ADR 0011 (class teachers) is unchanged and is
the model followed here.

## Context

ADR 0012 D9 says historical results are visible to a teacher "only for the
Section/dates or offering/Section they were assigned to at the time", and that
ending an assignment removes access to further data immediately.

`AssessmentTeacherAssignment` (ADR 0010) cannot meet this. It has no dates and
is unique per offering + Section, so changing the teacher means deleting the
row and creating another. The previous teacher's history is destroyed, and the
current teacher sees every finalized result of the offering + Section,
including assessments held before they took over. Class teachers (ADR 0011)
already have dated rows, hand-overs that end the old row, and results limited
to their own dates.

## Decision

- **D1 Dates.** An assignment has `start_date` and an optional `end_date`, both
  inclusive. A null `end_date` runs to the end of the offering's Academic Year;
  it never carries into the next year. Both dates must fall inside that year,
  and the end may not be before the start.
- **D2 One teacher at a time.** For one offering + Section, at most one
  assignment is effective on any date. Ranges for the same offering + Section
  may not overlap. Shared ownership is still outside scope (ADR 0010).
- **D3 Reassignment ends, never deletes.** Changing the teacher ends the
  current assignment on the day before the new start date and creates a new
  row, in one transaction that locks the offering. Nothing is overwritten.
- **D4 Future-dated assignments are allowed.** They must be inside the
  Academic Year and grant no access before `start_date`.
- **D5 Deletion.** An assignment may be deleted only if it has never taken
  effect (start date after the school-local business date) and nothing depends
  on it (no result entered by that teacher for that offering + Section inside
  its range). Any other assignment is ended instead. A future assignment with
  a wrong teacher or start date is deleted and recreated; R10 adds no general
  workflow for editing historical rows.
- **D6 Operational ownership (DRAFT work).** Entering or changing DRAFT
  results, and viewing the working gradebook, require an assignment effective
  on the business date. If Teacher B takes over today, B can finish an old
  DRAFT rather than leaving it stranded with Teacher A. Existing rules still
  prevent entry before the assessment date and any change to FINALIZED
  results.
- **D7 Historical visibility (FINALIZED results).** A teacher sees a finalized
  result of an offering + Section only if the assessment's `assessment_date`
  falls inside one of that teacher's assignments for it. The date used is the
  assessment date, not the finalization or entry date. This is the same rule
  already applied to class teachers.
- **D8 Former assignments.** After an assignment ends, the teacher loses
  student-list and student-profile access (these use current scope only, ADR
  0012 D8), result entry, and anything dated after the end. They keep
  read-only access to finalized results whose assessment date fell inside the
  assignment, through a past-duties section on "My results". No entry,
  gradebook editing or Student profile comes with it.
- **D9 Losing teacher status.** Leaving the Teachers group or being
  deactivated removes all access immediately, including D8's historical
  reads (the same as ADR 0011 D14), and never changes the rows. The
  "active Teachers-group login" check applies only when a row is created, so
  an administrator can still end a departed teacher's row.
- **D10 Offering scope.** An offering's Section scope still cannot drop a
  Section that has any assignment row, current or historical.
- **D11 Year copy.** Copying a year creates, for the same offering and
  Section, a row starting on the target year's first day, from the assignment
  effective on the source year's last day (as for class teachers).
- **D12 Administrator screens.** The assignments page shows the current
  teacher with a history list, offers Reassign (teacher + start date), End and
  Delete according to D5, and the gap report, inactive flag and teacher
  workload use dated rows.

## Migration baseline

Existing rows have no dates. The migration sets each one's `start_date` to its
Academic Year's start and leaves `end_date` empty, so current access is
unchanged on deploy. R10 cannot reconstruct teacher history that was deleted
before the migration. The backfill is a baseline assumption, not a claim that
the surviving teacher taught the Subject for the whole past year.

## Consequences

- Subject teachers lose sight of finalized results dated before their start
  date for assignments created after R10. Backfilled rows keep today's
  visibility.
- Reversing the migration is refused if any offering + Section has more than
  one assignment row, rather than silently destroying history. Once real
  hand-overs exist, rollback means backup and restore.
- Overlap is enforced in the application under a lock, with a unique
  constraint on (offering, Section, start date) and a check that the end is not
  before the start. There is no database-level range-exclusion constraint,
  because PostgreSQL and SQLite would then enforce different invariants. This
  is a known boundary, the same as for `SectionClassTeacher`: writes that
  bypass the model methods (raw SQL, bulk updates) can create overlaps.
- Not covered: timetable periods, cover or substitute teachers, shared
  ownership, and editing historical rows.

## Related

ADR 0010, ADR 0011, ADR 0012 (D8, D9, D14 by reference to ADR 0011).
