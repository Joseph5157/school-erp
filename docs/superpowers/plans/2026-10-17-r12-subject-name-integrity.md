# R12 — Subject historical-name integrity: implementation plan

Design: ADR 0019. Implemented in R12 PR #78.

## Staging findings (read-only, 2026-10-17)

3 Subjects, 3 finalized Assessments, 3 PUBLISHED publications (all scheme 1,
0 STALE/SUPERSEDED/WITHDRAWN). 0 entries whose stored label differs from the
live Subject name; 0 Subjects edited after their first finalization. No legacy
recovery is needed on staging; the backfill still covers other databases.

## Known bug being fixed

Renaming a Subject changes `entry_values()["subject_label"]`, so
`live_fingerprint()` no longer matches the stored fingerprint and
`guardian_visible()` hides a PUBLISHED card with no STALE marker.

## Steps (TDD: failing test first in each step)

1. **Reproduce.** Test: publish a Term, rename the Subject, assert the portal
   still shows the card. Fails today.
2. **Model + migration.** `Assessment.subject_label` (CharField 100, blank,
   default ""). Check constraint: DRAFT ⇒ empty, FINALIZED ⇒ non-empty.
   Add `subject_display` property. Include `subject_label` in the guard that
   rejects edits to a finalized assessment.
3. **Data migration.** Backfill FINALIZED rows: earliest
   `TermPublicationEntry.subject_label` for the assessment's results, else the
   current Subject name. Legacy recovery assumption (ADR 0019 D6): with several
   different published labels, the earliest entry wins (`published_at`, then
   publication id, then entry id); history is not inferred or corrected. Print
   counts per source, including how many had conflicting labels. Reversible
   (no-op reverse). Constraint is added after the backfill (0074 column, 0075
   backfill, 0076 constraint).
4. **Finalize path.** Set `subject_label` from the live name inside the existing
   finalization transaction. Test rename-after-finalize leaves it unchanged,
   and that a result correction does not touch it.
5. **Publication.** `entry_values` takes the label source by scheme. Scheme 1:
   stored entry label. Scheme 2: `assessment.subject_label`. New publications
   write scheme 2; `live_fingerprint` and `guardian_visible_many` read
   `publication.fingerprint_scheme`. Tests: old scheme-1 card survives a
   rename; a real score change still marks it not visible; scheme-2 card
   survives a rename.
6. **Reads.** Replace `...subject.name` with `subject_display` in the admin
   templates, teacher templates, `assessment_reports.py`, `views.py`
   (ordering via an annotation: `subject_label` if non-empty else live name)
   and `assignments.py` where it describes an assessment. Offering/duty
   labels with no assessment (`my_gradebook` header, assignment pages) keep
   the live name.
7. **Report grouping.** `term_report_card` groups by Subject id and carries the
   display label; adjust `report_term_report_card.html`.
8. **Subject form.** Help text on the name field: a rename applies to draft and
   future assessments only.
9. **Matrix test.** Rename a Subject after finalize+publish and assert, for
   each output (sheet, Student history, Subject/Section report, term report,
   teacher views, preview, portal card, PDF): finalized shows the old name,
   a draft shows the new name.
10. **Docs.** Flip ADR 0019 to Accepted on merge; add follow-up audit item for
    Class/Grade, Section, Term and Academic Year labels.

## Rollout

Single deploy; pre-deploy `migrate` runs the column, backfill and constraint.
Readers fall back to the live name for any blank label, so a partially applied
state cannot blank a screen. Verify on staging with the same read-only script,
then rename a staging Subject and confirm the guardian card stays visible
(rename back afterwards).

## Out of scope

Class/Grade, Section, Term, Academic Year label drift; a rename audit trail.

## Follow-up audit items (not part of R12)

- Class/Grade, Section, Term and Academic Year names are read live outside the
  publication snapshots (`class_grade_label`, `section_label`, `term_label`,
  `academic_year_label`). Audit the same rename question for each, per ADR 0019
  D7.
