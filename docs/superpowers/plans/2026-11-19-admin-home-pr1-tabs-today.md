# Admin home PR 1: tab shell, removals, Today tab (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the crowded admin Overview into four tabs (Today / Attendance / Academics / Parents), delete the removed charts and their code, and build the full Today tab.

**Architecture:** One view (`core.views.admin_overview`) reads `?tab=` and builds only the active tab's context. Today's data comes from a new read-only module `core/home_today.py` (no HTTP). Each tab is its own partial under `templates/partials/home/`. Cards that survive from the old page move to their tab as they are; PRs 2–4 then rebuild those tabs from the spec.

**Tech Stack:** Django 5 templates (no JS needed), PostgreSQL, `static/css/erp.css`, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-11-18-admin-home-tabs-design.md`

**Scope:** This plan covers **PR 1 only**. PRs 2 (Attendance), 3 (Academics) and 4 (Parents) each get their own plan once the PR before them is merged, per the owner's one-PR-at-a-time rule.

## Global Constraints

- Tabs, in this order: **Today**, **Attendance**, **Academics**, **Parents**. Each is its own URL: `?tab=today|attendance|academics|parents`. No `tab`, or an unknown value, shows Today.
- Tabs are plain links with `aria-current="page"` on the active one. Not `role="tablist"`: each tab is a separate page load and works without JS.
- No rings, gauges or decorative charts. Use cards, lists, bars, the existing donut and the existing heatmap only.
- Every list row links somewhere, but only when the viewer has the permission that the target view's decorator checks. Otherwise it is plain text.
- Register late = not submitted by **10:00** on a school day. This is a per-school setting, `School.register_cutoff`, default `10:00`.
- Marks late = an assessment still DRAFT more than **15 days** after its `assessment_date`.
- Attendance statuses are only PRESENT and ABSENT (ADR 0007). The donut has **no "late" slice**, even though the spec says "present / late / absent".
- Birthdays: students only, ACTIVE, with a `date_of_birth`.
- Nothing repeats across tabs.
- Copy is short and plain, with sentence case and no em dashes, matching existing page copy.
- Tests: lint + the changed test modules + `--pattern="test_ui*.py"` (CSS changed). This PR adds a **migration**, so run the full suite locally once before pushing (`python manage.py test --parallel 4 --noinput`), per the test-running rule.

## Review Focus

1. **A non-school day** (weekend or holiday): Today says "No school day today". Compliance lists nothing as missing. Assessments and birthdays still show. → test in Task 3.
2. **Before 10:00**: a register not yet submitted is "not taken yet", never "late" or "missing". → test in Task 3.
3. **A birthday on 29 Feb in a non-leap year** shows on 28 Feb. **A week that crosses New Year** (Wed 30 Dec → Sun 3 Jan) still finds 1–3 Jan birthdays. → tests in Task 4.
4. **`?tab=nonsense` or `?tab=`** renders Today with status 200. **Old links with `?period=term`** are ignored (no notice, no error). → test in Task 5.
5. **A viewer without student permission** sees birthday and absentee counts but no names, and no row links to pages they cannot open. → test in Task 5.

---

## File map

| File | Change | Responsibility |
|---|---|---|
| `core/models.py` (`School`) | modify | add `register_cutoff` |
| `core/migrations/0094_school_register_cutoff.py` | create | the field |
| `core/forms.py` (`SchoolForm`) | modify | expose the field |
| `core/home_today.py` | create | Today data: attendance today, compliance, week assessments, week birthdays |
| `core/dashboard.py` | modify | glance cards = students, teachers, classes, current term; drop the `attendance` attention card |
| `core/analytics.py` | modify | delete removed code; add `attendance_tab_context`, `academics_tab_context` |
| `core/charts.py` | modify | delete `ring`, `gauge`, `_gauge_point` |
| `core/views.py` (`admin_overview`) | modify | tab routing, per-tab context |
| `core/templates/core/admin_overview.html` | rewrite | header + tab bar + active tab partial |
| `templates/partials/home/_tabs.html` | create | the tab bar |
| `templates/partials/home/_today.html` | create | Today cards |
| `templates/partials/home/_attendance.html` | create | heatmap + absentees (moved, interim) |
| `templates/partials/home/_academics.html` | create | attention list + subject bars (moved, interim) |
| `templates/partials/home/_parents.html` | create | guardian count + access reviews + announcements link (interim) |
| `templates/partials/_attendance_analytics.html`, `charts/_gauge.html`, `charts/_ring.html`, `_trend_svg.html` | delete | removed |
| `static/css/erp.css` | modify | delete rules for removed parts; add `.erp-home-tabs`, `.erp-home-card`, `.erp-home-list` |
| `core/tests/test_home_today.py` | create | Task 3–4 tests |
| `core/tests/test_ui_admin_home_tabs.py` | create | Task 5–6 page and CSS tests |
| `core/tests/test_admin_overview_analytics.py`, `test_ui_overview_order.py`, `test_ui_admin_overview_glance.py`, `test_charts.py`, `test_ui_school_charts.py` | modify | delete tests of removed code; point page tests at the right `?tab=` |

Work in a worktree: `.worktrees/admin-home-pr1`, branch `ui/admin-home-tabs-today`. Docker Postgres must be running (`everclass-postgres`), with `DJANGO_DEBUG=True`.

---

### Task 1: Per-school register cut-off

**Files:**
- Modify: `core/models.py` (class `School`, after `notification_channel`)
- Create: `core/migrations/0094_school_register_cutoff.py` (via `makemigrations`)
- Modify: `core/forms.py` (`SchoolForm.Meta.fields`)
- Test: `core/tests/test_home_today.py`

**Interfaces:**
- Produces: `School.register_cutoff: datetime.time`, default `datetime.time(10, 0)`. Also `home_today.register_cutoff() -> datetime.time`, which returns the school's value, or `time(10, 0)` when no School row exists.

- [ ] **Step 1: Write failing tests**

```python
class RegisterCutoffTests(TestCase):
    def test_default_is_ten_oclock(self):
        school = School.objects.create(name="X")
        self.assertEqual(school.register_cutoff, datetime.time(10, 0))

    def test_falls_back_to_ten_without_a_school(self):
        self.assertEqual(home_today.register_cutoff(), datetime.time(10, 0))

    def test_school_form_saves_the_cutoff(self):
        form = SchoolForm(data={"name": "X", "notification_channel": "PORTAL_ONLY",
                                "register_cutoff": "09:30"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().register_cutoff, datetime.time(9, 30))
```

- [ ] **Step 2: Run them to see them fail**

Run: `python manage.py test core.tests.test_home_today.RegisterCutoffTests --noinput`
Expected: FAIL (no field, no module).

- [ ] **Step 3: Implement**

`register_cutoff = models.TimeField("Registers due by", default=datetime.time(10, 0), help_text="A register submitted after this time on a school day counts as late.")`. Add it to `SchoolForm.Meta.fields` after `principal_name`, with widget `forms.TimeInput(attrs={"type": "time"}, format="%H:%M")`. Run `python manage.py makemigrations core -n school_register_cutoff`. Create `core/home_today.py` with a module docstring and `register_cutoff()`.

- [ ] **Step 4: Run tests to see them pass**, plus `python manage.py makemigrations --check --dry-run` (expected: "No changes detected").

- [ ] **Step 5: Commit** `feat(school): per-school register cut-off, default 10:00`

---

### Task 2: Remove the old charts and their code

Delete first, so later tasks build on a clean base.

**Files:**
- Modify: `core/analytics.py`. Delete `default_period`, `previous_period`, `_parse_date`, `_custom_label`, `resolve_period`, `trend_summary`, `term_attendance`, `ring_term`, `completion_rings`, `trend_chart`, `marks_snapshot`, `overview_context`, `MAX_CUSTOM_DAYS`, `MARK_BANDS`, `DEFAULT_PERIOD_DAYS`, `STEADY_BAND`. **Keep** `Period`, `current_term`, `_entries`, `today_strip`, `daily_trend`, `class_comparison` (PR 2 needs it), `student_attendance_by_month`, `_class_row`, `frequent_absentees`, `absent_day_counts`, `_heat_tier`, `attendance_heatmap`, `_subject_rows`.
- Modify: `core/charts.py`. Delete `ring`, `_gauge_point`, `gauge`.
- Delete: `templates/partials/_attendance_analytics.html`, `templates/partials/charts/_gauge.html`, `templates/partials/charts/_ring.html`, `templates/partials/_trend_svg.html`
- Modify: `core/dashboard.py`. Delete `system_checklist`.
- Modify: `static/css/erp.css`. Delete the rules for `.erp-rings`, `.erp-ring-*`, `.erp-gauge*`, `.erp-analytics-card--gauge|--rings|--trend|--classes|--bands`, `.erp-trend-*`, `.erp-period*`, `.erp-class-desk`, `.erp-class-phone`, `.erp-class-callouts`, `.erp-clear-row`, `.erp-clear-*`, `.erp-chart-pair`. Before deleting each selector, check with Grep that no other template uses it.
- Modify tests: delete the tests for the deleted functions and selectors in `test_admin_overview_analytics.py` (gauge, rings, period, trend, bands, class columns/callouts, card order), `test_ui_overview_order.py` (`test_gauge_and_rings_are_kept`, `test_checklist_*`, `SystemChecklistTests`), `test_charts.py` (ring, gauge) and `test_ui_school_charts.py` (string pins for the deleted CSS).

**Interfaces:**
- Produces: `analytics` without the deleted names. `admin_overview` is temporarily broken until Task 5. Keep the suite importable: in this task, have `admin_overview` render the header only (context `{}`).

- [ ] **Step 1: Delete the code, templates, CSS and tests listed above.**
- [ ] **Step 2: Prove nothing still points at them.** Run: `git grep -nE "completion_rings|term_attendance|resolve_period|trend_chart|marks_snapshot|overview_context|charts\.(ring|gauge)|_gauge\.html|_ring\.html|_trend_svg|_attendance_analytics|system_checklist"`. Expected: no output.
- [ ] **Step 3: Run** `ruff check .` and `python manage.py test core.tests.test_admin_overview_analytics core.tests.test_charts core.tests.test_ui_overview_order --noinput`, plus `--pattern="test_ui*.py"`. Expected: all pass.
- [ ] **Step 4: Commit** `refactor(overview): remove rings, gauge, trend, by-class, bands, period picker and checklist row`

---

### Task 3: Today data: attendance today and teacher compliance

**Files:**
- Modify: `core/home_today.py`
- Test: `core/tests/test_home_today.py` (reuse `AnalyticsFixture` / `MarksFixture` and `TODAY` from `core.tests.test_admin_overview_analytics`. TODAY is Tue 14 Jul 2026.)

**Interfaces:**
- Consumes: `reports.missing_attendance(start, end)`, `reports.expected_registers`, `analytics.today_strip(today)`, `charts.donut(parts)`, `SectionClassTeacher.objects.effective_on(date)`, `AssessmentTeacherAssignment`.
- Produces:
  - `attendance_today(today, *, can_open_registers: bool) -> dict` with keys `school_day: bool`, `donut` (`charts.donut([("Present", n), ("Absent", n)])`, or None when nothing is submitted), `present: int`, `absent: int`, `not_taken: list[dict]`. Each `not_taken` row is `{class_name, section_name, teacher_name, state, url}`, in class order then section. `teacher_name` is the class teacher effective today (`get_full_name() or username`), or `""`. `url` is the draft register's detail page when a register exists, otherwise `core:attendance-register-create`. It is None unless `can_open_registers`.
  - `register_compliance(today, now: datetime.datetime, cutoff: datetime.time) -> dict` with keys `late: list[row]` (submitted today after `cutoff` in local time; row adds `submitted_at`), `missing: list[row]` (not submitted, but only once `now`'s local time is past `cutoff`), `before_cutoff: bool`.
  - `overdue_marks(today, days=15) -> list[dict]`: DRAFT assessments with `assessment_date < today - timedelta(days=15)`, oldest first. Each row is `{name, class_name, section_name, subject, teacher_name, days_late, url}`. `teacher_name` comes from the `AssessmentTeacherAssignment` for the offering+section effective on `assessment_date`. `days_late = (today - assessment_date).days - 15`.
  - All three use a constant number of queries, whatever the number of sections or assessments (look up teachers in one query and map them by section/offering).

- [ ] **Step 1: Write failing tests**

```python
def test_not_taken_lists_class_and_teacher_in_class_order(self): ...
    # two sections, one submitted: one row, teacher_name == class teacher's full name
def test_not_taken_rows_link_only_with_permission(self): ...
    # can_open_registers=False -> every url is None
def test_donut_has_only_present_and_absent(self): ...
    # [s["label"] for s in result["donut"]["segments"]] == ["Present", "Absent"]
def test_non_school_day_has_no_rows_and_says_so(self): ...
    # Saturday 18 Jul 2026: school_day False, not_taken == [], compliance missing == []
def test_register_submitted_after_cutoff_is_late(self): ...
    # submitted_at 10:20 local, cutoff 10:00 -> in late, not in missing
def test_before_cutoff_nothing_is_missing(self): ...
    # now 09:15, register not submitted -> missing == [], before_cutoff True
def test_after_cutoff_unsubmitted_is_missing(self): ...
    # now 10:01 -> the section is in missing
def test_cutoff_is_read_from_the_school(self): ...
    # School.register_cutoff 09:00, submitted 09:30 -> late (via the view helper that passes register_cutoff())
def test_overdue_marks_after_15_days_only(self): ...
    # DRAFT dated today-15 -> not overdue; today-16 -> overdue with days_late == 1; FINALIZED today-30 -> not listed
def test_overdue_marks_names_the_assigned_teacher(self): ...
def test_compliance_query_count_does_not_grow_with_sections(self): ...
    # assertNumQueries(n) with 2 sections, the same n with 4
```

- [ ] **Step 2: Run them to see them fail.** `python manage.py test core.tests.test_home_today --noinput`
- [ ] **Step 3: Implement the three functions** in `core/home_today.py`. Use `timezone.localtime(...)` for every time comparison. Get "school day" from `bool(reports.expected_registers(today, today))`.
- [ ] **Step 4: Run them to see them pass.**
- [ ] **Step 5: Commit** `feat(home): today's attendance, late/missing registers and overdue marks`

---

### Task 4: Today data: this week's assessments and birthdays

**Files:**
- Modify: `core/home_today.py`
- Test: `core/tests/test_home_today.py`

**Interfaces:**
- Produces:
  - `week_range(today) -> tuple[date, date]`: `(today, the Sunday on or after today)`.
  - `week_assessments(today, *, can_open: bool) -> dict` with keys `today: list[row]` and `later: list[row]` (tomorrow through Sunday, by date then class order). A row is `{name, subject, class_name, section_name, date, url}`. `url` is `core:assessment-detail` when `can_open`, otherwise None.
  - `week_birthdays(today, *, can_see_names: bool) -> dict` with keys `today: list[row]`, `later: list[row]` and `count: int`. A row is `{name, class_name, date, age, url}`, where `date` is the birthday this year (a 29 Feb birthday falls on 28 Feb in a non-leap year), `age` is the age on that day, and `url` is `core:student-detail`. When `can_see_names` is False, both lists are empty and only `count` is filled.

- [ ] **Step 1: Write failing tests**

```python
def test_week_runs_from_today_to_sunday(self):
    self.assertEqual(home_today.week_range(TODAY), (TODAY, datetime.date(2026, 7, 19)))
def test_assessments_split_today_and_later_this_week(self): ...
    # one dated TODAY, one Thu 16 Jul, one Mon 20 Jul (excluded)
def test_birthday_today_and_later_this_week(self): ...
    # dob 2015-07-14 -> today, age 11; dob 2016-07-17 -> later; dob 2016-07-21 -> excluded
def test_29_feb_birthday_shows_on_28_feb_in_a_non_leap_year(self): ...
    # today = 2027-02-28 (Sun), dob 2016-02-29 -> in today
def test_week_crossing_new_year_finds_january_birthdays(self): ...
    # today = 2026-12-30 (Wed), dob 2017-01-02 -> in later, date 2027-01-02
def test_inactive_students_and_missing_dob_are_left_out(self): ...
def test_without_name_permission_only_the_count_is_given(self): ...
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement.** Birthday matching is done in Python over ACTIVE students with a `date_of_birth`. Select only the fields needed (`values` for id, full name, date_of_birth, plus the current class from the ACTIVE enrollment, in one query). That is cheap at school scale and handles 29 Feb and New Year without date arithmetic in SQL.
- [ ] **Step 4: Run them to see them pass.**
- [ ] **Step 5: Commit** `feat(home): this week's assessments and birthdays`

---

### Task 5: Tab shell and the per-tab view context

**Files:**
- Modify: `core/views.py` (`admin_overview`)
- Modify: `core/analytics.py` (add the two tab contexts below)
- Modify: `core/dashboard.py`. In `glance_cards`, the cards become students, teachers, classes and **current term** (key `term`, count = `current_term(today).name`, or `"-"`, summary "Running today." or "No term is running today.", url `core:academic-year-list` when the user has `core.view_academicyear`). Remove `_attendance` from `_CARDS` (Today's attendance card replaces it) and remove `_access_reviews` from `_CARDS` (it moves to Parents). Move the guardians glance card to a new `parents_glance(user)`.
- Rewrite: `core/templates/core/admin_overview.html`
- Create: `templates/partials/home/_tabs.html`, `_attendance.html`, `_academics.html`, `_parents.html`
- Test: `core/tests/test_ui_admin_home_tabs.py`; update page tests in `test_admin_overview_analytics.py` and `test_ui_admin_overview_glance.py` to request the right `?tab=`.

**Interfaces:**
- Consumes: Task 3–4 functions; `analytics.attendance_heatmap`, `frequent_absentees`, `absent_day_counts`, `_subject_rows`; `marks_analytics.reporting_term`, `term_label`, `students_needing_attention`; `dashboard.overview_cards`, `split_cards`.
- Produces:
  - `HOME_TABS = (("today", "Today"), ("attendance", "Attendance"), ("academics", "Academics"), ("parents", "Parents"))` in `core/views.py`.
  - Template context: `tabs` (list of `{key, label, url, current}`), `tab` (active key), plus exactly one of `today`, `attendance_tab`, `academics_tab`, `parents_tab`.
  - `analytics.attendance_tab_context(today, *, include_absentees: bool) -> dict` with keys `heatmap` and `absentees` (`frequent_absentees(Period(today.replace(day=1), today))`, or None), `absentee_threshold` and `label="this month"`.
  - `analytics.academics_tab_context(today, *, include_marks: bool, include_attention: bool) -> dict` with keys `term`, `term_label`, `subjects` (`_subject_rows(term)`) and `attention` (`students_needing_attention(term, absent_day_counts(this month), threshold=ABSENTEE_THRESHOLD_DAYS, period_label="this month", term_label=...)`, or None).
  - Today context (built in the view): `glance_cards`, `attention_cards` (the remaining `_CARDS`, attention only), `setup_first`/setup-checklist keys as today, `attendance` (Task 3), `compliance` (Task 3, `now=timezone.now()`, `cutoff=home_today.register_cutoff()`), `overdue_marks`, `assessments`, `birthdays`. Permission gates: `can_open_registers = has_perm("core.add_attendanceregister")`; compliance and overdue marks are shown only with `core.view_attendanceregister` / `core.view_assessment` respectively; `can_see_names = has_perm(data_access.STUDENT)`.
  - Parents context: `parents_glance(user)` card, `access_review_card` (`dashboard._access_reviews` when the user has `core.view_guardianaccessreview`), and an announcements link when the user has `core.view_announcement`.

- [ ] **Step 1: Write failing tests** in `test_ui_admin_home_tabs.py`

```python
def test_default_tab_is_today_and_marked_current(self): ...
    # GET overview -> 'aria-current="page"' on the Today link; four tab links in order Today, Attendance, Academics, Parents
def test_each_tab_has_its_own_url(self): ...
    # ?tab=attendance shows "Attendance heatmap", not "Birthdays"
def test_unknown_or_empty_tab_shows_today(self): ...
    # ?tab=nonsense and ?tab= -> 200, Today current
def test_old_period_links_are_ignored(self): ...
    # ?period=term -> 200, no notice text, Today current
def test_only_the_active_tab_is_queried(self): ...
    # assertNumQueries for ?tab=parents is below that of ?tab=today
def test_removed_parts_are_gone(self): ...
    # no "Still to finish", "Score bands", "Daily attendance", "erp-ring", "erp-gauge", "Checklist" on any tab
def test_viewer_without_student_permission_sees_no_names(self): ...
    # a user with view_school but not data_access.STUDENT: Today birthdays show a count only; Attendance tab has no absentee list
def test_nothing_repeats_across_tabs(self): ...
    # "Pending access reviews" only on Parents; "Attendance today" card only on Today
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement the view, the contexts and the templates.** The tab bar is a `<nav class="erp-home-tabs" aria-label="Overview sections">` holding links. Move the old cards' markup into `_attendance.html` (heatmap and absentees cards, unchanged apart from `a.` → `attendance_tab.`) and `_academics.html` (attention card and subject bars). Each interim tab ends with nothing else. PRs 2–4 fill them in.
- [ ] **Step 4: Run** the new module, `test_admin_overview_analytics`, `test_ui_admin_overview_glance`, `test_ui_overview_order` and `test_ui_admin_setup_checklist`. Expected: pass.
- [ ] **Step 5: Commit** `feat(overview): four tabs by job, each its own URL`

---

### Task 6: Today tab cards and CSS

**Files:**
- Create: `templates/partials/home/_today.html`
- Modify: `static/css/erp.css`
- Test: `core/tests/test_ui_admin_home_tabs.py`

**Card order (phone and desktop alike):** Needs attention rows (if any) → School at a glance → Attendance today → Teacher compliance → Assessments this week → Birthdays this week → setup checklist card (when setup is not first).

**Copy (exact):**
- Attendance today: heading "Attendance today". Donut legend "Present N", "Absent N". List heading "Not taken yet", with each row as "{class} {section} · {teacher}" and an action "Open". Empty states: "All registers are in." / "No school day today." / "No attendance yet."
- Teacher compliance: heading "Teacher compliance", with sub-lists "Late registers (after {cutoff:H:i})", "Missing registers" and "Marks overdue (15+ days)". Before the cut-off, show "Registers are due by {cutoff:H:i}." in place of the missing list. Empty: "Everyone is on time."
- Assessments: heading "Assessments", with groups "Today" and "Later this week". Empty: "No assessments this week."
- Birthdays: heading "Birthdays", with groups "Today" and "Later this week". Rows read "{name} · {class} · turns {age}". Without names: "{count} birthdays this week." Empty: "No birthdays this week."

**CSS:** `.erp-home-tabs` is a horizontal scrollable row of links on phones (16px gutter, no page side-scroll, 44px tap height). The current tab gets a teal underline using the existing teal token. `.erp-home-grid` is one column on phones and two columns from 992px. `.erp-home-list` rows reuse the compact tappable-row look of `.erp-attention-list` (PR #249).

- [ ] **Step 1: Write failing tests** (string pins and render checks)

```python
def test_today_cards_in_order(self): ...
    # index("School at a glance") < index("Attendance today") < index("Teacher compliance") < index("Assessments") < index("Birthdays")
def test_not_taken_row_shows_teacher_and_open_link(self): ...
def test_before_cutoff_shows_due_by_line(self): ...
    # patch timezone.now to 09:00 local -> "Registers are due by 10:00."
def test_tabs_css_is_pinned(self):
    css = Path("static/css/erp.css").read_text(encoding="utf-8")
    self.assertIn(".erp-home-tabs {", css)
    self.assertIn('.erp-home-tabs a[aria-current="page"]', css)
```

- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Write `_today.html` and the CSS.**
- [ ] **Step 4: Run** `python manage.py test core.tests.test_ui_admin_home_tabs core.tests.test_home_today --noinput` and `python manage.py test --pattern="test_ui*.py" --parallel 4 --noinput`. Expected: pass.
- [ ] **Step 5: Look at it.** Run `collectstatic --noinput`, restart the server and screenshot each tab at 360, 390 and 1280 wide (the stale-staticfiles rule). Check: no horizontal scroll, the tab bar fits or scrolls inside itself, and the donut and lists are readable.
- [ ] **Step 6: Commit** `feat(home): Today tab cards`

---

### Task 7: Full check, PR, review

- [ ] **Step 1:** `ruff check .` and `python manage.py test --parallel 4 --noinput` (a migration is in this PR). Expected: all pass. Report any flaky date test as known (see the parallel-date note) after re-running it serially.
- [ ] **Step 2:** Push, then open the PR "Admin home PR 1: four tabs, removals, Today tab", with the screenshots and a note that the "late" donut slice was left out under ADR 0007.
- [ ] **Step 3:** Start the PR reviewer subagent, verify what it finds, and report a verdict table. Fix only what the owner picks. Merge only on the owner's "merge #N".
