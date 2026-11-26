# G-06 spec: "Can't sign in?" request page (ADR 0029, option G)

- **Status:** **Draft r1**, 2026-11-26. Not approved. Needs the security-focused review (ADR 0029 item 3)
  and the product owner's decisions in §12 before any code.
- **Baseline:** `origin/main` 0e8b946 (logout speed fix, PR #313). The office reset spec
  ([G06_OFFICE_RESET_SPEC.md](G06_OFFICE_RESET_SPEC.md)) PRs 1 to 4 are merged.
- **Risk tier:** **Critical** (password and account recovery; a new anonymous route;
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3).
- **Design source:** [ADR 0029](../adr/0029-guardian-account-recovery.md) Decision 2 (option G), Accepted
  2026-11-23 with OD-G1 to OD-G16 as recommended. Threat model:
  [G06_RECOVERY_THREAT_MODEL.md](G06_RECOVERY_THREAT_MODEL.md), mainly T2, T8, T18, T21, T23.
- **Proposed deviation from ADR 0029 (owner to decide, §12 OD-H1):** ADR item 5 asks counsel to confirm
  retention before build. The school has no counsel. This spec keeps the request rows for 30 days, the
  shortest period in OD-G4, and asks the owner to accept building before counsel confirms.
- **Not in this spec:** any message to the guardian, any reset from the page, any channel (OD-G2 stays
  "none"), owner notification (T10 stays High, accepted).

## 1. Outcome

A guardian who cannot sign in taps **"Can't sign in?"** on the sign-in page and fills in three short
fields. The page always gives the same answer and never says whether an account exists. Nothing is
reset and nothing is sent. Named office staff see the request in a queue, find the family in the
guardian list themselves, call **only the number on the record** (ADR 0029 Appendix A), book a visit,
and reset the password in person with the existing reset form. Requests are capped per source and per
day, are deleted after 30 days, and the office sees how many were dropped by the caps.

## 2. Requirements covered

| ADR 0029 | Where |
| --- | --- |
| R1 no account-existence leak | §4.4; tests §10 |
| R6 caps (5 per source per hour, 200 per day), dropped-request count | §4.3, §5.3 |
| R7 generic responses | §4.4 |
| R10 audit events | §5.4 (request handled); no event on submit (§5.4 explains) |
| R11 no grant changes | §4.4; test |
| R12 CSRF, frame denial | site-wide; tests on all three new routes (§8) |
| R13 logging hygiene | §9; test |
| R14 route inventory | §8. The page is the only **new** anonymous route; `core:school-logo` and `root:pwa-manifest` were public before. |
| R21 three fields, no lookup, autoescape, daily purge | §4.2, §4.4, §5.2, §6 |
| R22 dedicated queue permission, teachers and guardians 403 | §5.1 |
| OD-G4 build, purge after 30 days | §6; counsel deviation OD-H1 |
| OD-G14 the model's own view and change permissions | §5.1 |
| OD-G15 R6 numbers as starting values | §4.3 |
| R2 to R5, R8, R9, R15 to R20 | Not applicable: the page issues no secret and touches no login. |

## 3. Data

### 3.1 `accounts.SignInHelpRequest`

Lives in `accounts`, next to `LoginFailure` (`accounts/models.py`), because it belongs to sign-in.

| Field | Type | Notes |
| --- | --- | --- |
| `guardian_name` | CharField 100 | as typed, after §4.2 clean-up |
| `child_name` | CharField 100 | as typed |
| `child_class` | CharField 30 | as typed, for example "Class 5 B" |
| `received_at` | DateTimeField, default now, indexed | |
| `source_key` | CharField 64 | HMAC of the source address, **domain-separated** (§4.3) |
| `outcome` | CharField, choices (§5.2), blank | blank means open |
| `handled_at` | DateTimeField, null | |
| `handled_by` | FK `accounts.User`, `SET_NULL`, null | |

Index on `(source_key, received_at)` for the per-source cap. Default permissions only
(`view_signinhelprequest`, `change_signinhelprequest`; add and delete are never granted). Not registered
in the Django admin; a test asserts it is absent from `admin.site._registry`. No phone, email, free text,
user agent or raw address is stored.

### 3.2 `accounts.SignInHelpDropCount`

`day` (DateField, unique, local date in `Asia/Kolkata`, `config/settings.py:211`) and `count`
(PositiveInteger). One row per day with drops. Incremented with
`filter(day=d).update(count=F("count") + 1)`; when no row exists, `create(count=1)`, retrying the update
on `IntegrityError`. It holds no personal data and no source.

**Risk:** Medium. Migration: two new tables (reverse drops them, losing at most 30 days of requests,
which is acceptable: they are short-lived by design).

## 4. PR 2: the public page

### 4.1 Route and switch

| Name | Path | Methods | Guard |
| --- | --- | --- | --- |
| `root:sign-in-help` | `accounts/sign-in-help/` | GET, POST (`require_http_methods`) | none (anonymous by design), `never_cache` |

In `config/urls.py` next to `login`, view in `accounts/views.py`.

**Switch.** `SIGN_IN_HELP_ENABLED`, read with `config/deployment_safety.parse_flag` (a bad value stops
start-up). Off by default. When off: the route returns 404 and the sign-in page keeps today's text
("Forgot your password? Ask the school office to reset it."). When on: the sign-in page shows a
**"Can't sign in?"** link in its place (`templates/registration/login.html`, under the form, phone and
desktop). The switch is the rollback (§7).

**Signed-in visitors** are redirected to `home`, like `accounts.views.LoginView` does; nothing is
stored. A login that must change its password is sent to the change page by the middleware first
(`accounts/middleware.py:177-180`), as today.

### 4.2 Form (R21)

Exactly three fields, all required. No phone, email or message field.

| Label | Name | Max | Allowed |
| --- | --- | --- | --- |
| Your full name | `guardian_name` | 100 | letters and marks in any script, spaces, `.` `'` `-` |
| Your child's full name | `child_name` | 100 | same |
| Your child's class and section | `child_class` | 30 | letters, digits, spaces, `-` `/` `.` |

Clean-up before validation: Unicode NFC, trim, collapse inner whitespace. Refused: control characters,
`<`, `>`, `@`, `:` and any run of 6 or more digits (so URLs, emails and phone numbers cannot be typed).
Errors show per field in the existing form style. Validation depends only on the typed text, never on
school data, so an error reveals nothing about accounts. A form with errors stores nothing and does not
count toward any cap.

`autocomplete="name"` on the guardian name, `off` on the other two. `enterkeyhint` on each field.

**Page text** (static; the page queries no school data, like the sign-in page):

> **Can't sign in?**
> Tell the school who you are. The office will call you on the phone number it already has for you
> and ask you to come in with an identity document. Nothing changes on your account until then.
>
> Do not type a password or phone number here.
>
> *Button:* Send to the school office
>
> What we keep: these three answers, for 30 days, so the office can help you. Only office staff who
> reset passwords can see them.
>
> Staff: ask the school office. · Back to Log in

### 4.3 Caps (R6, OD-G15)

Constants in a new module `accounts/sign_in_help.py`:

| Cap | Start value | Counted from |
| --- | --- | --- |
| Per source | 5 stored requests in the last 60 minutes | `SignInHelpRequest` rows with this `source_key` |
| Global | 200 stored requests per local day | `SignInHelpRequest` rows received today |

**Source key.** `hmac(SOURCE_HASH_KEY, "sign-in-help:" + client_address(request), sha256)`, reusing
`accounts.security.client_address` (`accounts/security.py:49-58`). The prefix keeps the value different
from the `source_key` on `LoginFailure` and `SecurityEvent` rows, so a database reader cannot join an
anonymous request to a sign-in attempt.

Rows are counted whatever their outcome and are removed only by the purge (§6), so handling a request
does not loosen a cap. Two simultaneous submissions can both pass a check and exceed a cap by one or
two; the caps are soft limits and that is accepted.

Per-source caps depend on `DJANGO_TRUSTED_PROXIES` (`config/settings.py:170`). Railway already needs it
for the HTTPS redirect (`docs/OPERATIONS.md`, Production settings), so it is set wherever the app runs
behind Railway. If it were missing, every request would share the proxy's address and the per-source cap
would act as a global 5 per hour. The staging check (§7) confirms two networks are counted separately.

Carrier-grade NAT can put a whole area behind one address (threat model §6); 5 per hour is a starting
value to watch on staging.

### 4.4 Submit path (R1, R7, R11)

On a valid POST, in one `transaction.atomic`:

1. Count the per-source rows, then today's rows (two queries, the same for every input).
2. Under both caps: insert the request. At or over either cap: increment today's drop count instead.
3. Render the answer page.

There is **no account lookup**: no query on `User`, `Guardian`, `Student`, `GuardianAccount` or any
other school table. The answer is rendered with status 200 from one template whether the request was
stored or dropped:

> **Thank you.** The school will contact you using the details it already has. If your phone number has
> changed, please visit the school office. · Back to Log in

The answer is rendered directly (no redirect), so the page is one route and no typed value ever appears
in a URL. Refreshing re-posts; the per-source cap bounds that.

**R1 equality.** Known input (names that match a real guardian and child) and unknown input give the same
status, template, body (apart from the CSRF token) and the same SQL statements, writes included.
Throttled input gives the same status, template, body and the same reads; its write differs (the drop
count instead of the insert), which reveals nothing about accounts because the caps ignore what was typed
(ADR 0029 R1). Tests compare captured SQL, not timing.

**No grant or login change (R11).** A submission writes only to the two tables in §3; a test asserts no
row changes in `User`, `GuardianAccount`, `GuardianStudentAccess`, `LoginFailure` or `SecurityEvent`.

**Risk:** Critical (anonymous write path).

## 5. PR 1: the office queue

### 5.1 Who sees it (R22, OD-G14, OD-H2)

Permissions `accounts.view_signinhelprequest` (list) and `accounts.change_signinhelprequest` (record an
outcome). A data migration adds both to the **"Portal password resets"** group (`core/reset_staff.py:15`),
so the staff who reset passwords are the staff who see requests (recommended, OD-H2). If the group does
not exist, the migration creates nothing and the permissions stay with superusers only; the PR 2
migration of the reset spec created it, so this only happens on an unusual install. Reverse: remove both
permissions from the group.

The "Password reset staff" page (`core/reset_staff.py`, spec §6a) gets one line: "Members also see
sign-in help requests." A test asserts no other shipped group holds either permission. School
Administrators outside the group, teachers and guardians get 403.

Queue rows show only what was typed and the received time. The page shows no matched record, no guess
at a match and no source key, so it shows no child data beyond what the requester typed (R22).

### 5.2 Routes and page

| Name | Path | Method | Guard |
| --- | --- | --- | --- |
| `core:sign-in-help-requests` | `access/sign-in-help/` | GET (`require_safe`) | `administrator_required("accounts.view_signinhelprequest")` |
| `core:sign-in-help-request-handle` | `access/sign-in-help/<int:pk>/handle/` | POST (`require_POST`) | `administrator_required("accounts.change_signinhelprequest")` |

**Sidebar.** "Access and security" (`core/navigation.py:55-61`): "Sign-in help requests" after "Sign-in
lockouts", with a badge of open requests through `core/nav_badges.py` (the same count feeds an Overview
card "Sign-in help requests", `core/dashboard.py`, shown only to holders of the view permission).

**Page.**

- At the top, ADR 0029 Appendix A as a short checklist: check the guardian's profile for a phone change
  in the last 30 days (then in person only); call only the number on the record; never a number from
  anyone else; book a visit; reset at the visit with "In person, with identity documents"; never read a
  password aloud.
- Two tabs, **Open** (oldest first) and **Handled** (newest first), paginated with `build_table`
  (`core/tables.py:73`), 25 per page. Columns: received (date and time), your name, child's name, class
  and section; on Handled also outcome, by whom and when. All values autoescaped; no `urlize`, no
  `|safe`.
- No search box and no "find guardian" link: a prefilled search would put typed names in a URL and the
  access logs (R13). Staff type the name into the guardian list themselves.
- Notice when caps dropped requests: "Not saved because of limits: today N, last 7 days M." Aggregate
  counts only (R6).
- Footer: "Requests are deleted 30 days after they arrive, handled or not."
- Phone layout: stacked rows (`erp-table--stack`), outcome as a select plus a Save button. No new CSS
  component. Checked at 360, 390 and 1280.

**Outcome** (one choice, required, no free text):

| Value | Label |
| --- | --- |
| `VISIT_BOOKED` | Called the number on record, visit booked |
| `NOT_REQUESTED` | Called the number on record, they did not ask for this |
| `NOT_REACHED` | Could not reach the number on record |
| `NO_MATCH` | No matching guardian record |
| `NOT_GENUINE` | Not a real request |

**Handle service.** `sign_in_help.handle(request_id, *, actor, outcome)` locks the row
(`select_for_update`); if it already has an outcome it changes nothing and the page says "Already handled
by <name>." Otherwise it sets outcome, `handled_at`, `handled_by` and records the event (§5.4) in one
transaction. An outcome is final. The view returns 404 for an id that does not exist (purged).

### 5.3 Dropped-request count

Read from `SignInHelpDropCount` for today and the last 7 days. Shown only on the queue page.

### 5.4 Event

New `SecurityEvent` type `SIGN_IN_HELP_HANDLED` ("Sign-in help request handled"), **ROUTINE** (365 days),
added to `SecurityEvent.ROUTINE_TYPES` because `class_for` defaults to HISTORY (`accounts/models.py`); a
test pins the class. `actor` set; `detail = {"outcome": "<value>"}` only. No guardian link, no typed
names, no request id. These events give the request and outcome counts that a later channel decision
needs (ADR 0029 Rationale), and they outlive the 30-day request rows.

No event is written on submit: an anonymous writer must not be able to fill the append-only table, and
the request row plus the drop count already record arrivals.

**Risk:** High. Migration: the two tables (§3), the event-type choice, the group permissions.

## 6. Purge (R21, OD-G4)

New command `purge_sign_in_help_requests`: deletes `SignInHelpRequest` rows with `received_at` older
than 30 days and `SignInHelpDropCount` rows older than 30 days; prints only the two counts. It needs no
`--by`: it deletes short-lived rows that are not security events, like `purge_usage_counters`.

- Runs daily on the Railway cron service as its own `;`-separated step, so a failure does not stop the
  next step (`docs/OPERATIONS.md`, Retention). **Deploy step** after PR 1: add
  `python manage.py purge_sign_in_help_requests;` to the cron start command in staging, later production.
- Safe to run by hand at any time.
- The queue never lists rows older than 30 days, even if the cron step is missing, and shows "Old
  requests are waiting to be deleted. Check the daily cron job." when such rows exist.

## 7. Staged rollout and rollback (ADR 0029 item 4)

| Step | What | Rollback |
| --- | --- | --- |
| PR 1 | Models, queue, handle, event, purge command, group permissions, nav badge, Overview card, runbook. No public page yet, so the queue stays empty. | Revert; the reverse migration drops the tables and removes the permissions. **Rehearse backward on a copy of the local demo database before merge.** |
| PR 1 deploy | Add the purge step to the staging cron start command. | Remove the step. |
| PR 2 | Public page, caps, sign-in link, all behind `SIGN_IN_HELP_ENABLED` (off). | Revert. No migration. |
| PR 2 switch-on, staging | Set `SIGN_IN_HELP_ENABLED=True`. Check on a real phone: submit, see it in the queue, handle it; a sixth request from the same network in an hour is not stored and the drop count rises; a request from a second network (mobile data versus Wi-Fi) is stored; the queue at 360, 390 and 1280. | Unset the variable: the page returns 404 and the sign-in page shows the old text. Stored requests stay until purged. |
| Production | After a school has named reset staff and the cron step exists there. | Same switch. |

## 8. Routes and inventory (R12, R14)

- `root:sign-in-help`: added to `INTENTIONALLY_UNPERMISSIONED`
  (`core/tests/test_security_gate4b_route_inventory.py:15`) with the reason "the "Can't sign in?" request
  page, anonymous by design (ADR 0029 option G); does no account lookup and serves no school data", and to
  `test_the_root_application_routes_are_covered`.
- `core:sign-in-help-requests` and `core:sign-in-help-request-handle`: pinned with their permissions in
  `core/tests/route_permissions.json` (`python core/tests/route_inventory.py --write`).
- Tests on all three: `X-Frame-Options: DENY`; a POST without a CSRF token gets the custom failure page
  (`CSRF_FAILURE_VIEW`); GET to the handle route gets 405.

## 9. Privacy, logging and retention (R13)

- Never logged, measured, alerted or put in a URL: the three typed values and the source address. POST
  data is masked in crash reports (`PrivacyExceptionReporterFilter`, `config/error_reporting.py:30`). No
  usage counters (ADR 0027) on either page.
- Tests capture logs on a stored submit, a dropped submit, a form error and a handle, and assert none of
  the typed values appear.
- Retention: request rows and drop counts 30 days (§6); `SIGN_IN_HELP_HANDLED` events 365 days (ROUTINE,
  purged by the monthly `purge_security_events`). Nothing is HISTORY.
- `docs/OPERATIONS.md` gets a section: the switch, the cron step, the daily queue routine (Appendix A),
  and that 30 days is not yet confirmed by counsel (OD-H1).
- ADR 0013 ("no self-service password recovery") needs no change: the page resets nothing (OD-G12). PR 2
  adds a "See also ADR 0029" line to it.

## 10. Tests (minimum)

**PR 1:** both models migrate forward and backward on SQLite and Postgres; the group gets both permissions
and no other shipped group holds them; a group member sees the queue (200) and handles a request; a School
Administrator outside the group, a teacher and a guardian get 403; anonymous goes to sign-in; outcome
required and limited to the five values; a second handle changes nothing and says who handled it; handle
of a missing id returns 404; one ROUTINE `SIGN_IN_HELP_HANDLED` event with only `{"outcome": …}`; typed
`<script>` shows as text; rows older than 30 days hidden and the cron warning shown; purge deletes rows
and counts older than 30 days and keeps newer ones; drop-count notice shows today and the last 7 days;
nav badge and Overview card show the open count only to holders; model not in the Django admin; route
inventory updated; CSRF and frame denial; logs hold no typed values.

**PR 2:** switch off: 404 and the old sign-in text; switch on: the link shows and the page renders with no
query on school tables; signed-in visitor redirected and nothing stored; each field required, length caps,
refused characters (`<`, `@`, `:`, 6+ digits, control characters), non-Latin names accepted, whitespace
collapsed; a form error stores nothing and does not count; known, unknown and throttled input give the
same status, template and body (CSRF token aside) and the same reads; known and unknown give the same
writes; throttled input stores nothing and increments the drop count (per-source cap at the sixth request
in 60 minutes, global cap at the 201st of the day, both with frozen time); the drop count's create race is
handled; a different source is not capped by another's requests; the source key differs from
`security.source_key` for the same address; no change to `User`, `GuardianAccount`,
`GuardianStudentAccess`, `LoginFailure` or `SecurityEvent` on submit; `never_cache` on the page; CSRF and
frame denial; no typed value in logs or in any `Location` header; invalid `SIGN_IN_HELP_ENABLED` stops
start-up.

**Every PR:** `ruff check .`; `makemigrations --check --dry-run` clean after the PR's own migration;
route inventory test; targeted tests for accounts, the sign-in page, reset staff and the new module; full
CI on the final head.

## 11. Acceptance checklist

- [ ] Security-focused review of this spec (ADR 0029 item 3); findings applied in r2.
- [ ] Owner decisions OD-H1 to OD-H4 recorded (§12).
- [ ] Owner approves the spec for build.
- [ ] PR 1 merged after a backward-migration rehearsal; purge step added to the staging cron.
- [ ] PR 2 merged with the switch off.
- [ ] Switch on in staging and the §7 checks recorded.

## 12. Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-H1 | Build before counsel confirms retention (ADR 0029 item 5) | (a) Build now with 30 days, revisit when counsel is available; (b) wait for counsel | (a). Three short fields, kept 30 days, no contact data; the shortest period in OD-G4. |
| OD-H2 | Who sees the queue | (a) Members of "Portal password resets" (one list of named staff); (b) a separate group with its own page | (a). The people who reset are the people who call back; no second page to build. |
| OD-H3 | Prompt for waiting requests | (a) Sidebar badge and Overview card; (b) none | (a). Without a prompt requests sit unseen until purged. |
| OD-H4 | Caps | Accept 5 per source per hour and 200 per day as starting values (OD-G15); set others | Accept; tune on staging. |

## 13. Out of scope and accepted residual risks

- Any reply to the requester, any channel and owner notification (OD-G2; T10 High, accepted).
- A flood can fill the daily cap and push real requests out; the office sees the drop count (T18, M for
  office time, accepted in ADR 0029).
- No CAPTCHA (third-party service, accessibility cost) and no hidden extra field (R21 allows exactly three
  fields). Revisit only if staging shows automated spam.
- Spam can make staff call a real family who asked for nothing; Appendix A's script says the school is
  returning a request and resets nothing on the call (T18).
- The page is in English only.
- Matching is manual; a request with a misspelt name may get `NO_MATCH`. The answer page tells families
  they can visit the office.
