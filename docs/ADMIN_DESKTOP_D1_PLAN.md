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
- **D1-3 Admissions and people:** applicants, guardians, teacher accounts and profile/admin forms. Keep existing audits, saved query state and permissions. Do not duplicate UI-D0 Students work.
- **D1-4 Attendance administration:** register list, detail and reports, corrections. Preserve Draft/Submitted and reportable-attendance rules.
- **D1-5 Assessments/results:** list/planning, publication, result review, report/export pages. Preserve release-order, finalized-result, and guardian publication semantics.
- **D1-6 Communication and operations:** announcements, notification queues, documents, import, access reviews, lockouts and reporting. Restrict sensitive actions to their established views.

Sequence after D1-1 is provisional; confirm against screenshots and current code before implementation. No automatic rollout across all admin templates.

## Separate future work

`docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md` is queued for its **Rollover 0 ADR freeze**. Do not implement rollover domain code in any UI-D1 branch.
