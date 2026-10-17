# 0019. Subject name captured at assessment finalization

## Status

Proposed (2026-10-17, completed-scope repair R12).

Clarifies ADR 0009 (Subject identity) and keeps ADR 0014 (published content is
never silently changed) true when a Subject is renamed. Does not change any
frozen decision.

## Context

ADR 0009 says historical records must not depend on renaming a Subject. Today
that holds for identity only: assessments point at the Subject row through
their offering, so a rename never breaks a reference. The displayed name is
read live (`offering.subject.name`) by every admin sheet, Student history,
Subject/Section report, term report card and teacher view.

Guardian publication already snapshots `TermPublicationEntry.subject_label`.
But the fingerprint that guards a published card is recomputed from live
values, and `entry_values` reads the live Subject name. Renaming a Subject
therefore changes the live fingerprint of every publication that includes it.
`guardian_visible` becomes false, the published card disappears for guardians,
and no version is marked STALE, so nobody is told. This contradicts ADR 0014.

Staging check (read-only, 2026-10-17): 3 Subjects, 3 finalized Assessments,
3 PUBLISHED publications, all fingerprint scheme 1. No stored entry label
differs from the live name, and no Subject was edited after its first
finalization. No legacy rename needs recovery on staging. This says nothing
about other databases; the backfill below handles that case.

## Decision

- **D1 Identity unchanged.** History references the Subject by foreign key.
  Renaming stays allowed and keeps every offering and assessment attached.
- **D2 Capture at finalization.** `Assessment.subject_label` records the
  Subject name at the moment of finalization, in the same transaction that
  sets the other finalization fields. It is empty while DRAFT, non-empty once
  FINALIZED (database constraint), and never changes afterwards, including
  through result corrections.
- **D3 One display rule.** `Assessment.subject_display` returns
  `subject_label` for a FINALIZED assessment and the live Subject name for a
  DRAFT. Every screen, report and document that shows a Subject name for an
  assessment uses it. Drafts follow a rename; finalized work does not.
- **D4 Reports.** Reports display and sort by `subject_display`. The term
  report card groups by Subject identity plus that display name
  (`SubjectGroup(subject, name)`), so a Subject renamed mid-year appears as
  one heading per name its assessments were finalized with, ordered by name.
- **D5 Fingerprint keeps released labels.** The subject label stays part of
  the fingerprinted released content. Only its source changes:
  - scheme 1 publications (existing): verify live result and remark values, but
    take the label from the stored `TermPublicationEntry.subject_label`. Old
    cards stay visible after a rename and real result or remark changes are
    still detected. Their stored fingerprints remain valid unchanged.
  - scheme 2 publications (new): the label is `Assessment.subject_label`.
    The entry snapshot is written from it. Scheme 2 is used for every new
    version.
  - `live_fingerprint` and `guardian_visible_many` choose the scheme from the
    stored `fingerprint_scheme`.
- **D6 Legacy backfill.** A data migration fills `subject_label` for existing
  FINALIZED assessments from the earliest published entry label for one of its
  results, else from the current Subject name. The migration reports how many
  rows used each source. Recovery of a rename that happened before this
  migration is possible only where a published entry exists.
  **Legacy recovery assumption:** if an assessment was published under several
  different labels, the earliest published entry wins, ordered by publication
  `published_at`, then publication id, then entry id, so the result is
  deterministic. History is not inferred or corrected: later labels are
  neither merged nor reconciled, and the migration reports how many
  assessments had conflicting labels so an administrator can review them.
- **D7 Scope.** Subject names only. Class/Grade, Section, Term and Academic
  Year label behavior outside publication snapshots is logged as follow-up
  audit items, not repaired here.

## Alternatives rejected

- Remove `subject_label` from the fingerprint: released labels are released
  content and must stay protected.
- Block renaming once history exists: forces a duplicate Subject to fix a typo
  and splits the identity.
- A dated Subject-name history table: heavier than needed; revisit only if a
  rename audit trail is required.

## Consequences

- One additive column, one constraint, one data migration. The new column is
  safe to deploy before the code that reads it; readers fall back to the live
  name when it is empty.
- The Subject form should say that a rename applies to draft and future
  assessments only.
- Fingerprint scheme 2 exists beside scheme 1; scheme 1 code is retained for
  existing publications.
