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
- An existing Guardian is reused only when both the normalized phone number
  and the normalized name match, so siblings share one record. The same
  phone with a different name produces a warning and a separate Guardian,
  because two parents can share a phone. Within one file, a Guardian with no
  phone is identified by email plus name. A Guardian with neither phone nor
  email produces a warning and is never matched. Same student name plus date
  of birth is flagged for human review. Nothing is auto-merged. (Amended
  2026-10-17; see below.)
- Safety: file size, row and sheet limits; read-only parsing; a cell
  containing a formula is rejected with a row-level error (paste values
  only); macros are not read and .xlsm is rejected. Exported files neutralize
  cells beginning with =, +, - or @. (Amended 2026-10-17; see below.)
- `ImportBatch` and per-row results are retained for audit. An import records
  a security event.

## Consequences

- Import is slower and more complex than a raw load, but preserves ADR 0002.
- Messy real data will surface duplicates and invalid dates; the preview is
  the place to resolve them.
- Needs a schema change to mark imported applicants (reviewed migration).

## Amendments

- **2026-10-17 - Guardian matching and formulas.** The original text said
  Guardians were matched by phone alone and that formulas were ignored. The
  implemented and accepted behaviour is stricter: matching uses normalized
  phone plus normalized name (core/imports.py), and formulas are rejected
  rather than ignored. This amendment records that behaviour so the code is
  not "corrected" back to phone-only matching, which would merge different
  parents who share a phone.
- **2026-10-17 - Guardians are optional.** A student row may list 0, 1 or 2
  guardians, matching the Phase 1 lifecycle in which a Student can exist with
  none. A guardian whose cells are all empty is skipped; if any cell of a
  guardian is filled, its name and relationship are required. A student with
  no guardian imports with a warning (no portal access or messages until one
  is added), which must be reviewed before the batch is committed.
- **2026-10-17 - Pending-batch retention.** Parsed rows in a pending batch
  are cleared after 24 hours. Expiry runs when import pages are used and
  through the `expire_import_batches` management command, which must be run
  on a schedule in production.

## Related

ADR 0002, ADR 0001; Phase 1 requirements (admission and progression).
