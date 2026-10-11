# 0012. Phase 5 teacher attendance and student access authorization

## Status

Accepted

## Context

Through Phase 4, attendance is administrator-only (ADR 0007) and teachers can
only enter DRAFT results and Term remarks for their assigned Subject/Section
(ADR 0010). Phase 5 lets the class teacher (ADR 0011) take daily attendance
and lets teachers look up their own Students, while keeping corrections,
finalization and record editing with administrators.
Planning: `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md` (decisions D4–D10).

## Decision

FROZEN:

- **D4** The class teacher effective on a date may open, fill and submit
  that Section's attendance register for that date. Submission uses the
  existing register lifecycle and records the teacher as `submitted_by`.
  Administrators keep every Phase 2 attendance power.
- **D5** Teachers may take or submit attendance for the school-local
  business date only, and only on an instructional day. Earlier NOT TAKEN or
  DRAFT registers are an administrator task.
- **D6** No substitute/cover workflow. When the class teacher is away an
  administrator takes attendance or changes the dated class teacher
  assignment.
- **D7** Teachers may edit a DRAFT register they may take, until it is
  submitted. SUBMITTED registers are read-only to teachers; corrections stay
  the audited administrator workflow of ADR 0007.
- **D8** Limited, read-only student access. A teacher may view a teacher
  student profile for a Student whose enrollment is effective today in a
  Section where the teacher is class teacher today or holds a subject teacher
  assignment:
  - every such teacher: name, current Class/Section, status, this year's
    attendance summary, and finalized results for the Subjects they teach
    there;
  - the class teacher additionally: finalized results for every Subject in
    the Section, and guardian names, relationships and contact details;
  - never: date of birth, Student contact details, applicant/admission
    records, Students outside scope, or any edit action.
- **D9** "My Students" lists use enrollments effective today. Historical
  registers and results are visible to a teacher only for the Section/dates
  or offering/Section they were assigned to at the time. Ending an
  assignment, or losing teacher status (ADR 0011 D14), removes access to
  further data immediately.
- **D10** Term remarks are written by the class teacher effective on the
  Term's end date (or on the business date, for a Term still running), for
  Students in that Section. Subject teachers no longer may. Administrators
  keep their power. Existing remarks are unchanged. This supersedes the
  Phase 4 remark rule recorded in ADR 0010 and the Phase 4 plan.

## Consequences

- ADR 0007's administrator-only attendance rule is narrowed: the class
  teacher may take and submit today's register for their Section; correction
  of submitted attendance remains administrator-only.
- ADR 0010's Term remark rule is replaced by D10.
- New checks (`class_teacher_on`, `can_take_attendance`,
  `teacher_student_scope`, guardian-contact visibility, updated
  `can_write_term_remarks`) live in `core.authorization` and every new view is
  covered by the app-wide authorization sweep.
- Attendance windows other than D5, cover teachers, teacher corrections and
  teacher editing of student or guardian data are stop-and-return-to-planning
  conditions.

## Related requirements/domain decisions

- `docs/PHASE_5_TEACHER_WORKFLOWS_PLAN.md`
- `docs/adr/0007-phase-2-attendance-model.md`
- `docs/adr/0010-phase-4-assessment-teacher-authorization.md`
- `docs/adr/0011-phase-5-class-teacher-and-teacher-workflow-model.md`
