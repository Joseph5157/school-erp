# Roadmap

The roadmap below is directional and meant to guide planning. Later phases may change as we learn more about real school workflows, data quality needs, and operational constraints.

Foundation
→ Phase 1 Student Lifecycle
→ Phase 2 Attendance
→ Phase 3 Fees
→ Phase 4 Assessments
→ Phase 5 Teacher Workflows
→ Phase 6 Parent/Student Experience
→ Phase 7 Communication & Reporting
→ Production Hardening

## Phase descriptions

### Foundation
- establish project governance and source-of-truth documentation
- define domain model, requirements, and architecture constraints
- confirm the initial school workflow boundaries and scope

### Phase 1 Student Lifecycle
- school configuration
- academic years
- classes and sections
- applicants
- guardians
- admission decisions
- student creation and enrollment
- academic enrollment and assignment
- student profiles, listing, and basic search
- student status changes (ACTIVE/INACTIVE)
- admin authorization foundation
- Phase 1 integration and hardening close-out

Status: complete.

### Phase 2 Attendance
- attendance register and per-enrollment status capture
- attendance history and operational corrections
- administrator-facing capture and reporting views
- attendance authorization using the shared authorization foundation

Status: planned (see `docs/adr/0005-phase-2-attendance-domain-model.md`).

Planned scope:
- attendance is enrollment-scoped and year-aware (ADR 0001, ADR 0005)
- minimum statuses PRESENT, ABSENT, LATE, EXCUSED
- corrections preserve history and are never destructive
- reporting limited to date-range attendance summaries

Out of scope for Phase 2:
- period/slot-level attendance
- teacher/parent/student attendance portals
- holiday calendar, notifications, device-based capture, dashboards

### Phase 3 Fees
- fee structures
- obligations/schedules
- payment recording
- fee reporting and reconciliation

### Phase 4 Assessments
- assessment planning
- result capture
- grade philosophy and reporting

### Phase 5 Teacher Workflows
- teacher assignment workflows
- class-specific operations
- daily teaching tasks and limited student access

### Phase 6 Parent/Student Experience
- guardian and student-facing information
- status visibility and announcements
- role-specific interaction model

### Phase 7 Communication & Reporting
- communication channels
- operational reporting
- management dashboards and reports

### Production Hardening
- security hardening
- operations and deployment readiness
- data integrity checks
- performance tuning and maintenance planning

## Roadmap principle

CURRENT: The roadmap is intentionally directional, not fixed forever. It should be revisited as the product learns from real usage and operational needs.
