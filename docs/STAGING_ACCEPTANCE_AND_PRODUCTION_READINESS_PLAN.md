# Consolidated staging acceptance and production readiness — PLAN ONLY

**Status:** **PLAN ONLY, awaiting independent review.** This document and its PR are documentation only: nothing is deployed, no application code, template, test, setting or Railway resource is changed, and no hardening is started.
**Follows:** the Admin Desktop redesign (UI-D0, UI-D1-1 to UI-D1-6), implementation-complete and recorded in [the final gate ledger](ADMIN_DESKTOP_REDESIGN_FINAL_GATE_LEDGER.md). That ledger states the redesign is **not yet accepted on Railway staging and not approved for production.**
**Inputs:** the L1 to L11 deferred-work ledger (D1-6 plan section 13), ADRs 0004, 0013 to 0017, and the Phase 6/7 plans.

## 1. Why this plan exists and how it is split

Every UI-D1 gate was verified locally: PostgreSQL tests plus synthetic SQLite screenshots. Nothing proves the redesigned pages behave on the real deployment, with real browsers and assistive technology, against a restored copy of realistic data, with the real deployment and rollback path. Several known defects (L1, L10, L11) are **functional** and must be fixed by their own reviewed gates, not by UI work.

The work is therefore split into three phases with different rules:

| Phase | Purpose | May change application code? | Output |
| --- | --- | --- | --- |
| **S — Staging acceptance** | Prove the current `main` on Railway staging end to end; find defects | **No** (findings only) | Signed acceptance record and a defect list |
| **H — Production-hardening implementation** | Fix what S and the ledger require, one narrow gate at a time | Yes, per approved gate | Merged, tested fixes |
| **P — Production readiness** | Prove the hardened build can be run, observed, backed up and rolled back; go/no-go | No (configuration and runbooks only) | Go/no-go record |

Order: **S0 → S1 → S2 … S8 → decide H scope → H gates → S-re-run of affected journeys → P.** S may not be closed while a mandatory H item is open; P may not start until H is closed.

Ground rules for every phase: synthetic data only (never real students, guardians, phone numbers or documents in evidence); one gate = one draft PR or one dated evidence record, independently reviewed; no deployment, migration or data change without explicit approval for that step; failures are recorded, not worked around.

## 2. Phase S — Staging acceptance (no code changes)

### S0. Baseline and deployed-state check (first, mandatory)
The gate docs record every UI-D1 gate as "not deployed", but staging is configured to build from `main` and auto-deploy on merge. Before anything else, establish **what is actually running**:
- the deployed commit SHA, deployment time and migration state of `school-erp-web`, and whether auto-deploy is on;
- whether the cron service (`expire_import_batches`) matches the same commit;
- the environment variables present (names only), the Pango/PDF configuration, and that `DEBUG` is off;
- if auto-deploy is on, either record that staging already runs the redesign (then S proceeds on that build) or pause auto-deploy and deploy a named SHA deliberately. Whichever is chosen is recorded; this plan does not itself deploy.
Evidence: deployment list excerpt (SHA and time), settings checklist.

### S1. Deployment and rollback verification
- A deployment of a **named SHA** completes: build (`collectstatic`), pre-deploy `migrate`, start, health.
- Static assets resolve (stale-staticfiles risk: the hashed manifest is rebuilt; no unstyled pages).
- PDF generation works on the server (Pango present).
- **Rollback rehearsal:** redeploy the previous known-good deployment; confirm the app starts and old and new code both run against the current schema (the UI gates added no migrations; earlier migrations are checked in S7).
- The cron service runs and clears expired import payloads.
Evidence: deployment ids, timings, screenshots or log excerpts, rehearsal outcome.

### S2. End-to-end journeys (scripted, with synthetic users)
Each journey is a numbered script with expected results; every step is pass/fail with a screenshot of the decisive state.
- **Administrator:** sign in; Overview; school configuration; admit and enrol a Student (including the guardian access review step on a placement end and on deactivation); guardians and portal accounts; attendance registers, corrections and reports; assessments, finalization, correction; Term publication preview, confirm, stale, republish, withdraw; documents (Bonafide, Attendance summary, report card PDF); announcements (preview, publish, prepare WhatsApp in ASSIST mode, withdraw); the To send queue (open link, mark sent, dismiss); bulk import (upload, review, confirm with reviewed warnings, discard, expired); sign-in lockout clear.
- **Teacher:** sign in; My day; take and submit attendance; enter marks; teacher report card; confirm that no administrator page is reachable.
- **Guardian:** first sign-in and forced password change; children switcher; attendance; published report card and PDF; notices; confirm that unpublished or stale cards, other families' children and withdrawn notices are not visible.

### S3. Device, zoom and keyboard acceptance
- Widths 360, 390, 768, 992, 1024, 1280, 1440; no page-level horizontal overflow; wide tables scroll only inside labelled regions.
- Browser zoom 200% and 400% on desktop; phone text-size increase; the known shared top-bar overflow at about 195 CSS px (L9) is re-measured and recorded.
- Keyboard-only run of the administrator, teacher and guardian journeys: logical order, visible focus, every control reachable, no traps, scroll regions operable with arrow keys, skip link works.
- Real browsers: current Chrome, Firefox and Safari (desktop), Chrome on Android, Safari on iOS.
Evidence: matrix of page × width × browser with pass/fail, screenshots for failures.

### S4. Permissions and security boundary checks
- For each role (administrator, teacher, guardian, anonymous) and for the restricted administrator profiles used in the redesign (for example `view_*` only, `run_import` only, `send_notification` only, `issue_document` only), request every administrator route: expected 200, 302 or 403 per the matrix; no link shown that ends in a 403.
- Guardian boundary: no cross-family access by URL guessing; portal PDFs only for the current published snapshot.
- Sensitive screens: credential slips and resets send `no-store`; session behaviour after password change; login throttling and lockout clear.
- Notification safety: message text contains no marks, grades or correction reasons; text is escaped; no sending path exists (the ERP never sends).
- Security headers, cookie flags (`Secure`, `HttpOnly`, `SameSite`), CSRF on every POST, HTTPS redirect, `ALLOWED_HOSTS`, `DEBUG` off.
Evidence: route-by-role result table and a header/cookie capture.

### S5. Workflow acceptance (data-changing, on staging data only)
For each workflow: happy path, the main refusal, the audit record, and the unchanged invariant.
- **Import:** valid workbook, workbook with warnings (acknowledgment required), rejected workbook, records-changed failure, expiry, repeated confirm; the committed batch's audit event and counts; a 200-row workbook.
- **Attendance:** submit, correct, reports match the register; non-working days.
- **Assessment:** plan, mark, finalize, correct with reason; results and report cards reflect corrections.
- **Publication:** preview, confirm, stale after a correction, republish, withdraw; guardian visibility at each state.
- **Documents:** each issuance creates exactly one audited record with the next serial; GET never issues; PDF headers; report card list is current-published-only.
- **Notifications:** consent gates the queue; opt-out honoured; mark sent and dismiss recorded; the `to_send()` consent-skip behaviour observed and recorded.

### S6. Manual accessibility and screen-reader verification (closes L8's manual part)
- Screen readers: NVDA with Firefox and Chrome (Windows), VoiceOver with Safari (macOS and iOS), TalkBack with Chrome (Android).
- Representative pages per area (at least: list, form with errors, detail with status, table with a scroll region, confirmation panel, error summary, toolbar filter).
- Check: landmark and heading structure, one H1, table captions and scopes read correctly, status badges announce text, form errors announced and linked, accessible names of repeated controls (Send, Mark as sent, Dismiss, Clear, PDF), live regions and messages, focus after actions.
Evidence: dated notes per reader × page with defects filed.

### S7. Database backup, restore, monitoring and migration readiness
- **Backup/restore:** confirm the Postgres backup mechanism and schedule; take a backup; restore into a **separate** database; run `manage.py check`, `migrate --plan` (no unapplied surprises), and a smoke subset against the restored copy; record restore time. Restore is the only rollback for a bad data migration (earlier phases already assume this).
- **Migration readiness:** `makemigrations --check` is clean; list unapplied migrations between staging and the target SHA; confirm database-level triggers and constraints (append-only history, import batch freezing) survive a restore; time `migrate` on a restored copy.
- **Monitoring:** application logs retained and searchable; error reporting or alerting for 5xx and failed deploys; uptime check on a health URL; cron job success visibility; disk and database size alerts; who is notified and how.
- **Secrets and config:** rotate the staging `DJANGO_SECRET_KEY` (it appeared in a session log) and any other exposed secret; document required variables; confirm the demo account and demo data are removed or isolated before production.
Evidence: backup and restore log, migration plan output, monitoring screenshots, rotation record.

### S8. Triage of L1 to L11 and defects
Hold a triage review of the ledger and every defect found in S0 to S7. Output: a dated table assigning each item to **mandatory before production (Phase H)**, **launch-readiness decision (accept, schedule or defer with owner)**, or **backlog**, with the reason.

Recommended starting priority (to be confirmed at S8):

| Priority | Items |
| --- | --- |
| **Mandatory before production** | L1 (publish-only redirect to 403), L10 (announcement action redirects), L11 (import permission mismatch), L8 (manual accessibility and staging verification — this plan), L2 (security review of sensitive account screens) |
| **Launch-readiness decision** | L3 (confirmation workflows for Discard import, Dismiss message, Withdraw notice, Clear lockout, assessment Delete, grade-band Remove), L6 (import detail pagination, search, sorting; queue filter) |
| **Backlog** | L4, L5, L7, L9 |
| **Also review** | `to_send()` consent-skip during a GET; first-view issuance on a report card PDF GET; `view_attendanceentry` versus `view_attendanceregister` reconciliation |

### Phase S acceptance gates

| Gate | Pass criteria | Evidence required |
| --- | --- | --- |
| SA-0 | Deployed state known and recorded; auto-deploy decision made | S0 record |
| SA-1 | Named-SHA deploy succeeds; rollback rehearsal succeeds | S1 record |
| SA-2 | All three role journeys pass with no blocker defects | Scripted results and screenshots |
| SA-3 | Device, zoom and keyboard matrix passes; failures filed | Matrix |
| SA-4 | Route-by-role matrix matches expectations; security checklist passes | Tables and captures |
| SA-5 | All six workflows pass with audit records verified | Workflow results |
| SA-6 | Screen-reader pass complete; no unresolved blocker | Dated notes |
| SA-7 | Backup restored and verified; migrations clean; monitoring in place; secrets rotated | S7 record |
| SA-8 | Triage complete; mandatory list agreed | Triage table |

**S closes** when SA-0 to SA-8 are accepted by the reviewer and any blocker defect has a Phase H gate or an explicit accepted waiver.

## 3. Phase H — Production-hardening implementation (separate gates, after S8)

Not part of this PR. Each item is its own narrowly scoped, independently reviewed draft PR with tests; none is started until S8 assigns it.

### H-A. Post-action permission mismatches (mandatory)
Three sibling defects share one cause: an action view needs one permission, but redirects to a page needing another, so a legitimate user lands on a 403 after the action succeeded.
- **L1** `publication_withdraw` → Publication detail needs `view_termpublication` (publish-only users).
- **L10** announcement Create (confirm), Prepare and Withdraw → Announcement detail needs `view_announcement`.
- **L11** import upload, commit and discard → Import detail needs `view_importbatch` (and template download needs only `run_import`).

Decision to take before implementation (review item, not decided here): either **(a)** make the post-action redirect permission-aware (redirect to a page the actor can open, with the success message), or **(b)** align the permission groups so that the action permission always implies the view permission. Option (a) changes views only; option (b) changes authorization data and needs a migration plan. Whichever is chosen applies consistently to all three, with tests for every permission combination, and a regression test that every mutating route's redirect target is reachable by the permission that reaches the route. Behaviour that must not change: audit events, atomicity, validation and messages.

### H-B. Sensitive account screens (L2)
Credential slips and the reset, username, revoke, reactivate and deactivate confirmations: security review, `no-store` and print behaviour verified, then the shared-pattern gate.

### H-C. Confirmation workflows (L3), if accepted at S8
Real confirmation pages for Discard import, Dismiss message, Withdraw notice, Clear lockout, assessment Delete and grade-band Remove (new views, routes, tests; the interim consequence text is replaced).

### H-D. Smaller reviewed items
`to_send()` consent-skip on GET; report card PDF first-view issuance (document the invariant or make issuance explicit); attendance permission reconciliation; any S-phase defects.

### Phase H acceptance gates

| Gate | Pass criteria | Evidence required |
| --- | --- | --- |
| HA-n (per item) | Narrow diff, tests first, full PostgreSQL suite `--parallel 4` green, permission matrix tests, no unrelated change | Draft PR with tests, test counts, review sign-off |
| HA-regress | After H closes, the S2, S4 and S5 scripts affected by each fix are re-run on staging | Re-run records |

## 4. Phase P — Production readiness (after H)

- **Environment:** create the production Railway environment (it does not exist yet) from documented configuration; separate database, secrets and domain; `DEBUG` off; `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, secure cookies, HSTS decision; Pango for PDFs; the `expire_import_batches` cron service; portal base URL set; school record, letterhead and notification mode configured.
- **Data:** no demo data; initial administrator accounts and permission groups created by a reviewed procedure; password and first-login policy confirmed; one-time guardian session reset communicated (Phase 6 note).
- **Deploy and rollback runbook:** backup immediately before every deploy; deploy of a named SHA; smoke script; rollback by redeploying the previous deployment, and restore-from-backup for data problems; named owner and escalation contacts.
- **Operations:** monitoring and alert routing live; log retention; backup schedule and a **dated restore test**; capacity and cost review; support process for guardians and staff.
- **Go/no-go record:** all mandatory H items merged; SA-0 to SA-8 and HA gates accepted; open ledger rows each have an owner and a decision; privacy and data-protection sign-off for real student and guardian data; rollback rehearsed on the production-shaped environment.

### Phase P acceptance gates

| Gate | Pass criteria | Evidence required |
| --- | --- | --- |
| PR-1 | Production environment built from documentation only; smoke script passes | Config checklist and smoke output |
| PR-2 | Runbook rehearsed: deploy, rollback and restore | Rehearsal record with timings |
| PR-3 | Monitoring, alerting and backup verified with a real alert and a real restore | Screenshots and logs |
| PR-4 | Go/no-go review held; every open item has an owner and decision | Signed go/no-go record |

## 5. Evidence conventions

- Location: `docs/staging-acceptance/<gate>/` for Phase S, `docs/production-readiness/<gate>/` for Phase P, each with a README that lists date, SHA under test, tester, environment and results.
- Screenshots use synthetic data and carry the viewport width in the file name; no real contact details or credentials appear (mask or avoid).
- Test results quote the exact command and counts. Manual results record date, browser or assistive technology version and tester.
- Defects are filed with the step, expected and observed result, and a priority; each is closed by a Phase H gate, a waiver with an owner, or a backlog entry.

## 6. Out of scope

Any change to application behaviour, deployment of any gate, new features (including pagination, search, new import formats, API or SMS delivery), the Guardian Portal redesign, and production data migration.

## 7. Decisions requested at review

1. Approve the three-phase split and the rule that S makes no code changes.
2. Confirm the recommended priority table (mandatory: L1, L2, L8, L10, L11; decision: L3, L6).
3. Choose the approach for H-A (permission-aware redirect versus aligned permissions), or ask for an options paper first.
4. Confirm browser and assistive-technology coverage in S3 and S6.
5. Decide how S0 resolves the auto-deploy question (accept that staging already runs `main`, or pause auto-deploy and deploy named SHAs).
