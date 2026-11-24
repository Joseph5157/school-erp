# G-06 spec: improved office password reset (ADR 0029, option A)

- **Status:** **Draft r1**, 2026-11-24, for product-owner decisions (§12) and a security-focused review
  (ADR 0029 "What would make this acceptable", item 3). Approves no code until accepted.
- **Baseline:** `origin/main` 06d8eeb (never-signed-in list, PR #303, merged).
- **Risk tier:** **Critical** (password and account recovery, authentication and sessions,
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3).
- **Design source:** [ADR 0029](../adr/0029-guardian-account-recovery.md) Decision 1 (option A), Accepted
  2026-11-23 with OD-G1 to OD-G16 as recommended. Threat model:
  [G06_RECOVERY_THREAT_MODEL.md](G06_RECOVERY_THREAT_MODEL.md). This spec does not reopen those decisions;
  it turns them into code-level rules and asks only the questions they leave open (§12).
- **Not in this spec:** the "Can't sign in?" request page (option G, ADR 0029 Decision 2). It gets its own
  Critical spec after this one ships, because it adds the only anonymous route and a purge job. Channels
  (email, SMS, WhatsApp) stay deferred (OD-G2).
- **Already done:** R16 (reset clears lockout) and R19 (new password must differ) shipped in PR #302.

## 1. Outcome

When a guardian cannot sign in, the office can reset the password with a record of who did it, how
identity was checked, and when. The temporary password expires. A phone number that changed recently
cannot support a weaker check. After signing in, the guardian sees that the school reset the password.
Every write to a guardian's phone or email leaves an audit event. The never-signed-in list gets its
"Reset password" link.

## 2. Requirements covered

| ADR 0029 | Where in this spec |
| --- | --- |
| R2 entropy (12 characters over 31 symbols, `secrets`) | unchanged, `generate_temporary_password` (`core/guardian_accounts.py`); a test pins it (§10) |
| R3 expiry, backfill, deploy step | §5 (PR 3) |
| R4 single use | §5.4 |
| R5 hashed, shown once, `no-store` | unchanged (`_credential_slip`, `core/views.py:4125-4134`); a test pins it |
| R7 generic responses | §5.3 |
| R8 sessions end, forced change | unchanged (`reset_guardian_password`); a test pins it |
| R9 informational reset notice | §4.5 |
| R10 audit events (reset with method, first sign-in after reset, expiry, lockout cleared, contact changed) | §3, §4, §5 |
| R11 no grant changes | §4.1; test |
| R12 CSRF, frame denial | site-wide; tests on the changed route |
| R13 logging hygiene | §9; test |
| R14 route inventory | §8 (no new route) |
| R15 privileged logins excluded | unchanged (`is_portal_manageable`); test |
| R17 contact changes audited at one choke point | §3 (PR 1) |
| R18 callback rules, phone-change window | §4.1, §4.3 |
| OD-G7 named staff only | §6 |
| OD-G8 reset is HISTORY | §4.2, §9 |
| OD-G16 method choice, "Other" note in a deletable table | §4.1, §4.4 |

## 3. PR 1: contact changes are audited (R17)

**Event.** New `SecurityEvent.EventType.GUARDIAN_CONTACT_CHANGED` ("Guardian contact details changed"),
HISTORY class. `detail = {"fields": ["phone"]}`, `["email"]` or both. Never the old or new value (R10;
`SecurityEvent` docstring, `accounts/models.py:60-66`). `guardian` is set; `actor` is the signed-in user,
or none for management commands.

**One choke point.** A service function `core.guardian_records.save_guardian(guardian, *, actor)` reads the
stored row under `select_for_update` inside `transaction.atomic`, compares `phone` and `email`, saves, and
records one event if either changed. Creating a guardian with a phone or email counts as a change from
empty. Every write path calls it:

| Path | Today |
| --- | --- |
| `guardian_create` (`GuardianForm`, `core/views.py:3619`) | `form.save()` |
| `guardian_edit` (`GuardianForm`, `core/views.py:3641-3651`) | `form.save()` |
| Bulk import (`core/imports.py:779`) | `Guardian.objects.create(...)` with phone and email |
| Demo seeds (`seed_demo.py:199`, `seed_school_demo.py:175`; `refresh_demo_school` calls the latter) | `Guardian.objects.create(...)`; switch to the service with `actor=None` |

Adding a guardian to an applicant or a student links an existing record and writes no contact field.

A test keeps the list honest: it scans `core/` (excluding tests and migrations) for
`Guardian.objects.create`, `GuardianForm(` saves and `.phone =`/`.email =` on guardians, and fails if a call
site is not in its allow-list. `Guardian` stays unregistered in the Django admin (`core/admin.py:3`); a test
asserts it is not in `admin.site._registry`.

**Shown where.** The guardian profile's "Account and access history" already lists HISTORY events for
holders of `accounts.view_securityevent` (`core/views.py:3774-3787`). The new event appears there as
"Contact details changed (phone)" with actor and date.

**Risk:** High (audit trail, guardian data). Migration: `SecurityEvent.event_type` choices only.

## 4. PR 2: the improved reset (option A)

### 4.1 Reset form

The confirm page `core/guardian_reset_confirm.html` (view `guardian_account_reset_password`,
`core/views.py:4257-4281`) becomes a form:

| Field | Values | Rule |
| --- | --- | --- |
| How was identity checked? | **In person, with identity documents** (`IN_PERSON_DOCUMENTS`); **Other** (`OTHER`) | required radio, no default |
| Note | text, max 100 characters | required for Other, refused otherwise; help text "No phone numbers, addresses or other personal details." |
| Confirmation | checkbox "I checked this person's identity myself" | required |

"Callback to the number on record" is **not** a method. Under OD-G3 (b) the callback only books a visit;
the reset happens at the visit, where the method is "In person, with identity documents" (ADR 0029
Appendix A, step 6). "Known to staff" is not offered (OD-G3 (d)). The page shows Appendix A as a short
checklist above the form.

POST keeps today's guards: `administrator_required("core.reset_guardian_password")`, the one-time token
(`one_time_forms`), and `is_portal_manageable` inside the service. It never touches grants (R11).

The service becomes `reset_guardian_password(*, account, actor, method, note="")` and validates method and
note itself, so no caller can skip the rules.

### 4.2 Reset event

`PASSWORD_RESET_BY_ADMIN` leaves `SecurityEvent.ROUTINE_TYPES` (`accounts/models.py:103-112`), so new reset
events are HISTORY (OD-G8). Existing events keep their stored class (ADR 0029 Consequences); a test pins
that an old ROUTINE row is untouched. `detail = {"method": "<choice>"}`. The note is **not** in `detail`
(§4.4). Once HISTORY, the event shows on the guardian profile history.

### 4.3 Recent phone change (R18, OD-G13)

If a `GUARDIAN_CONTACT_CHANGED` event naming `phone` exists for this guardian in the last 30 days, or PR 1
was deployed less than 30 days ago (OD-R3), the form shows "This guardian's phone number changed on
<date>. Reset only after checking identity documents in person." and offers only **In person, with identity
documents**. The service enforces the same rule. The check reads events only, never the phone value. The
date of PR 1's deploy is the time of its migration, read from `django_migrations`.

### 4.4 "Other" note storage (OD-G16)

New model `accounts.ResetNote`: `event` (one-to-one to `SecurityEvent`, `on_delete=PROTECT`), `note`
(CharField, 100), `created_at`. It is a separate table because events are append-only and HISTORY events
are never deleted (`accounts/models.py:60-66`), while the note must be deletable. `purge_security_events`
(`accounts/management/commands/purge_security_events.py`) also deletes notes older than 365 days (OD-R5).
The note shows on the guardian profile history next to its event, for `accounts.view_securityevent`
holders, autoescaped.

### 4.5 Reset notice in the portal (R9)

On the guardian portal home (`core/portal_views.py:85`, `portal/home.html`): when the signed-in login's
latest `PASSWORD_RESET_BY_ADMIN` event is under 30 days old, show an info note: "Your password was reset by
the school on <date>. If you did not ask for this, contact the school office." It is informational only.
There is no "this was not me" button, and no text calls it detection or notification (R9; threat model
T10). One query on `subject_user` and `occurred_at`.

### 4.6 First sign-in after reset (R10)

New event `FIRST_SIGN_IN_AFTER_RESET`, HISTORY. Recorded in the sign-in success path
(`accounts/forms.py:63`, next to `LOGIN_SUCCEEDED`) when the login's temporary-password kind is `RESET`
(§5.1) and no such event exists since the issue time. No detail beyond actor and subject.

### 4.7 Teacher resets

Unchanged in this spec except expiry (§5, OD-R1). Teacher reset already ends sessions, forces a change and
clears lockouts (PR #302).

**Risk:** Critical. Migrations: `ResetNote`; event-type choices; the group data migration (§6).

## 5. PR 3: temporary passwords expire (R3)

### 5.1 Fields

On `accounts.User`: `temporary_password_issued_at` (DateTimeField, null) and `temporary_password_kind`
(CharField, choices `CREATED`/`RESET`, blank). Set in the same `save` that sets `must_change_password` in
`create_guardian_account`, `reset_guardian_password`, and (OD-R1) `create_teacher` and
`reset_teacher_password`. Cleared with `must_change_password`, in the one `update()` of
`PasswordChangeView.form_valid` (`accounts/views.py:130-143`). `link_existing_login` issues no password and
sets nothing.

### 5.2 Windows (OD-G5)

| Kind | Window |
| --- | --- |
| `CREATED` (account slip) | 14 days |
| `RESET` (office reset) | 72 hours |

Constants in `accounts/security.py`. They are not settings: nobody asked for per-install tuning.

### 5.3 Enforcement

In `NormalizedUsernameBackend.authenticate` (`accounts/backends.py:15-33`), after `check_password` and
`user_can_authenticate` pass: if `must_change_password` is set and the issue time plus the window is in the
past, return `None`. The sign-in form then shows its generic error (`accounts/forms.py:10`): the same text,
status and template as a wrong password (R7). The failure counts toward throttling as today. A test asserts
the expired response equals the wrong-password response (status, template, message).

The only extra work on that path is the one-time expiry event (§5.5). It shows nothing to the person
signing in, and only someone who already holds the temporary password can trigger it.

A session that is already signed in is not cut off by expiry: the forced change still applies to it
(`accounts/middleware.py:177-180`), and a reset has already ended older sessions (R8).

### 5.4 Single use (R4)

A temporary password is one Django password hash. A new reset replaces it (`set_password`), so the older one
stops working; a successful change replaces it again. A test pins both.

### 5.5 Expiry event

New event `TEMPORARY_PASSWORD_EXPIRED`, HISTORY, recorded the first time an expired temporary password is
presented for a login (at most once per issue time). Detail: `{"kind": "CREATED"}` or `{"kind": "RESET"}`.

### 5.6 Backfill and deploy step

Data migration: every login with `must_change_password = True` and no issue time gets
`issued_at = <migration time>` and `kind = CREATED` (the longer window), including resets issued before
deploy whose kind was never recorded (R3). Reverse: clear both fields.

**Before expiry is switched on** (§7) the office runs the never-signed-in list (both chips) and re-issues
slips or calls families, so slips do not expire silently (R3; never-signed-in spec §12a).

**Risk:** Critical. Migration: two fields plus the reversible backfill.

## 6. Named staff only (OD-G7)

Today `core.reset_guardian_password` is in the School Administrators group
(`core/migrations/0043_add_guardian_account_permissions_to_group.py:13`), so every administrator can reset.

A data migration in PR 2 creates the group **"Portal password resets"** holding only
`core.reset_guardian_password`, and removes that permission from School Administrators. Superusers keep
every permission (Django default). A superuser sets membership in the Django admin, where `User` is
registered (`accounts/admin.py:59`). The reverse migration puts the permission back on School
Administrators and deletes the group.

**Deploy step:** the owner names the staff (OD-R2) before PR 2 reaches staging; right after deploy a
superuser adds them. Until then only superusers can reset.

## 7. Staged rollout and rollback (ADR 0029 item 4)

| Step | What | Rollback |
| --- | --- | --- |
| PR 1 | Contact audit, alone. | Revert. Old rows keep the event type harmlessly (choices only). |
| PR 2 | Reset form, HISTORY class, notes, notice, first-sign-in event, named-staff group. | Revert the code; the reverse migration restores the group permission and drops `ResetNote`. HISTORY events written meanwhile stay (append-only by design). |
| PR 3 code | Fields and backfill, enforcement **off** behind the environment flag `TEMP_PASSWORD_EXPIRY` (default off). Issue times are recorded from deploy. | Revert; the reverse migration drops the fields. |
| PR 3 switch-on | After the never-signed-in run (§5.6): flag on in staging, check, then production. | Unset the flag. No data change. |
| PR 4 | "Reset password" link on the never-signed-in list (that spec's §5), shown with `core.reset_guardian_password`. | Revert. |

The flag is the only new setting. A later PR removes it once expiry has run on production for a term.

**Data recovery.** No migration deletes or rewrites existing rows except the reversible backfill. Take a
staging database backup before PR 3 (daily backups already run on staging).

## 8. Routes

No new route. Changed: `core:guardian-account-reset-password` becomes a form with the same guard; POST stays
one-time. Regenerate `core/tests/route_permissions.json` only if its inner permissions change.

## 9. Privacy, logging and retention (R13)

- Never logged, measured or alerted: the temporary password, the note, phone or email values, typed
  usernames beyond what `LOGIN_FAILED` already stores.
- Tests capture logs on a reset, an expired sign-in and a contact change, and assert that none of the
  password, note, phone or email appear.
- Reset events are HISTORY and permanent (OD-G8) **subject to counsel** (OD-G11; ADR 0029 item 5). PR 2 may
  reach staging before counsel answers. It must not reach production until counsel confirms, or the owner
  keeps resets ROUTINE.

## 10. Tests (minimum)

**PR 1:** a form edit of the phone records one event naming `phone` and no value; email likewise; no event
when neither changes; the import and seed paths record events (seed with no actor); `Guardian` is not in the
admin; call-site allow-list test.

**PR 2:** method required; Other needs a note and In person refuses one; a note over 100 characters is
refused; the service refuses a bad method without the form; a recent phone change removes Other and the
service refuses it; the first 30 days after PR 1 count as recent; a new reset is HISTORY with
`{"method": …}` and no note in `detail`; old ROUTINE resets unchanged; the note is stored in `ResetNote`,
shown autoescaped and purged after 365 days; portal notice shown within 30 days and absent after; first
sign-in after reset recorded once; grants unchanged (R11); privileged login refused (R15); sessions ended
and change forced (R8); slip `no-store` (R5); a School Administrator outside the new group gets 403, a
group member and a superuser get 200; generator still 12 of 31 symbols (R2); CSRF and
`X-Frame-Options: DENY` on the route (R12).

**PR 3:** flag off: an expired temporary password still signs in; flag on: `CREATED` expires after 14 days
and `RESET` after 72 hours (frozen time); same response as a wrong password; one expiry event per issue; a
new reset makes sign-in work again; a password change clears both fields; backfill sets `CREATED` and the
migration time, and its reverse clears them; teacher create and reset set the fields (OD-R1);
`link_existing_login` sets nothing.

**Every PR:** `ruff check .`; `makemigrations --check --dry-run` clean after the PR's own migration; route
inventory test; targeted tests for accounts, guardian accounts, teacher accounts and portal home; full CI
on the final head.

## 11. Acceptance checklist

- [ ] Owner decisions OD-R1 to OD-R5 recorded (§12).
- [ ] Security-focused review of this spec done and findings applied (ADR 0029 item 3).
- [ ] PR 1 merged; contact edits appear in guardian history on staging.
- [ ] Named staff chosen; PR 2 merged; group membership set on staging; reset form checked at 360, 390 and
      desktop.
- [ ] PR 3 merged with the flag off; never-signed-in run done; flag on in staging; expiry checked.
- [ ] PR 4 merged; link shown only to group members and superusers.
- [ ] Counsel answer on HISTORY retention before production (ADR 0029 item 5).

## 12. Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-R1 | Teacher temporary passwords | Expire like guardians (same fields and windows); leave teachers unchanged | Expire like guardians: same login model and backend, and a teacher slip is the same kind of bearer secret. The teacher reset form is otherwise unchanged. |
| OD-R2 | Who is in "Portal password resets" at launch | Names from the owner | Two named office staff, so resets do not stop when one is away; superusers in addition |
| OD-R3 | Phone history before PR 1 is unknown | Treat as "not changed" (fail open); treat the first 30 days after PR 1 as "recently changed" (fail closed) | Fail closed. For those 30 days only "In person, with identity documents" is accepted, which is what the office does anyway. |
| OD-R4 | How expiry is switched on | At once on deploy; behind an environment flag, switched on after the never-signed-in run | Behind the flag (§7) |
| OD-R5 | "Other" note retention | Keep forever with the event; delete after 365 days with the routine purge | Delete after 365 days |

## 13. Out of scope

- The request page and its purge (option G): the next spec.
- Any channel, owner notification or verified contact data (OD-G2, OD-G10).
- Two-person approval for resets (OD-G7 "later option").
- Changing how accounts are created, beyond recording the issue time.
- Staff logins other than teachers: managed in the Django admin (`is_portal_manageable`).
