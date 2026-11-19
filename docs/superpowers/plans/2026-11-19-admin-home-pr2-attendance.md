# Admin home PR 2: Attendance tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the interim Attendance tab (heatmap and absentees only) into the spec's five cards: trend vs last month, the 4-week heatmap, the day-of-week pattern, the best and worst classes, and absentees with a "this month / below 75% this term" switch.

**Architecture:** The aggregates are read-only functions in `core/analytics.py`, built on `reports.reportable_entries()` (submitted registers on instructional days only, PRESENT/ABSENT only). `attendance_tab_context` puts them together. `admin_overview` in `core/views.py` passes the permission flags and the `?absent=` choice. `templates/partials/home/_attendance.html` renders them with `erp-` classes only. The absentee switch is two plain links (`?tab=attendance&absent=term`), so it works without JavaScript.

**Tech Stack:** Django 5 server-rendered templates, PostgreSQL, `static/css/erp.css` (Everclass design system), Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-11-18-admin-home-tabs-design.md` (sections "Tabs → Attendance", "Merges", "My calls", "Anti-goals").

**Branch:** create `ui/admin-home-attendance` from `origin/feature/admin-home`. The PR **targets `feature/admin-home`, never main.** Do not merge anything: the owner tests locally and gives the word.

## Global Constraints

- Cards, in this order on phones: 1 Trend vs last month · 2 Heatmap, last 4 weeks (existing) · 3 Day-of-week pattern · 4 Best and worst 3 classes · 5 Absentees.
- Best/worst lists show 3 each and are hidden when fewer than 4 classes have data (spec "My calls").
- Absentees card: one card with a switch between "this month" (N+ days, N = `ABSENTEE_THRESHOLD_DAYS` = 3) and "below 75% this term".
- No rings, gauges or new chart types. Use cards, lists, the existing horizontal bars (`partials/charts/_bars.html`) and the existing heatmap.
- No long scroll: every list folds after 5 rows with `partials/home/_fold_rows.html`.
- Every list row links somewhere the viewer is allowed to open. Student rows link to `core:student-detail` (needs `core.view_student`, which `include_absentees` already requires). Class rows link to `core:class-grade-detail` only when the viewer has `core.view_classgrade` (`can["classes"]`).
- Attendance statuses are PRESENT and ABSENT only (ADR 0007). The word "Late" must not appear (`test_there_is_no_late_status_anywhere`).
- A period with no submitted data is "no data", never 0%.
- Bootstrap-free: inside `.erp-home` use only `erp-` classes. Cards are `erp-card` (+ `erp-card--<name>`), in-card empty messages are `erp-card-empty`, muted text is `erp-note-text`. Grep `erp.css` before adding a class name (`docs/DESIGN_SYSTEM.md` rule 3). New class names in this PR: `erp-seg`, `erp-seg-link`, `erp-trend-*`.
- Colours and spacing come from `--erp-*` tokens. No raw hex values in new rules.
- Up/down is said in words, not by colour alone.
- `core/tests/route_permissions.json` must not be edited.
- Only the active tab is built. Only the chosen absentee view is queried.
- Tests: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test <labels> --noinput`; after CSS edits also `--pattern="test_ui*.py" --parallel 4`. Do not run the full suite locally (CI does).

## Review Focus

1. **The first days of a month or term.** On 1–3 July, "this month" has one or two days and a student absent on day one would show 0%. The 75% list needs `LOW_ATTENDANCE_MIN_DAYS` = 5 marked days. Trend shows "No comparison yet" when either month has no data. Tested in Tasks 1 and 2.
2. **No term running** (holidays, or no terms set up). The "below 75% this term" view says "No term is running." and never errors. Tested in Task 2.
3. **Few classes.** With 4 or 5 classes, the best 3 and worst 3 would overlap. Each side shows `min(3, n // 2)` classes, so no class appears on both. Tested in Task 2.
4. **A viewer without `view_student` or `view_classgrade`** sees no names in either absentee view and sees class names without links. Tested in Task 3.
5. **Query growth.** The tab's query count must not grow with the number of classes or students. Tested in Task 3.

---

## File Structure

- `core/analytics.py`: new `month_trend`, `weekday_pattern`, `class_extremes`, `low_attendance_students`; `attendance_tab_context` extended.
- `core/views.py` `admin_overview`: reads `?absent=` and passes `absent_view` and `class_links`.
- `templates/partials/home/_attendance.html`: rewritten with five cards.
- `templates/partials/home/_absentee_row.html` (new): one `<li class="erp-home-row">` per student.
- `static/css/erp.css`: switch (`erp-seg`), trend figure (`erp-trend-*`), desktop spans for the five cards. Remove `.erp-absentee*` rules if nothing else uses them.
- `core/tests/test_home_attendance.py` (new): data functions.
- `core/tests/test_ui_admin_home_tabs.py`: tab rendering, gating, switch, guard tests.
- `docs/DESIGN_SYSTEM.md`: add the Segmented switch row.

---

### Task 1: Trend vs last month and the day-of-week pattern

**Files:**
- Modify: `core/analytics.py`
- Test: `core/tests/test_home_attendance.py` (create). Classes use `AnalyticsFixture` from `core/tests/test_admin_overview_analytics.py`. In that fixture, `TODAY` is Tue 2026-07-14, `self.day(date, {enrollment: P|A})` makes a submitted register, and `self.s1`, `self.s2` are two students in Grade 1.

**Interfaces:**
- Produces:
  - `month_trend(today: date) -> dict` with keys `this` (float|None, % for the 1st..today), `last` (float|None, % for the whole previous calendar month), `change` (float|None, `round(this - last, 1)`), `direction` (`"up"`, `"down"`, `"same"` or None), `last_label` (previous month's full name, e.g. `"June"`).
  - `WEEKDAY_WINDOW_DAYS = 56`, `WEEKDAY_MIN_DAYS = 2`, `WEEKDAY_GAP_POINTS = 2`.
  - `weekday_pattern(today: date, days: int = WEEKDAY_WINDOW_DAYS) -> dict` with keys `rows` (Monday-first list of `_bars.html` rows: `label` = `"Mon"`.., `value`, `display` = `"92.5%"`, `low` = value < `ATTENDANCE_TARGET_PERCENT`, `url` = None) and `lowest` (`{"day": "Monday", "gap": 4}` or None).

- [ ] **Step 1: Write the failing tests**

```python
class MonthTrendTests(AnalyticsFixture, TestCase):
    def test_down_against_last_month(self):
        for d in (2, 3):
            self.day(datetime.date(2026, 6, d), {self.s1: P, self.s2: P})
        for d in (6, 7):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        t = analytics.month_trend(TODAY)
        self.assertEqual(t["this"], 50.0)
        self.assertEqual(t["direction"], "down")
        self.assertEqual(t["last_label"], "June")
        self.assertEqual(t["change"], round(50.0 - t["last"], 1))

    def test_no_data_this_month(self):
        self.day(datetime.date(2026, 6, 2), {self.s1: P, self.s2: P})
        t = analytics.month_trend(TODAY)
        self.assertIsNone(t["this"])
        self.assertIsNone(t["direction"])

    def test_no_comparison_without_last_month(self):
        AttendanceRegister.objects.filter(date__lt=datetime.date(2026, 7, 1)).delete()
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: A})
        t = analytics.month_trend(TODAY)
        self.assertEqual(t["this"], 50.0)
        self.assertIsNone(t["last"])
        self.assertIsNone(t["change"])
        self.assertIsNone(t["direction"])

    def test_draft_registers_do_not_count(self):
        self.day(datetime.date(2026, 7, 6), {self.s1: A, self.s2: A}, submit=False)
        self.assertIsNone(analytics.month_trend(TODAY)["this"])


class WeekdayPatternTests(AnalyticsFixture, TestCase):
    def test_mondays_stand_out(self):
        for d in (6, 13):  # Mondays
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        for d in (1, 7, 8, 14):  # Wed, Tue, Wed, Tue
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        w = analytics.weekday_pattern(TODAY, days=14)
        self.assertEqual([r["label"] for r in w["rows"]], ["Mon", "Tue", "Wed"])
        self.assertEqual(w["rows"][0]["value"], 50.0)
        self.assertTrue(w["rows"][0]["low"])
        self.assertEqual(w["lowest"]["day"], "Monday")
        self.assertEqual(w["lowest"]["gap"], 33)  # overall 10/12 = 83.3, Monday 50.0

    def test_a_weekday_with_one_day_of_data_is_left_out(self):
        self.day(datetime.date(2026, 7, 13), {self.s1: P, self.s2: A})  # one Monday only
        for d in (7, 14):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        w = analytics.weekday_pattern(TODAY, days=14)
        self.assertEqual([r["label"] for r in w["rows"]], ["Tue"])
        self.assertIsNone(w["lowest"])  # needs two weekdays to compare

    def test_no_day_stands_out_under_two_points(self):
        for d in (6, 7, 13, 14):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: P})
        self.assertIsNone(analytics.weekday_pattern(TODAY, days=14)["lowest"])

    def test_no_data(self):
        self.assertEqual(analytics.weekday_pattern(TODAY, days=14), {"rows": [], "lowest": None})
```

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_attendance --noinput`
Expected: FAIL with `AttributeError: module 'core.analytics' has no attribute 'month_trend'`.

- [ ] **Step 3: Implement `month_trend` and `weekday_pattern` in `core/analytics.py`**

- `month_trend`: use `reports.counts(_entries(period))["percentage"]` for each period. `direction` is `"same"` when `change == 0`.
- `weekday_pattern`: run one grouped query over `_entries(Period(today - days + 1, today))` by `register__date`, then group by weekday in Python. Keep a weekday only if it has at least `WEEKDAY_MIN_DAYS` dates. Each weekday's % is the sum of present over the sum of present+absent across its dates. The overall % is the same sum across the kept weekdays. `lowest` is set only when 2 or more weekdays are kept and `overall - min >= WEEKDAY_GAP_POINTS`. `gap = round(overall - min)`, and `day` is the full English weekday name.

- [ ] **Step 4: Run the tests and see them pass**

Run: the same command. Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add core/analytics.py core/tests/test_home_attendance.py
git commit -m "feat(overview): attendance trend vs last month and day-of-week pattern"
```

---

### Task 2: Best and worst classes, the 75% list, and the tab context

**Files:**
- Modify: `core/analytics.py` (`attendance_tab_context`)
- Test: `core/tests/test_home_attendance.py`

**Interfaces:**
- Consumes: `month_trend`, `weekday_pattern` (Task 1); the existing `class_comparison(period)`, `_class_row(row, with_link)`, `frequent_absentees(period)`, `current_term(today)`, `month_to_date(today)`.
- Produces:
  - `class_extremes(rows: list, *, with_links: bool) -> dict | None`. `rows` comes from `class_comparison` (lowest first). Returns None when `len(rows) < 4`. Otherwise `{"best": [...], "worst": [...]}` with `k = min(3, len(rows) // 2)`. `best` holds the top k, highest first. `worst` holds the bottom k, lowest first. Both are mapped through `_class_row`.
  - `LOW_ATTENDANCE_PERCENT = 75`, `LOW_ATTENDANCE_MIN_DAYS = 5`.
  - `low_attendance_students(term, today, limit=ABSENTEE_LIST_LIMIT) -> dict` returns `{"rows": [{"student_id", "name", "class_name", "percentage"}], "total": n}`. It counts students with at least `LOW_ATTENDANCE_MIN_DAYS` marked days in `term.start_date..min(today, term.end_date)` and a percentage strictly below 75, lowest first, then by name. The class shown is the student's ACTIVE enrollment, as in `frequent_absentees`. The query count stays constant.
  - `ABSENT_VIEWS = ("month", "term")`.
  - `attendance_tab_context(today, *, include_absentees: bool, absent_view: str = "month", class_links: bool = False) -> dict` with keys:
    - `trend`, `heatmap`, `has_data`, `weekday`.
    - `classes` (from `class_extremes(class_comparison(month_to_date(today)), with_links=class_links)`).
    - `absent_view` (an unknown value becomes `"month"`).
    - `absentees`: None without `include_absentees`. For `"month"` it is `frequent_absentees(month_to_date(today))`. For `"term"` it is `low_attendance_students(term, today)` when a term is running, or `{"rows": [], "total": 0, "no_term": True}` otherwise. Only the chosen view is queried.
    - `absentee_threshold`, `low_percent` (75), `label`.

- [ ] **Step 1: Write the failing tests**

```python
def _rows(*pcts):
    return [{"class_grade_id": i, "class_name": f"C{i}", "class_order": i, "present": 0, "absent": 0,
             "percentage": p} for i, p in enumerate(sorted(pcts), start=1)]


class ClassExtremesTests(TestCase):
    def test_hidden_under_four_classes(self):
        self.assertIsNone(analytics.class_extremes(_rows(70, 80, 90), with_links=False))

    def test_four_or_five_classes_split_without_overlap(self):
        for rows in (_rows(70, 80, 90, 95), _rows(70, 80, 85, 90, 95)):
            c = analytics.class_extremes(rows, with_links=False)
            self.assertEqual([r["value"] for r in c["worst"]], [70, 80])
            self.assertEqual([r["value"] for r in c["best"]], [95, 90])

    def test_three_each_from_six_or_more(self):
        c = analytics.class_extremes(_rows(60, 70, 80, 85, 90, 95, 99), with_links=False)
        self.assertEqual([r["value"] for r in c["worst"]], [60, 70, 80])
        self.assertEqual([r["value"] for r in c["best"]], [99, 95, 90])
        self.assertIsNone(c["best"][0]["url"])

    def test_links_only_when_allowed(self):
        c = analytics.class_extremes(_rows(60, 70, 80, 90), with_links=True)
        self.assertTrue(c["best"][0]["url"].startswith("/"))


class LowAttendanceTests(MarksFixture, TestCase):  # term_b = 2026-07-01..09-30
    def test_below_75_this_term_lowest_first(self):
        for d, s2 in zip((1, 2, 3, 6, 7, 8), (A, A, A, A, P, P)):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: s2})
        result = analytics.low_attendance_students(self.term_b, TODAY)
        self.assertEqual([(r["name"], r["percentage"]) for r in result["rows"]], [("Meena Das", 33.3)])
        self.assertEqual(result["total"], 1)

    def test_exactly_75_is_not_listed(self):
        for d, s2 in zip((1, 2, 3, 6, 7, 8, 9, 10), (A, A, P, P, P, P, P, P)):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: s2})
        self.assertEqual(analytics.low_attendance_students(self.term_b, TODAY)["rows"], [])

    def test_needs_five_marked_days(self):
        for d in (1, 2, 3, 6):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        self.assertEqual(analytics.low_attendance_students(self.term_b, TODAY)["rows"], [])

    def test_tab_context_switches_views_and_handles_no_term(self):
        ctx = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        self.assertEqual(ctx["absent_view"], "term")
        self.assertNotIn("no_term", ctx["absentees"])
        bogus = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="bogus")
        self.assertEqual(bogus["absent_view"], "month")
        self.term_b.delete()
        none = analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        self.assertTrue(none["absentees"]["no_term"])
        hidden = analytics.attendance_tab_context(TODAY, include_absentees=False, absent_view="term")
        self.assertIsNone(hidden["absentees"])

    def test_only_the_chosen_view_is_queried(self):
        with mock.patch("core.analytics.low_attendance_students") as term_list:
            analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="month")
        term_list.assert_not_called()
        with mock.patch("core.analytics.frequent_absentees") as month_list:
            analytics.attendance_tab_context(TODAY, include_absentees=True, absent_view="term")
        month_list.assert_not_called()
```

(`MarksFixture` is imported from `core.tests.test_admin_overview_analytics`; `mock` from `unittest`. If deleting `term_b` is blocked by a protected relation, end its dates before TODAY instead.)

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_attendance --noinput`
Expected: FAIL with `AttributeError ... 'class_extremes'`.

- [ ] **Step 3: Implement** `class_extremes`, `low_attendance_students` and the extended `attendance_tab_context` to the Interfaces above. For `low_attendance_students`, run one grouped query per student (present and absent counts) filtered with `.filter(total__gte=LOW_ATTENDANCE_MIN_DAYS)`. Compute the percentage in Python with `reports.percentage`, then filter, sort and trim. Do not run a query per student.

- [ ] **Step 4: Run the tests and see them pass**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_attendance core.tests.test_admin_overview_analytics core.tests.test_ui_admin_home_tabs --noinput`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add core/analytics.py core/tests/test_home_attendance.py
git commit -m "feat(overview): best and worst classes, below-75% list, attendance tab context"
```

---

### Task 3: View, template, CSS and page tests

**Files:**
- Modify: `core/views.py` (`admin_overview`, the `tab == "attendance"` branch)
- Modify: `templates/partials/home/_attendance.html` (rewrite)
- Create: `templates/partials/home/_absentee_row.html`
- Modify: `static/css/erp.css`
- Modify: `docs/DESIGN_SYSTEM.md` (add the row `| Segmented switch (links) | erp-seg, erp-seg-link with aria-current="page" | btn-group | Ready |`)
- Test: `core/tests/test_ui_admin_home_tabs.py`

**Interfaces:**
- Consumes: `attendance_tab_context(today, *, include_absentees, absent_view, class_links)` (Task 2).
- View: `absent_view=request.GET.get("absent", "month")`, `class_links=can["classes"]`. The gating rule for `include_absentees` stays `can_see_students and can_see_attendance`.

**Card copy (exact):**

| Card | `erp-card--` | Title (`h3.erp-analytics-title`) | Content |
|---|---|---|---|
| 1 | `trend` | Attendance this month | `<p class="erp-trend-figure">{{ this }}%</p>`, then one of: "Up {change} points from {last}% in {last_label}." / "Down {abs change} points from {last}% in {last_label}." / "Same as {last_label} ({last}%)." / "No comparison yet." An arrow ▲/▼ goes in `<span aria-hidden="true">`. When `this` is None: `erp-card-empty` "No submitted attendance this month yet." |
| 2 | `heat` | Attendance heatmap | unchanged from today's template |
| 3 | `weekday` | Day of the week | sub "Last 8 weeks."; `_bars.html` with `rows=weekday.rows colour="attendance" target=80`; the line "{Day}s are {gap}% lower than average." or "No day of the week stands out."; `erp-card-empty` "Not enough attendance yet to compare days." when `rows` is empty |
| 4 | `classes` | Best and worst classes | sub "This month."; `h4.erp-home-sub` "Highest" then `_bars.html` best, "Lowest" then `_bars.html` worst (`target=80`). The whole card is left out when `classes` is None |
| 5 | `absent` | Absentees | switch `<nav class="erp-seg" aria-label="Absentee view">` with two `a.erp-seg-link`: "This month" (`?tab=attendance`) and "Below 75% this term" (`?tab=attendance&absent=term`), the active one with `aria-current="page"`. Sub: "Absent {threshold} or more days, this month." / "Under 75% attendance this term (5 or more days marked)." Rows: `_fold_rows.html` with `row_template="partials/home/_absentee_row.html" noun="students"`. Empty: "No student was absent {threshold} or more days this month." / "No student is under 75% this term." / "No term is running." When `total` exceeds the rows shown: `erp-note-text` "Showing {n} of {total}." The card is left out when `absentees` is None |

`_absentee_row.html`: an `li.erp-home-row` holding `span.erp-home-main` (name · class) and `span.erp-home-meta` ("{n} days absent" or "{pct}%"), wrapped as a link to `core:student-detail` in the same way as `_register_row.html` (an `a.erp-home-open` "Open" with `erp-sr-only` name).

**CSS:**
- `.erp-seg` is a two-link pill row (`display:flex`, gap `--erp-space-1`, border `--erp-rule`, radius 999px). `.erp-seg-link` has a minimum height of 44px. `[aria-current="page"]` uses `--erp-action-wash` and `--erp-action-strong`.
- `.erp-trend-figure` uses `font-size: var(--erp-text-title)` and weight 700.
- In the existing desktop media query, inside `.erp-home .erp-analytics`: `--trend` span 4, `--heat` span 8, `--weekday` span 6, `--classes` span 6, `--absent` span 12. When `--classes` is absent, `--weekday` spans 12 (an `erp-analytics--no-classes` modifier, matching how `--no-absent` works today).
- Delete `.erp-absentee*` rules only if `grep -rn "erp-absentee" templates core/templates core/tests` finds no other use, and update any `test_ui_*` that pins them.

- [ ] **Step 1: Write the failing page tests** (in `HomeTabsTests`; seed data in each: `for d in (1, 2, 3, 6, 7, 8): self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})`). Add a helper `four_classes(self)` that makes Grade 2–4, each with a Section "A", one student enrolled via `self.enroll_student`, and a submitted register on 2026-07-02.

```python
    def test_attendance_cards_in_order(self):
        html = self.get(tab="attendance").content.decode()
        order = [html.index(t) for t in ("Attendance this month", "Attendance heatmap", "Day of the week", "Absentees")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("Best and worst classes", html)  # one class only

    def test_absentee_switch_links_and_current(self):
        month = self.get(tab="attendance").content.decode()
        self.assertIn('href="?tab=attendance&amp;absent=term"', month)
        self.assertRegex(month, r'<a class="erp-seg-link" href="\?tab=attendance" aria-current="page">This month</a>')
        term = self.get(tab="attendance", absent="term")
        self.assertEqual(term.context["attendance_tab"]["absent_view"], "term")
        self.assertContains(term, "Meena Das")
        self.assertEqual(self.get(tab="attendance", absent="x").context["attendance_tab"]["absent_view"], "month")

    def test_no_names_in_either_absentee_view_without_view_student(self):
        client = self.viewer("att-only", "view_school", "view_attendanceentry")
        for view in ("month", "term"):
            response = self.get(client, tab="attendance", absent=view)
            self.assertNotContains(response, "Meena Das")
            self.assertNotContains(response, "erp-seg")

    def test_class_links_need_view_classgrade(self):
        self.four_classes()
        self.assertContains(self.get(tab="attendance"), "erp-class-link")
        client = self.viewer("no-classes", "view_school", "view_attendanceentry", "view_student")
        response = self.get(client, tab="attendance")
        self.assertContains(response, "Best and worst classes")
        self.assertNotContains(response, "erp-class-link")

    def test_attendance_tab_queries_do_not_grow_with_classes(self):
        self.get(tab="attendance")
        with CaptureQueriesContext(connection) as before:
            self.get(tab="attendance")
        self.four_classes()
        with CaptureQueriesContext(connection) as after:
            self.get(tab="attendance")
        self.assertEqual(len(before), len(after))

    def test_attendance_card_css_is_pinned(self):
        css = Path(settings.BASE_DIR, "static/css/erp.css").read_text(encoding="utf-8")
        for rule in ('.erp-seg-link[aria-current="page"]', ".erp-trend-figure",
                     ".erp-home .erp-analytics > .erp-card--absent { grid-column: span 12;"):
            self.assertIn(rule, css)
```

Note: the query-growth test compares a 1-class page (no classes card) with a 4-class page (classes card shown). If showing the card adds a fixed number of queries, seed `four_classes` first and then add three more classes before the second capture, so both captures render the same cards.

Also extend `OverviewNoBootstrapTests`. In `test_overview_uses_no_bootstrap_classes` and `test_overview_cards_use_erp_card`, add the attendance tab with `absent=term` to the pages checked, and seed data so the trend, weekday and absentee cards render.

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs --noinput`
Expected: FAIL (titles missing, no `erp-seg`).

- [ ] **Step 3: Implement** the view change, the template, `_absentee_row.html`, the CSS and the DESIGN_SYSTEM row, to the table above.

- [ ] **Step 4: Run the tests and see them pass**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs core.tests.test_home_attendance core.tests.test_admin_overview_analytics --noinput`, then `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core --pattern="test_ui*.py" --parallel 4 --noinput`, then the Gate 4B tests (the module holding the `attendance_pages` rules; find it with `grep -rln attendance_pages core/tests`).
Expected: all `OK`, with `route_permissions.json` unchanged.

- [ ] **Step 5: Check in the browser** at 360px and 1280px (restart `runserver` first, because the template loader is cached, and open `/static/css/erp.css` directly to refresh it). Check: no horizontal scroll, switch targets are at least 44px, the five cards are in spec order, and the desktop grid has no holes. Stop the server afterwards (low memory on this PC).

- [ ] **Step 6: Commit**

```bash
git add core/views.py templates/partials/home/_attendance.html templates/partials/home/_absentee_row.html static/css/erp.css docs/DESIGN_SYSTEM.md core/tests/test_ui_admin_home_tabs.py
git commit -m "ui(overview): Attendance tab with trend, day-of-week, best/worst classes and absentee switch"
```
