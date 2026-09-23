# 0006. Academic Enrollment effective dating

## Status

Accepted

## Context

ADR 0001 establishes Academic Enrollment as the historical placement record for a
Student. Phase 2 attendance must determine the Student's placement on the
attendance date, including before and after a transfer. Creation and update audit
timestamps cannot answer that business question reliably.

## Decision

FROZEN:

- AcademicEnrollment has a business-effective `start_date`.
- An ACTIVE enrollment has no effective `end_date`.
- A COMPLETED enrollment has an effective `end_date`.
- An enrollment's `end_date`, when present, must not precede its `start_date`.
- Effective enrollment periods for the same Student must not overlap.
- `created_at` and `updated_at` are audit metadata, not business-effective dates.
- A transfer preserves the former enrollment, closes its effective period, and
  creates the later enrollment with its own effective start date.
- Date-sensitive operational records use the enrollment effective on their
  business date.

## Consequences

- Current placement remains derived from the ACTIVE enrollment, as defined by
  ADR 0001 and ADR 0003.
- Attendance can retain the placement that was true on its date even after a
  later transfer.
- Migration and backfill work must not guess business-effective dates from
  audit timestamps; unknown historical dates require an explicit staged or
  data-entry approach.

## Related requirements/domain decisions

- `docs/DOMAIN_MODEL.md` — Academic Enrollment
- `docs/REQUIREMENTS.md` — Academic Enrollment and assignment
- `docs/adr/0001-academic-structure-and-enrollment-history.md`
- `docs/adr/0003-phase-1-status-and-transition-rules.md`
