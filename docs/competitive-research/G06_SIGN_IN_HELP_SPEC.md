# G-06 spec: "Can't sign in?" request page (ADR 0029, option G)

- **Status:** **Draft r2**, 2026-11-26. Not approved. r2 applies the security-focused review of r1
  (ADR 0029 item 3; findings SR-01 to SR-19, §14) and the owner's two conditions on OD-H1 and OD-H2.
  Needs the owner's decisions in §12 and approval before any code. The reviewer advised a short re-check
  of r2, because SR-01 and SR-04 change the data model.
- **Baseline:** `origin/main` 0e8b946 (logout speed fix, PR #313). The office reset spec
  ([G06_OFFICE_RESET_SPEC.md](G06_OFFICE_RESET_SPEC.md)) PRs 1 to 4 are merged.
- **Risk tier:** **Critical** (password and account recovery; a new anonymous route;
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3).
- **Design source:** [ADR 0029](../adr/0029-guardian-account-recovery.md) Decision 2 (option G), Accepted
  2026-11-23 with OD-G1 to OD-G16 as recommended. Threat model:
  [G06_RECOVERY_THREAT_MODEL.md](G06_RECOVERY_THREAT_MODEL.md), mainly T2, T8, T18, T21, T23.
- **Legal gate (ADR 0029 item 5, OD-H1, not approved):** the feature may be built and merged with the page
  off. It **cannot collect real requests** until the owner records an explicit acceptance of the retention
  and legal risk. The code enforces this (§4.1).
- **Proposed deviations from ADR 0029, owner to confirm (§12 OD-H5):**
  - R10 lists "request handled or refused" as HISTORY events. This spec records "handled" as **ROUTINE**
    (365 days), as the reset spec did (S-03), and writes **no event on submit or drop**: the daily drop
    count is the refusal record, aggregate only (R6).
  - R21 allows "the hashed source". This spec keeps a stricter rule: request rows carry **no network
    identifier at all**; a keyed hash lives only in rate-limit rows kept 2 hours (§3.3).
  - R14 says "the only anonymous route". Read here as "the only **new** anonymous route": sign-in,
    `core:school-logo` and `root:pwa-manifest` were public before.
- **Not in this spec:** any message to the guardian, any reset from the page, any channel (OD-G2 stays
  "none"), owner notification (T10 stays High, accepted).

## 1. Outcome

A guardian who cannot sign in taps **"Can't sign in?"** on the sign-in page and fills in three short
fields. The page always gives the same answer and never says whether an account exists. Nothing is
reset and nothing is sent. Named office staff see the request in a queue, find the family in the
guardian list themselves, call **only the number on the record** (ADR 0029 Appendix A), book a visit,
and reset the password in person with the existing reset form. Requests are capped per source and per
day, repeats are not stored twice, rows are deleted after 30 days, and the office sees how many were
dropped.

## 2. Requirements covered

| ADR 0029 | Where |
| --- | --- |
| R1 no account-existence leak | §4.4; tests §10 |
| R6 caps (5 per source per hour, 200 per day), dropped-request count | §4.3, §5.3 |
| R7 generic responses | §4.4 |
| R10 audit events | §5.4; deviation OD-H5 |
| R11 no grant changes | §4.4; test |
| R12 CSRF, frame denial | site-wide; tests on all three new routes (§8) |
| R13 logging hygiene | §9; test |
| R14 route inventory | §8; "only new anonymous route" (OD-H5) |
| R21 three fields, no lookup, autoescape, daily purge | §4.2, §4.4, §5.2, §6; stricter source rule (OD-H5) |
| R22 dedicated queue permission, teachers and guardians 403 | §5.1 |
| OD-G4 build, purge after 30 days | §6; legal gate OD-H1 |
| OD-G14 the model's own view and change permissions | §5.1, OD-H2 |
| OD-G15 R6 numbers as starting values | §4.3, OD-H4 |
| ADR item 5 counsel confirms retention | not met; OD-H1 gate in code (§4.1) |
| R2 to R5, R8, R9, R15 to R20 | Not applicable: the page issues no secret and touches no login. |

## 3. Data

All three models live in `accounts`, next to `LoginFailure` (`accounts/models.py`). None is registered in
the Django admin; a test asserts each is absent from `admin.site._registry`.

### 3.1 `accounts.SignInHelpRequest`

| Field | Type | Notes |
| --- | --- | --- |
| `guardian_name` | CharField 100 | as typed, after §4.2 clean-up |
| `child_name` | CharField 100 | as typed |
| `child_class` | CharField 30 | as typed, for example "Class 5 B" |
| `match_key` | CharField 64, indexed | SHA-256 of the three cleaned values, NFKC and case-folded, for repeats (§4.3) |
| `received_at` | DateTimeField, default now, indexed | |
| `is_test` | BooleanField, default false | set in test mode (§4.1) |
| `outcome` | CharField, choices (§5.2), blank | blank means open |
| `handled_at` | DateTimeField, null | |
| `handled_by` | FK `accounts.User`, `SET_NULL`, null | |

Index `(outcome, received_at)` for the open count. Default permissions only (`view_signinhelprequest`,
`change_signinhelprequest`; add and delete are never granted). **No network identifier**, phone, email,
free text or user agent is stored on the row (SR-04). `match_key` is a plain hash of text already stored
in clear in the same row, so it adds nothing a reader cannot already see.

### 3.2 `accounts.SignInHelpDay`

`day` (DateField, unique, local date in `Asia/Kolkata`, `config/settings.py:211`), `stored` and `dropped`
(PositiveInteger). One row per day with any submission. It is the **gate row** for the caps (§4.3) and
the drop count (§5.3). No personal data, no source.

### 3.3 `accounts.SignInHelpSourceHit`

`source_key` (CharField 64) and `at` (DateTimeField), index `(source_key, at)`. One row per **stored**
request from a known source. Deleted after 2 hours (§4.4, §6): long enough for the one-hour cap, short
enough that no lasting network log exists (SR-04).

**Risk:** High. Migration: three new tables. Reverse drops them (§7, SR-14).

## 4. PR 2: the public page

### 4.1 Route, switch and legal gate (OD-H1, SR-07)

| Name | Path | Methods | Guard |
| --- | --- | --- | --- |
| `root:sign-in-help` | `accounts/sign-in-help/` | GET, POST (`require_http_methods`) | none (anonymous by design), `never_cache` |

In `config/urls.py` next to `login`, view in `accounts/views.py`.

**Settings**, read in `config/settings.py`:

| Setting | Type | Meaning |
| --- | --- | --- |
| `SIGN_IN_HELP_ENABLED` | flag (`config/deployment_safety.parse_flag`) | master switch, off by default |
| `SIGN_IN_HELP_RETENTION_ACCEPTED` | string, stripped | the owner's dated acceptance reference, for example `OD-H1 2026-12-01`; empty means not accepted |
| `SIGN_IN_HELP_TEST_MODE` | flag | staging tests with made-up names |

**The page is served only when** the switch is on **and** exactly one of these holds: the acceptance is
non-empty (live mode), or test mode is on (test mode). Otherwise the route gives Django's standard 404 and
the sign-in page keeps today's text ("Forgot your password? Ask the school office to reset it."). When
served, the sign-in page shows a **"Can't sign in?"** link in its place (`templates/registration/login.html`,
under the form, phone and desktop).

**Start-up refuses** (`ImproperlyConfigured`, like the HTTPS rule) when: test mode and an acceptance are
both set (a contradiction); or the switch is on, `DEBUG` is off and `TRUSTED_PROXIES` is empty (SR-03:
every request would share the proxy's address). The switch on with neither acceptance nor test mode is
allowed and simply keeps the page off.

**Test mode** (staging only, by the runbook). The page shows at the top "Test only. Type made-up names."
Rows are stored with `is_test = true`, labelled "Test" in the queue, and deleted after 24 hours (§6).
Nothing in the code tells staging from production (no such setting exists), so keeping test mode out of
production is a runbook rule; the banner limits the harm if it is ever set there. The staging address is
not shared during a test. After each test, `purge_sign_in_help_requests --all` (§6).

**Signed-in visitors**, on GET and POST, are redirected to `home`, like `accounts.views.LoginView` does;
nothing is stored. A login that must change its password is sent to the change page by the middleware first
(`accounts/middleware.py:177-180`), as today.

### 4.2 Form (R21, SR-09)

Exactly three fields, all required. No phone, email or message field.

| Label | Name | Max |
| --- | --- | --- |
| Your full name | `guardian_name` | 100 |
| Your child's full name | `child_name` | 100 |
| Your child's class and section | `child_class` | 30 |

**Clean-up:** Unicode NFKC (folds fullwidth and compatibility forms), trim, collapse inner whitespace to
one space.

**Allow-list by Unicode category; anything else is refused:**

- Name fields: letters (L\*), marks (M\*), the space, and `.` `'` `-`. U+200C and U+200D (ZWNJ, ZWJ) only
  between two letters or marks, because Malayalam, Tamil, Devanagari and Bengali names need them. **No
  digits.**
- Class field: the same, plus decimal digits (Nd), `/`, with **at most 3 digits in total** (counted after
  NFKC, so non-ASCII and split digits count too).
- Refused everywhere: every other format character (Cf, including U+202E and U+2066 to U+2069 and U+200B),
  control (Cc), private use (Co), surrogates (Cs), line and paragraph separators, unassigned code points,
  and any run of more than 3 combining marks.

So links, emails and phone numbers cannot be typed. Errors show per field in the existing form style.
Validation depends only on the typed text, never on school data, so an error reveals nothing about
accounts. A form with errors stores nothing, takes no lock and does not count toward any cap.

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
> What we keep: these three answers, deleted from the school's system within 30 days. Only a few named
> office staff can see them. Backup copies are deleted when the backups expire.
>
> Staff: ask the school office. · Back to Log in

The backup sentence states the real backup period once the runbook records it (SR-19).

### 4.3 Caps, repeats and the source bucket (R6, OD-G15, SR-01 to SR-04, SR-15)

Constants in a new module `accounts/sign_in_help.py`:

| Rule | Start value | Counted from |
| --- | --- | --- |
| Per source | 5 stored requests in the last 60 minutes | `SignInHelpSourceHit` rows for this bucket |
| Global | 200 stored requests per local day | `SignInHelpDay.stored` |
| Repeat | the same three answers within 7 days | `SignInHelpRequest.match_key` |

**Source bucket (SR-02, SR-03).** From `accounts.security.client_address` (`accounts/security.py:49-58`):
an IPv4-mapped IPv6 address becomes its IPv4 address; an IPv6 address becomes its **/64 network**, so an
attacker cannot rotate addresses inside one /64; an IPv4 address is used as is. When the address is
`"unknown"`, there is no bucket: only the global cap and the repeat rule apply, and no hit is written.

**Keyed, domain-separated hash (SR-04).** A sub-key `HMAC(SOURCE_HASH_KEY, "sign-in-help/v1")`, then
`HMAC(sub-key, bucket)`, SHA-256. Never a plain hash and never a raw address. It cannot be joined to
`LoginFailure` or `SecurityEvent` source values without the key. With the key, IPv4 values can be
brute-forced, which is why hits are kept only 2 hours. Rotating `DJANGO_SOURCE_HASH_KEY` or `SECRET_KEY`
resets the per-source counts; that is harmless.

**Atomic admission (SR-01, SR-05).** Count-then-insert without a lock lets N simultaneous requests all pass.
Every valid submission therefore serialises on today's gate row (§4.4, step 1), so both caps are exact
across workers and processes: under Postgres `SELECT ... FOR UPDATE` the second submission waits for the
first to commit; SQLite serialises writes. At about 200 stored requests a day the lock costs nothing; under
a flood only valid submissions queue on it.

Carrier-grade NAT can put a whole area behind one address (threat model §6); 5 per hour is a starting
value to watch on staging.

### 4.4 Submit path (R1, R7, R11)

On a valid POST, in one `transaction.atomic`:

1. Get or create today's `SignInHelpDay` inside a savepoint (retry the read on `IntegrityError`, as
   `core/usage.py:293-296` does), then lock it with `select_for_update`.
2. Housekeeping, independent of the input: delete hits older than 2 hours; delete up to 100 requests past
   their retention (§6), oldest first.
3. Count this bucket's hits in the last 60 minutes (skipped, with the same query shape, when there is no
   bucket); check for a request with the same `match_key` in the last 7 days.
4. Stored when `day.stored < 200`, the bucket has fewer than 5 hits, and it is not a repeat: insert the
   request and a hit, `stored += 1`. Otherwise `dropped += 1`.
5. Render the answer page.

There is **no account lookup**: no query on `User`, `Guardian`, `Student`, `GuardianAccount` or any other
school table. The answer is rendered with status 200 from one template whether the request was stored or
dropped:

> **Thank you.** The school will contact you using the details it already has. If your phone number has
> changed, please visit the school office. · Back to Log in

The answer is rendered directly (no redirect), so the page is one route and no typed value ever appears in
a URL. Refreshing re-posts; the repeat rule then drops it.

**R1 equality (SR-11).** Known input (names matching a real guardian and child) and unknown input give the
same status, template, body (apart from the CSRF token), response headers (`Set-Cookie`, `Cache-Control`,
`Vary`) and the same SQL, writes included. Throttled and repeated input give the same status, template,
body, headers and reads; their write differs (`dropped` instead of the insert), which reveals nothing
about accounts because the caps and the repeat rule ignore school data (ADR 0029 R1). Tests compare
captured SQL, not timing. No session is created for an anonymous visitor (an empty session is never
saved); GET sets only the CSRF cookie (SR-18).

Known differences that reveal nothing about accounts, accepted: with the page off, a POST without a CSRF
token gets 403 (CSRF middleware runs first) and with a token gets 404; a validation error re-shows the form.

**No grant or login change (R11).** A submission writes only to the three tables in §3; a test asserts no
row changes in `User`, `GuardianAccount`, `GuardianStudentAccess`, `LoginFailure` or `SecurityEvent`.

**Abuse outside Django (SR-18).** CSRF is not a rate limit: one GET gives a token for unlimited POSTs.
Invalid POSTs cost only validation CPU and write nothing. Volume attacks are left to the hosting platform.

**Risk:** Critical (anonymous write path).

## 5. PR 1: the office queue

### 5.1 Who sees it (R22, OD-G14, OD-H2, SR-08)

The views check **only** the dedicated permissions `accounts.view_signinhelprequest` (list) and
`accounts.change_signinhelprequest` (record an outcome), never `core.reset_guardian_password`.

**Data migration** (depends on the model migration and `core` 0096):

- Creates the accounts permissions itself with `create_permissions`, as `core/migrations/0096` does
  (lines 13-19), because permissions otherwise appear only after `post_migrate`.
- If the "Portal password resets" group (`core/reset_staff.py:15`) exists, adds both permissions to it. If
  it does not exist, does nothing (superusers only). It never raises because the group has other
  permissions, and running it twice changes nothing.
- Reverse removes only these two permissions from the group.

**Reset staff page and reviews** (`core/reset_staff.py`, reset spec §6a):

- One line under the member list: "Members also see sign-in help requests." The add confirmation says
  "This also lets them see sign-in help requests."
- The read-only "Can also reset" block gains "Can also see sign-in help requests": superusers, direct
  grants and other groups holding either queue permission (`core/reset_staff.py:83` pattern).
- `role_permission_gaps` prints holders of both queue permissions.
- `core.W001` (`core/checks.py`) is unchanged. A new Warning applies only when the page is served and no
  active user can see the queue.

School Administrators outside the group, teachers and guardians get 403. Queue rows show only what was typed
and the received time: no matched record, no guess at a match, no source value (R22).

### 5.2 Routes and page

| Name | Path | Method | Guard |
| --- | --- | --- | --- |
| `core:sign-in-help-requests` | `access/sign-in-help/` | GET (`require_safe`) | `administrator_required("accounts.view_signinhelprequest")` |
| `core:sign-in-help-request-handle` | `access/sign-in-help/<int:pk>/handle/` | POST (`require_POST`) | `administrator_required("accounts.change_signinhelprequest")` |

**Sidebar and Overview (SR-06, SR-12, SR-15).** "Access and security" (`core/navigation.py:55-61`): "Sign-in
help requests" after "Sign-in lockouts", badge from `core/nav_badges.py`. The badge counts open rows inside
retention (`outcome = ""`, `received_at` within 30 days). The same count feeds an Overview card
(`core/dashboard.py`). The card also shows, when non-zero, "N not saved today because of limits" and
"Old requests are waiting to be deleted. Check the daily cron job." Both are visible only to holders of the
view permission. `queue_counts` checks `has_perm` first and caches per request, so other users run no query;
a test pins that.

**Page.**

- At the top, ADR 0029 Appendix A as a short checklist: check the guardian's profile for a phone change in the
  last 30 days (then in person only); call only the number on the record; never a number from anyone else;
  book a visit; reset at the visit with "In person, with identity documents"; never read a password aloud.
- Two tabs, **Open** (oldest first) and **Handled** (newest first), paginated with `build_table`
  (`core/tables.py:73`), 25 per page. Columns: received (date and time), your name, child's name, class and
  section, a "Test" label on test rows; on Handled also outcome, by whom and when.
- **Rendering rules (SR-17, SR-09):** typed values appear only as element text, autoescaped, each inside
  `<bdi>`. Never in an attribute, `title`, `data-*`, `json_script`, a message built with `mark_safe`, a CSV
  or an email. No `urlize`, no `|safe`. "Already handled by <name>" is escaped too.
- No search box and no "find guardian" link: a prefilled search would put typed names in a URL and the
  access logs (R13). Staff type the name into the guardian list themselves.
- Drop notice: "Not saved because of limits or repeats: today N, last 7 days M." Aggregate only (R6).
- Footer: "Requests are deleted 30 days after they arrive, handled or not."
- Rows past retention are never listed, even if the purge has not run.
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

**Handle service.** `sign_in_help.handle(request_id, *, actor, outcome)` locks the row (`select_for_update`);
if it already has an outcome it changes nothing and the page says "Already handled by <name>." Otherwise it
sets outcome, `handled_at`, `handled_by` and records the event (§5.4) in one transaction. The view returns
404 for an id that does not exist (purged). **An outcome is final** (SR-16, accepted): a mis-click only means
the office does not follow up, and the answer page tells families they can visit the office.

### 5.3 Dropped-request count

`SignInHelpDay.dropped` for today and the last 7 days, on the queue page and the Overview card (§5.2).

### 5.4 Event

New `SecurityEvent` type `SIGN_IN_HELP_HANDLED` ("Sign-in help request handled"), **ROUTINE** (365 days),
added to `SecurityEvent.ROUTINE_TYPES` because `class_for` defaults to HISTORY (`accounts/models.py`); a test
pins the class. `actor` set; `detail = {"outcome": "<value>"}` only. No guardian link, no typed names, no
request id. Not written for test rows. These events give the outcome counts a later channel decision needs
(ADR 0029 Rationale) and outlive the 30-day rows.

No event is written on submit or drop: an anonymous writer must not be able to fill the append-only table
(OD-H5).

**Risk:** High. Migration: the three tables (§3), the event-type choice, the group permissions.

## 6. Purge (R21, OD-G4, SR-06, SR-14)

New command `purge_sign_in_help_requests`. It prints only counts and needs no `--by`: it deletes short-lived
rows that are not security events, like `purge_usage_counters`.

| Deletes | When |
| --- | --- |
| `SignInHelpRequest`, live | `received_at` older than 30 days, open or handled |
| `SignInHelpRequest`, test | older than 24 hours |
| `SignInHelpSourceHit` | older than 2 hours |
| `SignInHelpDay` | older than 30 days |
| everything in the three tables | with `--all` (teardown after a staging test, or when the feature is retired) |

- Runs daily on the Railway cron service as its own `;`-separated step (`docs/OPERATIONS.md`, Retention).
  **Deploy step** after PR 1: add `python manage.py purge_sign_in_help_requests;` to the cron start command
  in staging, later production.
- **Defence in depth:** every stored submit also deletes up to 100 expired rows (§4.4, step 2), so
  retention holds even if the cron step fails while the page is in use.
- **Visible failure:** the queue never lists expired rows, and the Overview card warns holders when expired
  rows exist (§5.2).
- **Backups:** daily and weekly backups keep copies of deleted rows until they expire. The runbook states
  the period and the owner's acceptance (OD-H1) covers it.

## 7. Staged rollout and rollback (ADR 0029 item 4)

| Step | What | Rollback |
| --- | --- | --- |
| PR 1 | Models, queue, handle, event, purge command, group permissions, reset-staff page lines, badge, Overview card, runbook. No public page, so the queue stays empty. | Revert; the reverse migration drops the three tables (deleting any rows, which is the privacy-safe direction; it prints the row counts first, counts only) and removes the two permissions. `SIGN_IN_HELP_HANDLED` events stay (append-only); history views must show an unknown type by its raw name. **Rehearse backward on a copy of the local demo database before merge.** |
| PR 1 deploy | Add the purge step to the staging cron start command. | Remove the step. |
| PR 2 | Public page, caps, legal gate, test mode, sign-in link. Switch off. | Revert. No migration. |
| Staging test | `SIGN_IN_HELP_ENABLED=True`, `SIGN_IN_HELP_TEST_MODE=True`, made-up names only. Check on a real phone: submit, see it in the queue labelled "Test", handle it; a sixth request from the same network in an hour is not stored and the drop count rises; a repeat is not stored; mobile data and Wi-Fi are counted separately; queue at 360, 390 and 1280. Then `purge_sign_in_help_requests --all` and unset both variables. | Unset the variables; `--all`. |
| Live (staging or production) | Only after the owner records OD-H1 acceptance in this spec and in a dated entry in `docs/OPERATIONS.md`: set `SIGN_IN_HELP_RETENTION_ACCEPTED` to that reference and `SIGN_IN_HELP_ENABLED=True`. Production also needs named reset staff and the cron step. | Unset `SIGN_IN_HELP_ENABLED`: page 404, old sign-in text. Run `--all` if collected requests must go at once. |

## 8. Routes and inventory (R12, R14)

- `root:sign-in-help`: added to `INTENTIONALLY_UNPERMISSIONED`
  (`core/tests/test_security_gate4b_route_inventory.py:15`) with the reason "the "Can't sign in?" request
  page, anonymous by design (ADR 0029 option G); does no account lookup and serves no school data", and to
  `test_the_root_application_routes_are_covered`.
- `core:sign-in-help-requests` and `core:sign-in-help-request-handle`: pinned with their permissions in
  `core/tests/route_permissions.json` (`python core/tests/route_inventory.py --write`).
- Tests on all three: `X-Frame-Options: DENY`; a POST without a CSRF token gets the custom failure page
  (`CSRF_FAILURE_VIEW`); GET to the handle route gets 405.

## 9. Privacy, logging and retention (R13, SR-13)

- **The application never logs, measures, alerts on or puts in a URL** the typed values or the source
  address. POST data is masked in crash reports (`PrivacyExceptionReporterFilter`,
  `config/error_reporting.py:30`); Telegram and email alerts use an allow-list with no values. No usage
  counters (ADR 0027) on either page.
- **Platform logs:** the hosting platform's access log records each request's path, status and client
  address; the app cannot remove that and its retention is set by the host. Typed values are never in the
  path. PR 2 confirms the web start command uses no custom access-log format that includes bodies.
- Tests capture logs on a stored submit, a dropped submit, a form error, a handle and a forced database
  error on insert, and assert none of the typed values appear.
- Retention: live request rows 30 days, test rows 24 hours, hits 2 hours, day rows 30 days (§6);
  `SIGN_IN_HELP_HANDLED` events 365 days (ROUTINE, monthly `purge_security_events`). Nothing is HISTORY.
- `docs/OPERATIONS.md` gets a section: the three settings, the legal gate and where acceptance is recorded,
  test mode and teardown, the cron step, the backup period, and the daily queue routine (Appendix A).
- ADR 0013 ("no self-service password recovery") needs no change: the page resets nothing (OD-G12). PR 2
  adds a "See also ADR 0029" line to it.

## 10. Tests (minimum)

**PR 1:** the three models migrate forward and backward on SQLite and Postgres; the reverse prints counts
only; the data migration creates the permissions, adds them to an existing group, does nothing without the
group, does not raise on a group with other permissions, is idempotent, and its reverse leaves the group's
other permissions alone; a holder of only `reset_guardian_password` gets 403 on the queue; a group member
sees the queue (200) and handles a request; a School Administrator outside the group, a teacher and a
guardian get 403; anonymous goes to sign-in; outcome required and limited to the five values; a second
handle changes nothing and says who handled it; handle of a missing id returns 404; one ROUTINE
`SIGN_IN_HELP_HANDLED` event with only `{"outcome": …}`, none for a test row; values with `<script>`, `'`, `&`
and U+202E render escaped inside `<bdi>` on both tabs; expired rows hidden and the Overview warning shown;
purge deletes each table at its own age, `--all` empties all three; drop notice shows today and the last
7 days; badge counts only open rows inside retention; a non-holder runs no badge query; reset staff page and
`role_permission_gaps` list queue holders; model not in the Django admin; route inventory updated; CSRF and
frame denial; logs hold no typed values.

**PR 2:** gate: page 404 unless the switch is on with exactly one of acceptance or test mode; acceptance plus
test mode stops start-up; switch on, `DEBUG` off and no trusted proxies stops start-up; invalid flag values
stop start-up; test mode shows the banner and stores `is_test`; page renders with no query on school tables;
signed-in GET and POST redirected with nothing stored; field rules: required, lengths, NFKC, whitespace
collapsed, Malayalam with ZWJ accepted, U+202E, U+2066, U+200B, zalgo, fullwidth digits, split digits,
digits in a name, a fourth digit in the class, `<`, `@`, `:` refused; a form error stores nothing and takes
no lock; R1: known, unknown, throttled and repeated input give the same status, template, body (CSRF token
aside), headers and reads, known and unknown the same writes; per-source cap at the sixth stored request in
60 minutes, global cap at the 201st of the day, repeat within 7 days dropped and after 7 days stored, all
with frozen time; **Postgres concurrency: 20 parallel submissions from one source store exactly 5, and from
20 sources with 3 slots left store exactly 3**; IPv6 addresses in one /64 share a bucket, an IPv4-mapped
address equals its IPv4; `"unknown"` source gets only the global cap and writes no hit; the hash differs from
`security.source_key` for the same address; hits older than 2 hours are deleted on submit; no change to
`User`, `GuardianAccount`, `GuardianStudentAccess`, `LoginFailure` or `SecurityEvent` on submit; `never_cache`
on the page; no session row created; CSRF and frame denial; no typed value in logs or any `Location` header.

**Every PR:** `ruff check .`; `makemigrations --check --dry-run` clean after the PR's own migration; route
inventory test; targeted tests for accounts, the sign-in page, reset staff and the new module; full CI on the
final head.

## 11. Acceptance checklist

- [x] Security-focused review of r1 (ADR 0029 item 3); confirmed findings applied in r2 (§14).
- [ ] Reviewer re-check of r2 (advised for SR-01 and SR-04).
- [ ] Owner decisions OD-H2 to OD-H5 recorded (§12).
- [ ] Owner approves the spec for build.
- [ ] PR 1 merged after a backward-migration rehearsal; purge step added to the staging cron.
- [ ] PR 2 merged with the switch off.
- [ ] Staging test in test mode recorded, then `--all`.
- [ ] **OD-H1: owner's acceptance of the retention and legal risk recorded** (this spec and a dated
      `docs/OPERATIONS.md` entry); only then `SIGN_IN_HELP_RETENTION_ACCEPTED` is set anywhere.

## 12. Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-H1 | Collecting real requests before counsel confirms retention (ADR 0029 item 5). **Not approved.** | (a) Build and merge with the page off; collect real requests only after the owner records acceptance, enforced by `SIGN_IN_HELP_RETENTION_ACCEPTED` (§4.1); (b) wait for counsel before building | (a). Building is harmless with the page off; the legal decision stays open and separate. |
| OD-H2 | Who sees the queue | (a) Dedicated permissions (OD-G14), added by migration to "Portal password resets"; the views never check `reset_guardian_password` (§5.1); (b) a separate group and page | (a). One list of named staff, without reusing the reset permission. |
| OD-H3 | Prompt for waiting requests | (a) Sidebar badge and Overview card, with drop and stale-row notices for holders; (b) none | (a). Without a prompt requests sit unseen until purged. |
| OD-H4 | Caps | Accept 5 per source (IPv6 per /64) per hour, 200 per day and repeats dropped for 7 days as starting values; set others | Accept; tune on staging. |
| OD-H5 | Deviations from ADR 0029 wording (header) | Accept R10 as ROUTINE with no event on submit or drop; no network identifier on request rows; R14 as "only new anonymous route" | Accept. Each is narrower or follows the approved reset-spec precedent. |

## 13. Out of scope and accepted residual risks

- Any reply to the requester, any channel and owner notification (OD-G2; T10 High, accepted).
- A flood from many networks can still fill the daily cap and push real requests out; the drop count shows
  on the Overview card (T18, M for office time, accepted in ADR 0029). No separate cap on open rows: the
  daily cap and 30-day purge already bound the backlog at about 6,000 rows (SR-15).
- No CAPTCHA (third-party service, accessibility cost) and no hidden extra field (R21 allows exactly three
  fields). Revisit only if staging shows automated spam.
- Spam can make staff call a real family who asked for nothing; repeats are dropped for 7 days and Appendix
  A's script resets nothing on the call (T18).
- Test mode out of production is a runbook rule, not enforced in code (§4.1).
- Outcomes are final (SR-16).
- The page is in English only.
- Matching is manual; a misspelt name may get `NO_MATCH`. The answer page tells families they can visit.

## 14. Review record (r1 → r2)

Security-focused review of r1, 2026-11-26 (independent reviewer, ADR 0029 item 3). Verdict: "Approve r2
after these changes"; a short re-check of r2 advised.

| ID | Sev | Finding | r2 |
| --- | --- | --- | --- |
| SR-01 | High | Count-then-insert caps not atomic across workers | Applied: gate-row lock (§4.3, §4.4); Postgres concurrency tests |
| SR-02 | High | IPv6 per-address lets one /64 bypass the per-source cap | Applied: /64 bucket, IPv4-mapped folded (§4.3) |
| SR-03 | Medium | `"unknown"` and empty trusted proxies collapse sources | Applied: no bucket for unknown; start-up refusal (§4.1, §4.3) |
| SR-04 | Medium | Same key, 30-day pseudonymous address log | Applied: sub-key; no source on request rows; hits kept 2 hours (§3.3) |
| SR-05 | Medium | Drop-count create race breaks the outer transaction | Applied: savepoint; counts moved onto the gate row (§3.2, §4.4) |
| SR-06 | High | Purge failure visible only on the queue page | Applied: Overview warning, purge on submit, backup note (§5.2, §6) |
| SR-07 | High | OD-H1 enforced only by the runbook | Applied: acceptance setting checked in code, test mode, `--all` (§4.1, §7, §11) |
| SR-08 | Medium | Permission migration and reset-staff interplay under-specified | Applied (§5.1) |
| SR-09 | Medium | Bidi, format characters, split and non-ASCII digits, zalgo | Applied: category allow-list after NFKC, `<bdi>` (§4.2, §5.2) |
| SR-10 | Medium | R10 and R14 departures not flagged | Applied: header deviations, OD-H5 |
| SR-11 | Medium | R1 test should include headers; switch-off oracle | Applied (§4.4) |
| SR-12 | Low | Badge filter and index | Applied (§3.1, §5.2) |
| SR-13 | Low | "Never logged" overstated; DB error text | Applied: reworded, forced-error test (§9) |
| SR-14 | Medium | Reverse migration deletes requests silently | Applied: stated, counts printed, `--all` (§6, §7) |
| SR-15 | Medium | Repeat-name harassment; flood hidden | Applied: 7-day repeat rule, drop count on the card. Not applied: open-row cap (§13 reason) |
| SR-16 | Low | Final outcome cannot be corrected | Not applied: accepted as final (§5.2) |
| SR-17 | Low | Escaping rules beyond element text | Applied (§5.2) |
| SR-18 | Info | Anonymous CSRF and session behaviour | Applied: stated (§4.4) |
| SR-19 | Medium | Page notice promises not literally true | Applied: reworded (§4.2); legal question stays in OD-H1 |
