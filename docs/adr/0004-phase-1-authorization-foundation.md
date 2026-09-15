# 0004. Phase 1 authorization foundation

## Status

Accepted

## Context

`docs/ARCHITECTURE.md` requires authorization to be designed from the beginning, requires a custom User model created before the first migration, and explicitly forbids using school-domain entities (Student, Guardian, Teacher, and similar) directly as the authentication identity. `docs/REQUIREMENTS.md` requires every Phase 1 administrative mutation to be protected and verified by automated tests, while explicitly not requiring complete workflows for future Teacher, Staff, Parent/Guardian, or Student roles.

This ADR fixes the minimum Phase 1 authorization foundation consistent with those constraints.

## Decision

FROZEN:

- Authentication identity uses the custom Django User model.
- Student, Guardian, Teacher, and similar school-domain identities are not authentication models and never log in as themselves.
- Phase 1 uses Django Groups/Permissions as the authorization foundation.
- Phase 1 implements only the minimum administrator authorization required to protect Phase 1 administrative workflows; the full future role matrix (Teacher/Staff/Parent-Guardian/Student authorization) is not implemented yet.
- Every Phase 1 administrative mutation (school configuration, academic setup, applicant/guardian records and relationships, admission decisions, Applicant-to-Student progression, Academic Enrollment changes, Student status changes) must require authenticated, authorized administrative access.
- Authorization logic must be centralized and reusable — a single shared mechanism — rather than independently reimplemented in every view.
- Fine-grained field-level or object-level RBAC is outside Phase 1 unless a concrete requirement emerges.
- No disposable dummy feature is built solely to demonstrate authorization; authorization is verified against the first real protected Phase 1 workflow and every subsequent protected operation.

## Alternatives considered

- **Use Django's `is_staff`/`is_superuser` flags alone, without Groups/Permissions.** Rejected: less extensible toward the future role matrix (Teacher/Staff/Parent-Guardian/Student) that `docs/ARCHITECTURE.md` requires the system to be able to grow into.
- **Build a full custom RBAC system (roles, field-level permissions) in Phase 1.** Rejected as over-engineering: `docs/REQUIREMENTS.md` only requires blocking non-administrators from Phase 1 mutations, and `docs/ARCHITECTURE.md` favors minimal infrastructure.
- **Check authorization ad hoc inside each view/handler as it is written.** Rejected: creates a hidden-coupling risk where a missed check in one view silently leaves a mutation unprotected, and duplicates logic that should exist once.
- **Verify authorization via a purpose-built dummy/demo view.** Rejected per explicit decision: authorization must be proven against real Phase 1 workflows, not a throwaway feature.

## Consequences

- A single shared authorization mechanism (for example, a mixin or decorator) must exist before the first real protected workflow is implemented, and every subsequent protected workflow reuses it rather than reinventing checks.
- Teacher/Staff/Parent-Guardian/Student authentication and authorization are explicitly deferred; introducing them later adds role scaffolding on top of the existing custom User model rather than requiring it to be reworked.
- Automated tests must cover the authorized/unauthorized boundary for every Phase 1 administrative mutation, per `docs/REQUIREMENTS.md`'s acceptance criteria — verified against real workflows as they are built, starting with the first one.

## Related requirements/domain decisions

- `docs/ARCHITECTURE.md` — "Authorization principle", "Authentication principle"
- `docs/REQUIREMENTS.md` — "Administrative authorization"
