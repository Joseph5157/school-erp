# Admin tables and table tokens (UI-06, UI-14) — plan

Status: **PLAN, decisions settled 2026-10-25; awaiting review before execution.** No code written. Branch `docs/ui-06-14-tables-tokens-plan` from `main` (`a332a0b`).
Source: Admin Desktop UI/UX audit items UI-06 (Medium, "two table systems coexist") and UI-14 (Low, "fractional type and spacing values").
Out of scope: palette (UI-10), buttons (UI-15), icons (UI-16), filter/form density (UI-08), sticky headers, empty-state pattern, Teacher and Guardian-portal tables, print/credential slips, any model/migration/route/permission change.

## What a survey found (so the plan is smaller than the audit suggests)
- The audit's "two table systems" is real but narrow. ~40 admin tables already sit in `.erp-panel` + `.erp-table-scroll` and share one rule block (`erp.css` ~1221-1231). Only **8 templates** still render plain Bootstrap tables: `student_detail` (3 tables), `term_remarks`, `timetable_index`, `timetable_periods`, `timetable_sections`, `timetable_issues` (2 tables). The Assessment detail results table is already inside a panel.
- There is no global `.table`/`th`/`td` rule, so legacy tables get Bootstrap's 16px headers and `.5rem` padding. The 41–121px row-height spread in the audit is mostly content (multi-line cells), not two paddings.
- The fractional values come from: `--erp-text-xs: .78rem` (12.48px) used by the shared table header; a literal `.7rem` (11.2px) header padding at `erp.css:1223`; and `--erp-text-sm: .9rem` (14.4px). Roughly 80 other fractional literals exist across the stylesheet and are **not** touched here.
- No test asserts a table pixel value or table font-size. Tests that constrain the work are listed under Constraints.

## Decisions (settled)
1. **Type tokens: table-only.** The global `--erp-text-*` tokens are left unchanged. New table tokens carry the whole-pixel values, so the rest of the product does not shift.
2. **Legacy tables: convert all eight templates** onto the panel look.
3. **Sweep scope: tables and token definitions only.** The other fractional literals wait for a per-page token pass.
4. **Header style: 13px, uppercase, weight 600**, keeping today's letter-spacing.

## Design
New tokens in `:root` (names are final, values in px at a 16px base):
- `--erp-table-head-size: .8125rem` (13px), `--erp-table-head-weight: 600`, `--erp-table-head-tracking: .04em` (unchanged),
- `--erp-table-pad-y: .75rem` (12px), `--erp-table-pad-x: 1rem` (16px), `--erp-table-head-pad-y: .75rem` (12px, replaces the `.7rem` literal).
Cells keep the inherited 16px size and 12px/16px padding: rows stay ~48px for single-line content, inside the audit's 44-48px target. No new density modes (YAGNI).
The shared rule `.erp-panel .table > thead th` and `.erp-panel .table > tbody td, th` read the tokens. `.erp-rc-table` (report-card tables) adopts the same header tokens. Teacher grid (`.erp-grid`) is not touched.

## Constraints
- Do not reformat the `erp.css` line `.erp-panel > .erp-table-scroll { border-radius: 0; scrollbar-gutter: auto; }` (asserted verbatim by `test_ui_admin_desktop_d0.py:80`) or the `.erp-table-scroll:focus-visible` rule (`test_ui_table_scroll_focus.py:13`).
- Keep these exact HTML strings where tests assert them: `class="erp-table-scroll" role="region"` (timetable issues/periods tests), `<div class="erp-panel">\n<div class="erp-table-scroll" role="region" ` (attendance), `<th scope="col" class="erp-num">`, `<td class="erp-num">`, and `scope="col"` on headers.
- Phone behaviour: tables need `.erp-keep` to scroll instead of reflowing (see the CSS/nav gotchas note); every converted table gets it, as the modern ones do.
- CSS added for a page must be scoped to that page's own class; an earlier unscoped rule once collided with `.erp-section-title`.
- Match surrounding style. Reuse `partials/_table_head.html` only where a table already has sort data (no new sortable columns).

### Task 1: Table tokens and the shared panel table rule
Files: `static/css/erp.css` (`:root` block; rules around 1174-1175 and 1221-1231), a new CSS-text test (add to `core/tests/test_ui_admin_desktop_d0.py` or a new `core/tests/test_ui_table_tokens.py`).
Add the six `--erp-table-*` tokens to `:root`. Rewrite `.erp-panel .table > thead th` to use `font-size: var(--erp-table-head-size)`, `font-weight: var(--erp-table-head-weight)`, `letter-spacing: var(--erp-table-head-tracking)`, `padding: var(--erp-table-head-pad-y) var(--erp-table-pad-x)`; keep uppercase, `nowrap` and the `--erp-paper` background. Cells: `padding: var(--erp-table-pad-y) var(--erp-table-pad-x)`. Point `.erp-rc-table thead th` at the same head size/weight/tracking tokens.
Done when: no `.7rem` literal remains in the panel table header rule; the tokens exist with the stated values; a test reads the stylesheet and asserts the token values, that the panel header rule references them, and that the two protected rules above are unchanged; no existing test changes.

### Task 2: Timetable pages onto the panel look
Files: `core/templates/core/timetable_index.html`, `timetable_periods.html`, `timetable_sections.html`, `timetable_issues.html` (two tables), their existing tests (`test_timetable_*_ui.py`).
Wrap each table's existing `<div class="erp-table-scroll" ...>` in `<div class="erp-panel">` and add `erp-keep` to the `<table class="table">`. Do not change table content, headings, links, forms or empty states. The exact string `class="erp-table-scroll" role="region"` must remain a substring.
Done when: each of the five tables renders inside `.erp-panel`, carries `erp-keep`, and every existing timetable test passes unchanged; add one test per template asserting the panel wrapper and `erp-keep`.

### Task 3: Student detail and Term remarks
Files: `core/templates/core/student_detail.html` (three tables, ~lines 50, 99, 137), `core/templates/core/term_remarks.html` (~line 20), their existing tests.
These tables are bare (no scroll wrapper). Wrap each table in `<div class="erp-panel"><div class="erp-table-scroll" role="region" aria-label="…" tabindex="0">` with a meaningful label per table (reuse the table's preceding heading text), add `erp-keep`, and keep `align-middle` on Term remarks. Do not change cell content, links or form controls inside Term remarks.
Done when: all four tables are panel-wrapped with labelled regions, existing tests pass, and a test per template asserts the wrapper, label and `erp-keep`; the Term remarks form still posts exactly as before.

## Verification (after all tasks)
`manage.py check`, the touched test modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order` and one date-dependent test are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, drop afterwards) at 1366×768: Students list, Subjects, Timetable overview, Student detail, Term remarks, and Report card; compare header size, row height and alignment against a modern table. Measure computed header font-size (13px) and header padding (12px/16px) in the browser. Rollback = revert the PR; no migrations.
