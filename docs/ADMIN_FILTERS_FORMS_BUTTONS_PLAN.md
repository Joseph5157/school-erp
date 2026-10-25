# Admin filters, forms and buttons (UI-08, UI-15) — plan

Status: **PLAN, decisions settled 2026-10-25; awaiting review before execution.** No code written. Branch `docs/ui-08-15-plan` from `main` (`6bb736e`).
Source: Admin Desktop UI/UX audit items UI-08 (Medium, "filter and form density varies") and UI-15 (Low, "button hierarchy and radii").
Out of scope: palette (UI-10), header (UI-11), icons (UI-16), sticky table headers, converting the other ~60 admin forms to a grid, Teacher and Guardian-portal pages, any model/migration/route/permission change.

## What a survey found (so the plan is smaller than the audit suggests)
- **Attendance filters.** The audit says they wrap to two rows at 1366px. They do, but only once a filter is applied: the "Clear filters" link then pushes the buttons onto a second row. The bar has no page modifier, so its fields get the default 18rem basis (3 x 288px + gaps + buttons is about 1090px against about 1003px available). Four other toolbars already use an 11rem/17rem field rule that fits.
- **No filter-bar component.** `.erp-toolbar` / `.erp-toolbar--inline` is the shared pattern, with six per-page modifier classes that each only override the field basis (four of them identical). The six classes are asserted verbatim by tests, so they stay in the markup.
- **Forms are one stacked 46rem column everywhere.** There is no form grid. The Assessment add form has 7 short fields (Term, Subject, Section, Name, Date, Max marks, Pass mark) in one column.
- **Buttons.** Bootstrap 5.3.3 supplies radius, height and padding; `erp.css` only overrides colours. `.btn` is 6px, `.btn-sm` is 4px (about 30 files use it). Desktop buttons are about 38px high next to 44px fields. Cancel is `btn-link` in 44 of 44 places, which is already consistent.
- **Filter submit buttons.** Most are `btn-outline-secondary`; three pages differ (`attendance_summary` and `document_report_cards` use `btn-primary`, `academic_year_calendar` uses `btn-outline-primary`).
- About 28 test files mention `btn-` classes. A CSS-only restyle breaks none of them; removing or renaming classes in markup would.

## Decisions (settled)
1. **Radius: 6px for every button** (`btn`, `btn-sm`, `btn-lg`), matching `--erp-radius-sm` and `UI_DESIGN_RULES.md` section 3.
2. **Height: 40px buttons, 32px small buttons on desktop.** Form fields on desktop drop from 44px to 40px so toolbar rows line up. Phones keep the 44px touch targets (existing rules at max-width 767.98px stay).
3. **Filter submit buttons are `btn-outline-secondary`.** The three odd pages change to match. Cancel/Back stay `btn-link`.
4. **Form grid: Assessment form only.** Build a reusable `.erp-form-grid`; other forms opt in later.
5. Defaults taken without asking (reversible): the six per-page toolbar modifier classes stay in the markup and the CSS blocks are left as explicit overrides; plain `erp-toolbar` search bars on Students/Teachers/Applicants are not converted.

## Design
- **Buttons (CSS only, `static/css/erp.css`).** Add button tokens in `:root`: `--erp-btn-radius: var(--erp-radius-sm)`, `--erp-btn-height: 2.5rem` (40px), `--erp-btn-height-sm: 2rem` (32px). Under `@media (min-width: 768px)`: `.btn { --bs-btn-border-radius: var(--erp-btn-radius); min-height: var(--erp-btn-height); }` and `.btn-sm { --bs-btn-border-radius: var(--erp-btn-radius); min-height: var(--erp-btn-height-sm); }`; `.btn-lg` gets the radius only. Radius is not media-scoped. Do not touch the colour-variable blocks (`.btn-primary`, `.btn-outline-primary`, `.btn-outline-secondary`, disabled).
- **Desktop field height.** `.erp-field :where(input, select, textarea)` keeps `min-height: 2.75rem` as the base (phones) and uses `var(--erp-btn-height)` from 768px up. Textareas are excluded from the height change.
- **Toolbar fields.** `.erp-toolbar--inline > .erp-field` becomes `flex: 1 1 11rem; max-width: 17rem` (the value four toolbars already use), so the bare inline toolbar fits at 1366px with Section + Start + End + "Filter" + "Clear filters". The `erp-grading-toolbar` and `erp-publication-toolbar` overrides keep their own bases. Keep the phone rule at max-width 575.98px verbatim.
- **Form grid.** `.erp-form-grid` is a CSS grid, 1 column by default, 2 columns from 992px (`repeat(2, minmax(0, 1fr))`, gap 0 1rem), with `.erp-field--full` to span both columns. It is allowed to exceed the 46rem reading width (cap at 60rem) only when the form carries the grid class.

## Constraints
- Do not reformat these rules (tests assert them verbatim): `.erp-toolbar {` block and the 575.98px phone rule (`test_ui_admin_desktop_d0.py:72-81`); the `.btn-outline-secondary {` block with `var(--erp-ink)` and `var(--erp-ink-soft)` (`test_ui_admin_phase3e.py:70-110`); `.erp-panel > .erp-table-scroll { border-radius: 0; scrollbar-gutter: auto; }`; `.erp-table-scroll:focus-visible`.
- Keep the exact toolbar class strings the tests pin: `class="erp-toolbar" role="search"`, `<form method="get" class="erp-toolbar erp-toolbar--inline" `, `erp-toolbar erp-toolbar--inline erp-attendance-report-toolbar`, the document-toolbar form tag, and `class="erp-form-actions"`.
- Existing button class strings in markup do not change except on the three filter-button pages, whose tests are updated deliberately (see Task 3).
- New CSS is scoped to its own class; do not add unscoped rules that touch `.erp-section-title` or other shared headings.
- Phone behaviour must not regress: 44px targets and the full-width primary button in `.erp-form-actions` stay.

### Task 1: Button tokens and the toolbar field basis
Files: `static/css/erp.css` (`:root`, the `.btn` area near the button colour blocks, `.erp-field` input rule ~642-653, toolbar rules ~1215-1225), new `core/tests/test_ui_button_tokens.py`.
Add the three tokens and the desktop `.btn`/`.btn-sm` rules; set the desktop field height; change the bare inline toolbar field basis as above.
Done when: the CSS-text test asserts the token values, the radius rule on `.btn`/`.btn-sm`/`.btn-lg`, the 768px min-height rules, the new toolbar basis, and that the protected rules above are unchanged; no existing test changes; `manage.py check` clean.

### Task 2: Form grid and the Assessment form
Files: `static/css/erp.css` (new `.erp-form-grid`, `.erp-field--full`), `core/templates/core/assessment_form.html` (7 fields), `core/tests/test_ui_admin_desktop_d1_5b_assessments.py` (or the module that covers this form).
Render the Assessment fields in the grid in this order: Term + Section, Subject (full width), Name (full width), Assessment date + Maximum marks, Pass mark (with its help text). Keep the required legend, error summary and the `.erp-form-actions` footer outside the grid and unchanged. Do not change `AssessmentForm` or any field name/order logic.
Done when: the form renders every field exactly once with the same names, labels and errors; the page is at most about 600px tall at 1440 (was ~974px); a test asserts the grid class, one `erp-field--full` per full-width field, and that the actions footer sits after the grid; existing form POST tests pass unchanged.

### Task 3: Filter submit buttons
Files: `core/templates/core/attendance_summary.html`, `document_report_cards.html`, `academic_year_calendar.html`, and `test_ui_admin_desktop_d1_6c_documents.py` for the affected assertions only.
Change the filter submit class on these three pages to `btn btn-outline-secondary` (keeping the label, `type` and any extra classes). Leave Back/Cancel as `btn btn-link` everywhere.
Done when: the three pages render `btn-outline-secondary` on the filter submit, tests for those pages are updated minimally and assert the new class, and no other page's markup changes.

## Verification (after all tasks)
`manage.py check`, the touched test modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order` and one date-dependent test are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, drop afterwards) at 1366x768 and 390px: Attendance list with a filter applied (one row, no wrap), Assessment add form (height, two columns), a table-row `btn-sm`, Students toolbar, a form footer, attendance summary. Measure computed `border-radius` (6px), `.btn` height (40px) and `.btn-sm` (32px) at 1366 and 44px at 390. Rollback = revert the PR; no migrations.
