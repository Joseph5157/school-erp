# 0010. Phase 4 assessment-scoped teacher authorization

## Status

Accepted — implemented in Phase 4 (tag `phase-4-complete`)

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

DECIDED (Gate 2):
- A teacher is an active login in the "Teachers" group. There is no separate
  staff profile record. The group carries no model permissions: what a
  teacher may do is decided only by their assignments. Logins are added to
  the group through the site administration.
- Each offering + Section has exactly one owning teacher; one teacher may
  hold several assignments. Shared ownership of one result workflow would
  need a new decision.
- An offering's Section scope cannot drop a Section that has an assigned
  teacher.
- Leaving the group or being deactivated removes result-entry rights
  immediately. Administrator permissions and superuser status do not make
  someone a result-entering teacher.
- Reusable checks live in `core.authorization`: `is_teacher`,
  `teacher_assignments` and `can_enter_results`.

## Consequences

- ADR 0004's administrator-only rule remains true for every module except
  Phase 4 DRAFT result entry, which becomes assignment-scoped.
- The old Phase 5 assumption that all teacher assignment is deferred is
  narrowed: minimal assessment assignment is Phase 4; everything else about
  teachers remains Phase 5.

Later change: ADR 0012 D10 (Phase 5) moves Term remarks to the class
teacher; subject teacher assignments no longer grant remark writing.
ADR 0011 adds dated class teacher assignment alongside this one.

## Related requirements/domain decisions

- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0009-phase-4-assessment-and-results-model.md`
- `docs/PHASE_4_ASSESSMENTS_PLAN.md` — sections 10 and 16, Gate 2
