# Phase 5 — Teacher Workflows

## Status

FROZEN (Gate 0) — decisions D1–D14 in section 3 are accepted as the Phase 5
baseline and recorded in ADR 0011 (class teacher and teacher workflow model)
and ADR 0012 (teacher attendance and student access). If this plan and an
ADR ever differ, the ADR is authoritative. Implementation follows the gates
below, in order.

Starting point:

- Phase 1 Student Lifecycle — complete
- Phase 2 Attendance — complete (`phase-2-complete`); administrator-only
- Phase 3 Fees — deferred
- Phase 4 Assessments — complete (`phase-4-complete`); introduced the
  Teachers group and assessment-scoped teacher assignment (ADR 0010)

Research inputs:

- Gibbon separates the *form group tutor* (pastoral: daily attendance,
  behaviour, student well-being) from the *subject teacher* (planner,
  markbook). By default any teacher may take any form group's attendance,
  relying on an audit log; a later "my groups only" permission was added and
  schools report it gets in the way of cover/substitute teachers.
- Frappe Education links Instructors to a Student Group and marks attendance
  in bulk per group and date through an attendance tool; instructor scoping
  is left to role permissions.
- Indian school practice (the deployment context, `Asia/Kolkata`): every
  Section has one *class teacher* who takes daily attendance, owns report-card
  remarks and is the parent's first contact; subject teachers teach and
  assess their subjects across Sections.

The plan keeps this project's established principles: one school, historical
correctness, explicit lifecycles, audited corrections, centralized
authorization, and no direct exposure of the admin ERP as a teacher portal
(PRODUCT.md, FROZEN).

---

# 1. Phase 5 goals

Phase 5 lets teachers do their daily, Section-specific work themselves,
inside a teacher area, without administrator mediation and without widening
access beyond what their assignments justify:

- class teacher assignment per Section and Academic Year
- teacher-taken daily attendance for the class teacher's own Section
- a teacher home page: today's work across attendance, marks and remarks
- limited, read-only student access scoped to the teacher's Sections
- teacher-facing read-only attendance and result views for their scope
- administrator workflows to manage teacher assignments over a year and
  across years

---

# 2. Explicitly out of scope

- timetable, periods, period/slot-level attendance
- substitute/cover workflows and workload tracking (see D6)
- staff/teacher attendance, leave, HR records, payroll
- lesson plans, homework, gradebooks outside assessments
- teacher-to-parent messaging, announcements, notifications (Phase 6/7)
- guardian and student portals (Phase 6)
- mobile applications
- behaviour/discipline records, counselling notes
- teacher editing of student, guardian or enrollment records
- teacher finalization of results or correction of submitted attendance

---

# 3. Frozen decisions (Gate 0)

Each decision is FROZEN (ADR 0011, ADR 0012). Rejected alternatives are kept for the record.

### D1. Class teacher is a separate assignment from subject teaching

FROZEN: Add `SectionClassTeacher` (User + Academic Year + Section). It is
independent of `AssessmentTeacherAssignment`: a class teacher need not teach
a subject in that Section, and a subject teacher is not a class teacher.

Alternative: derive the class teacher from subject assignments (rejected —
ambiguous when several teachers teach one Section).

### D2. Exactly one class teacher per Section per Academic Year, at a time

FROZEN: At most one *current* class teacher per Section and Academic Year.
A teacher may be class teacher of more than one Section (rare; allowed).
Co-class-teachers are out of scope.

### D3. Class teacher changes are dated, not overwritten

FROZEN: `SectionClassTeacher` carries `start_date` and optional `end_date`
inside the Academic Year, and ranges for one Section may not overlap
(same pattern as effective-dated enrollment, ADR 0006). Replacing a class
teacher ends the old row and starts a new one. Authorization uses the row
effective on the relevant date; history ("who was class teacher in July")
stays answerable.

Alternative: one row per Section/year, edited in place (simpler; loses
history, and actor fields on registers would be the only trace).

FROZEN note: once a row has taken effect (start_date on or before the
business date) or any record depends on it, normal workflows end it and
never delete it. Only a not-yet-effective row with no dependents may be
deleted. Gate 8 hardens application and database deletion protection.

### D4. Teachers take daily attendance for their own Section

FROZEN: The class teacher effective on a date may open, fill and **submit**
that Section's register for that date. Submission uses the existing
`AttendanceRegister.submit(actor=...)`; `submitted_by` records the teacher.
Administrators keep every current attendance power.

Alternative: teacher saves DRAFT only and an administrator submits (mirrors
assessment finalization; rejected because daily attendance must be official
the same day and would create a daily admin bottleneck).

### D5. Teacher attendance date window

FROZEN: A teacher may take or submit attendance for **today only**
(school-local business date), on an instructional day. Earlier missing or
DRAFT registers are handled by an administrator. The missing-attendance
report already shows them.

Alternatives: today plus N previous instructional days (more forgiving;
needs a setting and widens the window for after-the-fact edits).

### D6. No substitute/cover workflow in Phase 5

FROZEN: When the class teacher is away, an administrator takes attendance
(today's behaviour) or changes the dated class-teacher assignment.
A cover-assignment model is a stop-and-return-to-planning condition.

Alternative: a dated `CoverAssignment` granting temporary register access
(Gibbon's experience shows strict scoping without cover causes friction).

### D7. Submitted attendance stays administrator-corrected

FROZEN: Teachers cannot change a SUBMITTED register. Corrections remain
the audited administrator workflow from Phase 2 (ADR 0007). A teacher may
edit their own DRAFT until submission.

### D8. Limited student access

FROZEN: A teacher may view a read-only **teacher student profile** for a
Student whose enrollment is effective today in a Section the teacher is
assigned to (class teacher or subject teacher):

- both: name, admission/student identifier, current Class/Section, status,
  attendance summary for this year, finalized results for subjects they
  teach (class teacher: all subjects in their Section)
- class teacher only: guardian names, relationships and contact phone/email
- never: date of birth and Student contact details beyond what the class
  teacher needs, applicant/admission records, other Students outside scope,
  any edit action

Alternative: class teachers only, no subject-teacher access (stricter).

### D9. Scope follows the current date, history follows the record

FROZEN: Lists of "my Students" use enrollments effective **today**.
Historical records (registers, results) remain visible to a teacher only for
the Section/date or offering/Section they were assigned to at that time.
A teacher who leaves an assignment loses access to new data immediately.

### D10. Term remarks belong to the class teacher

FROZEN (changes a Phase 4 decision): from Phase 5, the class teacher
effective at the Term end writes the Term remark for each Student in their
Section; subject teachers no longer may. Administrators keep their power.
Existing remarks are unchanged.

Alternative: keep Phase 4 behaviour (any teacher assigned to a Subject in
the Section may write remarks).

### D11. Teacher area, not the admin ERP

FROZEN: All teacher pages live under `my/` with their own templates and
navigation. Teachers continue to hold no model permissions; every check is
assignment-based and centralized in `core.authorization`. The Teachers group
remains the definition of "is a teacher".

### D12. No staff profile record yet

FROZEN: Keep teachers as Users (first/last name, email) with no Staff/HR
model. A staff directory or HR record is a stop-and-return-to-planning
condition.

### D13. Assignment workflows for administrators

FROZEN: An administrator can see, per Academic Year, every Section with
its class teacher and every offering/Section with its subject teacher, find
gaps (unassigned Sections or offering/Sections), view one teacher's full
load, and copy a previous year's assignments into a new year as a reviewed,
explicit action (only where the same Class/Grade, Section name and Subject
exist).

FROZEN note: copy is preview-first and conservative. Nothing is written
before the administrator confirms the preview. Matches are never guessed:
inactive or non-teacher logins, ambiguous Sections or Subjects, missing
equivalents and already-assigned targets are skipped, and every skip is
reported with its reason. Confirming twice creates nothing new.

### D14. Deactivation

FROZEN: Deactivating a login or removing it from the Teachers group
removes all teacher access immediately (already true for results). The
administrator overview flags assignments held by inactive or non-teacher
logins so they can be reassigned. No assignment rows are deleted
automatically.

FROZEN note: losing teacher status removes access immediately but never
deletes, ends or rewrites existing class or subject teacher assignments;
assignment history is preserved.

---

# 4. Core domain additions

## SectionClassTeacher

- teacher (User, PROTECT)
- academic_year (PROTECT)
- section (PROTECT)
- start_date, end_date (nullable)
- created_at, updated_at

Rules:

- start/end inside the Academic Year; end ≥ start
- no overlapping ranges for one Section and Academic Year
- teacher must be an active Teachers-group login at creation
- `section` must belong to a Class/Grade in use that Academic Year
- once effective, or once any record depends on it, a row is ended, not
  deleted (D3); only a not-yet-effective row without dependents may be deleted

## No change to existing models

`AttendanceRegister`, `AttendanceEntry`, `AttendanceCorrection`,
`AssessmentTeacherAssignment`, `StudentResult` and `TermRemark` keep their
schemas. Phase 5 adds authorization paths, not new record kinds.

---

# 5. Authorization (centralized in `core.authorization`)

New helpers:

- `class_teacher_on(user, section, on_date)` → bool
- `class_teacher_sections(user, on_date)` → Sections
- `can_take_attendance(user, register_or_section, on_date)` → bool
  (administrator permission, or class teacher on that date and D5 window)
- `teacher_student_scope(user, on_date)` → Students visible to the teacher
- `can_view_student_as_teacher(user, student)` / `guardian_contact_visible`
- `can_write_term_remarks` updated per D10

Every new view is covered by the app-wide authorization sweep test.

---

# 6. Teacher home page

`my/` shows, for today:

- attendance: each Section the user is class teacher of, with NOT TAKEN /
  DRAFT / SUBMITTED / not an instructional day
- assessments: DRAFT assessments in their offering/Sections whose entry is
  open and roster incomplete
- remarks: Terms ending soon or ended with remarks still missing for their
  Section

Constant query count regardless of the number of assignments.

---

# Gate-by-Gate Implementation Plan

Each gate: build, full suite on SQLite and PostgreSQL, `check`,
`makemigrations --check`, Ruff, then commit, PR, merge.

## Gate 0 — Freeze Phase 5 source of truth

- ADR 0011 — Phase 5 class teacher and teacher workflow model (D1–D3,
  D11–D14)
- ADR 0012 — Phase 5 teacher attendance and student access authorization
  (D4–D10)
- Update REQUIREMENTS (Phase 5 scope/out of scope), DOMAIN_MODEL, ROADMAP;
  ADR 0007 and ADR 0010 consequence notes
- No code

## Gate 1 — Class teacher assignment

- `SectionClassTeacher` model, constraints (incl. PostgreSQL-safe overlap
  check under row lock), migrations, permissions for administrators
- Administrator UI: assign, end, replace a class teacher per Section/year
- Helpers: `class_teacher_on`, `class_teacher_sections`
- Tests: overlap, dates in year, inactive/non-teacher rejected, history query,
  effective rows cannot be deleted through normal workflows (D3)

## Gate 2 — Teacher home page

- `my/` home with the three panels; teacher nav landing moves here
- Query-count test; non-teachers get 403; administrators unaffected

## Gate 3 — Teacher attendance capture

- Teacher register open/capture/submit for their Section today (D4, D5)
- Reuse register model methods; actor recorded; DRAFT editable by teacher
  until submit; SUBMITTED read-only to teachers (D7)
- Tests: wrong Section, wrong date, non-instructional day, ended class
  teacher, replaced mid-year, admin still works, concurrent submit

## Gate 4 — Teacher attendance views

- Read-only views of their Section's registers and monthly summary, limited
  to dates they were class teacher (D9)
- Tests: history boundary at hand-over date

## Gate 5 — Limited student access

- `my/students/` list (today's scope) and teacher student profile (D8)
- Guardian contact shown only to the class teacher
- Tests: out-of-scope Student 404/403, transferred Student drops out of the
  old teacher's list, field-level visibility

## Gate 6 — Teacher result views and Term remarks ownership

- Read-only finalized results for the teacher's subjects/Sections; class
  teacher sees the Section's Term report cards
- Term remarks moved to the class teacher (D10)
- Tests: remark permission change, subject teacher denied, history kept

## Gate 7 — Administrator assignment workflows

- Per-year assignment overview with gaps; per-teacher load page
- Copy previous year's assignments: preview first, explicit confirm,
  idempotent; never guesses matches; skips inactive/non-teacher logins,
  ambiguous or missing Sections/Subjects and already-assigned targets, and
  reports every skip with its reason (D13)
- Inactive/non-teacher assignment flags (D14)

## Gate 8 — Integration hardening

- End-to-end journey: admin assigns class and subject teachers → teacher
  home → teacher submits today's attendance → admin corrects it → teacher
  enters marks → admin finalizes → class teacher writes remark → class
  teacher replaced mid-year → old teacher loses access, history intact →
  next year copy of assignments
- Authorization sweep, query counts, transactions, migration review
- Deletion protection for historically relevant SectionClassTeacher rows at
  application and database level (D3); assignment history untouched by
  deactivation (D14)

## Gate 9 — Documentation closeout

- README, ROADMAP (Phase 5 complete), REQUIREMENTS, DOMAIN_MODEL, ADRs,
  plan status table; tag `phase-5-complete`

---

# Stop-and-return-to-planning conditions

- timetable or period-level attendance
- substitute/cover assignment (D6)
- staff profile, HR, leave or staff attendance (D12)
- teacher-to-guardian communication
- teachers editing student or guardian data
- teacher correction of submitted attendance or finalized results
- more than one simultaneous class teacher per Section
- attendance windows other than D5

# Phase 5 completion principle

Phase 5 is complete when a teacher can log in, see today's work, take and
submit their own Section's attendance, enter marks, write remarks and look up
their own Students — and cannot see or change anything outside their dated
assignments — while every historical record still shows who did what, when.
