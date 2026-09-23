# 0005. Phase 2 attendance domain model and rules

## Status

Accepted

## Context

`docs/ROADMAP.md` defines Phase 2 as Attendance with three directional bullets: attendance capture and reporting, attendance history and operational corrections, and role-appropriate attendance views. `docs/DOMAIN_MODEL.md` already names attendance as a historical record subject to the FROZEN "no destructive updates" principle, and ADR 0001 fixes Academic Enrollment as the single record of a Student's placement for an Academic Year, Class/Grade, and Section. ADR 0004 fixes the shared authorization foundation.

Phase 2 planning review identified several modeling questions left unresolved by the existing documentation: what an attendance record attaches to, whether a register/session grouping exists, the minimum attendance status vocabulary, how corrections preserve history, and how much role-based access belongs in Phase 2 versus later phases. This ADR fixes the minimum Phase 2 attendance model consistent with the constraints above.

## Decision

FROZEN — Attendance is enrollment-scoped and year-aware:

- Attendance is recorded against a Student's Academic Enrollment for the relevant Academic Year, not against a mutable field on Student.
- Each attendance record concerns one Student, one Academic Year, one date, and the Class/Grade + Section context derived from that Academic Enrollment.
- A Student cannot be marked for a Class/Grade + Section + Academic Year they are not enrolled in.
- An attendance date must fall within the date range of the associated Academic Year.

FROZEN — Attendance register:

- Attendance for a Section on a date is captured through an explicit register scoped to a Class/Grade + Section and a date, rather than as ungrouped per-student rows.
- The register is the unit of capture and of "who has been marked" reporting for that Section and date.
- Period/slot-level registers (more than one register per Section per day) are not part of Phase 2.

FROZEN — Minimum attendance statuses:

- PRESENT
- ABSENT
- LATE
- EXCUSED
- No additional status (Half-day, Leave, and similar) is added until the corresponding workflow exists.

FROZEN — Historical integrity and corrections:

- Attendance records are historical records and are not hard-deleted.
- Every change to a previously captured attendance status is recorded as an explicit correction carrying the previous status, the new status, the correcting actor, the timestamp, and a reason.
- Correction history is preserved and is never overwritten by the current value.
- The effective attendance status for a Student/date is the latest captured or corrected value.

FROZEN — Authorization:

- Every attendance mutation (register creation, status capture, correction) requires authenticated, authorized administrative access through the shared authorization mechanism (ADR 0004).
- Attendance reads respect the same administrative boundary.
- Teacher, Guardian, and Student attendance access is not implemented in Phase 2.

CURRENT — Role-appropriate views interpretation:

- "Role-appropriate attendance views" in Phase 2 means administrator-facing capture versus administrator-facing reporting/read-only views, not end-user portals.
- The model and permission boundaries must not preclude later scoping a Teacher to their assigned Section(s) (Phase 5) or exposing a read-only Guardian/Student view (Phase 6), but neither is built in Phase 2.

CURRENT — Reporting scope:

- Phase 2 reporting is limited to attendance over a date range: per-Student attendance history and per-Section attendance for a date/range, including an attendance summary (for example, counts/percentage by status).
- Dashboards, analytics, and scheduled reports remain out of scope (Phase 7).

OPEN:

- Period/slot-level attendance capture.
- A formal holiday/non-instructional-day calendar; Phase 2 assumes registers are only created for actual school days.
- Attendance entry removal/void semantics beyond status correction.
- Teacher, Guardian, and Student attendance access.
- Attendance-based notifications to Guardians.

## Alternatives considered

- **Record attendance directly against Student and Section instead of Academic Enrollment.** Rejected: ADR 0001 makes Academic Enrollment the authoritative placement record, and recording against a mutable Student/Section pairing would allow attendance to drift from historical placement.
- **A flat per-Student/per-date model with no register.** Rejected: capture and "unmarked student" reporting for a Section are core operational needs, and reconstructing a register from flat rows adds complexity without benefit.
- **Mutable attendance status with no correction history.** Rejected: directly conflicts with the FROZEN historical-record principle in `docs/DOMAIN_MODEL.md`.
- **Append-only status rows with no current-value field.** Rejected as more complex than needed for Phase 2; a current value plus an immutable correction log expresses the same history with simpler reads.
- **Pre-define a large attendance status enum now.** Rejected: statuses without a corresponding workflow violate the minimum-set principle established in ADR 0003.
- **Build teacher/Guardian/Student attendance views in Phase 2.** Rejected: those roles and their assignment scoping are Phase 5 and Phase 6 work; Phase 2 stays administrator-facing while keeping the boundary open.

## Consequences

- Attendance depends on Academic Enrollment being correct; an unenrolled Student cannot be marked, which keeps attendance consistent with historical placement.
- A register plus per-enrollment entries is required, with uniqueness per (register, enrollment) enforced at implementation time.
- A correction record (previous status, new status, actor, timestamp, reason) must exist and must be tested, including that corrections never erase prior values.
- Reporting is bounded to date-range summaries; richer analytics are deferred to Phase 7.
- Adding period-level attendance, a holiday calendar, or role-scoped views later requires a new ADR amending or superseding this one rather than an ad hoc schema change.

## Related requirements/domain decisions

- `docs/ROADMAP.md` — "Phase 2 Attendance"
- `docs/DOMAIN_MODEL.md` — "Historical data", "Academic Enrollment"
- `docs/REQUIREMENTS.md` — "Phase 2 scope", "Attendance capture", "Attendance corrections", "Attendance reporting"
- `docs/adr/0001-academic-structure-and-enrollment-history.md`
- `docs/adr/0003-phase-1-status-and-transition-rules.md`
- `docs/adr/0004-phase-1-authorization-foundation.md`
