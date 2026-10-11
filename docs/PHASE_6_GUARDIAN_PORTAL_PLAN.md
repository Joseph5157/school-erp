# Phase 6 — Guardian Portal

## Status

APPROVED (Gate 0) — product decisions P1–P14 and OD-1–OD-8 were decided by
the product owner on 2026-10-11 and are recorded here, in ADR 0013 (guardian
accounts, access grants, multiple roles, revocation, sessions, audit) and in
ADR 0014 (guardian-visible information and explicit result publication),
both Accepted. This plan is the Phase 6 source of truth; if it and an ADR
ever differ, the ADR is authoritative. Implementation follows the gates
below, in order.

Starting point (verified 2026-10-11):

- `main` = `phase-5-complete` = `350be94`; Phase 5 PRs #24–#33 merged.
- 796 tests pass on SQLite and PostgreSQL 16; `check`, `makemigrations
  --check` and Ruff clean; migrations applied through `core.0041`.
- Phase 3 Fees deferred. The unmerged `planning/future-phases` branch is
  outdated research and is not a source for this plan (P14).

Facts about the current code that shape this plan:

- No "close Academic Year" workflow exists; an Academic Year ends only by its
  end date passing.
- An enrollment ends only when `Student.enroll` records a new placement;
  there is no standalone "end enrollment" workflow, and an ACTIVE enrollment
  keeps an empty end date after its year's end date.
- Neither an admission number nor a roll number exists in the schema.
- `TermRemark` has no finalized state.

---

# 1. Phase 6 goal

A bounded, read-only, internet-facing Guardian Portal: an administrator
creates a guardian's account after verifying identity, explicitly grants
access to specific Students, and publishes Term results; the guardian signs
in, sees only those Students, and reads their approved profile, submitted
attendance and published Term report cards. Nothing a guardian has seen
changes silently afterwards, and every released version can be
reconstructed.

# 2. Out of scope

- Student logins (future Phase 6B: age, consent, credentials, recovery,
  safeguarding) — no Student login-link model is created (P2)
- self-registration, self-service forgotten-password, email or SMS delivery (P3)
- any editing or change request by guardians (P7)
- fees, fee placeholders or fee navigation (P10)
- announcements and messaging (moved to Phase 7) (P11)
- PDF or downloadable report cards; no PDF library (P12)
- attendance drafts, absence notes, correction history, correctors (P8)
- unpublished, draft or stale results; assessment-level publication (P9)
- page-view logging (P13)
- bulk grants, automatic grants by relationship type, bulk account creation,
  matching accounts by phone, email or name (P4, P5, OD-6)
- an Academic Year closing workflow or a standalone enrollment-ending
  workflow (any future one must call the access review rule)

# 3. Decisions

| # | Decision | Where frozen |
| --- | --- | --- |
| P1 | Read-only Guardian Portal for explicitly authorised Students | ADR 0014 |
| P2 | No Student logins; Phase 6B later | ADR 0013 |
| P3 | Admin-created accounts after identity verification; offline temporary password; forced change; admin-only reset ending sessions | ADR 0013 |
| P4 | Normalized username login; one rule everywhere; one User per person; explicit area choice | ADR 0013 |
| P5 | Access only by explicit admin grant per guardian–Student relationship | ADR 0013 |
| P6 | Revoke, never delete; explicit retain/revoke when placement ends | ADR 0013 |
| P7 | Approved profile fields only; read-only | ADR 0014 |
| P8 | Submitted attendance only; current values and summary | ADR 0014 |
| P9 | Publication separate from finalization; per Term; preview-first; idempotent; snapshot per version; stale on correction | ADR 0014 |
| P10–P12 | Fees, announcements and PDFs excluded | ADR 0014 |
| P13 | Throttling, generic errors, sessions, secure cookies, bounded audit | ADR 0013, §8 |
| P14 | Do not merge `planning/future-phases`; recommend deletion only after approval | this plan |
| OD-1 | `Student.admission_number` (optional, never generated, school-wide unique case-insensitively); `AcademicEnrollment.roll_number` (optional positive integer, never generated, unique within Academic Year + Section) | ADR 0014 |
| OD-2 | Publish at any time when the selected results are finalized; preview flags incomplete Students | ADR 0014 |
| OD-3 | Keyed hash of the canonical source address; forwarded headers only from configured trusted proxies | ADR 0013 |
| OD-4 | Guardian-linked usernames/passwords change only through the audited workflows, not the site administration | ADR 0013 |
| OD-5 | 30 minutes inactivity, 8 hours absolute; Secure, HttpOnly, SameSite=Lax cookies in production | ADR 0013 |
| OD-6 | No bulk grants; every grant explicit and individual | ADR 0013 |
| OD-7 | Routine authentication events 365 days; link, grant, revocation, review and publication history kept with domain records; LoginFailure 24 hours | ADR 0013 |

# 4. OD-8 — fail closed while a date-based review is pending (approved)

When a Student has no enrollment effective on the business date within its
own Academic Year (for example after the year's end date), there is no
workflow to block, so the review is date-based. The rule fails closed:

- the grant is not revoked and no decision is inferred; it enters the
  administrator review queue;
- from the first business date the condition holds, and until an
  administrator records RETAINED or REVOKED, the guardian receives no data
  for that Student: the portal lists the Student only as "access under
  review by the school", and every profile, attendance and report-card page
  for that Student responds as not available;
- there is no grace period and no continued access while pending;
- RETAINED restores access immediately for that ended placement; REVOKED
  revokes the grant in the same transaction;
- if the condition stops holding before a decision (for example a new
  placement is recorded, which itself requires a review), the pending date
  review is superseded by that workflow's decision.

Rejected: full access until decided (could last indefinitely if the queue is
ignored); a grace period (an extra rule with no product basis).

# 5. Proposed database model

All new tables and columns are additive. Nothing existing is renamed or
dropped, and no existing value is rewritten.

## accounts.User (existing; changed in Gate 1)

- `must_change_password` boolean, default false
- `session_version` positive integer, default 0; part of
  `get_session_auth_hash()`
- constraint `user_username_ci_unique` on `Lower("username")`
- `normalize_username()` (NFKC, strip, lower-case) and the allowed form
  `[a-z0-9._-]{3,30}` for new or changed usernames, used by account creation,
  the username-change workflow, the authentication backend (lookup by the
  normalized value) and the site-administration user forms

## core.Student and core.AcademicEnrollment (existing; changed in Gate 4)

- `Student.admission_number`: char(30), null; stored trimmed; constraint
  unique on `Upper("admission_number")` where not null (ASCII values are
  enforced so SQLite and PostgreSQL agree); administrator-entered only
- `AcademicEnrollment.roll_number`: positive small integer, null;
  constraint unique (`academic_year`, `section`, `roll_number`) where not
  null; administrator-entered only

## core.GuardianAccount (Gate 1) — login ↔ Guardian

- `user` FK User PROTECT, `guardian` FK Guardian PROTECT
- `identity_verified_by` FK User PROTECT, `identity_verification_method`
  (IN_PERSON_DOCUMENTS / EXISTING_RECORDS / OTHER),
  `identity_verification_note`
- `created_by` FK User PROTECT, `created_at`
- `revoked_at`, `revoked_by` FK User PROTECT null, `revocation_reason`
- constraints: unique active (`revoked_at IS NULL`) per `user`; unique active
  per `guardian`; revocation fields all set or all empty
- triggers: no DELETE; identity, verification and creation columns
  immutable; a revocation can be set once and never cleared

## core.GuardianStudentAccess (Gate 1) — explicit grant per relationship

- `student_guardian` FK StudentGuardian PROTECT
- `public_id` UUID unique, used in portal URLs
- `granted_by` FK User PROTECT, `granted_at`
- `revoked_at`, `revoked_by`, `revocation_reason`
- constraints: unique active per `student_guardian`; revocation fields all
  set or all empty
- triggers: no DELETE; `student_guardian`, `public_id`, `granted_*`
  immutable; a revocation can be set once and never cleared

## core.GuardianAccessReview (Gate 2) — explicit retain/revoke decisions

- `grant` FK GuardianStudentAccess PROTECT
- `trigger`: STUDENT_INACTIVE, PLACEMENT_ENDED, NO_CURRENT_ENROLLMENT
- `enrollment` FK AcademicEnrollment PROTECT null — the placement that ended
  (or the last placement, for NO_CURRENT_ENROLLMENT)
- `decision`: RETAINED or REVOKED; `decided_by`, `decided_at`, `note`
- constraint: unique (`grant`, `trigger`, `enrollment`) — one decision per
  ended placement
- triggers: no UPDATE, no DELETE
- A REVOKED decision also revokes the grant in the same transaction.
- A pending date-based review is computed, not stored: an active grant whose
  Student has no enrollment effective on the business date within its own
  Academic Year and no decision for that last placement.

## core.TermPublication (Gate 6) — one released version per Student per Term

- `student` FK PROTECT, `term` FK PROTECT, `placement` FK
  AcademicEnrollment PROTECT
- `version` positive integer (1, 2, … per Student + Term)
- `status`: PUBLISHED, STALE, SUPERSEDED, WITHDRAWN
- `is_partial` boolean and `pending_assessments` (count) — set when an
  incomplete Student was explicitly included
- snapshot header: `term_label`, `academic_year_label`, `class_grade_label`,
  `section_label`; `remark_text` (null) and `remark` FK TermRemark SET_NULL
  null (traceability only)
- `fingerprint` (SHA-256 hex) and `fingerprint_scheme` (integer, starts at 1)
- `published_by`, `published_at`; `status_changed_at`, `status_changed_by`
  null, `status_reason`
- constraints: unique (`student`, `term`, `version`); at most one row per
  Student + Term in PUBLISHED or STALE
- triggers: no DELETE; every column except the status fields immutable;
  status only moves PUBLISHED → STALE / SUPERSEDED / WITHDRAWN and
  STALE → SUPERSEDED / WITHDRAWN

## core.TermPublicationEntry (Gate 6) — immutable result snapshot

- `publication` FK TermPublication PROTECT, `result` FK StudentResult
  PROTECT (traceability)
- displayed fields only: `subject_label`, `assessment_label`,
  `assessment_date`, `maximum_marks`, `pass_mark` (null), `status`
  (MARKED/ABSENT), `score` (null), `percentage` (null), `grade_label` (null),
  `pass_fail_label` (null), `display_order`
- unique (`publication`, `result`); triggers: no UPDATE, no DELETE

## accounts.SecurityEvent (Gate 1) — bounded audit

- `event_type`, `event_class` (ROUTINE or HISTORY, fixed by event type),
  `occurred_at`
- `actor` FK User SET_NULL null, `subject_user` FK User SET_NULL null;
  optional `guardian`, `student`, `term` ids (no copied personal data)
- `source_key` (keyed hash, OD-3), `detail` small JSON of non-sensitive codes
- triggers: no UPDATE; DELETE refused unless `event_class` = ROUTINE and
  `occurred_at` is more than 365 days before the database's current time
  (both databases store UTC; the margin makes the check insensitive to
  timezones and test clocks)

## accounts.LoginFailure (Gate 7) — throttling state

- `username_key` (normalized attempted username), `source_key`,
  `occurred_at`; index on (`username_key`, `source_key`, `occurred_at`)
- operational: rows older than 24 hours are purged on each sign-in attempt;
  an administrator may clear a username's rows (audited)

## Not created

No Student login link, fee model, announcement model, page-view log or year
closing workflow.

# 6. Result publication design (P9, OD-2, revision 1)

**Snapshot per version.** Each publication version stores exactly what the
guardian report card displays (ADR 0014): header labels, one
`TermPublicationEntry` per released result with its displayed values, and
the remark text. The portal renders only from the snapshot, so any earlier
version can be shown exactly as released, even after its source results
were corrected. Each entry references its source result for traceability.
No other Student data is copied.

**Content.** All FINALIZED results of the Student in that Term (the Phase 4
`term_report_card` content), grouped by Subject in the order the card
displays them, and the class teacher's Term remark as it stands at
confirmation.

**Fingerprint (scheme 1).** SHA-256 over a canonical, sorted JSON of the
snapshot fields plus the source result ids and remark id. Computed from
stored values only; any change to the serialization requires a new scheme.

**Preview (Term + Section).** For each Student whose Term placement
(`AcademicTerm.enrollment_for`) is in the Section, the preview shows one of:

- **will publish** — the exact results and remark;
- **will republish** — the current version is STALE;
- **incomplete — not included unless selected** — an assessment in the Term
  on which the Student was on the roster is not FINALIZED; the preview lists
  those assessments; the administrator may tick the Student to publish the
  finalized results as a partial publication;
- **skipped: already published** — current PUBLISHED version has the same
  fingerprint (makes confirmation idempotent);
- **skipped: nothing to publish** — no finalized results and no remark;
- **skipped: ambiguous** — no single Term placement.

The preview token is a hash of the selected Student ids and their planned
fingerprints. Confirmation recomputes the plan inside a transaction under row
locks; a different token writes nothing and asks for a new review.
Confirming the same preview twice publishes nothing new. Republishing marks
the previous version SUPERSEDED and creates version n+1.

**Staleness.** In the same transaction as the change,
`StudentResult.correct()` marks the current publication of that Student +
Term STALE; saving or clearing a Term remark does the same. As a backstop for
any missed write path, the portal recomputes the live-source fingerprint and
shows a Term only when the current version is PUBLISHED and the fingerprints
match. Stale publications are listed for administrators to review and
republish; administrators may also withdraw a publication. All transitions
are audited as history events.

**Publication history.**
- Every version — PUBLISHED, STALE, SUPERSEDED and WITHDRAWN — and its
  snapshot is permanent history: never deleted, never rewritten, and not
  covered by the 365-day routine-event retention.
- Guardians see only the current PUBLISHED version of a Term whose
  fingerprint still matches. They never see STALE, SUPERSEDED or WITHDRAWN
  versions, earlier versions, version numbers or the change history.
- Administrators can view every version exactly as released, with who
  published it, when, and every status change with its actor and reason.
- A STALE or WITHDRAWN Term is simply absent from the portal; the guardian is
  not shown the previous values or told what changed.

# 7. Authorization matrix

Legend: ✔ allowed · ✖ refused (403) · 404 = treated as not existing ·
"own" = Students covered by the user's active grants with no pending review
(active login, active GuardianAccount, active grant).

| Action | Anonymous | School administrator | Teacher (Phase 5 scope) | Guardian (active link + grant) | Guardian whose link or grant is revoked | Teacher who is also a guardian |
| --- | --- | --- | --- | --- | --- | --- |
| Sign in | ✔ (throttled) | ✔ | ✔ | ✔ | ✔ (no Students if link revoked; sessions ended on link revocation) | ✔ |
| Forced password change when flagged | — | ✔ | ✔ | ✔ | ✔ | ✔ |
| Area choice / role-aware navigation | ✖ | own areas | own areas | own areas | own areas | My day **and** Guardian Portal |
| Guardian Portal home and child switcher | → login | ✖ unless also a guardian | ✖ | own Students; pending review shown as "under review" | none listed / 404 | own Students |
| Student profile (approved fields) | → login | admin pages only | Phase 5 teacher view | own: ✔, others: 404 | 404 | own: ✔ |
| Submitted attendance history and summary | → login | admin pages | Phase 5 scope | own: ✔, others: 404 | 404 | own: ✔ |
| Published Term report cards | → login | admin pages | Phase 5 scope (unpublished too) | own, current version PUBLISHED and fingerprint matching | 404 | own: ✔ |
| Any admin or teacher page | → login | ✔ (permissions) | teacher pages only | ✖ | ✖ | teacher pages only |
| Create guardian account / link existing login | ✖ | ✔ `add_guardianaccount` | ✖ | ✖ | ✖ | ✖ |
| Revoke account link | ✖ | ✔ `change_guardianaccount` | ✖ | ✖ | ✖ | ✖ |
| Grant / revoke Student access | ✖ | ✔ `add_`/`change_guardianstudentaccess` | ✖ | ✖ | ✖ | ✖ |
| Retain / revoke in an access review | ✖ | ✔ `add_guardianaccessreview` | ✖ | ✖ | ✖ | ✖ |
| Reset guardian password; change guardian username; clear lockout | ✖ | ✔ `reset_guardian_password`, `change_guardian_username`, `clear_login_lockout` | ✖ | ✖ | ✖ | ✖ |
| Preview / publish / withdraw Term results | ✖ | ✔ `publish_termpublication` | ✖ | ✖ | ✖ | ✖ |
| View security events | ✖ | ✔ `view_securityevent` | ✖ | ✖ | ✖ | ✖ |
| Purge routine security events older than 365 days | ✖ | operator command, `purge_securityevent` | ✖ | ✖ | ✖ | ✖ |
| Change a guardian-linked username or password in the site administration | ✖ | ✖ (dedicated workflows only) | ✖ | ✖ | ✖ | ✖ |

Notes:
- Guardians hold no model permissions; access comes only from links and is
  checked per request in `core.authorization`.
- Administrator powers never make someone a guardian.
- The app-wide authorization sweep is extended so that every existing URL
  refuses a guardian-only login and every portal URL refuses non-guardians.

# 8. Security design (P13, OD-3, OD-5, OD-7)

**Source address.** The client address is `REMOTE_ADDR`, unless the request
arrives from an address in the configured trusted-proxy list, in which case
the right-most `X-Forwarded-For` entry not in that list is used. The address
is canonicalized (IPv4 dotted form; IPv6 compressed lower-case) and stored
only as HMAC-SHA256 under a dedicated secret setting. With no trusted proxies
configured, forwarded headers are ignored.

**Throttling (Gate 7).** For each sign-in attempt, `username_key` is the
normalized attempted username and `source_key` the hashed source.
- Rule A: 5 failures for the same `username_key` + `source_key` within 15
  minutes → that pair is refused, without checking the password, until the
  oldest of those failures is 15 minutes old.
- Rule B: 20 failures for the same `username_key` from any sources within 15
  minutes → the username is refused for 15 minutes.
- A successful sign-in clears Rule A failures for that pair.
- Refusals show the same message as a wrong password ("The username or
  password is incorrect, or sign-in is temporarily unavailable.") and are
  routine events. Administrators can clear a username's failures (audited).
  Rows expire after 24 hours.

**Sessions and the enforcement point.** `AccountSecurityMiddleware`
(project middleware) sits immediately after Django's `AuthenticationMiddleware` and
runs on every request:
1. it resolves `request.user`, which makes Django verify the session hash —
   including `session_version` — and signs out a mismatched or inactive
   session;
2. it signs out a session idle for more than 30 minutes or older than 8
   hours since sign-in (both times kept in the session);
3. it enforces forced password change.
`session_version` is bumped on administrator password reset, deactivation
through the ERP and revocation of a guardian account link. A password change
through the forced-change page keeps only the current session.

**Forced password change.** A flagged login reaches only the
password-change page (GET, POST), sign-out (POST), static files (served
before the middleware) and the 403/404/500 error responses. Everything else,
including the site administration and the portal, redirects to the
password-change page.

**Cookies and transport (production).** Secure, HttpOnly, SameSite=Lax
session and CSRF cookies; HTTPS redirect and HSTS when not in DEBUG;
`manage.py check --deploy` clean with production settings;
temporary-password pages sent with `Cache-Control: no-store`.

**Audit events and retention.**
- Routine (365 days, purgeable): LOGIN_SUCCEEDED, LOGIN_FAILED,
  LOGIN_THROTTLED, LOCKOUT_CLEARED, PASSWORD_CHANGED, PASSWORD_RESET_BY_ADMIN.
- History (never deleted): ACCOUNT_CREATED, ACCOUNT_LINKED,
  ACCOUNT_LINK_REVOKED, USERNAME_CHANGED, ACCESS_GRANTED, ACCESS_REVOKED,
  ACCESS_RETAINED, ACCESS_REVIEW_PENDING, TERM_PUBLISHED, PUBLICATION_STALE,
  PUBLICATION_WITHDRAWN, SECURITY_EVENTS_PURGED.
- Retention purge: a management command run by an operator holding
  `purge_securityevent`; it deletes only routine events older than 365 days
  (the database trigger refuses anything else) and records a history event
  with the count. Append-only protection and retention are separate: history
  events and the domain records are never purgeable.
- Failed sign-ins record the subject login only if the normalized username
  exists, never the attempted text. No passwords, page content or contact
  data in events. No page-view events.

# 9. Migration and rollback strategy

- Every gate's migrations are additive and reversible on a test database.
  Before each gate ships, migrations are applied forward, reversed and applied
  again on SQLite and PostgreSQL test databases.
- Trigger migrations follow `core.0041`: vendor-specific SQL in `RunPython`
  with matching drop statements. Only the routine-event purge trigger
  compares with the database clock, with a 365-day margin.
- The `accounts` username constraint migration first runs a check that lists
  case-only duplicates and usernames outside the allowed form, then stops. It
  never merges, renames or rewrites accounts.
- The OD-1 constraint migrations first check for duplicate recorded values
  (none can exist yet, as the fields are new).
- Introducing `session_version` ends all existing sessions once at
  deployment; this is stated in the release notes.
- Permission data migrations add the new permissions to "School
  Administrators" and remove them on reverse.
- **Production rollback is not routine.** Reversing a migration is safe only
  before the gate's feature has been used in production. Once production
  holds guardian accounts, grants, reviews, publications or security events,
  dropping those tables destroys history: rolling back is then a
  restore-from-backup operation (take a backup before every Phase 6
  deployment), never a casual `migrate` backwards.

| Gate | Migration |
| --- | --- |
| 1 | accounts: `must_change_password`, `session_version`, case-insensitive username constraint (with pre-check); `SecurityEvent` + triggers |
| 1 | core: `GuardianAccount`, `GuardianStudentAccess`, permissions, history triggers |
| 2 | core: `GuardianAccessReview`, permission, triggers |
| 4 | core: `Student.admission_number`, `AcademicEnrollment.roll_number` with constraints |
| 6 | core: `TermPublication`, `TermPublicationEntry`, `publish_termpublication` permission, triggers |
| 7 | accounts: `LoginFailure`; `clear_login_lockout`, `purge_securityevent` permissions |

# 10. SQLite and PostgreSQL differences

- Expression (`Lower`, `Upper`) and partial (`condition=`) unique constraints
  work on both. SQL `LOWER`/`UPPER` fold only ASCII on SQLite, so new
  usernames and admission numbers are restricted to ASCII and stored
  normalized; tests assert case-only duplicates are rejected on both.
- Triggers need separate SQL per vendor; PostgreSQL raises
  `integrity_constraint_violation` so both surface as `IntegrityError`.
- The purge trigger compares `occurred_at` with `now()` (PostgreSQL) and
  `datetime('now')` (SQLite); Django stores UTC in both and the 365-day
  margin absorbs format and timezone differences. Tests insert events with
  explicit old and recent timestamps.
- `select_for_update` is a no-op on SQLite; correctness relies on unique
  constraints, with locking as extra protection on PostgreSQL.
- UUIDs are text on SQLite and native on PostgreSQL; only equality is used.

---

# Gate-by-Gate Implementation Plan

Each gate: build; full suite on SQLite and PostgreSQL; `check`,
`makemigrations --check`, Ruff; migrations reversed and re-applied on both
test databases; one commit, one PR, merge before the next gate. Bulk writes
always preview first and confirm idempotently. No account or
guardian–Student match is ever guessed.

## Gate 0 — Approved ADRs, requirements and implementation plan

Deliver ADR 0013, ADR 0014, this plan and the REQUIREMENTS, DOMAIN_MODEL and
ROADMAP updates. Acceptance: planning PR approved (PR #34); ADRs Accepted;
OD-1–OD-8 decided.

## Gate 1 — Guardian account links, explicit Student access grants and password change

Build: `normalize_username` and the authentication backend; User changes and
username constraint; `GuardianAccount`, `GuardianStudentAccess`,
`SecurityEvent`; administrator workflows on the Guardian page (create
account with verification, temporary password shown once; link an existing
login by exact normalized username; change a guardian username; revoke link;
grant/revoke access per recorded relationship; administrator password reset);
forced first-login password change through the security middleware; the
site administration refusing guardian-linked username/password changes.

Acceptance:
- no self-registration route; a recorded Guardian has no access until an
  administrator grants it, one relationship at a time;
- case-only duplicates are refused by every path (forms, site
  administration, database) on both databases; sign-in works with any case
  of a username;
- linking an existing teacher login creates no second account;
- temporary passwords are never stored in plain text, logged or rendered
  twice; first sign-in forces a change and only the allowed endpoints are
  reachable until then; reset ends existing sessions;
- links and grants cannot be deleted or rewritten (application and
  triggers); revocation is immediate, recorded and irreversible;
- every listed action writes the matching event in the right class; no event
  contains a password.

## Gate 2 — Authorization boundary, access reviews and application-wide sweep

Build: `core.authorization` helpers (`is_guardian`, `guardian_account`,
`guardian_grants`, `guardian_can_view`, `pending_access_reviews`);
`GuardianAccessReview`; blocking review steps in `Student.record_status_change`
(INACTIVE) and `Student.enroll` (placement ended); the date-based review
queue with the fail-closed rule (OD-8); the extended sweep.

Acceptance:
- a guardian-only login receives 403 on every existing admin and teacher URL;
- a Student outside the user's active grants is 404 on every portal URL,
  covering revoked links, revoked grants, inactive logins and other
  families' grants;
- making a Student INACTIVE, or recording a new placement (another Section,
  Class/Grade or Year), shows every active grant and requires retain or
  revoke for each before saving; nothing is inferred;
- a Student with no enrollment effective on the business date enters the
  review queue and the guardian receives no data for that Student until an
  administrator decides (OD-8, fail closed); a decision is asked once
  per ended placement and again for a later one;
- review decisions cannot be changed or deleted (triggers) and are audited.

## Gate 3 — Guardian portal shell, child switcher and multi-role navigation

Build: `guardian/` area with its own templates and navigation; home listing
granted Students by opaque id; child switcher; area choice page and
role-aware navigation; landing routing.

Acceptance: guardian-only logins land in the portal; multi-role logins see an
explicit choice and links to every area they hold, nothing hidden; portal
URLs contain no database ids; fees and announcements appear nowhere; constant
query count as Students and grants grow.

## Gate 4 — Approved read-only Student profile

Build: `Student.admission_number` and `AcademicEnrollment.roll_number` with
constraints and administrator entry on the existing Student and enrollment
pages; the portal profile with exactly the P7 fields.

Acceptance: values are never generated; duplicates are refused by form and
database on both databases (admission number case-insensitively; roll
number per Year + Section); missing values are omitted, not invented;
date of birth, Student phone/email, other guardians, internal ids and
staff-only data never render; POST is refused.

## Gate 5 — Submitted attendance history and summary

Build: per-Academic-Year history of SUBMITTED dates with current status and
the Phase 2 summary.

Acceptance: drafts, absence notes, correction history and correctors never
render; a correction shows only the corrected value; missing attendance is
never shown as absent; results match `reports.student_summary`; constant
query count.

## Gate 6 — Explicit Term publication and guardian report-card view

Build: `TermPublication`, `TermPublicationEntry`; administrator preview →
confirm per Term + Section with individually selectable incomplete Students;
stale marking in result correction and remark edits; stale review list;
withdraw; administrator view of any version; guardian report-card view from
the snapshot.

Acceptance:
- finalized but unpublished results never render in the portal; publication
  works before the Term ends;
- the preview lists every Student with exact content or a reason;
  incomplete Students are flagged and excluded unless individually selected,
  then marked partial; ambiguous Students cannot be published;
- nothing is written before confirmation; a stale token writes nothing;
  confirming twice publishes nothing new;
- a correction or remark change hides that Student's Term in the same
  transaction; a fingerprint mismatch from any other path also hides it;
  republishing creates version n+1;
- every earlier version renders exactly as released from its snapshot after
  its source results change;
- publication rows and snapshot entries cannot be deleted or rewritten
  (triggers).

## Gate 7 — Authentication, throttling, sessions, revocation and privacy hardening

Build: throttled sign-in and source-address handling (§8); generic errors;
lockout clearing; inactivity and absolute session limits; session-version
bumps on deactivation and link revocation; production cookie and HTTPS
settings; `no-store` on credential pages; routine-event retention purge.

Acceptance: Rule A and Rule B proven with fixed clocks; trusted-proxy
handling proven, and forwarded headers ignored without configuration;
expiry and admin clearing work; error messages identical for unknown user,
wrong password and throttled; 30-minute idle and 8-hour absolute limits
enforced; deactivation, reset and link revocation end sessions;
`check --deploy` clean with production settings; purge removes only routine
events older than 365 days and the database refuses any other delete; logs
and events contain no passwords or page content.

## Gate 8 — End-to-end integration, database protections and migration verification

End-to-end journey: admin verifies a guardian and creates the account →
offline password → forced change → grant one of two children → portal shows
one child only → submitted attendance visible, draft hidden → Term results
finalized but hidden → preview, incomplete Student flagged → publish →
report card visible → result corrected → Term hidden → republish → earlier
version still reconstructable → Student moved to another Section → explicit
retain → year end → review queue → link revoked → access gone, history
intact. Plus a teacher-who-is-a-parent journey, cross-family isolation,
trigger tests for every protected table, migrations forward/backward on both
test databases, query counts.

## Gate 9 — Documentation closeout and phase-6-complete release

README, ROADMAP, REQUIREMENTS, DOMAIN_MODEL, ADR status, completion table;
release notes include the one-time session reset, the backup-before-deploy
requirement and the restore-from-backup rollback rule. The
`phase-6-complete` tag is created by the product owner via a GitHub release.
A recommendation on deleting `planning/future-phases` is made here and not
acted on without approval (P14).

---

# Stop-and-return-to-planning conditions

- Student logins or any Student-facing view (Phase 6B)
- email, SMS or any external delivery; self-service password recovery
- guardian editing or change requests
- fee visibility or fee data
- announcements or messaging
- PDF/downloadable documents
- assessment-level or immediate-on-finalize publication
- automatic or bulk grants, or matching by relationship type, phone, email
  or name
- automatic revocation at year end or on transfer
- page-view logging or analytics
- new infrastructure (Redis, Celery, external auth providers)

# Unresolved technical risks

1. Existing case-only duplicates or non-conforming usernames stop the Gate 1
   migration; resolving them is a manual administrator decision.
2. A wrong trusted-proxy configuration either throttles everyone together or
   lets clients spoof addresses; the default (no trusted proxies) is safe but
   throttles per proxy if one is deployed unconfigured.
3. Rule B can lock a known guardian username for 15 minutes; mitigated by
   Rule A being primary, the higher threshold and admin clearing.
4. Introducing `session_version` logs every user out once at deployment.
5. The server shell and direct database access bypass stale marking and
   audit; the render-time fingerprint check keeps changed results hidden, but
   the shell remains trusted.
6. Fingerprints must depend only on stored values; a serialization change
   without a new scheme number would turn every publication stale.
7. Date-based reviews depend on enrollments' effective dates. An ACTIVE
   enrollment keeps an empty end date after its year ends, so a grant created
   for a Student whose only placement is in an ended year enters review
   immediately (expected, and visible in the queue).
8. Roll numbers are never reused within a Year + Section, which may differ
   from a school's practice for re-admitted Students.
9. One grant per relationship means data entry for the whole school (OD-6);
   there is deliberately no bulk path.

# Phase 6 completion principle

Phase 6 is complete when an administrator can verify, create and link a
guardian account, grant access to specific Students and publish Term results
through a preview; the guardian can sign in safely and see only those
Students' approved profile, submitted attendance and published report cards;
nothing released changes silently and every released version can be
reconstructed; every account, access, review and publication change is
audited; and no record of who could see what is ever deleted.
