# Admin list pagination (UI-07) — plan

Status: **PLAN, executed subagent-driven.** Branch `feat/ui-07-list-pagination` from `main` (`a332a0b`).
Source: Admin Desktop UI/UX audit item UI-07 (Medium).

## What the audit got right and wrong
The audit saw "pagination element count zero" on Students, Attendance and Assessments. Students, Teachers, Applicants and Attendance **already paginate** at 25 rows through `core/tables.py::build_table` and `templates/partials/_table_footer.html`; the footer nav is hidden when there is only one page, and staging has fewer than 25 rows. That part is a false positive. **Assessments** is a real gap, and a survey found two more unbounded, fast-growing admin lists: **Guardians** and the **Message queue**.

## Scope
In: Guardians list, Message queue ("to send" list), Assessments list. Each adopts the existing `build_table` pattern: 25 per page, result count, sortable headers where useful, filters preserved across pages.
Out (deferred, listed so nobody re-surveys): sticky table headers (the shared `.erp-table-scroll` wrapper is an `overflow-x` scroll container, so `position: sticky` would stick to that box, not the page; needs a design decision); student attendance history, teacher assignments, stale publications, pending access reviews (slower growth); capped lists (imports 50, announcements 100, documents 50). No models, migrations, routes, URL names or permissions change.

## Global constraints
- Reuse `core/tables.py` (`Column`, `build_table`, `parse_choice`) and the partials `_table_head.html` and `_table_footer.html`. Do not fork or edit them unless a task says so.
- Page size is `PER_PAGE` (25). A bad `page`, `sort` or filter value is clamped or ignored, never an error.
- Existing context keys the templates and tests use must keep working unless the task says otherwise.
- Match the surrounding code's comment density and naming. Django tests run with `manage.py test <module> --parallel 4` after loading the DB env vars from the Windows user scope (see memory `local-postgres-setup`). Use `.\.venv\Scripts\python.exe`.
- Tests live beside the existing tests for that page. Each task adds tests: page 1 and page 2 contents, count text, an out-of-range `page` clamps, filters survive in the pagination links, permission behaviour unchanged.
- Never touch Teacher or Guardian-area pages.

### Task 1: Guardians list
Files: `core/views.py` (`guardian_list`, around line 2202), `core/templates/core/guardian_list.html`, tests in the existing guardian list test module (find it with `grep -rl "guardian-list" core/tests`).
Today the view passes `Guardian.objects.all()` and the template renders its own `<thead>`.
Change: define `GUARDIAN_COLUMNS` next to the other `*_COLUMNS` in `core/views.py` with sortable Name (`full_name`, tiebreak by pk handled by `build_table`) and non-sortable Phone and Email; call `build_table(request, Guardian.objects.all(), GUARDIAN_COLUMNS, "name")`; pass `table` and keep `guardians` as `table.page`. Template: use `partials/_table_head.html` and `partials/_table_footer.html` exactly like `student_list.html`. Keep the empty-state row and the "Add guardian" action.
Done when: 26+ guardians show 25 on page 1 and the rest on page 2, the footer reads "Showing 1–25 of N", clicking Name toggles sort and keeps `page` reset, an out-of-range page shows the last page, and the empty state is unchanged.

### Task 2: Message queue (to send)
Files: `core/notification_views.py` (`to_send`), `core/notifications.py` (`to_send`, read only unless needed), `core/templates/core/notifications_to_send.html`, existing notification-queue tests.
Today `to_send` builds `rows` for every prepared notification (rendering text and the WhatsApp link for each) and passes everything.
Change: paginate the prepared queue with `build_table` using columns for Guardian, Message and Created (only Created sortable, default oldest first to match today). Build the `rows` list **only for the current page** (so rendering cost is per page). Keep `notifications.to_send()` as the source: it also marks consent-blocked rows SKIPPED, a side effect that must still run on every request. Keep `sent_today`, `portal_only`, `portal_address_missing` and the mark-sent / mark-skipped redirects working; after marking a row sent the redirect returns to `core:notifications-to-send` (page 1 is fine because the queue drains).
Done when: with 26+ prepared notifications page 1 has 25 rows and page 2 the rest, the count footer shows, consent skipping still happens, the sent-today section is unchanged, and rendering is done for 25 rows not all (assert via a query/mock count or by checking only 25 rendered rows).

### Task 3: Assessments list
Files: `core/views.py` (`academic_year_assessments`, around line 541), `core/templates/core/assessment_list.html`, `AssessmentFilterForm` (read only), existing assessment list tests (`grep -rl "academic-year-assessments" core/tests`).
Today the view filters by optional term, section and status via `AssessmentFilterForm`, annotates `subject_order` and orders by `("assessment_date", "subject_order")`, and passes `assessments`.
Change: `build_table` with columns for Date (sortable, `assessment_date`), Subject (sortable, `subject_order`), Section, Term, Status, Marks (not sortable unless the existing table already sorts) matching the template's current columns; default sort by Date ascending then subject (use the `Column.ordering` tuple `("assessment_date", "subject_order")`). The filter form submits via GET: the pagination and sort links must keep `term`, `section`, `status` (build_table preserves all non-reserved GET params; confirm the form field names are the GET keys). Keep the form, the year breadcrumb/header and the "Plan assessment" action.
Done when: 26+ assessments paginate, filters persist across page links and sort links, an invalid filter value still shows the existing form errors without crashing, and the empty state and permissions are unchanged.

## Verification (after all tasks)
`manage.py check`, the three touched test modules, then the full suite (`--parallel 4`; known flaky `u4_3a_subject_order` and one date-dependent test on main are unrelated). Visual check in a scratch Postgres database (create, migrate, `seed_demo` with `DJANGO_DEBUG=True`, 60 extra guardians/assessments via a shell script, drop afterwards): page 1, page 2 and the footer at 1366×768 for each of the three pages. Rollback = revert the PR.
