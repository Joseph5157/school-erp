# 0013. Phase 6 guardian accounts, access grants, multiple roles and revocation

## Status

Accepted (2026-10-11, Phase 6 planning PR #34).
Planning: `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md` (decisions P1–P6, P13, P14,
OD-3 to OD-8).

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

**Identity and provisioning (P3)**
- A guardian logs in as an ordinary `User`. There is no self-registration and
  no self-service password recovery in Phase 6.
- Only an administrator creates a guardian account, after verifying the
  person's identity against the institution's existing records, and records
  the verification method and a short note. Creation is audited.
- The account is created with a system-generated temporary password shown
  once to the administrator for offline delivery (printed slip or another
  institution-controlled method). It is never stored in plain text, logged,
  emailed or rendered a second time. The account must change its password at
  first login.
- Password reset is an administrator action that issues a new temporary
  password, forces a change at next login and ends every existing session of
  that account.

**Usernames (P4, revision 3)**
- The login identifier is a username, never a phone number or email.
- One rule, implemented once (`normalize_username`) and used by every path
  that creates, changes or looks up a username: Unicode NFKC, surrounding
  whitespace removed, lower-cased. New and changed usernames must match
  `[a-z0-9._-]`, 3–30 characters, after normalization.
- The same comparison is used by: account creation, the username-change
  workflow, the authentication backend (looks up by the normalized value),
  the site-administration user forms, and the database constraint
  `UniqueConstraint(Lower("username"))`. Restricting new usernames to ASCII
  makes SQL `LOWER` (ASCII-only on SQLite) and Python lower-casing agree.
- Existing usernames are not rewritten. A migration pre-check lists any
  case-only duplicates or usernames outside the allowed form and stops; it
  never merges, renames or guesses.

**Linking and multiple roles (P4)**
- `GuardianAccount` links one `User` to one `Guardian`. At most one active
  link per User and per Guardian.
- A person who is both a teacher and a guardian uses one User linked to both
  roles. Linking an existing User is an explicit administrator choice by
  exact (normalized) username, never a guessed match by name, phone or email.
- A login with more than one area (administration, My day, Guardian Portal)
  is shown an explicit area choice and role-aware navigation. No role is
  silently chosen or hidden.

**Explicit access grants (P5, OD-6)**
- Being recorded as a Guardian grants nothing. Portal visibility of a Student
  requires an explicit, administrator-created `GuardianStudentAccess` grant
  for that exact `StudentGuardian` relationship. Grants are created one at a
  time; there is no bulk grant in Phase 6.
- Relationship labels (father, mother, guardian, ...) never decide
  authorization. Restricted and non-custodial relationships are simply not
  granted.
- A guardian may see a Student only while all of these hold: the User is
  active; it has an active `GuardianAccount`; that Guardian has an active
  grant for that Student; and no access review for that grant is pending.
  Checks run on every request.

**Revocation and history (P6)**
- Account links, grants and review decisions are revoked or superseded,
  never deleted. Revocation records who, when and why, takes effect
  immediately and cannot be undone (re-granting creates a new grant, so the
  history shows the gap). Database triggers refuse deleting these rows,
  rewriting their identity columns or clearing a revocation.
- Revoking a guardian account link ends that account's sessions. Revoking one
  Student grant takes effect on the next request through the per-request
  check.
- While a grant is active and not under review, the guardian may see the
  Student's approved historical information (earlier Academic Years included).

**Access review when a Student's placement ends (P6, revision 2)**
- A grant must be explicitly retained or revoked by an administrator, never
  inferred, when any of these happens:
  1. the Student is made INACTIVE;
  2. the Student's current enrollment ends because a new placement is
     recorded (`Student.enroll`), including a move to another Section,
     Class/Grade or Academic Year;
  3. the Student has no enrollment effective on the business date within its
     own Academic Year (this covers the end of an Academic Year: the code has
     no year-closing workflow, so the year's end date is the trigger);
  4. any future workflow that ends an enrollment (it must call the same
     review rule).
- Triggers 1, 2 and 4 are blocking steps inside the workflow: the
  administrator sees every active grant of that Student and must choose
  retain or revoke for each before the change is saved.
- Trigger 3 has no workflow, so it is date-based and **fails closed** (OD-8):
  the grant enters the administrator review queue and, from the first
  business date the condition holds until an administrator records RETAINED
  or REVOKED, the guardian receives no data for that Student (it is listed
  only as "access under review by the school"). There is no grace period.
  The grant is not revoked and no decision is inferred.
- Each decision is an immutable `GuardianAccessReview` row tied to the
  trigger and the enrollment it concerns, so a retained decision for one
  ended placement is not asked again, and a later ended placement asks
  again. Decisions are audited.

**Sessions (P13, OD-5, revision 4)**
- A per-user `session_version` is part of the session authentication hash.
  Bumping it ends every session of that login: on administrator password
  reset, deactivation through the ERP and revocation of a guardian account
  link.
- Enforcement point: `AccountSecurityMiddleware`, placed immediately after Django's
  authentication middleware runs on every request. It resolves the user
  (which verifies the session hash, including `session_version`, and signs
  out a mismatched or inactive session), enforces a 30-minute inactivity
  limit and an 8-hour absolute limit from sign-in, and enforces forced
  password change.
- A login that must change its password reaches only: the password-change
  page (GET and POST), sign-out (POST), static files, and the 403/404/500
  error responses. Every other request, including the site administration,
  redirects to the password-change page.
- Production cookies are Secure, HttpOnly and SameSite=Lax.

**Student logins (P2)**
- Out of scope. Recorded as future Phase 6B (age, consent, credentials,
  recovery and safeguarding decisions required). No Student login-link model
  is created in Phase 6.

**Security and audit (P13, OD-3, OD-4, OD-7, revision 6)**
- Database-backed login throttling with generic errors (plan §8). Network
  sources are stored only as a keyed hash of the canonical client address;
  forwarded headers are trusted only from explicitly configured trusted
  proxy addresses.
- Guardian-linked usernames and passwords change only through the dedicated
  audited workflows; the site administration refuses those changes.
- Security events fall into two classes:
  - **routine authentication events** (sign-in succeeded, failed or
    throttled, lockout cleared, password changed by the user, password reset
    by an administrator) are append-only and kept 365 days; an authorized
    retention purge removes only routine events older than 365 days and
    records that it ran;
  - **history events** (account created, linked or link revoked; access
    granted, revoked, retained or put under review; publication made, stale
    or withdrawn; retention purge run) are never deleted.
- The domain records themselves (`GuardianAccount`, `GuardianStudentAccess`,
  `GuardianAccessReview`, publications) are the permanent history and are
  immutable apart from their allowed revocation and status transitions.
- Login-failure throttling records are operational and expire after 24 hours.
- No passwords, page contents or unnecessary raw personal data are logged;
  there is no page-view logging.

## Alternatives rejected

- Guardian email or phone as login: not unique, changes over time, and would
  create a reset channel the institution does not operate.
- Granting access to every recorded Guardian, or by relationship type:
  guesses custody and visibility.
- Deleting links or grants: loses the audit trail of who could see what.
- Separate accounts for a teacher who is also a parent: duplicate identities,
  split password and audit history.
- Reviewing access only on INACTIVE status: misses transfers and year end.
- Automatically revoking at year end: infers a decision the school must make.

## Consequences

- ADR 0004's "Guardian is never the login" holds; Guardians gain an optional,
  explicit login link.
- `User` gains `must_change_password`, `session_version` and a
  case-insensitive username constraint; introducing `session_version` ends all
  existing sessions once at deployment.
- `Student.record_status_change` and `Student.enroll` gain a blocking access
  review step when the Student has active grants.

## Related

- `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`
- `docs/adr/0002-applicant-student-and-guardian-lifecycle.md`
- `docs/adr/0004-phase-1-authorization-foundation.md`
- `docs/adr/0006-academic-enrollment-effective-dating.md`
- `docs/adr/0011-phase-5-class-teacher-and-teacher-workflow-model.md`
- `docs/adr/0014-phase-6-guardian-visible-information-and-result-publication.md`
