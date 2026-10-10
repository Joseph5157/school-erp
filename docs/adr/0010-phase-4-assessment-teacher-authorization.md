# 0010. Phase 4 assessment-scoped teacher authorization

## Status

Accepted

## Context

Through Phase 2 every mutation is administrator-only (ADR 0004), and teacher
assignment was assumed to be Phase 5 work. Phase 4 needs teachers to enter
marks, but only for the subjects and sections they teach. This ADR moves the
minimum assignment needed for safe result entry into Phase 4, and nothing
more.

## Decision

FROZEN:

- `AssessmentTeacherAssignment` links a User (the teacher's login), an
  AcademicSubjectOffering and a Section. It answers one question: may this
  user enter DRAFT results for this Subject/Section in this Academic Year?
- It does not represent timetable periods, workload, substitutions, HR
  assignment or payroll. Broader teacher workflows stay in Phase 5.
- Teachers authenticate as ordinary Users, consistent with ADR 0004: school
  domain records are never the authentication identity.
- A teacher may, only for assigned Subject/Section: view the relevant
  assessments and their date-valid roster, enter and modify DRAFT results,
  and mark a Student ABSENT.
- A teacher may not finalize results, change FINALIZED results, enter results
  for an unassigned Subject/Section, or reach other mutation workflows.
- Administrators configure academic structures, create assessments, review
  completeness, finalize, and perform audited corrections.
- Protected result reads respect these role boundaries. Guardian and Student
  access remains deferred.
- Scoped checks are centralized and reusable, extending the shared
  authorization foundation of ADR 0004 rather than being re-implemented per
  view.

OPEN (Gate 2):
- How a teacher login is recognized (for example a "Teachers" group) and
  whether a separate staff profile record is needed; ADR 0004 already forbids
  using a domain entity as the login itself.

## Consequences

- ADR 0004's administrator-only rule remains true for every module except
  Phase 4 DRAFT result entry, which becomes assignment-scoped.
- The old Phase 5 assumption that all teacher assignment is deferred is
  narrowed: minimal assessment assignment is Phase 4; everything else about
  teachers remains Phase 5.

## Related requirements/domain decisions

- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0009-phase-4-assessment-and-results-model.md`
- `docs/PHASE_4_ASSESSMENTS_PLAN.md` — sections 10 and 16, Gate 2
