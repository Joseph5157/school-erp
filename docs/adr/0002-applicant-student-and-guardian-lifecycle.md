# 0002. Applicant, Student, and Guardian lifecycle

## Status

Accepted

## Context

`docs/DOMAIN_MODEL.md` and `docs/REQUIREMENTS.md` establish Applicant and Student as distinct concepts connected by an explicit progression workflow, and Guardian as a first-class, reusable record independent of both.

Phase 1 planning review identified an open modeling question left unresolved by the existing documentation: the exact shape of the Guardian relationship before a Student exists, and how a Guardian association recorded during Applicant handling carries forward once a Student is created. This ADR resolves that shape. It fixes the invariants involved and does not prescribe Django foreign-key direction beyond what is needed to express them.

## Decision

FROZEN:

- Applicant and Student are distinct domain identities with distinct lifecycles.
- Creating an Applicant never creates a Student.
- Only an Applicant with an ACCEPTED decision may explicitly progress to Student.
- One Applicant may produce at most one Student.
- The resulting Student must remain traceable to its source Applicant.
- The progression action must be protected against accidental duplicate Student creation from the same Applicant.
- Guardian is a reusable, first-class record, independent of both Applicant and Student.
- An Applicant may be associated with one or more Guardians before a Student exists, through an explicit ApplicantGuardian relationship carrying a `relationship_type`.
- A Student has its own, separate StudentGuardian relationship, also carrying a `relationship_type`.
- During a successful Applicant → Student progression, the approved ApplicantGuardian relationships are used to establish the corresponding StudentGuardian relationships for the new Student.
- ApplicantGuardian history must remain intact after Student creation — it is not deleted or replaced by the resulting StudentGuardian relationships.
- Shared Guardian records must be reused across siblings rather than duplicated merely because a Guardian relates to multiple Applicants or Students.

## Alternatives considered

- **A single, polymorphic "PersonGuardian" relationship** usable against either an Applicant or a Student. Rejected: blurs the Applicant/Student separation that is FROZEN elsewhere in the domain model, and complicates preserving ApplicantGuardian history intact once a Student exists.
- **Attach Guardian directly to Applicant only**, creating the Student–Guardian link fresh at progression time with no carry-forward. Rejected: would silently lose the `relationship_type` context recorded during applicant handling, requiring it to be re-entered.
- **Link Guardian one-to-one to a future authentication User at this stage.** Rejected: out of scope for Phase 1 (no Guardian portal), and would prematurely couple Guardian identity to authentication, which ADR 0004 keeps separate.

## Consequences

- Two distinct association records are needed — ApplicantGuardian and StudentGuardian — both carrying `relationship_type`. This is a modeling decision for the admissions-side and student-side of the domain respectively, not a duplication to be collapsed later without a new ADR.
- Progression logic must explicitly translate approved ApplicantGuardian relationships into StudentGuardian relationships; this is business logic that must be tested, including that a repeated/duplicate progression attempt does not duplicate these associations either.
- Traceability from Student back to its source Applicant requires a reference to be carried on the Student side; the exact foreign-key direction is left to implementation, since only the invariant is fixed here.

## Related requirements/domain decisions

- `docs/DOMAIN_MODEL.md` — "Applicant and Student are different concepts", "Guardians"
- `docs/REQUIREMENTS.md` — "Applicant management", "Guardian records and relationships", "Explicit Applicant-to-Student progression"
