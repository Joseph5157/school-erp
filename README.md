# School ERP

## Project status

This repository contains the documentation foundation and the completed
Phase 1, Phase 2, Phase 4, Phase 5 and Phase 6 implementations of the School ERP.

Current status:
- documentation foundation established; business and domain decisions are the source of truth
- approved technology stack recorded in `docs/ARCHITECTURE.md` (Django + PostgreSQL)
- Phase 1 Student Lifecycle is complete:
  - custom User model (accounts)
  - school configuration
  - academic year management
  - class/grade and section management
  - applicant registration and guardian records with Applicant–Guardian relationships
  - explicit admission decisions (accept/reject)
  - explicit Applicant-to-Student progression with carried-forward guardians
  - academic enrollment with historical placement (one ACTIVE per Student)
  - student list, search, profile, and ACTIVE/INACTIVE status workflow
  - initial administrative authorization/permissions (School Administrators group)
  - full acceptance journey verified end to end by automated tests
- Phase 2 Attendance is complete (tag `phase-2-complete`), reconciled gate by
  gate per `docs/PHASE_2_RECONCILIATION_PLAN.md`:
  - effective-dated Academic Enrollment with date-correct historical lookup (ADR 0006)
  - minimal Academic-Year-aware school calendar: weekly pattern plus holiday /
    working-Saturday exceptions (ADR 0008)
  - daily Section/date registers with a date-effective roster
  - statuses PRESENT and ABSENT only, with an optional absence note
  - DRAFT → SUBMITTED registers; a complete roster is required to submit;
    missing or DRAFT attendance is never treated as ABSENT
  - audited corrections of submitted attendance (status, note, actor, time, reason)
  - reports: daily register, absent list, Student history and percentage,
    missing attendance, monthly Class/Section summary
  - administrator-only authorization; reconciled acceptance journey verified
    end to end; full suite passes on SQLite and PostgreSQL
- Phase 3 Fees is deferred (not implemented; the phase keeps its number).
- Phase 4 Assessments is complete (tag `phase-4-complete`), implemented gate by
  gate per `docs/PHASE_4_ASSESSMENTS_PLAN.md` (ADR 0009, ADR 0010):
  - Subjects, Academic-Year-aware subject offerings (optionally limited to
    Sections) and ordered Academic Terms
  - minimal teacher assignment (Teachers group; one teacher per offering + Section)
    scoping result entry and Term remarks
  - reusable grading scales (min-percentage bands); bands are frozen onto an
    assessment when it is finalized
  - subject assessments with a date-effective roster from Academic Enrollment
  - teacher DRAFT entry of MARKED / ABSENT results (ABSENT is never zero;
    missing is never ABSENT)
  - administrator finalization of complete rosters; audited corrections afterwards
  - optional Term teacher remarks
  - reports: assessment result sheet, Student result history, Subject/Section
    results, Term report card — finalized values only, history never rewritten
  - full acceptance journey verified end to end; full suite passes on SQLite
    and PostgreSQL
- Phase 5 Teacher Workflows is complete (tag `phase-5-complete`), implemented
  gate by gate per `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md` (ADR 0011, ADR 0012):
  - dated class teacher assignment per Section (one at a time; hand-overs end
    the old row; effective rows are ended, never deleted or rewritten —
    enforced in the application and by database triggers)
  - teacher area (`my/`): My day, today's attendance for the class teacher's
    Section (business date only; submitted registers read-only to teachers),
    attendance history for their own assignment dates
  - limited, read-only teacher student profiles; guardian contacts for the
    class teacher only; no date of birth, Student contacts or edits
  - teacher result views; Term remarks and report cards owned by the class
    teacher on the Term's last day
  - administrator assignment overview with gaps and inactive holders flagged,
    per-teacher load, and a preview-first, never-guessing copy of another
    year's assignments
  - full acceptance journey verified end to end; full suite passes on SQLite
    and PostgreSQL
- Phase 6 Guardian Portal is complete (tag `phase-6-complete`), implemented gate
  by gate per `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md` (ADR 0013, ADR 0014):
  - administrator-created guardian accounts after identity verification, with a
    one-time temporary password, forced first-login change and
    administrator-only reset; one normalized, case-insensitive username rule
  - one login per person (a teacher who is also a parent) with explicit area
    choice; explicit, per-relationship Student access grants
  - links, grants, access reviews and publications are revoked or superseded,
    never deleted or rewritten (application rules and database triggers)
  - explicit retain/revoke review when a Student becomes inactive or a
    placement ends; fail-closed review when a Student has no current
    enrollment
  - read-only portal (`guardian/`): approved profile (including optional
    admission and roll numbers), submitted attendance and summary, and Term
    report cards published explicitly through a preview, stored as immutable
    snapshots and hidden again when a released result or remark is corrected
  - database-backed sign-in throttling, generic sign-in errors, 30-minute idle
    and 8-hour absolute sessions, hashed network sources, production HTTPS
    settings and a security audit with routine-event retention
  - Student accounts are deferred to Phase 6B; fees, announcements and PDFs are
    excluded
  - full acceptance journey verified end to end; full suite passes on SQLite
    and PostgreSQL

## Documentation

- [docs/PRODUCT.md](docs/PRODUCT.md) — product vision, users, principles, and module strategy
- [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) — domain model, lifecycle, enrollment, and historical-data rules
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) — Phase 1, 2 and 4 scope, out-of-scope items, and acceptance criteria
- [docs/PHASE_2_RECONCILIATION_PLAN.md](docs/PHASE_2_RECONCILIATION_PLAN.md) — Phase 2 gate-by-gate plan and completion record
- [docs/PHASE_4_ASSESSMENTS_PLAN.md](docs/PHASE_4_ASSESSMENTS_PLAN.md) — Phase 4 gate-by-gate plan and completion record
- [docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md](docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md) — Phase 5 gate-by-gate plan and completion record
- [docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md](docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md) — Phase 6 gate-by-gate plan, completion record and release notes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — engineering principles, security, architecture guidance, and source-of-truth hierarchy
- [docs/ROADMAP.md](docs/ROADMAP.md) — directional roadmap across future phases
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — running a production installation: crash logs and error emails
- [docs/ECC_EVALUATION.md](docs/ECC_EVALUATION.md) — ECC experiment goals and evaluation framework
- [docs/adr/README.md](docs/adr/README.md) — ADR purpose and process

## Important note

The approved technology stack is recorded in `docs/ARCHITECTURE.md`. Future
phases must follow the documented domain model, requirements, and ADRs.
Out-of-scope modules must not be started.
