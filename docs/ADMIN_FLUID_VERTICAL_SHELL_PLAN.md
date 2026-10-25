# Admin "Fluid vertical" shell, section labels, action icons and fluid content — plan

Status: **PLAN, decisions settled 2026-10-25; for a future implementation gate. No code written.** Branch `docs/fluid-vertical-shell-plan` from `main` (`25d8caf`).
Reference: Tabler "Fluid vertical" layout, https://preview.tabler.io/layout-fluid-vertical.html (saved in memory as `tabler-admin-template-reference`). It is a full-width left sidebar with the brand at the top and the account block pinned at the bottom, no separate top bar, small-caps section labels, an outline plus a filled-with-icon action pair in the page header, and a fluid card grid.
Out of scope: Teacher area (top links + bottom tab bar), Guardian portal (`templates/portal/base.html`), login/403/404/password-change pages (they keep the current top bar), dark mode, KPI trend arrows or new overview data, replacing the drawer with a bottom tab bar, any model/migration/permission change.

## What a survey found
- `templates/base.html` is shared by admin, Teacher, login, 403, 404 and password change; the Guardian portal has its own template but uses the same `.erp-topbar` CSS and `_account_menu.html`. Admin pages get `body.has-sidebar` (when `office_nav` is non-empty); Teacher gets `erp-teacher has-tabbar`.
- The 56px `header.erp-topbar` holds, in order: hamburger (below 992px), brand (`School ERP`, optional logo), school name, year chip or year menu, spacer, account menu. The sidebar is fixed from 992px at `top: var(--erp-topbar-h)`, width 15.5rem, and an offcanvas drawer below that (which also carries the phone year list `.erp-year-drawer`).
- `--erp-topbar-h` is used in three other places that must change: the sidebar top (`erp.css` ~256-260), the messages toast offset at 992px and up (~561-565) and `scroll-margin-top` of `.erp-main section[id]` (~1058-1059).
- The sidebar is about 22 links in 7 groups: roughly 540-580px in the default state (Home + active group open) and about 1130px fully expanded (estimates, no browser measure). At 768px viewport height a pinned brand (~64px) and user block (~64px) leave about 640px for the scrolling middle.
- The account menu and the year menu are JS-free `<details>` dropdowns whose panels open **downward and are absolutely positioned**: inside a scrolling container they would be clipped, so the sidebar header and footer must sit outside the scrolling area, and the account panel must open upward at the bottom.
- Tests are cheap to keep green: nothing pins `.erp-topbar`, `erp-spacer` or `<header class="erp-topbar">`. Constraints are in the section below.

## Decisions (settled)
1. **Sidebar shell (admin only):** brand + school name + year menu under the logo at the top of the sidebar (pinned, outside the scroll area); the account menu pinned at the bottom (opens upward); no desktop top bar. Below 992px a slim top bar keeps the hamburger, the brand and the account menu so phones are unchanged in behaviour.
2. **Section labels:** the existing group headings get Tabler-style small-caps labels (mostly CSS on `.erp-nav-heading`; no group renames).
3. **Primary action icons:** a "+" icon beside the primary action in the page header (`partials/_page_header.html`, the Add/New/Create buttons), label always kept, `aria-hidden` icon.
4. **Wider fluid content:** relax the 46rem cap only where a two-column grid exists (`.erp-form-grid`), and let list/panel pages fill the width (they already do). No new form grids in this gate.
5. Defaults taken (reversible): Teacher and Guardian shells unchanged; login/403/404/password-change keep the brand top bar; the phone year list `.erp-year-drawer` is replaced by the same year menu inside the sidebar header (one control for all widths, tests updated deliberately).

## Design
- **Scoping.** Every new rule is scoped to `body.has-sidebar` so Teacher, Guardian and no-sidebar pages are untouched.
- **Sidebar layout** (`templates/partials/_sidebar.html`, `static/css/erp.css`): the sidebar becomes a flex column: `.erp-sidebar-head` (brand anchor ending in `School ERP</a>` with the existing `erp-brand-logo`, the `erp-topbar-school` span, the year menu/chip with the exact existing markup), `.erp-sidebar-body` (`flex: 1; overflow-y: auto`, the nav groups), `.erp-sidebar-foot` (the account menu include). From 992px: `position: fixed; top: 0; bottom: 0; left: 0; width: var(--erp-sidebar-w)`; `body.has-sidebar .erp-topbar { display: none }` at 992px and up. Below 992px the offcanvas shows the same three blocks and the slim top bar stays.
- **Account panel at the foot:** scoped override `.erp-sidebar .erp-account-panel { top: auto; bottom: calc(100% + .4rem); left: 0; right: auto; width: calc(var(--erp-sidebar-w) - 1rem) }`; optional small `erp.js` addition to close open `<details>` menus on Esc / outside click (the sidebar head and foot menus).
- **Offsets:** messages toast at 992px and up becomes `top: 1rem` for `body.has-sidebar`; `.erp-main section[id]` scroll-margin drops the top-bar term at 992px and up for `body.has-sidebar`.
- **Section labels:** `.erp-nav-heading` gets uppercase, `letter-spacing`, small token size and `--erp-ink-soft`, as in Tabler; chevron and badge behaviour unchanged; sticky heading background unchanged.
- **Primary action icon:** `_page_header.html` renders `{% include "partials/_icon.html" with name=primary_icon only %}` before the label of `primary_url` when a new `primary_icon` variable is set, so only Add/New/Create call sites opt in (`primary_icon="plus"`); add one `plus` glyph to `_icon.html` (16px, class `erp-btn-icon`, inline-flex with a gap on `.btn`).
- **Fluid content:** `.erp-form.erp-form-grid` cap moves from 60rem to the full content width capped at 80rem; plain `.erp-form` stays 46rem (reading width).

## Constraints
- Keep: `School ERP</a>` anchor text (`test_school_logo.py`), `class="erp-brand-logo"`, `class="erp-topbar-school`, the chip markup `<span class="visually-hidden">Academic year </span>NAME</span>`, `<details class="erp-year-menu`, `aria-current="true"` on the selected year, `id="erp-sidebar"`, `class="erp-account"` (also on the Guardian 403), `erp-menu-btn` markup (`test_ui_hamburger.py`), `erp-nav-group` order and `.erp-sidebar .nav-link.active::before` / `{` blocks with `var(--erp-brand)` (palette and d0 tests).
- Tests to update deliberately (not by loosening): `test_ui_year_selector_ui.py` (the phone `erp-year-drawer d-lg-none` block is replaced by the single year menu in the sidebar head; keep the "year control before the nav groups" intent), and the exact-string assertions of primary buttons that gain an icon (`<a class="btn btn-primary" href="...">Create Guardian</a>` in `test_ui_admin_desktop_d1_3a.py`, `New notice` in d1_6b, and any others the implementer finds by grepping `btn btn-primary" href`).
- Teacher (`nav.erp-topbar-links`, `has-tabbar`) and the Guardian portal must render byte-identically in their headers; add tests for it.
- Login, 403, 404 and password change keep a top bar with the brand and (when signed in) the account menu; the admin 403 keeps the sidebar (`test_403_neutral_shell.py`).
- Protected rules and pinned CSS strings stay verbatim (`.erp-toolbar {`, the 575.98px phone rule, `.btn-outline-secondary {`, table-scroll rules, `--erp-btn-*`/`--erp-table-*`/palette tokens).
- Phone behaviour: hamburger 44px, drawer opens as today; the drawer must show head, scrolling body and foot (flex column inside `.offcanvas-body`), with the account menu reachable without scrolling the nav.
- No JS dependency for the menus to work; the small close-on-Esc script is an enhancement only. Focus order: skip link, (hamburger on phones), sidebar head, nav groups, account menu foot, main.
- New CSS scoped to its own classes; no new colours.

### Task 1: Sidebar shell (head, scrolling body, account foot, no desktop top bar)
Files: `templates/base.html`, `templates/partials/_sidebar.html`, `static/css/erp.css`, `static/js/erp.js` (optional close handler), tests.
Done when: at 992px and up for an admin the top bar is not displayed, the brand, school name and year menu are at the top of the sidebar and the account menu at the bottom (panel opens upward and is not clipped), the nav groups scroll between them at a 768px viewport height with the active link scrolled into view, and messages/anchor offsets no longer reserve top-bar space; below 992px the slim bar (hamburger, brand, account) and the drawer (head, body, foot) work; Teacher, Guardian, login and error pages are unchanged; the header-context, year-selector, logo, 403 and foundation tests pass (updated only where listed in Constraints).

### Task 2: Section labels
Files: `static/css/erp.css` (`.erp-nav-heading`), tests.
Done when: group headings render as small-caps labels with the existing chevron and badge behaviour, no wrap or overflow at the 15.5rem width (longest: "Assessments & Results", "Access and security"), and a CSS-text test pins the label style.

### Task 3: "+" icon on primary page-header actions
Files: `templates/partials/_page_header.html`, `templates/partials/_icon.html` (add `plus`), `static/css/erp.css`, the templates that render Add/New/Create primary actions (grep `primary_url=` and pass `primary_icon="plus"` for the creation actions only), tests.
Done when: every creation action in a page header shows the icon before its visible label (icon `aria-hidden`), Save/Submit/non-creation actions are untouched, label text and hrefs are unchanged, and the pinned exact-string assertions are updated deliberately with a note listing each.

### Task 4: Fluid content width
Files: `static/css/erp.css` (`.erp-form.erp-form-grid` cap), tests.
Done when: the Assessment form (the only grid form) uses the wider cap without its fields stretching past a readable length (inputs max out inside their grid cell), plain `.erp-form` pages stay at 46rem, and a CSS-text test pins both.

## Verification (after all tasks)
`manage.py check`, touched modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order`, `test_toolbar_fields_labels_and_no_defaults` and one date-dependent test are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, add a second year, drop afterwards) at 1366x768, 992x768 and 390x800: sidebar head/body/foot, account menu panel opening upward fully visible, year menu panel, active link scrolled into view, no top bar at desktop, slim bar + drawer on phones, messages toast position, a page with in-page anchors, section labels without wrapping, "+" icons on Add/New buttons, the Assessment form width; Teacher (as a teacher), Guardian portal and login page unchanged. Rollback = revert the PR; no migrations.
