# Admin Overview in the Tabler dashboard look — plan

Status: **PLAN, decisions settled 2026-10-25; for a future implementation gate. No code written.** Branch `docs/overview-tabler-look-plan` from `main` (`25d8caf`).
Reference: the Tabler dashboard, https://tabler.io/admin-template/preview and its Fluid vertical variant (saved in memory as `tabler-admin-template-reference`): a welcome card, a row of KPI cards, small stat cards with coloured icon squares, then charts.
Out of scope: KPI numbers that do not exist today, charts (our `UI_DESIGN_RULES.md` and the attendance-reports test ban invented numbers and charts), trend arrows, illustrations, the sidebar shell change (see `docs/ADMIN_FLUID_VERTICAL_SHELL_PLAN.md`, independent but visually complementary), any new query, model or permission change.

## What a survey found
- The Overview (`core/templates/core/admin_overview.html`, view `core/views.py::admin_overview`, data `core/dashboard.py`) shows: a page header ("School administration" / "Overview" / "What needs attention today."), the setup checklist first only while a foundation step is missing, "Needs attention" cards for non-zero counts (`partials/_stat_card.html`, tone `attention` with a 4px left accent), a compact "Nothing waiting" link row for zero counts, an all-clear line when nothing needs attention, and the setup checklist last once the foundation is complete.
- Card keys come from `core/dashboard.py` (attendance, applicants, publications, access_reviews, notifications, ...), each with `title`, `count`, `summary`, `url`, `detail`, `tone`. Counts reuse the destination page's own data, so the card and its link cannot disagree.
- Tests pin: one `btn btn-primary btn-sm mt-auto` per page and exactly one `btn-primary` in the attention section (`test_ui_admin_phase2.py:111,242`), `Nothing needs attention today.`, the setup checklist markup (`test_ui_admin_setup_checklist.py`), and card h3 titles.

## Decisions (settled)
1. **Look only, with our own data.** No new numbers, no new queries, no charts.
2. **Welcome card** at the top (Tabler's hero card): "Welcome back, {first name or username}", today's date, the school name and current academic year, and one summary line ("N items need attention" or the existing "Nothing needs attention today."). No illustration.
3. **Attention cards become Tabler-style stat cards:** a coloured icon square (brand wash with brand icon) per card key, the count as the large value, the title as a small-caps label, summary and detail below, and the single primary "Open" button as today.
4. **Setup checklist stays a card**, restyled only by the shared card styles (no logic change).

## Design
- **Welcome card** (new `templates/partials/_overview_welcome.html`, `.erp-welcome` in `erp.css`): grid with the greeting and date on the left and the school/year meta on the right; shown only on the Overview; the summary line uses `attention_cards|length` already in the context (no new context). The page header stays (overline + title) above it. Greeting name from `request.user.get_short_name` falling back to `username` (template filter chain, no new view code); date formatted with the existing date style (`d M Y`).
- **Stat cards** (`partials/_stat_card.html`): add `<span class="erp-stat-icon" aria-hidden="true">` containing `{% include "partials/_icon.html" with name=card.icon only %}`; `core/dashboard.py::_card` gains an `icon` key (a fixed name per card key, reusing existing glyphs: attendance, applicants, results/stale, access, queue). The h3 title, count, summary, detail and the `btn ... mt-auto` Open button markup stay as they are so the pinned counts hold. CSS: `.erp-stat-icon` 2.5rem rounded square with `--erp-brand-wash` background and `--erp-brand` colour; the `.erp-stat-card--attention` left accent is replaced by the icon square (tone still `attention`/`clear` for the "Nothing waiting" row).
- **Layout:** the welcome card spans the full width, then the attention cards sit in the existing auto-fill grid (15rem to 22rem cards). No overlap with the Fluid vertical shell work.
- **No new colours or tokens:** uses `--erp-brand*`, `--erp-surface`, `--erp-rule`, `--erp-radius`.

## Constraints
- Keep the exact strings tests assert: `Nothing needs attention today.`, `btn btn-primary btn-sm mt-auto` (once), only one `btn-primary` in the attention section, the card h3 titles, the setup checklist markup and classes, and the `Needs attention` / `Nothing waiting` headings.
- The icon is decorative (`aria-hidden`), never the only signal; counts and titles stay as text.
- Do not change the foundation-incomplete ordering rule (`setup_first`) or `core/dashboard.py` counts.
- Scope CSS to the new classes; do not touch protected rules (`.erp-toolbar {`, the 575.98px phone rule, `.btn-outline-secondary {`, table-scroll rules, token blocks).
- Phones: cards stack in one column, the welcome card stays readable at 360px, no horizontal overflow.

### Task 1: Welcome card
Files: `templates/partials/_overview_welcome.html` (new), `core/templates/core/admin_overview.html`, `static/css/erp.css`, tests.
Done when: the Overview shows the welcome card with the user's name, today's date, school name and current year (each omitted gracefully when missing), the summary line shows the attention count or the existing all-clear sentence (the old standalone all-clear paragraph is removed so the sentence appears once), and tests cover: with attention cards, with none, no school row, no academic year, a user with no first name.

### Task 2: Stat cards with icon squares
Files: `core/dashboard.py` (`icon` per card key), `templates/partials/_stat_card.html`, `static/css/erp.css`, tests.
Done when: every attention card renders its icon square beside the label; each card key has a known icon (a test fails if a new card key has none); pinned counts and strings still pass; the left accent border rule is removed from `.erp-stat-card--attention` without changing the clear-row styles.

### Task 3: Layout and polish
Files: `static/css/erp.css`, tests.
Done when: the welcome card and cards align on a common grid at 1366px and stack at 390px, the setup-first state (new school) still shows the checklist above the welcome summary correctly, and the setup-complete state matches the earlier Overview layout rules.

## Verification (after all tasks)
`manage.py check`, touched modules, then the full suite (`--parallel 4`; known flaky tests unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, drop afterwards) at 1366x768 and 390x800: the Overview with attention cards, with none, and for a fresh school (setup-first); compare against the Tabler dashboard screenshot for rhythm (card spacing, label style, icon squares). Rollback = revert the PR; no migrations.
