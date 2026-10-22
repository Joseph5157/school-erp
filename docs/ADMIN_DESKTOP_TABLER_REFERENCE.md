# Admin Desktop — Tabler Visual Reference

Status: **UI-D0 preferred design reference**, recorded 2026-10-20. This is a visual direction, **not** approval of full application migration or the Tabler runtime. Review actual School ERP screenshots before freezing the design.

## Reference URLs (viewed 2026-10-20)

- Tabler landing/preview: https://tabler.io/admin-template/preview
- Tabler live vertical sidebar: https://preview.tabler.io/layout-vertical.html
- Tabler fluid layout: https://preview.tabler.io/layout-fluid.html
- Tabler data tables: https://preview.tabler.io/tables.html
- Tabler wizard: https://preview.tabler.io/wizard.html
- Layout and accessibility guidance: https://docs.tabler.io/ui/layout/page-layouts
- Component documentation: https://docs.tabler.io/ui/components
- Open-source implementation / MIT license: https://github.com/tabler/tabler

## Decision

**Borrow the feel and proven interaction patterns; continue to own the School ERP design system.** The visual target is Tabler's light, vertical-sidebar administrative workspace: restrained surfaces, clear typography, compact controls, generous horizontal working room, stable header, scannable tables and explicit task actions.

Do **not** load a second Bootstrap/theme bundle, install `@tabler/core`, replace base.html with a stock Tabler page, or make Django templates dependent on Tabler-specific classes just to reproduce the screenshot. If any exact open-source snippet is copied in a later gate, check its applicable license and record its provenance. Reproduce approved patterns with Bootstrap 5.3.3 and project-owned `erp-*` classes.

Keep the School ERP's existing green `--erp-accent`, typography hierarchy, spacing and other `--erp-*` tokens. Tabler's default blue/demo business branding and charts are **not** an ERP design requirement.

## What already exists in the code and should be reused

- `templates/base.html`: sticky top bar, school brand, account menu, main landmark and skip link.
- `templates/partials/_sidebar.html`: permission-scoped office navigation with grouped sections, active link, waiting badge, and Bootstrap offcanvas on small screens.
- `core/navigation.py`: permission-filtered navigation configuration and active destination.
- `core/context_processors.py`: explicit admin/teacher/guardian area separation and breadcrumb context.
- `static/css/erp.css`: existing 992px desktop breakpoint, ~15.5rem sidebar width and school-owned color/spacing tokens.
- Existing table/list/breadcrumb/empty-state components: audit before creating duplicates.

No work should weaken or replace the authorization checks in views. Sidebar visibility is display only.

## UI-D0 visual design target

### Desktop shell (>= 992px)

- Permanent, clearly grouped vertical **left sidebar**, light surface with muted separators/section headings; one text-labelled primary destination and an evident active marker. Group labels remain readable. Prefer current groups as a starting point rather than inventing new routes.
- Compact top bar with School ERP branding/school logo and signed-in account menu. Avoid duplicate headers or multiple prominent nav bands.
- Fluid, breathable content area for heavy administration: page title + breadcrumbs + brief context + a single prominent page-level primary action when relevant. Preserve reasonable reading widths for long form/help content; do not blindly make every form 100% width.
- Reuse existing `erp-*` classes and Bootstrap utilities. Adopt Tabler-like proportion, whitespace, typography and low-contrast borders; avoid a card around every element.
- A folded/icon-only sidebar, hover-only flyouts, top-level reorganization, dark-mode toggle and dynamic theme customizer are **not** UI-D0 goals. Explore separately only if usability demonstrates need.

### Operational behavior

- Below 992px retain the current office offcanvas behavior and existing teacher and guardian mobile experiences; do not compress desktop-only bulk actions into unusable mobile tables.
- Real, semantic HTML controls and table headers; keyboard focus, active destination text + aria-current, responsive scrolling confined to data tables, visible skip link on focus, no horizontal *page* overflow.
- Headings, badges, buttons and empty states must follow `docs/UI_DESIGN_RULES.md`. No misleading demo/sample counts or analytics. A chart is only permitted when backed by meaningful real data and the domain rules.
- Keep school access restrictions, denied 403 shell, account switching, academic-year and term rules unchanged.

## Page-to-pattern mapping for the first five-screen spike

| School ERP page | Tabler pattern to study | Adaptation requirements |
| --- | --- | --- |
| Overview | Light dashboard, page header, concise stat cards | Use real permitted school metrics and actionable queues. No sales/revenue/user growth dashboard filler; avoid faux charts. |
| Students | Tables, filters, pagination, badges | Clear name + admission identifier + Class/Section + status; URL-backed filters, real counts and permission-safe links; existing list behaviour must be preserved. |
| Academic Years | Settings/list forms, hierarchy, status badges | Clear current/past/future years and dates from real records; do not imply a rollover exists yet; no state mutation in spike. |
| Teacher mapping | Forms, tables, tabs / grouped controls | Date-effective assignment and existing permissions stay authoritative. Prefer a scannable section/teacher assignment layout over a dense generic CRUD form. |
| Timetable | Wide working area, filter strip, tabular grid | Preserve constraints and actual timetable data. Use local grid scroll where needed; do not add a generic chart/calendar plugin. |

## Later reference for Academic Year Rollover

Tabler wizard steps, progress/summary tables, and confirmation patterns are good for Rollover 2 **after** the separate Rollover 0 ADR/decision freeze and Rollover 1 domain foundation. Use five explicit outcomes (PROMOTE, REPEAT, GRADUATE, LEAVE, HOLD); real counts, stale-plan checks and consequences, not demo data or automatic promotion.

## UI-D0 review evidence / stop rule

Take side-by-side Tabler reference and actual School ERP screenshots of Overview, Students, Academic Years, teacher mapping and Timetable at 1280px and 1440px; assess navigation, spacing, density, hierarchy, content width, and real-data readability. Check 992px, 768px and 390px for regressions; separately inspect teacher, guardian, login and 403.

Classify proposed patterns as **reuse / adapt / defer**, with filenames and rationale. Do not start full page-by-page migration or any rollover backend changes. **Stop at a draft PR** for visual sign-off.
