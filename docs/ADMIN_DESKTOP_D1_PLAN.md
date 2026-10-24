# UI-D1 — Admin Desktop Page-by-Page Adoption

Status: **D1-1 ACCEPTED and MERGED** (PR #93, merge `45b0088`, 2026-10-22). **D1-2A ACCEPTED and MERGED** (PR #94, merge `19fd57b`, 2026-10-22). **D1-2B ACCEPTED and MERGED** (PR #95, merge `e43d477`, 2026-10-22); D1-2 School Configuration complete. D0 foundation merged in PR #92 (`dd6e9daa`). This document is a narrow follow-up plan; **do not** implement all items in this plan together.

## Baseline / binding design rules

- Source: `main` after PR #92.
- Preferred visual reference: `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md` and `docs/ADMIN_DESKTOP_PRODUCT_DIRECTION.md`.
- Keep Django server-rendered templates, Bootstrap 5.3.3 and School ERP's `erp-*` tokens and components.
- `erp-panel`, `erp-toolbar`, and data-table conventions from UI-D0 are approved; reuse before adding more CSS.
- Use desktop workspace at >=992px, ensure no page-level horizontal overflow at any breakpoint. When a wide grid must scroll, keep it local, accessible and keyboard scrollable.
- Only migrate one logical set of pages per PR. No unrelated domain behavior, migration, view, service, route or authorization changes. Do not install Tabler.
- Preserve accessible headings, skip link, labelled table scroll region, focus styles, permission-scoped actions, existing form actions, and active navigation.
- Revisit status after each PR: merge only after review and credible tests.

## D1-1 — Teacher assignment history readability (ACCEPTED / MERGED)

**Implementation (2026-10-22, merged PR #93):** each History entry is a list item with status + teacher, then the date range (each date `text-nowrap`), then its permitted End/Delete planned actions. The History cell has a `17rem` floor, so at 768–1024px the table scrolls inside its labelled region instead of squeezing; at 1280/1440px it fits without scrolling. Headers have `scope="col"` and the action column has a visually hidden "Actions" label. Screenshots: `docs/ui-reviews/ui-d1/` (seeded demo data). Template and `erp-assignment-*` CSS only; no view, permission or POST changes.

Source: PR #92 design review. At width **992px** the `History` column of `core/templates/core/teacher_assignments.html` collapses excessively; the teacher name/dates wrap into many short lines, producing unusually tall rows. This is a known nonblocking D0 issue and now the first D1 fix.

### Required outcome

- Keep six semantic columns: Class/Grade, Subject, Section, Current teacher, History, contextual action.
- Teacher assignment history should show **status, teacher identity, effective start/end dates, and permitted End/Delete planned action** in a readable layout without changing their logic.
- Prefer a compact multi-line **history entry** within the History cell (status + teacher on one logical line; date range on a following line; permitted action separately), preserving every historical entry. Avoid cryptic truncation, ellipsis hiding data, tooltip-only information, or wrapping within a date token.
- At widths 992px and 1024px, a minimum reasonable History width is preferred; when there is genuinely insufficient space, use the already-existing `.erp-table-scroll` region for table-local horizontal scroll rather than squeezing other columns or the action button into unreadability.
- Avoid adding a fixed-width assumption that damages 1280/1440px layouts. Use `scope="col"` headings and retain existing permission checks. Ensure historical information remains readable with keyboard, zoom and long teacher names.
- Do not touch effective-dating rules, teacher accounts, classroom permissions, POST behavior, current/past/future status logic, service calls, or deletion logic.

### Scope

Allowed: `core/templates/core/teacher_assignments.html`; scoped `static/css/erp.css` styles (new `erp-assignment-*` only if needed); focused UI/test files and screenshots under `docs/ui-reviews/ui-d1/`; this plan/status document.

Not allowed: `core/models.py`, views, forms, URLs, authorization, migrations, database changes, teacher/guardian portal UI or broad global table refactors.

### D1-1 acceptance scenarios

1. **Typical desktop:** screenshot 992, 1024, 1280 and 1440px with multiple history entries and both active/past statuses. No broken teacher names mid-word; no tall letter-by-letter or date-token wrapping; no page horizontal overflow.
2. **Small/mobile:** 390 and 768px screenshots. The admin table may scroll *inside its labeled region*, with clear readable cells; no changes to Teacher and Guardian portal shells.
3. **Long names / many entries:** stress with a long teacher name, an open-ended assignment, a past assignment, and multiple entries for one slot. Never suppress data. Table scroll is acceptable; a full-page overflow is not.
4. **Permissions:** `Reassign`, `End`, and `Delete planned` appear only under their existing authorized conditions; no changed request method or confirmation semantics.
5. **Accessibility:** accessible table/heading structure, visible keyboard focus, action link/button discernibility, labeled scroll region.
6. **Verification:** `python manage.py check`, relevant authorization and teacher-assignment tests, newly added UI tests, and full PostgreSQL suite when supported. State exact result and any constraints. Screenshots are seeded demo data; say so.
7. **Stop:** publish a draft PR with before/after, tests, diff scope, and known limits. No merge/deploy until accepted.

## D1-2+ — Candidate adoption sequence (D1-2A MERGED)

Each is a separate scoped PR only after the previous gate is reviewed:

- **D1-2A School configuration (accepted/merged, PR #94):** four existing class/subject/term/offering list pages; exact scope and acceptance in `docs/ADMIN_DESKTOP_D1_2_SCHOOL_CONFIGURATION_PLAN.md`. **D1-2B (accepted/merged, PR #95):** class teacher mapping and assignment overview; scope and acceptance in `docs/ADMIN_DESKTOP_D1_2B_CLASS_TEACHER_MAPPING_PLAN.md`. Full PostgreSQL suite 2,303 passing.
- **D1-3 Admissions and people (COMPLETE, merged):** PRs #96–#100, final D1-3D2 merge `d60de53`, docs-only closeout `436fa75`; see `docs/ADMIN_DESKTOP_D1_3_ADMISSIONS_PEOPLE_PLAN.md` and the D1-3D1/D1-3D2 closeout plans. Not deployed as part of the UI-D1 gates. Keep existing audits, saved query state and permissions. Do not duplicate UI-D0 Students work.
- **D1-4 Attendance administration (independent UI gates):** **D1-4A Attendance Register List: MERGED** (PR #101, merge `fbc8520`, head `e325f81`; docs closeout `288fc0d`; not deployed; see [D1-4A closeout](ADMIN_DESKTOP_D1_4A_ATTENDANCE_REGISTER_LIST_PLAN.md)). **D1-4B Register Detail + Corrections: MERGED** (PR #102, merge `c443cb4`, head `a0ae0c6`; not deployed; see [specification and closeout](ADMIN_DESKTOP_D1_4B_REGISTER_DETAIL_CORRECTIONS_PLAN.md)). The shared roster-comment micro-fix is **MERGED** (PR #103, merge `f8f9e47`, head `3af1566`; not deployed). The U4-3A flaky-test fix is **MERGED** (PR #104, merge `9aa08e4`, head `a394300`; test-only, see [evidence](test-reviews/u4-3a-subject-order-flaky.md); not deployed). D1-4C Attendance Reports: **planning MERGED** (PR #105, merge `64809e5`, head `a25e5a9`; D1–D7 approved with clarifications; see [D1-4C plan](ADMIN_DESKTOP_D1_4C_ATTENDANCE_REPORTS_PLAN.md)). Implementation is split: **D1-4C-1 MERGED** (PR #106, merge `6ef74be`, head `c0d073c`; hub, Daily absent students, Missing attendance, permission-aware breadcrumbs; full PostgreSQL suite 2,558 OK; evidence `docs/ui-reviews/ui-d1-4c1/`; not deployed). **D1-4C-2 MERGED** (PR #107, merge `aedfd33`, head `00c113c`; Monthly Class/Section summary, Student attendance history, permission-aware breadcrumbs; full PostgreSQL suite 2,593 OK; evidence `docs/ui-reviews/ui-d1-4c2/`; not deployed). **UI-D1-4 Attendance Administration is COMPLETE** (D1-4A, D1-4B, D1-4C-1, D1-4C-2). Known follow-ups: per-row "counted in summary" marker on Student history (D7); `FieldAccessibilityMixin` on the report forms for automatic error focus; reconciling `view_attendanceentry` vs `view_attendanceregister` across the index, nav and Missing report. Not deployed. Preserve Draft/Submitted, unmarked-is-not-Absent, correction history and reportable-attendance rules.
- **D1-5 Assessments/results:** list/planning, publication, result review, report/export pages. Preserve release-order, finalized-result, and guardian publication semantics. **Planning approved with clarifications (PR #108)** (see [D1-5 plan](ADMIN_DESKTOP_D1_5_ASSESSMENTS_RESULTS_PLAN.md)): four proposed gates (D1-5A grading scales, D1-5B assessments and corrections, D1-5C result reports, D1-5D Term publication); not implemented. **D1-5A Grading scales: MERGED** (PR #109, merge `fe23608`, head `76bea51`; list, detail, band management and create/edit forms plus permission-aware breadcrumbs; full PostgreSQL suite 2,619 OK; evidence `docs/ui-reviews/ui-d1-5a/`; not deployed). The D1-4C-1 test hardening is **MERGED** (PR #110, merge `cb1a139`, head `dd6144f`; test-only: two Section-id substring assertions replaced by value-based checks, full PostgreSQL suite 2,620 OK; not deployed). **D1-5B Assessments, finalization and corrections: MERGED** (PR #111, merge `7f052ed`, head `44e0343`; assessment list and filters, form, detail and roster, finalization presentation, correction form and history, permission-aware breadcrumbs; full PostgreSQL suite 2,660 OK; evidence `docs/ui-reviews/ui-d1-5b/`; not deployed). Review corrections: scoped `erp-correction-table` Correction History (readable widths, local scroll, 0px page overflow at 360/390/768/1440) and an exact empty-roster `colspan`. **D1-5C Result reports: MERGED** (PR #112, merge `5df0b68`, head `a8d8e03`; result sheet, Student results, Subject/Section matrix with a sticky Student column, and the shared Term report card, plus permission-aware breadcrumbs; full PostgreSQL suite 2,692 OK; evidence `docs/ui-reviews/ui-d1-5c/`; not deployed). **D1-5D Term publication: MERGED** (PR #113, merge `b963a8e`, head `7616c01`; preview and confirmation presentation, stale list, publication detail and version history, withdrawal, permission-aware breadcrumbs; full PostgreSQL suite 2,739 OK; evidence `docs/ui-reviews/ui-d1-5d/`; not deployed). **UI-D1-5 Assessments and Results is CLOSED** (D1-5A grading scales #109, D1-5B assessments and corrections #111, D1-5C result reports #112, D1-5D Term publication #113; none deployed). **Mandatory pre-production follow-up:** after a successful withdrawal the existing `publication_withdraw` view redirects to Publication detail, which a publish-only user (holding `publish_termpublication` without `view_termpublication`) cannot open (403). It needs a separate, narrowly scoped functional fix with its own tests and review; D1-5 deliberately did not change publication views or permissions.
- **D1-6 Communication and operations:** announcements, notification queues, documents, import, access reviews, lockouts and reporting. Restrict sensitive actions to their established views. **Planning approved with clarifications (PR #114)** (see [D1-6 plan](ADMIN_DESKTOP_D1_6_COMMUNICATION_OPERATIONS_PLAN.md)): five approved gates (D1-6A security operations, D1-6B announcements, D1-6C documents, D1-6D notification queue, D1-6E bulk imports) and a deferred-work ledger (section 13); implementation in progress. **D1-6A Security operations: MERGED** (PR #115, merge `97a2d79`, head `aeb83f2`; Sign-in lockouts and the Student guardian-access review step, `login-lockouts` breadcrumb rule; full PostgreSQL suite 2,763 OK; evidence `docs/ui-reviews/ui-d1-6a/`; not deployed). Accepted limits: the review step has no breadcrumb trail (its routes have no rule; a rule would alter the untouched Enrollment form); Clear lockout is still an unconfirmed POST with consequence text only (ledger L3); the manual screen-reader pass and PostgreSQL staging verification remain open (L8).

Sequence after D1-1 is provisional; confirm against screenshots and current code before implementation. No automatic rollout across all admin templates.

## Separate future work

`docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md` is queued for its **Rollover 0 ADR freeze**. Do not implement rollover domain code in any UI-D1 branch.
