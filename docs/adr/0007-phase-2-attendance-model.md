# 0007. Corrected Phase 2 attendance model

## Status

Accepted

## Supersession

This ADR **supersedes ADR 0005 for Phase 2 attendance decisions**. ADR 0005 is
preserved as historical evidence of the earlier model and is not the source of
truth for reconciled Phase 2 implementation decisions.

## Context

The existing Phase 2 implementation contains useful register, entry, correction,
authorization, and reporting foundations. It must be reconciled with
date-effective enrollment, explicit calendar, register-submission, and
missing-attendance semantics before Phase 2 can be complete.

## Decision

FROZEN:

- Attendance is daily only; period or subject attendance is out of scope.
- An AttendanceRegister is scoped to one Section and one date, with at most one
  register for that Section/date.
- The roster is derived from AcademicEnrollments effective on the attendance
  date, not merely from the Student's current placement.
- Each AttendanceEntry references the applicable AcademicEnrollment.
- The Phase 2 status vocabulary is exactly PRESENT and ABSENT. ABSENT may carry
  an optional note.
- A minimal Academic-Year-aware school calendar determines whether attendance
  is expected. It supports holidays/closures and exceptional instructional dates
  such as working Saturdays; it is not a timetable or event system.
- Registers progress from DRAFT to SUBMITTED. Submission requires one explicit
  PRESENT or ABSENT entry for every effective roster enrollment.
- No register or an unsubmitted DRAFT register means attendance is not taken;
  missing or unsubmitted attendance is never interpreted as ABSENT.
- Attendance cannot be recorded or submitted for a future date.
- Corrections to submitted attendance are audited with the prior value, new
  value, correcting administrator, and timestamp. Existing reason requirements
  may remain as a stricter operational rule.
- Phase 2 attendance mutations remain administrator-only through the shared
  authorization foundation. Teacher attendance remains a Phase 5 concern.
- Student attendance percentage is `PRESENT / (PRESENT + ABSENT)` using only
  submitted, eligible attendance entries. Future, non-instructional,
  out-of-enrollment, missing, and DRAFT attendance are excluded.

## Consequences

- Academic Enrollment effective dating (ADR 0006) is a prerequisite for
  attendance roster correctness.
- The register lifecycle distinguishes recordkeeping not yet completed from a
  Student absence.
- Phase 2 must not add LATE, EXCUSED, HALF_DAY, leave, teacher assignment,
  portals, notifications, timetable, or period-level workflows without a new
  decision.

## Related requirements/domain decisions

- `docs/PHASE_2_RECONCILIATION_PLAN.md`
- `docs/REQUIREMENTS.md` — Phase 2 attendance
- `docs/DOMAIN_MODEL.md` — Attendance domain principles
- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0005-phase-2-attendance-domain-model.md` — superseded for Phase 2
  attendance decisions
- `docs/adr/0006-academic-enrollment-effective-dating.md`
