# UI-D1-6 — Admin Communication and Operations

**Status:** **PLAN ONLY — awaiting planning review.** This document and its PR are documentation only; no application code, template, CSS or test is changed and nothing is implemented. The audit behind it is read-only.
**Planning branch:** `plan/ui-admin-desktop-d1-6-communication-operations`, based on `main` `c52ac4b` (UI-D1-5 closed).
**Parent:** `docs/ADMIN_DESKTOP_D1_PLAN.md` (D1-6). **Binding design:** `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, and the accepted D0 / D1-3 / D1-4 / D1-5 patterns (page header, toolbar, panel, status badge, labelled table region, permission-aware breadcrumbs, error summary).
**Domain authority:** ADR 0015 (notifications, consent and delivery modes), ADR 0016 (issued documents and PDF generation), ADR 0017 (bulk import through applicant progression), ADR 0013 (guardian accounts, access grants and sign-in security), ADR 0014 (what guardians see; report-card PDFs come only from the current published snapshot), ADR 0004 (authorization foundation).

D1-6 is, like D1-3, D1-4 and D1-5, a **presentation-only** programme. It brings the remaining Communication and Operations administrator pages into the accepted admin-desktop system. It adds **no new send path, issuance path, import rule, report, export, permission, route or workflow**, and it changes no delivery, issuance, validation or audit behaviour. It is split into five independent gates (section 8), each its own draft PR and review, in risk-ascending order.

## 1. Scope

**In scope (administrator pages):**

| Area | Pages |
| --- | --- |
| Security operations | Sign-in lockouts; the Student guardian-access review step (`student_access_review`) |
| Announcements | list, new-notice form, preview, detail (prepare and withdraw controls) |
| Documents | index with recent issuances, Bonafide form, Attendance summary (preview and issue), Report card PDF list |
| Notification queue | "To send" (ASSIST delivery) |
| Bulk imports | list, upload, detail (preview, errors, warnings, confirm and discard) |

**Out of scope (and why):**

- **Guardian Portal** (`templates/portal/*`, `core/portal*.py`): a separate area (ADR 0013/0014). Untouched; its tests must pass unmodified. The portal shares only the partials `_empty.html`, `_messages.html` and `_account_menu.html` with the admin shell, so **those must not change** in any D1-6 gate.
- **Teacher pages:** none of the D1-6 routes is a teacher route (all use `administrator_required`), and no teacher template includes a D1-6 template (verified by search).
- **Sensitive account screens:** the one-time credential slips (`guardian_credential_slip`, `teacher_credential_slip`) and the reset, username, revoke, reactivate and deactivate confirmations. They handle one-time secrets and print layout; D1-3 already excluded them and asked for their own security review (decision F2).
- **Residual configuration forms** (school, class/grade, section, subject, Term, offering, calendar, class-teacher, teacher-assignment, copy-assignments and timetable delete pages): the parent plan places them under D1-2 / D1-3 follow-ups, not D1-6 (decision F3).
- **"Reporting":** closed by D1-4C (attendance reports) and D1-5C (result reports). No results export exists and none is added.
- **Term remarks:** shared with class teachers; excluded since D1-5 (E2).
- No models, migrations, services, delivery code, PDF engine, import parser, authorization decorators, routes, new exports, pagination or search.

## 2. Audited inventory (read at `c52ac4b`)

| Page | Route name | Permission | Template (lines) | Notes |
| --- | --- | --- | --- | --- |
| Announcements list | `announcement-list` | `view_announcement` (New notice: `add_announcement`) | `announcement_list.html` (24) | bare `h1`, plain table |
| New notice form | `announcement-create` (GET) | `add_announcement` | `announcement_form.html` (17) | shared JS contract (below) |
| Notice preview | `announcement-create` (POST, no `confirm`) | `add_announcement` | `announcement_preview.html` (29) + `_announcement_hidden.html` (5) | already has the page header; two POST forms with replayed hidden fields |
| Notice detail | `announcement-detail` | `view_announcement` | `announcement_detail.html` (27) | Prepare WhatsApp (`send_notification`, ASSIST mode only); Withdraw (`withdraw_announcement`) |
| Prepare / withdraw | `announcement-prepare`, `announcement-withdraw` | `send_notification`, `withdraw_announcement` | POST only | `require_POST`; withdraw requires a reason (service validates) |
| To send | `notifications-to-send` | `send_notification` | `notifications_to_send.html` (46) | card stack; the sidebar item carries a waiting count |
| Mark sent / dismiss | `notification-mark-sent`, `notification-dismiss` | `send_notification` | POST only | dismiss requires a reason |
| Documents index | `document-index` | `issue_document` | `document_index.html` (27) | already has the header; "Recently issued" table, 50 rows |
| Bonafide | `bonafide-create` | `issue_document` | `bonafide_form.html` (12) | `form.as_p`; success redirects to the PDF |
| Attendance summary | `attendance-summary` | `issue_document` | `attendance_summary.html` (32) | GET builds a preview; POST issues a serial-numbered PDF |
| Report card PDFs | `document-report-cards` | `issue_document` | `document_report_cards.html` (23) | lists `visible_publications(student)` |
| Document PDF | `document-pdf`, `document-report-card-pdf` | `issue_document` | no template | inline PDF response; a non-current report card redirects with an error message |
| Imports list | `import-list` | `view_importbatch` (New import and template: `run_import`) | `import_list.html` (32) | plain table, status as text; sidebar item "Import" (Admissions) |
| Import upload | `import-upload` | `run_import` | `import_upload.html` (12) | multipart; `form.as_p` |
| Import detail | `import-detail` | `view_importbatch` (confirm and discard: `run_import`) | `import_detail.html` (103) | preview, live errors, new warnings, row errors and warnings, confirm and discard |
| Commit / discard / CSV / template | `import-commit`, `import-discard`, `import-issues-csv`, `import-template` | `run_import` / `view_importbatch` | POST / downloads | atomic commit; CSV neutralizes formula-leading cells |
| Sign-in lockouts | `login-lockouts` | `accounts.clear_login_lockout` | `login_lockouts.html` (13) | `ul` with an inline Clear form per username |
| Student access review step | rendered by the Student status flows via `_access_review_page` | the originating Student status route's permission | `student_access_review.html` (33) | one template for several flows; replays the originating POST in hidden fields |
| Guardian access reviews | `guardian-access-reviews` | `view_guardianaccessreview` | `guardian_access_reviews.html` (48) | **already migrated in D1-3C**; do not rework |

Entry points today (unchanged by this programme): the sidebar groups **Admissions** (Import), **Daily** (Announcements, To send, Documents), **Results** (Stale publications) and **Access and security** (Access reviews, Sign-in lockouts). `core/breadcrumbs.py` has rules only for `announcement-create` and `announcement-detail`; none of the other D1-6 routes shows a trail or keeps a sidebar item active.

Forms (`core/forms.py`): `AnnouncementForm`, `BonafideForm`, `AttendanceSummaryForm`, `DocumentStudentForm`, `ImportUploadForm`. **None uses `FieldAccessibilityMixin`**, so, as in D1-4 and D1-5, automatic focus to the first invalid field is not available (a recorded gap; forms are out of scope).

Existing tests that pin behaviour: `test_phase7_{notifications,alerts,announcements,documents,import}.py`, `test_ui_admin_phase3b.py` (announcement preview and conditional fields), `test_ui_admin_phase3e.py` (empty-state actions), `test_ui_admin_phase3f.py`, `test_ui_admin_desktop_d1_3c_access_reviews.py`, the Phase 6 suites and the D1 CSS-scoping tests.

## 3. Rules that must not change

### 3.1 Announcements (ADR 0015)

- **Form, then preview, then publish.** Nothing is stored until `confirm` is posted; confirm re-validates everything the preview carried in hidden fields. `edit` returns to the form without validation noise. The hidden field names (`title`, `body`, `audience`, `class_grade`, `section`, `confirm`, `edit`) and the `_announcement_hidden.html` replay are part of the contract.
- **Published notices cannot be edited**; to correct one the administrator withdraws and republishes. Withdrawal requires a reason and is recorded.
- **Portal first, WhatsApp separate.** Publishing makes the notice visible in the portal; "Prepare WhatsApp messages" is a separate explicit step, shown only in ASSIST mode and only with `send_notification`. The audience counts (guardians with portal access, opted in to WhatsApp) come from the existing service and must not be recomputed in a template.
- **JavaScript contracts** in `static/js/erp.js`: `data-erp-audience-form` / `data-erp-audience-field` (show the Class or Section selector for its audience and disable hidden controls so they are not submitted; both stay visible without JS) and `data-erp-once` (disable the Publish button after the first submit so a double click cannot publish twice). These attributes, the radio `name="audience"` and the field names must survive, and the page must work with JavaScript off.

### 3.2 Notification queue (ADR 0015)

- **The ERP never sends.** "Send on WhatsApp" is a click-to-chat link (`target="_blank" rel="noopener"`) built by the existing service; the staff member sends it from their own WhatsApp and confirms with "Mark as sent". No network call is added.
- **Message text is exactly what `notifications.render` returns** (first name, date and portal link at most; never marks, grades, reasons or correction details). The template displays `row.text` and must not reformat, truncate or add to it.
- **Consent gates the queue:** no consent means no entry; opt-out is honoured at once. Dismiss requires a reason; mark-sent and dismiss are POST only and recorded with the actor.
- The portal-only and missing-portal-address warnings and the "Phone number missing or not usable" state are shown exactly as today (with their links).

### 3.3 Documents (ADR 0016)

- **Issuing is a POST that creates an append-only `IssuedDocument`** (serial per type and Academic Year, immutable snapshot, content hash, security event). A GET never issues. Bonafide uses the current enrollment; the Attendance summary uses submitted, eligible entries only (Phase 2 rules).
- **Report card PDFs come only from the current PUBLISHED snapshot.** The list is `visible_publications(student)`, and its membership must not change (stale, superseded and withdrawn versions produce no PDF). A non-current issued report card redirects to the index with the existing error message.
- Success redirects to the inline PDF response; PDF responses and headers are untouched. Documents never render PDF content inside an HTML page.

### 3.4 Bulk imports (ADR 0017)

- **Flow:** upload, parse, validate (dry run), preview with row-level errors, explicit confirmation, one atomic commit. The batch succeeds entirely or not at all; a file with errors is REJECTED and imports nothing.
- **Confirmation contract:** Confirm is hidden when `live_errors` exist (the school's records changed since the check); when warnings (recorded or new) exist, `reviewed_warnings=yes` is required and the checkbox stays `required`; a checked file can be confirmed within 24 hours of upload; Discard is a separate POST.
- **Safety rules** (size and row limits, formula cells rejected, `.xlsm` rejected, exported CSV cells starting with `=`, `+`, `-` or `@` neutralized) are service behaviour and are not touched. Existing Guardians are reused only on a normalized phone-and-name match; nothing is auto-merged; Student name plus date of birth is flagged for review.
- `import_detail` renders **all** error, warning and preview rows with no pagination; D1-6 must not add pagination, search or sorting (functional changes).

### 3.5 Security operations (ADR 0013)

- **Sign-in lockouts:** Clear is a POST per username, recorded as a security event, and allowed only with `accounts.clear_login_lockout`. Lockouts expire on their own. No bulk "clear all" is added.
- **Student access review step:** an explicit decision per guardian (radio `decision_<grant pk>`), an optional note (`access_note`), the marker `access_review=1`, and the originating POST replayed as hidden fields. Nothing is saved until every guardian is decided. This template is rendered by several Student status flows (section 4), so it must be tested through each.

## 4. Shared-template and dependency hazards

- **`student_access_review.html`** is rendered by `_access_review_page` for several Student flows with different `action` URLs and hidden-field sets. Any change needs a test per originating flow, and the hidden fields must round-trip byte for byte.
- **`announcement_form.html`** carries the audience JS contract; **`_announcement_hidden.html`** is included by the preview only.
- **Report card PDF list** depends on D1-5D publication states; the D1-5D follow-up (publish-only redirect after withdrawal) is independent and still mandatory before production.
- **Shell and partials:** `partials/_empty.html`, `_messages.html`, `_account_menu.html` are shared with the Guardian Portal and must not change; `_form_field.html`, `_form_error_summary.html`, `_status_badge.html` and `_page_header.html` are reused as they are.
- **No teacher or guardian template includes any D1-6 template.** Guardians see announcements only through `templates/portal/*` (separate); every D1-6 gate must still prove, by before/after response comparison, that portal responses are unchanged.
- **Legacy strings pinned by existing tests** and therefore kept verbatim: "No notices yet." with its "Publish a notice" action, "No imports yet." with "Start an import", "No usernames are locked.", the empty-state action class assertions in `test_ui_admin_phase3e.py`, and the absence of the empty-state action button on informational lists.
- **Sidebar waiting count** for "To send" comes from the shell (`queue_counts`) and is unchanged.

## 5. UI/UX gaps found

Observable from the templates; none needs a business change.

1. **Page identity.** Twelve of the fifteen D1-6 templates use a bare `h1` (only the preview, the Documents index and Guardian access reviews use the shared header).
2. **Navigation context.** No breadcrumb rules for notifications, documents, imports or lockouts; only `announcement-create` and `-detail` have rules (both should be re-checked for same-model `pk` use). Sidebar items exist but do not stay active on deep pages.
3. **Tables.** Announcements, Imports, Documents "Recently issued" and the three Import detail tables have no `caption`, `scope` or labelled scroll region; Import detail can hold unbounded rows and widens the page on phones.
4. **Status.** "Live / Withdrawn" and the import status ("Validated — awaiting confirmation", "Rejected — has errors", "Imported", "Discarded", "Expired", "Failed at import") are plain text, not badges.
5. **Announcement detail.** Inline `style` boxes, bare action forms; the withdraw reason input has a visually hidden label but only a placeholder cue; counts are prose.
6. **Notification queue.** A stack of Bootstrap cards with up to four controls per message; "Phone number missing or not usable" is red text only (it has text, but no badge); the dismiss reason input is a small placeholder-only field.
7. **Forms.** Bonafide, the Attendance-summary filter, the report-card Student picker and the import upload use `form.as_p`: no error summary, no required legend, no field association.
8. **Imports.** The warnings checkbox and the Confirm / Discard pair sit in a bare flex row; Discard is an unconfirmed POST; error and warning headings use colour utility classes (`text-danger`, `text-warning`) as the only severity cue.
9. **Lockouts.** A `ul` of usernames with an inline Clear button whose accessible name does not include the username.
10. **Access review step.** Radios sit in table cells with no fieldset or legend naming the guardian.
11. **Document links.** "PDF" links have non-descriptive names; the report-card link list is unstructured.
12. **Errors and accessibility.** No summaries; the audience radio group relies on `as_field_group` rendering that must keep its legend.

## 6. Permission boundaries and display gating (must not change)

Existing view decorators are authoritative (section 2). Display gating only hides links the viewer cannot use; where a destination is not permitted the text stays but is **not a link**.

| Link / control | Shown when (existing, unchanged) |
| --- | --- |
| "New notice" and the empty-state "Publish a notice" | `add_announcement` |
| "Prepare WhatsApp messages" | `send_notification` and ASSIST mode, notice not withdrawn |
| Withdraw (notice) | `withdraw_announcement`, notice not withdrawn |
| To send actions (Send, Mark as sent, Dismiss) | page requires `send_notification` |
| Documents: issue and PDF links | page requires `issue_document` |
| "Download template", "New import", "Start an import" | `run_import` |
| Confirm import / Discard | batch pending and `run_import` (Confirm also needs no live errors) |
| Clear (lockout) | page requires `accounts.clear_login_lockout` |
| "School settings" link in the portal-only warning | existing link (destination `school-detail`); gate on `view_school` if the destination would 403 for the viewer |
| "Update the guardian" link in a missing-phone row | existing link (`guardian-edit`); gate on its own permission if it would 403 |

Rules for the new chrome: header actions and breadcrumb parents reuse the **destination's** permission (as in D1-4C and D1-5); the Overview crumb needs `core.view_school`; users without `view_school` get no admin sidebar or trail. **Any link the old page showed unconditionally to a destination with a different permission is gated by that destination's permission** (the lesson of the D1-5D Withdraw correction): audit each header action, Cancel and back link in every gate. **No page gains an action, link or data field its viewer could not already use.** Teachers, Guardians and anonymous users keep today's 403 / redirect outcomes for every route in section 2.

## 7. Reusable components and lessons from D1-4 and D1-5

Reuse, do not reinvent: `partials/_page_header.html`; `erp-toolbar erp-toolbar--inline` (+ the scoped one-row modifier pattern); `erp-panel` with `erp-panel-head`; `partials/_status_badge.html` (tones `draft`, `pending`, `submitted`, `finalized`, `published`, `stale`, `inactive`, `info`, `revoked`, neutral); labelled `erp-table-scroll` regions with `caption` and `scope`; `partials/_form_field.html` plus `partials/_form_required_legend.html` and `partials/_form_error_summary.html`; `partials/_empty.html`; permission-aware `Crumb(perm=...)` rules; the `erp-keep` + scoped padding approach; the description-list panel used on detail pages.

Carried lessons:

- **Breadcrumb ids:** `Crumb.uses_pk` only for a parent of the **same model** as the current route's pk (import detail → imports list needs no id; notice detail → announcements list needs no id; notice-withdraw and prepare are POST-only). Test with distinct ids.
- **Legacy strings and element hooks** asserted by existing tests are kept verbatim; keep a legacy-compatible text and add accessible names with `aria-label` or visually hidden text (as with the D1-5B "Correct" link).
- **Gate every back link, Cancel and header action by the destination's permission.**
- **Status is never colour-only**; use a badge with text. Severity headings (errors, warnings) get a badge or text label, not colour alone.
- **Scoped CSS** goes before the `/* UI-D1-4B` marker and must not use `overflow-wrap: anywhere`; one block per gate.
- **Evidence:** synthetic data only; a throwaway SQLite database seeded through the real services; the full PostgreSQL suite on the final head.
- **Do not change** the interim unconfirmed POSTs (Discard, Dismiss, Withdraw notice, Clear lockout): consequence text only, confirmation pages as a launch-readiness follow-up (decision F6).

## 8. Proposed implementation gates

Five independent draft PRs, each stopping for design review. Order is risk-ascending (decision F1).

### D1-6A — Security operations (lockouts and the Student access review step)

**Pages:** `login_lockouts.html`, `student_access_review.html`. **Also:** breadcrumb rule for `login-lockouts` (sidebar section "Access and security").
**Contract:** header with purpose text; lockouts as a labelled table (Username, Action) with the **username in the Clear button's accessible name**, the existing explanation of the 5 / 20 / 15-minute rule and "Lockouts expire on their own; clearing one is recorded", the legacy empty text "No usernames are locked." kept; consequence text beside Clear (interim). The access review step: header naming the Student and trigger, a description-list context, one **fieldset with a legend per guardian** around the decision radios (same `name="decision_<pk>"`, values and `required`), the note field with the same `name="access_note"`, the same hidden-field replay and `access_review=1`, Cancel gated by `view_student`.
**Tests:** structure; Clear POST unchanged (URL, fields, recorded event, permission); empty text; every originating Student flow still round-trips its hidden fields and decisions (one test per flow); decisions required; no Student change is saved until every guardian is decided; breadcrumbs matrix; teacher and guardian 403.

### D1-6B — Announcements

**Pages:** `announcement_list.html`, `announcement_form.html`, `announcement_preview.html`, `announcement_detail.html` (+ `_announcement_hidden.html` untouched). **Also:** breadcrumb rules (`announcement-list`, `-create`, `-detail`; review the existing two).
**Contract:** list with header, gated "New notice", a labelled table (Published, Title, Audience, Status badge Live / Withdrawn, with `caption` and `scope`), legacy empty state and action; form through `_form_field.html` with required legend and error summary, keeping the audience group, `data-erp-audience-form` / `-field` attributes and the field names; preview with the audience counts as facts, the "Nobody can see this notice yet" notice as a labelled status, the two POST forms unchanged (hidden fields, `confirm`, `edit`, `data-erp-once`); detail with a status badge, facts, the notice body in a panel (no inline style), the counts, and gated actions: Prepare WhatsApp (ASSIST and `send_notification`) and Withdraw (reason field with a visible label, consequence text "Guardians stop seeing it at once").
**Tests:** the whole form → preview → confirm round trip (hidden fields, `edit` refill, confirm re-validation, double-submit attribute present); audience JS hooks and the no-JS rendering; counts equal `announcements` service values; withdraw reason required; prepare gating by mode and permission; `test_ui_admin_phase3b`, `test_ui_admin_phase3e` and `test_phase7_announcements` unmodified; portal responses byte-identical before and after.

### D1-6C — Documents

**Pages:** `document_index.html`, `bonafide_form.html`, `attendance_summary.html`, `document_report_cards.html`. **Also:** breadcrumb rules (`document-index`, `bonafide-create`, `attendance-summary`, `document-report-cards`).
**Contract:** index with the three document types as a list of described links and "Recently issued" as a labelled table (Serial, Type, Student, Issued, a **descriptive PDF link** that names the serial); Bonafide form with the serial-number consequence ("a serial number is assigned and the PDF opens next"); Attendance summary as a toolbar (GET filter) plus the summary table region with `scope` and the totals row, and the issue POST as its own clearly labelled step with the same hidden fields; Report card list with the Student picker toolbar, a table of current published report cards (Term, Academic Year, PDF link) and the existing empty text.
**Tests:** issuance unchanged (exactly one `IssuedDocument` per POST, none on GET, serial and security event); PDF links point to the same routes and responses (status, content type, `Content-Disposition`); the report card list equals `visible_publications` for every publication state (stale, superseded and withdrawn are absent); a non-current issued report card still redirects with the existing message; `test_phase7_documents` unmodified. **Screenshots never open or render a PDF** and use invented Students only.

### D1-6D — Notification queue

**Pages:** `notifications_to_send.html`. **Also:** breadcrumb rule for `notifications-to-send`.
**Contract:** header with the waiting and sent-today counts as facts; the portal-only and missing-portal-address warnings as labelled notices keeping their links (gated); one record per message (guardian, type and child first name, prepared time, a status badge such as "Ready to send" or "Phone number missing") with the message text **displayed exactly as `row.text`** in a quoted block; the Send link keeps `target="_blank" rel="noopener"`, Mark as sent and Dismiss keep their POSTs, field names, `required` reason and recorded actor; consequence text beside Dismiss ("The message will not be sent; the reason is recorded"); "Sent today" as a labelled table with the sender; the legacy empty state through `partials/_empty.html`.
**Tests:** every control's URL, method, CSRF and field name; message text identical to the service output for each notification type, with no marks, grades, reasons or correction details; consent and mode gating (no entry without consent; portal-only banner); missing-phone state; mark-sent and dismiss recorded; GET never writes; `test_phase7_notifications` and `test_phase7_alerts` unmodified; teacher and guardian 403.

### D1-6E — Bulk imports (highest risk)

**Pages:** `import_list.html`, `import_upload.html`, `import_detail.html`. **Also:** breadcrumb rules (`import-list`, `import-upload`, `import-detail`; sidebar section: the existing "Import" item).
**Contract:** list with header, gated actions, a labelled table with a **status badge** for each status (Validated, Rejected, Imported, Discarded, Expired, Failed) and the legacy empty state; upload form through `_form_field.html` with the file input, required legend, error summary and a short "what happens next" note; detail with a header carrying the status badge, a facts panel, the committed or rejected summary as a labelled status, the **Preview** as a summary strip (the existing counts) plus a labelled table region, the live-errors and new-warnings notices keeping their text, **Errors and Warnings tables as labelled regions with `caption`, `scope` and a severity badge**, the CSV link, and the Confirm / Discard actions grouped in a panel: the warnings checkbox stays `required` with `name="reviewed_warnings" value="yes"`, Confirm stays hidden when live errors exist, Discard keeps its POST with consequence text ("Nothing is imported and the file is discarded"), and the 24-hour note is kept.
**Tests:** the full state matrix (VALIDATED with and without warnings, with live errors, REJECTED, COMMITTED, DISCARDED, EXPIRED, FAILED); Confirm gating and the `reviewed_warnings` requirement; commit and discard POST behaviour and atomicity unchanged; CSV download unchanged; row tables render every row (no pagination added) with 200-row and long-text fixtures; permission matrix (`view_importbatch` versus `run_import`); `test_phase7_import` unmodified.

### Cross-gate requirements

- **Breadcrumbs:** each gate adds its routes to `core/breadcrumbs.py` with the destination's permission on every parent crumb and same-model `pk` reuse only; tests cover the `view_school` and per-parent permission matrix, as in D1-4C and D1-5.
- **Responsive and accessible:** no page-level horizontal overflow at 360, 390, 768, 992, 1024, 1280, 1440px; wide tables scroll only inside labelled, keyboard-focusable regions; one H1; `caption` and `scope` on every table; status never colour-only; errors summarised and associated through the shared partials; works with JavaScript off; no JavaScript added or changed.
- **Evidence:** synthetic data only (invented Students, Guardians, phone numbers and files; no real contact details); before and after screenshots for every state in the gate, including restricted-permission users and error states; measurements and README under `docs/ui-reviews/ui-d1-6<x>/`; focused tests, the existing Phase 6 and 7 modules, then the full PostgreSQL suite with `--parallel 4` on the final head.
- **Forbidden in every gate:** `core/models.py`, migrations, `core/views.py`, `core/forms.py`, `core/announcement_views.py`, `core/notification_views.py`, `core/document_views.py`, `core/import_views.py`, the `announcements`, `notifications`, `documents`, `imports` and `guardian_access` services, `accounts` security code, authorization decorators and routes, the PDF engine and responses, `static/js/erp.js`, the Guardian Portal and teacher templates, the shared partials `_empty`, `_messages`, `_account_menu`, any new export, pagination, search, automation or delivery mode, and deployment.

## 9. Testing and acceptance (every gate)

| Check | Pass condition |
| --- | --- |
| Context invariance | Rendered contexts identical before and after for every state the gate touches; no per-row query growth |
| Mutations unchanged | Every POST keeps its URL, method, CSRF, field names, validation and redirect; GETs never write |
| Delivery, issuance, import and audit safeguards | Section 3 holds: no send path added; issuance only by POST; import confirmation, warnings review, atomic commit and 24-hour rule intact; every recorded event still recorded |
| Permissions | Section 6 matrix holds; anonymous redirects; teacher and guardian 403 where today; no link shown that the viewer cannot open |
| Guardian boundary | Portal responses compared before and after are identical; the existing Phase 6 boundary suites pass unmodified |
| Legacy strings | Strings and element hooks pinned by existing tests are unchanged |
| Accessibility | Section 8 "Cross-gate requirements" |
| Regression | `manage.py check`; focused module; `test_phase7_*`, `test_ui_admin_phase3*`, Phase 6 modules; full PostgreSQL `--parallel 4`, exact counts reported |
| PR hygiene | Template (plus breadcrumbs, a status partial if needed, and minimal scoped CSS) diff only; draft PR; no merge, deploy or next gate without approval |

## 10. Decisions requested from the reviewer

- **F1: Gate split and order.** Recommended: A security operations, B announcements, C documents, D notification queue, E bulk imports (risk ascending: unconfirmed destructive-looking controls and a multi-flow template first; irreversible serial numbers next; real-world messaging next; data creation last). Alternative: swap C and D, or fold A into B.
- **F2: Sensitive account screens** (credential slips, reset, username, revoke, reactivate and deactivate confirmations). Recommended: exclude from D1-6 and give them their own security-reviewed gate (one-time secrets, print CSS, `no-store` headers), opened only on explicit approval.
- **F3: Residual configuration forms and calendar pages.** Recommended: not part of D1-6; a separate "residual forms sweep" gate after D1-6, using the accepted form pattern.
- **F4: "Reporting".** Recommended: treat as closed by D1-4C and D1-5C; D1-6 adds no report, export or chart.
- **F5: Import detail volume.** Recommended: no pagination or search in D1-6 (functional change); use labelled scroll regions and the existing counts; log pagination as a follow-up gate.
- **F6: Unconfirmed POSTs** (Discard import, Dismiss message, Withdraw notice, Clear lockout). Recommended: consequence text only now; real confirmation pages as a launch-readiness follow-up, consistent with D1-5 (E5).
- **F7: Documents evidence.** Recommended: screenshots never open or render a PDF; only the index, forms and lists, with invented Students.
- **F8: Notification text.** Recommended: display `row.text` exactly, never reformat; do not change the Send link attributes; no automation or API-mode UI.
- **F9: Carried item.** The D1-5D publish-only post-withdrawal redirect-to-403 stays a **mandatory pre-production follow-up** and is not part of D1-6.

## 11. Execution plan (after approval of this plan)

1. Merge this documentation PR; fresh branch from `main` for the first approved gate (recommended D1-6A) in the separate clean worktree.
2. Templates, breadcrumb rules and scoped CSS only; tests per section 9; focused, then the Phase 6 and 7 modules, then the full PostgreSQL `--parallel 4` suite.
3. Synthetic screenshots, measurements and README under `docs/ui-reviews/ui-d1-6a/` and so on.
4. One draft PR per gate; report head SHA and results; **stop** for design review. No merge, no deployment, no next gate without approval.

## 12. Explicit follow-ups — not in D1-6

- Confirmation pages for Discard import, Dismiss message, Withdraw notice and Clear lockout (launch readiness); the same for D1-5's Delete and Remove.
- Import detail pagination, search and sorting; a real notification-queue filter (by type, by guardian).
- `FieldAccessibilityMixin` on the announcement, document and import forms (automatic error focus).
- A security-reviewed gate for credential slips and the reset, username, revoke and reactivate confirmations.
- A residual configuration-forms sweep.
- The D1-5D publish-only redirect fix (mandatory before production) and any API-mode, SMS or automation UI (none exists).
- Deployment of any UI-D1 gate.
