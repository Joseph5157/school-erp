# Phase 6 — Guardian Portal

## Status

PLANNED — documentation only, for review. Product decisions P1–P14 were
provided by the product owner on 2026-10-11 and are recorded here, in
ADR 0013 (guardian accounts, access grants, multiple roles, revocation) and in
ADR 0014 (guardian-visible information and explicit result publication).
The ADRs become Accepted, and this plan becomes the Phase 6 source of truth,
when the planning PR is approved. Section 4 lists the remaining open
decisions; those marked "blocks" must be answered before the gate they block.
No application code, migration or template may be written before approval.

Starting point (verified 2026-10-11):

- `main` = `phase-5-complete` = `350be94`; Phase 5 PRs #24–#33 merged.
- 796 tests pass on SQLite and PostgreSQL 16; `check`, `makemigrations
  --check` and Ruff clean; migrations applied through `core.0041`.
- Phase 3 Fees deferred. The unmerged `planning/future-phases` branch is
  outdated research and is not a source for this plan (P14).

---

# 1. Phase 6 goal

A bounded, read-only, internet-facing Guardian Portal: an administrator
creates a guardian's account after verifying identity, explicitly grants
access to specific Students, and publishes Term results; the guardian signs
in, sees only those Students, and reads their approved profile, submitted
attendance and published Term report cards. Nothing a guardian has seen
changes silently afterwards.

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
- automatic grants by relationship type, bulk account creation from guardian
  records, matching accounts by phone/email/name (P4, P5)

# 3. Product decisions (P1–P14)

| # | Decision | Where frozen |
| --- | --- | --- |
| P1 | Read-only Guardian Portal for explicitly authorised Students | ADR 0014 |
| P2 | No Student logins; Phase 6B later | ADR 0013 |
| P3 | Admin-created accounts after identity verification; offline temporary password; forced change at first login; admin-only reset that ends sessions | ADR 0013 |
| P4 | Normalized username login; case-only duplicates impossible; one User per person across teacher/guardian roles; explicit area choice | ADR 0013 |
| P5 | Access only by explicit admin grant per guardian–Student relationship; labels never authorize | ADR 0013 |
| P6 | Revoke, never delete; immediate; history kept; INACTIVE Student forces explicit retain/revoke | ADR 0013 |
| P7 | Approved profile fields only; read-only | ADR 0014 |
| P8 | Submitted attendance only; current values and summary | ADR 0014 |
| P9 | Publication separate from finalization; per-Term, preview-first, idempotent; correction makes it stale | ADR 0014 |
| P10 | Fees excluded | ADR 0014 |
| P11 | Announcements → Phase 7 | ADR 0014 |
| P12 | No PDFs | ADR 0014 |
| P13 | Throttling, generic errors, sessions, secure cookies, bounded audit | ADR 0013, §8 |
| P14 | Do not merge `planning/future-phases`; decide its deletion after approval | this plan |

# 4. Open decisions needing approval

Recommendations are given; nothing below is assumed by the ADRs.

- **OD-1 (blocks Gate 4) — Public Student identifier and roll number do not
  exist.** P7 lists "admission number or approved public student identifier"
  and "roll number", but the schema has neither (Student has name, date of
  birth, email, phone, status; AcademicEnrollment has no roll number).
  Recommendation: add, as administrator-entered data with no automatic
  numbering and no guessing,
  `Student.admission_number` (optional; unique case-insensitively when set)
  and `AcademicEnrollment.roll_number` (optional positive integer; unique per
  Academic Year + Section among overlapping enrollments when set), plus
  admin entry on the existing Student and enrollment pages. If not approved,
  the portal omits both and shows only name and placement.
- **OD-2 (blocks Gate 6) — When may a Term be published?**
  Recommendation: only after the Term's end date (it is a Term report card);
  earlier publication is refused.
- **OD-3 (blocks Gate 7) — Network source in throttling and audit.**
  Recommendation: never store raw IP addresses; store an HMAC of the client
  address keyed with a dedicated setting. Use `REMOTE_ADDR` unless a
  deployment explicitly configures the number of trusted reverse proxies.
- **OD-4 (blocks Gate 7) — Django site administration and guardian logins.**
  Teachers are added to their group through the site administration
  (ADR 0010), so it stays. Recommendation: the site administration refuses
  password and username changes for logins that have a guardian link, so the
  only path is the audited ERP reset workflow.
- **OD-5 (Gate 7) — Session lifetime.** Recommendation: 8 hours absolute
  for every login, cookies Secure/HttpOnly/SameSite=Lax in production.
- **OD-6 (Gate 1) — Bulk grants.** P5 requires an explicit grant per
  relationship. Recommendation: no bulk grant in Phase 6; grants are made one
  relationship at a time from the Guardian or Student page.
- **OD-7 (Gate 7) — Security-event retention.** Recommendation: keep
  indefinitely in Phase 6 (events are discrete, not per page view); a purge
  policy belongs to Production Hardening.

# 5. Proposed database model

All new tables are additive. Nothing existing is renamed or dropped.

## accounts.User (existing; changed in Gate 1)

- `must_change_password` boolean, default false
- `session_version` positive integer, default 0; included in
  `get_session_auth_hash()` so bumping it ends every session of that login
- constraint `user_username_ci_unique` on `Lower("username")`
- username normalization (NFKC, strip, lower-case) on every ERP create path;
  the constraint is the backstop for any other path

## core.GuardianAccount (Gate 1) — login ↔ Guardian

- `user` FK User PROTECT, `guardian` FK Guardian PROTECT
- `identity_verified_by` FK User PROTECT, `identity_verification_method`
  (short choice: IN_PERSON_DOCUMENTS / EXISTING_RECORDS / OTHER),
  `identity_verification_note` (short text)
- `created_by` FK User PROTECT, `created_at`
- `revoked_at`, `revoked_by` FK User PROTECT null, `revocation_reason`
- constraints: unique active (`revoked_at IS NULL`) per `user`; unique active
  per `guardian`; revocation fields all set or all empty
- triggers (SQLite + PostgreSQL): no DELETE; no change to `user`,
  `guardian`, verification and creation columns; `revoked_at` can go from
  empty to set, never back

## core.GuardianStudentAccess (Gate 1) — explicit grant per relationship

- `student_guardian` FK StudentGuardian PROTECT (the recorded relationship;
  a grant cannot exist without one)
- `public_id` UUID, unique, used in portal URLs instead of database ids
- `granted_by` FK User PROTECT, `granted_at`
- `revoked_at`, `revoked_by`, `revocation_reason`
- `last_reviewed_at`, `last_reviewed_by`, `last_review_decision`
  (RETAINED — set when an administrator explicitly keeps access for an
  INACTIVE Student; revocation is recorded in the revocation fields)
- constraints: unique active per `student_guardian`; revocation fields all
  set or all empty; review fields all set or all empty
- triggers: no DELETE; no change to `student_guardian`, `public_id`,
  `granted_*`; no clearing a revocation

## core.TermPublication (Gate 6) — one released version per Student per Term

- `student` FK PROTECT, `term` FK PROTECT, `placement` FK AcademicEnrollment
  PROTECT (the Term placement at publication)
- `version` positive integer (1, 2, … per Student + Term)
- `status`: PUBLISHED, STALE, SUPERSEDED, WITHDRAWN
- `fingerprint` (SHA-256 hex) and `fingerprint_scheme` (integer, starts at 1)
- `remark` FK TermRemark SET_NULL null (the remark released, if any)
- `published_by`, `published_at`; `status_changed_at`,
  `status_changed_by` null, `status_reason`
- constraints: unique (`student`, `term`, `version`); at most one row per
  Student + Term in PUBLISHED or STALE (the current version)
- triggers: no DELETE; `student`, `term`, `placement`, `version`,
  `fingerprint`, `published_*` immutable; status only moves
  PUBLISHED → STALE / SUPERSEDED / WITHDRAWN and STALE → SUPERSEDED / WITHDRAWN

## core.TermPublicationResult (Gate 6) — what was released

- `publication` FK TermPublication PROTECT, `result` FK StudentResult PROTECT
- unique (`publication`, `result`); no UPDATE or DELETE (triggers)

## accounts.SecurityEvent (Gate 1) — bounded, append-only audit

- `event_type` (see §8), `occurred_at`
- `actor` FK User SET_NULL null, `subject_user` FK User SET_NULL null
- optional `guardian`, `student`, `term` references (ids only, no copied
  personal data)
- `source_key` (HMAC of network source, see OD-3), `detail` small JSON of
  non-sensitive codes (never passwords, page content or contact data)
- triggers: no UPDATE, no DELETE

## accounts.LoginFailure (Gate 7) — throttling state

- `username_key` (normalized attempted username), `source_key`,
  `occurred_at`; index on (`username_key`, `source_key`, `occurred_at`)
- operational data: rows older than 24 hours are purged on each login
  attempt; may be deleted by administrator recovery

## Optional, only if OD-1 is approved (Gate 4)

- `Student.admission_number`, `AcademicEnrollment.roll_number` as described
  in OD-1, with their uniqueness constraints.

## Not created

No Student login link, fee model, announcement model or page-view log.

# 6. Result publication design (P9)

**Version record, not a copy.** A publication references the exact
`StudentResult` rows and `TermRemark` it released and stores a fingerprint
of their released values. Result data stays in one place (Phase 4 tables);
the publication proves what was released.

**Fingerprint (scheme 1).** SHA-256 over a canonical, sorted JSON list of,
for each released result: result id, assessment id, assessment name, date,
maximum marks, pass mark, status, score, and the grade label from the
assessment's frozen grading snapshot; plus the remark id and text (or
none). Only stored values are used, so later code changes cannot alter it;
a new scheme number is required for any change to the serialization.

**What a Student's Term publication contains.** The Term report card
content of Phase 4 (`term_report_card`): every FINALIZED result of the
Student in that Term, grouped by Subject, and the class teacher's remark.

**Preview (Term + Section).** For each Student whose Term placement
(`AcademicTerm.enrollment_for`) is in the Section, the preview lists either
"will publish" with the exact results and remark, or "skipped" with a reason:

- no Term placement or more than one candidate placement (ambiguous);
- any assessment in the Term on which the Student was on the roster is not
  FINALIZED (incomplete);
- no finalized results and no remark (nothing to publish);
- the current publication is already PUBLISHED with the same fingerprint
  (already published — makes confirmation idempotent);
- the Term has not ended (if OD-2 is approved).

A Student whose current publication is STALE appears as "will republish".
The preview carries a token (hash of the planned Student ids and
fingerprints). Confirmation recomputes the plan inside a transaction under
row locks; a different token writes nothing and asks for a new review.
Confirming the same preview twice publishes nothing new. Republishing marks
the previous version SUPERSEDED and creates version n+1.

**Staleness.** In the same transaction as the change:
`StudentResult.correct()` marks the current publication of that Student +
Term STALE; saving or clearing a Term remark does the same. As a backstop
for any missed write path, the portal recomputes the fingerprint on render
and shows a Term only when the current version is PUBLISHED and the
fingerprint matches; otherwise the Term is hidden (never shown with new
values). Stale publications are listed for administrators to review and
republish. Administrators may also withdraw a publication (audited).

# 7. Authorization matrix

Legend: ✔ allowed · ✖ refused (403) · 404 = treated as not existing ·
"own" = only Students covered by the user's active grants (active login,
active GuardianAccount, active grant).

| Action | Anonymous | School administrator | Teacher (Phase 5 scope) | Guardian (active link + grant) | Guardian whose link or grant is revoked | Teacher who is also a guardian |
| --- | --- | --- | --- | --- | --- | --- |
| Sign in | ✔ (throttled) | ✔ | ✔ | ✔ | ✔ (sees no Students if link revoked; sessions ended on link revocation) | ✔ |
| Forced password change when flagged | — | ✔ | ✔ | ✔ | ✔ | ✔ |
| Area choice / role-aware navigation | ✖ | own areas | own areas | own areas | own areas | My day **and** Guardian Portal |
| Guardian Portal home and child switcher | → login | ✖ unless also a guardian | ✖ | own Students | no Students listed / 404 | own Students |
| Student profile (approved fields) | → login | admin pages only | Phase 5 teacher view | own: ✔, others: 404 | 404 | own: ✔ |
| Submitted attendance history and summary | → login | admin pages | Phase 5 scope | own: ✔, others: 404 | 404 | own: ✔ |
| Published Term report cards | → login | admin pages | Phase 5 scope (unpublished too) | own and PUBLISHED with matching fingerprint only | 404 | own: ✔ |
| Any admin or teacher page | → login | ✔ (permissions) | teacher pages only | ✖ | ✖ | teacher pages only |
| Create guardian account / link existing login | ✖ | ✔ `add_guardianaccount` | ✖ | ✖ | ✖ | ✖ |
| Revoke account link | ✖ | ✔ `change_guardianaccount` | ✖ | ✖ | ✖ | ✖ |
| Grant / revoke / retain Student access | ✖ | ✔ `add_`/`change_guardianstudentaccess` | ✖ | ✖ | ✖ | ✖ |
| Reset guardian password; clear lockout | ✖ | ✔ `reset_guardian_password`, `clear_login_lockout` | ✖ | ✖ | ✖ | ✖ |
| Preview / publish / withdraw Term results | ✖ | ✔ `publish_termpublication` | ✖ | ✖ | ✖ | ✖ |
| View security events | ✖ | ✔ `view_securityevent` | ✖ | ✖ | ✖ | ✖ |

Notes:
- Guardians hold no model permissions; like teachers, their access comes
  only from links and is checked per request in `core.authorization`.
- Administrator powers never make someone a guardian; an administrator sees
  the portal only if they personally hold a guardian link and grant.
- The app-wide authorization sweep is extended so that every existing URL
  refuses a guardian-only login, and every portal URL refuses non-guardians.

# 8. Security design (P13)

**Throttling (Gate 7).** On each sign-in attempt, compute `username_key`
(normalized attempted username) and `source_key` (OD-3).
- Rule A: 5 failures for the same `username_key` + `source_key` within 15
  minutes → further attempts from that source for that username are refused
  without checking the password until the oldest of those 5 failures is 15
  minutes old.
- Rule B: 20 failures for the same `username_key` from any sources within
  15 minutes → the username is refused for 15 minutes (distributed guessing).
- A successful sign-in clears Rule A failures for that key pair.
- Refusals show the same generic message as a wrong password ("The username
  or password is incorrect, or sign-in is temporarily unavailable.") and are
  audited as LOGIN_THROTTLED. Administrators can clear a username's
  failures (audited LOCKOUT_CLEARED). Rows expire after 24 hours.

**Sessions.** Bumping `User.session_version` ends every session of a login.
It is bumped on administrator password reset, on deactivation through the ERP,
and on revocation of a guardian account link. Grant revocation needs no
session change because the grant is checked on every request. Changing a
password through the forced-change page keeps only the current session.

**Forced password change.** A middleware sends any signed-in login with
`must_change_password` to the password-change page; only that page, sign
out and static files are reachable until it is done.

**Cookies and transport (production).** Secure, HttpOnly, SameSite=Lax
session and CSRF cookies; HTTPS redirect and HSTS when not in DEBUG;
`manage.py check --deploy` clean with production environment variables;
temporary-password pages sent with `Cache-Control: no-store`.

**Audit events.** ACCOUNT_CREATED, ACCOUNT_LINKED, ACCOUNT_LINK_REVOKED,
ACCESS_GRANTED, ACCESS_REVOKED, ACCESS_RETAINED, PASSWORD_RESET_BY_ADMIN,
PASSWORD_CHANGED, LOGIN_SUCCEEDED, LOGIN_FAILED, LOGIN_THROTTLED,
LOCKOUT_CLEARED, TERM_PUBLISHED, PUBLICATION_STALE, PUBLICATION_WITHDRAWN.
Failed sign-ins record the subject login only if the normalized username
exists, and never the attempted text (people type passwords into the
username box). No page-view events.

# 9. Migration and rollback strategy

- Every gate's migrations are additive, reversible and verified forward,
  backward and forward again on SQLite and PostgreSQL before shipping.
- Trigger migrations follow `core.0041`: vendor-specific SQL in `RunPython`
  with matching drop statements; triggers never consult the clock.
- `accounts` username constraint: a `RunPython` pre-check lists any
  case-only duplicate usernames and aborts with that list; it never merges
  or renames accounts. Reverse drops the constraint.
- Adding `session_version` to the session hash ends all existing sessions
  once at deployment; this is expected and documented in the release notes.
- Permission data migrations add the new permissions to "School
  Administrators" and remove them on reverse (existing `permmig` pattern).
- Reversing a migration that created a table drops its data. Production
  rollback of a gate that has created guardian links, grants, publications
  or audit events requires an export first; the closeout documents this.

Planned migrations (numbers indicative):

| Gate | Migration |
| --- | --- |
| 1 | accounts: `must_change_password`, `session_version`, case-insensitive username constraint (with pre-check); `SecurityEvent` + append-only triggers |
| 1 | core: `GuardianAccount`, `GuardianStudentAccess`, permissions, history triggers |
| 4 | core: `admission_number`, `roll_number` (only if OD-1 approved) |
| 6 | core: `TermPublication`, `TermPublicationResult`, `publish_termpublication` permission, triggers |
| 7 | accounts: `LoginFailure`; `clear_login_lockout`, `reset_guardian_password` permissions |

# 10. SQLite and PostgreSQL differences

- Expression (`Lower`) and partial (`condition=`) unique constraints work on
  both; tests assert the database rejects case-only duplicates and second
  active links on both.
- Triggers need separate SQL per vendor; PostgreSQL raises
  `integrity_constraint_violation` so both surface as `IntegrityError`.
- `select_for_update` is a no-op on SQLite; correctness under concurrency
  relies on the unique constraints, with locking as extra protection on
  PostgreSQL.
- SQLite case-insensitive matching is ASCII-only; usernames are stored
  already normalized, so lookups compare normalized values exactly.
- UUID fields are text on SQLite and native on PostgreSQL; only equality is
  used.

---

# Gate-by-Gate Implementation Plan

Each gate: build; full suite on SQLite and PostgreSQL; `check`,
`makemigrations --check`, Ruff; migrations reversed and re-applied on both;
one commit, one PR, merge before the next gate. Bulk writes always preview
first and confirm idempotently. No account or guardian–Student match is ever
guessed.

## Gate 0 — Approved ADRs, requirements and implementation plan

Deliver ADR 0013, ADR 0014, this plan, REQUIREMENTS, DOMAIN_MODEL and
ROADMAP updates. Acceptance: planning PR approved; OD-1 answered before
Gate 4; OD-2 before Gate 6; OD-3/4/5/7 before Gate 7.

## Gate 1 — Guardian account links, explicit Student access grants and password change

Build: User changes and username constraint; `GuardianAccount`,
`GuardianStudentAccess`, `SecurityEvent`; administrator workflows on the
Guardian page: create account (verification recorded, normalized username,
temporary password shown once), link an existing login by exact username,
revoke link; grant/revoke access per recorded relationship; administrator
password reset; forced first-login password change.

Acceptance:
- no self-registration route exists; a recorded Guardian has no access
  until an administrator grants it per relationship;
- usernames differing only by case are refused by form and database on both
  databases;
- linking an existing teacher login creates no second account;
- temporary passwords are never stored in plain text, logged or rendered
  twice; first sign-in forces a change; reset ends existing sessions;
- links and grants cannot be deleted or rewritten (application and
  triggers); revocation is immediate, recorded and irreversible;
- every listed action writes the matching security event; no event contains
  a password.

## Gate 2 — Authorization boundary and application-wide access sweep

Build: `core.authorization` helpers (`is_guardian`, `guardian_account`,
`guardian_grants`, `guardian_can_view`), the INACTIVE-Student access review
inside the status-change workflow, and the extended sweep.

Acceptance:
- a guardian-only login receives 403 on every existing admin and teacher URL;
- a Student outside the user's active grants is 404 on every portal URL;
  revoked links, revoked grants, inactive logins and grants of other
  guardians are covered;
- making a Student INACTIVE shows every active grant and requires an
  explicit retain/revoke for each before saving; nothing is inferred; the
  decisions are audited; retained grants appear in a review list.

## Gate 3 — Guardian portal shell, child switcher and multi-role navigation

Build: `guardian/` area with its own templates and navigation; home listing
granted Students by opaque id; child switcher; area choice page and
role-aware navigation for multi-role logins; landing routing.

Acceptance:
- guardian-only logins land in the portal; multi-role logins see an explicit
  choice and links to every area they hold; nothing is hidden;
- portal URLs contain no database ids; constant query count as Students and
  grants grow; fees and announcements appear nowhere.

## Gate 4 — Approved read-only Student profile

Build: profile with exactly the P7 fields (plus OD-1 fields if approved,
with their administrator entry).

Acceptance: field-level tests prove date of birth, Student phone/email,
other guardians, internal ids and staff-only data never render; POST is
refused; historical placements shown only while the grant is active.

## Gate 5 — Submitted attendance history and summary

Build: per-Academic-Year history of SUBMITTED dates with current status and
the Phase 2 summary.

Acceptance: drafts, absence notes, correction history and correctors never
render; a correction shows only the corrected value; missing attendance is
never shown as absent; results match `reports.student_summary`; constant
query count.

## Gate 6 — Explicit Term publication and guardian report-card view

Build: `TermPublication`, `TermPublicationResult`; administrator preview →
confirm per Term + Section; stale marking in result correction and remark
edits; stale review list; withdraw; guardian report-card view.

Acceptance:
- finalized but unpublished results never render in the portal;
- the preview lists every Student with exact results or a skip reason;
  nothing is written before confirmation; a stale token writes nothing;
  confirming twice publishes nothing new;
- a correction or remark change makes that Student's Term hidden in the same
  transaction; a fingerprint mismatch from any other path also hides it;
  republishing creates version n+1 and keeps history;
- publication rows cannot be deleted or rewritten (triggers).

## Gate 7 — Authentication, throttling, sessions, revocation and privacy hardening

Build: throttled sign-in (§8), generic errors, lockout clearing,
session-version bumps on deactivation and link revocation, production cookie
and HTTPS settings, `no-store` on credential pages, OD-4 site-administration
restrictions.

Acceptance: Rule A and Rule B proven with fixed clocks; expiry and admin
clearing work; error messages identical for unknown user, wrong password and
throttled; deactivation, reset and link revocation end sessions;
`check --deploy` clean with production settings; logs and events contain no
passwords or page content.

## Gate 8 — End-to-end integration, database protections and migration verification

End-to-end journey: admin verifies a guardian and creates the account →
offline password → forced change → grant one of two children → portal shows
one child only → submitted attendance visible, draft hidden → Term results
finalized but hidden → preview and publish → report card visible → result
corrected → Term hidden → republish → link revoked → access gone, history
intact. Plus a teacher-who-is-a-parent journey, cross-family isolation,
trigger tests for every protected table, migration forward/backward on both
databases, query counts.

## Gate 9 — Documentation closeout and phase-6-complete release

README, ROADMAP, REQUIREMENTS, DOMAIN_MODEL, ADR status, completion table;
release notes include the one-time session reset and rollback/export note.
The `phase-6-complete` tag is created by the product owner via a GitHub
release. Recommendation on deleting `planning/future-phases` is made here,
not acted on without approval (P14).

---

# Stop-and-return-to-planning conditions

- Student logins or any Student-facing view (Phase 6B)
- email, SMS or any external delivery; self-service password recovery
- guardian editing or change requests
- fee visibility or fee data
- announcements or messaging
- PDF/downloadable documents
- assessment-level or immediate-on-finalize publication
- automatic grants or matching by relationship type, phone, email or name
- page-view logging or analytics
- new infrastructure (Redis, Celery, external auth providers)

# Unresolved technical risks

1. Existing case-only duplicate usernames would stop the Gate 1 migration;
   resolving them is a manual administrator decision.
2. Client address behind a reverse proxy: a wrong trusted-proxy setting
   either throttles everyone together or lets clients spoof addresses (OD-3).
3. Rule B can be used to lock a known guardian username for 15 minutes;
   mitigated by Rule A being primary, the higher threshold and admin clearing.
4. Introducing `session_version` logs every user out once at deployment.
5. Write paths outside the ERP (site administration, shell, future code)
   could change results, remarks or passwords without the stale/audit side
   effects; the render-time fingerprint check and OD-4 restrictions limit the
   impact, but the shell remains trusted.
6. The fingerprint must depend only on stored values; any change to its
   serialization needs a new scheme number, or every publication turns stale.
7. "Leaving" is modelled only by Student INACTIVE status (Phase 1). A Student
   whose enrollment ends without a status change triggers no access review.
8. P7 fields admission number and roll number do not exist (OD-1).
9. One grant per relationship means data-entry effort for the whole school
   (OD-6); there is deliberately no bulk path.

# Phase 6 completion principle

Phase 6 is complete when an administrator can verify, create and link a
guardian account, grant access to specific Students, and publish Term results
through a preview; the guardian can sign in safely and see only those
Students' approved profile, submitted attendance and published report cards;
nothing released changes silently; every account, access and publication
change is audited; and no record of who could see what is ever deleted.
