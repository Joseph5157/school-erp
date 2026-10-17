# R11 - Cross-phase repair hardening

Baseline: `4805a77` (R10 merged). Scope: integration evidence only. No new
behavior, no new model fields, no UI changes, no ADR.

R11 checks that repairs R1-R10 work together and that fixing one completed
phase did not damage another. The tests are in
`core/tests/test_cross_phase_hardening.py` and reuse the existing fixtures.

## Matrix (15 tests)

| Area | Tests |
|---|---|
| **R7 x assessments, results, publication** | A legal Term edit before finalization keeps the Assessment/Term association and the report query unchanged. After publication a Term-date edit is rejected and the report card and published page are unchanged. A boundary-day Assessment survives a legal edit and blocks a shrink past it. |
| **R8/R10 x teacher access** | After a subject-teacher handover the new owner sees the admission number and the former owner gets 403. A former owner gets no admission number from the list or from other Sections. A class teacher keeps the Student through subject handovers. |
| **R10 x Phase 5 workflows** | The dashboard marks panel moves to the current owner. Class-teacher attendance, remarks panel and remark rights ignore subject handovers. Class-teacher report cards stay open to the class teacher and closed to subject owners. |
| **R9 x Phases 1/6/7** | A guardianless imported Student is a normal Student; a Guardian added later through the ordinary StudentGuardian workflow gives no portal access until an account and a grant exist. Absence alerts follow the chain: no relationship, relationship only, and relationship plus account give no message; plus grant without opt-in gives a skipped message; plus opt-in gives a prepared message. A guardianless Student's published results reach no guardian and no notification. |
| **Permissions after migrations 0070-0073** | School Administrators hold the assignment, import and guardian permissions and Teachers hold none of them. Representative routes open for administrators and return 403 for teachers. Teachers cannot POST the end or delete actions. |

Not duplicated: copy-year after a subject handover is already covered by
`test_copy_takes_the_teacher_effective_on_the_last_day`.

## Findings

No production defects found. All 15 tests passed against unmodified `4805a77`
code. The only failures during development were two mistakes in the new tests
(a per-request CSRF token in a page comparison, and a second attendance
register for one Section and date); both were fixed in the tests.

## Verification

- 1640 PostgreSQL tests pass (1625 from R10 plus 15).
- Ruff clean.
- `makemigrations --check` clean.
- SQLite subset intentionally not rerun: PostgreSQL is the target database and
  no migration or model changed in R11.

## Known boundaries (unchanged)

- Subject-teacher overlap is enforced in the application under a lock, not by a
  database exclusion constraint; raw SQL or bulk updates can bypass it (ADR 0018).
- Surviving legacy assignment rows were backfilled to the Academic Year start;
  history deleted before R10 cannot be recovered (ADR 0018).
- A slot can legitimately have no current teacher after an assignment ends
  without a successor or when only a future one exists; the gap report shows it.
- Absence-alert idempotency is per guardian, student and day, so recording
  consent later does not re-create an absence alert already skipped that day.
