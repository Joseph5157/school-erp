# School Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved charts to the Admin Overview, student page and teacher area, plus a Needs attention list, term comparison and printable summary, and stop charts stretching on wide screens.

**Architecture:** Pure geometry lives in `core/charts.py`. Marks calculations live in `core/marks_analytics.py`, attendance additions in the existing `core/analytics.py`. Views pass plain dicts to template partials that draw inline SVG. No JavaScript, chart library, model or migration.

**Tech Stack:** Django, server-rendered templates, inline SVG, `static/css/erp.css`, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-11-02-school-charts-design.md`. Read it first. Mockup: `.superpowers/brainstorm/2755-1793591243/content/combined-v1.html`.

## Global Constraints

- No migrations and no new dependencies.
- Attendance uses `reports.reportable_entries()`. A day with no data is left out, never 0%. Statuses are only PRESENT and ABSENT.
- Marks use FINALIZED assessments and MARKED results. A score is a percentage of its own assessment's maximum. ABSENT is never zero.
- Dates use `business_today()`.
- `ATTENDANCE_TARGET_PERCENT = 80`, `MIN_COMPARISON_STUDENTS = 5`, radar shows 3 to 8 subjects on a 0-100 scale in stable order, term comparison needs at least 3 shared subjects.
- Bars and columns are at most 24px thick. Under 80% attendance is red and also labelled with its value.
- Colours are existing tokens: `--erp-viz-attendance`, `--erp-viz-marks`, `--erp-viz-low`, `--erp-viz-grid`. Bullet and radar use grey plus attendance blue.
- Chart markup uses SVG attributes and no `style="..."`, because the existing analytics avoid inline styles.
- Every chart has `role="img"`, a text alternative, a visually hidden value list (`visually-hidden erp-visually-hidden-data`) and a `<title>` per mark.
- Link a chart only when the viewer can open the target. Read the target view's decorator and test the same permission.
- Rows are never ranked by performance, except the lowest-first lists the spec names.
- Phones: 360 and 390 px, no sideways page scroll, 44px tap targets.
- Copy on the print page: "Progress summary. Not an official report card."
- The Overview already has a card section titled "Needs attention". The new student list is titled **"Students needing attention"** so the page doesn't have two identical headings. Its empty state is "No students need attention right now."
- After CSS edits, run `python manage.py test --pattern="test_ui*.py" --parallel 4`. Run `collectstatic` and restart the server before screenshots.
- Each stage is one PR, checked at 360, 390, 1440 and 1920 px with the sidebar open and closed. Merge only on green CI and the product owner's say-so.

## Review Focus

- A score of exactly 0: it's a real value and draws an empty bar labelled 0, not hidden. Avoid truthiness checks on scores. Tested in Tasks 1 and 4.
- A student ABSENT for every test in a subject: the subject is left out, never drawn as 0. Tested in Task 4.
- A student who moved section mid-term: the section average uses their term placement section, and their own score keeps all their results. Tested in Task 4.
- A school with many classes (25+): columns scroll inside their card, and the page itself doesn't scroll sideways. Tested in Task 2.
- A print link opened after results were corrected or withdrawn: "not available yet", no marks shown. Tested in Task 10.

---

## Stage 0

### Task 0: Check staging and start the branch

**Files:** Modify `.gitignore`; add the spec and this plan.

- [ ] **Step 1:** Open staging in the product owner's Chrome (the local machine may not resolve the host), and check the Overview and Students pages at desktop and phone widths. Report any problem before continuing. Expected: pages load with no visible breakage.
- [ ] **Step 2:** From up-to-date `main`, create `feat/charts-overview-attendance`. Add `.superpowers/` to `.gitignore`.
- [ ] **Step 3:** Commit: `git add .gitignore docs/superpowers/specs/2026-11-02-school-charts-design.md docs/superpowers/plans/2026-11-02-school-charts.md && git commit -m "docs: school charts design and plan"`

## Stage 1: Overview attendance (PR 1)

### Task 1: Chart geometry

**Files:** Create `core/charts.py`, `core/tests/test_charts.py`.

**Interfaces:** Produces these pure functions. All return plain dicts for templates, with no database access. `None` means "nothing to draw".

- `ring(done: int, total: int, size=76, stroke=8) -> dict | None`: keys `percent` (whole number), `done`, `total`, `size`, `center`, `radius`, `stroke`, `circumference`, `dash`.
- `donut(parts: list[tuple[str, int]], size=110, stroke=15) -> dict | None`: keys `total`, `size`, `center`, `radius`, `stroke`, `headline_percent` (first part's share), `segments`, a list of `{label, count, share, dash, gap, offset, index}`. Zero-count parts draw nothing but stay in the list. Shares come from `shares()` (below), so they total 100.
- `gauge(percent: float | None, target: float) -> dict | None`: 200x122 viewBox semicircle. Keys `percent`, `target`, `track_d`, `value_d`, `tick` (`x1, y1, x2, y2`), `met` (bool).
- `columns(rows: list[dict], height=120, max_value=100) -> list[dict]`: each input row has `label`, `value`, `display`, optional `url`, `low`. Adds `bar_height` and `bar_y`. A zero value has `bar_height` 0.
- `bullet(score: float, pass_percent: float | None, comparison: float | None) -> dict`: 0-100 coordinates for a `viewBox="0 0 100 16"`. Keys `score`, `pass_width` (None if no pass mark), `marker_x` (None if no comparison).
- `radar(axes: list[str], outlines: list[dict], size=(280, 180)) -> dict | None`: returns None unless `3 <= len(axes) <= 8`. Each outline is `{key, label, values}` and at most 2 are allowed (raise `ValueError` for more). Returns `width`, `height`, `grid` (four polygon strings at 25/50/75/100), `spokes`, `labels` (`{text, x, y, anchor}`), `outlines` (`{key, label, points}`). First axis at the top, clockwise.

- [ ] **Step 1: Write failing tests** in `test_charts.py`:

```python
def test_ring_is_none_with_nothing_to_count(self):
    self.assertIsNone(charts.ring(0, 0))
def test_ring_zero_done_is_a_real_zero(self):
    self.assertEqual(charts.ring(0, 8)["percent"], 0)
    self.assertEqual(charts.ring(0, 8)["dash"], 0)
def test_ring_full_dash_equals_circumference(self):
    r = charts.ring(8, 8); self.assertEqual(r["percent"], 100); self.assertEqual(r["dash"], r["circumference"])
def test_donut_shares_total_100_and_empty_is_none(self):
    d = charts.donut([("Present", 412), ("Absent", 38)])
    self.assertEqual(sum(s["share"] for s in d["segments"]), 100)
    self.assertEqual(d["headline_percent"], 92)
    self.assertIsNone(charts.donut([("Present", 0), ("Absent", 0)]))
def test_gauge_none_percent_draws_nothing_and_met_flag(self):
    self.assertIsNone(charts.gauge(None, 80))
    self.assertTrue(charts.gauge(80, 80)["met"]); self.assertFalse(charts.gauge(79.9, 80)["met"])
def test_columns_zero_value_has_no_height(self):
    row = charts.columns([{"label": "1", "value": 0, "display": "0%"}])[0]
    self.assertEqual(row["bar_height"], 0); self.assertEqual(row["bar_y"], 120)
def test_bullet_keeps_zero_score_and_missing_parts(self):
    b = charts.bullet(0, None, None)
    self.assertEqual(b["score"], 0); self.assertIsNone(b["pass_width"]); self.assertIsNone(b["marker_x"])
def test_radar_only_draws_3_to_8_axes(self):
    self.assertIsNone(charts.radar(["a", "b"], [{"key": "s", "label": "S", "values": [1, 2]}]))
    self.assertIsNone(charts.radar(list("abcdefghi"), [{"key": "s", "label": "S", "values": [1] * 9}]))
    self.assertIsNotNone(charts.radar(list("abc"), [{"key": "s", "label": "S", "values": [1, 2, 3]}]))
def test_radar_first_axis_points_straight_up_at_100(self):
    r = charts.radar(list("abcd"), [{"key": "s", "label": "S", "values": [100, 0, 0, 0]}])
    x, y = r["outlines"][0]["points"].split()[0].split(",")
    self.assertAlmostEqual(float(x), r["width"] / 2, places=1); self.assertLess(float(y), r["height"] / 2)
def test_radar_refuses_three_outlines(self):
    outline = {"key": "s", "label": "S", "values": [1, 2, 3]}
    with self.assertRaises(ValueError):
        charts.radar(list("abc"), [outline, outline, outline])
```

- [ ] **Step 2:** Run `python manage.py test core.tests.test_charts`. Expected: FAIL, module not found.
- [ ] **Step 3:** Implement `core/charts.py` with the signatures above. Move `_shares` from `analytics.py` to `charts.py` as `shares` and import it back in `analytics.py`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(charts): add chart geometry helpers`.

### Task 2: Chart partials and the no-stretch CSS

**Files:** Create `templates/partials/charts/_ring.html`, `_donut.html`, `_gauge.html`, `_columns.html`, `_bars.html`; modify `templates/partials/_trend_svg.html`, `core/analytics.py` (`trend_chart` only if needed), `static/css/erp.css`; test `core/tests/test_ui_school_charts.py`.

**Interfaces:**
- Consumes the Task 1 dicts.
- Produces includes taking `c` (chart dict) and `label` (accessible text). `_columns.html` takes `rows` and `colour` (`attendance` or `marks`). `_bars.html` takes `rows` (`label`, `value`, `display`, `low`, optional `url`) and `colour`, and draws with the existing `erp-class-bars` and `erp-class-row` markup and `<progress>`.
- CSS classes: `.erp-chart-card` (flex column), `.erp-chart-head`, `.erp-chart-big`, `.erp-chart-scroll` (`overflow-x: auto`), `.erp-cols`, `.erp-col`, `.erp-col--low`. The chart roots are `.erp-ring`, `.erp-donut` and `.erp-gauge`.

Rules that decide the build:
- Ring, donut, gauge and radar SVGs have fixed `width` and `height` attributes, so text never scales.
- Each column is its own `<svg width="24" height="120">` with a `<rect>` set by attributes, inside a flex row, so bars stay 24px on any screen. Each column has `min-width: 2.25rem`. `.erp-chart-scroll` wraps the row, so many classes scroll inside the card.
- Horizontal bars: `.erp-class-bars { max-width: 32rem; }`.
- Wide trend chart: replace the `height: auto` scaling. `.erp-trend--wide { height: 12.5rem; width: 100%; }` with `preserveAspectRatio="none"` on the wide SVG, and `vector-effect: non-scaling-stroke` on the line and grid. Dots in the wide SVG become zero-length `<line>` elements (`stroke-linecap: round`, non-scaling stroke, 8px, plus a 20px transparent one as the hit area) so they stay round when stretched. The phone chart stays as it is. Keep the `<title>` text unchanged, because `test_trend_dots_and_heat_cells_name_their_value_on_hover` pins it.

- [ ] **Step 1: Write failing tests** rendering each partial with `render_to_string`:

```python
def test_ring_partial_has_fixed_size_and_text_alternative(self): # asserts 'width="76"', 'role="img"', label text
def test_column_svg_is_24px_wide_whatever_the_card_width(self): # asserts 'width="24"' once per row, no 'style='
def test_many_columns_scroll_inside_the_card(self):
    html = render_to_string("partials/charts/_columns.html", {"rows": charts.columns([{"label": str(i), "value": 90, "display": "90%"} for i in range(25)]), "colour": "attendance", "label": "x"})
    self.assertIn("erp-chart-scroll", html); self.assertEqual(html.count('width="24"'), 25)
def test_column_links_only_when_given_a_url(self): # row with url renders <a href>, row without renders no <a>
def test_low_column_is_red_and_labelled(self): # low=True adds erp-col--low; display text is visible
def test_wide_trend_keeps_a_fixed_height_in_css(self):
    css = (Path(settings.BASE_DIR) / "static/css/erp.css").read_text(encoding="utf-8")
    self.assertIn(".erp-trend--wide { height: 12.5rem;", css); self.assertIn(".erp-class-bars { max-width: 32rem;", css)
```

- [ ] **Step 2:** Run `python manage.py test core.tests.test_ui_school_charts`. Expected: FAIL, template missing.
- [ ] **Step 3:** Create the partials and CSS as above.
- [ ] **Step 4:** Run the same command, then `python manage.py test core.tests.test_admin_overview_analytics` and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(charts): add chart partials and stop charts stretching`.

### Task 3: Overview attendance cards

**Files:** Modify `core/analytics.py`, `core/views.py:882-886`, `templates/partials/_attendance_analytics.html`, `static/css/erp.css`, `core/tests/test_admin_overview_analytics.py`.

**Interfaces:**
- Consumes `charts.ring`, `donut`, `gauge`, `columns` and the Task 2 partials.
- Produces `analytics.ATTENDANCE_TARGET_PERCENT = 80`, and:
  - `term_attendance(today) -> {"term", "percent", "chart"} | None`: `current_term` only. None when no term runs or no data.
  - `ring_term(today) -> AcademicTerm | None`: the most recently started term, which is the running term or the one just ended.
  - `completion_rings(today, *, can_view_results: bool, can_view_publications: bool, missing_attendance_url: str | None) -> list[dict]`: each `{key, label, term_name, chart, url}`.
  - `overview_context(..., include_publications=False, missing_attendance_url=None)` adds `gauge`, `donut`, `rings`, `class_columns`, `class_bars_phone`.

Definitions:
- *Registers today:* `strip["submitted"]` of `strip["expected"]`.
- *Marks entered:* assessments in `ring_term` dated up to today, FINALIZED out of all. Needs `core.view_studentresult`.
- *Results published:* distinct students with a `TermPublication` in status PUBLISHED for that term, out of distinct students with an enrollment effective in that term. A correction already turns a publication STALE, so don't compute fingerprints here. Needs `core.view_termpublication`.
- `class_columns`: `class_comparison` rows re-sorted by class name, `low` when under 80, `url` to `core:class-grade-detail` when the viewer may open it. `class_comparison` needs to return `class_grade_id`.
- `class_bars_phone`: the 5 lowest rows from `class_comparison`.

Template:
- Row 1: gauge, Today donut and rings. These replace `erp-today-strip` at all widths. Keep the "No school day today." text as the donut's empty state.
- Keep the trend card, heatmap and absentees as they are.
- Class card: `_columns.html` at desktop, `_bars.html` with `class_bars_phone` plus a link to all classes on phones (same hide/show pattern as `.erp-trend--phone`).
- Desktop grid: change `.erp-analytics` to `repeat(12, minmax(0, 1fr))`, with spans gauge 3, donut 3, rings 6, trend 8, heat 4, classes 8, absent 4, marks 12. The existing desktop-only-CSS test must still pass.

- [ ] **Step 1: Write failing tests** in a new `OverviewChartCardsTests(AnalyticsFixture, TestCase)`:

```python
def test_gauge_is_hidden_when_no_term_runs(self): # no term: assertNotContains(response, "erp-gauge")
def test_gauge_uses_the_running_term_and_names_the_80_target(self): # create term over TODAY, submit data: contains "Target 80%"
def test_donut_shows_todays_counts(self): # P+A today: contains "Present 1", "Absent 1"
def test_no_school_day_message_replaces_the_donut(self): # patch today to a Sunday: contains "No school day today"
def test_registers_ring_counts_submitted_of_expected(self): # context rings[key=registers] chart done/total == strip values
def test_marks_ring_needs_results_permission(self): # view_school-only login: no "Marks entered"
def test_publication_ring_needs_publication_permission(self): # view_school + view_studentresult login: no "Results published"
def test_rings_between_terms_name_the_term_that_just_ended(self): # term ended before TODAY: label contains its name
def test_class_columns_are_in_class_order_not_by_performance(self): # Grade 1 50%, Grade 2 100%: Grade 1 first, and Grade 3 at 40% still last
def test_class_under_80_is_flagged_low(self): # 50% row: low True
def test_class_link_absent_without_permission_to_open_it(self): # no <a> to class-grade-detail for a view_school-only login
def test_query_count_stays_constant_with_more_classes(self): # CaptureQueriesContext: 1 class vs 3 classes, assertEqual
```

Update this existing test: `test_renders_strip_trend_and_class_bars_with_data` now asserts `erp-donut` instead of `erp-today-strip`. Change any other page-level strip assertions the same way. Don't change `today_strip` unit tests, since that function stays.

- [ ] **Step 2:** Run `python manage.py test core.tests.test_admin_overview_analytics`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement the functions, the view arguments (`include_publications=request.user.has_perm("core.view_termpublication")`, and `missing_attendance_url` when the user passes the decorator on `report_missing_attendance`), the template and CSS.
- [ ] **Step 4:** Run that test module, then `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Run the app with a scratch seeded DB (see `memory/admin-overview-analytics.md`, "How to check visually"), `collectstatic`, and take screenshots at 360, 390, 1440 and 1920 with the sidebar open and closed. Expected: no stretched bars, no page sideways scroll, gauge text legible at phone size.
- [ ] **Step 6:** Commit `feat(ui): Overview gauge, donut, rings and class columns`. Push, open PR 1, and stop for the product owner's "merge".

## Stage 2: Overview marks and Needs attention (PR 2)

Branch `feat/charts-overview-marks` from updated `main`.

### Task 4: ADR and marks calculations

**Files:** Create `docs/adr/0022-analytics-subject-averages.md`, `core/marks_analytics.py`, `core/tests/test_marks_analytics.py`; modify `docs/UI_DESIGN_RULES.md:183`, `docs/adr/README.md`, `core/analytics.py`.

**Interfaces:** Produces in `core/marks_analytics.py`:
- `MIN_COMPARISON_STUDENTS = 5`
- `reporting_term(today) -> AcademicTerm | None`: the running term if it has finalized MARKED results, otherwise the most recently started term that does. `analytics.marks_snapshot` switches to this.
- `marked_results(term, scope: Q = Q()) -> QuerySet`: FINALIZED + MARKED `StudentResult` for the term, annotated with `percent` and `subject_name` (from `Assessment.subject_display_expression("assessment__")`).
- `subject_averages(term) -> list[{"subject_name", "average", "results"}]`: lowest first, ties by name.
- `student_subject_scores(student, term, scope: Q = Q()) -> list[SubjectScore]`, in subject name order. `SubjectScore` is a frozen dataclass: `subject_name: str, score: float, pass_percent: float | None, below_pass: bool, section_average: float | None`. `scope` filters both the student's and the section's results.
- `terms_with_results(student) -> list[AcademicTerm]`: newest first.

Rules:
- `score` is the plain average of the student's MARKED percents in the subject.
- `pass_percent` and `below_pass` use only tests where the student is MARKED and `pass_mark` is set: average of the student's percents vs average of `pass_mark * 100 / maximum_marks` over exactly those tests.
- `section_average` uses `term.enrollment_for(student).section`: the average of all MARKED percents in that section, subject and term, or None when fewer than `MIN_COMPARISON_STUDENTS` distinct students have marks.

- [ ] **Step 1:** Write ADR 0022 recording D1 and D2 from the spec: display-only averages, never stored, never on official report cards or guardian views, with `my_student_detail` as the only teacher result view allowed to show them. Amend `UI_DESIGN_RULES.md:183` to: "No totals, weighting, averages or ranks on teacher or guardian result views, except the charts on the teacher's student page (ADR 0022)." Add it to the ADR index.
- [ ] **Step 2: Write failing tests.** Reuse `MarksFixture` from `test_admin_overview_analytics` with its `assessment()` helper, extended with `subject=` and `pass_mark=` arguments:

```python
def test_reporting_term_prefers_the_running_term_with_results(self): ...
def test_reporting_term_falls_back_when_the_running_term_has_no_results(self): ...
def test_draft_assessments_are_ignored(self): ...
def test_score_is_the_plain_average_of_test_percentages(self):
    # 10/20 and 40/50 -> 65.0, not (50/70)
def test_zero_score_counts_as_a_real_zero(self):
    # score 0/20 -> score 0.0, subject present
def test_absent_for_every_test_leaves_the_subject_out(self): ...
def test_absent_test_is_skipped_not_zeroed(self):
    # 10/20 + ABSENT -> 50.0
def test_pass_compare_uses_only_tests_sat_with_a_pass_mark(self):
    # A: 8/20 pass 10, sat. B: 20/20 no pass mark. C: pass 20 of 20, ABSENT.
    # score 70.0; pass_percent 50.0; below_pass True
def test_no_pass_mark_means_no_pass_percent(self): ...
def test_section_average_hidden_under_5_students_and_shown_at_5(self): ...
def test_section_average_uses_the_term_placement_section_after_a_move(self): ...
def test_scope_limits_the_score_and_the_section_average(self): ...
def test_renamed_subject_groups_like_the_report_card(self):
    # subject_label differs across finalized assessments: two groups
def test_subject_averages_are_lowest_first(self): ...
```

- [ ] **Step 3:** Run `python manage.py test core.tests.test_marks_analytics`. Expected: FAIL.
- [ ] **Step 4:** Implement `core/marks_analytics.py`, using `values()` aggregation and a constant number of queries.
- [ ] **Step 5:** Run it, and `core.tests.test_admin_overview_analytics`. Expected: PASS.
- [ ] **Step 6:** Commit `feat(marks): subject scores for charts, ADR 0022`.

### Task 5: Marks by subject and score band columns

**Files:** Modify `core/analytics.py` (`overview_context`), `templates/partials/_attendance_analytics.html`, `static/css/erp.css`, `core/tests/test_admin_overview_analytics.py`.

**Interfaces:** Consumes `subject_averages`, `reporting_term`. Adds context key `marks_subjects` (rows for `_bars.html`, colour `marks`) and `marks.band_columns` (rows for `_columns.html`).

Replace the single `--marks` card with two: `erp-analytics-card--subjects` titled "Marks by subject" and `erp-analytics-card--bands` titled "Score bands". Each names the term. The marks-by-class bars go away. The "Finalized only, absent not counted as zero" text moves to the bands card, and absent count stays.

- [ ] **Step 1: Write failing tests:**

```python
def test_marks_by_subject_lists_lowest_first_and_names_the_term(self): ...
def test_score_bands_draw_as_columns_with_counts(self): # 'width="24"' once per band, counts visible
def test_marks_cards_need_results_permission(self): # no "Marks by subject" without view_studentresult
def test_no_results_shows_the_existing_empty_message(self): # "No finalized results yet."
```

Change `Marks snapshot` assertions in existing tests to `Marks by subject`. Keep `.erp-class-bar--marks` in CSS since the new bars use it.

- [ ] **Step 2:** Run the test module. Expected: new tests FAIL.
- [ ] **Step 3:** Implement. Update desktop grid spans so `subjects` and `bands` sit in row 4 and 5 per Task 6.
- [ ] **Step 4:** Run the module and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(ui): marks by subject and score band charts`.

### Task 6: Students needing attention

**Files:** Modify `core/marks_analytics.py`, `core/analytics.py`, `core/views.py:882-886`, `templates/partials/_attendance_analytics.html`, `static/css/erp.css`; test `core/tests/test_marks_analytics.py`, `core/tests/test_admin_overview_analytics.py`.

**Interfaces:** Produces `marks_analytics.students_needing_attention(term, absent_days: dict[int, int], threshold=3, limit=10) -> {"rows": [...], "total": int}`. Rows: `{student_id, name, class_name, below_subjects: list[str], absent_days: int | None, reason: str}`. `analytics.absent_day_counts(period) -> dict[student_id, days]`. Overview gets `overview_context(include_attention=False)`, set when the user has both `core.view_student` and `core.view_studentresult`, adding the key `attention`.

Rule: active students (Student ACTIVE with an ACTIVE enrollment) with `len(below_subjects) >= 2`, or `len(below_subjects) == 1` and `absent_days >= threshold`. Ordered by class name, then student name. Reason text exactly like: `Below pass in Maths and Science (Term 1); absent 4 days (last 14 days)`. Use one grouped query per student and subject. The Python step only groups rows.

- [ ] **Step 1: Write failing tests:**

```python
def test_two_subjects_below_pass_is_listed(self): ...
def test_one_subject_below_pass_alone_is_not_listed(self): ...
def test_one_subject_plus_frequent_absence_is_listed(self): ...
def test_frequent_absence_alone_is_not_listed(self): ...
def test_subject_with_no_pass_mark_never_counts(self): ...
def test_inactive_student_is_left_out(self): ...
def test_rows_order_by_class_then_name_not_by_performance(self): ...
def test_limit_keeps_the_true_total(self): ...
def test_reason_names_term_and_period(self):
    self.assertIn("Below pass in English and Mathematics (Term 2)", row["reason"])
def test_query_count_does_not_grow_with_students(self): # 2 vs 12 students, assertEqual
# Overview:
def test_list_needs_both_view_student_and_view_results(self): ...
def test_empty_state_wording(self): # "No students need attention right now."
def test_rows_link_to_the_student_page(self): ...
```

- [ ] **Step 2:** Run the modules. Expected: FAIL.
- [ ] **Step 3:** Implement. On phones the card comes right after the rings. On desktop: row 4 is attention span 7 and subjects span 5; row 5 is bands span 12 with its column row capped at `max-width: 32rem`.
- [ ] **Step 4:** Run both modules and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Screenshots at all four widths with the sidebar open and closed. Commit `feat(ui): students needing attention on the Overview`. Push, open PR 2, and stop for "merge".

## Stage 3: Student page (PR 3)

Branch `feat/charts-student-page`.

### Task 7: Progress section on the admin student page

**Files:** Create `templates/partials/charts/_bullet.html`, `_radar.html`, `templates/partials/_student_progress.html`, `core/tests/test_student_progress.py`; modify `core/views.py:2981-3004`, `core/templates/core/student_detail.html`, `core/analytics.py`, `static/css/erp.css`.

**Interfaces:**
- Consumes `student_subject_scores`, `terms_with_results`, `charts.bullet`, `charts.radar`, `charts.columns`.
- Produces:
  - `analytics.student_attendance_by_month(student, year, today) -> list[{"month": date, "label": "Jul", "percentage", "present", "absent"}]`: one query via `TruncMonth`, months with no data left out.
  - `marks_analytics.student_progress_context(student, term_id: str | None, scope=Q(), include_comparison=True) -> dict`: keys `term`, `terms`, `scores`, `bullets` (each score plus its `charts.bullet`), `radar` (None outside 3-8 subjects), `radar_note`. Later tasks rely on this name.
  - `_student_progress.html`, which takes that dict as `progress` and an optional `attendance_months`.

Term chosen by `?term=<id>`, restricted to `terms_with_results`; anything else falls back to the newest. Add `("progress", "Progress", True)` to `profile_sections`. Marks parts render only with `core.view_studentresult`. Attendance by month needs only `core.view_student`, which the page already requires. Desktop spans: bullet 5, radar 4, months 3. Chart roots are `.erp-bullet` and `.erp-radar`, and the comparison tick is `.erp-bullet-marker`. Each bullet row is one `<svg viewBox="0 0 100 16" preserveAspectRatio="none">` with a non-scaling tick, inside a row capped at `max-width: 32rem`. The bullet legend says "Section average". Bullet bar dark grey `#39424e` token: add `--erp-viz-student` and validate with the dataviz script.

- [ ] **Step 1: Write failing tests:**

```python
def test_progress_section_appears_in_the_section_nav(self): ...
def test_marks_charts_need_results_permission(self): # view_student only: months shown, no bullet
def test_defaults_to_newest_term_and_honours_a_valid_term_choice(self): ...
def test_unknown_term_param_falls_back_safely(self): # ?term=abc and another student's term
def test_radar_note_under_3_subjects_and_over_8(self): ...
def test_bullet_rows_keep_subject_order_not_score_order(self): ...
def test_marker_and_label_absent_when_section_is_small(self): # no 'erp-bullet-marker' under 5 students
def test_no_pass_mark_draws_no_band(self): ...
def test_month_with_no_register_is_left_out(self): ...
def test_student_with_no_results_sees_a_message(self): # "No finalized results yet."
def test_query_count_constant_with_more_subjects(self): ...
```

- [ ] **Step 2:** Run `python manage.py test core.tests.test_student_progress`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run it and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Screenshots at all widths. On phones check radar labels don't clip at 360. Commit `feat(ui): student progress charts`. Push, open PR 3, and stop for "merge".

## Stage 4: Term comparison (PR 4)

Branch `feat/charts-term-compare`.

### Task 8: Compare with the previous term

**Files:** Modify `core/marks_analytics.py`, `templates/partials/_student_progress.html`; test `core/tests/test_student_progress.py`.

**Interfaces:** `student_progress_context` gains `compare: str | None` and returns `compare_url`, `comparing: bool`, `compare_note`.

With `?compare=previous` and a previous term in `terms_with_results` sharing at least 3 subjects, the radar draws only the shared subjects, with the grey outline as the previous term, labelled by its name. Otherwise the radar shows section average as normal. The link only appears when the comparison is possible, and it keeps the chosen `term`. The bullet chart doesn't change.

- [ ] **Step 1: Write failing tests:**

```python
def test_compare_link_needs_a_previous_term_with_3_shared_subjects(self): ...
def test_compare_draws_only_shared_subjects_with_the_term_name(self): ...
def test_compare_replaces_section_average_so_only_two_outlines_draw(self): ...
def test_bad_compare_value_is_ignored(self): ...
def test_compare_link_keeps_the_chosen_term(self): ...
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat(ui): compare a student's radar with the previous term`. Push, open PR 4, and stop for "merge".

## Stage 5: Teacher version (PR 5)

Branch `feat/charts-teacher`.

### Task 9: Teacher charts

**Files:** Modify `core/views.py` (`_teacher_visible_results` at 1388, `my_student_detail` at 1427, `my_home` at 993, `my_subject_results` at 1484), `core/templates/core/my_student_detail.html`, the `my_home` template, `core/templates/core/my_subject_results.html`, `core/marks_analytics.py`; test `core/tests/test_teacher_charts.py`.

**Interfaces:** Consumes `student_progress_context`, `charts.ring`, `charts.donut`.
- Refactor: extract `_teacher_result_scope(user, academic_year) -> Q` from `_teacher_visible_results` with unchanged behaviour. Pass it as `scope`.
- `marks_analytics.teacher_marks_ring(user, today) -> dict | None`: assessments in `current_teacher_assignments` scope, in the running or just-ended term, dated up to today, FINALIZED out of all.
- `analytics.class_teacher_attendance(section, today) -> dict`: the default period's `reports.counts` for that section.
- `marks_analytics.assessment_pass_fail(assessments, rows) -> dict[assessment_id, donut]`, computed from already loaded rows, with no extra queries. Only for assessments with a pass mark.

Placement: the spec's "assessment results page" is `my_subject_results` (there's no single-assessment teacher page), with one small donut above the table per assessment that has a pass mark. No charts on `my_gradebook` or marks entry. `my_student_detail` gets `_student_progress.html` above the Results table, scoped, without `attendance_months`.

- [ ] **Step 1: Write failing tests:**

```python
def test_subject_teacher_chart_only_has_their_subject(self): ...
def test_results_outside_the_assignment_dates_are_excluded(self): ...
def test_section_average_uses_only_the_teachers_scope(self): ...
def test_class_teacher_sees_all_subjects_of_their_section(self): ...
def test_fewer_than_3_visible_subjects_shows_only_the_bullet_chart(self): ...
def test_teacher_cannot_open_a_student_outside_scope(self): # still PermissionDenied
def test_home_ring_counts_only_own_assignments(self): ...
def test_attendance_summary_only_for_class_teachers(self): ...
def test_pass_fail_donut_only_with_a_pass_mark(self): ...
def test_gradebook_still_has_no_average_or_percent_text(self): ...
def test_guardian_views_have_no_charts(self): # report card page lacks 'erp-radar' and 'erp-bullet'
def test_scope_refactor_returns_the_same_results(self): # existing teacher tests also cover this
```

- [ ] **Step 2:** Run `python manage.py test core.tests.test_teacher_charts`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run it, then existing teacher and authorization tests: `python manage.py test core.tests.test_authorization --parallel 4` and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Screenshots of the teacher pages at 360 and 390. Commit `feat(ui): teacher charts`. Push, open PR 5, and stop for "merge".

## Stage 6: Printable summary (PR 6)

Branch `feat/charts-progress-summary`.

### Task 10: Progress summary page

**Files:** Create `core/templates/core/progress_summary.html`, `core/tests/test_progress_summary.py`; modify `core/views.py`, `core/urls.py`, `core/marks_analytics.py`, `templates/partials/_student_progress.html`, `static/css/erp.css`.

**Interfaces:**
- Consumes `publication.guardian_visible`, `charts.bullet`, `charts.radar`, `reports.student_summary`.
- Produces `marks_analytics.summary_from_publication(publication) -> list[SubjectScore]`, built from `publication.entries`: uses `subject_label`, `percentage`, `pass_mark`, `maximum_marks` and `status`, with the same rules as Task 4 and `section_average=None`.
- Routes: `students/<int:pk>/progress-summary/<int:term_pk>/` named `progress-summary`, decorated `administrator_required("core.view_studentresult")`, and `my/students/<int:pk>/progress-summary/<int:term_pk>/` named `my-progress-summary`, `teacher_required` with `can_view_report_card_as_teacher`, otherwise `PermissionDenied`. Both render `progress_summary.html`.

Behaviour:
- Find the student's PUBLISHED `TermPublication` for the term. If there isn't one or `guardian_visible()` is False, respond 200 with "This summary isn't available yet. It appears once this term's report card is published and up to date." and no marks.
- Marks and remark come from the publication (`remark_text`). `is_partial` shows "Some results are still pending." Attendance: `reports.student_summary(student, term.start_date, min(term.end_date, today))`.
- School name and logo: reuse whatever the report-card PDF letterhead uses (see `core/document_views.py:72` and ADR 0020).
- No section average and no marker. Radar has one outline.
- Print CSS in `erp.css`: `@media print` hides navigation and buttons, fits A4, bars use dark grey and hatched below-pass area so it reads in black and white. No new JavaScript: the page shows the text "Use your browser's Print command" and hides it when printing.
- Link from `_student_progress.html` only when the publication is visible and the viewer has access.

- [ ] **Step 1: Write failing tests:**

```python
def test_not_available_without_a_publication(self): # 200, wording, no score text
def test_not_available_after_a_correction_makes_it_stale(self): ...
def test_not_available_after_withdrawal(self): ...
def test_shows_published_values_and_the_published_remark(self):
    # A visible publication: its entry percentage and remark_text appear on the page.
def test_header_says_not_an_official_report_card(self):
    self.assertContains(response, "Progress summary. Not an official report card.")
def test_no_section_average_anywhere(self): # 'Section average' and 'erp-bullet-marker' absent
def test_partial_publication_says_results_are_pending(self): ...
def test_needs_results_permission_for_admins(self): ...
def test_subject_teacher_denied_and_class_teacher_allowed(self): ...
def test_nothing_is_created_or_sent(self): # TermPublication, Notification, IssuedDocument counts unchanged
def test_print_link_only_when_available(self): ...
```

- [ ] **Step 2:** Run `python manage.py test core.tests.test_progress_summary`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run it and `--pattern="test_ui*.py" --parallel 4`. Expected: PASS.
- [ ] **Step 5:** Open the page in Chrome's print preview. Expected: one A4 page, readable in black and white, no navigation.
- [ ] **Step 6:** Commit `feat(ui): printable progress summary`. Push, open PR 6, and stop for "merge".
