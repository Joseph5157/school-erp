# UI Phase 3A: Shared Data Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One reusable server-rendered table pattern (sort, pagination, result count, URL-preserved filters, correct table semantics) applied to the attendance register, student and applicant lists (audit F10, F12).

**Architecture:** `core/tables.py` turns `request.GET` into a safe sort/page state (`build_table`), and two shared partials render the head (caption, `scope="col"`, sort links with `aria-sort`) and footer (count, pagination, clear filters). Each list view calls the helper; pages keep writing their own rows. Existing context keys (`registers`, `students`, `applicants`) are kept and now hold the current page. No models, no migration, no JavaScript.

**Tech Stack:** Django `Paginator`, Bootstrap 5.3, `static/css/erp.css` tokens, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-10-16-ui-phase3a-data-table-design.md`

## Global Constraints

- Branch `ui/audit-phase3a-data-table` (from `main`, which has Phases 0-2). Do not push or open a PR until asked.
- Run tests with `.venv\Scripts\python.exe manage.py test <labels> --parallel 4`. One date-dependent attendance test already fails on `main`; ignore only that one.
- No new models or migrations; `makemigrations --check` stays clean.
- Permission gates on the three views are unchanged (`administrator_required(...)`).
- Sort keys are whitelisted per page; nothing from the URL reaches `order_by` unvalidated. Bad `sort`, `status` and `page` values never raise.
- Real CSS tokens only: `--erp-ink`, `--erp-ink-soft`, `--erp-rule`, `--erp-accent`, `--erp-accent-wash`, `--erp-surface`, `--erp-radius-sm`, `--erp-space-1..7`, `--erp-text-xs/sm/base`, `--erp-focus-ring`. (`--erp-border` and `--erp-muted` do NOT exist.)
- Touch targets: links/buttons in the new controls use `min-height: 2.75rem` like the existing rule at `static/css/erp.css:333`.
- Existing empty-row texts ("No Students found.", "No Applicants yet.", "No attendance registers yet.") and the Phase 0 student search label/Clear search behaviour must keep working.
- GateGuard hooks block the first Bash command, first Edit of a file and first Write of a new file: state the requested facts in text, then retry the same call.

## Review Focus

1. `?sort=garbage`, `?sort=-`, `?sort=--name`, `?page=abc`, `?page=999`, `?page=0`, `?status=BOGUS` → 200, default behaviour, no exception (Task 1 helper tests and Task 2/3/4 page tests).
2. Attendance section summary is computed over the whole filtered set: identical on page 1 and page 2 (Task 2).
3. Rows that tie on the sort column never repeat or vanish across a page boundary: ordering is deterministic because of the `pk` tiebreak (Task 1).
4. A filtered list that returns nothing shows the page's empty row, "No results", and a "Clear filters" link (Task 1 footer, Tasks 3-4).
5. Sorting by a column, then paging, keeps the filters and the sort; changing the sort drops back to page 1 (Task 1).

## File Structure

| File | Responsibility |
|---|---|
| `core/tables.py` (new) | `Column`, `Header`, `Table`, `build_table`, `parse_choice` |
| `templates/partials/_table_head.html` (new) | Caption, `scope="col"`, sort links, action header |
| `templates/partials/_table_footer.html` (new) | Result count, pagination nav, Clear filters |
| `static/css/erp.css` | Sort link, `aria-sort` indicator, pagination, count line |
| `core/views.py` | `attendance_register_list`, `student_list`, `applicant_list` call `build_table` |
| `core/templates/core/attendance_register_list.html`, `student_list.html`, `applicant_list.html` | Use the partials; status filters |
| `core/dashboard.py` | Applicants card links to `?status=PENDING` |
| `core/tests/test_tables.py` (new) | Helper unit tests |
| `core/tests/test_ui_admin_phase3a.py` (new) | Page-level tests |

Existing page templates live in `core/templates/core/`; shared partials in `templates/partials/`.

---

### Task 1: Table helper, partials, styles

**Files:**
- Create: `core/tables.py`, `templates/partials/_table_head.html`, `templates/partials/_table_footer.html`, `core/tests/test_tables.py`
- Modify: `static/css/erp.css`

**Interfaces:**
- Produces:
  - `Column(label: str, key: str | None = None, ordering: tuple = (), descending: tuple | None = None, action: bool = False)`; property `sortable`; method `order_by(desc: bool) -> tuple`.
  - `build_table(request, queryset, columns, default_sort: str, per_page: int = 25) -> Table`. `default_sort` is a key, optionally prefixed with `-`.
  - `Table` attributes: `page`, `paginator`, `headers` (list of `Header(label, sortable, action, url, aria_sort)`), `count_text`, `sorted_by`, `filtered`, `clear_url`, `prev_url`, `next_url`, `page_links` (list of dicts `number`, `url`, `current`).
  - `parse_choice(request, name, choices) -> str`.

- [ ] **Step 1: Write the failing tests** (`core/tests/test_tables.py`)

```python
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from core.models import Applicant
from core.tables import Column, build_table, parse_choice

COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Status", "status", ("admission_status",)),
    Column("Notes"),
    Column("Actions", action=True),
)


class BuildTableTests(TestCase):
    def setUp(self):
        for index in range(30):
            Applicant.objects.create(full_name=f"Person {index:02d}")

    def table(self, query="", per_page=10, default_sort="name"):
        request = RequestFactory().get("/applicants/" + query)
        return build_table(
            request, Applicant.objects.all(), COLUMNS, default_sort, per_page=per_page
        )

    def names(self, table):
        return [applicant.full_name for applicant in table.page]

    def test_default_sort_ascending_with_aria_sort(self):
        table = self.table()
        self.assertEqual(self.names(table)[0], "Person 00")
        self.assertEqual(table.headers[0].aria_sort, "ascending")
        self.assertEqual(table.headers[1].aria_sort, "")
        self.assertEqual(table.sorted_by, "Name, ascending")

    def test_descending_sort_and_toggle_link(self):
        table = self.table("?sort=-name")
        self.assertEqual(self.names(table)[0], "Person 29")
        self.assertEqual(table.headers[0].aria_sort, "descending")
        self.assertIn("sort=name", table.headers[0].url)
        self.assertNotIn("sort=-name", table.headers[0].url)

    def test_ascending_header_links_to_descending(self):
        table = self.table()
        self.assertIn("sort=-name", table.headers[0].url)

    def test_unknown_or_unsortable_sort_falls_back_to_default(self):
        for raw in ("garbage", "-", "--name", "notes", "actions", "full_name"):
            with self.subTest(raw=raw):
                table = self.table(f"?sort={raw}")
                self.assertEqual(self.names(table)[0], "Person 00")

    def test_page_is_clamped_never_raises(self):
        self.assertEqual(self.table("?page=999").page.number, 3)
        self.assertEqual(self.table("?page=abc").page.number, 1)
        self.assertEqual(self.table("?page=0").page.number, 3)  # get_page clamps

    def test_count_text(self):
        self.assertEqual(self.table("?page=2").count_text, "Showing 11–20 of 30")

    def test_empty_queryset_says_no_results(self):
        request = RequestFactory().get("/applicants/?status=PENDING")
        table = build_table(request, Applicant.objects.none(), COLUMNS, "name")
        self.assertEqual(table.count_text, "No results")
        self.assertTrue(table.filtered)
        self.assertEqual(table.clear_url, "/applicants/")

    def test_header_links_keep_filters_and_drop_page(self):
        table = self.table("?status=PENDING&page=2")
        url = table.headers[0].url
        self.assertIn("status=PENDING", url)
        self.assertNotIn("page=", url)

    def test_page_links_keep_sort_and_filters(self):
        table = self.table("?status=PENDING&sort=-name&page=2")
        self.assertIn("sort=-name", table.next_url)
        self.assertIn("status=PENDING", table.next_url)
        self.assertIn("page=3", table.next_url)
        self.assertIn("page=1", table.prev_url)
        current = [link for link in table.page_links if link["current"]]
        self.assertEqual([link["number"] for link in current], [2])

    def test_first_and_last_page_have_no_prev_next(self):
        self.assertEqual(self.table().prev_url, "")
        self.assertEqual(self.table("?page=3").next_url, "")

    def test_action_and_plain_columns_are_not_sortable(self):
        table = self.table()
        self.assertFalse(table.headers[2].sortable)
        self.assertTrue(table.headers[3].action)
        self.assertFalse(table.headers[3].sortable)

    def test_ordering_is_deterministic_across_pages_with_ties(self):
        Applicant.objects.all().update(full_name="Same")
        seen = []
        for page in (1, 2, 3):
            seen += [a.pk for a in self.table(f"?page={page}").page]
        self.assertEqual(len(seen), 30)
        self.assertEqual(len(set(seen)), 30)

    def test_descending_override_is_used(self):
        columns = (
            Column("Date", "date", ("created_at", "full_name"), ("-created_at", "full_name")),
        )
        request = RequestFactory().get("/x/?sort=-date")
        table = build_table(request, Applicant.objects.all(), columns, "-date")
        self.assertEqual(table.sorted_by, "Date, descending")
        self.assertEqual(
            columns[0].order_by(True), ("-created_at", "full_name")
        )
        self.assertEqual(columns[0].order_by(False), ("created_at", "full_name"))

    def test_flipped_descending_when_no_override(self):
        column = Column("Name", "name", ("full_name", "-pk"))
        self.assertEqual(column.order_by(True), ("-full_name", "pk"))


class ParseChoiceTests(TestCase):
    CHOICES = [("PENDING", "Pending"), ("ACCEPTED", "Accepted")]

    def parse(self, query):
        return parse_choice(RequestFactory().get("/" + query), "status", self.CHOICES)

    def test_valid_value_returned(self):
        self.assertEqual(self.parse("?status=PENDING"), "PENDING")

    def test_invalid_or_missing_value_is_empty(self):
        self.assertEqual(self.parse("?status=BOGUS"), "")
        self.assertEqual(self.parse(""), "")


class PartialRenderingTests(TestCase):
    def setUp(self):
        for index in range(30):
            Applicant.objects.create(full_name=f"Person {index:02d}")
        request = RequestFactory().get("/applicants/?page=2")
        self.table = build_table(request, Applicant.objects.all(), COLUMNS, "name", per_page=10)

    def test_head_has_caption_scope_aria_sort_and_action_label(self):
        html = render_to_string(
            "partials/_table_head.html", {"table": self.table, "caption": "Applicants"}
        )
        self.assertIn("<caption", html)
        self.assertIn("Applicants", html)
        self.assertIn("Sorted by Name, ascending", html)
        self.assertIn('scope="col"', html)
        self.assertIn('aria-sort="ascending"', html)
        self.assertIn("Actions", html)

    def test_footer_has_count_and_pagination_nav(self):
        html = render_to_string("partials/_table_footer.html", {"table": self.table})
        self.assertIn("Showing 11–20 of 30", html)
        self.assertIn('aria-label="Pagination"', html)
        self.assertIn('aria-current="page"', html)

    def test_footer_hides_pagination_for_single_page(self):
        request = RequestFactory().get("/applicants/")
        table = build_table(request, Applicant.objects.all(), COLUMNS, "name", per_page=100)
        html = render_to_string("partials/_table_footer.html", {"table": table})
        self.assertNotIn('aria-label="Pagination"', html)
        self.assertIn("Showing 1–30 of 30", html)

    def test_footer_offers_clear_filters_when_filtered_and_empty(self):
        request = RequestFactory().get("/applicants/?status=PENDING")
        table = build_table(request, Applicant.objects.none(), COLUMNS, "name")
        html = render_to_string("partials/_table_footer.html", {"table": table})
        self.assertIn("No results", html)
        self.assertIn("Clear filters", html)
```

Note on `?page=0`: Django's `Paginator.get_page` treats a non-positive page as out of range and returns the last page; the test asserts that real behaviour. If the installed Django differs, assert `1 <= page.number <= 3` instead and say so in the report.

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_tables --parallel 4`
Expected: FAIL (`ModuleNotFoundError: core.tables`).

- [ ] **Step 3: Implement `core/tables.py`**

```python
"""Shared state for admin list tables: sort, pagination, URL-preserved filters.

Pages call `build_table` and keep writing their own rows. Sort keys are
whitelisted per page; a bad `sort`, `page` or filter value is ignored or
clamped, never an error (audit F10).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.paginator import Paginator

PER_PAGE = 25
_RESERVED = ("sort", "page")
_WINDOW = 2


@dataclass(frozen=True)
class Column:
    label: str
    key: str | None = None  # URL token; None = not sortable
    ordering: tuple = ()  # ascending ORM ordering
    descending: tuple | None = None  # override when a tiebreak must not flip
    action: bool = False  # blank-label action column

    @property
    def sortable(self):
        return bool(self.key and self.ordering)

    def order_by(self, desc):
        if not desc:
            return self.ordering
        if self.descending is not None:
            return self.descending
        return tuple(f[1:] if f.startswith("-") else f"-{f}" for f in self.ordering)


@dataclass(frozen=True)
class Header:
    label: str
    sortable: bool
    action: bool
    url: str
    aria_sort: str


@dataclass
class Table:
    page: object
    paginator: object
    headers: list
    count_text: str
    sorted_by: str
    filtered: bool
    clear_url: str
    prev_url: str
    next_url: str
    page_links: list


def parse_choice(request, name, choices):
    """The GET value if it is an allowed choice value, else ''."""
    value = request.GET.get(name, "")
    return value if value in {choice for choice, _ in choices} else ""


def _query(params, **extra):
    data = {**params, **{k: v for k, v in extra.items() if v not in (None, "")}}
    return "?" + urlencode(data)


def build_table(request, queryset, columns, default_sort, per_page=PER_PAGE):
    sortable = {column.key: column for column in columns if column.sortable}
    raw = request.GET.get("sort", "")
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    if key not in sortable:
        desc = default_sort.startswith("-")
        key = default_sort[1:] if desc else default_sort
    active = sortable[key]
    token = f"-{key}" if desc else key

    params = {k: v for k, v in request.GET.items() if v and k not in _RESERVED}

    ordered = queryset.order_by(*active.order_by(desc), "pk")
    paginator = Paginator(ordered, per_page)
    page = paginator.get_page(request.GET.get("page"))

    headers = []
    for column in columns:
        if column.sortable:
            is_active = column.key == key
            next_token = f"-{column.key}" if is_active and not desc else column.key
            aria = ("descending" if desc else "ascending") if is_active else ""
            headers.append(
                Header(column.label, True, column.action, _query(params, sort=next_token), aria)
            )
        else:
            headers.append(Header(column.label, False, column.action, "", ""))

    total = paginator.count
    count_text = (
        f"Showing {page.start_index()}–{page.end_index()} of {total}" if total else "No results"
    )
    page_links = [
        {
            "number": number,
            "url": _query(params, sort=token, page=number),
            "current": number == page.number,
        }
        for number in paginator.page_range
        if abs(number - page.number) <= _WINDOW
    ]
    return Table(
        page=page,
        paginator=paginator,
        headers=headers,
        count_text=count_text,
        sorted_by=f"{active.label}, {'descending' if desc else 'ascending'}",
        filtered=bool(params),
        clear_url=request.path,
        prev_url=_query(params, sort=token, page=page.previous_page_number())
        if page.has_previous()
        else "",
        next_url=_query(params, sort=token, page=page.next_page_number())
        if page.has_next()
        else "",
        page_links=page_links,
    )
```

`templates/partials/_table_head.html`:

```django
<caption class="visually-hidden">{{ caption }}. Sorted by {{ table.sorted_by }}.</caption>
<thead>
    <tr>
        {% for header in table.headers %}
        <th scope="col"{% if header.aria_sort %} aria-sort="{{ header.aria_sort }}"{% endif %}>
            {% if header.sortable %}<a class="erp-sort-link" href="{{ header.url }}">{{ header.label }}</a>{% elif header.action %}<span class="visually-hidden">{{ header.label|default:"Actions" }}</span>{% else %}{{ header.label }}{% endif %}
        </th>
        {% endfor %}
    </tr>
</thead>
```

`templates/partials/_table_footer.html`:

```django
<div class="erp-table-footer">
    <p class="erp-table-count" role="status">{{ table.count_text }}{% if table.filtered and not table.paginator.count %} <a href="{{ table.clear_url }}">Clear filters</a>{% endif %}</p>
    {% if table.paginator.num_pages > 1 %}
    <nav class="erp-pagination" aria-label="Pagination">
        <ul>
            {% if table.prev_url %}<li><a href="{{ table.prev_url }}" rel="prev">Previous</a></li>{% endif %}
            {% for link in table.page_links %}
            <li>{% if link.current %}<span aria-current="page">{{ link.number }}</span>{% else %}<a href="{{ link.url }}" aria-label="Page {{ link.number }}">{{ link.number }}</a>{% endif %}</li>
            {% endfor %}
            {% if table.next_url %}<li><a href="{{ table.next_url }}" rel="next">Next</a></li>{% endif %}
        </ul>
    </nav>
    {% endif %}
</div>
```

`static/css/erp.css` (append):

```css
.erp-sort-link { color: inherit; text-decoration: none; display: inline-flex; align-items: center; min-height: 2.75rem; }
.erp-sort-link:hover { text-decoration: underline; }
th[aria-sort="ascending"] .erp-sort-link::after { content: " \25B2"; font-size: var(--erp-text-xs); }
th[aria-sort="descending"] .erp-sort-link::after { content: " \25BC"; font-size: var(--erp-text-xs); }
.erp-table-footer { display: flex; flex-wrap: wrap; gap: var(--erp-space-3); align-items: center; justify-content: space-between; margin-top: var(--erp-space-3); }
.erp-table-count { margin: 0; color: var(--erp-ink-soft); font-size: var(--erp-text-sm); }
.erp-pagination ul { display: flex; flex-wrap: wrap; gap: var(--erp-space-1); list-style: none; margin: 0; padding: 0; }
.erp-pagination a, .erp-pagination span { display: inline-flex; align-items: center; justify-content: center; min-width: 2.75rem; min-height: 2.75rem; padding: 0 var(--erp-space-3); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius-sm); background: var(--erp-surface); color: var(--erp-ink); text-decoration: none; }
.erp-pagination a:hover { background: var(--erp-accent-wash); }
.erp-pagination span[aria-current] { background: var(--erp-accent); border-color: var(--erp-accent); color: #fff; font-weight: 600; }
```

- [ ] **Step 4: Run Task 1 tests, expect PASS.** Fix the `?page=0` assertion per the note if Django's behaviour differs.

- [ ] **Step 5: Commit**

```bash
git add core/tables.py templates/partials/_table_head.html templates/partials/_table_footer.html static/css/erp.css core/tests/test_tables.py
git commit -m "feat(ui): add shared data-table helper and partials (F10 F12)"
```

---

### Task 2: Attendance register list

**Files:**
- Modify: `core/views.py` (`attendance_register_list`, ~line 2391), `core/templates/core/attendance_register_list.html`
- Test: `core/tests/test_ui_admin_phase3a.py` (create)

**Interfaces:**
- Consumes: `Column`, `build_table` (Task 1).
- Produces: context keys `table` (a `Table`) and `registers` (= `table.page`).

- [ ] **Step 1: Write the failing tests** (`core/tests/test_ui_admin_phase3a.py`)

```python
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin


class AttendanceTableTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        start = date(2026, 8, 1)
        for index in range(30):
            AttendanceRegister.objects.create(
                academic_year=self.year, class_grade=self.class_grade,
                section=self.section, date=start + timedelta(days=index),
            )
        self.url = reverse("core:attendance-register-list")

    def dates(self, response):
        return [register.date for register in response.context["registers"]]

    def test_first_page_has_25_rows_newest_first_and_second_page_the_rest(self):
        page1 = self.administrator.get(self.url)
        page2 = self.administrator.get(self.url, {"page": 2})
        self.assertEqual(len(self.dates(page1)), 25)
        self.assertEqual(self.dates(page1), sorted(self.dates(page1), reverse=True))
        self.assertGreater(min(self.dates(page1)), max(self.dates(page2)))

    def test_sort_by_date_ascending(self):
        response = self.administrator.get(self.url, {"sort": "date"})
        dates = self.dates(response)
        self.assertEqual(dates, sorted(dates))

    def test_bad_sort_and_page_values_do_not_error(self):
        for params in ({"sort": "bogus"}, {"page": "abc"}, {"page": "999"}, {"sort": "-"}):
            with self.subTest(params=params):
                self.assertEqual(self.administrator.get(self.url, params).status_code, 200)

    def test_semantics_caption_scope_aria_sort_and_pagination(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "<caption")
        self.assertContains(response, 'scope="col"')
        self.assertContains(response, 'aria-sort="descending"')
        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, "Showing 1–25 of")

    def test_filters_are_carried_into_pagination_links(self):
        response = self.administrator.get(self.url, {"section": self.section.pk})
        self.assertContains(response, f"section={self.section.pk}")
        self.assertContains(response, "page=2")

    def test_section_summary_covers_whole_filtered_set_not_one_page(self):
        params = {"section": self.section.pk}
        first = self.administrator.get(self.url, params)
        second = self.administrator.get(self.url, {**params, "page": 2})
        self.assertIsNotNone(first.context["section_summary"])
        self.assertEqual(first.context["section_summary"], second.context["section_summary"])
        self.assertEqual(first.context["section_total"], second.context["section_total"])

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
```

- [ ] **Step 2: Run, expect FAIL** (rows are not paginated; no caption).

- [ ] **Step 3: Implement**

`core/views.py`: add `from core.tables import Column, build_table` with the other imports, define once at module level:

```python
REGISTER_COLUMNS = (
    Column("Date", "date", ("date", "section__class_grade", "section"),
           ("-date", "section__class_grade", "section")),
    Column("Academic year"),
    Column("Class/Grade"),
    Column("Section", "section", ("section__class_grade", "section")),
    Column("Status", "status", ("status",)),
    Column("Entries", "entries", ("entry_count",)),
)
```

In `attendance_register_list`, keep the queryset, filter form and the `section_summary` block exactly as they are (the summary is computed from the unpaginated `registers` queryset before pagination; do not move it), drop the trailing `.order_by(...)` from the initial queryset (the helper orders), and just before `render`:

```python
    table = build_table(request, registers, REGISTER_COLUMNS, "-date")
```

The context becomes `{"registers": table.page, "table": table, "form": form, "section_summary": ..., "section_total": ...}`.

Check that `registers.filter(...)` still works without `.order_by` and that the `section_summary` queries do not depend on the ordering.

`core/templates/core/attendance_register_list.html`: replace the table's `<thead>...</thead>` with `{% include "partials/_table_head.html" with table=table caption="Attendance registers" only %}`, change `{% for register in registers %}` to `{% for register in table.page %}`, and after the closing `</div>` of `erp-table-scroll` add `{% include "partials/_table_footer.html" with table=table only %}`. The filter `<form>` must keep submitting `section`, `start`, `end` as GET; do not add `page` or `sort` to it.

- [ ] **Step 4: Run Task 2 tests** and the existing register tests:

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase3a core.tests.test_ui_admin_phase0 core.tests.test_phase5_attendance_views core.tests.test_authorization --parallel 4`
Expected: PASS. `test_ui_admin_phase0`'s newest-first test and `test_phase5_attendance_views` read `response.context["registers"]`, which is now a `Page`: `list(page)` and `page[0]` work, so they should pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/attendance_register_list.html core/tests/test_ui_admin_phase3a.py
git commit -m "feat(ui): paginate and sort the attendance register list (F10 F12)"
```

---

### Task 3: Student list

**Files:**
- Modify: `core/views.py` (`student_list`, ~line 2261), `core/templates/core/student_list.html`
- Test: `core/tests/test_ui_admin_phase3a.py`

**Interfaces:**
- Consumes: `Column`, `build_table`, `parse_choice` (Task 1).
- Produces: context `students` (= `table.page`), `table`, `query`, `status`, `status_choices`.

- [ ] **Step 1: Write the failing tests** (append to `test_ui_admin_phase3a.py`; add the imports at the top of the file)

```python
from core.models import Applicant, Student


def make_students(count):
    students = []
    for index in range(count):
        applicant = Applicant.objects.create(full_name=f"Student {index:02d}")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        students.append(applicant.progress_to_student())
    return students


class StudentTableTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.students = make_students(30)
        self.url = reverse("core:student-list")

    def names(self, response):
        return [student.full_name for student in response.context["students"]]

    def test_pagination_25_then_remainder_sorted_by_name(self):
        page1 = self.administrator.get(self.url)
        page2 = self.administrator.get(self.url, {"page": 2})
        self.assertEqual(len(self.names(page1)), 25)
        self.assertEqual(len(self.names(page2)), 5)
        self.assertEqual(self.names(page1)[0], "Student 00")
        self.assertContains(page1, "Showing 1–25 of 30")

    def test_sort_descending_by_name(self):
        response = self.administrator.get(self.url, {"sort": "-name"})
        self.assertEqual(self.names(response)[0], "Student 29")
        self.assertContains(response, 'aria-sort="descending"')

    def test_status_filter(self):
        Student.objects.filter(pk=self.students[0].pk).update(status=Student.Status.INACTIVE)
        response = self.administrator.get(self.url, {"status": "INACTIVE"})
        self.assertEqual(self.names(response), ["Student 00"])
        self.assertContains(response, "Showing 1–1 of 1")

    def test_invalid_status_is_ignored(self):
        response = self.administrator.get(self.url, {"status": "BOGUS"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.names(response)), 25)

    def test_search_and_status_survive_pagination_links(self):
        response = self.administrator.get(self.url, {"q": "Student", "status": "ACTIVE"})
        self.assertContains(response, "q=Student")
        self.assertContains(response, "status=ACTIVE")
        self.assertContains(response, "page=2")

    def test_filter_with_no_matches_offers_clear_filters(self):
        response = self.administrator.get(self.url, {"q": "zzz-no-match"})
        self.assertContains(response, "No Students found.")
        self.assertContains(response, "No results")
        self.assertContains(response, "Clear filters")

    def test_search_label_and_clear_search_from_phase0_remain(self):
        response = self.administrator.get(self.url, {"q": "Student"})
        self.assertContains(response, 'for="student-search"')
        self.assertContains(response, "Clear search")

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
```

If `Student.objects.filter(...).update(status=...)` trips a model constraint, set the status the same way the Phase 0 deactivation tests do (see `core/tests/test_ui_admin_phase0.py`, `DeactivateStudentTests`) and say so in the report.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

`core/views.py` (import `parse_choice` alongside `Column, build_table`):

```python
STUDENT_COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Status", "status", ("status",)),
    Column("Email"),
    Column("Phone"),
)
```

```python
@administrator_required("core.view_student")
def student_list(request):
    query = request.GET.get("q", "").strip()
    status = parse_choice(request, "status", Student.Status.choices)
    students = Student.objects.all()
    if query:
        students = students.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status:
        students = students.filter(status=status)
    table = build_table(request, students, STUDENT_COLUMNS, "name")
    return render(
        request,
        "core/student_list.html",
        {
            "students": table.page,
            "table": table,
            "query": query,
            "status": status,
            "status_choices": Student.Status.choices,
        },
    )
```

`core/templates/core/student_list.html`: keep the existing `<label for="student-search" ...>Search students</label>`; inside the `input-group`, add the status select after the search input and make the Clear link cover both filters:

```django
    <div class="input-group">
        <input type="search" id="student-search" name="q" value="{{ query }}" class="form-control" placeholder="Name, email, or phone">
        <label for="student-status" class="visually-hidden">Status</label>
        <select id="student-status" name="status" class="form-select">
            <option value="">All statuses</option>
            {% for value, label in status_choices %}<option value="{{ value }}"{% if value == status %} selected{% endif %}>{{ label }}</option>{% endfor %}
        </select>
        <button type="submit" class="btn btn-outline-secondary">Search</button>
        {% if query or status %}<a class="btn btn-link" href="{% url 'core:student-list' %}">{% if status %}Clear filters{% else %}Clear search{% endif %}</a>{% endif %}
    </div>
```

Replace the table: wrap it in `<div class="erp-table-scroll" role="region" aria-label="Students" tabindex="0">`, include `_table_head.html` with `caption="Students"`, loop `table.page`, keep the `{% empty %}` row (`colspan="4"`), and add `{% include "partials/_table_footer.html" with table=table only %}` after the wrapper.

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase3a core.tests.test_ui_admin_phase0 core.tests.test_acceptance core.tests.test_authorization --parallel 4`
Expected: PASS (`test_acceptance.py:150` and `test_authorization.py:1215-1230` read `context["students"]` via `list(...)`, which works on a `Page`).

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/student_list.html core/tests/test_ui_admin_phase3a.py
git commit -m "feat(ui): paginate, sort and filter the student list (F10 F12)"
```

---

### Task 4: Applicant list and Overview card link

**Files:**
- Modify: `core/views.py` (`applicant_list`, ~line 1679), `core/templates/core/applicant_list.html`, `core/dashboard.py` (`_applicants`), `core/tests/test_ui_admin_phase2.py` (the applicants-card URL assertion)
- Test: `core/tests/test_ui_admin_phase3a.py`

**Interfaces:**
- Consumes: `Column`, `build_table`, `parse_choice` (Task 1).
- Produces: context `applicants` (= `table.page`), `table`, `status`, `status_choices`; the applicants Overview card `url` becomes `reverse("core:applicant-list") + "?status=PENDING"`.

- [ ] **Step 1: Write the failing tests** (append; import `overview_cards` at the top of the file)

```python
from core.dashboard import overview_cards


class ApplicantTableTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        for index in range(30):
            Applicant.objects.create(full_name=f"Applicant {index:02d}")
        accepted = Applicant.objects.get(full_name="Applicant 00")
        accepted.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.url = reverse("core:applicant-list")

    def names(self, response):
        return [applicant.full_name for applicant in response.context["applicants"]]

    def test_pagination_and_default_name_sort(self):
        page1 = self.administrator.get(self.url)
        self.assertEqual(len(self.names(page1)), 25)
        self.assertEqual(self.names(page1)[0], "Applicant 00")
        self.assertContains(page1, "Showing 1–25 of 30")
        self.assertContains(page1, "<caption")
        self.assertContains(page1, 'scope="col"')

    def test_sort_by_admission_status_descending_puts_pending_first(self):
        response = self.administrator.get(self.url, {"sort": "-status"})
        first = response.context["applicants"][0]
        self.assertEqual(first.admission_status, Applicant.AdmissionStatus.PENDING)
        self.assertNotIn("Applicant 00", self.names(response))  # the one ACCEPTED row is last
        self.assertContains(response, 'aria-sort="descending"')

    def test_status_filter_pending_excludes_decided(self):
        response = self.administrator.get(self.url, {"status": "PENDING"})
        self.assertNotIn("Applicant 00", self.names(response))
        self.assertContains(response, "Showing 1–25 of 29")

    def test_invalid_status_and_page_ignored(self):
        response = self.administrator.get(self.url, {"status": "BOGUS", "page": "999"})
        self.assertEqual(response.status_code, 200)

    def test_empty_filter_result_keeps_empty_row_and_clear_link(self):
        response = self.administrator.get(self.url, {"status": "REJECTED"})
        self.assertContains(response, "No Applicants yet.")
        self.assertContains(response, "Clear filters")

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)

    def test_overview_card_links_to_pending_filter(self):
        card = next(c for c in overview_cards(self.admin_user) if c["key"] == "applicants")
        self.assertEqual(card["url"], reverse("core:applicant-list") + "?status=PENDING")
        self.assertEqual(card["count"], 29)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement**

`core/views.py`:

```python
APPLICANT_COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Admission status", "status", ("admission_status",)),
)
```

```python
@administrator_required("core.view_applicant")
def applicant_list(request):
    status = parse_choice(request, "status", Applicant.AdmissionStatus.choices)
    applicants = Applicant.objects.all()
    if status:
        applicants = applicants.filter(admission_status=status)
    table = build_table(request, applicants, APPLICANT_COLUMNS, "name")
    return render(
        request,
        "core/applicant_list.html",
        {
            "applicants": table.page,
            "table": table,
            "status": status,
            "status_choices": Applicant.AdmissionStatus.choices,
        },
    )
```

`core/templates/core/applicant_list.html`: after the page header add

```django
<form method="get" class="mb-3" aria-label="Filter applicants">
    <div class="input-group">
        <label for="applicant-status" class="visually-hidden">Admission status</label>
        <select id="applicant-status" name="status" class="form-select">
            <option value="">All admission statuses</option>
            {% for value, label in status_choices %}<option value="{{ value }}"{% if value == status %} selected{% endif %}>{{ label }}</option>{% endfor %}
        </select>
        <button type="submit" class="btn btn-outline-secondary">Filter</button>
        {% if status %}<a class="btn btn-link" href="{% url 'core:applicant-list' %}">Clear filters</a>{% endif %}
    </div>
</form>
```

Wrap the table in `<div class="erp-table-scroll" role="region" aria-label="Applicants" tabindex="0">`, use `_table_head.html` with `caption="Applicants"`, loop `table.page`, keep the `{% empty %}` row (`colspan="2"`), and include `_table_footer.html` after the wrapper.

`core/dashboard.py` `_applicants`: change the card URL to `reverse("core:applicant-list") + "?status=PENDING"`.

`core/tests/test_ui_admin_phase2.py`: update the existing assertion `card["url"] == reverse("core:applicant-list")` to the new URL (it is the only assertion that encodes the old link).

- [ ] **Step 4: Run**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase3a core.tests.test_ui_admin_phase2 core.tests.test_authorization core.tests.test_acceptance --parallel 4`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/views.py core/templates/core/applicant_list.html core/dashboard.py core/tests/test_ui_admin_phase3a.py core/tests/test_ui_admin_phase2.py
git commit -m "feat(ui): paginate and filter the applicant list; link Overview card to it (F10 F12)"
```

---

### Task 5: Verification, responsive check, notes

**Files:**
- Modify: `docs/UI_REFERENCES.md` (one Status-line mention), this plan (completion notes)

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python.exe manage.py test --parallel 4`
Expected: only the known date-dependent attendance test fails.

- [ ] **Step 2: Static checks**

Run: `.venv\Scripts\python.exe -m ruff check core`, `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, `git diff --check`.
Expected: ruff clean; "No changes detected".

- [ ] **Step 3: Browser smoke test (Playwright MCP, isolated server)**

Isolated server on a spare port against a throwaway SQLite database (do NOT use the dev Postgres env vars; another process may hold port 8765, so pick a different port). Seed demo data and add enough extra rows to exceed 25 on each list (a short Django shell snippet is fine). At 320, 768 and 1440px on the attendance, student and applicant lists check: no horizontal document overflow; column header sort links toggle `aria-sort`; Next/Previous and page numbers work and keep sort and filters; the status filters work; the pagination controls are at least 44px tall; keyboard Tab reaches sort links and pagination. Stop the server and delete the temp DB afterwards.

- [ ] **Step 4: Fix anything found, test first where it is a regression.**

- [ ] **Step 5: Record results**

Add a "Completion notes" section at the end of this plan (tests, counts, browser results, deviations) and a short Phase 3A mention in `docs/UI_REFERENCES.md`'s Status line.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs: record Phase 3A verification"
```

Do not push or open a PR until the user asks.
