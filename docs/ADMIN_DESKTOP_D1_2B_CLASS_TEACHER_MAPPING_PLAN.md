# UI-D1-2B — Class Teacher Mapping and Assignment Overview

Status: **ACCEPTED and MERGED** (PR #95, implementation `16d5785`, merge `e43d477`, 22 October 2026). Evidence in `docs/ui-reviews/ui-d1-2b/`. Full PostgreSQL suite: 2,303 tests reported passing (local; no CI). Accepted design: stacked history entries reusing `erp-assignment-*`, two labelled overview tables with a visible Status column, and a presentation-only "No Sections yet." empty row. Accepted limitations: 390px tables scroll inside their labelled region (Actions off-screen until scrolled); no true empty-state screenshot; 125-200% zoom not tested (defer to a later accessibility audit).
Implementation branch: `ui/admin-desktop-d1-class-teacher-mapping`.
Source main: `b85f7fa09ce4cf4eb2e337a43c6759c21cdbcf48` (docs-only closeout after PR #94; D1-2A merge `19fd57b43889ccaeffa8d66d7e7d26828fc61760`).
Parent decisions: `docs/ADMIN_DESKTOP_D1_PLAN.md`, `docs/ADMIN_DESKTOP_D1_2_SCHOOL_CONFIGURATION_PLAN.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, `docs/UI_DESIGN_RULES.md`, `docs/UI_REFERENCES.md`.

## Purpose / gate discipline

Finish the remaining **school configuration teacher-mapping list screens** using the accepted D0, D1-1 and D1-2A Tabler-inspired, project-owned patterns. This is a **template/CSS-only presentation gate**. Use Django server-rendered templates, Bootstrap 5.3.3, `_page_header.html`, `erp-panel`, `erp-table-scroll`, existing School ERP tokens, and already proven `erp-assignment-*` rules where appropriate. Do not introduce Tabler runtime/dependencies. Do not infer missing permissions, change current-year semantics, invent teacher assignment statuses, or alter any domain rule.

**Only two implementation pages:**

- `core/templates/core/academic_year_class_teachers.html`
- `core/templates/core/academic_year_assignments.html`

Allowed accompanying files: narrowly scoped `static/css/erp.css` adjustments (only if needed); focused UI/template test file(s); screenshots under `docs/ui-reviews/ui-d1-2b/`; this gate plan and project gate status docs.

Forbidden: Django views, forms, models, migrations, URL config, services, queries, auth/permissions, navigation, school calendar, Guardian and Teacher portals, global base shell, D1-1 subject teacher page, academic rollover, data writes or workflow changes. If a genuine functional defect is discovered, report it separately; do **not** silently change behavior in this UI PR.

## D1-2B-1 — Class Teacher Mapping

### Actual existing behavior to preserve

The page is academic-year scoped; title includes `academic_year.name`. Existing guidance says each Section has no more than one class teacher at a time; changed assignments become historical; `year_is_current` controls whether "Current" means effective today, and the date comes from the existing `today` context.

The `sections` rows currently expose the Section's Class/Grade, Section name, optional current teacher, an unbounded historical assignment list, and a permitted Assign/Replace link.

Within each history entry:

- display teacher full name with username fallback;
- show existing start and optional end date (historical template uses `open` for absent end date);
- keep `End` behind `perms.core.change_sectionclassteacher` exactly as currently written;
- keep `Delete planned` behind **both** `perms.core.delete_sectionclassteacher` **and** `not assignment.is_historically_relevant`;
- preserve the `method="post"` form and `{% csrf_token %}`;
- preserve the Assign/Replace URL, `?section=` query parameter and `perms.core.add_sectionclassteacher` gate.

### Design outcome

- Use standard School setup page header, with year shown as context; keep the explanatory note (can make it visually quieter).
- One responsive panel around a semantic five-column table: Class/Grade, Section, Current class teacher, History, Actions. Keep original row and history order exactly, no sorting or server changes.
- Present each historical assignment as a *distinct readable item* (teacher name, bounded date tokens / date range, permitted actions), without losing or truncating entries. Reuse D1-1 assignment history conventions where compatible but do **not** copy its status badge logic: this page currently has no per-history item `status` context.
- Keep long names readable; protect individual date tokens from breaks. Prefer a minimum usable History column width and labelled keyboard-scrollable table region for constrained width rather than wrapping names letter-by-letter.
- Use `scope="col"` and a visually hidden Actions heading. Empty state "No Sections yet." remains truthful and unchanged in meaning.
- Avoid duplicate visible actions, misleading "Current" statuses for historical years, or invented "effective now" badges.

## D1-2B-2 — Assignment Overview

### Actual existing behavior to preserve

Existing `on_date`, `class_gaps`, `subject_gaps`, and `inactive` counts are supplied by the view. The page links to:

- **Copy from another year…** only when **both** `perms.core.add_sectionclassteacher` and `perms.core.add_assessmentteacherassignment` are present;
- **Class teachers** link (existing URL and visibility);
- **Subject teachers** only with `perms.core.view_assessmentteacherassignment`.

Two existing independent datasets:

1. `class_rows`: Section, optional class teacher (existing `core:teacher-load` URL), plus gap/inactive explanation.
2. `subject_rows`: Class/Grade, Subject, Section, optional teacher (same URL type), plus gap/inactive explanation.

Rows with gaps or inactive/nonteacher accounts already use `table-warning`; retain meaning and data. The view determines `row.gap` and `row.inactive` — do not recalculate these in templates or duplicate backend logic.

### Design outcome

- A readable School setup page header with academic year and the existing `on_date` date context.
- Present gap and inactive counts without implying new data or inventing severity/color semantics; **prefer a concise summary line or subdued count cells** using real view values. No fabricated metrics/charts.
- Keep Copy / Class teachers / Subject teachers as contextual links/actions. Do not change access policy or destination.
- Use **two separate, labelled** `erp-panel` + `erp-table-scroll` tables with semantic headings; one for Class teachers and one for Subject teachers. Keep existing row order, empty-state semantics, teacher detail links, and warning text for both gap and inactive cases. Don't hide warnings behind color-only signals or tooltips.
- If the existing template lacks an empty class-teachers row, do not invent data; a semantic presentation-only empty-state can be added without changing view/query behavior if justified and covered by test. If uncertain, preserve existing output.
- No new controls for resolving gaps if the existing view does not supply the URLs/actions.

## Acceptance / verification contract

1. **Diff scope:** only the two templates + optionally small scoped CSS, UI tests and evidence docs. No backend or permission code, form methods, route or domain changes.
2. **Authorization parity:** test administrators and view-only users. Ensure Class Teacher `Assign/Replace`, `End`, and `Delete planned` appear *only under the pre-existing conditions*. Keep planned deletion POST+CSRF. Ensure overview Copy requires both add permissions, Subject teachers link keeps view permission, and link targets remain unchanged.
3. **Historical integrity:** show all history entries and dates for a Section with multiple assignments; avoid misleading active markers, silent truncation or list reordering. Test a long-name case and both historically relevant and planned entries.
4. **Overview data fidelity:** preserve `on_date`, counts and actual `gap`/`inactive` message distinctions with representative fixtures. Subject/Class teacher links are based on existing view context only.
5. **Accessibility:** semantic one-H1 page header, second-level table headings for overview, `th scope="col"`, named Actions or Status headings when appropriate, keyboard-focusable labelled scroll regions, strong link/action accessible names and visible status text. Preserve existing skip link.
6. **Responsive evidence:** before/after seeded disposable database captures of both pages at 390, 768, 992, 1024, 1280 and 1440px; include multiple histories, a very long teacher name, missing/inactive assignments, empty state and view-only state where feasible. Capture scrolled table view where action column starts off-screen. Measure no *page-level* horizontal overflow; contained table scrolling is acceptable. Check 125%-200% zoom or equivalently narrowed viewport.
7. **Test report:** `python manage.py check`, focused Class Teacher / Subject Teacher authorization, existing D0/D1-1/D1-2A UI tests, new focused tests, and complete PostgreSQL suite when available. Report real passed/failed totals and DB used; don't claim browser or CI evidence not actually obtained. Ensure `staticfiles/` is freshly collected for browser screenshots (the previous gate caught stale ignored staticfiles); screenshots are not staging verification.
8. **Stop:** commit only this gate; create a **draft PR**, attach real screenshots and tests, and return PR URL/commit SHA/issues for design acceptance. Do **not** mark ready, merge, deploy, edit the Railway environment, delete the prior `d12a_demo` database, proceed to D1-3, or begin Rollover 0/domain work.

## After acceptance (not authorized yet)

Only after D1-2B review and explicit separate go-ahead: merge, document D1-2 completed on a separate docs-only commit, and plan the next admin-area scope (D1-3 Admissions/People). Academic Year Rollover remains separate and must start with its Rollover 0 ADR freeze.
