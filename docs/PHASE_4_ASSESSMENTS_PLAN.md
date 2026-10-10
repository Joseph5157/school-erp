# Phase 4 — Assessments and Results

## Status

COMPLETE — all gates implemented and merged; decisions recorded in ADR 0009
(assessment and results model) and ADR 0010 (assessment-scoped teacher
authorization). Tag: `phase-4-complete`.

| Gate | Scope | PR |
| --- | --- | --- |
| 0 | Freeze Phase 4 source of truth | #12 |
| 1 | Academic Terms and Subjects | #13 |
| 2 | Minimal assessment teacher assignment | #14 |
| 3 | Grading scale foundation | #15 |
| 4 | Assessment planning | #16 |
| 5 | Date-effective roster and DRAFT result capture | #17 |
| 6 | Finalization | #18 |
| 7 | Audited corrections | #19 |
| 8 | Result UI and Term remarks | #20 |
| 9 | Reporting and Term report cards | #21 |
| 10 | Integration hardening | #22 |
| 11 | Documentation closeout | this PR |

Closeout verification: 674 tests pass on SQLite and PostgreSQL 16;
`manage.py check` and `makemigrations --check` clean; Ruff clean; the
app-wide authorization sweep covers every Phase 4 URL. No stop-and-return-to-
planning condition arose. No Phase 4 blocker is open.

Phase 4 builds a small, historically correct assessment and result system for the single-school ERP.

The design takes inspiration from:

- Frappe Education for separation of assessment planning and results
- Gibbon for teacher workflow and historical student context
- Fedena for draft/finalized marks workflows
- openSIS for explicit academic terms and reporting periods

The project intentionally does not copy the full complexity of those systems.

---

# 1. Phase 4 goals

Phase 4 must support:

- Subjects
- Academic-Year-aware subject offerings
- Terms
- minimal teacher-to-subject/section assignment
- subject assessments
- date-valid student rosters
- DRAFT result entry
- MARKED / ABSENT student results
- administrator finalization
- audited post-finalization corrections
- reusable grading scales
- derived grades
- optional assessment pass marks
- student result history
- class/section result sheets
- simple Term report cards
- optional Term teacher remarks

The system must preserve historical academic context.

---

# 2. Explicitly out of scope

Initial Phase 4 will not include:

- GPA
- class rank / position
- percentile ranking
- complex assessment weighting
- category weighting
- rubrics
- outcomes / competency frameworks
- homework gradebooks
- online examinations
- question banks
- hall tickets
- exam seating
- timetable integration
- automatic promotion
- transcript engine
- board-specific result rules
- parent/student result publication
- co-scholastic grading
- teacher workload management
- substitute-teacher workflows

These require separate planning if later needed.

---

# 3. Core domain model

## Subject

`Subject` is the long-lived identity of an academic subject.

Examples:

- Mathematics
- English
- Science
- Social Studies

A Subject does not permanently belong to a particular Grade or Academic Year.

Suggested fields:

- name
- code, optional
- active/inactive state

Historical records should not depend on renaming the Subject.

---

## AcademicSubjectOffering

Represents a Subject being taught to a Grade during a particular Academic Year.

Conceptually:

Academic Year\
\+ Class/Grade\
\+ Subject

Examples:

2026–27 + Grade 6 + Mathematics

The offering may apply to all Sections of that Grade or may be restricted to specific Sections.

This prevents assessments from using free-text subject names.

Assessments reference an AcademicSubjectOffering.

---

## AcademicTerm

Each Academic Year contains explicitly ordered Terms.

Example:

Academic Year 2026–27

→ Term 1\
→ Term 2\
→ Term 3

Suggested fields:

- academic_year
- name
- start_date
- end_date
- display_order

Rules:

- Term dates must fall inside the Academic Year.
- Terms must have valid chronological dates.
- Ordering is explicit rather than inferred from names.

Nested Semester → Quarter hierarchies are not part of Phase 4.

---

## AssessmentTeacherAssignment

Phase 4 introduces only the minimum teacher assignment required for secure result entry.

Conceptually:

Teacher\
\+ AcademicSubjectOffering\
\+ Section

Example:

Teacher Rao\
→ Grade 6 Mathematics\
→ Section A\
→ 2026–27

Purpose:

- determine which teacher may enter DRAFT results
- scope assessment access

It does not represent:

- timetable periods
- staff workload
- substitutions
- HR assignment
- payroll

Broader teacher workflows remain Phase 5.

---

## GradingScale

A reusable grading policy.

Example:

2026–27 Standard Scale

with boundaries such as:

90–100 → A1\
80–89.99 → A2\
etc.

The exact labels and boundaries are configuration.

Grading scales may be assigned at an appropriate Academic Year / Grade scope.

Numeric marks remain the canonical result.

Grades are derived from marks and the applicable scale.

Finalized historical results must not silently change merely because a grading scale is edited later.

The implementation must therefore preserve or version the grading context used for finalized results.

---

## Assessment

An Assessment represents exactly one Subject assessment.

Example:

Term 1\
→ Grade 6 Mathematics\
→ Section A\
→ Unit Test 1\
→ 15 July 2026\
→ Maximum marks 20

Suggested context:

- AcademicTerm
- AcademicSubjectOffering
- Section scope
- name
- assessment_date
- maximum_marks
- optional pass_mark
- lifecycle state

An Assessment does not represent an entire multi-subject examination.

If future requirements need:

Midterm Examination
→ Mathematics
→ English
→ Science

a lightweight grouping concept such as `ExamSeries` may be added later without changing the core Assessment model.

### Assessment lifecycle

DRAFT\
→ FINALIZED

DRAFT means marks entry is still operationally editable.

FINALIZED means the assessment has become an accepted historical academic record.

---

# 4. Assessment rules

The assessment date must:

- fall within its Academic Year
- fall within its Academic Term
- not allow result entry before the assessment date

Future Assessments may be created for planning.

Future result entry is prohibited.

Once any StudentResult exists:

- maximum marks becomes immutable
- subject context becomes immutable
- Grade/Section/Term/date context should not be casually rewritten
- Assessment cannot be normally deleted

Before results exist, an unused Assessment may be deleted.

---

# 5. Student assessment roster

Assessment eligibility is derived from `AcademicEnrollment`.

For assessment date D, an eligible student is one whose AcademicEnrollment:

- is effective on D
- belongs to the relevant Academic Year
- belongs to the Assessment's Grade
- belongs to the Assessment's Section scope

The roster must not use only the student's current placement.

A later transfer must never rewrite an older assessment roster or result.

Each StudentResult references the applicable AcademicEnrollment.

---

# 6. StudentResult

A StudentResult represents one eligible AcademicEnrollment's result in one Assessment.

Exactly one result is allowed per:

Assessment + AcademicEnrollment

### Result state

Initial Phase 4 supports exactly:

- MARKED
- ABSENT

### MARKED

Requires:

- numeric score
- score >= 0
- score <= assessment maximum marks

### ABSENT

Requires:

- no numeric score

ABSENT must never be represented as numeric zero.

Zero marks is a valid MARKED score and is semantically different from absence.

---

# 7. Assessment completeness

A DRAFT Assessment may have:

- incomplete roster
- missing results
- partially entered marks

Before FINALIZED:

every eligible AcademicEnrollment must have exactly one StudentResult.

That result must be:

- MARKED, or
- ABSENT

Missing result means:

**result entry incomplete**

It must never automatically mean ABSENT.

---

# 8. Pass/fail

An Assessment may define an optional pass mark.

If no pass mark is configured:

- no assessment-level pass/fail is derived

If configured:

MARKED score >= pass mark\
→ PASS

MARKED score < pass mark\
→ FAIL

ABSENT remains ABSENT rather than being silently converted to FAIL.

Pass/fail should normally be derived rather than independently editable.

---

# 9. Marks and grading philosophy

Numeric marks are the canonical academic result.

Example:

17 / 20

Derived:

85%

Then applicable grading scale may derive:

A

The grade must not become a second manually editable source of truth.

Initial Phase 4 contains no assessment weighting.

Therefore:

- Unit Test 1
- Unit Test 2
- Midterm

remain distinct assessments.

The system must not invent weighted Term percentages until a weighting policy is explicitly approved.

---

# 10. Teacher and administrator responsibilities

## Teacher

For assigned Subject/Section only:

- view relevant Assessments
- view date-valid student roster
- enter DRAFT marks
- mark student ABSENT
- modify DRAFT results

Teacher may not:

- finalize official results
- silently modify FINALIZED results
- enter results for unassigned Subject/Section

## Administrator

May:

- configure academic assessment structures
- create Assessments
- review result completeness
- FINALIZE Assessments
- perform audited corrections after finalization

---

# 11. Finalization

Only an authorized administrator finalizes an Assessment.

Finalization requires:

- assessment date has occurred
- every eligible student has exactly one valid result
- no ineligible AcademicEnrollment result exists
- all numeric scores are valid
- result context is internally consistent

Finalization should record at least:

- finalized_by
- finalized_at

After finalization, normal marks editing stops.

---

# 12. Corrections

FINALIZED results are historical records.

A correction must not silently overwrite accepted history.

An authorized administrator may correct a finalized result.

Correction history records:

- previous result state
- previous score where applicable
- new result state
- new score where applicable
- administrator
- timestamp
- required reason

Examples:

MARKED 17\
→ MARKED 18

or:

ABSENT\
→ MARKED 15

The current accepted StudentResult may change, but correction history remains immutable.

Repeated corrections preserve the entire sequence.

---

# 13. Term teacher remark

Phase 4 supports one optional teacher remark per Student per Term.

This is separate from:

- numeric marks
- grades
- assessment results

Example:

“Shows strong improvement in Mathematics and Science.”

The remark may be shown on the Term report card.

It should not influence calculations.

---

# 14. Reporting

Initial Phase 4 reports:

1. Assessment result sheet
2. Student result history
3. Subject/Section result view
4. Term student report card

Term report card may show:

- Subject
- individual Assessments
- marks
- maximum marks
- percentage where valid
- derived grade
- ABSENT status
- pass/fail where configured
- optional Term teacher remark

Report cards are generated views of canonical results.

They must not duplicate marks into a separate independent source of truth.

No ranking is included.

No complex weighting is included.

---

# 15. Historical integrity

The following principle is FROZEN:

Assessment history belongs to the academic context that was true at the time.

Therefore:

- transfers never rewrite old results
- Subject offerings are Academic-Year-aware
- results reference historical AcademicEnrollment
- finalized results cannot be silently edited
- grading-policy changes must not silently rewrite finalized historical grades
- deletion is restricted once historical results depend on a record

---

# 16. Phase 4 authorization

Phase 4 introduces scoped teacher mutation for DRAFT results.

Authorization must ensure:

- administrator controls configuration and finalization
- teacher access is limited to assigned Subject/Section
- teacher cannot access unrelated assessment mutation workflows
- finalized corrections require administrator authorization
- protected academic result reads respect role boundaries

Parent/Guardian and Student access remains deferred.

---

# Gate-by-Gate Implementation Plan

## Gate 0 — Freeze Phase 4 source of truth

### Goal

Update documentation before implementation.

Create assessment ADR(s) freezing:

- Subject and AcademicSubjectOffering
- AcademicTerm
- assessment-only teacher assignment
- subject-level Assessment
- date-effective roster
- MARKED / ABSENT semantics
- numeric marks as canonical
- reusable grading scales
- DRAFT → FINALIZED
- admin finalization
- audited corrections
- report-card philosophy
- historical integrity rules

Update:

- REQUIREMENTS.md
- DOMAIN_MODEL.md
- ROADMAP.md
- future-phase planning documentation

Explicitly reconcile the old Phase 5 assumption that all teacher assignments were deferred.

Only the minimum assessment assignment moves into Phase 4.

### Acceptance

Documentation agrees before code changes.

STOP and review.

---

## Gate 1 — Academic Terms and Subjects

### Goal

Create the academic structures assessments depend on.

Implement:

- Subject
- AcademicTerm
- AcademicSubjectOffering
- Section applicability

Required constraints:

- Term inside Academic Year
- valid Term date range
- appropriate uniqueness
- offering Grade/Academic-Year consistency
- no contradictory Section scope

Provide basic administrator configuration UI.

### Acceptance

The system can answer:

> Which Subjects are offered to this Grade/Section in this Academic Year and Term context?

STOP and review.

---

## Gate 2 — Minimal assessment teacher assignment

### Goal

Establish safe ownership for teacher marks entry.

Implement:

AssessmentTeacherAssignment

linking:

- Teacher/User identity
- AcademicSubjectOffering
- Section

Do not build broader Phase 5 teacher workspace.

Add scoped authorization primitives needed by later gates.

### Acceptance

The system can reliably answer:

> Is this teacher authorized to enter results for this Subject/Section?

STOP and review.

---

## Gate 3 — Grading scale foundation

### Goal

Provide reusable grading configuration.

Implement:

- GradingScale
- GradeBoundary / equivalent
- Academic Year / Grade applicability

Validate:

- non-overlapping ranges
- complete/allowed numeric range policy
- deterministic grade resolution

Do not yet build GPA or weighting.

Define safe historical/version behavior before finalized results begin depending on scales.

### Acceptance

A numeric percentage can deterministically resolve to the appropriate configured grade.

STOP and review.

---

## Gate 4 — Assessment planning

### Goal

Create subject Assessments.

Implement:

- Assessment
- DRAFT lifecycle
- Term
- Subject offering
- Section
- assessment date
- maximum marks
- optional pass mark

Rules:

- date inside Term and Academic Year
- pass mark cannot exceed maximum marks
- future planning allowed
- result entry before assessment date prohibited
- context/max marks lock once results exist
- deletion allowed only while unused

### Acceptance

Administrators can safely plan future and current assessments.

STOP and review.

---

## Gate 5 — Date-effective roster and DRAFT result capture

### Goal

Allow teachers to enter marks safely.

Implement:

- StudentResult
- MARKED / ABSENT
- result references AcademicEnrollment
- date-effective roster
- teacher-scoped DRAFT entry

Rules:

MARKED:
- score required
- 0 <= score <= maximum marks

ABSENT:
- score must be empty

Roster eligibility comes from AcademicEnrollment effective on assessment date.

Teachers may edit only their assigned DRAFT Assessments.

### Acceptance

Transfer history remains correct and incomplete DRAFT marks entry is supported.

STOP and review.

---

## Gate 6 — Finalization

### Goal

Turn completed marks into official results.

Administrator-only operation:

DRAFT → FINALIZED

Require:

- complete effective roster
- exactly one result per eligible enrollment
- no ineligible results
- valid marks/status combinations
- assessment date reached

Record:

- finalized_by
- finalized_at

Prevent normal editing after finalization.

### Acceptance

The system distinguishes unfinished marks entry from accepted official results.

STOP and review.

---

## Gate 7 — Audited corrections

### Goal

Allow legitimate changes without destroying history.

Implement administrator correction workflow.

Correction records:

- previous state/value
- new state/value
- actor
- timestamp
- reason

Support:

MARKED → MARKED\
MARKED → ABSENT\
ABSENT → MARKED

Reject:

- no-op correction
- invalid score
- unauthorized correction

Do not reopen the whole Assessment merely to fix one student.

### Acceptance

Finalized results are correctable and auditable.

STOP and review.

---

## Gate 8 — Result UI and Term remarks

### Goal

Make the operational workflow usable.

Teacher workflow:

Assessment\
→ roster\
→ bulk marks entry\
→ save DRAFT

Administrator workflow:

review\
→ completeness validation\
→ FINALIZE\
→ correction when required

Add optional Term teacher remark workflow.

Use Django Templates + Bootstrap + minimal JavaScript.

### Acceptance

Everyday result entry is practical without weakening domain rules.

STOP and review.

---

## Gate 9 — Reporting and Term report cards

### Goal

Provide trustworthy academic output.

Implement:

- Assessment result sheet
- Student result history
- Subject/Section results
- simple Term report card

Use:

- accepted finalized results
- correct historical AcademicEnrollment
- grading scale applicable to finalized context
- current accepted value after corrections

Do not include:

- rank
- GPA
- weighting
- promotion
- transcript logic

### Acceptance

All reports derive from the same canonical result data.

STOP and review.

---

## Gate 10 — Integration hardening

### Goal

Test the full Phase 4 journey.

End-to-end scenario:

Academic Year\
→ Terms\
→ Subjects\
→ Subject offering\
→ Teacher assignment\
→ Assessment\
→ historical date-valid roster\
→ teacher enters DRAFT marks\
→ one student ABSENT\
→ incomplete finalization rejected\
→ complete roster\
→ administrator FINALIZES\
→ correction performed\
→ grading/report updated\
→ student later transfers Section\
→ old result remains under historical placement\
→ Term report card remains correct

Hardening:

- database constraints
- direct ORM misuse tests
- authorization tests
- transaction safety
- duplicate/conflict paths
- delete protection
- query efficiency
- migration review
- full test suite
- Django check
- Ruff
- deployment-sensitive checks

STOP and review.

---

## Gate 11 — Documentation closeout

Update:

- README
- ROADMAP
- REQUIREMENTS
- DOMAIN_MODEL
- relevant ADRs

Verify:

- all gates merged
- no unresolved Phase 4 blocker
- full suite clean
- migrations clean
- authorization reviewed

Then create annotated tag:

`phase-4-complete`

---

# Stop-and-return-to-planning conditions

Implementation must stop rather than invent new behavior if a real requirement emerges for:

- GPA
- rank
- weighted assessments
- assessment categories
- rubrics
- competency/outcome grading
- elective StudentSubjectEnrollment
- students taking subjects outside their Grade/Section offering
- multi-subject ExamSeries becoming operationally necessary
- retests/supplementary exams with special replacement rules
- grace marks
- moderation
- external/board examinations
- transcript rules
- automatic promotion
- parent/student publication workflow
- co-scholastic grading
- timetable integration
- multiple teachers jointly owning one result workflow in ways not covered by the minimal assignment model

Those require explicit domain decisions before implementation continues.

---

# Phase 4 completion principle

Phase 4 is complete when the ERP can reliably perform:

Configure Term + Subjects\
→ assign Subject to Grade/Section\
→ assign teacher\
→ create Assessment\
→ derive correct historical roster\
→ teacher enters MARKED/ABSENT DRAFT results\
→ administrator finalizes complete results\
→ administrator corrects an error with audit history\
→ generate trustworthy student and Term reports

without rewriting academic history.