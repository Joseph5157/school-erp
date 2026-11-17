# Teacher Timetable, Step 2: class picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the teacher Timetable page, a chip opens a bottom sheet to pick "My timetable", one of "My classes", or any class; a picked class shows that class's Day and Week timetable with subject and teacher, read-only.

**Architecture:** Same route `core:my-timetable`, new `?section=<pk>` (plus the no-JS `?pick=1`). New pure builders in `core/timetable.py` produce class rows/weeks in the same shapes as the teacher ones; the week assembly is shared with `teacher_week`. The sheet is a native `<dialog>` opened by a small `erp.js` block; without JS the chip is a link to `?pick=1`, which renders the same list in the page.

**Tech Stack:** Django templates, `erp.css` tokens, vanilla JS in `static/js/erp.js`, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-11-17-teacher-timetable-class-picker-design.md`

## Global Constraints

- Audience: `teacher_required` (unchanged). Any teacher may view any Section, read-only; the view writes nothing.
- `section` param: an existing Section id shows that class (even with nothing scheduled); missing, malformed or unknown ids show "My timetable". Never 404/500.
- Teacher of a slot on a date = holder of the `AssessmentTeacherAssignment` (offering + Section) effective that date, regardless of account state (ADR 0018 D9). Shown via the existing `_teacher_name(user)` (full name or username). None -> "No teacher assigned".
- School-day rules for a class = the teacher view's rules applied to that Section's slots (years with the Section's slots effective that day; `is_instructional_day`; Saturday hidden when not a school day; "Holiday"/"No school"; Sunday opens the coming week via `week_monday`).
- Short subject label: `name.strip()[:3]` ("Mathematics" -> "Mat", "English" -> "Eng", "Hindi" -> "Hin").
- Copy: chip "My timetable" or `str(section)`; sheet title "Choose a timetable"; group headings "My timetable", "My classes", "All classes"; search label "Search classes"; no-teacher text "No teacher assigned"; Week key entries "<short> <full subject>"; hint "Tap a class to open that day." unchanged for both modes.
- Week box aria-label for a class: "<Subject>, <teacher or 'No teacher assigned'>, period <n>, <l j F>" (e.g. "Mathematics, Mrs Rao, period 3, Monday 16 November").
- Sheet lists: Day view uses the selected date; Week view uses every day of the displayed week. "My classes" = class-teacher Sections first, then subject Sections, de-duplicated, each group in (grade display_order, section name) order. "All classes" = Sections with slots effective on those dates, grouped by Class/Grade in display order.
- Every link (toggle, arrows, date strip chips, "Today", week boxes) keeps `section` when a class is shown; "My timetable" links drop it.
- ADR 0021 D10/D11 amendment for the read-only class view and its audience; no clock times, free periods or placeholders.
- Phone: 360/390 px, no page scroll, chip and sheet rows >= 44 px. New CSS block next to the `.erp-tt-*` blocks (before the `/* UI-D1-4B` marker); do not edit old CSS text; no `overflow-wrap: anywhere`.
- Tests: `DJANGO_DEBUG=True python manage.py test <modules> --noinput`, one process at a time; `--pattern="test_ui*.py" --parallel 4` after CSS edits; no full local suite (CI runs it).

## Review Focus

1. Two Sections of different Academic Years open on the same date (year rollover overlap): a class's day uses only years where *that Section* has slots; sheet lists both without duplicates. Test in Task 1 (`test_class_day_ignores_other_years_slots`).
2. A teacher handed over mid-week: class Week shows the old teacher's name before the hand-over and the new one after. Test in Task 1 (`test_class_week_teacher_changes_mid_week`).
3. `?section=` with garbage ("abc", "-1", "99999999", "1.5"): page loads as My timetable, 200. Test in Task 3 (`test_bad_section_values_fall_back_to_mine`).
4. A class picked and then the date strip / arrows / toggle used: `section` stays in every link. Test in Task 3 (`test_class_links_keep_section`).
5. Query count stays bounded for a full class week (no per-cell or per-teacher queries). Test in Task 1 (`test_class_week_query_count_does_not_grow_with_rows`).

## File Structure

- Modify `core/timetable.py`: `short_subject_label`, `class_timetable_on`, `class_week`, `timetable_picker`; extract shared week assembly from `teacher_week`.
- Modify `core/views.py` (`my_timetable`): read `section` / `pick`; class context.
- Modify `core/templates/core/my_timetable.html`: chip, `<dialog>` sheet, no-JS picker list, class Day cards, class Week boxes and key.
- Modify `static/css/erp.css`: new `.erp-tt-pick*` / `.erp-tt-sheet*` block.
- Modify `static/js/erp.js`: open/close the sheet, filter on search.
- Modify `docs/adr/0021-timetable-periods-and-weekly-slots.md`: amendment.
- Tests: `core/tests/test_teacher_timetable_class.py` (new; reuse `TimetableDashboardFixture` from `core.tests.test_ui_teacher_timetable`).

---

### Task 1: Class rows and class week

**Files:** Modify `core/timetable.py`; Create `core/tests/test_teacher_timetable_class.py`.

**Interfaces:**
- Produces:
  - `short_subject_label(name: str) -> str`.
  - `class_timetable_on(section, on_date, year_is_instructional) -> list[dict] | None` — `year_is_instructional(year) -> bool` as in `teacher_timetable_on`; None when no Academic Year holding this Section's effective slots is instructional that day; rows ordered by period sequence, each `{"period", "sequence", "section", "subject", "teacher": User | None, "teacher_name": str, "short": short_subject_label(subject)}` where `teacher_name` is `_teacher_name(teacher)` or "No teacher assigned".
  - `class_week(section, any_date, today, year_is_instructional) -> dict` — same keys as `teacher_week` (`monday, days, grid, key, is_empty, heading, contains_today`); `year_is_instructional(year, day)`; `key` = distinct subjects `{"short", "full"}` sorted by full name.
  - `teacher_week` unchanged in output; both use a private week-assembly helper (name is the implementer's) so day/label/Saturday/heading logic exists once.
- Consumes: `week_monday`, `_week_heading`, `_teacher_name`, `TimetableSlot.objects.effective_on`, `AssessmentTeacherAssignment.objects.effective_on`.

- [ ] **Step 1: Write failing tests** in `ClassTimetableTests(TimetableDashboardFixture, TestCase)`:
  - `test_short_subject_label`: "Mathematics"->"Mat", "English"->"Eng", "Hindi"->"Hin", "  Art "->"Art", "PE"->"PE".
  - `test_class_day_lists_every_period_with_subject_and_teacher`: rao assigned maths 6-A, iyer assigned science 6-A; slots P1 maths, P2 science on Monday -> rows `[("P1","Mathematics", rao), ("P2","Science", iyer)]`, `teacher_name` values are `_teacher_name` of each.
  - `test_class_day_shows_slots_without_a_teacher`: slot with no assignment -> one row, `teacher is None`, `teacher_name == "No teacher assigned"`.
  - `test_class_day_none_on_non_school_day`: SUNDAY -> None; a `SchoolCalendarDay(is_instructional=False)` Monday -> None.
  - `test_class_day_ignores_other_years_slots` (Review Focus 1): a second AcademicYear overlapping MONDAY with a 6-B slot only; 6-A's day rows contain only 6-A's year's slots, and a 6-A day where only the other year is instructional returns None.
  - `test_class_week_teacher_changes_mid_week` (Review Focus 2): `assign_between(rao, maths, six_a, 2026-06-01, 2026-10-13)`, `assign_between(iyer, maths, six_a, 2026-10-14)`, Mon–Fri P1 slots -> Mon/Tue teacher rao, Wed–Fri iyer.
  - `test_class_week_key_and_short_labels`: maths + science slots -> key `[{"short":"Mat","full":"Mathematics"},{"short":"Sci","full":"Science"}]`; box rows carry `short`.
  - `test_class_week_query_count_does_not_grow_with_rows` (Review Focus 5): 1 slot vs 10 slots (2 periods x 5 days, two teachers) -> equal `CaptureQueriesContext` lengths.
- [ ] **Step 2:** Run `DJANGO_DEBUG=True python manage.py test core.tests.test_teacher_timetable_class --noinput`. Expected: ImportError / failures.
- [ ] **Step 3: Implement** the three public functions and the shared week helper. Teacher lookup: one `AssessmentTeacherAssignment` query per day for the day's (offering, section) pairs, `select_related("teacher")`, effective on that day.
- [ ] **Step 4:** Run `core.tests.test_teacher_timetable_class core.tests.test_teacher_timetable_page`. Expected: OK (the existing page module proves `teacher_week` is unchanged).
- [ ] **Step 5: Commit** `feat: class timetable rows and week builder`.

### Task 2: Sheet lists

**Files:** Modify `core/timetable.py`; tests in `core/tests/test_teacher_timetable_class.py`.

**Interfaces:**
- Produces: `timetable_picker(user, dates) -> dict` with `{"mine": list[Section], "grades": list[{"grade": ClassGrade, "sections": list[Section]}]}`. `dates` = list of dates (one for Day, the shown week's days for Week). Sections `select_related("class_grade")`.
- Consumes: `class_teacher_assignments(user, on_date)` and `current_teacher_assignments(user, on_date)` from `core.authorization`.

- [ ] **Step 1: Write failing tests** `PickerTests`:
  - `test_mine_lists_class_teacher_section_first_then_subject_sections_once`: rao class teacher of 6-B, assigned maths 6-A and sanskrit 6-B -> `mine == [six_b, six_a]`.
  - `test_all_classes_grouped_by_grade_in_display_order`: slots in 6-A, 6-B and a Grade 7 section -> grades `[Grade 6: [6-A, 6-B], Grade 7: [7-A]]` (respecting `display_order`).
  - `test_week_dates_include_sections_active_any_day`: a 6-B slot starting Wednesday; `dates` = Mon only -> 6-B absent; `dates` = Mon–Sat -> present.
  - `test_sections_without_slots_are_not_listed`.
- [ ] **Step 2:** Run the module. Expected: failures for the new tests.
- [ ] **Step 3: Implement** `timetable_picker` (a fixed number of queries per date, at most).
- [ ] **Step 4:** Run the module. Expected: OK.
- [ ] **Step 5: Commit** `feat: timetable class picker lists`.

### Task 3: Page, sheet, ADR

**Files:** Modify `core/views.py`, `core/templates/core/my_timetable.html`, `static/css/erp.css`, `static/js/erp.js`, `docs/adr/0021-timetable-periods-and-weekly-slots.md`; tests in `core/tests/test_teacher_timetable_class.py`.

**Interfaces:**
- Consumes: Task 1 and Task 2 functions; existing `teacher_week`, `teacher_timetable_on`, `date_strip`, `parse_timetable_date`, `week_monday`.
- Produces: context keys `section` (Section | None), `picker` (from `timetable_picker`), `pick` (bool); for a class, Day `rows` come from `class_timetable_on`, Week `week` from `class_week`.

- [ ] **Step 1: Write failing tests** `ClassPageTests` (business date MONDAY):
  - `test_chip_says_my_timetable_and_class_name`: no `section` -> chip text "My timetable"; `?section=<6-A>` -> "Grade 6 - A".
  - `test_class_day_cards_show_subject_and_teacher`: 6-A with maths (rao) P1, science (no teacher) P2 -> page contains "Mathematics", rao's name, "Science", "No teacher assigned"; another teacher (iyer) viewing it gets the same (any teacher may view).
  - `test_class_week_boxes_and_key`: `?view=week&section=<6-A>` -> box `<a href="…?date=2026-10-12&amp;section=<pk>" aria-label="Mathematics, <rao name>, period 1, Monday 12 October">Mat</a>`; key contains "Mat" and "Mathematics".
  - `test_class_links_keep_section` (Review Focus 4): Day page with section -> every `erp-tt-chip` href, the toggle's Week href and the "Today" link contain `section=<pk>`; Week page -> both arrow hrefs and the Day toggle contain it; the sheet's "My timetable" link does not.
  - `test_bad_section_values_fall_back_to_mine` (Review Focus 3): "abc", "-1", "99999999", "1.5", "" -> 200, `context["section"] is None`, chip "My timetable".
  - `test_sheet_lists_three_groups`: page contains a `<dialog` with "Choose a timetable", "My timetable", "My classes", "All classes", a `type="search"` input labelled "Search classes", and one link per listed Section carrying `section=<pk>` plus the current `view`/`date`.
  - `test_no_js_pick_list`: `?pick=1` renders the same three groups in the page body (outside the dialog) and the chip href is `?pick=1&…`.
  - `test_class_view_writes_nothing`: wrap a class Day and Week request in `CaptureQueriesContext`; no query starts with INSERT/UPDATE/DELETE.
  - `test_non_teacher_gets_403_with_section`: admin and guardian -> 403 for `?section=<pk>`; logged out -> 302.
  - `test_existing_section_with_nothing_scheduled_stays_on_that_class`: a Section with no slots -> chip shows its name, Day says "No school timetable on this day." (existing sentence).
- [ ] **Step 2:** Run the module. Expected: failures.
- [ ] **Step 3: Implement** the view branch (parse `section` with `int()` inside try, `Section.objects.select_related("class_grade").filter(pk=…).first()`), template (chip, dialog, no-JS list, class cards: badge + subject + teacher line; class Week: same table markup with `short` and the class aria-label), CSS block, JS (open dialog on chip click with `showModal`, close on backdrop/close button, filter list items by `data-name` substring, case-insensitive; chip without JS stays a link), ADR amendment ("Amendment, 2026-11-17 (teacher Timetable page, class view)": any teacher may view any Section's timetable read-only from the Timetable page; subject and teacher per period; teacher derived per ADR 0018; no clock times, free periods or placeholders).
- [ ] **Step 4:** Run `core.tests.test_teacher_timetable_class core.tests.test_teacher_timetable_page`, then `--pattern="test_ui*.py" --parallel 4`, then `ruff check core/`. Expected: OK.
- [ ] **Step 5: Commit** `feat: class picker sheet and class timetables on the teacher Timetable page`.

### Task 4: Verify and PR

- [ ] `collectstatic`, run the worktree server with `--noreload`, log in as a demo teacher at 360 and 390 px: chip opens the sheet, search filters, picking a class shows Day cards with teachers, Week boxes fit with no page scroll, a box opens that day for the same class, "My timetable" returns to own view, Back works. Also open `?pick=1` directly (the no-JS path).
- [ ] Push, open the PR, reviewer subagent, verdict table to the user, wait for "merge #N".
