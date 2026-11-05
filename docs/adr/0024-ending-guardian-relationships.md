# ADR 0024: Ending a Student-Guardian relationship

Status: accepted, 2026-11-05.

## Context
A guardian linked to the wrong student could only have the relationship type changed. Access to a child's data follows the relationship, so a mistaken link needs a controlled, recorded way to end.

## Decision
- **Ended, not deleted:** `StudentGuardian` gains `ended_at`, `ended_by` and `end_reason`. A check constraint requires all three together, and a reason is required.
- **Access goes with it:** `end_relationship` revokes the active access grant for that child in the same transaction. The guardian's login and access to other children do not change.
- **History is fixed:** database triggers refuse UPDATE and DELETE of an ended row.
- **Linking again:** creates a new row with no access, so access must be granted again on purpose. The one-link rule now covers current relationships only.
- **Permissions:** both `change_studentguardian` and `change_guardianstudentaccess`.

## Consequences
- Any code that treats a relationship as still in force must use `StudentGuardian.objects.current()`. Portal data, notices and alerts read active grants, so revoking the grant closes them.
- Applicant-side relationships are unchanged. Removing a mistaken link before progression is not covered here.
