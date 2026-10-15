# 0017. Phase 7 bulk import through applicant progression

## Status

Accepted (2026-10-15, Phase 7 planning PR #45) — FROZEN.
Planning: `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (decisions D9, D10).

## Context

Schools arrive with existing Excel records. A Student cannot exist without an
Applicant (one-to-one, ADR 0002), and Student creation happens only through
explicit progression (`Applicant.progress_to_student()`). A bulk loader that
wrote Student rows directly would bypass the lifecycle rules, constraints and
history the project depends on.

## Decision

- Import creates records only through the existing domain rules: Applicant,
  admission decision and `progress_to_student()`, then guardian links and
  academic enrollment. No direct writes that bypass them.
- Imported applicants carry an explicit marker identifying the import batch
  (a "migrated" origin), so they are traceable and distinguishable.
- Scope of the first version: classes, sections, guardians, students,
  guardian links and academic enrollment. Historical attendance and marks are
  out of scope.
- Flow: upload, parse, validate (dry run), preview with row-level errors,
  explicit confirmation, then one atomic commit. The batch succeeds entirely
  or not at all.
- Guardians are matched by phone number so siblings share one record;
  same name plus date of birth is flagged for human review. Nothing is
  auto-merged.
- Safety: file size, row and sheet limits; read-only parsing; formulas and
  macros ignored; .xlsm rejected. Exported files neutralize cells beginning
  with =, +, - or @.
- `ImportBatch` and per-row results are retained for audit. An import records
  a security event.

## Consequences

- Import is slower and more complex than a raw load, but preserves ADR 0002.
- Messy real data will surface duplicates and invalid dates; the preview is
  the place to resolve them.
- Needs a schema change to mark imported applicants (reviewed migration).

## Related

ADR 0002, ADR 0001; Phase 1 requirements (admission and progression).
