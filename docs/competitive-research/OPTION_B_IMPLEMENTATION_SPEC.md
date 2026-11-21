# Option B Implementation Specification: Phone Save Quality and Privacy-Safe Measurement

- **Status:** Approved implementation specification. All product-owner decisions OD-B1 to OD-B16 are approved (revision 3, after two product-owner reviews). The F-1 fix is part of B1.
- **Baseline:** `main` at `a78734c` (Option A3 merged, PR #280). Option A (A1–A3) and ADR 0026 are in this baseline.
- **Source:** `CURRENT_STATE_BENCHMARK_AUDIT.md` (approved planning baseline), Option B, gaps G-05 and G-04, and the research questions in §13 that feed MOB-04, MOB-06 to MOB-10 and G-06.
- **Companion documents:** `CURRENT_STATE_EVIDENCE_INDEX.md`, `OPTION_A_IMPLEMENTATION_SPEC.md`, `docs/PWA_GATE_1_PLAN.md`, `docs/PWA_STARTER_PLAN.md` (Gate 2).

Placeholders such as `{student}` and `{max}` stand for values filled in at runtime. Line numbers refer to `a78734c`.

## 1. Scope

| # | Item | Audit gap | Outcome |
| --- | --- | --- | --- |
| B1 | Marks-entry autosave | G-05 (ACA-03, TEA-07) | Each marks row saves itself when the teacher leaves the score box or picks a status. Each row and the whole page show Saving, Saved or Not saved, with Retry. Nothing about who may enter marks, finalization, corrections or publication changes. |
| B2 | Measurement policy and store | G-04 (ADM-08, MOB-01); inputs to MOB-04, MOB-06 to MOB-10, G-06 | A short ADR (0027) says what may and may not be measured. One aggregate-only, identifier-free table holds daily counts and bucketed durations. It holds no person, record or value. It is off by default, and a daily cron job purges it. |
| B3 | Workflow instrumentation and evidence report | Same as B2 | Named admin, teacher and guardian phone workflows report start, completion, save-attempt and failure counts, plus bucketed durations. A management command prints the aggregates, with small numbers hidden after every filter and grouping. |

Section 9 sets out how the evidence feeds later decisions on offline sync, push, login convenience and native apps. Those decisions are **not** made here.

### Out of scope

- No service worker, offline page, offline saving, write queue, background sync or client-side storage of school data. `test_pwa_gate1::test_no_service_worker_is_registered` must keep passing.
- No push notifications and no request for notification permission.
- No native app, wrapper or app-store work.
- No passkeys, "remember me", longer sessions or other login changes. B3 only measures sign-in friction.
- No fee work (issue #274 stays deferred).
- No change to who may enter, finalize, correct or publish results (ADR 0009, 0010, 0018; Phase 6 publication).
- No new result statuses (ADR 0009 MARKED/ABSENT stays; the ACA-04 conflict is not reopened).
- No change to attendance autosave behaviour, except the shared signed-out reply in 4.7 (OD-B3).
- No per-person read tracking of notices (ANA-06 stays a research question). B3 only counts notice views in aggregate (OD-B13).
- No third-party analytics script, SDK, pixel or external endpoint.

## 2. Rules this spec must keep

| Rule | Source | Effect on Option B |
| --- | --- | --- |
| Only the teacher whose assignment for this offering and Section is effective **today** may enter DRAFT results. | ADR 0010 D6; `authorization.can_enter_results`, `core/authorization.py:100` | Every autosave request checks this again. A teacher reassigned while the page is open gets "can no longer enter marks", not a save. |
| A subject teacher sees a finalized assessment only if assigned on its date. | ADR 0018 D7; `can_view_finalized_as_subject_teacher`, `core/authorization.py:89` | The autosave endpoint never serves finalized data. It refuses before reading any result. |
| Results are entered only from the assessment date, only while DRAFT, and only for date-effective roster enrollments. | `Assessment.save_draft_result`, `core/models.py:3182`; `StudentResult.clean`, `core/models.py:3301` | Autosave calls `save_draft_result` unchanged, which locks the assessment row and re-reads its status (`_lock`). |
| Results are MARKED (0 ≤ score ≤ max) or ABSENT (no score). A missing row means not entered, never ABSENT. | ADR 0009; `ResultStatus`, DB check `studentresult_status_matches_score` | A blank row sends nothing. Autosave never creates an ABSENT row on its own. |
| A saved result cannot be cleared from the entry page. | `ResultEntryForm`, `core/forms.py:879-883` (no "Not entered" choice once saved) | Clearing the score of a saved MARKED row is a validation error shown on the row. It is not a delete (OD-B5). |
| Editing a DRAFT result is a normal edit. Changing a FINALIZED one is an audited administrator correction. | ADR 0009 Gate 7; `StudentResult.correct`, `core/models.py:3347`; `ResultCorrection` | Autosave can only reach DRAFT results. It never writes `ResultCorrection` and never marks a publication STALE. |
| Finalization needs `core.finalize_assessment`, locks the assessment and freezes grading. | `Assessment.finalize`, `core/models.py:3132` | Finalizing, the whole-form Save draft and autosave all lock the assessment row **first**, then touch result rows (4.3). They run one after the other and cannot deadlock. A save that arrives after finalizing is refused with 409. |
| Guardians see only published, non-stale publications. | ADR 0014; `core/publication.py` | Drafts are never visible to guardians, so autosave changes nothing guardians can see. |
| Sessions: 30 minutes idle, 8 hours absolute, enforced on every request. An expired session is signed out and redirected with `expired=` and `unsaved=1` for non-GET requests. | ADR 0013 OD-5; `accounts/middleware.py:49-101` | Autosave counts as activity, as attendance autosave already does. A background request from an expired session gets 401 instead of the sign-in page (4.7). |
| Crash reports carry the route pattern, never the concrete URL, values, usernames or messages. | Security Gate 4A; `config/error_reporting.py:1-12` | Measurement follows the same allow-list approach. |
| Security events never store passwords, page contents or contact data. Routine events are kept 365 days. | `accounts/models.py:60-131` | Measurement data is kept apart from `SecurityEvent` and kept for less time (OD-B7). |
| localStorage holds UI preferences only, with no school data. | Audit §7; `static/js/erp.js:138-186,974-987` | B1 and B3 add nothing to localStorage, sessionStorage, IndexedDB or cookies. |
| Gate 1 PWA is online-only. On network loss a save stays failed and unsaved, with no background retry or queued write. | `docs/PWA_GATE_1_PLAN.md:8`; PWA Gate 2 journey "Network loss during a save" | Retry is always a tap by the teacher. Autosave never retries on its own. |
| Every route is in the route inventory with its guard. | `core/tests/route_permissions.json`; `test_security_gate4b_route_inventory` | B1 adds one route and B2 adds one route. Both are added to the inventory. |

## 3. Product-owner decisions

Each row needs an explicit answer before its PR starts. The recommendation comes first, and the rest of the spec assumes it.

**Review status:** all decisions OD-B1 to OD-B16 are approved. OD-B1, OD-B9, OD-B10, OD-B14 and OD-B15 were approved after corrections, which revisions 2 and 3 apply:

- OD-B1: lock order, base submission, and a fallback that never bypasses the base check.
- OD-B9: documented school approval.
- OD-B10: both the header and the browser signal.
- OD-B14: final dimensions, allow-lists, and `multi` limited to sign-in events.
- OD-B15: calculable triggers with minimum samples, precise event labels, observed network failures, a trusted re-sign-in marker and the native-app meta-trigger.

| ID | Decision | Recommendation | Alternatives |
| --- | --- | --- | --- |
| OD-B1 | What happens when the same row is saved from two places, such as two tabs, two devices or a stale page? | **Detect the conflict.** Each row carries hidden base inputs holding the last confirmed value (4.4). The server locks the assessment, then the result row, and compares (4.3). If they differ, it refuses with 409 and shows the newer value (4.5). | Last write wins, as attendance does today. It is simpler, but a stale tab can silently overwrite a newer mark. |
| OD-B2 | When does a row save? | **On `change`**: leaving the score box, pressing Next or Enter, or choosing a status. It never saves on each keystroke. | Save after a pause in typing (debounce). This risks saving "8" while the teacher is still typing "85". |
| OD-B3 | Reply to a background request (HTMX or `fetch`) from a signed-out session | **401 with a small body**, for requests marked `HX-Request: true` or `X-Requested-With: XMLHttpRequest`. Normal page requests keep today's redirect. This also changes attendance autosave (4.7). | Keep the redirect. The browser then follows it to the sign-in page, and a 200 sign-in page can be read as a successful save (4.7, finding F-1). |
| OD-B4 | The Save draft button once autosave works | **Hide it while saves succeed, and show it as a fallback when any row fails.** With JavaScript and HTMX, it re-sends only the failed rows through the autosave endpoint, each with its own base values, so conflict protection still applies. It never submits the whole form in that mode. Without JavaScript or HTMX, it stays the only action and submits the whole form as today. | Always visible. This is safer to discover but suggests two save paths. |
| OD-B5 | The teacher clears the score of a row that is already saved | **The row shows the local state "Enter a score", sends nothing and stays Not saved** (4.2 step 4). The server still answers a hand-crafted request with 422. No result is deleted. This matches the current rule. | Allow un-entering a draft result. That would be a new delete path and needs its own decision. |
| OD-B6 | How measurement is stored | **Daily aggregate counters only.** No raw event rows and no per-request log of measurement events. | Identifier-free raw events kept for a short time. These allow richer analysis but carry timestamps that, in a small school, can point to one person. |
| OD-B7 | Retention | **180 days**, then deleted by a daily cron job that runs whether or not measurement is switched on (5.4). That covers a term plus the review window. | 90 days, or 365 days to match routine security events. |
| OD-B8 | Who can read the measurements | **Operators only, through a management command** (`usage_report`) run on the server. No in-app page in v1. | An in-app page behind a new permission `core.view_usagecounter` given to no group by default. |
| OD-B9 | Default state and approval | **Off by default** (`USAGE_MEASUREMENT_ENABLED=False`). It is switched on per deployment only after **documented school approval**: a written approval from the school's head or authorised officer (letter or email), naming ADR 0027 and the privacy-notice paragraph. Its date and reference go in the deployment's operations record before the variable is set. A verbal notice is not enough. | On by default. Or switch on after notice alone. |
| OD-B10 | Global Privacy Control | **Honour it on both sides.** The server records nothing for a request carrying `Sec-GPC: 1`, and leaves out `data-erp-usage` when the page request carried it. The client sends nothing when `navigator.globalPrivacyControl === true`, checked before every flush. | Ignore it. The data is aggregate and identifier-free, but honouring the signal costs nothing. |
| OD-B11 | Device dimensions | **Width class (phone, tablet, desktop), display mode (browser or installed) and coarse platform (Android, iOS, other).** No user-agent string, model, browser version or screen size. | Width class and display mode only. Without platform, native-app evidence (9.4) is weaker. |
| OD-B12 | Small numbers in reports | **Hide any cell under 5 and report by ISO week**, even though rows are stored daily. | Show exact daily counts. A small school has about 10 teachers, so one teacher's day could be identified. |
| OD-B13 | Guardian notice timing | **Count notice views in aggregate by notice-age bucket** (same day, 1–2 days, 3–7 days, later). No per-guardian or per-notice record. | Do not measure. Push evidence (9.2) would then rest on interviews only. |
| OD-B14 | Schema | **Accept one new model and migration** (`UsageCounter`) in B2, with the dimensions in 5.4: separate `duration_bucket`, `size_bucket` and `age_bucket` columns, a curated `page_route` allow-list, and database check constraints on every enum and on which workflows may use which column. Adding a measurable route later needs an allow-list change and a migration. B1 needs no schema change. | Write measurements to the console log instead. Railway would keep them outside the retention rule, with timestamps. |
| OD-B15 | Evidence triggers in section 9 (revised) | **Approve the rewritten section 9 as review triggers, not automatic decisions.** Every trigger in 9.1 to 9.3 is built from ratios of two stored counters, each with a stated minimum denominator, combined by an explicit Boolean rule. The native-app rule in 9.4 is a meta-trigger over those triggers, applied per platform, and it also requires documented PWA capability testing. Each trigger opens a design gate; none approves a build. Questions the counters cannot answer, such as reach, unique people and the reasons for failures, are decided by interviews. | Set different numbers, or decide each case only after reading the data. |
| OD-B16 | Order | **B1 first (no schema, highest user value), then ADR 0027 with B2, then B3.** B1 does not wait for the measurement policy. | Measure first, to get a "before" figure for marks entry. That delays the fix by at least one PR. |

## 4. B1: Marks-entry autosave

### 4.1 Current behaviour

- `assessment_marks_entry` (`core/views.py:2193-2222`) shows `ResultEntryForm` for the whole roster. A POST saves every answered row in one transaction through `save_draft_result`, then redirects with "Marks saved as draft."
- If any row is invalid, nothing is saved and every typed value is kept (`test_ui_teacher_marks::test_invalid_post_keeps_typed_values`).
- `erp.js` (`static/js/erp.js:562-636`) gives live counts, filter tabs, "typing a score selects Marked", "Absent clears the score", and moves to the next student on Next or Enter. Nothing is saved until **Save draft**.
- There is no unsaved-changes warning on this page. Leaving it, losing the network or letting the session expire loses everything typed since the last Save draft. The audit infers this (ACA-03).
- Attendance already has the model to follow: per-row HTMX autosave, per-row and page-level save states, Retry, a fallback Save draft, and in-flight bookkeeping that stops races (`static/js/erp.js:225-560`; `core/views.py:1646-1692`).

### 4.2 UX flow

**Normal flow (phone first):**

1. The teacher opens marks entry. The page-level line under the counts reads "Changes save automatically". The Save draft button is hidden (OD-B4).
2. The teacher types `42` and presses **Next**. Focus moves to the next student (existing behaviour). The row that lost focus shows `Saving…`, and the page line shows `Saving…`.
3. The server confirms. The row shows `✓ Saved` and the counts update from the server reply. When no row is in flight or failed, the page line shows `All changes saved`.
4. Choosing **Absent** clears the score (existing behaviour) and saves at once. Choosing **Marked** with an empty score, or clearing the score of a Marked row, **sends nothing**. The client cancels that row's request (`htmx:confirm`) and shows the local state `Enter a score`. The row counts as not saved for the page line and the leave-page warning until the teacher enters a score or chooses Absent. The server's 422 (pre-check 6) remains only as defence in depth for a request that arrives anyway.
5. When every student has a mark or Absent, the existing "All students have a mark or Absent." announcement is made, and the hint reads `0 not entered`.

**Failure flow:**

```
Arjun K      [ 42 ]  (Marked) Absent      Not saved: no connection. [Retry]
Meera S      [ 51 ]  (Marked) Absent      Not saved: the maximum is 50.
Ravi P       [ 38 ]  (Marked) Absent      Changed on another device to 40. [Use 38] [Keep 40]
─────────────────────────────────────────────────────────────────────────
Changes not saved (2)                                   [Save draft]
```

- **Row states:** idle (no badge), `Saving…`, `✓ Saved`, and `Not saved: {reason}` with an optional action.
- **Page states:** `All changes saved`, `Saving…`, and `Changes not saved ({n})`, the last with the fallback Save draft. The page line uses the existing `[data-erp-autosave-state]` style, so it is not new CSS where avoidable.
- **Retry** is offered only when trying again could succeed: network failure, timeout or 5xx. It is not offered for validation errors (fix the value), finalized (nothing to retry) or no longer assigned (reload).
- **Conflict (OD-B1)** offers two buttons. **Use `{mine}`** first replaces the row's hidden base inputs with the server value carried in the conflict reply, then re-sends the teacher's value, which is now compared against that server value. **Keep `{theirs}`** puts the server value in both the visible fields and the base inputs, and marks the row saved without a request. Neither choice is ever made automatically. If the value changes again on the other device in the meantime, "Use mine" gets a fresh 409.
- **Leaving the page:** while any row is in flight or failed, `beforeunload` warns. When everything is saved, there is no warning.
- **Fallback Save draft:**
  - **With JavaScript and HTMX.** The button intercepts the form's `submit` and calls `preventDefault()`, so the whole form is never posted. It first waits for in-flight row saves, as attendance does (`static/js/erp.js:510-516`). Then it re-sends each row whose state is `Not saved` through the autosave endpoint, with that row's own hidden base inputs, by triggering the row's `change`.
    - Every re-sent row passes the same lock, recheck and base comparison (T1 to T8). A stale row therefore gets the 409 conflict prompt, never an overwrite.
    - Rows already showing a conflict are not re-sent, because they need the teacher's Use or Keep choice. Rows refused as invalid, finalized, no longer assigned or off the roster are also skipped, because a re-send would fail the same way. The page line then reads "{n} rows need your attention".
    - The button records `fallback_save_used` once per tap.
  - **Without JavaScript or HTMX.** The button is a normal submit, and the whole form posts to `assessment_marks_entry` exactly as at `a78734c`. This is the only path that uses the whole-form POST.
- **No JavaScript or no HTMX:** the page behaves exactly as today.

**Accessibility:**

- Every row status and Retry button carries hidden text naming the student, as in attendance ("Retry saving Arjun K", audit 12 A11Y-03).
- A polite live region announces "Saved Arjun K." or "Could not save Arjun K. Use Retry or Save draft." It never announces on every keystroke.
- Focus is never moved by a save reply. The Next key behaviour is unchanged.
- Colour is never the only signal: every state is written out.

### 4.3 Server: new autosave endpoint

Route: `core:assessment-marks-autosave` at `my/assessments/<int:pk>/marks/autosave/`. View `assessment_marks_autosave`, decorated with `@teacher_required` and `@require_POST`. Add it to `route_permissions.json` with flags `require_POST` and `teacher_required`, matching `core:my-attendance-autosave`.

Request: `HX-Request: true`, the CSRF header, and the row's own form fields: `enrollment`, `status_{pk}`, `score_{pk}`, `base_status_{pk}` and `base_score_{pk}`, where `{pk}` is the enrollment id. The base fields are hidden inputs inside the row (4.4), so `hx-include="this"` sends them with every request. They hold the value the server last confirmed for this row, and are empty for a row never saved. A request without the two base fields is refused with 400, so a missing base can never mean "overwrite whatever is there".

**Pre-checks** (no lock, no write; cheap early refusals). **No reply body ever includes another student's data or any value beyond this row.**

| # | Check | Reply |
| --- | --- | --- |
| 1 | Not an HTMX request, or base fields missing | 400 "Autosave needs HTMX; use the Save draft button." (same as attendance) |
| 2 | Assessment not found in `_assessments()` | 404 |
| 3 | `can_enter_results(user, offering, section)` is false | 403 partial: "You can no longer enter marks for this assessment. Reload the page." No Retry. |
| 4a | Assessment is no longer DRAFT | 409 "This assessment is finalized. Ask an administrator if a result needs correcting." No Retry. |
| 4b | Assessment is DRAFT but dated after today (`is_open_for_entry` false) | 409 "Marks cannot be entered before the assessment date." No Retry. |
| 5 | `enrollment` not on `assessment.roster()` | 404 "Not on this assessment's roster." (same pattern as attendance) |
| 6 | Row fails `ResultEntryForm` validation, built from this row's two fields only, as attendance does with `AttendanceCaptureForm` | 422 with the first error |
| 7 | Row status is blank and score is blank | 204 with nothing to save. The client treats the row as idle. |

**Write transaction.** The lock order below is the one every path that writes results already uses. Autosave must keep it.

| # | Step, inside one `transaction.atomic()` | Reply when it fails |
| --- | --- | --- |
| T1 | Begin the transaction. | — |
| T2 | Lock and re-read the assessment: `assessment._lock()` (`select_for_update` on the assessment row, `core/models.py:3092`). | — |
| T3 | Recheck under the lock: status is DRAFT, `is_open_for_entry` is true, `can_enter_results` is true, and the enrollment is still on the roster. Pre-checks 3 to 5 may have passed before a concurrent change. | The same reply as pre-check 3, 4a, 4b or 5 |
| T4 | Lock the existing result row, if there is one: `assessment.results.select_for_update().filter(academic_enrollment=enrollment).first()`. | — |
| T5 | Compare its `(status, score)` with the submitted base. No row is equal to an empty base (OD-B1). | 409 conflict partial carrying only this row's current server value and the two buttons |
| T6 | If the new value equals the current saved value, write nothing. `updated_at` and `entered_by` stay unchanged, which makes the request idempotent. | 200 "Saved" |
| T7 | Save through the existing rules: `assessment.save_draft_result(enrollment=…, status=…, score=…, actor=request.user)`. | On `ValidationError`, 409 with the first message, and the transaction rolls back |
| T8 | Commit. Build the reply after the commit: out-of-band counts and the new base values. | 200 "Saved" |

Notes:

- **Lock order is assessment first, then the result row, on every path:**
  - The whole-form Save draft (`core/views.py:2207-2212`) opens one outer transaction. Its first `save_draft_result` call takes the assessment lock (`_lock`, `core/models.py:3209`) and holds it until commit. Only then does it write result rows.
  - `finalize` locks the assessment, then reads and freezes results.
  - Autosave takes the assessment lock at T2, before T4 touches any result row.

  Autosave follows the existing assessment-then-result lock order. This avoids introducing the inversion present in Revision 1 of this specification; concurrency tests protect that order. Taking `_lock` again inside `save_draft_result` at T7 is harmless, because the lock is already held in the same transaction.
- **The assessment lock serialises all saves for one assessment.** Autosave against autosave, autosave against the whole-form Save draft, and autosave against finalize all run one after the other. Each request holds the lock only for one row's read-compare-write, which takes milliseconds. Rosters are at most a few dozen rows, so serialising is acceptable.
- **`IntegrityError` only inside a savepoint.** `save_draft_result` already wraps its insert in an inner `transaction.atomic()` savepoint and turns `IntegrityError` into `ValidationError` (`core/models.py:3207-3219`). The surrounding transaction therefore stays usable, and T7's failure path can still roll back cleanly. Under the assessment lock, two first saves for one enrollment can no longer race, because the second one reads the committed winner at T4 and gets the T5 conflict. The savepoint stays as a defence in depth. Rule for the implementation: **any `IntegrityError` the autosave view itself catches must come from a block wrapped in its own nested `transaction.atomic()`**. A bare `try/except IntegrityError` inside the outer transaction is not allowed, because PostgreSQL would leave the transaction aborted.
- **Known asymmetry, unchanged by B1:** `save_draft_result` reads the existing result before it takes the lock (`core/models.py:3200`). In the whole-form path, a row that autosave inserted while the form waited for the lock can make the whole form fail with "This Student already has a result for this assessment.". Nothing is partly saved, and the typed values are kept, which is today's behaviour. The whole-form POST has no base check. After B1 it is reached only without JavaScript or HTMX (4.2), so with JavaScript every save, including the fallback, goes through the base comparison. The no-JavaScript path keeps today's last-write-wins rule (section 12).
- Score comparison uses `Decimal`, so "42", "42.0" and "42.00" are equal. The base travels as the same plain string the form shows (`_plain_score`).
- The view must not loop over the whole roster for counts more than once per request. Counts come from one query over `assessment.results` against the roster, after commit, with the query count fixed and tested (10.1).

### 4.4 Client: `erp.js`

- The marks sheet (`[data-erp-marks]`) gains the same autosave wiring as the attendance roster, behind the same check: HTMX loaded and the rows carry `hx-post`. The template loads `vendor/htmx/2.0.4/htmx.min.js` only when the form is shown, matching `my_attendance.html:52`.
- Each row (`fieldset[data-erp-row]`) gets `hx-post`, `hx-trigger="change"`, `hx-include="this"`, `hx-vals` with the enrollment id, and `hx-sync="this:queue last"`.
- **Base submission (chosen design: hidden inputs).** Each row contains two hidden inputs, `base_status_{pk}` and `base_score_{pk}`, rendered from the saved result (empty when none). Because they sit inside the row's fieldset, `hx-include="this"` sends them with every autosave request, and no request hook is needed. They change **only** in three cases: (a) a 200 "Saved" reply, whose partial swaps them out of band with the confirmed value; (b) **Keep `{theirs}`**, which copies the server value from the conflict partial; (c) **Use `{mine}`**, which copies the server value from the conflict partial into the base, then triggers `change` to resend. A failed, refused or in-flight request never changes them. The whole-form Save draft also posts these inputs, and `ResultEntryForm` ignores fields it does not declare. A test pins that ignoring (10.1).
- The per-row bookkeeping (`_seq`, `_sent`, `_dirty`) and the "wait for in-flight saves before the form submits" guard are reused. Recommendation: move them into one small shared helper used by both sheets, without changing attendance behaviour. If that refactor is judged too risky, copy them, and add a comment pointing at the attendance block.
- `change` on a score box fires on blur, Next or Enter, not per keystroke (OD-B2). The existing "typing a score selects Marked" logic stays, but runs on `input` without triggering a save. Only `change` saves.
- The Next or Enter handler (`static/js/erp.js:620-636`) still moves focus to the next student. The `change` event from the field being left starts that row's save, and moving on never waits for it.
- **Final row:** today, Enter on the last row focuses the Save draft button (`static/js/erp.js:634-635`), which OD-B4 hides. With autosave wired, Enter on the last row instead starts that row's save, by triggering `change` on its score when the value differs from the last one sent, and **keeps focus in that row's score box**. It never moves focus to the hidden fallback button. When autosave is not wired (no HTMX), today's behaviour stays.
- On a 401 (OD-B3), every in-flight row shows `Not saved: you have been signed out.` and the existing session box switches to its signed-out state ("Anything on this page that was not saved is lost."), with a sign-in link that keeps `next`. Typed values stay on screen so the teacher can copy them. Nothing is written to browser storage.
- No automatic retry of any kind, on a timer or when the connection comes back. The `online` event is used only to update the reason text ("Connection is back. Tap Retry."), never to send.
- **Marks-page response handler (scoped).** The marks sheet does **not** change `htmx.config.responseHandling`. That global setting is set only inside the attendance block (`static/js/erp.js:438-445`), and other pages keep HTMX's defaults. Instead, the marks block adds `htmx:beforeSwap`, `htmx:sendError` and `htmx:timeout` listeners on the marks sheet element itself, so they see only that sheet's requests:
  - **2xx:** swap the row fragment; 204 swaps nothing.
  - **403, 404, 409 and 422 carrying the response header `X-ERP-Row-Fragment: 1`:** swap the row fragment with `isError = true`, so the server's own message appears in the row, with no Retry. The autosave view sets that header on every fragment it returns.
  - **403 without that header:** this is the CSRF failure page. Nothing is swapped. The row shows `Not saved: the page has expired. Reload the page.`, and `csrf` is recorded. A 404 without the header is treated the same way, with a generic message.
  - **401:** nothing is swapped. The row shows `Not saved: you have been signed out.`, and the session box switches to its signed-out state.
  - **Network errors (`htmx:sendError`), timeouts and 5xx:** nothing is swapped. The row shows `Not saved` with Retry, and `network` or `server` is recorded.
  - **Anything else:** nothing is swapped, and a generic `Not saved` is shown.
  - HTML from a reply that is not a marked row fragment is never inserted into the page.
- **Every background request identifies itself.** HTMX requests carry `HX-Request: true`. Every `fetch` in `erp.js` must send `X-Requested-With: XMLHttpRequest`. The attendance bulk-present `fetch` (`static/js/erp.js:399-404`) and the session-status `fetch` (`static/js/erp.js:1117`) already do. The B3 usage flush must as well. A static test fails if any `fetch(` call in `erp.js` lacks the header (10.1), so a new background request cannot quietly reintroduce F-1.

### 4.5 Concurrency and failure handling

| Situation | What happens | Why it is safe |
| --- | --- | --- |
| Teacher changes the same row twice quickly | `hx-sync queue last` sends one request at a time per row. The last value wins locally. The hidden base inputs update from each 200 reply before the queued request is built, so the second save is compared against the first save's result. | No lost update inside one tab. |
| Same row edited in two tabs or devices | Both saves wait on the assessment lock (T2). The second one reads the first's committed row at T4, finds its base stale at T5, gets 409, and shows both values with Use and Keep (OD-B1). | No silent overwrite. |
| Two first saves for a row never saved (two devices) | The assessment lock serialises them. The second one sees the first's committed row at T4 and gets the conflict at T5. The unique constraint and the savepoint in `save_draft_result` remain a backstop. | No 500, and the transaction is never left aborted. |
| Autosave on one device while a no-JavaScript whole-form Save draft from another device is committing | Both lock the assessment first, and the later one waits. If autosave runs second, its base check sees the form's values. If the form runs second, it keeps today's last-write-wins rule (4.3 note, section 12). | The same lock order on both paths. The concurrency tests protect it. |
| Admin finalizes while the teacher types | Finalize and autosave both lock the assessment first and run one after the other. A save after finalizing gets 409 "finalized" at T3. Finalizing after a save sees the saved row. | Finalization rules are untouched. A finalized result is only ever changed through `correct()`, with its history. |
| Admin finalizes when a row is still unsaved on the teacher's phone | `finalization_problems` already refuses while any roster enrollment has no result. If every row was saved, the unsaved local edit is refused (409) and the teacher is told to ask for a correction. | The correction path keeps its reason and history. |
| Teacher reassigned or deactivated mid-entry | The next save gets 403 (assignment) or is signed out (deactivated: the session hash check in `AccountSecurityMiddleware`). | `can_enter_results` is checked on every request. |
| Student leaves the roster mid-entry (enrollment ended or backdated) | 404 "Not on this assessment's roster." The row shows it with no Retry. | The roster is date-effective, so no result is written for an ineligible enrollment. |
| Network lost | XHR status 0 or a timeout (15 s) shows `Not saved: no connection. [Retry]`. The page line shows `Changes not saved`. | Nothing is queued, so nothing is sent later without the teacher (PWA Gate 2 rule). |
| Server error (5xx) | `Not saved. [Retry]`. The crash report follows Security Gate 4A. | Same as attendance. |
| Session idle or absolute expiry | 401 (OD-B3). Signed-out state as in 4.4. Values stay on screen. | No false "Saved". The server signs out as before. |
| CSRF failure (stale token after re-sign-in in another tab) | 403 from `CSRF_FAILURE_VIEW`, without the `X-ERP-Row-Fragment` header, so the scoped handler swaps nothing (4.4). The row shows `Not saved: the page has expired. Reload the page.` No Retry. | A retry would fail the same way. |
| Absolute 8-hour limit near | The existing session warning appears ("Save your work now"). Autosave keeps saving until the limit. | Unchanged. |
| Fallback Save draft pressed while rows are in flight (JavaScript mode) | The button waits for in-flight saves, then re-sends only the failed rows through autosave with their bases. A row changed elsewhere gets the conflict prompt. | No whole-form POST in JavaScript mode, so the fallback cannot bypass OD-B1. |
| Duplicate request, for example a proxy replay | Step T6 makes an equal value a no-op. A different value with an old base hits the conflict check. | Idempotent. |

### 4.6 What does not change

- `assessment_marks_entry` GET and POST handling, the redirect and its messages.
- `ResultEntryForm` rules, including "a score with no status is Marked" and "a saved result cannot be un-entered".
- `save_draft_result`, `finalize`, `correct`, `ResultCorrection`, `mark_stale_for_result`, publication and the guardian portal.
- The finalized and not-yet-open views of the page (cards and the "opens on" alert).
- Who can open the page and the route inventory entry for `core:assessment-marks-entry`.

### 4.7 Signed-out reply for background requests (OD-B3)

**Finding F-1 (inference, read from code, not exercised):** when the session has expired, `AccountSecurityMiddleware` answers every request with a 302 to the sign-in page (`accounts/middleware.py:84-89`). XHR and `fetch` follow redirects without telling the page, so the page receives the sign-in HTML with status 200:

- **Attendance row autosave (HTMX):** 200 counts as successful, so HTMX would swap the sign-in page's HTML into the row status cell and clear the row's dirty flag.
- **Attendance bulk present (`fetch`, `static/js/erp.js:399-433`):** `response.ok` is true and `response.json()` fails into `{}`, so every row would show `✓ Saved` although nothing was saved.

The session warning usually signs the page out first, which makes this rare. But a phone that sleeps through the warning wakes with a stale page, so it can happen.

**Change:** in `AccountSecurityMiddleware`, when expiry is detected and the request has `HX-Request: true` or `X-Requested-With: XMLHttpRequest`, return `401` with body `{"error": "signed-out", "expired": "idle"|"limit"}` and `Cache-Control: no-store`, instead of the redirect. The session is still logged out. Normal page requests keep the redirect, `expired` and `unsaved=1` exactly as today.

- **Coverage of every background path:**
  - Attendance row autosave and marks autosave are HTMX, so they carry `HX-Request`.
  - Attendance bulk present already sends `X-Requested-With` (`static/js/erp.js:403`). After the change it gets 401, `response.ok` is false, and every row shows its failure text instead of `✓ Saved`.
  - Session status already sends `X-Requested-With` and treats 401 as signed out (`static/js/erp.js:1117-1128`).
  - The B2 beacon must send `X-Requested-With` as well (5.6).

  A static test enforces the header on every `fetch` (4.4).
- `session-status` already answers signed-out clients with 401 (`test_session_errors_audit18::test_signed_out_gets_401_and_answers_are_not_cached`), so the session script handles 401 already.
- On the attendance page, the existing global `responseHandling` (`static/js/erp.js:438-445`) swaps only `409|422`. Every other `[45]..` reply, including 401, is an error with no swap, so the attendance row shows "Not saved." with Retry and never the sign-in page. The marks page uses its own scoped handler (4.4) and leaves that global setting alone.
- B1 adds one more line to attendance: on 401, call the session box's signed-out state, as marks entry does.
- **Signed out without an expiry** (signed out in another tab, session deleted, cookie cleared). The request arrives anonymous, so the expiry branch never runs. `teacher_required` would then redirect to sign-in, and F-1 would return. **Change, part 2:** in the same middleware's response phase, a redirect to `LOGIN_URL` answering a background request (`HX-Request` or `X-Requested-With`) is replaced by the same 401 body, with `"expired": null`. That covers every guarded background endpoint without editing each decorator. Normal page requests are untouched.
- The beacon does not rely on either path. It returns 401 itself for any request that is not authenticated (5.6).

### 4.8 Edge cases

| Case | Expected |
| --- | --- |
| Score `0` | Saved as MARKED 0 (`test_zero_score_counts_as_marked` stays green). |
| Score `50.005` with maximum 50 | 422 from the form's `decimal_places=2` or `max_value` check. The row shows the message. |
| Score typed as `1e` (browser shows empty) | The browser number check stays on (`core/forms.py:903-909`), so no change fires with an empty value for a typo. A blank score with Marked shows the local `Enter a score` state and sends nothing. A request that arrives anyway gets 422 "Enter a score or choose Absent". |
| Teacher selects Absent on a saved MARKED row | Saved as ABSENT with the score cleared. Draft edit, not a correction. |
| Teacher clears the score of a saved MARKED row | Local `Enter a score` state, nothing sent, saved result unchanged (OD-B5). A hand-crafted request gets 422 "Enter a score or choose Absent." Nothing is deleted. |
| Assessment dated tomorrow (page shows "opens on") | No form, so no autosave. A hand-crafted POST gets 409 "Marks cannot be entered before the assessment date." at pre-check 4b, before `save_draft_result` is reached. "Finalized" is used only when the assessment is no longer DRAFT. |
| Roster of 0 | Empty state as today. No autosave wiring. |
| Teacher with admin rights who is not the assigned teacher | 403, as on the page (Teachers group plus assignment decide, not admin permissions). |
| Guardian session | 403 from `teacher_required`. |
| Assessment finalized between page load and the first save | 409 "finalized". The page line shows `Changes not saved`. Reloading shows the finalized cards. |

## 5. B2: Measurement policy and store

### 5.1 Principles (proposed ADR 0027 wording)

1. **Purpose limitation.** Measurements exist only to answer the questions in section 9 and the audit's §13. A new purpose needs an ADR amendment.
2. **No person, no record, no value.** No measurement row, request body, log line or report contains a user, guardian, teacher or student identifier, name or username. It also contains no database ID or public UUID of any record, no URL path with IDs, no query string, no search term, no typed value, no mark, no attendance status, no count of absences, no note, no free text, no error message text, no IP address (raw or hashed), no user-agent string, no session ID or cookie, and no precise timestamp.
3. **Aggregate at write time.** The server turns each accepted event into an increment on a daily counter row. No per-event row exists at any point, and measurement events are not logged (OD-B6).
4. **Allow-list everything.** Event names, workflow keys, steps, failure codes, page routes, device dimensions and buckets are fixed enums in code, mirrored by database check constraints. Anything else is rejected and dropped.
5. **Small numbers stay hidden.** Reports hide cells under 5 after every filter and grouping, and group by ISO week (OD-B12).
6. **Short retention.** A daily cron job deletes rows older than 180 days, whether or not measurement is switched on (OD-B7).
7. **Off unless the school approves in writing.** `USAGE_MEASUREMENT_ENABLED` defaults to False and is switched on only after documented school approval (OD-B9). When it is off, the client sends nothing and the server stores nothing. Global Privacy Control is honoured on both server and client (OD-B10).
8. **No new client storage.** No cookie, localStorage, sessionStorage or IndexedDB entry is added. Multi-page workflows keep their start time in the server-side Django session (section 6), which is deleted at sign-out.
9. **Honest claims.** The data is described as *aggregate, identifier-free and designed to minimise re-identification*, never as absolutely anonymous. In a small school a weekly count can still hint at a person when combined with other knowledge. That is why principles 5 and 7 and operator-only access exist.

### 5.2 What may be recorded

Every counter row has exactly the dimensions below. Each value comes from a fixed enum, and a blank is allowed only where the "Used by" column permits it. The final schema is in 5.4.

| Dimension | Values | Used by | Source |
| --- | --- | --- | --- |
| `day` | Calendar date in school time | All | Server clock (`business_today`) |
| `area` | `admin`, `teacher`, `guardian`, `multi`, `public`. **Page and workflow events always use the surface they happened on** (admin, teacher or guardian), even for a user with several areas. `multi` is used only for sign-in events where no single area applies: `sign_in/completed`, `sign_in/password_changed_first` and `session/relogin_after_expiry` for a user with more than one area. `public` means not signed in, which includes every failed sign-in. | All | Server only: from the route (`core/navigation.py`), or from `user_areas` at sign-in. A value reported by the client is accepted only if it is one of the signed-in user's own areas. |
| `workflow` | Keys in section 6, plus `page`, `sign_in`, `session` | All | Allow-list |
| `step` | `started`, `completed`, `attempt`, `saved`, `viewed`, `shown`, `installed`, `dismissed`, `failed`, `throttled`, `expired_idle`, `expired_limit`, `expired_unsaved`, `relogin_after_expiry`, `password_changed_first`, `retry_tapped`, `retry_succeeded`, `fallback_save_used`, and the failure codes `network`, `server`, `signed_out`, `forbidden`, `conflict`, `closed`, `invalid`, `csrf`. This list is the database check constraint, with nothing else allowed. | All | Allow-list; the allowed steps per workflow are listed in section 6 |
| `page_route` | A curated allow-list (below), or `other` | `page` only; blank otherwise | The server renders it into the page, and the beacon re-checks it against the allow-list (5.6) |
| `duration_bucket` | `<5s`, `5–15s`, `15–60s`, `1–3m`, `3–10m`, `10–30m`, `>30m` | `completed` steps of workflows with a timer (section 6); blank otherwise | Server-computed for session timers; client-computed for page-memory timers, then checked against the enum |
| `size_bucket` | `1–20`, `21–40`, `41+` | `attendance_capture` and `marks_entry` only; blank otherwise | Server, from the roster size; never the exact number |
| `age_bucket` | `same_day`, `1–2d`, `3–7d`, `later` | `notice_view` only; blank otherwise | Server, from the notice's publish date and today (OD-B13) |
| `device` | `phone` (<576 px), `tablet` (576–991 px), `desktop` (≥992 px), or blank when unknown | All | Client `matchMedia`, sent in the `X-ERP-Client` header or the beacon; matches the CSS breakpoints |
| `display` | `browser`, `installed`, or blank | All | Client `matchMedia('(display-mode: standalone)')` |
| `platform` | `android`, `ios`, `other`, or blank | All | Client coarse check (OD-B11) |

**`page_route` allow-list (v1).** Adding a route means editing the enum and adding a migration that updates the check constraint, so each addition is a deliberate, reviewed change.

| Area | Routes |
| --- | --- |
| Admin | `core:admin-overview`, `core:student-list`, `core:student-detail`, `core:student-attendance`, `core:attendance-register-list`, `core:attendance-register-detail`, `core:attendance-reports`, `core:report-missing-attendance`, `core:report-daily-absentees`, `core:announcement-list`, `core:announcement-detail`, `core:guardian-list`, `core:guardian-detail`, `core:teacher-list`, `core:teacher-detail`, `core:applicant-list`, `core:applicant-detail`, `core:timetable-index`, `core:notifications-to-send`, `core:publications-stale`, `core:import-list` |
| Teacher | `core:my-home`, `core:my-attendance`, `core:my-attendance-history`, `core:my-assessments`, `core:assessment-marks-entry`, `core:my-students`, `core:my-student-detail`, `core:my-timetable`, `core:my-gradebook`, `core:my-results` |
| Guardian | `portal:home`, `portal:child`, `portal:attendance`, `portal:notices`, `portal:notice`, `portal:report-cards`, `portal:report-card` |
| Public | `root:login` (recorded server-side on the sign-in GET, with blank device fields, because signed-out browsers cannot use the beacon) |

Every signed-in page outside the list is recorded as `other` for its area, so the report shows how much of phone use the list does not cover.

**Failure codes** (closed list, used as `step`):

- `network`: an **observed network failure**, meaning a save that ended with status 0 or a timeout. It is client-reported. While offline, the browser cannot report it, so it is kept in page memory and sent with the next successful flush (6). If the page closes first, it is lost.
- `server`: 5xx. **Client-recorded**, through the beacon.
- `signed_out`: 401 on an autosave route. **Server-recorded**, by `AccountSecurityMiddleware` when it answers 401 to a background request on `core:assessment-marks-autosave`, `core:my-attendance-autosave` or the bulk-present route. Both the expiry path and the anonymous redirect path count. The area is the route's, and the workflow is `marks_entry` or `attendance_capture`.
- `forbidden`: 403 from the autosave view. **Server-recorded.**
- `conflict`: 409 conflict. **Server-recorded.**
- `closed`: 409 finalized, before the assessment date, or register submitted. **Server-recorded.**
- `invalid`: 422. **Server-recorded.**
- `csrf`: 403 from the CSRF failure view. **Client-recorded**, because the CSRF view runs before any autosave code. The client recognises it as a 403 without `X-ERP-Row-Fragment` (4.4).

The save-handling steps are all **client-recorded**: `retry_tapped` (each Retry tap), `retry_succeeded` (a Retry whose request then returns 200), and `fallback_save_used` (each tap of the fallback Save draft, 4.2). `attempt` is also client-recorded, once per autosave request sent.

**Value:** `count`, a positive integer, incremented.

### 5.3 What must never be recorded

| Never | Reason |
| --- | --- |
| Names, usernames, emails, phone numbers | Personal data |
| User, student, guardian, enrollment, assessment, section, register or announcement IDs, or portal UUIDs | Linkable to a person or record |
| Marks, scores, statuses, attendance values, absence counts, notes, remarks | School record content |
| URLs, paths with IDs, query strings, search terms, route names outside the allow-list | Can contain IDs or names, or widen what is measured |
| Error message text | Can quote a value or name (Security Gate 4A applies the same rule to crash email) |
| IP address, hashed or not; user-agent string; screen size; device model | Fingerprinting |
| Session ID, cookie values, CSRF tokens | Linkable |
| Time of day | Re-identifies people in a small school |
| Which notice a guardian opened, or whether a given guardian ever opened one | Per-person read tracking is ANA-06, which is undecided |
| A role guessed from a failed username | A failed sign-in has no authenticated role, so it is always `public` |

### 5.4 Model, write path and retention

New model `core.UsageCounter` (B2 migration; OD-B14):

| Field | Type |
| --- | --- |
| `day` | `DateField`, indexed |
| `area`, `workflow`, `step` | `CharField(choices=…)`, never blank |
| `page_route`, `duration_bucket`, `size_bucket`, `age_bucket`, `device`, `display`, `platform` | `CharField(choices=…, blank=True, default="")` |
| `count` | `PositiveIntegerField`, at least 1 |

**Constraints:**

- **Unique** on `(day, area, workflow, step, page_route, duration_bucket, size_bucket, age_bucket, device, display, platform)`. Blanks are empty strings, never NULL, so identical rows really merge.
- **Enum checks:** every enum field is in its allow-list, or blank where blank is allowed.
- **Column-use checks:**
  - `page_route` is non-blank if and only if `workflow = 'page'`.
  - `size_bucket` is blank unless `workflow` is `attendance_capture` or `marks_entry`.
  - `age_bucket` is non-blank if and only if `workflow = 'notice_view'`.
  - `duration_bucket` is blank unless `step = 'completed'`.
  - `area = 'public'` only for `workflow = 'sign_in'`, or for `workflow = 'page'` with `page_route = 'root:login'`.
  - `area = 'multi'` only for `sign_in` with step `completed` or `password_changed_first`, or `session` with step `relogin_after_expiry`.

The database refuses unknown values and wrong combinations, even if a code path forgets.

**Never registered in Django admin.** `core/admin.py` does not import it, and a test asserts it is absent from `admin.site._registry`.

**Write: `usage.record(**dims)`.** It validates every dimension against the enums before touching the database. It is a no-op when the setting is off or the request carries `Sec-GPC: 1`. Otherwise:

```text
try:
    with transaction.atomic():                      # savepoint S1
        n = UsageCounter.objects.filter(**dims).update(count=F("count") + 1)
        if n == 0:
            try:
                with transaction.atomic():          # savepoint S2
                    UsageCounter.objects.create(**dims, count=1)
            except IntegrityError:                  # another request created it first
                UsageCounter.objects.filter(**dims).update(count=F("count") + 1)
except DatabaseError:
    log the route pattern only; drop the event
```

- `update_or_create` with `F()` is **not** used, because its create path cannot insert an `F()` expression.
- A creation race rolls back only S2, then retries the update once against the row the other request committed.
- Any other database error rolls back only S1. The application's own transaction is never left aborted, whether `record()` runs inside one or not.
- Views call `record()` **after** their own write transaction has closed. In the autosave views that is after T8, so a measurement problem cannot affect a save. If a caller is ever inside an atomic block, S1 still isolates it.

**Retention: `purge_usage_counters`:**

- **Cutoff:** it deletes rows where `day <= business_today() − 180 days`. On any date it keeps exactly the 180 calendar days that end today, from `today − 179` to `today` inclusive.
- **Schedule:** it runs daily on the **existing cron service**, as its own step in the start command, so a failure in another step cannot skip it. For example: `sh -c "python manage.py purge_usage_counters; python manage.py expire_import_batches && …"`. `README.md` and `docs/OPERATIONS.md` are updated to match.
- It runs whether or not measurement is switched on, so switching measurement off never strands old rows.
- It is idempotent, prints only the number of rows deleted, and needs no setting.
- **Safety net, not a substitute:** `usage_report` prints a warning when any row is older than the cutoff, which means the cron step is missing or failing. The checklist for switching measurement on (OD-B9) includes confirming that the cron step exists.

### 5.5 Server-side signals

These are recorded where these moments happen. `accounts/views.py` `LoginView` subclasses Django's `LoginView` and today overrides none of `get`, `form_valid` or `form_invalid`. **B2 adds those three overrides.** Each records its signal, then returns the result of `super()`. Authentication, throttling, redirects, `redirect_authenticated_user` and the existing `get_redirect_url` stay exactly as they are. If a measurement call fails, it is ignored, as `record()` already guarantees (5.4).

| Signal | Where | Area | Workflow and step |
| --- | --- | --- | --- |
| Sign-in page shown | `LoginView` GET | `public` | `page` / `viewed`, `page_route = root:login` |
| Sign-in failed | `accounts/views.LoginView.form_invalid` | `public`, always | `sign_in` / `failed` |
| Sign-in throttled | Throttle path in `accounts/forms.py` (`security.is_throttled`) | `public`, always | `sign_in` / `throttled` |
| Sign-in succeeded | `LoginView.form_valid` | From `user_areas`: `admin`, `teacher`, `guardian` or `multi` | `sign_in` / `completed` |
| Signed in again within 10 minutes of an expiry | When `AccountSecurityMiddleware` expires a session, it logs out (which flushes the session). It then stores a marker `_u_expired_at` holding epoch seconds only in the new anonymous session. Django's `login()` keeps an anonymous session's data, because it only cycles the key. `LoginView.form_valid` records the event only if that marker exists and is at most 10 minutes old. It then deletes the marker after **every** successful sign-in, whatever its age. The editable `?expired=` query value is used only for the on-screen message and is never trusted for measurement. The marker is never written to `UsageCounter`. | As above | `session` / `relogin_after_expiry` |
| Forced password change completed | Password-change view | As above | `sign_in` / `password_changed_first` |
| Session expired, idle or limit, with or without an unsaved POST | `accounts/middleware.expired_redirect` and the new 401 path | Area of the route requested | `session` / `expired_idle`, `expired_limit`, `expired_unsaved` |
| Autosave outcomes the server sees | The two autosave views and bulk present | Route area | `attendance_capture` or `marks_entry` / `saved`, `invalid`, `conflict`, `closed`, `forbidden` |
| Signed-out reply to an autosave request | `AccountSecurityMiddleware`, on both 401 paths (4.7) | Route area | `attendance_capture` or `marks_entry` / `signed_out` |

The device dimensions for server-side signals come from one request header, which `erp.js` sets on its own XHR and HTMX requests: `X-ERP-Client: device=phone;display=installed;platform=android`. It is parsed strictly against the enums, and any other value is dropped. Signals from requests without it, such as the sign-in POST and plain form posts, record blank `device`, `display` and `platform`. **The header is never logged.**

### 5.6 Client beacon endpoint

Route: `usage-beacon` at `/u/` in `config/urls.py`, POST only.

- **Guard:**
  - The view itself returns **401** with an empty body and `Cache-Control: no-store` for any request that is not authenticated. It does not use `login_required`, because that redirects.
  - An expired session also gets 401, from the middleware (4.7), because the beacon sends `X-Requested-With: XMLHttpRequest`.
  - CSRF is checked through the `X-CSRFToken` header on `fetch(…, {keepalive: true})`. `navigator.sendBeacon` is not used, because it cannot send either header.
- **Idle clock:** like `session-status`, a beacon must **not** count as activity, or a page left open would never expire. `AccountSecurityMiddleware` skips the `SEEN_KEY` update for this exact path. It still checks the idle and absolute limits, and signs out an expired session.
- **Forced password change:** the beacon is not in `ALLOWED_WHILE_CHANGE_REQUIRED`, so it is redirected and dropped. This is acceptable.
- **Body:** JSON, at most 2 KB and at most 20 events:
  - Each event is `{"w": workflow, "s": step, "b": duration_bucket}`.
  - One shared object is `{"d": device, "x": display, "p": platform, "r": page_route, "a": area}`.
  - `r` and `a` are copied from `data-erp-route` and `data-erp-area` on `<body>`. The server renders `data-erp-route` only as an allow-listed route name or `other`, and never as a path.
- **Validation:**
  - `r` must be in the allow-list or `other`.
  - `a` must be one of `user_areas(request.user)`.
  - Every other field must match its enum and the column-use rules.
  - **If any field fails, the whole batch is dropped** (400, nothing recorded).
- **Rate limit:** at most 200 accepted events per session per hour, counted in the server session. Excess events are silently dropped with 204.
- **Reply:** 204, no body, `Cache-Control: no-store`.
- **When off, or GPC is set:**
  - The page carries no `data-erp-usage` attribute, so `erp.js` sends nothing.
  - `erp.js` also checks `navigator.globalPrivacyControl === true` before every flush.
  - The server returns 204 without recording when the setting is off or the request carries `Sec-GPC: 1`.

Add `usage-beacon` to `route_permissions.json` with flags `require_POST` and `never_cache` and no decorator guard. This matches `root:session-status`, which also authenticates inside the view. A test asserts that an anonymous POST gets 401, not 302.

## 6. B3: Workflows to instrument

**Counting rules:**

- **Completion rate = completed ÷ started**, per ISO week.
- **Left incomplete = started − completed.** It is derived, never stored as an event. Leaving the page, hiding it or switching apps records nothing.
- No start is ever joined to its completion, and nothing is counted per person.
- **Limitations, stated in every report:** one person may start a workflow several times, and a workflow started in one week and finished in the next counts in both. So "left incomplete" is an upper bound on unfinished work. It is not a count of people who gave up.

| Key | Area | Steps recorded | Started when | Completed when | Timer kept in | Extra dimension |
| --- | --- | --- | --- | --- | --- | --- |
| `attendance_capture` | Teacher | `started`, `completed`, `attempt`, `saved`, failure codes | First GET of `my-attendance` for today's register in this session, with the register DRAFT or not yet open | POST to `my-attendance-submit` succeeds | Server session key `_u_attendance` (epoch seconds only) | `size_bucket` |
| `marks_entry` | Teacher | Same as above | Marks-entry page shown with a form | Not-entered count reaches 0 in this page view (from server reply counts) | Page memory only | `size_bucket` |
| `teacher_home` | Teacher | `started`, `completed` | `my-home` requested | Page `load` event | Page memory only | — |
| `find_student` | Admin | `started`, `completed` | GET of `student-list` with a non-empty `q` (measurement never reads the term) | GET of `student-detail` in the same session within 10 minutes | Server session key `_u_find_student` | — |
| `missing_attendance_act` | Admin | `started`, `completed` | GET of the Missing attendance report | A "Take register" or "Review class teacher" link is followed (Option A1 links) | Page memory; sent on click | — |
| `page` | Admin, teacher, guardian (beacon); `public` for the sign-in page (server) | `viewed` | Any HTML page | — | — | `page_route`. This is the G-04 phone inventory. |
| `guardian_first_view` | Guardian | `started`, `completed` | Successful guardian sign-in | First GET of a portal child, attendance or report page | Server session key `_u_guardian` | — |
| `guardian_report_pdf` | Guardian | `started`, `completed` | Report card page shown | PDF download response sent (server side) | Server only, no timer | — |
| `notice_view` | Guardian | `viewed`, recorded when the notice detail is shown | — | — | — | `age_bucket` (OD-B13) |
| `install` | All | `shown`, `installed`, `dismissed` | Install bar shown (`shown`) | The `appinstalled` event records `installed`. The install bar's dismiss button records `dismissed`. These are separate outcomes, and a dismissal never counts as an installation. | Page memory | — |

**Save attempts.** Every autosave request the client sends records `attempt`, through the beacon:

- **Client-recorded:** `attempt`, `network`, `server`, `csrf`, `retry_tapped`, `retry_succeeded` and `fallback_save_used`.
- **Server-recorded (5.5):** `saved`, `invalid`, `conflict`, `closed`, `forbidden` and `signed_out`.

Client-reported counts are **lower bounds**: an event still queued in memory is lost if the page closes before a flush succeeds. This matters most for `network`. A browser cannot report a failure while it is offline, so observed network failures reach the server only when a later flush succeeds after the connection returns: after a successful Retry, a later save, or the next 30-second flush. A complete disconnect that lasts until the teacher closes the page is never counted. The report labels the figure "observed network failures (undercounts complete disconnects)".

**Session timer keys** hold only a number. They are removed on completion and vanish at sign-out, and they never hold a record ID. For `attendance_capture`, "today's register in this session" is decided by the view, which already knows the register. The key itself carries no section or register ID, so two sections in one session share one timer. That inaccuracy is accepted.

**Client mechanics:**

- `base.html` and `portal/base.html` add `data-erp-usage="1"`, `data-erp-route` and `data-erp-area` on `<body>`. They do this only when measurement is on and the page request carried no `Sec-GPC: 1`.
- `erp.js` sends nothing when `navigator.globalPrivacyControl === true`.
- Events are queued in memory only, at most 20, and the oldest are dropped first.
- The queue flushes on `visibilitychange` to hidden, or every 30 seconds. Every flush sends `X-Requested-With` (4.4).
- If a flush fails, its events stay in memory until the next flush moment. A successful save or Retry also triggers a flush, so failures observed while offline are sent as soon as the connection is proven back. They are never written to storage, and they are lost when the page unloads.
- This queue holds only measurement events, never school data or a save.

### 6.1 Report

`python manage.py usage_report --weeks 4 [--area teacher] [--workflow marks_entry] [--device phone]` prints, per ISO week:

- for each workflow: started, completed, completion rate, left incomplete (derived, with its limitation), and the duration bucket distribution, split by `size_bucket` for marks and attendance;
- save attempts and each failure code, with the ratios used in section 9;
- `page` counts per `page_route` by device, including the `other` share. This is the admin phone inventory;
- `notice_view` by `age_bucket`, labelled "among notices that were viewed";
- install `shown`, `installed` and `dismissed` as separate lines;
- the share of installed versus browser use, and platform splits.

**Suppression:**

- Suppression is applied **after** every filter (`--area`, `--workflow`, `--device`) and after weekly grouping, on the final table that is printed.
- Any cell under 5 prints as `<5`.
- If exactly one cell in a row or column is hidden and a total is printed, the next-smallest cell is hidden too, so the hidden value cannot be recovered by subtraction.
- A ratio prints as `n/a` when its denominator is below the minimum stated for it in section 9.
- CSV mode applies the same rules.

Output goes to stdout only, as plain text or `--format csv`. No file is kept on the server. The report also warns about rows older than the retention cutoff (5.4).

## 7. Security and privacy boundaries

| Boundary | Rule | Enforced by |
| --- | --- | --- |
| B1 does not widen access | The autosave endpoint has the same guard as the page (`teacher_required` plus `can_enter_results`) and refuses finalized assessments | View checks; route inventory; tests 10.1 |
| B1 does not weaken history | Only `save_draft_result` writes. It cannot reach FINALIZED results, `ResultCorrection` or publication | Existing model locks; tests 10.1 |
| Autosave replies leak nothing | Bodies contain only the posted row's own status, score and message, and on conflict that same row's server value, which this teacher may already see on the page | Template partial; test asserting no other enrollment's data appears |
| Measurement is aggregate and identifier-free | Allow-list enums, a curated `page_route` list and column-use rules, all mirrored by DB check constraints. No free-text column exists. The design minimises re-identification; it does not claim absolute anonymity (5.1 principle 9) | Model constraints; tests 10.2 |
| Measurement is not a log | No `logger` call includes beacon bodies, the `X-ERP-Client` header or counter dimensions | Code review checklist; test patching the logger |
| Measurement cannot slow or break workflows | `record()` is an update, then an insert only if needed, inside its own savepoints, and it is called after the view's write transaction closes. A database error rolls back only the measurement savepoint (5.4). The beacon is `keepalive` and fire-and-forget | Tests 10.2 |
| Measurement does not extend sessions | The beacon path does not touch the idle clock | Middleware test |
| Signed-out browsers cannot send beacons | The beacon view returns 401 itself for unauthenticated requests, and the middleware returns 401 for expired sessions; never a redirect | Tests 10.2 |
| Global Privacy Control | `Sec-GPC: 1` stops server recording and the body attribute; `navigator.globalPrivacyControl === true` stops client sending | Tests 10.2, 10.3 |
| Reports minimise re-identification | Cells under 5 hidden after every filter and grouping, secondary suppression where a total would reveal a hidden cell, weekly grouping, no time of day | `usage_report` tests |
| Access to reports | Server shell access only (OD-B8). No route serves counters, and `UsageCounter` is never registered in Django admin | No route exists, which the inventory test proves; an admin-registry test |
| Off by default, on only with written approval | Setting default False. Switching on requires documented school approval recorded in the operations record (OD-B9) | Settings test; `docs/OPERATIONS.md` checklist |
| Retention does not depend on use | `purge_usage_counters` runs daily on the cron service whether or not measurement is on | Purge tests; operations checklist |
| Third parties | None. Counters stay in the school database. Crash email rules are unchanged | No new dependency |

**Threats considered:**

- A signed-in user forging beacons to skew counts. Impact: misleading evidence. Mitigation: per-session rate limit, strict enums, `area` checked against the user's own areas, and treating counts as signals reviewed with interviews, not as proof.
- Re-identification by combining a weekly count with `entered_by` or register data. Mitigation: no time of day, weekly reporting with k ≥ 5 applied after filtering, secondary suppression, and operator-only access. Residual risk remains in a very small school, which is why the data is never described as anonymous.
- Measurement code reading form values by mistake. Mitigation: the beacon payload builder takes only enum constants. A test feeds a page with typed marks and asserts that no digit-bearing value except buckets and allowed route names reaches the payload.

## 8. Affected files

| File | PR | Change |
| --- | --- | --- |
| `core/views.py` | B1 | New `assessment_marks_autosave`. Counts helper shared with the page. |
| `core/urls.py` | B1 | `my/assessments/<int:pk>/marks/autosave/`. |
| `core/tests/route_permissions.json` | B1, B2 | New entries `core:assessment-marks-autosave` and `usage-beacon`. |
| `core/templates/core/assessment_marks_entry.html` | B1 | Row `hx-*` attributes, hidden `base_status_{pk}` and `base_score_{pk}` inputs, the page autosave line, Save draft as fallback, HTMX script block, live region. |
| `core/templates/core/_marks_autosave_status.html` (new) | B1 | Row status, error, Retry and conflict partial (carrying the server value for Use and Keep), plus out-of-band counts and base inputs. |
| `core/forms.py` | B1 | `ResultEntryForm` may accept a single-row subset (no rule changes). Helper to read and compare the base value. |
| `static/js/erp.js` | B1, B3 | Marks autosave wiring; shared row bookkeeping helper; 401 handling in both sheets; later the usage queue and `X-ERP-Client` header. |
| `accounts/middleware.py` | B1, B2 | 401 for background requests on expiry, and in place of a sign-in redirect for anonymous background requests (B1). Beacon path skips the idle clock (B2). |
| `static/css/erp.css` | B1 (only if needed) | Reuse `.erp-row-saved`, `.erp-row-failed` and `[data-erp-autosave-state]`. Any new rule triggers the `test_ui*` string tests. |
| `docs/adr/0027-privacy-safe-usage-measurement.md` (new) | B2 | Principles 5.1, enums 5.2 and 5.3, retention and access. |
| `core/models.py` + `core/migrations/00xx_usagecounter.py` | B2 | `UsageCounter` with unique and check constraints. |
| `core/usage.py` (new) | B2 | Enums, `record()`, purge, header parser, beacon validation. |
| `core/usage_views.py` (new) | B2 | Beacon view. |
| `config/urls.py` | B2 | `usage-beacon` route. |
| `config/settings.py` | B2 | `USAGE_MEASUREMENT_ENABLED = parse_flag(…, default False)`. |
| `accounts/views.py`, `accounts/forms.py` | B2 | Sign-in page view, sign-in, throttle, relogin and password-change signals. |
| `core/views.py`, `core/portal_views.py` | B3 | Workflow start and completion calls listed in 6. |
| `templates/base.html`, `templates/portal/base.html` | B3 | `data-erp-usage`, `data-erp-route` (allow-listed name or `other`) and `data-erp-area` on `<body>` when enabled and no `Sec-GPC`. |
| `core/management/commands/usage_report.py` (B3), `purge_usage_counters.py` (B2) (new) | B2, B3 | Report and purge. |
| `README.md` (cron section) | B2 | Daily cron start command gains `purge_usage_counters` as its own step. |
| `docs/OPERATIONS.md`, `docs/PERMISSIONS.md`, `docs/ROADMAP.md`, the privacy notice text | B2, B3 | The switch-on checklist: written school approval recorded, cron purge step confirmed, setting set. How to read and purge. That no permission is added. The school notice paragraph. |

No new permission, dependency or CI job. The only deployment change is one added step in the existing cron start command (B2). `core/admin.py` is not changed. B1 has no migration. B2 has exactly one. A later `page_route` addition needs its own migration.

## 9. How the evidence guides later decisions

Each trigger below is a **review trigger** (OD-B15). Meeting it opens a design gate with its own spec and approval. Missing it keeps the current decision. The numbers are proposals.

**Rules that apply to every trigger:**

- **Only calculable ratios.** Every figure is the sum of one stored counter divided by the sum of another, over the whole window. Weekly ratios are never averaged. Nothing below needs a per-person, per-workflow-instance or per-session join, because the counters cannot support one.
- **Window:** at least 4 instructional weeks.
- **Minimum denominators:** each ratio states its own. Below it, the report prints `n/a` and the trigger reads "not enough data", which is never taken as met or missed.
- **Lower bounds:** client-reported counts (`attempt`, `network`, `server`, retries, `fallback_save_used`) are lower bounds (section 6), and ratios that use them are labelled as such.
- **Not answerable from counters, so decided by short interviews (audit §13):**
  - how many distinct people or workflows were affected;
  - whether unfinished work followed a failure;
  - who never saw a notice;
  - why a sign-in failed.

### 9.1 Offline write and sync (MOB-08, MOB-09)

| Ratio | Definition (phone, `attendance_capture` + `marks_entry`) | Minimum denominator |
| --- | --- | --- |
| N, observed network failure rate | `network` (observed network failures) ÷ `attempt` | 500 attempts |
| R, retry success rate | `retry_succeeded` ÷ `retry_tapped` | 20 retry taps |
| F, fallback rate (supporting) | `fallback_save_used` ÷ `attempt` | 500 attempts |

- **Trigger to open an offline-write design gate:** `(N ≥ 2%) AND (R < 80%)`. Connections drop on phones often enough to matter, and tapping Retry within the task usually does not fix it.
- **If N ≥ 2% but there are fewer than 20 retry taps:** not enough data. Interviews ask teachers what they did after "no connection".
- **Stays online-only if:** `N < 2%` or `R ≥ 80%`. Autosave plus Retry is then enough.
- **Why not decide now:** offline write needs device storage of marks and attendance on possibly shared phones, conflict rules for assignment changes and finalization, and duplicate-submission handling (`PWA_STARTER_PLAN.md`, Later work). That cost is only worth paying against real failure data.

### 9.2 Push notifications (MOB-06)

| Ratio | Definition | Minimum denominator |
| --- | --- | --- |
| S, share of recorded notice-view events occurring on the publication day | `notice_view` with `age_bucket = same_day` ÷ all `notice_view` (guardian) | 100 notice-view events |
| P, share of guardian page-view events occurring on phones | guardian `page` `viewed` with `device = phone` ÷ guardian `page` `viewed` with a known device | 200 page-view events |
| I, share of iOS guardian page-view events occurring in the installed app (supporting) | guardian `page` `viewed` with `platform = ios` and `display = installed` ÷ guardian `page` `viewed` with `platform = ios` | 50 page-view events |

All three count **events, not people or notices**. One guardian who opens the same notice several times, or uses the portal far more than others, moves S, P and I more than an occasional user does. They describe what was recorded. They are not shares of guardians.

- **Trigger to open a push design gate:** `(S < 50%) AND (P ≥ 70%)`. Fewer than half of recorded notice-view events happen on the publication day, and at least 70% of guardian page-view events happen on phones.
- **Stays notices plus WhatsApp if:** `S ≥ 50%`. That suggests the existing WhatsApp alerts (ADR 0015) already bring guardians in.
- **Stated limitation:** S describes latency **only among notices that were viewed**. It cannot show notices that no guardian opened, or guardians who never sign in, and those are the people push would most help. Before any push build, the design gate must establish reach, either from office interviews or from a separately approved reach measurement. That measurement is outside this spec and needs its own ADR 0027 amendment.
- **Constraints for any later gate:** consent and audience rechecks equal to ADR 0015, and no permission prompt at install. iOS needs the installed app first, so read I alongside S.

### 9.3 Login convenience (MOB-04, G-06)

| Ratio | Definition | Minimum denominator |
| --- | --- | --- |
| E, expired-unsaved rate | teacher `session/expired_unsaved` ÷ teacher `sign_in/completed` | 200 successful teacher sign-ins |
| L, re-sign-in rate | teacher `session/relogin_after_expiry` ÷ teacher `sign_in/completed` | 200 successful teacher sign-ins |
| G, overall sign-in failure rate | `sign_in/failed` (always `public`) ÷ (`sign_in/failed` + `sign_in/completed` in all areas) | 300 sign-in attempts |
| T, throttle share (supporting) | `sign_in/throttled` ÷ `sign_in/failed` | 50 failures |

- **Trigger to open a login-convenience gate** (passkeys, device sign-in, or a longer idle limit for installed teacher apps, each needing a security review against ADR 0013): `(E > 5%) OR (L > 30%)`. E above 5% means more than one teacher sign-in in 20 is followed somewhere by a lost unsaved form.
- **Device split:** E and L are reported for all devices together. The sign-in POST and plain-form posts carry no client header, so their device is unknown. Phone context comes from the teacher `page` device share instead.
- **`multi` sign-ins** (users with more than one area) are reported separately and not added to the teacher denominator. Their expiries are recorded under the surface where they happened. A teacher-surface expiry by a `multi` user therefore counts in E's numerator but not its denominator, which slightly overstates E. The report shows `multi` sign-ins next to E, so the size of that effect is visible.
- **Guardian recovery (GUA-01):** failed sign-ins are never attributed to a role, so there is no guardian-only failure rate. A self-service recovery design opens only if `(G ≥ 20%) AND (the office confirms, by interview or from its own reset records, that guardian password resets are a recurring burden)`. The counters cannot tell a forgotten password from a mistyped one, or a guardian from a teacher.

### 9.4 Native apps (MOB-10)

This is a **meta-trigger**, not another ratio. It never fires on its own numbers. It asks whether a trigger defined elsewhere is met on one platform only, and whether a PWA can be shown to fall short there.

Only client-reported figures carry `platform`. N and R (9.1) and I (9.2) can be split by `android`, `ios` and `other`. E, L, G and S cannot, because they come from requests without a client header. So E, L, G and S can never activate this rule.

**Conditions that can activate it** (either one):

- **A, offline on one platform:** the 9.1 trigger `(N ≥ 2%) AND (R < 80%)` is met for platform X, using only X's events, with X's own 500 attempts and 20 retry taps reached. It is also *not met* on every other platform that reaches its own minimums there. A platform below its minimums counts as "no data", never as "not met".
- **B, iOS push reach:** the 9.2 trigger is met overall, `AND I < 20%`, with at least 50 iOS guardian page-view events. iOS web push needs the installed app, so a low installed share means a PWA push would miss most iOS guardians.

**Rule:** `(A OR B) AND (documented PWA capability testing shows the PWA cannot meet the need on that platform)`.

**What counts as documented testing:** the PWA Gate 2 device checklist, run on real devices of that platform. It records the device, OS version, browser and version, the date, the capability tested (for example background sync, or push without installation) and the observed result. An unperformed check is never recorded as passed. Without that record, the rule is not met, whatever the counters show.

- **Stays PWA if:** neither A nor B is met, or the documented testing shows the PWA can meet the need.

### 9.5 Admin phone coverage (G-04)

- **Evidence:** admin `page` `viewed` with `device = phone`, by `page_route`, including `other`.
- **Use:** rank allow-listed admin routes by phone views. Every route that averages at least 5 phone views a week over the window, and lacks a phone layout or `.erp-keep` table, gets a conversion task. This turns ADM-08 from "unproven" into a ranked list.
- **Allow-list review:** if `other` is 20% or more of admin phone views, review the allow-list. Adding routes needs a migration (OD-B14).

### 9.6 Marks entry (G-05 follow-up)

- **Evidence:**
  - `marks_entry` `completed` by `duration_bucket` within each `size_bucket` (minimum 20 completions per size bucket);
  - `invalid` ÷ `attempt` and `conflict` ÷ `attempt` (minimum 200 attempts).
- **Use:** informs whether bulk fill or other speed work (ACA-03) is worth a spec. It sets no trigger. It is only a "before and after" comparison if B3 runs before B1, which OD-B16 does not recommend.

## 10. Test plan

Tests are written before code in each PR. CI runs the full suite on PostgreSQL 16. Locally, run lint, the changed test files, and `--pattern="test_ui*.py"` if CSS changes. Per the project rule, run the full local suite for **B2** (model, migration and settings change) and for **B1** (middleware change). B3 needs only the changed tests.

### 10.1 PR B1: `core/tests/test_marks_autosave.py`

**Authorization and state:**

- non-HTMX POST gives 400; a POST without the base fields gives 400; GET gives 405;
- a teacher not assigned to the offering and Section gives 403; a guardian gives 403; anonymous is redirected (no HX header) or gets 401 (with HX header);
- the assigned teacher whose assignment ended yesterday gives 403;
- finalized assessment gives 409 and no write;
- assessment dated tomorrow gives 409 "Marks cannot be entered before the assessment date." and no write; the reply never says "finalized";
- an enrollment not on the date-effective roster gives 404 and no write;
- a teacher with admin permissions but no assignment gives 403.

**Saving:**

- MARKED with a valid score creates one result with `entered_by` set;
- ABSENT clears the score;
- score with blank status saves as MARKED (form rule);
- score above the maximum gives 422 and no write; score 0 saves;
- blank and blank gives 204 and no write;
- a request clearing the score of a saved MARKED row (defence in depth) gives 422 and the result is unchanged (OD-B5);
- `erp.js` source check: the marks sheet cancels the request (`htmx:confirm`) when the status is Marked and the score is empty, and shows `Enter a score`;
- equal value gives 200 and `updated_at` is unchanged (idempotent).

**Concurrency (OD-B1):**

- stale base gives 409 carrying only that row's server value; the result is unchanged;
- empty base against an existing row gives 409, so a stale page never overwrites a row it did not see;
- two first saves for one enrollment: the second gets 409 conflict, not 500, and no `IntegrityError` escapes;
- **lock order.** These run as a `TransactionTestCase` on PostgreSQL with two threads, each on its own connection, synchronised by a barrier. `lock_timeout` is set so that a deadlock fails fast instead of hanging.
  - Autosave against `finalize`: no deadlock, and whichever commits second sees the first's effect. If finalize commits first, the autosave gets 409 "finalized" at T3.
  - Autosave against the whole-form Save draft, on the same row and on different rows: no deadlock. If autosave runs second, it gets the T5 conflict when the form changed its row. If the form runs second, it keeps today's behaviour.
  - Autosave against autosave on the same row with the same base: one 200 and one 409.
  - The captured SQL of the autosave view shows `FOR UPDATE` on `core_assessment` before any lock on `core_studentresult`.
- **savepoint rule:** a forced `IntegrityError` inside T7 leaves the outer transaction usable. A query after it in the same transaction succeeds, and the view replies 409, not 500;
- finalize after every row is saved succeeds; a later autosave gets 409;
- the whole-form POST ignores the hidden base inputs and saves exactly as at `a78734c`.

**History and publication unchanged:**

- autosave never creates a `ResultCorrection` and never changes a `TermPublication` status;
- `StudentResult.correct` still refuses a DRAFT assessment.

**Replies:**

- the reply body contains no other enrollment's name or score;
- out-of-band counts equal `ResultEntryForm(...).counts()` after the save;
- fixed query count for rosters of 5 and 40.

**Page (`test_ui_teacher_marks.py` additions):**

- `erp.js` source check: the marks block never assigns `htmx.config.responseHandling`, and its `htmx:beforeSwap` listener is attached to the marks sheet, not to `document`; replies without `X-ERP-Row-Fragment` are never swapped; 401, network errors and 5xx swap nothing;
- every autosave fragment reply (200, 403, 404, 409, 422) carries `X-ERP-Row-Fragment: 1`; the CSRF failure view's 403 does not;
- `erp.js` source check: on the last row, the Enter handler triggers the row's save and focuses nothing outside the row when autosave is wired;
- rows carry `hx-post` to the autosave route, `hx-sync="this:queue last"`, `hx-include="this"`, and hidden `base_status_{pk}` and `base_score_{pk}` inputs holding the saved value (empty for unsaved rows);
- the 200 partial swaps the base inputs out of band; the 409 conflict partial carries the server value for Use and Keep;
- HTMX script loads only when the form is shown;
- Save draft is present in the HTML (fallback) and works without HX (existing `test_saving_still_works` stays green);
- `erp.js` source check: in the marks sheet, the Save draft handler calls `preventDefault()` and re-sends failed rows by triggering their `change`. No code path in JavaScript mode calls `form.submit()` or `requestSubmit()` for marks entry;
- a stale base re-sent through the fallback gets the 409 conflict, the same as any autosave (server test using the fallback's request shape);
- the live region and `[data-erp-autosave-state]` are present.

**Middleware (`test_session_errors_audit18.py` additions, OD-B3):**

- an expired session with `HX-Request: true` gets 401 JSON `{"error": "signed-out", "expired": "idle"}`, `no-store`, and is logged out;
- the same with `X-Requested-With: XMLHttpRequest`;
- a normal POST still gets the redirect with `unsaved=1` (existing test stays green);
- attendance autosave with an expired session gets 401, not 200;
- attendance bulk present with an expired session gets 401, because it sends `X-Requested-With`, so no row can show `✓ Saved`;
- an **anonymous** request (never signed in, or signed out in another tab) with `HX-Request` or `X-Requested-With` to a `teacher_required` route gets 401 with `"expired": null`, not a redirect. The same request without those headers still redirects;
- static test: every `fetch(` call in `static/js/erp.js` sends `X-Requested-With: XMLHttpRequest`.

**Manual (phone, 360 px and 390 px, real Android and iPhone where possible):** type and Next through 10 rows; airplane mode mid-entry, then Retry; two tabs with a conflict; let the session expire with the phone asleep, then wake it; admin finalizes mid-entry. Record outcomes and versions; do not mark unperformed checks as passed (PWA Gate 2 rule). Run `collectstatic` fresh before screenshots.

### 10.2 PR B2: `core/tests/test_usage_measurement.py`

- `record()` is a no-op when the setting is off, and when the request carries `Sec-GPC: 1`;
- `record()` creates a row with count 1; the same dimensions twice give count 2 (update path);
- creation race: with the row created between the update and the insert (patched), the insert's `IntegrityError` rolls back only its savepoint, and the retry update gives count 2;
- a forced `DatabaseError` inside `record()`, called **within** an outer `transaction.atomic()`, leaves the outer transaction usable: a later query succeeds, and the outer commit keeps its writes;
- an invalid enum value raises before the database; a raw insert of an invalid value is refused by the check constraint;
- column-use constraints: the database refuses each of these:
  - `page_route` on a non-`page` row;
  - `size_bucket` on `notice_view`;
  - a `notice_view` row with no `age_bucket`;
  - `duration_bucket` on a step other than `completed`;
  - `area='public'` on a teacher workflow;
- a route name outside the `page_route` allow-list is refused by the database, and the server maps it to `other` before writing;
- the model has no field that can hold free text (introspection test over field types and choices);
- `UsageCounter` is not in `admin.site._registry`;
- purge cutoff, under a patched `business_today`:
  - a row dated `today − 180` is deleted, and one dated `today − 179` is kept;
  - purge runs and deletes with `USAGE_MEASUREMENT_ENABLED=False`;
  - a second run deletes nothing;
- `usage_report` warns when a row older than the cutoff exists;
- the beacon: anonymous gets **401, not 302**; an expired session with `X-Requested-With` gets 401; missing CSRF gets 403; over 2 KB or over 20 events gets 400 and nothing is recorded; one bad field drops the whole batch; GPC header gives 204 and nothing recorded; setting off gives 204 and nothing recorded; rate limit drops above 200 per hour;
- the beacon does not move `SEEN_KEY` (the idle clock), but an expired session is still signed out;
- `X-ERP-Client` parsing accepts only enum values;
- no logger call receives beacon bodies or the header (patched logger asserts);
- a beacon whose `a` is not one of the user's areas, or whose `r` is neither allow-listed nor `other`, is dropped whole;
- relogin: a sign-in after a real expiry within 10 minutes records `relogin_after_expiry`, and the marker is gone afterwards. A sign-in with a forged `?expired=idle` and no marker records nothing. A marker older than 10 minutes records nothing and is still deleted. The marker holds only an integer;
- sign-in, throttle, expiry and relogin signals increment the expected rows with no user reference; a failed sign-in for a real guardian username is recorded as `area='public'`;
- route inventory includes `usage-beacon` with `require_POST` and `never_cache`.

### 10.3 PR B3

- each workflow in section 6 records only its listed steps: `started` and `completed` at the stated moments, with the right `duration_bucket` and `size_bucket` under a patched clock;
- hiding or leaving the page records nothing (no `abandoned` step exists);
- install: dismissing records only `dismissed`; `appinstalled` records only `installed`;
- session timer keys hold only numbers and are removed on completion; sign-out leaves none;
- `body` carries `data-erp-usage`, `data-erp-route` and `data-erp-area` only when measurement is enabled and the request had no `Sec-GPC: 1`;
- `erp.js` source check: the flush is guarded by `navigator.globalPrivacyControl` and sends `X-Requested-With`;
- `data-erp-route` is the route name, never the path: `/students/123/` renders `core:student-detail`, and a route outside the allow-list renders `other`;
- `notice_view` buckets by notice age and stores no notice reference;
- `usage_report`:
  - cells under 5 show `<5` after the `--area`, `--workflow` and `--device` filters and after weekly grouping;
  - secondary suppression hides a second cell when a total would reveal the first;
  - each section 9 ratio shows `n/a` below its minimum denominator;
  - `notice_view` is labelled "among notices that were viewed";
  - CSV mode follows the same rules;
- JS payload test (a template-level test reading the inline config): the event builder only uses enum constants.

## 11. Acceptance criteria

1. On marks entry with JavaScript, every row saves on change without pressing a button, and shows `Saving…`, `✓ Saved` or `Not saved: {reason}`. The page shows `All changes saved`, `Saving…` or `Changes not saved ({n})`.
2. Retry appears only for network, timeout and server failures. It is always a tap; nothing retries automatically or later.
3. Without JavaScript or HTMX, marks entry behaves exactly as it does at `a78734c`.
4. No user gains a power. Only the teacher whose assignment is effective today can save. Finalized assessments, future assessments and off-roster enrollments are refused with no write. Admin permissions alone do not allow autosave.
5. Autosave never creates a `ResultCorrection`, never changes a finalized result and never changes a publication.
6. A save based on an out-of-date value is refused with the current value shown and a choice for the teacher. No silent overwrite happens (OD-B1). With JavaScript, this covers the fallback Save draft too: it re-sends only failed rows through autosave with their bases, and never posts the whole form. The whole-form POST is used only without JavaScript or HTMX.
7. An expired or signed-out session during any background request (marks autosave, attendance autosave, bulk present, beacon) gets 401. It shows signed-out text wherever a status is shown, and never `✓ Saved` (OD-B3, F-1). Every `fetch` in `erp.js` sends `X-Requested-With`.
8. Autosave locks the assessment before any result row, matching the whole-form Save draft and `finalize`. Autosave follows the existing assessment-then-result lock order. This avoids introducing the inversion present in Revision 1 of this specification; concurrency tests protect that order. The PostgreSQL concurrency tests run against both paths, and no caught `IntegrityError` leaves a transaction aborted.
9. Leaving the page with unsaved or in-flight rows warns. Leaving with everything saved does not.
10. With `USAGE_MEASUREMENT_ENABLED=False` (the default), no beacon is sent and no counter row is written. With GPC, from the header or the browser signal, nothing is sent or recorded. The operations documentation says switching on requires written school approval.
11. When enabled, every stored row has only the dimensions in 5.4. Each comes from a fixed enum, the curated `page_route` list or the column-use rules, all enforced by database constraints. No row, log line or reply contains any item in 5.3. `UsageCounter` is not in Django admin.
12. Rows with `day <= today − 180` are deleted by the daily cron step, whether or not measurement is on, with no manual step.
13. Beacons do not keep a session alive, and a signed-out browser gets 401 from the beacon, never a redirect.
14. `usage_report` hides cells under 5 after every filter and grouping, applies secondary suppression, reports by ISO week, and prints `n/a` below each ratio's minimum. No web route exposes counters.
15. Every section 9 trigger is computable from stored counters alone, as written.
16. No service worker, offline storage, push, native code or fee code is added. `test_pwa_gate1` and the portal "no fee" tests stay green.
17. Route inventory and CI are green on the PR's latest commit before any merge. B1 has no migration, and B2 has exactly one.
18. Pages stay usable at 360 px with no new horizontal scroll, and every new control has an accessible name that includes the student where it acts on a row.

## 12. Risks

| Risk | Mitigation |
| --- | --- |
| A false "Saved" after session expiry or sign-out elsewhere (F-1), in attendance today and in marks after B1 | OD-B3 returns 401 to background requests from expired and anonymous sessions alike. Tests cover both sheets and bulk present. A static test keeps `X-Requested-With` on every `fetch`. |
| Conflict prompts confuse teachers | Conflicts need two devices or tabs on the same row, so they are rare. Wording is plain and names both values. The manual phone check covers it. |
| The refactor to a shared autosave helper breaks attendance | Keep attendance tests unchanged and green. If the shared helper is risky, copy the code (4.4). |
| Many small requests on slow networks | One request per changed row, only on change, queued per row. That is the same load pattern as attendance. |
| A lock-order inversion between autosave, the whole-form Save draft and finalize | One lock order everywhere: assessment first, then result rows (4.3). Autosave follows the existing assessment-then-result lock order. This avoids introducing the inversion present in Revision 1 of this specification; concurrency tests protect that order. PostgreSQL thread tests with `lock_timeout` cover autosave against both other paths, and a captured-SQL test pins the order. |
| The assessment lock serialises all saves for one assessment | Each autosave holds the lock only for one row's read-compare-write, and rosters are small. If contention ever shows, revisit with measurements, never by changing the lock order. |
| A stale page could overwrite newer marks through the fallback | In JavaScript mode the fallback re-sends failed rows through autosave with their bases, so OD-B1 holds for every save. Only the no-JavaScript whole-form POST keeps today's last-write-wins rule. That path is rare, unchanged from `a78734c`, and noted for a later decision. |
| A caught `IntegrityError` leaves a PostgreSQL transaction aborted | Rule: catch it only around a nested `transaction.atomic()` (4.3, 5.4). Tests force the error, then run a query in the same transaction. |
| Measurement read as surveillance by staff | Off by default; school notice; aggregate only; no person; operator-only access; ADR 0027 published in the repository. |
| Small schools give too little data for the thresholds | Every ratio has a minimum denominator. Below it, the trigger reads "not enough data" and interviews decide. |
| Client-reported failures are undercounted, because events are lost when a page closes before a flush, and an offline browser cannot report at all | N is labelled "observed network failures" and stated to undercount complete disconnects. A trigger met on observed failures is met in reality too. A miss, especially a narrow one, is checked with interviews about lost connections. |
| Counters cannot answer reach or per-person questions, such as who never viewed a notice or how many distinct people were affected | Section 9 states each limitation. Interviews decide those questions, or a separately approved measurement. |
| The daily purge silently stops (cron step removed or failing) | `usage_report` warns about rows past the cutoff. The switch-on checklist confirms the cron step. |
| Beacon counts forged by a signed-in user | Rate limit, strict enums, `area` checked against the user's own areas, and evidence used only as review triggers. |
| A future change adds a record ID to an event "just this once" | DB check constraints and the free-text introspection test fail the build. ADR 0027 needs amending first. |
| Route names change and break week-over-week `page` comparison | Renaming an allow-listed route needs a migration (OD-B14), so the rename and its effect on reports are reviewed in the same PR. |
| Wrong dates in parallel test runs | Patch `business_today` and clocks where each new module imports them (see the earlier date-capture note). |

Stop point: this specification is approved for implementation, one PR at a time, in the order set by OD-B16. No code, tests or migrations have been written yet.
