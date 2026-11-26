# G-06 spec: "Can't sign in?" request page (ADR 0029, option G)

- **Status:** **Approved for implementation with collection disabled. Collection of real requests is not
  approved.** r3, owner decisions OD-H1 to OD-H5 recorded 2026-11-26 (§12). Boundaries in §12. History: r1 had the security-focused review (ADR 0029
  item 3; SR-01 to SR-19); r2 applied it and the owner's conditions on OD-H1 and OD-H2, then removed staging
  test mode on the owner's condition; the focused re-check of r2 found RC-01 to RC-13; **r3 applies them**
  and the owner's six explicit points (§14). The final focused re-check approved r3 for owner decision
  after text edits FC-01 to FC-06, applied here with no further review round (§14). Merging this spec and
  starting PR 1 each still need the owner's separate approval.
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
  1. R10 lists "request handled or refused" as HISTORY events. This spec records "handled" as **ROUTINE**
     (365 days), as the reset spec did (S-03), and writes **no event on submit, drop or failure**: the daily
     drop count is the refusal record, aggregate only (R6).
  2. R21 allows "the hashed source" on request rows. This spec is stricter: request rows carry **no network
     identifier**; a keyed hash lives only in per-hour limit rows (§3.3).
  3. R14 says "the only anonymous route". Read here as "the only **new** anonymous route": sign-in,
     `core:school-logo` and `root:pwa-manifest` were public before.
  4. R21 lists "received time and hashed source only". This spec adds a **keyed repeat key** (`repeat_key`)
     derived from the typed text, and a repeat rule. R1 tolerates differing writes because "the cap ignores
     what was typed"; the repeat rule does depend on typed text, but **never on school data**, only on other
     **open** requests, and a repeat looks identical to a store to the visitor (§4.3, §4.4).
  5. Per-hour limit rows (§3.3) are kept until the next submit or cron run after their hour ends, so **up to
     about 6 hours** with the cron schedule in force on staging, longer only if both stop. They hold no typed
     value and share no column or key with requests, but at low traffic a request and an hour row that are
     alone in the same hour can be matched by timing alone. Source keys are not linkable across hours.
- **Not in this spec:** any message to the guardian, any reset from the page, any channel (OD-G2 stays
  "none"), owner notification (T10 stays High, accepted).

## 1. Outcome

A guardian who cannot sign in taps **"Can't sign in?"** on the sign-in page and fills in three short
fields. The page always gives the same answer and never says whether an account exists. Nothing is
reset and nothing is sent. Named office staff see the request in a queue, find the family in the
guardian list themselves, call **only the number on the record** (ADR 0029 Appendix A), book a visit,
and reset the password in person with the existing reset form. Requests are capped per source and per
day, an open request is not stored twice, rows are deleted after 30 days, and the office sees how many
were dropped.

## 2. Requirements covered

| ADR 0029 | Where |
| --- | --- |
| R1 no account-existence leak | §4.4; tests §10 |
| R6 caps (5 per source per hour, 200 per day), dropped-request count | §4.3, §5.3 |
| R7 generic responses | §4.4 |
| R10 audit events | §5.4; deviation OD-H5 (1) |
| R11 no grant changes | §4.4; test |
| R12 CSRF, frame denial | site-wide; tests on all three new routes (§8) |
| R13 logging hygiene | §9; test |
| R14 route inventory | §8; deviation OD-H5 (3) |
| R21 three fields, no lookup, autoescape, daily purge | §4.2, §4.4, §5.2, §6; deviations OD-H5 (2), (4) |
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
| `repeat_key` | CharField 64 | keyed HMAC of the three values (§4.3) |
| `received_at` | DateTimeField, indexed | |
| `outcome` | CharField, choices (§5.2), blank | blank means open |
| `handled_at` | DateTimeField, null | |
| `handled_by` | FK `accounts.User`, `SET_NULL`, null | |

Indexes: `(outcome, received_at)` for the open count; `(repeat_key, outcome, received_at)` for the repeat
rule. Default permissions only (`view_signinhelprequest`, `change_signinhelprequest`; add and delete are
never granted). The outcome columns serve the queue (R22). **No network identifier**, phone, email, free
text or user agent is stored on the row.

### 3.2 `accounts.SignInHelpDay`

`day` (DateField, unique, local date in `Asia/Kolkata`, `config/settings.py:211`), `stored` and `dropped`
(PositiveInteger). One row per day with any submission. It is the **gate row** for the caps (§4.3) and
the drop count (§5.3). No personal data, no source.

### 3.3 `accounts.SignInHelpSourceHour`

`source_key` (CharField 64), `hour_start` (DateTimeField: the start of the clock hour, local time),
`count` (PositiveInteger); unique `(source_key, hour_start)`. One row per source and clock hour with at
least one **stored** request. It holds **no typed value, no request id and no exact time**, and shares no
column or key with requests. At low traffic, a request and an hour row that are alone in the same hour can be
matched by timing alone, while the row exists (FC-02, OD-H5 (5)). Because the hour is part of the keyed input
(§4.3), one source's rows in different hours cannot be linked to each other.
Deleted when its hour has ended: on the next submit, or the next cron run (§6).

**Risk:** High. Migration: three new tables. Reverse drops them (§7).

## 4. PR 2: the public page

### 4.1 Route, switch and legal gate (OD-H1, SR-07, RC-08, RC-09)

| Name | Path | Methods | Guard |
| --- | --- | --- | --- |
| `root:sign-in-help` | `accounts/sign-in-help/` | GET, POST (`require_http_methods`) | none (anonymous by design), `never_cache` |

In `config/urls.py` next to `login`, view in `accounts/views.py`. The URL is always registered; the view
reads the gate from `settings` on every request (so tests can override it) and returns Django's standard 404
when the page is off.

**Settings**, parsed in `config/settings.py`:

| Setting | Type | Meaning |
| --- | --- | --- |
| `SIGN_IN_HELP_ENABLED` | flag (`config/deployment_safety.parse_flag`) | master switch, off by default |
| `SIGN_IN_HELP_RETENTION_ACCEPTED` | string, stripped | empty, `OD-H1 YYYY-MM-DD` (the owner's real acceptance), or `LOCAL YYYY-MM-DD` (local testing only) |

A reference is **valid** when it matches one of the two forms exactly and the date is a real calendar date.
There is no future-date rule (RC-09: it adds no security, and comparing dates at settings time risks a
time-zone error).

**Every combination fails closed. First matching row wins, top to bottom:**

| # | `ENABLED` | `RETENTION_ACCEPTED` | Other | Result |
| --- | --- | --- | --- | --- |
| 1 | invalid value | any | | start-up refused (`parse_flag`) |
| 2 | off or unset | any (even malformed) | | page 404; a malformed value gives a system check Warning only, so a leftover typo never stops the site |
| 3 | on | malformed | | start-up refused |
| 4 | on | `LOCAL …` | `DEBUG` and `TESTING` both false | start-up refused (RC-08) |
| 5 | on | empty or unset | | page 404, "on but not accepted" made visible (below) |
| 6 | on | `OD-H1 …`, or `LOCAL …` with `DEBUG` or `TESTING` true | `DEBUG` false, `TESTING` false and `TRUSTED_PROXIES` empty | start-up refused (SR-03: every request would share the proxy's address) |
| 7 | on | `OD-H1 …`, or `LOCAL …` with `DEBUG` or `TESTING` true | | **page served**, and the sign-in page shows the "Can't sign in?" link |

`TESTING` is the existing flag (`config/settings.py:32`). With the switch off, nothing is refused (RC-09).
**One function decides** (FC-05): `accounts.sign_in_help.gate_state(settings)` returns off, not accepted,
refused (with the reason) or served. Settings parsing, the view, the system check and the Overview card line all
call it, so they cannot disagree, and runtime setting overrides in tests behave like start-up.

**"On but not accepted" is visible (row 5, RC-09, FC-05):** one line logged at start-up from
`AccountsConfig.ready` ("Sign-in help is switched on but not accepted; the page is off."), the guaranteed
signal; a system check Warning tagged `Tags.database` like `core.W001` (`core/checks.py:21`), so `migrate` also
shows it where the deploy runs `migrate`; and a line on the Overview card for superusers.

When the page is off, the sign-in page keeps today's text ("Forgot your password? Ask the school office to
reset it."). When served, it shows a **"Can't sign in?"** link in its place
(`templates/registration/login.html`, under the form, phone and desktop).

**No deployed test mode.** A test mode would need a reliable marker telling staging from production; the
project has none. Testing before acceptance runs only on a local machine (§7, local test), using a `LOCAL`
reference with `DEBUG=True`. **The `OD-H1` form is never set on a local machine**, and a `LOCAL` value copied
to a deployed instance stops its start-up while the feature is enabled (row 4), unless that instance runs with
`DEBUG` on, which is already an unsafe misconfiguration (accepted, §13).

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
- Refused everywhere: every other format character (Cf, including U+202E, U+2066 to U+2069, U+200B),
  control (Cc), private use (Co), surrogates (Cs), line and paragraph separators, unassigned code points,
  and any run of more than 3 combining marks.

So links, emails and phone numbers cannot be typed. Errors show per field in the existing form style.
Validation depends only on the typed text, never on school data, so an error reveals nothing about
accounts. A form with errors stores nothing, opens no transaction and does not count toward any cap.

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

### 4.3 Caps, repeats and keys (R6, OD-G15, SR-01 to SR-04, RC-02, RC-04 to RC-07, RC-12)

Constants in a new module `accounts/sign_in_help.py`:

| Rule | Start value | Counted from |
| --- | --- | --- |
| Per source | 5 stored requests in the current clock hour | `SignInHelpSourceHour.count` for this source and hour |
| Global | 200 stored requests per local day | `SignInHelpDay.stored` |
| Repeat | the same three answers as an **open** request received in the last 7 days | `SignInHelpRequest` with the same `repeat_key` and `outcome = ""` |

The per-source window is the fixed clock hour, not a sliding 60 minutes, so the limit rows need no exact
time (RC-05). A source can store up to 5 just before and 5 just after the hour turns; accepted.

Repeats count only against **open** requests (RC-06): once staff record an outcome, the same answers are
stored again. A spammer who submits a family's names therefore cannot silence that family's own request
after staff have called them.

**Source bucket (SR-02, SR-03).** From `accounts.security.client_address` (`accounts/security.py:49-58`):
an IPv4-mapped IPv6 address becomes its IPv4 address; an IPv6 address becomes its **/64 network**; an IPv4
address is used as is. When the address is `"unknown"`, the bucket is a fixed constant that never gets a
row (RC-12): the same count query runs and finds nothing, so only the global cap and the repeat rule apply,
and no hour row is written.

**Keys (owner point, SR-04, RC-07).** Two separate keyed, domain-separated HMAC-SHA-256 values. Neither is
a plain hash, and neither uses the key of the other or of sign-in throttling:

| Value | Key | Input |
| --- | --- | --- |
| `source_key` (§3.3) | sub-key `HMAC(SOURCE_HASH_KEY, "everclass/sign-in-help/source/v1")` | the bucket string, a separator and `hour_start` (ISO 8601), so one source's rows in different hours cannot be linked (FC-02) |
| `repeat_key` (§3.1) | `salted_hmac("everclass/sign-in-help/repeat/v1", value, algorithm="sha256").hexdigest()`, keyed by `SECRET_KEY`, not by `SOURCE_HASH_KEY`. `algorithm="sha256"` is required: Django's default is SHA-1 (FC-01) | the three cleaned values, case-folded, joined with U+001F (the allow-list refuses every control character, so the join is unambiguous) |

Sign-in throttling uses `HMAC(SOURCE_HASH_KEY, address)` directly (`accounts/security.py:61-63`), so neither
value can be compared with `LoginFailure` or `SecurityEvent` source values without the keys. `repeat_key` is
used only in the model's own repeat query: never shown, exported, logged or compared anywhere else.
Rotating either key resets the matching counts or repeat detection; that is harmless. By default
`SOURCE_HASH_KEY` is itself derived from `SECRET_KEY` (`config/settings.py:175`), so the two keys are separate
derivations of one root secret unless `DJANGO_SOURCE_HASH_KEY` is set (FC-06); domain separation still holds.

**Exactness (SR-01, RC-02, RC-04).** Every valid submission serialises on today's gate row (§4.4), and every
writer that changes what the caps and the repeat rule check (submit) takes the gate first. On **PostgreSQL**,
the production database, both caps and the repeat rule are therefore exact across workers and processes.
SQLite is for development and tests only; its concurrent behaviour is not guaranteed and no global SQLite
setting is changed for this feature. The concurrency tests run on PostgreSQL only (CI runs PostgreSQL 16).

Carrier-grade NAT can put a whole area behind one address (threat model §6); 5 per hour is a starting value
to watch after acceptance.

### 4.4 Submit path (R1, R7, R11, RC-01 to RC-03)

Read `now` **once**, before the transaction. `day = localdate(now)`; the clock hour, the 7-day cutoff,
the 30-day cutoff and `received_at` all come from this `now`. Then, in one `transaction.atomic`:

1. **Timeouts (PostgreSQL).** First statements: `SET LOCAL lock_timeout = '2s'` and
   `SET LOCAL statement_timeout = '5s'`. `SET LOCAL` lasts only until this transaction commits or rolls
   back, so it cannot leak into later requests on the same connection (owner point). A test checks that
   after a submit, `SHOW lock_timeout` and `SHOW statement_timeout` on the same connection give the server
   defaults; it uses `TransactionTestCase`, because the outer transaction of `TestCase` would keep `SET LOCAL`
   alive (FC-04).
2. **Gate.** Get or create today's `SignInHelpDay` inside a savepoint (retry the read on `IntegrityError`, as
   `core/usage.py:293-296` does), then `select_for_update` it. **The `stored` and `dropped` values used below
   come only from this locking query**, never from the get-or-create result (RC-02). A request that locked
   the old day's row just before local midnight counts against the old day; accepted.
3. **Housekeeping, independent of the input,** in the shared lock order (below): lock with
   `select_for_update(skip_locked=True)` at most 100 `SignInHelpRequest` rows past retention, ordered by
   pk, and delete those pks; then the same for `SignInHelpSourceHour` rows whose hour has ended.
4. **Checks.** Count this bucket's row for the current hour (the same query when there is no bucket, §4.3);
   check for an open request with the same `repeat_key` since the 7-day cutoff.
5. **Decide and write.** Stored when `stored < 200`, the hour count is below 5, and it is not a repeat:
   insert the request, then insert or increment the hour row (inside a savepoint for the create race), then
   `stored += 1`. Otherwise `dropped += 1`.

After the transaction **commits**, render the answer page (RC-01: the lock never covers rendering).

**Shared lock order (owner point, RC-03).** Every transaction that touches these tables takes locks in this
order: (1) today's `SignInHelpDay` gate row; (2) other `SignInHelpDay` rows, by pk; (3) `SignInHelpRequest`
rows, by pk; (4) `SignInHelpSourceHour` rows, by pk. Deletes lock with `skip_locked`, so they never wait on a
row someone else holds. The cron purge (§6) follows the same order. The handle service (§5.2) locks only one
request row and nothing else, so it cannot form a cycle; if housekeeping deleted that row first, handle
returns 404.

**Failure path (owner point, RC-01).** The handler catches `DatabaseError` around the whole
`with transaction.atomic():` statement, including its exit, so a failure at commit is caught too (FC-04). Any
such error (lock timeout, statement timeout, deadlock, connection error, commit failure) rolls the transaction
back whole: **no request, no hour row, no day counter and no
audit event is written.** The view then returns one fixed page, status 503 with `Retry-After: 120`:

> **The school's page is busy.** Please try again in a few minutes, or contact the school office.

It is the same for every input, contains nothing typed, and is not the "Thank you" page, so a family never
believes an unsaved request was sent. One log line records the failure by exception class only (never the
exception message, which can quote values). A failure is caused by load, not by what was typed, so it reveals
nothing about accounts.

**No account lookup.** No query on `User`, `Guardian`, `Student`, `GuardianAccount` or any other school
table. On success the answer is rendered with status 200 from one template whether the request was stored or
dropped:

> **Thank you.** The school will contact you using the details it already has. If your phone number has
> changed, please visit the school office. · Back to Log in

The answer is rendered directly (no redirect), so the page is one route and no typed value ever appears in a
URL. Refreshing re-posts; the repeat rule then drops it while the first request is open.

**R1 equality (SR-11).** Known input (names matching a real guardian and child) and unknown input give the
same status, template, body (apart from the CSRF token), response headers (`Set-Cookie`, `Cache-Control`,
`Vary`) and the same SQL, writes included. Throttled and repeated input give the same status, template,
body, headers and reads; their write differs (`dropped` instead of the inserts), which reveals nothing about
accounts because the caps ignore what was typed and the repeat rule reads only other open requests, never
school data. **A repeat cannot be told from a store by the visitor** (RC-07). Tests compare captured SQL, not
timing. No session is created for an anonymous visitor (an empty session is never saved); GET sets only the
CSRF cookie (SR-18).

Known differences that reveal nothing about accounts, accepted: with the page off, a POST without a CSRF
token gets 403 (CSRF middleware runs first) and with a token gets 404; a validation error re-shows the form;
a database failure gives the 503 page.

**No grant or login change (R11).** A submission writes only to the three tables in §3; a test asserts no
row changes in `User`, `GuardianAccount`, `GuardianStudentAccess`, `LoginFailure` or `SecurityEvent`.

**Abuse outside Django (SR-18, RC-01).** CSRF is not a rate limit: one GET gives a token for unlimited POSTs.
Invalid POSTs cost only validation CPU and open no transaction. A flood of valid POSTs from many sources
queues on the gate for at most 2 seconds each and then gets the 503 page; sustained volume is left to the
hosting platform.

**Risk:** Critical (anonymous write path).

## 5. PR 1: the office queue

### 5.1 Who sees it (R22, OD-G14, OD-H2, SR-08, RC-13)

The views check **only** the dedicated permissions `accounts.view_signinhelprequest` (list) and
`accounts.change_signinhelprequest` (record an outcome), never `core.reset_guardian_password`.

**Data migration**, placed in `core` (which already depends on `accounts`), depending on the accounts model
migration and `core` 0096:

- Creates the accounts permissions itself with `create_permissions`, as `core/migrations/0096` does
  (lines 13-19), because permissions otherwise appear only after `post_migrate`.
- If the "Portal password resets" group (`core/reset_staff.py:15`) exists, adds both permissions to it. If it
  does not exist, does nothing (superusers only). It never raises because the group has other permissions,
  and running it twice changes nothing.
- Reverse removes only these two permissions from the group. Permission and content-type rows left after the
  models are dropped are harmless.

**Reset staff page and reviews** (`core/reset_staff.py`, reset spec §6a):

- One line under the member list: "Members also see sign-in help requests." The add confirmation says "This
  also lets them see sign-in help requests."
- The read-only "Can also reset" block gains "Can also see sign-in help requests": superusers, direct grants
  and other groups holding either queue permission (`core/reset_staff.py:83` pattern).
- `role_permission_gaps` prints holders of both queue permissions.
- `core.W001` (`core/checks.py`) is unchanged. A new Warning applies only when the page is served and no active
  user can see the queue, counting superusers the same way the reset holders check does (RC-13).

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
(`core/dashboard.py`). The card also shows, when they apply: "N not saved today because of limits or repeats";
"Old requests are waiting to be deleted. Check the cron job."; and, to superusers, "Sign-in help is switched on
but not accepted" (§4.1). Only holders of the view permission (and superusers) see the card. `queue_counts`
checks `has_perm` first and caches per request, so other users run no query; a test pins that.

**Page.**

- At the top, ADR 0029 Appendix A as a short checklist: check the guardian's profile for a phone change in the
  last 30 days (then in person only); call only the number on the record; never a number from anyone else;
  book a visit; reset at the visit with "In person, with identity documents"; never read a password aloud.
- Two tabs, **Open** (oldest first) and **Handled** (newest first), paginated with `build_table`
  (`core/tables.py:73`), 25 per page. Columns: received (date and time), your name, child's name, class and
  section; on Handled also outcome, by whom and when.
- **Rendering rules (SR-17, SR-09):** typed values appear only as element text, autoescaped, each inside
  `<bdi>`. Never in an attribute, `title`, `data-*`, `json_script`, a message built with `mark_safe`, a CSV or
  an email. No `urlize`, no `|safe`. "Already handled by <name>" is escaped too.
- No search box and no "find guardian" link: a prefilled search would put typed names in a URL and the access
  logs (R13). Staff type the name into the guardian list themselves.
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

**Handle service.** `sign_in_help.handle(request_id, *, actor, outcome)` locks the one row
(`select_for_update`). It returns 404 if the row does not exist or is past retention (RC-11). If the row
already has an outcome it changes nothing and the page says "Already handled by <name>." Otherwise it sets
outcome, `handled_at`, `handled_by` and records the event (§5.4) in one transaction. **An outcome is final**
(SR-16, accepted): a mis-click only means the office does not follow up, the same answers can be sent again
(repeats count only open requests), and the answer page tells families they can visit the office.

### 5.3 Dropped-request count

`SignInHelpDay.dropped` for today and the last 7 days, on the queue page and the Overview card (§5.2). A
database failure (§4.4) writes nothing, so it is not counted; accepted.

### 5.4 Event

New `SecurityEvent` type `SIGN_IN_HELP_HANDLED` ("Sign-in help request handled"), **ROUTINE** (365 days), added
to `SecurityEvent.ROUTINE_TYPES` because `class_for` defaults to HISTORY (`accounts/models.py`); a test pins
the class. `actor` set; `detail = {"outcome": "<value>"}` only. No guardian link, no typed names, no request
id. These events give the outcome counts a later channel decision needs (ADR 0029 Rationale) and outlive the
30-day rows.

No event is written on submit, drop or failure: an anonymous writer must not be able to fill the append-only
table (OD-H5 (1)).

**Risk:** High. Migration: the three tables (§3), the event-type choice, the group permissions.

## 6. Purge (R21, OD-G4, SR-06, SR-14, RC-03, RC-11)

New command `purge_sign_in_help_requests`. It prints only counts and needs no `--by`: it deletes short-lived
rows that are not security events, like `purge_usage_counters`.

| Deletes | When |
| --- | --- |
| `SignInHelpRequest` | `received_at` older than 30 days, open or handled |
| `SignInHelpSourceHour` | hour has ended |
| `SignInHelpDay` | older than 30 days |
| everything in the three tables | with `--all --yes` (after a local test, or when the feature is retired); without `--yes` it prints the three counts and stops |

- **Lock order (owner point):** each batch is one short transaction with the same `SET LOCAL` timeouts as
  §4.4: lock today's gate row **if it exists** (cron never creates it; without it the batch proceeds, which is
  safe because every delete uses `skip_locked` and so never waits), then select at most 1,000 rows of one table
  ordered by pk with `skip_locked`, delete those pks, commit. Tables in the §4.4 order. A batch holds the gate
  only for its own deletes (FC-03).
- **Failures are not silent (FC-03):** a batch that fails (for example on a lock timeout under a flood) makes the
  command exit non-zero. `--all --yes` loops until a pass deletes nothing, prints the remaining count and exits
  non-zero if any rows remain. To retire the feature or wipe after a test: switch the page off first, then run
  `--all --yes`.
- **Never touches `SecurityEvent`.** `SIGN_IN_HELP_HANDLED` events (outcome only, no personal data) stay until
  the monthly `purge_security_events` removes them after 365 days, `--all` included.
- **Schedule:** runs on the Railway cron service as its own `;`-separated step, each cron run (every 6 hours on
  staging today). **Deploy step** after PR 1: add `python manage.py purge_sign_in_help_requests;` to the cron
  start command in staging, later production.
- **Defence in depth:** every stored submit also deletes expired rows (§4.4, step 3), so retention holds even if
  the cron step fails while the page is in use.
- **Visible failure:** the queue never lists expired rows, and the Overview card warns holders when expired rows
  exist (§5.2).
- **Backups:** daily and weekly backups keep copies of deleted rows until they expire. The runbook states the
  period before acceptance, and the owner's acceptance (OD-H1) covers it.

## 7. Staged rollout and rollback (ADR 0029 item 4)

| Step | What | Rollback |
| --- | --- | --- |
| PR 1 | Models, queue, handle, event, purge command, group permissions, reset-staff page lines, badge, Overview card, runbook. No public page, so the queue stays empty. | Revert; the reverse migration prints the three row counts (counts only), then drops the tables (deleting any rows, the privacy-safe direction) and removes the two permissions. `SIGN_IN_HELP_HANDLED` events stay (append-only); history views show an unknown type by its raw name. **Rehearse backward on a copy of the local demo database before merge.** |
| PR 1 deploy | Add the purge step to the staging cron start command. | Remove the step. |
| PR 2 | Public page, caps, legal gate, failure page, sign-in link. Switch off; no acceptance set anywhere. | Revert. No migration. |
| Local test | On a local machine only: local PostgreSQL, `DEBUG=True`, demo data only (never a restore of real data), `SIGN_IN_HELP_RETENTION_ACCEPTED=LOCAL <date>`, made-up names, `runserver` bound to the LAN address in use. On a real phone over Wi-Fi: submit, see it in the queue, handle it; a sixth request in the hour is not stored and the drop count rises; a repeat of an open request is not stored and is stored again after it is handled; queue at 360, 390 and 1280. Then `--all --yes`; never copy that database elsewhere. | Nothing deployed. |
| Live (staging, then production) | Only after the owner records OD-H1 acceptance in this spec and in a dated entry in `docs/OPERATIONS.md`: set `SIGN_IN_HELP_RETENTION_ACCEPTED` to that `OD-H1 <date>` reference and `SIGN_IN_HELP_ENABLED=True`. First check on staging: mobile data and Wi-Fi are counted as separate sources. Rows from these checks are real rows under the accepted retention. Production also needs named reset staff and the cron step. | Unset `SIGN_IN_HELP_ENABLED`: page 404, old sign-in text. Run `--all --yes` if collected requests must go at once. |

## 8. Routes and inventory (R12, R14)

- `root:sign-in-help`: added to `INTENTIONALLY_UNPERMISSIONED`
  (`core/tests/test_security_gate4b_route_inventory.py:15`) with the reason "the "Can't sign in?" request page,
  anonymous by design (ADR 0029 option G); does no account lookup and serves no school data", and to
  `test_the_root_application_routes_are_covered`.
- `core:sign-in-help-requests` and `core:sign-in-help-request-handle`: pinned with their permissions in
  `core/tests/route_permissions.json` (`python core/tests/route_inventory.py --write`).
- Tests on all three: `X-Frame-Options: DENY`; a POST without a CSRF token gets the custom failure page
  (`CSRF_FAILURE_VIEW`); GET to the handle route gets 405.

## 9. Privacy, logging and retention (R13, SR-13)

- **The application never logs, measures, alerts on or puts in a URL** the typed values, the repeat key or the
  source address. POST data is masked in crash reports (`PrivacyExceptionReporterFilter`,
  `config/error_reporting.py:30`); Telegram and email alerts use an allow-list with no values. The failure path
  logs the exception class only. No usage counters (ADR 0027) on either page.
- **Platform logs:** the hosting platform's access log records each request's path, status and client address;
  the app cannot remove that and its retention is set by the host. Typed values are never in the path. PR 2
  confirms the web start command uses no custom access-log format that includes bodies.
- Tests capture logs on a stored submit, a dropped submit, a form error, a handle, a lock timeout and a forced
  database error on insert, and assert none of the typed values appear.
- Retention: request rows 30 days; hour rows until their hour has ended plus the next submit or cron run; day rows
  30 days (§6); `SIGN_IN_HELP_HANDLED` events 365 days (ROUTINE, monthly `purge_security_events`). Nothing is
  HISTORY.
- `docs/OPERATIONS.md` gets a section: the two settings and the fail-closed table, the legal gate and where
  acceptance is recorded, the rule that `OD-H1` is never set on a local machine, local testing and `--all --yes`,
  the cron step, the backup period, and the daily queue routine (Appendix A).
- ADR 0013 ("no self-service password recovery") needs no change: the page resets nothing (OD-G12). PR 2 adds a
  "See also ADR 0029" line to it.

## 10. Tests (minimum)

**PR 1:** the three models migrate forward and backward on SQLite and PostgreSQL; the reverse prints counts only;
the data migration creates the permissions, adds them to an existing group, does nothing without the group, does
not raise on a group with other permissions, is idempotent, and its reverse leaves the group's other permissions
alone; a holder of only `reset_guardian_password` gets 403 on the queue; a group member sees the queue (200) and
handles a request; a School Administrator outside the group, a teacher and a guardian get 403; anonymous goes to
sign-in; outcome required and limited to the five values; a second handle changes nothing and says who handled
it; handle of a missing or expired id returns 404; one ROUTINE `SIGN_IN_HELP_HANDLED` event with only
`{"outcome": …}`; values with `<script>`, `'`, `&` and U+202E render escaped inside `<bdi>` on both tabs; expired
rows hidden and the Overview warning shown; purge deletes each table at its own age, in batches, never touches
`SecurityEvent`; `--all` without `--yes` deletes nothing; drop notice shows today and the last 7 days; badge counts
only open rows inside retention; a non-holder runs no badge query; reset staff page and `role_permission_gaps`
list queue holders; the queue Warning counts superusers; models not in the Django admin; route inventory updated;
CSRF and frame denial; logs hold no typed values.

**PR 2:**

- Gate: each row of the §4.1 table, including a malformed value with the switch off (Warning only, site starts),
  `LOCAL` with `DEBUG` and `TESTING` false and the switch on (start-up refused), `LOCAL` under `TESTING` (served),
  and "on but not accepted" (404, Warning, start-up log line, superuser card line).
- Page renders with no query on school tables; signed-in GET and POST redirected with nothing stored.
- Field rules: required, lengths, NFKC, whitespace collapsed, Malayalam with ZWJ accepted; U+202E, U+2066,
  U+200B, zalgo, fullwidth digits, split digits, digits in a name, a fourth digit in the class, `<`, `@`, `:`
  refused; a form error stores nothing and opens no transaction.
- R1: known, unknown, throttled and repeated input give the same status, template, body (CSRF token aside),
  headers and reads; known and unknown the same writes.
- Caps and repeats with frozen time: per-source cap at the sixth stored request in the clock hour; global cap at the
  201st of the day; a repeat of an open request within 7 days dropped, stored after 7 days, stored again once the
  first is handled.
- **PostgreSQL only:** 20 parallel submissions from one source store exactly 5; from 20 sources with 3 global slots
  left store exactly 3; two connections, A holding the gate at `stored = 199`, B waiting, A commits, B drops; a
  submit and a cron purge run concurrently without error; with the gate held by another connection, a submit gets
  the 503 page within the timeout and writes nothing; after a submit, `SHOW lock_timeout` and
  `SHOW statement_timeout` give the defaults.
- Failure path: a forced `DatabaseError` writes no request, hour row, counter or event, returns the fixed 503 page
  with `Retry-After`, identical for every input, and logs the exception class only.
- Keys: IPv6 addresses in one /64 share a bucket; an IPv4-mapped address equals its IPv4; `"unknown"` writes no hour
  row and runs the same queries; `source_key` differs from `security.source_key` for the same address and differs between two
  hours for the same source; `repeat_key` is 64 hex characters, equals an independently computed HMAC-SHA-256
  over the same derived key, and differs from a plain SHA-256 of the same text and from any value made with
  `SOURCE_HASH_KEY`; the hour row holds
  no typed value and its `hour_start` is on the hour.
- No change to `User`, `GuardianAccount`, `GuardianStudentAccess`, `LoginFailure` or `SecurityEvent` on submit;
  `never_cache` on the page; no session row created; CSRF and frame denial; no typed value in logs or any `Location`
  header.

**Every PR:** `ruff check .`; `makemigrations --check --dry-run` clean after the PR's own migration; route inventory
test; targeted tests for accounts, the sign-in page, reset staff and the new module; full CI on the final head.

## 11. Acceptance checklist

- [x] Security-focused review of r1 (ADR 0029 item 3); confirmed findings applied in r2 (§14).
- [x] Focused re-check of r2; RC-01 to RC-13 applied in r3 (§14).
- [x] Final focused re-check of r3: approved for owner decision; FC-01 to FC-06 applied.
- [x] Owner decisions OD-H1 to OD-H5 recorded (§12), 2026-11-26.
- [x] Owner approves the spec for implementation with collection disabled (2026-11-26).
- [ ] Spec PR #314 merged (owner's separate approval).
- [ ] PR 1 merged after a backward-migration rehearsal; purge step added to the staging cron.
- [ ] PR 2 merged with the switch off.
- [ ] Local test recorded (local machine, demo data, `LOCAL` reference, made-up names), then `--all --yes`.
- [ ] **OD-H1: owner's acceptance of the retention and legal risk recorded** (this spec and a dated
      `docs/OPERATIONS.md` entry); only then is `SIGN_IN_HELP_RETENTION_ACCEPTED=OD-H1 <date>` set on any deployed
      instance. It is never set on a local machine.

## 12. Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-H1 | Collecting real requests before counsel confirms retention (ADR 0029 item 5). **Not approved; open as a legal risk.** | (a) Build and merge with the page off. Real requests are collected only after the owner records acceptance in this spec and in a dated `docs/OPERATIONS.md` entry, and `SIGN_IN_HELP_RETENTION_ACCEPTED` is set to `OD-H1 YYYY-MM-DD`. A `LOCAL YYYY-MM-DD` reference works only when `DEBUG` or `TESTING` is true and otherwise stops start-up while the feature is enabled. The `OD-H1` form is never set on a local machine. Testing before acceptance is local only, with no deployed test mode (§4.1). (b) Wait for counsel before building. | (a). Building is harmless with the page off; the legal decision stays open and separate. |
| OD-H2 | Who sees the queue | (a) ADR 0029's dedicated permissions `accounts.view_signinhelprequest` and `accounts.change_signinhelprequest` (OD-G14), added by migration to "Portal password resets"; the views never check `reset_guardian_password` (§5.1); (b) a separate group and page | (a). One list of named staff, without reusing the reset permission. |
| OD-H3 | Prompt for waiting requests | (a) Sidebar badge and Overview card for holders, which also warn about requests dropped by limits or repeats and about old rows the purge missed; superusers also see "on but not accepted"; (b) none | (a). Without a prompt requests sit unseen until purged. |
| OD-H4 | Caps | Accept as starting values, tuned after acceptance: 5 stored requests per source per clock hour (IPv6 grouped by /64), 200 per day, and a repeat of an **open** request within 7 days dropped; or set others | Accept. |
| OD-H5 | Deviations from ADR 0029 (header list) | Accept all five: (1) R10 as ROUTINE with no event on submit, drop or failure; (2) no network identifier on request rows; (3) R14 as "the only new anonymous route"; (4) a keyed `repeat_key` and a repeat rule that reads only typed text and other open requests, never school data, invisible to the visitor; (5) per-hour limit rows kept until their hour ends and the next submit or cron run (about 6 hours with the staging schedule), with no typed value and no shared column or key with requests; at low traffic a request can be matched to its hour row by timing alone; source keys are not linkable across hours | Accept. Items (1), (2), (3) and (5) are narrower than the ADR or follow the approved reset-spec precedent; item (4) adds a stored keyed derivative and a write that depends on typed text, never on school data, which the visitor cannot observe. |

### Recorded decisions (2026-11-26)

The product owner decided, in writing:

| ID | Decision |
| --- | --- |
| OD-H1 | **Option (a) approved.** Build and merge with the public page off. This does **not** approve collecting real requests. Real collection requires a later dated acceptance in this spec and in `docs/OPERATIONS.md`, plus the exact `OD-H1 YYYY-MM-DD` setting. |
| OD-H2 | Approved as written. Dedicated queue permissions, granted to the "Portal password resets" group through the migration. |
| OD-H3 | Approved as written. Permission-controlled sidebar count, Overview card, drop warnings and cleanup warnings. |
| OD-H4 | Approved as starting limits: 5 per network per clock hour, 200 per day, and 7-day repeat suppression against open requests only. Tune only after real collection is approved. |
| OD-H5 | Approved as written. The owner explicitly accepts the residual risk that low traffic may allow approximate matching by timing, although there is no shared key or column. |

**Spec status:** Approved for implementation with collection disabled. Collection of real requests is not
approved.

**Boundaries recorded by the owner:**

- `SIGN_IN_HELP_ENABLED` remains off by default.
- No deployed test mode.
- Invalid or missing acceptance fails closed.
- Implementation and migration may merge without collecting data.
- Enabling real collection requires a separate explicit owner decision.
- Counsel confirmation remains preferable before that activation decision.
- Merging this spec PR and starting each build PR need the owner's separate approval.

## 13. Out of scope and accepted residual risks

- Any reply to the requester, any channel and owner notification (OD-G2; T10 High, accepted).
- A flood from many networks can still fill the daily cap, or make valid submissions wait and get the 503 page;
  the drop count shows on the Overview card (T18, M for office time, accepted in ADR 0029). No separate cap on open
  rows: the daily cap and 30-day purge bound the backlog at about 6,000 rows (SR-15).
- No CAPTCHA (third-party service, accessibility cost) and no hidden extra field (R21 allows exactly three fields).
  Revisit only if automated spam appears after acceptance.
- Spam can make staff call a real family who asked for nothing; Appendix A's script resets nothing on the call
  (T18). Repeats count only open requests, so a handled spam request never blocks the family.
- At low traffic, a database reader can match a request to its hour row by timing alone when both are alone in the
  same hour, for as long as the hour row exists (up to about 6 hours on staging). With the keys also leaked, the small
  IPv4 space would then reveal the address. Rows of one source in different hours cannot be linked (OD-H5 (5), FC-02).
- A deployed instance that runs with `DEBUG` on would honour a `LOCAL` reference; running a deployment with `DEBUG`
  on is already an unsafe misconfiguration (§4.1).
- Database failures are not counted as drops (§5.3).
- No deployed test before acceptance: the real-proxy check happens only after live switch-on (§7).
- Outcomes are final (SR-16).
- The page is in English only.
- Matching is manual; a misspelt name may get `NO_MATCH`. The answer page tells families they can visit.

## 14. Review record

### r1 → r2: security-focused review (2026-11-26, ADR 0029 item 3)

Verdict: "Approve r2 after these changes".

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| SR-01 | High | Count-then-insert caps not atomic across workers | Gate-row lock (§4.3, §4.4); PostgreSQL concurrency tests |
| SR-02 | High | IPv6 per-address lets one /64 bypass the per-source cap | /64 bucket, IPv4-mapped folded (§4.3) |
| SR-03 | Medium | `"unknown"` and empty trusted proxies collapse sources | Constant bucket with no row; start-up refusal (§4.1, §4.3) |
| SR-04 | Medium | Same key, 30-day pseudonymous address log | Sub-key; no source on request rows; short-lived hour rows (§3.3) |
| SR-05 | Medium | Drop-count create race breaks the outer transaction | Savepoint; counts on the gate row (§3.2, §4.4) |
| SR-06 | High | Purge failure visible only on the queue page | Overview warning, purge on submit, backup note (§5.2, §6) |
| SR-07 | High | OD-H1 enforced only by the runbook | Acceptance setting checked in code, fail-closed table; staging test mode removed (owner condition) (§4.1, §7, §11) |
| SR-08 | Medium | Permission migration and reset-staff interplay | §5.1 |
| SR-09 | Medium | Bidi, format characters, split and non-ASCII digits, zalgo | Category allow-list after NFKC, `<bdi>` (§4.2, §5.2) |
| SR-10 | Medium | R10 and R14 departures not flagged | Header deviations, OD-H5 |
| SR-11 | Medium | R1 test should include headers; switch-off oracle | §4.4 |
| SR-12 | Low | Badge filter and index | §3.1, §5.2 |
| SR-13 | Low | "Never logged" overstated; DB error text | Reworded, forced-error test (§9) |
| SR-14 | Medium | Reverse migration deletes requests silently | Stated, counts printed, `--all` (§6, §7) |
| SR-15 | Medium | Repeat-name harassment; flood hidden | Repeat rule, drop count on the card; open-row cap not applied (§13) |
| SR-16 | Low | Final outcome cannot be corrected | Accepted as final (§5.2) |
| SR-17 | Low | Escaping rules beyond element text | §5.2 |
| SR-18 | Info | Anonymous CSRF and session behaviour | Stated (§4.4) |
| SR-19 | Medium | Page notice promises not literally true | Reworded (§4.2); legal question in OD-H1 |

### r2 → r3: focused re-check (2026-11-26)

Verdict: "Needs changes" (text only).

| ID | Sev | Finding | Resolution in r3 |
| --- | --- | --- | --- |
| RC-01 | High | Gate lock without a wait limit; rendering inside the lock; failure path unspecified | `SET LOCAL` timeouts, render after commit, fixed 503 page, nothing written (§4.4) |
| RC-02 | Medium | Stale counters before the lock; several clock reads near midnight | One `now`; counters only from the locking query (§4.4); two-connection test |
| RC-03 | Medium | Submit housekeeping and cron purge could deadlock | Shared lock order, `skip_locked`, batched cron (§4.4, §6) |
| RC-04 | Medium | SQLite does not queue concurrent writers | Exact on PostgreSQL only; SQLite not guaranteed; concurrency tests PostgreSQL only (§4.3) |
| RC-05 | Medium | "2 hours" untrue; exact hit times joinable to requests | Clock-hour rows with no exact time; honest retention (§3.3, OD-H5 (5)) |
| RC-06 | Medium | Repeat rule could silence a family after spam was handled | Repeats count open requests only (§4.3) |
| RC-07 | Low | Repeat key join and exposure | Keyed HMAC (owner point), U+001F join, used only in its own query (§4.3) |
| RC-08 | High | Local acceptance identical to the real one | `OD-H1` and `LOCAL` forms; `LOCAL` refused unless `DEBUG` or `TESTING` (§4.1) |
| RC-09 | Medium | Typo outage with the switch off; future-date trap; overlapping rows; unseen Warning | Ordered table, Warning when off, no future-date rule, visible "on but not accepted" (§4.1) |
| RC-10 | Medium | OD-H5 incomplete | Five deviations in the header and OD-H5 |
| RC-11 | Low | `--all` scope and confirmation; handle on expired rows; local data | `--all --yes`, never `SecurityEvent`, 404 on expired, local-data rule (§5.2, §6, §7) |
| RC-12 | Low | "Skipped, same query shape" contradictory | Constant bucket, same query (§4.3) |
| RC-13 | Low | Queue Warning should count superusers | §5.1 |

Owner points applied in r3: transaction-local timeouts that cannot leak (§4.4); a failure writes nothing and returns
the fixed 503 page (§4.4); `LOCAL` only with `DEBUG` or `TESTING`, otherwise start-up fails while enabled (§4.1); a
keyed, domain-separated repeat key distinct from the network and sign-in keys (§4.3); limit rows with no typed values
and no shared column or key with requests, matchable only by timing at low traffic, accepted in OD-H5 (5) (§3.3); one
lock order for cron and submit (§4.4, §6).

### r3 final focused re-check (2026-11-26)

Verdict: "Approve r3 for owner decision" after FC-01 and FC-02, with no further review round. RC-01 to RC-13
incorporated (RC-03 and RC-05 completed by FC-03 and FC-02). OD-H1 to OD-H4 match r3; OD-H5 needed the FC-02 and
FC-06 wording.

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| FC-01 | Medium | `salted_hmac` defaults to SHA-1 in Django 5.2 | `algorithm="sha256"` required; 64-hex test (§4.3, §10) |
| FC-02 | Medium | Hour rows matchable to requests by timing at low traffic; source rows linkable across hours | Honest wording everywhere; hour in the keyed input (§3.3, §4.3, §13, OD-H5 (5)) |
| FC-03 | Low | Cron and a missing gate row; `--all` leftovers; silent batch failure | Gate locked if it exists; `--all` loops and exits non-zero; switch off first (§6) |
| FC-04 | Low | `SET LOCAL` test needs `TransactionTestCase`; commit-time errors | Stated (§4.4) |
| FC-05 | Low | One gate predicate; Warning visibility; row 6 under `TESTING` | `gate_state()`; `Tags.database`; start-up log line guaranteed; `TESTING` exempt (§4.1) |
| FC-06 | Info | One root secret by default; OD-H5 "narrower" claim; cron schedule wording | Reworded (§4.3, OD-H5, header) |
