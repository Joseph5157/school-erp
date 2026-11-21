# ADR 0027: Privacy-safe usage measurement

Status: accepted, 2026-11-21 (Option B2; spec `docs/competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md`, sections 5, 7 and 9; decisions OD-B6 to OD-B14).

## Context
Later product decisions need evidence about phone use: offline sync, push notifications, login convenience, native apps and admin phone coverage (audit gaps G-04, G-06, MOB-04, MOB-06 to MOB-10). Today the product records nothing about how its screens are used. Measurement in a small school carries real risk: about ten teachers and a few hundred guardians mean that a precise event, or even a daily count, can point to one person. The existing rules already limit what may be stored: crash reports carry only the route pattern (Security Gate 4A), security events never store page contents or contact data (ADR 0013), and browser storage holds UI preferences only.

## Decision
**Purpose.** Measurement exists only to answer the questions in spec section 9 and the audit's §13. A new purpose needs an amendment to this ADR.

**No person, no record, no value.** No measurement row, request body, log line or report contains a user, guardian, teacher or student identifier, name or username; a database ID or public UUID of any record; a URL path, query string or search term; a typed value, mark, attendance status, absence count, note or free text; error message text; an IP address (raw or hashed); a user-agent string, screen size or device model; a session ID, cookie or CSRF token; or a time of day.

**Aggregate at write time.** One table, `core.UsageCounter`, holds daily counts. Each accepted event becomes `count + 1` on the row for its dimensions. No per-event row exists at any point, and measurement events are not logged. The write is an update, then an insert only if no row exists, each in its own savepoint; a creation race retries the update once. Any database error rolls back only the measurement savepoint and the event is dropped, so measurement can never break the caller's own work.

**Dimensions, all fixed enums** (`core/usage.py`, mirrored by database check constraints):

| Dimension | Values |
| --- | --- |
| `day` | Business date (school time) |
| `area` | `admin`, `teacher`, `guardian`; `multi` only for sign-in completion, first password change and re-sign-in after expiry by a login with several areas; `public` only for sign-in events and the sign-in page |
| `workflow` | `attendance_capture`, `marks_entry`, `teacher_home`, `find_student`, `missing_attendance_act`, `page`, `guardian_first_view`, `guardian_report_pdf`, `notice_view`, `install`, `sign_in`, `session` |
| `step` | The closed list in spec 5.2, including the failure codes `network`, `server`, `signed_out`, `forbidden`, `conflict`, `closed`, `invalid`, `csrf` |
| `page_route` | A curated allow-list of route names, or `other`; only and always for `page` |
| `duration_bucket` | `<5s`, `5-15s`, `15-60s`, `1-3m`, `3-10m`, `10-30m`, `>30m`; only on `completed` |
| `size_bucket` | `1-20`, `21-40`, `41+`; only for attendance capture and marks entry |
| `age_bucket` | `same_day`, `1-2d`, `3-7d`, `later`; only and always for `notice_view` |
| `device`, `display`, `platform` | `phone`/`tablet`/`desktop`, `browser`/`installed`, `android`/`ios`/`other`, or blank |

Stored bucket labels use ASCII hyphens (`5-15s`), where the spec text shows en dashes. Adding a value to any enum, including a new page route, is a reviewed change with its own migration. Code also enforces which steps and areas each workflow may use, and which events a browser may report.

**Off unless the school approves in writing.** `USAGE_MEASUREMENT_ENABLED` defaults to off. A deployment switches it on only after a written approval from the school's head or authorised officer (letter or email) that names this ADR and the notice paragraph below. Its date and reference go in the deployment's operations record before the variable is set. A verbal notice is not enough. While it is off, nothing is recorded and no expiry marker is kept.

**Global Privacy Control.** A request carrying `Sec-GPC: 1` is never recorded. The page-side check of `navigator.globalPrivacyControl` arrives with the client code in B3.

**Short retention.** `purge_usage_counters` deletes rows with `day <= today - 180 days`, keeping exactly the 180 days that end today. It runs daily on the existing cron service as its own step, whether or not measurement is on. `usage_report` warns when any row is past the cutoff.

**Access.** Operators only, through the `usage_report` management command run on the server. No web route serves counters, no permission is added, and `UsageCounter` is never registered in Django admin. Reports group by ISO week and print any cell under 5 as `<5`, after every filter and grouping.

**Beacon.** Signed-in pages may post allow-listed events to `/u/` (`usage-beacon`). The view returns 401 itself to a signed-out request (never a redirect), checks CSRF, accepts at most 2 KB and 20 events, refuses the whole batch if any field is outside the enums, the client-reportable events or the caller's own areas, and records at most 200 events per session per hour. A beacon never counts as activity for the 30-minute idle limit. Its reply has no body.

**No new client storage.** No cookie, localStorage, sessionStorage or IndexedDB entry is added. The only session values are bare integers: the expiry marker for the re-sign-in signal, the beacon rate window and, in B3, workflow start times. They hold no record ID and disappear at sign-out. The expiry marker sits in the anonymous session until the next successful sign-in removes it, or until that anonymous session itself expires; it is never copied into a counter row.

**Honest claims.** The data is described as aggregate, identifier-free and designed to minimise re-identification, never as anonymous. In a small school a weekly count can still hint at a person when combined with other knowledge, which is why the small-number rule, the written approval and operator-only access exist.

### Notice paragraph for the school
> To improve the app on phones, Everclass counts how often its screens and steps are used, for example how many marks saves succeed each week. The counts are daily totals with no names, accounts, students, marks or other school records, and no time of day. They are kept for 180 days, are seen only by the people who run the system, and are never shared with anyone else. Your browser's Global Privacy Control setting turns this off for you.

## Consequences
- One model and one migration (`core/migrations/0095_usagecounter.py`). No new permission, dependency or CI job. The only deployment change is one added step in the cron start command.
- B2 records only sign-in and session signals on the server: sign-in completed, failed (always `public`) and throttled; first forced password change; session expiry by idle or absolute limit, with `expired_unsaved` for a lost non-GET submission; and re-sign-in within 10 minutes of a real expiry, proven by a session marker and never by the editable `?expired=` value.
- Known limit: with `SESSION_SAVE_EVERY_REQUEST`, a beacon in flight while a page loads can save its older copy of the session over the page's, moving the idle clock back by that overlap (milliseconds). The same already holds for the session-status check. B3's client sends beacons only on hide or every 30 seconds, never alongside a navigation it starts.
- The ten workflows of spec section 6, the sign-in page view, the server-recorded autosave outcomes and the client queue that sends beacons are instrumented in B3. The full report sections, ratios, secondary suppression and CSV output also come in B3.
- B3 (implemented): signed-in pages carry `data-erp-usage`, `data-erp-route` (an allow-listed route name or `other`, never a path) and `data-erp-area` only when measurement is on and the request had no `Sec-GPC: 1`; `erp.js` also checks `navigator.globalPrivacyControl` before queuing and before every flush. Events wait in page memory only (at most 20) and are sent on hide, every 30 seconds or after a successful save. Session timers `_u_attendance`, `_u_find_student` and `_u_guardian` hold epoch seconds only and are removed on completion. The beacon accepts one more event key, `z` (a size bucket), only on `marks_entry` started and completed, because marks entry keeps its timer in page memory; the server renders the bucket, never the roster size. `signed_out` is counted by the middleware on both 401 paths of the three autosave routes. No schema change: B3 uses migration 0095 as it is.
- The report's complementary suppression compares the rows behind every printed cell: wherever printed cells add up to a printed or implied total, a second cell is hidden (`*`) until no `<5` cell can be recovered. Ratios print `n/a` below their minimum denominator and only an upper bound when the numerator is hidden. Section 9 triggers are printed only for an unfiltered report of at least 4 weeks.
