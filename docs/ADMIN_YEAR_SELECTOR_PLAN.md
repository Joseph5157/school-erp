# Admin academic-year selector (UI-04 remainder) — plan

Status: **PLAN, decisions settled 2026-10-25; awaiting review before execution.** No code written. Branch `docs/ui-04-year-selector-plan` from `main` (`720da52`).
Source: Admin Desktop UI/UX audit item UI-04 ("preserve year scoping through a visible academic-year selector"). The nav group and year links already shipped; the selector did not.
Out of scope: storing a "working year" (session or cookie), changing which year the sidebar links or the Students list use, past/future-year locking or a closed-year concept, Teacher and Guardian selectors, any model/migration/permission change.

## What a survey found
- "Current year" is date-derived (`core/academic_years.py::current_academic_year`: the year containing today, else the latest). There is no status, archived or closed flag on `AcademicYear`, and no user preference storage.
- Only three sidebar links take a year (Assessments, Subject/Section results, Grading scales); they always point at the auto-current year. About 24 `academic-years/<int:pk>/...` URL patterns are year-scoped, plus child-object pages that derive the year from the object. Everything else (Students, Attendance, Applicants, ...) is year-independent or silently uses the current year.
- The header already shows the year as a plain read-only chip (UI-11, `templates/base.html`), pinned by `core/tests/test_ui_header_context.py` (exact chip markup, no `core_academicyear` queries on the login page, empty for the Guardian portal).
- Year-scoped pages show no note when the year is not current; the only flag is `year_is_current` in one template.
- Users move between years today only through the Academic Years list (`.erp-year-links`, asserted by `test_ui_admin_desktop_d0.py`).

## Decisions (settled)
1. **Design A: a header dropdown that navigates.** It lists the years; choosing one opens the **same page for that year** when the current URL is year-scoped, otherwise the Academic Years list. No new storage; the sidebar keeps following the date-derived current year.
2. **A quiet note** on year-scoped pages when the year being viewed is not the current year. No locking.
3. **Admin only.** Teachers keep the plain chip; the Guardian portal and login/403 pages are unchanged.
4. **On phones the selector lives in the sidebar drawer** (offcanvas), because the header chip is hidden below 768px.

## Design
- **Year switching helper** (`core/academic_years.py`): `year_switch_url(resolver_match, year)` returns `reverse(url_name, kwargs={**kwargs, "pk": year.pk})` (query string dropped) when `resolver_match.url_name` is in an explicit allow-list of year-scoped names whose `pk` kwarg is the **year** pk; otherwise `reverse("core:academic-year-list")`. The allow-list is a module constant. Child-object pages (assessments, grading scales, terms, offerings, calendar days, class-teacher rows, report cards) are NOT in it and fall back to the list. Year-scoped URLs with extra kwargs (e.g. `timetable/sections/<section_pk>/`) fall back to the same year's sections list URL instead of reusing the section pk (tests define which names map where).
- **Context** (`core/context_processors.py`, admin area only, signed-in): `year_choices` = list of `{name, url, selected}` for all years ordered newest first (one query, shared with the existing current-year lookups where possible), plus `viewing_year_name` and `viewing_year_is_current` when the request is an allow-listed year-scoped page (year pk from the URL kwarg). Anonymous, Guardian, Teacher and 403-without-area requests get no new queries and empty values.
- **Header** (`templates/base.html`, `static/css/erp.css`): the existing `.erp-topbar-year` chip becomes the `<summary>` of a JS-free `<details class="erp-year-menu">` (same pattern as `_account_menu.html`), keeping the exact inner chip markup (`<span class="visually-hidden">Academic year </span>NAME`) and `d-none d-md-inline` visibility. The panel lists years as links with `aria-current="true"` on the selected one. The chip shows the **viewing** year on a year-scoped page, otherwise the date-derived current year. Rendered as a menu only for admins with more than one year; with exactly one year the chip stays plain text.
- **Sidebar drawer** (`templates/partials/_sidebar.html`): an "Academic year" row at the top of the offcanvas body, visible only below 992px (`d-lg-none`), with the same year list as simple links.
- **Note** (new `templates/partials/_year_note.html`): `<p class="erp-year-note" role="note">You are viewing 2025-26, not the current year (2026-27).</p>` when `viewing_year_is_current` is false. Use one include point (the `base.html` content wrapper) so the 24 year-scoped templates are not edited. CSS scoped to `.erp-year-note`, existing tokens only.

## Constraints
- Keep the exact asserted chip markup `class="erp-topbar-year` with `<span class="visually-hidden">Academic year </span>2026-2027</span>` (test_ui_header_context): wrap it, do not change it. Update only the assertions the wrapping genuinely breaks, and say which.
- Login/anonymous pages must still run no `core_academicyear` queries; Guardian portal shows no selector; Teacher pages keep the plain chip.
- Keep `office_nav(...)` signatures (`year` stays a keyword); do not change nav year-link behaviour (`test_year_links_open_the_current_year`).
- Do not touch protected rules (`.erp-toolbar {`, the 575.98px phone rule, `.btn-outline-secondary {`, table-scroll rules) or pinned test strings; `.erp-year-links` (Academic Years list) stays as is.
- No JS; accessible: the summary has visible text, links are real links, `aria-current` on the selected year.
- New CSS scoped to its own classes; no new colours.

### Task 1: Year switch helper and context
Files: `core/academic_years.py`, `core/context_processors.py`, new `core/tests/test_ui_year_selector_context.py`.
Add the allow-list, `year_switch_url`, and the context values. Tests: (a) every `academic-years/<int:pk>/...` URL name in `core/urls.py` is either in the allow-list or in a documented exclusion set (the test parses the URL patterns so a new year-scoped URL forces a decision); (b) an allow-listed page keeps its url_name and swaps the pk; (c) non-allow-listed and child-object pages fall back to the Academic Years list; (d) admin context lists all years newest first with the correct selected one; (e) no years gives empty values; (f) anonymous/guardian/teacher get no `year_choices` and run no extra queries; (g) the viewing flag is false for a past year and true for the current one.
Done when: new tests pass, existing tests pass unchanged, `manage.py check` clean.

### Task 2: Header dropdown and drawer row
Files: `templates/base.html`, `templates/partials/_sidebar.html`, `static/css/erp.css` (`.erp-year-menu*`), `core/tests/test_ui_header_context.py` (only assertions the wrapping breaks), new `core/tests/test_ui_year_selector_ui.py`.
Render the dropdown and the drawer row. Tests: admin with 2+ years sees `<details class="erp-year-menu">` with year links and `aria-current` on the selected one; exactly 1 year keeps a plain chip; teacher and portal render no menu; the drawer row exists with `d-lg-none`; chip inner markup unchanged.
Done when: the topbar stays 56px, the menu does not overflow at 1366 or narrow desktop widths, it opens from the keyboard, and existing header tests pass.

### Task 3: "Not the current year" note
Files: `templates/partials/_year_note.html`, the single include point, `static/css/erp.css` (`.erp-year-note`), tests.
Show the note on year-scoped admin pages when the year is not current; never on year-independent pages and never for the current year.
Done when: tests cover a past year, a future year, the current year (no note) and a non-year page (no note), and no year-scoped template is edited.

## Verification (after all tasks)
`manage.py check`, touched modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order`, `test_toolbar_fields_labels_and_no_defaults` and one date-dependent test are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, add a second past year, drop afterwards) at 1366x768 and 390px: open the menu on Assessments and switch years (same page, new year), switch from a non-year page (lands on Academic Years), switch from a child-object page (falls back), the note on the past year and none on the current, the drawer row on phones, topbar still 56px, a single-year school shows a plain chip, login page and a Teacher page show no menu. Rollback = revert the PR; no migrations.
