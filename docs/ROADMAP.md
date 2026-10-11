# Roadmap

The roadmap below is directional and meant to guide planning. Later phases may change as we learn more about real school workflows, data quality needs, and operational constraints.

Foundation
→ Phase 1 Student Lifecycle ✅
→ Phase 2 Attendance ✅
→ Phase 3 Fees ⏸️ deferred (not implemented)
→ Phase 4 Assessments ✅
→ Phase 5 Teacher Workflows (Gate 0: decisions frozen)
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
- effective-dated Academic Enrollment and minimal Academic-Year-aware calendar
- daily Section/date registers with date-effective roster capture
- DRAFT/SUBMITTED attendance and audited corrections
- administrator-facing capture and reporting views
- attendance authorization using the shared authorization foundation

Status: complete (tag `phase-2-complete`). Reconciled through Gates 0-9 of
`docs/PHASE_2_RECONCILIATION_PLAN.md`; see ADR 0006, ADR 0007 and ADR 0008.

Approved scope:
- daily attendance only; statuses PRESENT and ABSENT
- submitted complete roster required; missing/unsubmitted attendance is not ABSENT
- future attendance prohibited; working Saturdays supported when instructional
- corrections preserve history; percentages use submitted eligible entries only

Out of scope for Phase 2:
- period/slot-level attendance
- teacher/parent/student attendance portals
- notifications, device-based capture, dashboards

### Phase 3 Fees
- fee structures
- obligations/schedules
- payment recording
- fee reporting and reconciliation

Status: DEFERRED / NOT IMPLEMENTED. The phase keeps its number so existing
research, plans and references stay valid. Fees carry higher audit,
correction and money-integrity risk, and the financial model (in particular
how recorded payments and receipts are corrected) is not yet frozen. No fee
code may be written until its Gate 0 decisions are frozen.

### Phase 4 Assessments
- subjects, Academic-Year-aware subject offerings and academic terms
- minimal teacher-to-subject/section assignment for result entry
- subject assessments with a date-effective roster
- DRAFT marks entry (MARKED/ABSENT), administrator finalization, audited corrections
- reusable grading scales, derived grades and optional pass marks
- result sheets, Student result history and simple Term report cards with optional teacher remarks

Status: complete (tag `phase-4-complete`). Implemented through Gates 0-11 of
`docs/PHASE_4_ASSESSMENTS_PLAN.md`; decisions in ADR 0009 and ADR 0010.

Out of scope for Phase 4: GPA, rank, weighting, rubrics, competency grading,
online exams, exam logistics, timetable integration, automatic promotion,
transcripts, board-specific rules, parent/student publication and
co-scholastic grading.

### Phase 5 Teacher Workflows
- dated class teacher assignment per Section and Academic Year
- class teacher takes and submits today's attendance for their Section
- teacher home page; limited read-only student access in the teacher area
- teacher-facing attendance and result views; Term remarks by the class teacher
- administrator assignment overview and conservative copy-from-last-year

Status: Gate 0 — decisions frozen in ADR 0011 and ADR 0012; implementation
proceeds gate by gate per `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md`.

Out of scope for Phase 5: timetable and period attendance, substitute/cover
workflows, staff/HR records, leave and staff attendance, lesson plans and
homework, teacher-to-guardian messaging, portals and mobile apps.

Note: the minimum assessment teacher assignment needed for Phase 4 result
entry is part of Phase 4 (ADR 0010). Everything else about teachers stays here.

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
