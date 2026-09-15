# 0003. Phase 1 status and transition rules

## Status

Accepted

## Context

`docs/REQUIREMENTS.md` intentionally left the Student status list and the Academic Enrollment status list undefined, delegating the minimum set to the implementation plan ("the implementation plan must define only the minimum statuses necessary"). It also left the admission-decision repeat/conflict policy unspecified beyond the constraint that it "must not silently create a Student or erase the prior application history."

Phase 1 planning review identified these as open items that must be resolved before status fields can be modeled or tested. This ADR fixes the minimum Phase 1 status vocabularies and their transition rules.

## Decision

FROZEN — Admission lifecycle:

- PENDING → ACCEPTED
- PENDING → REJECTED
- ACCEPTED and REJECTED are final admission decisions for normal Phase 1 operation.
- Normal Phase 1 operations do not directly switch ACCEPTED ↔ REJECTED.
- Rejected Applicants cannot progress to Student.
- Repeated Student-progression attempts must not create another Student.

CURRENT — Decision correction:

- Future decision-correction/reopening functionality (for example, reversing a REJECTED decision) requires an explicit, audited workflow and is outside Phase 1.

FROZEN — Student status minimum set:

- ACTIVE
- INACTIVE
- No additional status (Graduated, Transferred, Suspended, Withdrawn, or similar) is added until the corresponding workflow exists.

FROZEN — Academic Enrollment status minimum set:

- ACTIVE
- COMPLETED
- A Student may have many COMPLETED historical enrollments.
- A Student may have at most one ACTIVE Academic Enrollment.
- Current academic placement is derived from the ACTIVE enrollment.
- Moving a Student into a new academic placement completes the previous ACTIVE enrollment and creates a new ACTIVE enrollment, rather than overwriting the historical record.

CURRENT — Status governance:

- If implementation later discovers a genuine need for another status (admission, Student, or Enrollment), that requires explicit review rather than silently expanding the enum.

## Alternatives considered

- **Allow ACCEPTED ↔ REJECTED to be freely toggled by any administrator at any time.** Rejected: conflicts with important status transitions being historical and auditable (`docs/DOMAIN_MODEL.md` — "Historical data"), and would make the "rejected cannot progress" guarantee unreliable without an audit trail.
- **Pre-define a larger Student status enum now** (including Graduated/Transferred/Withdrawn), anticipating future phases. Rejected: these statuses have no corresponding Phase 1 workflow, and `docs/REQUIREMENTS.md` explicitly calls for only the minimum necessary set.
- **Model Academic Enrollment status as a single boolean `is_current` flag** instead of ACTIVE/COMPLETED. Rejected: does not name the terminal historical state explicitly, and reads less clearly in audits/reports than an explicit COMPLETED status.

## Consequences

- Any admission-decision reversal needed in practice before Phase 1 ends must be raised as a scope/architecture question, not implemented ad hoc.
- "At most one ACTIVE Academic Enrollment per Student" and "at most one Student per Applicant" (ADR 0001, ADR 0002) are now expressed as concrete, testable status rules.
- Test suites can assert exact status values (PENDING/ACCEPTED/REJECTED, ACTIVE/INACTIVE, ACTIVE/COMPLETED) rather than placeholder ones.

## Related requirements/domain decisions

- `docs/REQUIREMENTS.md` — "Admission decision", "Student status", "Academic Enrollment and assignment"
- `docs/DOMAIN_MODEL.md` — "Historical data"
- `docs/adr/0001-academic-structure-and-enrollment-history.md`
- `docs/adr/0002-applicant-student-and-guardian-lifecycle.md`
