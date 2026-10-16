# UI Phase 3A: Shared Data Table — Design

Date: 2026-10-16
Source: `School_ERP_Admin_UI_UX_Audit.pdf` findings F10 (tables do not scale) and F12 (table semantics incomplete). First sub-project of the audit's Phase 3 (core workflows); the others (3B announcement preview, 3C applicant/student reconciliation, 3D teacher invitation, 3E polish) get their own specs.
Builds on: Phases 0-2 (merged to `main`).

## Intent

Office staff can still find a record when a list grows from dozens to thousands of rows, and a filtered/sorted/paged URL can be bookmarked or shared and shows the same list. Every table exposes correct semantics to assistive technology.

Agreed with the user: first pass covers **attendance registers, students and applicants**; guardians, announcements and the other lists follow in later PRs.

## Non-goals

Guardians/announcements/other lists, saved filters, column chooser, export, client-side JavaScript, `django-tables2`/`django-filter` (rejected: new dependencies and markup to restyle), any new model or migration.

## Design

### 1. Helper: `core/tables.py`

- `Column(label, key=None, ordering=(), descending=None, action=False)`. `key` is the URL token (`None` = not sortable); `ordering` is the ascending ORM ordering tuple; `descending` optionally overrides the flipped ordering (needed where a tiebreak must not flip); `action=True` marks a blank-label action column.
- `build_table(request, queryset, columns, default_sort, per_page=25) -> Table`.
  - Sort comes from `?sort=<key>` or `?sort=-<key>`; only keys of sortable columns are accepted. Anything else falls back to `default_sort`. A final `pk` tiebreak keeps pagination deterministic.
  - Page comes from `?page=N` via `Paginator.get_page`, so a non-numeric or out-of-range value never raises (clamped to the first / last page).
  - Returns `Table` with: `page`, `paginator`, `headers` (label, sortable, action, `url`, `aria_sort` of `ascending` / `descending` / empty), `count_text` ("Showing 26–50 of 312", or "No results"), `sorted_by` ("Name, ascending"), `filtered`, `clear_url`, `prev_url`, `next_url`, `page_links`.
- `parse_choice(request, name, choices) -> str`: returns the GET value only if it is one of the allowed choice values, else `""`. Invalid filter values are ignored, never an error.

### 2. URL state

`?sort=-date&page=2&section=3&start=2026-09-01`. Sort and page links keep every other non-empty query parameter. Changing the sort or a filter resets `page` (the header sort links omit `page`). Filters are plain GET parameters owned by each page's own form.

### 3. Shared partials

- `partials/_table_head.html` (inputs: `table`, `caption`): a visually hidden `<caption>` (includes the current sort), `<th scope="col">` for every column, sort links with `aria-sort` on the active column, and an explicit visually hidden "Actions" label for `action` columns. This is F12.
- `partials/_table_footer.html` (input: `table`): the result count; a `<nav aria-label="Pagination">` with Previous/Next and a window of numbered links (`aria-current="page"` on the current one) shown only when there is more than one page; and, when a filtered list is empty, a "Clear filters" link.
- Pages keep writing their own `<tbody>` rows (badges and links unchanged) inside the existing `erp-table-scroll` region wrapper.
- Styling uses existing Phase 1 tokens; links and the pagination controls meet the existing 2.75rem touch-target rule.

### 4. Pages in this pass

Context keys `registers`, `students`, `applicants` remain and now hold the current page, so existing tests and templates keep working; a new `table` key carries the table state.

- **Attendance registers** (`attendance_register_list`): columns Date, Academic year, Class/Grade, Section, Status, Entries. Sortable: Date (descending keeps the section tiebreak ascending), Section, Status, Entries. Default `-date`. The existing section/date-range form stays and its values carry through pagination. The section summary must still be computed over the **whole filtered set**, never the current page only.
- **Students** (`student_list`): sortable Name, Status; default `name`. Adds a Status filter (`?status=ACTIVE|INACTIVE`) beside the existing search (`?q=`). The Phase 0 label and Clear search behaviour stay; the link reads "Clear filters" when a status is selected.
- **Applicants** (`applicant_list`): sortable Name, Admission status; default `name`. Adds an Admission status filter (`?status=PENDING|ACCEPTED|REJECTED`).
- The Overview "Applicants awaiting decision" card now links to `applicant-list?status=PENDING`, so the card and its list agree (closes the Phase 2 minor M-1).

### 5. Errors and edge cases

- Zero results keep each page's existing empty row text; the footer adds the count and "Clear filters" when a filter is active.
- A one-page list shows only the count, no pagination bar.
- Unknown `sort`, invalid `status`, bad `page` values: ignored or clamped, never a 500.
- Permission gates on all three views are unchanged.

### 6. Testing

- Helper unit tests (`core/tests/test_tables.py`): default sort, `-` descending, unknown/unsortable sort falls back, page clamping, count text, header URLs keep filters and drop `page`, page links keep sort and filters, `aria_sort` values, action column header, `parse_choice`.
- Page tests (`core/tests/test_ui_admin_phase3a.py`): rows per page (25 + remainder), ordering, `<caption>`, `scope="col"`, `aria-sort`, pagination nav, filters carried across pages, status filters, attendance section summary identical on page 1 and page 2, permissions unchanged, Overview card link.
- Browser: Playwright pass at 320, 768 and 1440px (no document overflow; sort and page controls usable).

## Open items to confirm during planning

- Which existing tests read `response.context[...]` for the three lists (the context keys are kept, so none should change).
