# G-06 spec: improved office password reset (ADR 0029, option A)

- **Status:** **Draft r3**, 2026-11-24. r2 was approved for build (PR #304): OD-R1 to OD-R5 as recommended,
  review choices S-01 (a), S-03 option A, S-07 one-hour grace; r2 applied the security-focused review of r1
  (S-01 to S-19, N-1 to N-4; ADR 0029 item 3). **r3** adds the "Password reset staff" page (§6a, PR 2b) so
  the school chooses reset staff in the app instead of naming them before PR 2 (OD-R2 revised, OD-R6).
  Each build PR is still Critical tier.
- **Baseline:** `origin/main` 06d8eeb (never-signed-in list, PR #303, merged).
- **Risk tier:** **Critical** (password and account recovery, authentication and sessions,
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3).
- **Design source:** [ADR 0029](../adr/0029-guardian-account-recovery.md) Decision 1 (option A), Accepted
  2026-11-23 with OD-G1 to OD-G16 as recommended. Threat model:
  [G06_RECOVERY_THREAT_MODEL.md](G06_RECOVERY_THREAT_MODEL.md). This spec turns those decisions into
  code-level rules and records the questions they left open (§12).
- **One deviation from ADR 0029, owner-approved (§12, S-03):** OD-G8 made reset events HISTORY (permanent)
  "subject to the DPDP retention check", and OD-G11 put legal review before HISTORY retention. The school has
  no counsel, so **every event this spec adds or changes stays ROUTINE (365 days)**. Moving them to HISTORY
  is a later, separate PR, made only after counsel confirms (§9).
- **Not in this spec:** the "Can't sign in?" request page (option G). It gets its own Critical spec after
  this one ships. Channels stay deferred (OD-G2).
- **Already done:** R16 (reset clears lockout) and R19 (new password must differ), PR #302.

## 1. Outcome

When a guardian cannot sign in, the office resets the password with a record of who did it, how identity
was checked, and when. Only named staff can reset, and the same rules apply when a revoked login is
replaced. Temporary passwords expire, and a used slip stops working an hour after its first use. A phone
number that changed recently cannot support a weaker check. After signing in, the guardian sees that the
school reset the password. Every write to a guardian's phone or email leaves an audit event. The
never-signed-in list shows expired slips and gets its "Reset password" link.

## 2. Requirements covered

| ADR 0029 | Where |
| --- | --- |
| R2 entropy (12 characters over 31 symbols, `secrets`) | unchanged `generate_temporary_password` (`core/guardian_accounts.py`); test (§10) |
| R3 expiry, backfill, deploy step | §5 (PR 3). R3's 1-hour expiry for callback-delivered passwords does not apply: OD-G3 (c) was rejected. |
| R4 single use | §5.4: a new password replaces the old; a used slip stops working one hour after first sign-in (owner choice, §12) |
| R5 hashed, shown once, `no-store` | unchanged `_credential_slip` (`core/views.py:4125-4134`); test |
| R7 generic responses | §5.3 |
| R8 sessions end, forced change | unchanged `reset_guardian_password`; test |
| R9 informational reset notice | §4.5 |
| R10 audit events | §3, §4, §5; retention ROUTINE by owner choice (§9) |
| R11 no grant changes | §4.1, §4.8; test |
| R12 CSRF, frame denial | site-wide; tests on changed routes |
| R13 logging hygiene | §9; test |
| R14 route inventory | §8 |
| R15 privileged logins excluded | unchanged `is_portal_manageable`; test |
| R17 contact changes audited at one choke point | §3 (PR 1), enforced in the model |
| R18 callback rules, phone-change window | §4.1, §4.3, §4.8 |
| OD-G7 named staff only | §6, §4.8 |
| OD-G8 HISTORY | deviation: ROUTINE until counsel (§9) |
| OD-G16 method choice, "Other" note in a deletable table | §4.1, §4.4 |

## 3. PR 1: contact changes are audited (R17)

**Events.** Two new event types, one per field so the query needs no JSON lookup (SQLite has no JSON
`contains`; `config/settings.py` falls back to SQLite without `DB_NAME`):
`GUARDIAN_PHONE_CHANGED` ("Guardian phone changed") and `GUARDIAN_EMAIL_CHANGED` ("Guardian email changed").
ROUTINE (§9). `guardian` set; `actor` the signed-in user, or none for commands. Never the old or new value
(R10; `accounts/models.py:60-66`). One more type, `CONTACT_AUDIT_STARTED`, ROUTINE, is written once by PR 1's
data migration as the anchor for §4.3.

**Choke point in the model.** R17 allows "the model's save":

- `Guardian.from_db` keeps a snapshot of `phone` and `email`. `Guardian.save(*args, actor=None,
  audit=True, **kwargs)` saves, then, when `audit` is true, records one event per field that differs from
  the snapshot (a new guardian with a phone or email counts as a change from empty). Save and events run in
  one `transaction.atomic`.
- `GuardianQuerySet.update()` and `bulk_update()` raise `ValueError` when `phone` or `email` is among the
  fields; `bulk_create()` raises when any object has a phone or email. No production path uses them today.
- `audit=False` is allowed only in the demo seeds (`seed_demo.py:199`, `seed_school_demo.py:175`, used by
  the daily `refresh_demo_school`). Otherwise the daily refresh would write an event for every demo
  guardian every day.
- Callers that know the user pass `actor`: `guardian_create` (`core/views.py:3619`) and `guardian_edit`
  (`core/views.py:3641-3651`) call `form.save(commit=False)` then `guardian.save(actor=request.user)`;
  bulk import (`core/imports.py:779`) passes the importing user.
- Adding a guardian to an applicant or a student links an existing record and writes no contact field.
- A second-layer test scans non-test `core/` code for `audit=False`, `.update(` and `bulk_` on `Guardian`
  and fails on any call site outside its allow-list. `Guardian` stays out of the Django admin
  (`core/admin.py:3`); a test asserts it is not in `admin.site._registry`.
- Existing tests that write the phone with `.update(phone=...)` switch to `save()`:
  `core/tests/test_phase7_notifications.py:256`, `core/tests/test_security_gate4b_bundles.py:31`.

**Shown where.** The guardian profile history today lists HISTORY events only, capped at 50
(`core/views.py:3774-3777`). PR 1 changes it to list the guardian's HISTORY events **plus** these ROUTINE
types tied to the guardian: phone changed, email changed, password reset, first sign-in after reset,
temporary password expired. It is paginated with `build_table` (25 per page), so many contact edits cannot
push resets out of view. Same permission as today (`accounts.view_securityevent`).

**Risk:** High. Migration: event-type choices and the anchor event (reverse deletes nothing: events are
append-only; the anchor is harmless).

## 4. PR 2: the improved reset (option A)

### 4.1 Reset form

The confirm page `core/guardian_reset_confirm.html` (view `guardian_account_reset_password`,
`core/views.py:4257-4281`) becomes a form:

| Field | Values | Rule |
| --- | --- | --- |
| How was identity checked? | **In person, with identity documents** (`IN_PERSON_DOCUMENTS`); **Other** (`OTHER`) | required radio, no default |
| Note | text, max 100 characters | required for Other, refused otherwise; refused if it contains 6 or more digits in a row or "@"; help text "No phone numbers, addresses or other personal details." |
| Confirmation | checkbox "I checked this person's identity myself" | required |

"Callback to the number on record" is not a method: under OD-G3 (b) the callback only books a visit, and at
the visit the method is "In person, with identity documents" (ADR 0029 Appendix A, step 6). "Known to staff"
is not offered (OD-G3 (d)). Appendix A shows as a short checklist above the form.

**Order in the view (S-11):** validate the form first; on errors, re-render with a fresh
`one_time_forms.token_for`. Only a valid form reaches `one_time_forms.is_repeat` (which uses up the token,
`core/one_time_forms.py:30-42`), the same order as `guardian_account_create` (`core/views.py:4142-4143`).
Guards stay: `administrator_required("core.reset_guardian_password")`, the one-time token, and
`is_portal_manageable` in the service. Grants are never touched (R11).

**Service.** `reset_guardian_password(*, account, actor, method, note="")` validates method and note itself.
In one `transaction.atomic` it locks the **Guardian row first, then the account** (S-10; every service in
this spec takes locks in that order), reads the phone window (§4.3), then resets.

### 4.2 Reset event

`PASSWORD_RESET_BY_ADMIN` stays ROUTINE (§9). `detail = {"method": "<choice>"}`; the note is not in
`detail` (§4.4). It shows on the guardian profile history (§3).

### 4.3 Recent phone change (R18, OD-G13, OD-R3)

"Recent" means: a `GUARDIAN_PHONE_CHANGED` event for this guardian in the last 30 days, **or** the
`CONTACT_AUDIT_STARTED` anchor is less than 30 days old (history before PR 1 is unknown; fail closed). If
the anchor no longer exists (purged after 365 days), only the events count. One function,
`guardian_records.phone_changed_recently(guardian, now)`, answers it; tests patch it or create events.

When recent, the form shows "This guardian's phone number changed on <date>. Reset only after checking
identity documents in person." (or "Phone changes are only recorded since <anchor date>." in the first 30
days) and offers only **In person, with identity documents**. If the person who changed the phone is the
person resetting, the warning adds "You changed this number." The service enforces the same rule.

### 4.4 "Other" note storage (OD-G16, OD-R5)

New model `accounts.ResetNote`: `event` (one-to-one to `SecurityEvent`, `on_delete=PROTECT`), `note`
(CharField 100), `created_at`. Created in the same `atomic` as the event. It is a separate table so the note
can be deleted on its own schedule. `purge_security_events` deletes notes older than 365 days. That command
needs an authorizing operator (`--by`, `accounts/management/commands/purge_security_events.py:24-30`), so it
cannot run from cron unattended; the runbook (`docs/` operations notes) gets a monthly line for it. Shown on
the guardian profile history next to its event, autoescaped.

### 4.5 Reset notice in the portal (R9)

On the guardian portal home (`core/portal_views.py:85`, `portal/home.html`): when the signed-in login's
latest `PASSWORD_RESET_BY_ADMIN` event is under 30 days old, an info note: "Your password was reset by the
school on <date>. If you did not ask for this, contact the school office." Informational only. No "this was
not me" button, and no text calls it detection or notification (R9; threat model T10). One query.

### 4.6 First sign-in after reset (R10)

New event `FIRST_SIGN_IN_AFTER_RESET`, ROUTINE. Recorded in the sign-in success path (`accounts/forms.py:63`,
next to `LOGIN_SUCCEEDED`) only when all hold: `must_change_password` is true, the temporary-password kind is
`RESET` (§5.1), the login has an active guardian account, and no such event exists since the issue time.
Guardians only; teacher sign-ins record nothing new. `guardian` is set from the active account. Check and
write share one transaction; two simultaneous sign-ins may write two events, which is harmless.

### 4.7 Teacher resets

Unchanged except expiry (§5, OD-R1). Teacher reset already ends sessions, forces a change and clears
lockouts (PR #302), and cannot reach a login with an active guardian link
(`core/teacher_accounts.py:55-57`).

### 4.8 Replacing a revoked login (S-01, owner choice (a))

Access grants belong to the Guardian, not the login (`guardian_grants`, `core/authorization.py:360-369`), so
revoking a login and creating a new one returns every child with a fresh temporary password. Today that
needs only `core.change_guardianaccount` (`core/views.py:4199`) and `core.add_guardianaccount`
(`core/views.py:4137`), which every School Administrator holds.

When the Guardian has **any revoked `GuardianAccount`**, `guardian_account_create` and
`guardian_account_link` (views and services) also require `core.reset_guardian_password` (the named group,
§6) and apply the reset rules: method only `IN_PERSON_DOCUMENTS` or `OTHER` with a note under §4.1's note
rules (not `EXISTING_RECORDS`), and only `IN_PERSON_DOCUMENTS` when the phone changed recently (§4.3). The
service enforces it; the view hides the create and link buttons from users without the permission and says
why. A guardian with no revoked login is created as today.

**Risk:** Critical. Migrations: `ResetNote`; event-type choices; the group data migration (§6).

## 5. PR 3: temporary passwords expire (R3)

### 5.1 Fields

On `accounts.User`:

| Field | Type | Meaning |
| --- | --- | --- |
| `temporary_password_issued_at` | DateTimeField, null | when the current temporary password was issued |
| `temporary_password_kind` | CharField `CREATED`/`RESET`, blank | which window applies |
| `temporary_password_first_used_at` | DateTimeField, null | first successful sign-in with it (§5.4) |

Set (issued and kind; first-used cleared) in the same `save` that sets `must_change_password` in
`create_guardian_account`, `reset_guardian_password`, and (OD-R1) `create_teacher` and
`reset_teacher_password`. `link_existing_login` issues no password and sets nothing. All three are cleared
with `must_change_password` in `PasswordChangeView.form_valid` (`accounts/views.py:130-143`), in one
`update()` filtered on the issue time read before the change (N-2), so a reset that lands in between is not
cleared by the older request.

### 5.2 Windows (OD-G5)

| Kind | Window |
| --- | --- |
| `CREATED` (account slip) | 14 days |
| `RESET` (office reset) | 72 hours |
| After first sign-in | 1 hour from first use, if that ends sooner (§5.4) |

Constants in `accounts/security.py`.

### 5.3 Enforcement

**Switch (S-02, S-18).** Environment setting `TEMP_PASSWORD_EXPIRY_FROM`: an ISO 8601 date-time with time
zone, parsed strictly at start-up like `config/deployment_safety.parse_flag` does for flags. Unset means
expiry is off. A value that does not parse stops start-up with a clear error; it never silently means "off".

**Rule.** Expiry applies only when expiry is on **and** `must_change_password`, `issued_at` and `kind` are
all set. If any is missing the password does not expire, and the code never raises (S-04). Otherwise:

```
start   = max(issued_at, TEMP_PASSWORD_EXPIRY_FROM)
expires = start + window(kind)
if first_used_at: expires = min(expires, first_used_at + 1 hour)
```

Counting from the later of the issue time and the switch-on time gives every slip outstanding at switch-on a
full window, so switching on never expires old slips at once (S-02).

**Where.** In `NormalizedUsernameBackend.authenticate` (`accounts/backends.py:15-33`), after
`check_password` and `user_can_authenticate` pass: if expired, return `None`. This is the only backend
(`config/settings.py`), and the Django admin sign-in uses it, so expiry covers `/admin/login/` too. The form
shows its generic error (`accounts/forms.py:10`), the same text, status and template as a wrong password
(R7), and the failure counts toward throttling as today. Only someone holding the right temporary password
can reach this path, so it reveals nothing to anyone else.

A session already signed in is not cut off: the forced change applies to it
(`accounts/middleware.py:177-180`), and a reset has already ended older sessions (R8).

### 5.4 Single use (R4, owner choice)

A new reset replaces the hash (`set_password`), so the older password stops working; a successful change
replaces it again. On the first successful sign-in with a temporary password the backend sets
`first_used_at` (when it is empty, in one filtered `update()`). The slip then works for at most one more hour,
so a guardian who loses signal can sign in again and finish, but a slip left behind stops working. The
forced change at first sign-in is unchanged.

### 5.5 Expiry event

New event `TEMPORARY_PASSWORD_EXPIRED`, ROUTINE, recorded when an expired temporary password is presented and
no such event exists for this issue time. `detail = {"kind": …}`; `guardian` set from the active account,
if any. Simultaneous attempts may write two; that is harmless (S-19).

### 5.6 Backfill and deploy step

Data migration: every login with `must_change_password = True` and no issue time gets
`issued_at = <migration time>` and `kind = CREATED`, including resets issued before deploy whose kind was
never recorded (R3). Only guardian and teacher services set that flag, so staff logins are not touched.
Reverse: clear the three fields.

**Before switch-on** (§7) the office runs the never-signed-in list (both chips) and re-issues slips or calls
families. Because of §5.3's rule, every slip still gets 14 days (or 72 hours) from the switch-on time.

### 5.7 What the office and guardian see (S-17)

- **Slip page:** when expiry is on, "This password works until <date, time>." (the window from §5.3 at issue,
  ignoring first use).
- **Never-signed-in list:** an "Expired" badge on rows whose temporary password has expired (same rule,
  computed in the view from the three fields; no extra query). No new chip.

**Risk:** Critical. Migration: three fields plus the reversible backfill.

## 6. Named staff only (OD-G7, OD-R2)

Today `core.reset_guardian_password` is in the School Administrators group
(`core/migrations/0043_add_guardian_account_permissions_to_group.py:13`).

**Data migration (PR 2).**

- If a group named **"Portal password resets"** does not exist, create it with only
  `core.reset_guardian_password`. If it exists with exactly that permission, use it. If it exists with any
  other permission, stop with an error.
- Remove `core.reset_guardian_password` from School Administrators.
- Reverse: put the permission back on School Administrators; delete the group only if this migration created
  it (recorded in the migration by name and permission set) and it has no members.

**Membership** is in addition to School Administrators (members still need the guardian pages). It is set on
the "Password reset staff" page (§6a, PR 2b). Until PR 2b ships, a superuser can set it in the Django admin
(`accounts/admin.py:59`). Superusers keep every permission.

**Safety checks.**

- A Django system check warns (not an error, so test databases and fresh installs still start) when no active
  user can reset guardian passwords.
- `role_permission_gaps` (`core/management/commands/role_permission_gaps.py`) lists every active user and
  group holding `core.reset_guardian_password`, including direct user grants, for the periodic access review
  that T7 relies on.
- A test asserts no group other than "Portal password resets" holds the permission.
- `core/tests/test_authorization.py:137` pins the School Administrators permission set; PR 2 updates it.

**Deploy step:** none for names. After PR 2 deploys, only superusers can reset or replace a revoked login
until a superuser adds staff on the page (§6a) or, before PR 2b, in the Django admin (OD-R2).

## 6a. PR 2b: "Password reset staff" page (OD-R2, OD-R6)

**Outcome.** A superuser chooses, in the app, who may reset guardian passwords. Every change made on the page
is recorded. Ordinary administrators can see the list but cannot change it, so no one can add themselves.
This page is how OD-G7's "named staff" are named; there is no deploy step for names.

**Where.** Sidebar group "Access and security" (`core/navigation.py:55-59`), a new link "Password reset staff"
after "Sign-in lockouts". Shown to holders of `core.view_guardianaccount` and to superusers.

**Routes.**

| Name | Path | Method | Guard |
| --- | --- | --- | --- |
| `core:reset-staff` | `access/reset-staff/` | GET (`require_safe`) | `core.view_guardianaccount` |
| `core:reset-staff-add` | `access/reset-staff/add/` | POST (`require_POST`) | superuser only (403 otherwise) |
| `core:reset-staff-remove` | `access/reset-staff/<int:user_id>/remove/` | POST (`require_POST`) | superuser only (403 otherwise) |

Superuser-only is a small decorator `superuser_required` in `core/authorization.py` (login required, then
`PermissionDenied` unless `is_superuser`). It is deliberately not a permission: any permission can be put in a
group, and a School Administrators grant would then let admins add themselves (threat model T7; OD-R6).
Decorator order: `superuser_required` outermost, then `require_POST`, so a non-superuser gets 403 whatever
the method.

**Route inventory.** `core/tests/route_inventory.py` records the decorator as the flag `superuser_required`
with no permission. PR 2b adds `superuser_required` to `SCOPED_BY_OTHER_MEANS`
(`core/tests/test_security_gate4b_route_inventory.py:28`), so `test_no_route_is_public_by_accident` accepts
it; the routes are **not** added to `INTENTIONALLY_UNPERMISSIONED` (that list is for public pages). A test
asserts both POST routes carry the flag, so dropping the decorator fails CI.

**List page.**

- Members of "Portal password resets": name, username, added on and added by (from the latest
  `RESET_STAFF_ADDED` event for that user). When no such event exists (older than 365 days and purged, or
  added in the Django admin) the row says "Added more than a year ago or outside this page". Email addresses
  are never shown.
- Also listed, read-only, under "Can also reset": active superusers, and any active user or group holding
  `core.reset_guardian_password` directly (the same query as `role_permission_gaps`, §6). A direct grant shows
  "Granted outside this page. Remove it in the Django admin." so nothing is hidden.
- Empty group: "No staff can reset parent passwords. Only superusers can, until you add someone."
- For superusers only: an "Add staff" form and a "Remove" button per member. Others see the list without
  controls.

**Add.** One select of eligible users: active, in School Administrators, not a superuser (they can already
reset), not already a member, and with no active guardian account (`GuardianAccount` with `revoked_at` null).
Django-admin staff (`is_staff`) are excluded too, because `is_portal_manageable` treats them as privileged
(`core/guardian_accounts.py:43-60`). A teacher who is also a School Administrator is eligible: teacher resets
use a different permission. The service `reset_staff.add(user, *, actor)` re-checks eligibility after
`select_for_update` on the user, adds the user to the group, and records `RESET_STAFF_ADDED` (actor,
subject_user), all in one transaction. If the group does not exist the service fails with a clear error and
never creates it; only the PR 2 migration creates it.

A member who later stops being eligible stays in the group until removed. The list marks them "inactive",
"not an administrator", "Django admin staff" or "now has a parent login". Separately, `reset_guardian_password`
refuses when the actor's own login is the account being reset, so a member linked to a guardian account later
cannot reset their own password.

**Remove.** Reason as a choice: "Left the school", "Changed role", "Other". No free text, so no personal data
to guard. The view looks `<user_id>` up **among the group's current members** and returns 404 otherwise
(a superuser's id or a direct-grant holder's id is not a member). `reset_staff.remove(user, *, actor,
reason)` locks the user row (`select_for_update`), re-checks membership, removes it and records
`RESET_STAFF_REMOVED` with `detail = {"reason": "<choice>"}`, in one transaction. If the user is no longer a
member (two superusers at once) it changes nothing and records nothing. Remove only drops the group
membership: direct grants and superuser status are untouched. Removing the last member is allowed; the page
then shows the empty-group warning.

**Effect.** Membership changes apply from the next request: `request.user` is loaded fresh each request, so
Django's per-object permission cache does not carry over, and `accounts/request_cache.py` caches roles for one
request only. A removed member's open session gets 403 on the reset form at its next request, without being
signed out. No session ending is needed.

**Events.** `RESET_STAFF_ADDED` and `RESET_STAFF_REMOVED`, **ROUTINE** (S-03; owner confirmed for these two on
2026-11-24, option A). They must be added to `SecurityEvent.ROUTINE_TYPES`, because `class_for` defaults to
HISTORY (`accounts/models.py:140-144`); a test pins their class. The list page shows them as "Recent changes"
(last 20); `role_permission_gaps` prints them too.

**Safety test.** No group shipped by a migration grants a non-superuser `auth.change_user`,
`auth.change_group` or `auth.change_permission`, so no administrator can edit group membership in the Django
admin.

**Phone layout.** Members as stacked rows (`erp-table--stack`); the add form uses the compact filter pattern.
No new CSS component. Checked at 360, 390 and desktop.

**Risk:** Critical (roles and permissions). Migration: event-type choices only; no model change.

**Rollback.** Revert. Membership already set stays; a superuser can still edit it in the Django admin.

## 7. Staged rollout and rollback (ADR 0029 item 4)

| Step | What | Rollback |
| --- | --- | --- |
| PR 1 | Contact audit, profile history paging. | Revert. Events written stay (append-only, ROUTINE, purged after 365 days). |
| PR 2 | Reset form, notes, notice, first-sign-in event, revoked-login rule, named-staff group. | Revert; the reverse migration restores the group permission and drops `ResetNote`. **Rehearse the backward migration on a staging copy before merge.** |
| PR 2b | "Password reset staff" page. | Revert. Membership stays; edit it in the Django admin if needed. |
| PR 3 code | Fields and backfill. Expiry off (`TEMP_PASSWORD_EXPIRY_FROM` unset). Issue and first-use times recorded from deploy. | Revert; the reverse migration drops the fields. **Rehearse backward on a staging copy; back up staging and, when it exists, production before deploy.** |
| PR 3 switch-on | After the never-signed-in run: set `TEMP_PASSWORD_EXPIRY_FROM` in staging, check, then production. | Unset it. No data change. |
| PR 4 | "Reset password" link on the never-signed-in list (that spec's §5), shown with `core.reset_guardian_password`. | Revert. |

The switch is the only new setting. A later PR removes it, making expiry always on, one school term after
switch-on in production.

## 8. Routes

New routes only in PR 2b (§6a): `core:reset-staff`, `core:reset-staff-add` and `core:reset-staff-remove`,
each added to `core/tests/route_permissions.json` with its guard. Changed guards: `core:guardian-account-reset-password` becomes a form (same guard);
`core:guardian-account-create` and `core:guardian-account-link` check `core.reset_guardian_password` inside
the view for guardians with a revoked login. Regenerate `core/tests/route_permissions.json` for the new inner
permission.

## 9. Privacy, logging and retention (R13)

- Never logged, measured or alerted: the temporary password, the note, phone or email values, typed
  usernames beyond what `LOGIN_FAILED` already stores. POST data is already masked in crash reports
  (`PrivacyExceptionReporterFilter`, `config/settings.py`).
- Tests capture logs on a reset, an expired sign-in and a contact change, and assert none of the password,
  note, phone or email appear.
- **Retention (owner choice, S-03):** all events in this spec are ROUTINE, kept 365 days, then purged by
  `purge_security_events`. HISTORY rows can never be changed or deleted (database triggers,
  `accounts/models.py:60-66`), so nothing is written as HISTORY before counsel confirms. If counsel later
  confirms longer retention, one small PR moves the chosen types into HISTORY for new events only. Until then
  a dispute older than a year cannot be settled from these records; the owner accepted that.

## 10. Tests (minimum)

**PR 1:** form edit of the phone records one `GUARDIAN_PHONE_CHANGED` with no value; email likewise; none when
neither changes; create with a phone records one; import records events with the importer as actor; seeds
with `audit=False` record none; queryset `update`/`bulk_update`/`bulk_create` with contact fields raise;
call-site allow-list; `Guardian` not in the admin; the anchor event exists after migrate; profile history
shows the ROUTINE types, paginates, and an old reset stays visible after 60 contact edits; works on SQLite
and Postgres.

**PR 2:** method required; Other needs a note and In person refuses one; note over 100 characters, with 6+
digits or with "@" refused; a validation error keeps a usable token and the corrected resubmit resets once;
the service refuses a bad method without the form; recent phone change and the first 30 days after the
anchor allow only In person, in form and service; "You changed this number" shown to the same actor; reset
locks the guardian row; reset event ROUTINE with `{"method": …}` and no note; note stored, autoescaped,
purged after 365 days; portal notice within 30 days and absent after; first sign-in after reset recorded once
for a guardian, never for a teacher, never when `must_change_password` is false; revoked-login rule: create
and link refused without the group, `EXISTING_RECORDS` refused, allowed for a member with In person;
guardian without a revoked login unchanged; grants unchanged (R11); privileged login refused (R15); sessions
ended and change forced (R8); slip `no-store` (R5); School Administrator outside the group gets 403, member
and superuser 200; group migration forward and backward on a populated database, name collision with other
permissions stops, no other holder of the permission; system check warns with no eligible user; generator
still 12 of 31 symbols (R2); CSRF and `X-Frame-Options: DENY` on changed routes (R12).

**PR 3:** switch unset: an old temporary password signs in; invalid switch value stops start-up; switch set:
`CREATED` expires 14 days and `RESET` 72 hours after `max(issued, switch)`; a password issued 30 days before
switch-on still works until switch + window; one hour after first sign-in it stops; same response as a wrong
password (status, template, message); expired through `/admin/login/` too; null `issued_at` or blank kind:
no expiry and no error; one expiry event per issue; a new reset makes sign-in work again; password change
clears all three fields and does not clear a newer reset's fields; backfill and reverse; teacher create and
reset set the fields (OD-R1); `link_existing_login` sets nothing; signed-in session at expiry still forced to
change; slip shows the "works until" line only when the switch is set; never-signed-in list shows "Expired".

**PR 2b:** a School Administrator sees the list (200) without add or remove controls, and their POST to add
or remove gets 403; a teacher or guardian gets 403 on the list; anonymous goes to sign-in; GET to add or
remove gets 405; a superuser adds an eligible administrator (membership plus event with actor and subject) and
removes them with a reason (event with the choice); the add list excludes inactive users,
non-administrators, superusers, existing members and logins with an active guardian account, and the service
refuses each of them even when posted directly; a just-added member can open the reset form on the next
request and a removed one gets 403; direct grants and superusers appear under "Can also reset"; the
empty-group warning shows; recent changes list the last 20; CSRF and frame denial on the POST routes; route
inventory updated, both POST routes carry `superuser_required`, and `test_no_route_is_public_by_accident`
passes without listing them as unpermissioned; remove with a non-member id, a superuser's id or a
direct-grant holder's id returns 404 and records nothing; a second remove of the same member changes nothing;
`is_staff` users are not offered and are refused; the service fails when the group is missing; a removed
member's open session gets 403; the two event types are ROUTINE; "Added more than a year ago or outside this
page" shows when no add event exists; a member who now has a parent login is marked, and the reset service
refuses a reset of the actor's own login; no shipped group grants `auth.change_user`, `auth.change_group` or
`auth.change_permission`.

**Every PR:** `ruff check .`; `makemigrations --check --dry-run` clean after the PR's own migration (PR 1, 2
and 3 each add one migration altering event-type choices; each names it in its PR); route inventory test;
targeted tests for accounts, guardian accounts, teacher accounts, portal home and the never-signed-in list;
full CI on the final head.

## 11. Acceptance checklist

- [x] Owner decisions OD-R1 to OD-R5 and review choices S-01, S-03, S-07 recorded (§12).
- [x] Security-focused review of r1 done; findings applied in r2.
- [x] Owner accepts r2 (2026-11-24).
- [ ] PR 1 merged; contact edits appear in guardian history on staging.
- [ ] PR 2 merged after a backward-migration rehearsal; reset form checked at 360, 390 and desktop.
- [ ] PR 2b merged; a superuser adds reset staff on staging from the page; page checked at 360, 390 and
      desktop.
- [ ] PR 3 merged with expiry off after a rehearsal and backup; never-signed-in run done; switch set in
      staging; expiry checked.
- [ ] PR 4 merged; link shown only to group members and superusers.

## 12. Decisions for the product owner

All recorded 2026-11-24.

| ID | Decision | Chosen |
| --- | --- | --- |
| OD-R1 | Teacher temporary passwords | Expire like guardians (same fields and windows); teacher reset otherwise unchanged |
| OD-R2 | Who is in "Portal password resets" at launch | Revised in r3: the school chooses later on the "Password reset staff" page (§6a). No names are needed before any PR; until someone is added, only superusers can reset. |
| OD-R6 | Who can change the reset staff list | Superusers only (a check, not a permission, so it cannot be granted through a group). Administrators can view the list. |
| OD-R7 | Retention of reset-staff add and remove events | ROUTINE, 365 days, like the rest (option A, 2026-11-24). After that the page shows "Added more than a year ago or outside this page". |
| OD-R3 | Phone history before PR 1 | Fail closed: the first 30 days after PR 1 count as "recently changed" |
| OD-R4 | How expiry is switched on | Behind a setting, after the never-signed-in run (now a start time, §5.3) |
| OD-R5 | "Other" note retention | Deleted after 365 days |
| S-01 | Replacing a revoked login | (a) Same rules as a reset: named group, method limits, phone window (§4.8) |
| S-03 | Retention before counsel | Option A: all new and changed events stay ROUTINE (365 days); HISTORY only in a later PR after counsel. No counsel at present. |
| S-07 | A used slip | Stops working one hour after its first successful sign-in (§5.4). Chosen as the recommendation; the owner may switch to "stops at first use". |

## 13. Out of scope and accepted residual risks

- The request page and its purge (option G): the next spec.
- Any channel, owner notification or verified contact data (OD-G2, OD-G10). T10 stays High (accepted in
  ADR 0029).
- Two-person approval for resets (OD-G7 "later option"). One insider can still edit a phone and then reset
  in person; §4.3 shows "You changed this number" but does not block it (T7 Medium, accepted in ADR 0029).
- Membership changes made in the Django admin instead of the page are not recorded as events; the page lists
  direct grants and `role_permission_gaps` supports a periodic review. Changes made on the page are recorded
  (§6a).
- Reset records older than a year are not available for disputes until counsel allows longer retention (S-03).
- Staff logins other than teachers: managed in the Django admin (`is_portal_manageable`).
