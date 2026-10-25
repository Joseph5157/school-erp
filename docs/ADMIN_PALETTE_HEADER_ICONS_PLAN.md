# Admin palette, header, icons and Import placement (UI-10, UI-11, UI-16, UI-09 remainder) — plan

Status: **PLAN, decisions settled 2026-10-25; awaiting review before execution.** No code written. Branch `docs/ui-10-11-16-plan` from `main` (`6b3fba3`).
Source: Admin Desktop UI/UX audit items UI-10 (Medium, "one green family for brand, action and success"), UI-11 (Medium, "global header adds little"), UI-16 (Low, "no icon system") and the open part of UI-09 (Import placement).
Out of scope: a new navy/teal brand (a later one-line value change once tokens are split), a per-school brand colour (needs an ADR and a School field), dark mode, an academic-year selector (needs storage and URL semantics, a gate of its own), icons on action buttons, Guardian-portal header changes, command/search entry, any model/migration/permission change.

## What a survey found
- **Palette.** One accent trio (`--erp-accent #1f6b52`, `-strong #185842`, `-wash #e3efe9`) is brand, links, primary buttons, active nav, avatar, progress and focus-adjacent colour. `--erp-ok*` are only *aliases* of that trio, so recolouring the accent would silently recolour every success state. Focus is a different green (`--erp-focus-color #0b6e4f`). `--bs-primary` and `--bs-primary-rgb` (`31, 107, 82`) are hard-coded separately. Status chips (`erp-status--*`) already use their own warn/bad/info tokens; a few tones used in templates ("marks", "attendance") have no CSS rule and fall back to neutral. Teacher and Guardian pages share the same CSS.
- **Header.** `templates/base.html` has a 56px sticky topbar with the text "School ERP" (and optional logo), Teacher tabs, and the account menu. The context processor `core.context_processors.roles` exposes `brand_logo` (including the school name) but not the school name as text, and not the current academic year. The year comes from `core/academic_years.py::current_academic_year()` (the year containing today, else the latest). `test_school_logo.py:478,483` pins `School ERP</a>`.
- **Icons.** The only icon in the codebase is the Teacher tab-bar inline SVG (`templates/partials/_tab_icon.html`). Office sidebar links have no icon; `NavLink.icon` already exists in `core/navigation.py` and `.erp-sidebar .nav-link` is already flex with a gap. No CSP, so inline SVG is fine.
- **Navigation.** "Assessments & Results", "Message queue" and year-aware links already exist. Import still sits under Admissions.

## Decisions (settled)
1. **Palette: split tokens, no visual change.** Add `--erp-brand*` and `--erp-action*` tokens with today's values, give success its own literal hexes, keep everything looking identical.
2. **Header: school name + read-only year chip.** Keep "School ERP" as the brand text; add the school name beside it and the current academic year as a chip. Admin and Teacher header only; hidden on phones; Guardian portal unchanged.
3. **Icons: inline SVG, sidebar only,** always beside the visible label, `aria-hidden`.
4. **Import moves to a new "Data tools" group.**
5. Defaults taken (reversible): focus colour stays distinct (`#0b6e4f`); no dark mode; unmapped status tones are left as they are and logged.

## Design
- **Tokens.** In `:root` add `--erp-brand`, `--erp-brand-strong`, `--erp-brand-wash` and `--erp-action`, `--erp-action-strong`, `--erp-action-wash`, each initially `var(--erp-accent...)`, **except** that `--erp-ok`, `--erp-ok-strong`, `--erp-ok-wash` become literal hex copies of today's values (`#1f6b52`, `#185842`, `#e3efe9`) so they no longer alias the accent. Re-point: active nav, topbar links, avatar and brand-ish uses to `--erp-brand*`; primary button, outline-primary, links, chips/pagination/segmented fills and `--bs-primary`/`--bs-link-color` to `--erp-action*`; keep `--erp-accent*` defined (tests read them) as aliases of action. `--bs-primary-rgb` stays in sync with the action value.
- **Header.** `core/context_processors.py` adds `school_name` (text) and `current_year` (name) for signed-in office/teacher areas, reusing the existing School and `current_academic_year()` lookups (no new queries beyond one cached each). In `templates/base.html` the topbar keeps `<a class="erp-brand">…School ERP</a>`; after it, a muted `<span class="erp-topbar-school">` with the school name and, when a year exists, `<span class="erp-topbar-year">` chip ("2026-27"). Both `d-none d-md-inline`, no layout change to the 56px height.
- **Icons.** One inline-SVG partial `templates/partials/_icon.html` (16px, stroke `currentColor`, 1.75 stroke width, `aria-hidden="true"`, `focusable="false"`), glyphs for the sidebar links: overview, school, academic years, classes, subjects, timetable, teachers, applicants, students, guardians, import, attendance, reports, announcements, message queue, documents, assessments, results, grading, stale publications, access reviews, lockouts (reuse a glyph where a concept repeats). Rendered by `partials/_sidebar.html` before the label via the existing `NavLink.icon`. Teacher tab icons stay as is.
- **Data tools.** `core/navigation.py`: move the Import link out of Admissions into a new group "Data tools" (placed after Daily; permission unchanged).

## Constraints
- Do not rename or remove tokens read by tests: `--erp-accent`, `--erp-surface`, `--erp-ink`, `--erp-ink-soft`, `--erp-paper`, `--erp-focus-color`, `--erp-focus-ring`, `--erp-space-*`, `--erp-text-*`; tokens that `test_ui_admin_phase3e.py` parses must remain plain 6-digit hex in `:root`.
- Keep the `School ERP</a>` text (two `test_school_logo.py` assertions) and the existing nav link `href`s and labels exactly; tests mostly match by label and href.
- Existing CSS-text tests stay green unchanged: `.btn-outline-secondary {` block, `.erp-toolbar {` block and the 575.98px rule, protected table-scroll rules, `--erp-btn-*`/`--erp-table-*` values.
- Inline SVG only; no CDN, no icon font. Icons never replace labels (`UI_DESIGN_RULES.md` section on icons).
- CSS added for a page or component is scoped to its own class.

### Task 1: Split brand, action and success tokens (UI-10)
Files: `static/css/erp.css` (`:root`, `--bs-*` block, nav/avatar/button/link rules), new `core/tests/test_ui_palette_tokens.py`.
Add the six tokens and re-point the rules per Design with **no computed colour change** on any page. Make the `--erp-ok*` trio literal hex. Add a contrast test (reuse the helper in `test_ui_admin_phase3e.py`) for brand/action text on their washes and ok-strong on ok-wash (>= 4.5:1) and assert that `--erp-ok*` are not `var()` aliases and that action/brand default to the accent values.
Done when: the test passes, every existing test passes unchanged, and a browser check shows identical computed colours for primary button, link, active nav item, success chip and progress bar before and after.

### Task 2: Import under "Data tools" (UI-09)
Files: `core/navigation.py`, tests that list nav groups (find with Grep for `Admissions`/`Import` in `core/tests`).
Add the group and move the link. Update only assertions that pin group membership or order; add one test asserting Import's group and permission.
Done when: nav tests are updated minimally, the sidebar renders the new group for a user with the Import permission and hides it otherwise, and mobile nav still works.

### Task 3: Header school name and year chip (UI-11)
Files: `core/context_processors.py`, `templates/base.html`, `static/css/erp.css` (`.erp-topbar-school`, `.erp-topbar-year`), tests in a new `core/tests/test_ui_header_context.py`.
Add `school_name` and `current_year_name` to the context (admin and teacher areas, signed-in only) and render them as designed. Hidden below 768px. No year → no chip; no School row → no name.
Done when: tests cover (a) admin with school and year, (b) no year, (c) no School, (d) anonymous/login page unchanged, (e) Guardian portal header unchanged; the topbar stays 56px; `School ERP</a>` assertions pass unchanged.

### Task 4: Sidebar icons (UI-16)
Files: `templates/partials/_icon.html` (new), `templates/partials/_sidebar.html`, `core/navigation.py` (icon names), `static/css/erp.css` (`.erp-nav-icon`), tests.
Add the partial and glyphs, pass icon names through `NavLink.icon`, render before each sidebar label with `aria-hidden`. Active/hover colour inherits via `currentColor`. Do not alter hrefs or labels.
Done when: every office nav link shows an icon beside its label, the nav test files (~19 modules referencing sidebar markup) pass, a test asserts each link's label text is still present and the svg is `aria-hidden`, and the mobile offcanvas renders them.

## Verification (after all tasks)
`manage.py check`, touched modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order` and one date-dependent test are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, drop afterwards) at 1366x768 and 390px: Overview, Students, an Assessments page, Teacher area (as a teacher) and Guardian portal (to confirm no change); compare computed colours for primary button, link, active nav, success chip against `main`; confirm header height 56px, school name and year chip show at 1366 and hide at 390; confirm sidebar icons and the Data tools group; measure that no sidebar label wraps. Rollback = revert the PR; no migrations.
