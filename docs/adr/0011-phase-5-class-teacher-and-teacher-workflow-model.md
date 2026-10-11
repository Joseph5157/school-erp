# 0011. Phase 5 class teacher and teacher workflow model

## Status

Accepted

## Context

Phase 4 introduced the Teachers group and assessment-scoped subject teacher
assignment (ADR 0010). Daily, Section-level work — attendance, Term remarks,
first contact with guardians — belongs in this school to one *class teacher*
per Section, who may or may not teach a subject there. Phase 5 adds that role
and the administrator workflows around teacher assignment, without adding a
staff/HR record or a teacher-facing copy of the admin ERP.
Planning: `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md` (decisions D1–D3, D11–D14).

## Decision

FROZEN:

- **D1** `SectionClassTeacher` links a User, an Academic Year and a Section.
  It is independent of `AssessmentTeacherAssignment`: being class teacher does
  not imply teaching a Subject in that Section, and the reverse.
- **D2** At most one class teacher is effective for a Section on any date.
  One teacher may be class teacher of several Sections. Co-class-teachers are
  out of scope.
- **D3** Class teacher assignments are dated (`start_date`, optional
  `end_date`) inside the Academic Year; ranges for one Section never overlap.
  A change of class teacher ends the current row and starts a new one;
  authorization uses the row effective on the relevant date, and the history
  of who was class teacher when stays answerable.
  Deletion: a row becomes historically relevant once it has taken effect
  (its `start_date` is on or before the school-local business date) or once
  any record depends on it. From then on normal workflows **end** it and
  never delete it; only a not-yet-effective row with no dependent records may
  be deleted, to correct a planning mistake. Gate 8 hardens application and
  database deletion protection.
- **D11** Teacher pages live in a separate teacher area (`my/`) with their
  own templates and navigation; the admin ERP is not exposed to teachers.
  Teachers continue to hold no model permissions; every teacher check is
  assignment-based and centralized in `core.authorization`. Membership of the
  Teachers group remains the definition of "is a teacher".
- **D12** No staff profile, HR or directory record. Teachers are Users.
- **D13** Administrators get, per Academic Year, an overview of every
  Section's class teacher and every offering/Section's subject teacher, with
  gaps highlighted, a per-teacher load view, and a *copy previous year's
  assignments* action that is:
  - preview-first: nothing is written until the administrator confirms the
    previewed set;
  - conservative: a row is copied only when its equivalent is exact and
    unique (same Class/Grade and Section name in the new year; same Subject
    offered for that Class/Grade and Section in the new year). Matches are
    never guessed;
  - skipping, with every skip reported with its reason: inactive or
    non-teacher logins, ambiguous Sections or Subjects, missing equivalents,
    and targets that already have an assignment;
  - idempotent: confirming twice creates nothing new.
- **D14** Deactivating a login or removing it from the Teachers group removes
  all teacher access immediately, because every check requires an active
  Teachers-group login at request time. It never deletes, ends or rewrites
  existing class teacher or subject teacher assignments; history is
  preserved. The administrator overview flags assignments held by inactive or
  non-teacher logins so an administrator can deliberately end or replace them.

## Consequences

- The Teachers group plus dated assignments become the whole teacher model;
  adding a staff record later needs a new decision.
- Phase 5 adds one model (`SectionClassTeacher`); existing attendance,
  assessment and remark models keep their schemas.
- Substitute/cover workflows, co-class-teachers, timetable and HR are
  stop-and-return-to-planning conditions.

## Related requirements/domain decisions

- `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md`
- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0006-academic-enrollment-effective-dating.md`
- `docs/adr/0010-phase-4-assessment-teacher-authorization.md`
- `docs/adr/0012-phase-5-teacher-attendance-and-student-access.md`
