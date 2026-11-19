# Admin home PR 3: Academics tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the interim Academics tab (students needing attention and marks by subject) with the spec's six cards:
1. Results to finish, with Publish
2. Pass rate and grade spread per class
3. Best and worst 3 classes by marks
4. Subjects, with the change against last term
5. At-risk students
6. Top improvers

**Architecture:**
- A new module `core/home_academics.py` holds the tab's read-only aggregates and `academics_tab_context`, in the same way `core/home_today.py` holds the Today tab's. It replaces `analytics.academics_tab_context`.
- Two helpers that work per student or per term go in `core/marks_analytics.py`: `previous_term` and `student_average_changes`. `students_needing_attention` gets a `falling` input.
- `admin_overview` passes the permission flags.
- `templates/partials/home/_academics.html` is rewritten using only `erp-` classes.

**Tech Stack:** Django 5 server-rendered templates, PostgreSQL, `static/css/erp.css` (Everclass design system), Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-11-18-admin-home-tabs-design.md`. The sections that apply are "Tabs → Academics", "Merges", "My calls", "Data check" and "Anti-goals".

**Branch:**
- Work on `ui/admin-home-academics`, created from `origin/feature/admin-home` (worktree `.worktrees/admin-home-pr3`).
- The PR **targets `feature/admin-home`, never main.**
- Do not merge anything. The owner tests locally and gives the word.

## Global Constraints

**Cards and order**
- Phone order: 1 Results to finish · 2 Pass rate and grades by class · 3 Best and worst classes · 4 Subjects · 5 At-risk students · 6 Top improvers.
- **Results to finish** has three stages, each counted:
  - "Marking in progress"
  - "Ready to finalize"
  - "Finalized, not published": each section is listed with a **Publish** link to `core:term-publication` with `?section=<id>`.
- **Best and worst:** 3 each, ranked by average mark. Hidden when fewer than 4 classes have results. Each side shows `min(3, n // 2)` classes, so no class is on both sides. This is the same rule as on the Attendance tab.
- **Subjects:** the average, lowest first, with the change against the previous term in points. With no previous term, the card says "No comparison yet." (spec "Data check").

**Rules**
- **At-risk** (spec "My calls", merged from "needing attention"):
  - below pass in 2+ subjects, or
  - below pass in 1 subject and absent `ABSENTEE_THRESHOLD_DAYS` (3)+ days this month, or
  - average down `FALLING_POINTS` = **10** points or more since the previous term.
  - Order: by class, then name. Not ranked.
- **Improvers** (spec "My calls"):
  - the top `IMPROVER_LIMIT` = **5** students by the rise in their average against the previous term;
  - each needs at least `MIN_TERM_RESULTS` = **2** marked results in **each** term;
  - only a rise greater than 0 counts.

**Marks rules**
- Only FINALIZED assessments and MARKED results count (`marks_analytics._counted_results`).
- ABSENT is never a zero, and a score of exactly 0 is real.
- Percent is the score as a share of the assessment's own maximum.
- A pass is a score ≥ the pass mark: a tie passes (as `_is_below` is strict).
- A class with no pass mark on any result shows "No pass mark set", never 0%.

**Changes are in points**
- Shown as "Up 3 points", "Down 1.5 points" or "No change".
- Format the number as `f"{abs(round(change, 1)):g}"` (one decimal at most: "3", "1.5"), and use "point" when the shown number is "1". Do not use `percent_display` here, because it rounds 1.5 to "2".
- Up or down is said in words, never by colour alone.

**Layout and design system**
- No rings, gauges or new chart types. Use cards, `erp-home-row` lists and the existing horizontal bars (`partials/charts/_bars.html`).
- Every list folds after 5 rows with `partials/home/_fold_rows.html`.
- Every row links somewhere the viewer may open:
  - students → `core:student-detail`
  - classes → `core:class-grade-detail`, only with `core.view_classgrade` (`can["classes"]`); otherwise the name shows without a link
  - assessments → `core:assessment-detail` (`core.view_assessment`)
  - Publish → `core:term-publication` (`core.view_termpublication`, `can["publications"]`)
- Bootstrap-free. Inside `.erp-home` use only `erp-` classes:
  - Cards are `erp-card` + `erp-card--<name>`.
  - In-card empty text is `erp-card-empty`, and muted text is `erp-note-text`.
  - Grep `erp.css` before adding any class (`docs/DESIGN_SYSTEM.md` rule 3).
  - New names in this PR: `erp-card--results`, `--pass`, `--best`, `--improvers`, `erp-class-note`, `erp-stage-*`. All were checked as unused on 2026-11-19.
- Colours and spacing come from `--erp-*` tokens. No raw hex.

**Data access and queries**
- Gate 4B, checked in `admin_overview`:
  - Marks need `data_access.STUDENT_RESULT`.
  - Names need `data_access.STUDENT`.
  - At-risk also needs `data_access.ATTENDANCE_ENTRY` (absent days).
  - Results to finish needs `core.view_assessment`.
  - Nothing is queried for a card the viewer may not see.
- `core/tests/route_permissions.json` must not be edited.
- Only the active tab is built. The tab's query count must not grow with the number of classes, students or assessments.

**Tests**
- Run `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test <labels> --noinput`.
- After CSS edits, also run with `--pattern="test_ui*.py" --parallel 4`.
- Run `ruff check .` before each commit. Ruff 0.16.7 flags `zip()` without `strict=`.
- Do not run the full suite locally; CI does.

## Review Focus

1. **The start of a new term.** The running term may have drafts but no finalized marks yet:
   - "Results to finish" uses the running term (`work_term`).
   - The marks cards use the reporting term (the latest with finalized marks), and their titles name it, so old marks never read as this term's.
   - Tested in Tasks 1 and 4.
2. **No previous term with results** (a school's first term). Subjects says "No comparison yet." and no change is shown. Improvers says "No comparison yet." No student is flagged as falling. Tested in Tasks 2 and 3.
3. **A student who sat one test last term.** They are not an improver and are not "falling", because they need 2 marked results in each term. A student who left (not ACTIVE, or no ACTIVE enrollment) is never listed. Tested in Task 3.
4. **A draft with an empty roster, or a section where only some students have results.** An empty roster is "in progress", never "ready". Students who already have a current publication (PUBLISHED or STALE) are not counted as "not published". STALE is the existing "Results to publish" card's job, so it is not repeated here. Tested in Task 1.
5. **A viewer missing a permission.** Without `view_termpublication`: no Publish links or section rows, and counts only. Without `view_classgrade`: class names without links. Without `view_student`: no at-risk or improver card, and no name queries. Without `view_assessment`: no Results to finish card. Tested in Task 4.

---

## File Structure

- `core/home_academics.py` (new): `work_term`, `results_to_finish`, `class_marks`, `class_mark_extremes`, `subject_changes`, `change_words`, `top_improvers`, `academics_tab_context`, and constants.
- `core/marks_analytics.py`:
  - new `previous_term`, `MIN_TERM_RESULTS` and `student_average_changes`;
  - `students_needing_attention` gains `falling` and `falling_label`.
- `core/analytics.py`:
  - `split_extremes(rows)` taken out of `class_extremes`, which then uses it;
  - `academics_tab_context` and `_subject_rows` removed (move any callers).
- `core/views.py` `admin_overview`: the academics branch calls `home_academics.academics_tab_context`.
- `templates/partials/home/_academics.html`: rewritten with six cards.
- New row partials: `templates/partials/home/_finalize_row.html`, `_publish_row.html`, `_class_marks_row.html`, `_improver_row.html`.
- `templates/partials/charts/_bars.html`: optional `r.note`, shown under the bar as `erp-class-note`.
- `static/css/erp.css`: stage counts (`erp-stage-*`), `erp-class-note`, and the desktop spans.
- Tests:
  - `core/tests/test_home_academics.py` (new): data functions. Classes reuse `MarksFixture` from `core/tests/test_admin_overview_analytics.py`.
  - `core/tests/test_ui_admin_home_tabs.py`: rendering, gating, guard test, CSS pins.
  - `core/tests/test_admin_overview_analytics.py`: update the strings this PR renames.
- `docs/DESIGN_SYSTEM.md`: add "Stage counts" to the component table.

**Fixture facts for every task** (`MarksFixture`, `core/tests/test_admin_overview_analytics.py`):
- `TODAY` is Tue 2026-07-14.
- Terms:
  - `self.term_a` is "Term 1", 2026-06-01..06-30.
  - `self.term_b` is "Term 2", 2026-07-01..09-30.
- `self.s1` and `self.s2` are enrollments in `self.class_grade` (Grade 1) / `self.section`, from 2026-06-01.
- `self.assessment({enrollment: score}, name=, term=, class_grade=, section=, maximum="20", finalize=True, subject=, pass_mark=)`:
  - dates the assessment on the term's start;
  - a score of `None` is ABSENT;
  - `finalize=False` leaves it DRAFT;
  - it never sets `grading_snapshot`. Tests that need grades set it with `Assessment.objects.filter(pk=…).update(grading_snapshot={"scale": "S", "bands": [["80", "A"], ["50", "B"], ["0", "C"]]})`.
- `self.second_class()` returns `(grade, section, enrollment)` for "Grade 2".
- `self.enroll_student(name, grade, section)` adds a student.

---

### Task 1: Results to finish

**Files:**
- Create: `core/home_academics.py`, `core/tests/test_home_academics.py`

**Interfaces:**
- Produces:
  - `work_term(today: date) -> AcademicTerm | None`: the running term, else the latest started one. Order by `-start_date`, `-display_order` among terms with `start_date <= today`. This is the removed `analytics.ring_term`; see `git show cb03df4 -- core/analytics.py`.
  - `results_to_finish(today: date, *, publish_rows: bool) -> dict | None`. It returns None when `work_term` is None. Otherwise it returns:
    - `term`, `term_name`
    - `in_progress` (int)
    - `in_progress_url`: `core:academic-year-assessments` for the term's year, with `?term=<id>&status=DRAFT`
    - `ready`: a list of `{"name", "class_name", "section_name", "subject", "url"}`, oldest date first; `url` is `core:assessment-detail`
    - `unpublished_students` (int)
    - `unpublished_sections`: a list of `{"section_id", "class_name", "section_name", "students", "url"}` in class `display_order`, then section name; `url` is `core:term-publication` with `?section=<id>`. It is `[]` when `publish_rows` is False, and the counts are still filled.
- Rules:
  - Only DRAFT assessments of the term dated on or before `today` count.
  - "Ready" means the roster is non-empty and no roster enrollment lacks a result.
  - Every other counted draft is "in progress", including an empty roster.
  - "Not published" means an ACTIVE student with at least one FINALIZED result in the term and no TermPublication for the term in `CURRENT_STATUSES` (PUBLISHED, STALE). The student is grouped by the section of that result's `academic_enrollment` and counted once.
- Queries:
  - Use a constant number of queries.
  - For the roster checks, annotate with `Exists` subqueries over `AcademicEnrollment` (the pattern in `core/views.py` `_open_assessments_needing_marks`: the roster's year, grade and section come from `OuterRef`, and it is effective on `assessment_date`).
  - Do not call `Assessment.roster()` per assessment.

- [ ] **Step 1: Write the failing tests** in `class ResultsToFinishTests(MarksFixture, TestCase)`:

```python
def test_no_term_started_is_none(self):
    self.assertIsNone(home_academics.results_to_finish(datetime.date(2026, 5, 1), publish_rows=True))

def test_work_term_is_the_running_term_even_without_finalized_marks(self):
    self.assertEqual(home_academics.work_term(TODAY), self.term_b)

def test_fully_marked_draft_is_ready_and_partly_marked_is_in_progress(self):
    self.assessment({self.s1: 10, self.s2: 12}, name="All in", finalize=False)
    self.assessment({self.s1: 10}, name="Half", finalize=False)
    r = home_academics.results_to_finish(TODAY, publish_rows=True)
    self.assertEqual(r["in_progress"], 1)
    self.assertEqual([x["name"] for x in r["ready"]], ["All in"])
    self.assertTrue(r["ready"][0]["url"].startswith("/"))

def test_empty_roster_is_in_progress_not_ready(self):
    grade, section, enrollment = self.second_class()
    # end or remove `enrollment` so that the Grade 2 roster on 2026-07-01 is empty
    self.assessment({}, class_grade=grade, section=section, finalize=False)
    r = home_academics.results_to_finish(TODAY, publish_rows=True)
    self.assertEqual((r["in_progress"], r["ready"]), (1, []))

def test_future_drafts_and_finalized_assessments_are_not_counted(self): ...
    # a DRAFT dated 2026-08-01 and a finalized one: in_progress 0, ready []

def test_finalized_results_without_publication_are_unpublished_by_section(self):
    self.assessment({self.s1: 10, self.s2: None})  # ABSENT still has a finalized result
    r = home_academics.results_to_finish(TODAY, publish_rows=True)
    self.assertEqual(r["unpublished_students"], 2)
    row = r["unpublished_sections"][0]
    self.assertEqual((row["class_name"], row["students"]), ("Grade 1", 2))
    self.assertIn(f"?section={self.section.pk}", row["url"])

def test_published_and_stale_students_are_not_unpublished(self):
    # TermPublication for s1 PUBLISHED and s2 STALE in term_b (fields as in
    # core/tests/test_phase6_publication.py:234) -> unpublished_students == 0, sections == []

def test_publish_rows_false_keeps_counts_but_no_rows(self):
    self.assessment({self.s1: 10})
    r = home_academics.results_to_finish(TODAY, publish_rows=False)
    self.assertEqual((r["unpublished_students"], r["unpublished_sections"]), (1, []))

def test_query_count_does_not_grow_with_assessments(self):
    # measure with CaptureQueriesContext after 1 draft, then after 4 more drafts in a second
    # class; the two counts are equal
```

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_academics --noinput`
Expected: ImportError / AttributeError on `home_academics`.

- [ ] **Step 3: Implement** `work_term` and `results_to_finish` to the Interfaces above. The module docstring states the marks rules from Global Constraints. `home_academics` may import `analytics` and `marks_analytics`. Neither of them may import `home_academics`.

- [ ] **Step 4: Run the tests and see them pass** (same command). Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add core/home_academics.py core/tests/test_home_academics.py
git commit -m "feat(overview): results to finish for the Academics tab"
```

---

### Task 2: Classes by marks and subjects with change

**Files:**
- Modify: `core/marks_analytics.py`, `core/analytics.py`, `core/home_academics.py`
- Test: `core/tests/test_home_academics.py`, plus `core/tests/test_home_attendance.py` (`ClassExtremesTests` must still pass unchanged)

**Interfaces:**
- Consumes: Task 1's module.
- Produces:
  - `marks_analytics.previous_term(term: AcademicTerm) -> AcademicTerm | None`: the latest term with `start_date < term.start_date` that has counted results (`Exists(_counted_results(...))`). It is loaded with `select_related("academic_year")`, so `term_label` works.
  - `analytics.split_extremes(rows: list) -> tuple[list, list] | None`. It takes rows sorted lowest first and returns None under 4 rows. Otherwise it returns `(best highest first, worst lowest first)` with `k = min(3, len(rows) // 2)`. `class_extremes` calls it and its own behaviour does not change.
  - `home_academics.class_marks(term) -> list[dict]` in class `display_order`, then name. Each row has:
    - `class_grade_id`, `class_name`
    - `average` (float, 1 dp)
    - `pass_rate` (float 1 dp, or None when no counted result has a pass mark)
    - `grades`: a list of `{"label", "count"}`, highest band first, only labels with a count > 0
    - `grades_display`, e.g. `"A 2 · B 1"`, or `""`
  - Grades:
    - Each MARKED result is graded with `models.grade_from_bands(assessment.grading_snapshot["bands"], percent)`.
    - A result on an assessment without a snapshot is not graded.
    - Band order is the order of the bands' minimums, highest first, merged across the class's snapshots.
  - Queries: two at most (the results with percent, class and assessment id, and the snapshots by assessment id). The grading loop runs in Python.
  - `home_academics.class_mark_extremes(rows, *, with_links) -> dict | None`:
    - It sorts `rows` by `(average, class_name)` and calls `split_extremes`.
    - It returns `{"best": [...], "worst": [...]}` of `_bars.html` rows: `label` (class name), `value` (average), `display` (`f"{percent_display(average)}%"`), `low` False, `url` (class-grade-detail, or None).
  - `home_academics.subject_changes(term, previous) -> list[dict]`: `_bars.html` rows, lowest average first (ties by name). Each row has `label`, `value`, `display`, `low` False, `change` (float 1 dp, or None), `note`.
    - Without a previous term, or for a subject not in the previous term: `change` None and `note` "".
    - Otherwise `note` is `change_words(change)`.
  - `home_academics.change_words(change: float) -> str`: "Up 3 points", "Down 1.5 points", "Up 1 point", or "No change" (for 0.0).
- Refactor: delete `analytics._subject_rows`. Its tests in `test_admin_overview_analytics.SubjectAveragesTests.subject_display` change to `home_academics.subject_changes(term, None)`.

- [ ] **Step 1: Write the failing tests** (`ClassMarksTests`, `SubjectChangeTests`, `ChangeWordsTests` in `test_home_academics.py`):

```python
def test_previous_term_is_the_last_earlier_term_with_finalized_results(self):
    self.assertIsNone(marks_analytics.previous_term(self.term_b))
    self.assessment({self.s1: 10}, term=self.term_a, name="Draft only", finalize=False)
    self.assertIsNone(marks_analytics.previous_term(self.term_b))
    self.assessment({self.s1: 10}, term=self.term_a)
    self.assertEqual(marks_analytics.previous_term(self.term_b), self.term_a)

def test_pass_rate_counts_ties_as_passes_and_ignores_absent(self):
    self.assessment({self.s1: 10, self.s2: 9}, pass_mark=10)  # 1 of 2 pass
    self.assessment({self.s1: None}, name="Absent", pass_mark=10)  # not judged
    row = home_academics.class_marks(self.term_b)[0]
    self.assertEqual((row["class_name"], row["pass_rate"]), ("Grade 1", 50.0))

def test_no_pass_mark_is_none_not_zero(self):
    self.assessment({self.s1: 10})
    self.assertIsNone(home_academics.class_marks(self.term_b)[0]["pass_rate"])

def test_grade_spread_uses_the_frozen_snapshot(self):
    a = self.assessment({self.s1: 18, self.s2: 11})  # 90% A, 55% B
    Assessment.objects.filter(pk=a.pk).update(
        grading_snapshot={"scale": "S", "bands": [["80", "A"], ["50", "B"], ["0", "C"]]})
    row = home_academics.class_marks(self.term_b)[0]
    self.assertEqual(row["grades"], [{"label": "A", "count": 1}, {"label": "B", "count": 1}])
    self.assertEqual(row["grades_display"], "A 1 · B 1")

def test_extremes_hidden_under_four_classes_and_split_without_overlap(self):
    # 3 classes -> None; 5 classes (averages differ) -> 2 best, 2 worst, disjoint, best highest first

def test_subjects_change_against_previous_term(self):
    self.assessment({self.s1: 10}, term=self.term_a)          # 50%
    self.assessment({self.s1: 16})                            # 80%
    row = home_academics.subject_changes(self.term_b, self.term_a)[0]
    self.assertEqual((row["display"], row["change"], row["note"]), ("80%", 30.0, "Up 30 points"))

def test_subject_new_this_term_has_no_change(self):  # Science only in term_b -> change None, note ""

def test_change_words(self):
    self.assertEqual(home_academics.change_words(3.0), "Up 3 points")
    self.assertEqual(home_academics.change_words(-1.5), "Down 1.5 points")
    self.assertEqual(home_academics.change_words(1.0), "Up 1 point")
    self.assertEqual(home_academics.change_words(0.0), "No change")
```

Note: `percent_display` rounds to whole numbers, so `-1.5` displays as "2". The "Down 1.5 points" case therefore needs one-decimal formatting for changes. Format the number as `f"{abs(change):g}"` after `round(change, 1)`. This replaces the `percent_display` note in Global Constraints for change words only.

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_academics core.tests.test_home_attendance core.tests.test_admin_overview_analytics --noinput`
Expected: the new tests fail with AttributeError.

- [ ] **Step 3: Implement** the Interfaces above. Use `marks_analytics.marked_results(term)` for the percent and the subject names. Get the class from `assessment__offering__class_grade`, and the pass percent from `_PASS_PERCENT`.

- [ ] **Step 4: Run the tests and see them pass** (same command). Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add core/marks_analytics.py core/analytics.py core/home_academics.py core/tests/
git commit -m "feat(overview): class pass rates, grade spread, mark extremes and subject change"
```

---

### Task 3: At-risk students (with falling marks) and top improvers

**Files:**
- Modify: `core/marks_analytics.py`, `core/home_academics.py`
- Test: `core/tests/test_home_academics.py`; the existing attention tests in `core/tests/test_admin_overview_analytics.py` must still pass

**Interfaces:**
- Consumes: `previous_term` and `change_words` (Task 2).
- Produces:
  - `marks_analytics.MIN_TERM_RESULTS = 2`.
  - `marks_analytics.student_average_changes(term, previous, min_results=MIN_TERM_RESULTS) -> dict[int, dict]`:
    - Keyed by student id. Each value is `{"this": float, "last": float, "change": float}`; `this` and `last` are each term's average percent over MARKED results (1 dp), and `change = round(this - last, 1)`.
    - Only students with ≥ `min_results` marked results in **both** terms.
    - It returns `{}` when `previous` is None.
    - Two grouped queries.
  - `students_needing_attention(..., falling=None, falling_label=None)`:
    - `falling` is `{student_id: change}` (changes ≤ −10). A student in `falling` is flagged even with no below-pass subject.
    - Reason parts are joined with "; ":
      - the existing below-pass part, only when there are below-pass subjects;
      - the existing absent part, only when it already applies (below-pass students only);
      - `f"average down {n} points since {falling_label}"`, with `n` formatted as in `change_words`. Capitalise the first letter when this part comes first. Use "point" when `n` is "1".
    - The defaults keep today's behaviour exactly.
    - `marks_analytics` must not import `home_academics`, so put the number formatting in `marks_analytics` (or `charts`). `home_academics.change_words` reuses it.
  - `home_academics.FALLING_POINTS = 10`, `home_academics.IMPROVER_LIMIT = 5`.
  - `home_academics.top_improvers(changes: dict, limit=IMPROVER_LIMIT) -> list[dict]`:
    - Students with `change > 0`, sorted by change (largest first), then name.
    - Only ACTIVE students with an ACTIVE enrollment, whose class is the one shown.
    - Rows: `{"student_id", "name", "class_name", "change", "display"}`. `display` is e.g. `"Up 12 points (61% → 73%)"`: `change_words` plus the two `percent_display` values.
    - One query for names and classes.

- [ ] **Step 1: Write the failing tests** (`AverageChangeTests`, `AtRiskTests`, `ImproverTests`):

```python
def two_terms(self, a_scores, b_scores):
    """Two assessments per term per student: `{enrollment: (score, score)}` out of 20."""
    for term, scores in ((self.term_a, a_scores), (self.term_b, b_scores)):
        for i in range(2):
            self.assessment({e: s[i] for e, s in scores.items()}, term=term, name=f"T{i}")

def test_change_needs_two_marked_results_in_each_term(self):
    self.two_terms({self.s1: (10, 10), self.s2: (10, 10)}, {self.s1: (16, 16), self.s2: (16, None)})
    changes = marks_analytics.student_average_changes(self.term_b, self.term_a)
    self.assertEqual(changes[self.s1.student_id], {"this": 80.0, "last": 50.0, "change": 30.0})
    self.assertNotIn(self.s2.student_id, changes)  # one marked result in term_b

def test_no_previous_term_gives_no_changes(self):
    self.assertEqual(marks_analytics.student_average_changes(self.term_b, None), {})

def test_falling_student_is_at_risk_without_any_below_pass_subject(self):
    self.assessment({self.s1: 15})  # term_b has results, no pass mark
    result = marks_analytics.students_needing_attention(
        self.term_b, {}, falling={self.s1.student_id: -12.0}, falling_label="Term 1",
        period_label="this month")
    self.assertEqual(result["rows"][0]["reason"], "Average down 12 points since Term 1")

def test_falling_is_added_to_a_below_pass_reason(self):
    # s1 below pass in Mathematics and Science AND falling -12 ->
    # reason == "Below pass in Mathematics and Science (Term 2); average down 12 points since Term 1"

def test_defaults_are_unchanged(self): ...  # an existing attention case gives the same rows as before

def test_top_improvers_largest_rise_first_and_only_rises(self):
    changes = {self.s1.student_id: {"this": 73.0, "last": 61.0, "change": 12.0},
               self.s2.student_id: {"this": 50.0, "last": 55.0, "change": -5.0}}
    rows = home_academics.top_improvers(changes)
    self.assertEqual([r["student_id"] for r in rows], [self.s1.student_id])
    self.assertEqual(rows[0]["display"], "Up 12 points (61% → 73%)")
    self.assertEqual(rows[0]["class_name"], "Grade 1")

def test_improvers_are_capped_at_five_and_skip_inactive_students(self): ...
```

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_home_academics core.tests.test_admin_overview_analytics --noinput`
Expected: the new tests fail; the old ones pass.

- [ ] **Step 3: Implement** the Interfaces above. In `students_needing_attention`, build `flagged` as the union of the below-pass rule and `falling`. Keep the one-enrollment query and the class/name ordering.

- [ ] **Step 4: Run the tests and see them pass** (same command). Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add core/marks_analytics.py core/home_academics.py core/tests/
git commit -m "feat(overview): falling marks join at-risk; top improvers"
```

---

### Task 4: Tab context, view, template, CSS and page tests

**Files:**
- Modify:
  - `core/home_academics.py` (add `academics_tab_context`)
  - `core/analytics.py` (remove `academics_tab_context`)
  - `core/views.py` (`admin_overview`, academics branch)
  - `templates/partials/home/_academics.html`
  - `templates/partials/charts/_bars.html`
  - `static/css/erp.css`
  - `docs/DESIGN_SYSTEM.md`
- Create: `templates/partials/home/_finalize_row.html`, `_publish_row.html`, `_class_marks_row.html`, `_improver_row.html`
- Test: `core/tests/test_ui_admin_home_tabs.py`, `core/tests/test_admin_overview_analytics.py` (update renamed strings and CSS pins)

**Interfaces:**
- Produces: `home_academics.academics_tab_context(today, *, include_progress, publish_rows, include_marks, include_attention, include_improvers, class_links) -> dict`, with these keys:
  - `progress`: `results_to_finish(...)` when `include_progress`, else None.
  - `term`, `term_label`: the reporting term and its label, only queried when `include_marks or include_attention or include_improvers`.
  - `previous`, `previous_label`: `previous_term(term)` and `term_label(previous, today)`, or None.
  - `show_marks`: `include_marks`.
  - `classes`: `class_marks(term)`, or `[]`.
  - `extremes`: `class_mark_extremes(classes, with_links=class_links)`, or None.
  - `subjects`: `subject_changes(term, previous)`, or `[]`.
  - `attention`: `students_needing_attention(term, absent_days, …, falling={id: c["change"] for … if c["change"] <= -FALLING_POINTS}, falling_label=previous_label)` when `include_attention`, else None. Absent days are this month's, as now.
  - `improvers`: `top_improvers(changes)` when `include_improvers`, else None.
  - `class_links`.
  - `changes` is computed once and only when needed.
- View flags:
  - `include_progress = user.has_perm("core.view_assessment")`
  - `publish_rows = can["publications"]`
  - `include_marks = can_see_results`
  - `include_attention = can_see_students and can_see_results and can_see_attendance` (unchanged)
  - `include_improvers = can_see_students and can_see_results`
  - `class_links = can["classes"]`

**Template** (`<section class="erp-analytics …">`, cards in Global Constraints order):

| Card | Class | Title / content | Empty or hidden |
|---|---|---|---|
| 1 | `erp-card erp-card--results` | "Results to finish, {term_name}". Three stage counts in `<ul class="erp-stage-list">`: each is an `li.erp-stage` with `span.erp-stage-count` and `span.erp-stage-label`. The labels are "Marking in progress" (count links to `in_progress_url`), "Ready to finalize" and "Finalized, not published". Then `<h4 class="erp-home-sub">Ready to finalize</h4>` + fold of `_finalize_row.html` (noun "assessments"), and `<h4 class="erp-home-sub">To publish</h4>` + fold of `_publish_row.html` (noun "sections"); each sub-list appears only when it has rows. | Hidden when `progress` is None. When all three counts are 0: `erp-card-empty` "Nothing to finish for {term_name}." |
| 2 | `erp-card erp-card--pass` | "Pass rate and grades by class, {term_label}". Fold of `_class_marks_row.html` (noun "classes"): main = class name; meta = "Pass rate 85%" or "No pass mark set", then " · {grades_display}" only when it is non-empty; "Open" link only when `class_links`. | Hidden when not `show_marks`. No term: "No finalized results yet." |
| 3 | `erp-card erp-card--best` | "Best and worst classes", sub "Average mark, {term_label}.", "Highest" / "Lowest" headings + `_bars.html` with `colour="marks"`. | Omitted when `extremes` is None. |
| 4 | `erp-card erp-card--subjects` | "Subjects, {term_label}", sub "Average mark, lowest first. Change since {previous_label}." or "Average mark, lowest first. No comparison yet." + `_bars.html` with `colour="marks"` (bars show `r.note`). | Hidden when not `show_marks`. No term: "No finalized results yet." |
| 5 | `erp-card erp-card--attention` | "At-risk students", sub "Below pass in two or more subjects, or in one subject and often absent, or average down 10+ points since last term. In class order, not ranked." Same rows and empty states as today (`_attention_row.html`, fold). | Omitted when `attention` is None. |
| 6 | `erp-card erp-card--improvers` | "Top improvers", sub "Biggest rise in average mark since {previous_label}." Fold of `_improver_row.html`: name · class; meta = `display`; "Open" to student-detail. | Omitted when `improvers` is None. No previous term: "No comparison yet." Empty list: "No student's average has risen yet." |

- Section modifiers: `erp-analytics--no-best` when `extremes` is None, `--no-attention` when `attention` is None, `--no-improvers` when `improvers` is None.
- `_publish_row.html`: main = "{class_name} {section_name}"; meta = "{n} student(s)" (use `pluralize`); link text **"Publish"** to `url`.
- `_finalize_row.html`: main = name · subject; meta = "{class_name} {section_name}"; link "Open".
- `_bars.html` addition: `{% if r.note %}<span class="erp-class-note">{{ r.note }}</span>{% endif %}` after `.erp-class-pct`. Update the partial's header comment.

**CSS:**
- Phone: single column (existing).
- `.erp-stage-list`: a 3-column grid of equal stage tiles at all widths. The count uses `--erp-text-title`; the label uses `--erp-text-sm` and `--erp-ink-soft`. The count link is at least 44px tall.
- `.erp-class-note`: `--erp-text-xs`, `--erp-ink-soft`, on its own line under the bar (`grid-column: 1 / -1` or `flex-basis: 100%`, whichever `.erp-class-row` layout needs).
- Desktop (inside the existing `@media` block that holds the attendance spans):
  - `.erp-home .erp-analytics > .erp-card--results { grid-column: span 12; }`
  - `--pass` 7, `--best` 5, `--subjects` 12, `--attention` 7 `align-self: start`, `--improvers` 5 `align-self: start`
  - `.erp-home .erp-analytics--no-best > .erp-card--pass { grid-column: span 12; }`
  - `.erp-home .erp-analytics--no-attention > .erp-card--improvers { grid-column: span 12; }`
  - `.erp-home .erp-analytics--no-improvers > .erp-card--attention { grid-column: span 12; }`
  - Replace the old `.erp-analytics > .erp-card--attention { grid-column: span 12; … }` and `.erp-analytics > .erp-card--subjects { grid-column: span 7; }` rules, and update their pins in `test_admin_overview_analytics.py`.

**DESIGN_SYSTEM.md:** add the row "Stage counts | `erp-stage-list`, `erp-stage`, `erp-stage-count`, `erp-stage-label` | none | Ready (Academics)".

- [ ] **Step 1: Write the failing page tests** in `test_ui_admin_home_tabs.py`. Use a `MarksFixture`-based class for the data, `url = reverse("core:admin-overview") + "?tab=academics"`, and the existing clients (`self.administrator`, plus the reduced-permission users already used by the Attendance tests).
  - `test_academics_cards_in_spec_order`: with data for every card, the `html.index` of `erp-card--results`, `--pass`, `--best`, `--subjects`, `--attention`, `--improvers` are increasing. Give the data four classes, finalized marks in both terms, and one ready draft.
  - `test_ready_draft_is_listed_with_open_link` and `test_unpublished_section_has_publish_link`: assert `"Publish"` and `reverse("core:term-publication", args=[term_b.pk]) + f"?section={section.pk}"` are in the HTML.
  - `test_without_publication_permission_no_publish_rows`: the counts still show and `"Publish"` does not.
  - `test_without_assessment_permission_no_results_card`.
  - `test_without_student_permission_no_names_and_no_name_cards`: no `erp-card--attention` and no `erp-card--improvers`, and the student names are absent.
  - `test_class_rows_link_only_with_classgrade_permission`.
  - `test_first_term_says_no_comparison_yet`: results only in term_b. Both the subjects sub and the improvers card contain "No comparison yet".
  - `test_marks_cards_name_the_reporting_term`: drafts in term_b, finalized only in term_a. Card 1 says "Term 2"; cards 2 and 4 say "Term 1".
  - `test_academics_query_count_does_not_grow`: equal counts with 4 classes and with 6.
  - Guard test: extend `test_overview_uses_no_bootstrap_classes` (or its tab loop) so the academics tab with full data is checked.
  - CSS pins: the exact desktop span lines above, plus `.erp-class-note`.
  - Update renamed strings in `test_admin_overview_analytics.py`: "Marks by subject" becomes "Subjects", and "Students needing attention" becomes "At-risk students". Change only the assertion text, not what is tested.

- [ ] **Step 2: Run them to see them fail**

Run: `DJANGO_DEBUG=True ../../.venv/Scripts/python.exe manage.py test core.tests.test_ui_admin_home_tabs core.tests.test_admin_overview_analytics core.tests.test_home_academics --noinput`
Expected: the new tests fail.

- [ ] **Step 3: Implement** the context, the view flags, the template table, the row partials, the `_bars.html` note, the CSS and the DESIGN_SYSTEM row. Remove `analytics.academics_tab_context`, and grep that nothing else calls it.

- [ ] **Step 4: Run the tests and see them pass**

Run the Step 2 command, then `... manage.py test --pattern="test_ui*.py" --parallel 4 --noinput`, then `ruff check .`
Expected: all OK, no ruff findings.

- [ ] **Step 5: Check in the browser** at 360px and 1280px, signed in as demo_admin (`/accounts/login/`; credentials are in the local CSV):
  - Restart `runserver` first, because the template loader is cached, and open `/static/css/erp.css` directly to refresh it.
  - Save any screenshots under `.playwright-mcp/`.
  - Check:
    - no horizontal scroll at 360px;
    - the stage tiles fit three across at 360px;
    - tap targets are at least 44px;
    - the six cards are in spec order;
    - the desktop grid has no holes;
    - every row has a working link.
  - Stop the server afterwards (this PC is low on memory).

- [ ] **Step 6: Commit**

```bash
git add core/ templates/ static/css/erp.css docs/DESIGN_SYSTEM.md
git commit -m "ui(overview): Academics tab with six cards"
```

---

## Rulings made while planning (the owner can override)

- **"Latest exam" means the reporting term.** Assessments are per subject and per section, and there is no exam object grouping them. Pass rate and grade spread use every finalized result in the reporting term, which is the same term the other marks cards use.
- **"Results to finish" uses the running term, and the marks cards use the reporting term.** At the start of a term, drafts exist before any marks are finalized.
- **"Finalized, not published" leaves out STALE publications.** The existing "Results to publish" card already covers them, and nothing should repeat.
- **"Ready to finalize" checks only that the roster is fully marked.** Any other blocker (a score over the maximum, an incomplete grading scale) is explained on the assessment page when Finalize is pressed.
- **The falling-marks threshold is 10 points.** The spec says "falling marks vs last term" without a number.
