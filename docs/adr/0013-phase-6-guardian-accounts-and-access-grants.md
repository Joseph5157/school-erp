# 0013. Phase 6 guardian accounts, access grants, multiple roles and revocation

## Status

Proposed — becomes Accepted when the Phase 6 planning PR is approved.
Planning: `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md` (decisions P1–P6, P13, P14).

## Context

Guardians have been first-class records since Phase 1, linked to Students
through `StudentGuardian` with a relationship type. Every phase so far has
deferred guardian access. Phase 6 opens a read-only, internet-facing Guardian
Portal. ADR 0004 requires that school-domain records are never the login
itself; Phase 5 (ADR 0010, ADR 0011) established that a role is a group of
logins with no model permissions whose access comes only from explicit links.

Guardian accounts differ from staff accounts: the people are external, many
are parents of minors, some relationships are restricted or non-custodial,
and the institution has no email or SMS provider (DOMAIN_MODEL: the core
must not depend on an external messaging provider).

## Decision

FROZEN once accepted:

**Identity and provisioning (P3, P4)**
- A guardian logs in as an ordinary `User`. There is no self-registration and
  no self-service password recovery in Phase 6.
- Only an administrator creates a guardian account, after verifying the
  person's identity against the institution's existing records. The
  administrator records that verification (method and a short note) at
  creation; the record is audited.
- The login identifier is a normalized username, never the guardian's phone
  number or email (neither is unique, neither is an identity key).
  Normalization: Unicode NFKC, surrounding whitespace removed, lower-cased.
  A database constraint on `Lower(username)` rejects case-only duplicates on
  SQLite and PostgreSQL.
- An account is created with a system-generated temporary password, shown
  once to the administrator for offline delivery (printed slip or another
  institution-controlled method). It is never stored in plain text, logged or
  emailed. The account must change its password at first login.
- Password reset is an administrator action that issues a new temporary
  password, forces a change at next login and invalidates every existing
  session of that account.

**Linking (P4)**
- `GuardianAccount` links one `User` to one `Guardian`. At most one active
  link per User and per Guardian.
- A person who is both a teacher and a guardian uses one User linked to both
  roles. Duplicate accounts for the same person are not created; linking an
  existing User is an explicit administrator choice by exact username, never a
  guessed match by name, phone or email.
- A login with more than one area (administration, My day, Guardian Portal)
  is shown an explicit area choice and role-aware navigation. No role is
  silently chosen or hidden.

**Explicit access grants (P5)**
- Being recorded as a Guardian grants nothing. Portal visibility of a Student
  requires an explicit, administrator-created `GuardianStudentAccess` grant
  for that exact `StudentGuardian` relationship.
- Relationship labels (father, mother, guardian, ...) never decide
  authorization. Restricted and non-custodial relationships are simply not
  granted.
- A guardian may see a Student only while all of these hold: the User is
  active; the User has an active `GuardianAccount`; that Guardian has an active
  grant for that Student. Checks run on every request.

**Revocation and history (P6)**
- Account links and access grants are revoked, never deleted. Revocation
  records who, when and why, takes effect immediately, and cannot be undone
  (re-granting creates a new grant, so the history shows the gap).
- Database triggers refuse deleting these rows, rewriting their identity
  columns, or clearing a revocation.
- Revoking a guardian's account link invalidates that account's sessions.
  Revoking one Student grant takes effect on the next request through the
  per-request check; sessions are not needed to enforce it.
- While a grant is active the guardian may see the Student's approved
  historical information (earlier Academic Years included).
- When a Student is made INACTIVE, the administrator is shown every active
  grant for that Student in the same workflow and must explicitly retain or
  revoke each one. The system never infers the decision. The decision and
  any retained grants are audited, and retained grants stay visible in an
  administrator review list.

**Student logins (P2)**
- Out of scope. Recorded as future Phase 6B (age, consent, credentials,
  recovery and safeguarding decisions required). No Student login-link model
  is created in Phase 6.

**Security (P13)**
- Database-backed login throttling, generic login errors, forced first-login
  password change, session invalidation on reset/deactivation/link
  revocation, secure production cookie and session settings, and an
  append-only security-event audit of account creation, sign-in success and
  failure, password reset, link and grant changes and result publication.
  No passwords, page contents or unnecessary raw personal data are logged, and
  there is no page-view logging. Details: Phase 6 plan, sections 7–8.

## Alternatives rejected

- Guardian email or phone as login: not unique, changes over time, and would
  create a reset channel the institution does not operate.
- Granting access to every recorded Guardian, or by relationship type:
  guesses custody and visibility.
- Deleting links or grants: loses the audit trail of who could see what.
- Separate accounts for a teacher who is also a parent: duplicate identities,
  split password and audit history.

## Consequences

- ADR 0004's "Guardian is never the login" holds; Guardians gain an optional,
  explicit login link.
- The `User` model gains a forced-password-change flag and a case-insensitive
  username constraint; existing usernames must be checked for case-only
  duplicates before the constraint migration runs.
- Student status changes to INACTIVE gain a mandatory access-review step.

## Related

- `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`
- `docs/adr/0002-applicant-student-and-guardian-lifecycle.md`
- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0011-phase-5-class-teacher-and-teacher-workflow-model.md`
- `docs/adr/0014-phase-6-guardian-visible-information-and-result-publication.md`
