# 0009. Phase 4 assessment and results model

## Status

Accepted — implemented in Phase 4 (tag `phase-4-complete`)

## Context

Phase 4 adds assessments and results to the single-school ERP. The design was
researched against Frappe Education (separation of assessment planning and
results), Gibbon (teacher workflow, historical student context), Fedena
(draft/finalized marks) and openSIS (explicit terms), and deliberately keeps a
much smaller scope. The full decision record and gate plan is
`docs/PHASE_4_ASSESSMENTS_PLAN.md`; this ADR freezes the decisions that code
must follow. It builds on the historical-context rules of ADR 0001 and the
effective-dated enrollment of ADR 0006.

## Decision

FROZEN:

Structure
- `Subject` is a long-lived subject identity (name, optional code,
  active/inactive). It does not belong to a Grade or Academic Year, and
  historical records must not depend on renaming it.
- `AcademicSubjectOffering` = Academic Year + Class/Grade + Subject. It applies
  to all Sections of that Grade or to explicitly listed Sections.
  Assessments reference an offering, never free-text subject names.
- `AcademicTerm` belongs to one Academic Year, has start/end dates inside that
  year and an explicit `display_order`. No nested semester/quarter hierarchy.

Assessments
- An `Assessment` is exactly one subject assessment: Term + offering + Section
  scope + name + assessment date + maximum marks + optional pass mark +
  lifecycle state. It is not a multi-subject examination; a later `ExamSeries`
  grouping may be added without changing this model.
- The assessment date falls within its Academic Year and its Term. Future
  assessments may be planned; result entry before the assessment date is
  prohibited.
- The pass mark, when set, cannot exceed maximum marks.
- Once any result exists, maximum marks and the subject/Grade/Section/Term/date
  context are locked and the assessment cannot be deleted. An unused
  assessment may be deleted.
- Lifecycle: DRAFT → FINALIZED. DRAFT is editable work in progress; FINALIZED
  is an accepted historical academic record.

Roster and results
- The roster is derived from AcademicEnrollment effective on the assessment
  date, in the relevant Academic Year, Grade and Section scope — never from
  current placement alone. A later transfer never rewrites an older roster or
  result.
- A `StudentResult` references the applicable AcademicEnrollment; at most one
  result per Assessment + AcademicEnrollment.
- Result states are exactly MARKED and ABSENT. MARKED requires a numeric
  score with 0 ≤ score ≤ maximum marks. ABSENT has no score. ABSENT is never
  represented as zero; zero is a valid MARKED score.
- A DRAFT assessment may be incomplete. A missing result means "result entry
  incomplete" and is never treated as ABSENT.

Marks, grades and pass/fail
- Numeric marks are the canonical result. Percentage and grade are derived;
  a grade is never a second, manually editable source of truth.
- `GradingScale` (with grade boundaries) is reusable configuration, applied at
  an Academic Year / Grade scope. Finalized results must not silently change
  when a scale is edited later; the grading context used for finalized
  results is preserved or versioned.
- Pass/fail is derived only when the assessment has a pass mark: score ≥ pass
  mark is PASS, below is FAIL. ABSENT stays ABSENT, never FAIL.
- No weighting: separate assessments remain separate; no weighted term
  percentage is invented.

Finalization and corrections
- Only an authorized administrator finalizes. Finalization requires the
  assessment date to have occurred, exactly one valid result per eligible
  enrollment, no result for an ineligible enrollment, and consistent context.
  It records `finalized_by` and `finalized_at`. Normal editing stops after it.
- Finalized results are corrected only by an authorized administrator through
  an immutable correction record: previous state and score, new state and
  score, administrator, timestamp, required reason. MARKED→MARKED,
  MARKED→ABSENT and ABSENT→MARKED are allowed; no-op and invalid corrections
  are rejected; repeated corrections preserve the full sequence. Correcting one
  student never reopens the whole assessment.

Remarks and reporting
- One optional teacher remark per Student per Term, separate from marks and
  grades and never used in calculations.
- Reports — assessment result sheet, Student result history, Subject/Section
  results, Term report card — are generated views of canonical results using
  finalized values after corrections and the grading context that applied.
  They never store a second copy of marks. No rank, GPA, weighting, promotion
  or transcript logic.

Historical integrity
- Assessment history belongs to the academic context that was true at the
  time: transfers never rewrite results, offerings are Academic-Year-aware,
  results reference historical enrollment, finalized results are never
  silently edited, grading-policy changes never silently rewrite finalized
  grades, and deletion is restricted once results depend on a record.

DECIDED (Gate 1):
- An offering's Section scope is an explicit link table: no linked Sections
  means all Sections of the Grade; linked Sections must belong to the Grade.
  Terms of one year may not overlap.

DECIDED (Gate 3):
- A GradingScale belongs to an Academic Year and applies to the Grades
  linked to it; each Year + Grade has at most one scale.
- Bands are "from minimum percentage upward -> label"; a percentage gets the
  band with the highest minimum at or below it, so bands cannot overlap and
  resolution is deterministic. A scale is complete once it has a band
  starting at 0%.
- Historical grading uses a frozen copy: at finalization the assessment
  stores the scale name and its bands, and every later grade for that
  assessment is resolved from that copy. Scales stay editable without
  rewriting finalized history.

OPEN (decided in the named gate, not here):
- Whether a correction may also be made while the assessment is still DRAFT
  (expected: no — DRAFT is edited normally, as in Phase 2 attendance).

## Consequences

- Phase 4 reuses the Phase 2 patterns: date-effective roster, DRAFT → final
  lifecycle, missing ≠ absent, audited corrections, reports derived from one
  canonical source.
- Requirements outside this model stop implementation and return to planning:
  GPA, rank, weighting, categories, rubrics, competency grading, elective
  student-subject enrollment, operational ExamSeries, retest/supplementary
  rules, grace marks, moderation, board exams, transcripts, automatic
  promotion, publication to parents/students, co-scholastic grading, timetable
  integration, and shared multi-teacher ownership of one result workflow.

## Related requirements/domain decisions

- `docs/PHASE_4_ASSESSMENTS_PLAN.md`
- `docs/REQUIREMENTS.md` — Phase 4
- `docs/DOMAIN_MODEL.md` — Assessment principle
- `docs/adr/0001-academic-structure-and-enrollment-history.md`
- `docs/adr/0006-academic-enrollment-effective-dating.md`
- `docs/adr/0010-phase-4-assessment-teacher-authorization.md`
