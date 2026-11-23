# Everclass design system

Started 2026-11-19 · Owner decision: Everclass keeps its own design system in `static/css/erp.css` and phases Bootstrap out area by area. No other framework (Tailwind, Bulma, etc.).

Related: behaviour rules in `docs/UI_DESIGN_RULES.md`; the removal steps and constraints in `docs/BOOTSTRAP_REMOVAL_NOTE.md`.

## Rules

1. **New or rebuilt templates use only `erp-` classes.** No Bootstrap class names (`btn`, `form-control`, `row`/`col-*`, `d-*`, `m*-*`/`p*-*`, `alert`, `badge`, `table`, `progress`, `visually-hidden`, `text-muted`).
2. **Colours, spacing, radius and type come from tokens** (`--erp-*` in `:root` of `erp.css`). No raw hex values in new rules.
3. **One name, one job.** Before adding a class, grep `erp.css` for the name. (`.erp-note` already means the attendance note field; muted text is `.erp-note-text`.)
4. **Each converted area gets a guard test** that fails if a Bootstrap class comes back (pattern: `test_overview_uses_no_bootstrap_classes` in `core/tests/test_ui_admin_home_tabs.py`).
5. **Phone first.** 16px gutter, 44px tap targets, no horizontal page scroll at 360px.
6. **No JavaScript framework.** Interactions use native elements (`<details>`, `<dialog>`, plain links and forms).

## Tokens (summary; `erp.css` `:root` is the source)

| Group | Tokens |
|---|---|
| Ink and surfaces | `--erp-ink`, `--erp-ink-soft`, `--erp-paper`, `--erp-surface`, `--erp-rule`, `--erp-control-border` |
| Brand / action (teal) | `--erp-action`, `--erp-action-strong`, `--erp-action-wash`, `--erp-action-wash-strong` (`--erp-brand*`, `--erp-accent*` are aliases) |
| Status | `--erp-ok*`, `--erp-warn*`, `--erp-bad*`, `--erp-info*` (each has `-wash`, most have `-strong`) |
| Charts | `--erp-viz-attendance`, `--erp-viz-marks`, `--erp-viz-low`, `--erp-viz-heat-1..3`, `--erp-viz-grid` |
| Spacing | `--erp-space-1` (.25rem) … `--erp-space-7` (3rem) |
| Type | `--erp-text-xs/sm/base/lg/title`, `--erp-line-tight`, `--erp-line-body` |
| Shape | `--erp-radius` (10px), `--erp-radius-sm` (6px), `--erp-btn-radius-sm` (8px) |
| Controls | `--erp-btn-height` (2.5rem), `--erp-btn-height-sm` (2rem), `--erp-btn-soft*`, `--erp-focus-color`, `--erp-focus-ring` |
| Layout | `--erp-topbar-h`, `--erp-sidebar-w`, `--erp-tabbar-h`, `--erp-reading-width` |

## Components

Status: **Ready** = Bootstrap-free and used; **Partial** = ours, but still sits on Bootstrap classes somewhere; **To build** = Bootstrap is still the only version.

| Component | Classes | Replaces | Status |
|---|---|---|---|
| Button | `erp-btn` + `--primary` (filled teal), `--tonal` (light teal), `--soft` (grey) | `btn btn-primary`, `btn-outline-primary`, `btn-outline-secondary`, `btn-sm` | Ready (Overview); other pages still `.btn` restyled |
| Screen-reader text | `erp-sr-only` | `visually-hidden` | Ready |
| Muted text | `erp-note-text` | `text-muted` | Ready |
| Progress bar | `erp-setup-bar` + `erp-setup-bar-fill` | `progress` / `progress-bar` | Ready (setup card); generalise as `erp-bar` when a second use appears |
| Page header | `erp-page-header` (+ `-copy`, `-actions`, eyebrow/title/purpose) | none | Partial (its action buttons and `mt-2` are Bootstrap) |
| Tabs (page-level, link per tab) | `erp-home-tabs`, `erp-home-tab` with `aria-current="page"` | none | Ready |
| Segmented switch (links) | erp-seg, erp-seg-link with aria-current="page" | btn-group | Ready |
| Card | `erp-card` (the shared card: block, used by teacher pages and the School page) + `erp-card--<name>` hooks; inside `.erp-home` (the Overview) it lays out as a flex column | `card` | Ready (Overview). `erp-chart-card` / `erp-analytics-card` remain only on the student progress page; `erp-panel` converts area by area |
| Stat / glance tiles | `erp-stat-card`, `erp-stat-grid`, `erp-glance-*` | none | Ready |
| List rows (tappable) | `erp-home-row` (+ `-main`, `-meta`, `-open`), `erp-attention-list` | `list-group` | Ready |
| Stage counts | `erp-stage-list` (`--two` for a two-up row), `erp-stage`, `erp-stage-count`, `erp-stage-label`, `erp-stage-meta` (small soft line under a count) | none | Ready (Academics) |
| Fold ("Show all N") | `templates/partials/home/_fold_rows.html`, `erp-class-more` | `collapse` | Ready |
| Empty state | `erp-card-empty` (a message inside a card; `--block` for a standalone dashed box), `erp-empty` (the page-level block) | none | Ready |
| Charts | `erp-donut-*`, `erp-heat*`, `erp-class-bar*`, `erp-cols` | none | Ready |
| Form field | `erp-field` | `form-control`, `form-select`, `form-label`, `form-check` | To build |
| Table | `erp-rc-table`, `erp-chart-table`, `erp-keep`; phone stacked rows (opt-in): `erp-table--stack` on the table + `erp-table-scroll--stack` on its `erp-table-scroll` wrapper, a `data-label` on every body cell (the column header text), `erp-stack-actions` on the action cell. Under 576px each row is a block inside the panel (rows divided by a rule), every value beside its label in a 7rem label column, actions 44px tall (a lone action full width); the real table markup and headers stay. See `docs/competitive-research/PACKAGE_C_IMPLEMENTATION_SPEC.md` §4 | `table`, `table-*` | Partial (stacked rows: Grading scales) |
| Alert / message | none yet | `alert`, `alert-*`, `btn-close` + Bootstrap Alert JS | To build |
| Badge / pill | `erp-pill`, `erp-status` | `badge` | Partial |
| Layout utilities | `erp-grid`, `erp-home-grid`, `erp-stack` (to add) | `row`, `col-*`, `d-flex`, `gap-*`, `m*-*`, `p*-*` | To build |
| Sidebar drawer (phones) | `erp-sidebar` | Bootstrap Offcanvas JS | To build (native `<dialog>`) |

## Order of work

1. **Admin home** (`feature/admin-home`): Overview done; PRs 2–4 (Attendance, Academics, Parents tabs) are built Bootstrap-free with the guard test extended to each tab.
2. ~~Before PR 2: merge the card names into `erp-card` and the empty states.~~ Done: `erp-card` and `erp-card-empty` on the Overview.
3. **Then by area, alongside planned work:** forms (`erp-field`), tables, alerts (+ replace Alert JS), badges, layout utilities.
4. **Shell last:** sidebar Offcanvas → `<dialog>`, top bar, Guardian Portal shell, server-error page.
5. **Remove Bootstrap** only when a repo-wide guard test finds no Bootstrap class or `data-bs-` attribute, and after the checks listed in `BOOTSTRAP_REMOVAL_NOTE.md` (desktop, phone, print, keyboard, high contrast, no JS).

## Size of the job (2026-11-19 count, 216 templates)

| Bootstrap use | Templates |
|---|---|
| Buttons (`btn`) | 135 |
| Spacing / display utilities | 111 |
| `visually-hidden` / `text-muted` | 93 |
| Grid (`row`, `col-*`) | 75 |
| Tables | 73 |
| Alerts | 40 |
| Badges | 30 |
| Form controls | 19 |
| JS (`data-bs-`, offcanvas, collapse) | 6 |
