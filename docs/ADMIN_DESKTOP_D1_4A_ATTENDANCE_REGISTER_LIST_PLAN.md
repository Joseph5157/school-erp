# UI-D1-4A — Admin Attendance Register List

**Status:** Formal implementation specification prepared 23 October 2026; **implementation not started**, no draft PR opened, no merge/deployment authorized.
**Planning branch:** `plan/ui-admin-desktop-d1-4a-attendance-list`, based on `main` `436fa75148c3c3865d5df8af5456f4734be5c999` (UI-D1-3D2 closeout).
**Parent:** `docs/ADMIN_DESKTOP_D1_PLAN.md` (D1-4). **Binding design:** `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, established D0 / D1-3A list patterns.
**Single implementation target:** `core/templates/core/attendance_register_list.html` at route `core:attendance-register-list` (`/attendance/`). One independent, narrow UI gate. The screenshot set is **local synthetic evidence**, never production or staging verification.

## 1. Purpose and audited baseline

Make the existing administrator **Attendance Register List** consistent with the accepted page-header, filter-toolbar, panel, table and pagination system while retaining every current attendance rule and interaction. This is a **presentation-only** change, not a new Attendance feature.

Source audit of `main` at `436fa75`:
- Template already uses `partials/_page_header.html`, permission-gated **Open register** / **View reports** links, `partials/_table_head.html` and `_table_footer.html`, `erp-table-scroll`, and `_status_badge.html`. **Do not rewrite working partials.**
- The existing GET filter form is a generic `row g-2 align-items-end mb-3` rather than the shared `erp-toolbar`. The two-column Section summary is an ungrouped table, while the register grid is missing the established `erp-panel` surface. The empty-table message does not distinguish an empty database from a valid no-results filter. Filter validation errors are not currently displayed.
- `attendance_register_list` in `core/views.py` requires `core.view_attendanceregister`. `AttendanceRegisterFilterForm` supplies optional `section`, `start`, `end`. It applies filters only if the **entire form is valid**; an inverted range produces the existing `Start date must not be after the end date.` non-field error. Do **not** change the view's invalid-filter fallback in this visual gate.
- `REGISTER_COLUMNS` is exactly: **Date, Academic year, Class/Grade, Section, Status, Entries**. Sortable: Date, Section, Status, Entries. Initial order is **newest Date first** (`-date`), stable tied to Section/Grade and pk via `build_table`. `build_table` has a shared **25 rows/page** contract, URL-preserved GET sort/filters, table count and clamped/ignored invalid sort/page inputs.
- `register.entry_count` is a **raw count of saved AttendanceEntry rows in that register**, including Draft records. It is **not** the total roster size and **not** the reportable-attendance count.
- The **Section summary appears only for a valid selected Section** (with any optional valid date range) and counts **reportable submitted entries** through `reports.reportable_entries` and `reports.counts`. Its only status categories are **Present** and **Absent**; total is their sum. It is computed on the complete filtered queryset **before pagination**, not on the visible 25-row page.
- **Draft != Submitted.** A Draft can contain saved entries, but those entries are not reportable. Missing/unmarked entries are **not Absent**. Enrollment boundaries, school-calendar instructional days, non-future limits and corrections are defined by existing domain/report functions and cannot be reinterpreted in the UI.

## 2. Explicitly authorized implementation scope

**Allowed:**
1. `core/templates/core/attendance_register_list.html` — only application template in scope.
2. A small, **`erp-attendance-list-*` prefixed** CSS addition to `static/css/erp.css` **only if** existing `erp-toolbar`, `erp-panel` and Bootstrap 5 responsive utilities are insufficient; prefer **zero CSS**.
3. Focused UI/authorization/presentation regression tests in a new `core/tests/test_ui_admin_desktop_d1_4a_attendance_list.py`.
4. Synthetic before/after screenshots and evidence README under `docs/ui-reviews/ui-d1-4a/`; this plan and narrow parent status updates.

**Forbidden:** `core/views.py`, `core/forms.py`, `core/tables.py`, reports or attendance services, models/migrations/queries, permissions, route configuration, shared table/header/footer/status/empty partials, global layout CSS, Student/Teacher/Guardian portals, the register detail/capture/submit screens, correction pages, attendance reports, PDF/document issuance, Calendar, D1-4B/C, D1-5/6, academic-year rollover or Railway. No Tabler dependency; no JavaScript needed.

**CSS compatibility warning:** an existing D1-3D1 regression test inspects all CSS after `/* UI-D1-3D1 review fix` and requires Guardian-wrapper-prefixed selectors there (D1-3D2 appended one such rule). If unavoidable, insert the small, strictly `erp-attendance-list-*`-scoped block **BEFORE** the D1-3D1 review-fix comment; do not append an unrelated selector after it, or edit existing rules. Test against D1-3D1/D1-3D2.

## 3. Target page composition

1. **Header:** Keep exactly one H1 `Attendance`, eyebrow `Daily operations`, and existing accurate purpose. Reuse `partials/_page_header.html`, with the exact existing conditional links:
   - **Open register** only when `perms.core.add_attendanceregister`; route `core:attendance-register-create`.
   - **View reports** only when `perms.core.view_attendanceentry`; route `core:attendance-reports`.
   - Do not invent quick actions or broaden these predicates. There is a pre-existing possibility that users can open the reports index but lack permission on one of its subreports; **log separately**, do not alter authorization here.
2. **Filter toolbar:** Wrap existing `<form method="get">` in `erp-toolbar` with `aria-label="Filter attendance registers"`. Use responsive Bootstrap grid: all three controls **Section**, **Start date**, **End date** remain visibly labelled, in that order, stacked/usable on narrow screens and aligned at desktop. Render **existing Django fields**, retain names `section`, `start`, `end` and date input types; do not rebuild fields with hand-coded choices. Preserve GET submission and button label **Filter**. Preserve `table.sort_param` hidden `sort` only when the shared table supplies it; avoid carrying `page` through a new filter submission, so filtering starts at page 1. Offer an ordinary GET **Clear filters** link to `core:attendance-register-list` when Section/Start/End were supplied; the shared footer's existing filtered-empty link stays intact. Do not add status, keyword, year, date presets, or search boxes (not supported by current view).
3. **Invalid-filter state:** Render `form.non_field_errors` once in `erp-form-errors` / `role="alert"`, and field-local errors for Section, Start and End, without duplicating messages or hiding entered values. When the form is invalid, a short accurate note may explain **"Filters were not applied; showing all registers."** because that is what the untouched view actually does. Do not label its unfiltered results as if the invalid query had been applied. No new validation or changes to `AttendanceRangeForm.clean()`.
4. **Section summary panel:** Only when `section_summary is not None`, show a distinct `erp-panel` / accessible section heading `Section summary`. Accurately label it **"Reportable submitted attendance only"**, not all entries, missing registers or an attendance-completion percentage. Retain existing **Present / Absent / Total** values exactly as supplied. Use real table semantics (`caption` or heading association; `<th scope="col">` and sensible row/total headers), no invented KPIs. Zero counts remain zero; no Section selected means **no summary**.
5. **Register table panel:** Wrap the existing six-column table in `erp-panel`, keeping labelled keyboard-scrollable `erp-table-scroll` with `role="region" aria-label="Attendance registers" tabindex="0"`. Use the existing table-head and footer partials, their `aria-sort`, sort links, filtered GET state, count text and pagination unchanged. Preserve exact column order and cell values; Date remains the only row navigation to `core:attendance-register-detail`. Draft/Submitted are clearly written alongside existing status colors; `Entries` remains the raw entry count, not a completion indicator.
6. **Empty states:** Distinguish:
   - **No registers at all and no valid active filters:** `No attendance registers yet.` with the existing permission-gated route to open a register.
   - **Valid filters yielding zero results:** `No attendance registers match these filters.` and `Clear filters`, without falsely claiming the school has no attendance records. The shared footer must continue to show `No results` and its reset link.
   - **Invalid filters:** show validation feedback and do not claim the currently visible list reflects those invalid inputs.
   Existing table header, filters and footer remain available even when empty.
7. **Responsive and accessible:** No document-level horizontal overflow at 360, 390, 768, 992, 1024, 1280 and 1440px. The six-column table may horizontally scroll **only in its labelled container** on small widths; no text clipping or tiny collapsed columns. Keep date, long Academic Year / Class / Section names and all status labels legible; keyboard users can reach toolbar, table scroll and pagination. Don't produce duplicated heading or a fake mobile card driven by new APIs.

## 4. Hard business and permission invariants

- List remains a **read-only GET** surface. No submission, capture, correction, bulk operations, new requests or database writes. Preserve the List `view_attendanceregister` guard; anonymous user redirects to login, denied roles remain denied. A viewer without `add_attendanceregister` must not see **Open register**; a viewer without `view_attendanceentry` must not see **View reports**. Do not broaden access because summary counts or links are displayed.
- **Status semantics:** Draft/Submitted remain as recorded; a partially marked draft's `Entries` count may be nonzero while its contribution to the selected Section summary remains **zero**. A missing register has no row; it is neither Draft nor Absent. Never compute percentage from raw register counts or imply a fully captured roster.
- **Reportable semantics:** No changes to `reports.reportable_entries`, `reports.counts`, calendar or effective-date enrollment filtering, or correction projections. No manual report counts or date math in the template. Summary `Total = Present + Absent` for all currently selected reportable data only, never missing/draft/unmarked.
- **Filter/sort/pagination:** Section/date form validity, recognized sort tokens, default Date-desc ordering, 25/page, URL persistence and invalid query handling remain unchanged. Table footer count refers to **register rows**, not student attendance counts; summary counts refer to **reportable student entries**, not register rows.

## 5. Acceptance matrix (all required)

| Check | Pass condition |
| --- | --- |
| Structural | Exactly one H1, unchanged conditional header actions, `erp-toolbar`, labelled 3-field GET filter, separate summary (when applicable) and table `erp-panel` surfaces, shared head/footer/scroll/status components reused |
| Query invariance | Compare pre/post response contexts for unfiltered, Section only, Start only, End only, Section+range, invalid date/range and invalid sort/page; identical register identities/order, summary values and permission outcomes |
| Sort/pagination | Default newest first; Date/Section/Status/Entries order and `aria-sort`; 30+ registers show 25/page, correct count and Page 2 preserving Section/date/sort; Filter action resets page while keeping explicitly selected valid sort |
| Business semantics | Synthetic Draft with saved entries, Submitted Present/Absent, zero-entry Draft, unmarked roster, cross-section registers and a date window; only reportable submitted entries contribute to Section summary. Data from any nonreportable calendar/enrollment/future scenario must follow existing report functions |
| Validation/empty | All four states: no registers, filters yield no registers, filtered Section with zero reportable entries, invalid date or inverted date range. Error text visible once, no fabricated Absent counts, no data writes |
| Permissions | Admin viewer/limited viewer/anonymous/teacher/guardian route tests; header and empty-state Create action strictly gated by `add_attendanceregister`; View reports strictly gated by `view_attendanceentry`; no unauthorized routes introduced |
| Responsive/accessibility | Before/after synthetic browser screenshots at **390, 768, 992, 1024, 1280, 1440px** plus a **360px** measurement for base, filtered, Draft/Submitted, no-data and no-results states where useful; long Section/Academic Year names; no page overflow; labelled local table scroll; focus order, focus visibility, keyboard scrolling, sensible 200% zoom |
| Automated regression | `python manage.py check`; focused D1-4A module, existing admin-list/table tests and Phase 2/4 Attendance/report semantics tests; final **full local PostgreSQL suite with `--parallel 4`**, run with **no other concurrent test runner sharing test databases**. Report exact counts, commit, actual environment and limits (no CI claim absent evidence) |
| PR hygiene | Focused commits/diff only. No changed Python business logic. No snapshots with real student data or credentials. Evidence README identifies synthetic browser environment. Open **draft PR targeting main**, provide branch/head SHA and summary and stop. Do **not** mark ready, merge, deploy, start D1-4B/C or tidy unrelated worktrees/databases |

## 6. Execution plan

1. **Baseline / verify:** Start a fresh implementation branch from the latest approved `main`, incorporating this docs-only spec (use an orderly cherry-pick or branch from the planning branch if its parent is still current). Check clean status and no unrelated changes.
2. **Template only:** Adapt filters and validation presentation, Section summary panel, register table panel and empty states. First use existing components; add narrowly scoped CSS only to address proven responsive defects.
3. **Regression tests:** Add focused HTML/content and route-permission tests that compare existing contexts and status semantics, including the distinction between raw Entries and reportable summary counts.
4. **Visual review:** Use disposable database fixtures; gather named screenshots at specified widths, check 360px and 200% zoom, keyboard scrolling and no page overflow.
5. **Verify/stop:** Run focused checks and full PostgreSQL tests sequentially; stage explicit files, open one draft PR and stop for this gate's independent design review.

## 7. Explicit follow-ups — not in this PR

- **D1-4B:** register detail, Draft roster/capture surface and the correction form/history. The roster partial is reused by Teacher Workflows: a change requires an explicitly scoped review, not a side effect of D1-4A.
- **D1-4C:** Attendance reports index, daily absentees, missing attendance, monthly Section, Student attendance history.
- **Document Attendance Summary/PDF issuance:** separate Documents scope decision, not included here.
- **Existing cross-permission navigation oddities:** e.g. users able to view the reports index but not every linked subreport; permission behavior must be considered in another gate, never widened silently.
- **No data/business changes** to the Attendance Calendar, reportability rules or Guardian/Teacher attendance surfaces.
