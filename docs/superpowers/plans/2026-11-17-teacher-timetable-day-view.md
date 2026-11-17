# Teacher Timetable, Step 1: Day view with date strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A teacher opens a new Timetable screen from My day, scrolls a date strip, taps a date and sees their own periods for that day.

**Architecture:** One new server-rendered page `core:my-timetable` at `/my/timetable/?date=YYYY-MM-DD`. The existing `core/timetable.py` helper that builds today's rows is generalised to take any date; the page reuses it. Each date chip is a plain link, so there is no new JavaScript beyond centring the selected chip.

**Tech Stack:** Django templates, existing `erp.css` tokens, `erp.js`, Django `TestCase`.

**Spec:** This plan is the spec. Decisions come from the 2026-11-17 discussion with the user: mock-up `docs/audits/img/mock-tt-1-day-mine.png`, audit `docs/audits/mobile-ui-01-guardian-teacher.md`, ADR 0021 (timetable), and TDB-0 spec section 3 (Teacher dashboard).

## Scope

This is Step 1 of 3. Not in this step, each its own plan and PR after the user's go:
- Step 2: the class picker ("Mine" or any section; every section is visible to every teacher, read-only).
- Step 3: the Day | Week toggle and the weekly grid for "Mine" and for a class.
- Later: the "Attendance not taken" chip on period cards, tapping a period to open attendance, bell times (needs an ADR 0021 amendment).

## Global Constraints

- Phone first: every tap target at least 44px tall; no horizontal page scroll at 360px and 390px; the date strip itself scrolls sideways.
- Teacher area only: `@teacher_required`; the route name starts with `my-` so `current_area()` keeps the teacher shell.
- No clock times, no free periods, no placeholders (ADR 0021 D10). A day with no slots shows a plain sentence, not blank cards.
- The teacher is never stored on a slot; "mine" means a slot whose offering and section match one of the teacher's subject assignments effective on that date (ADR 0018).
- Dates: Monday to Saturday chips only (the model has no Sunday). Business date comes from `business_today()`, never `date.today()`.
- Accepted `?date=` window is today plus or minus 366 days; anything else falls back to today.
- Existing test `test_no_links_clock_times_free_periods_or_placeholders` stays true: the My day "Today's timetable" section keeps no links. The new entry link sits just outside that `<section>`.
- Copy: page title "Timetable"; back link "‹ My day"; entry link "Full timetable ›"; empty text "No periods scheduled for you on this day."; non-school text "No school timetable on this day."
- CSS tests pin exact `erp.css` text; run `python manage.py test --pattern="test_ui*.py"` after CSS edits. Use `DJANGO_DEBUG=True`; Docker Postgres container `everclass-postgres` must be up.
- Work in a fresh branch `feat/teacher-timetable-day-view` from `main`. Full local suite before push. One PR; wait for the user's "merge #N".

## Review Focus

1. A garbage, non-ISO, empty or far-out `?date=` (`abc`, `2026-13-40`, `9999-12-31`, `0001-01-01`): page loads for today, no 500.
2. A Sunday in the URL: page loads, strip still renders, shows the non-school sentence.
3. A teacher with no subject assignments, and a day that is a school holiday (`SchoolCalendarDay`): sentence shown, no crash.
4. A past date where the teacher's assignment ended (or had not started): rows follow the assignment effective on that date, not today's.
5. Another teacher's slots never appear; a non-teacher (administrator-only, guardian) gets 403.

## File Structure

- Modify `core/timetable.py`: add `teacher_timetable_on`, keep `todays_teacher_timetable` as a wrapper; add `parse_timetable_date`, `date_strip`.
- Modify `core/views.py`: add `my_timetable` after `my_home`.
- Modify `core/urls.py`: add the route beside the other `my/` routes.
- Modify `core/navigation.py`: map `my-timetable` to `my-home` in `TEACHER_TAB_PARENTS`.
- Create `core/templates/core/my_timetable.html`.
- Modify `core/templates/core/my_home.html`: entry link after the timetable `<section>`.
- Modify `static/css/erp.css` (new `.erp-tt-*` block at the end) and `static/js/erp.js` (centre selected chip).
- Modify `core/tests/route_permissions.json` (regenerated), `core/tests/test_ui_teacher_polish.py` (pinned map).
- Create `core/tests/test_teacher_timetable_page.py`; add one case to `core/tests/test_ui_teacher_timetable.py`.

---

### Task 1: Timetable rows for any date

**Files:**
- Modify: `core/timetable.py:147-188`
- Test: `core/tests/test_teacher_timetable_page.py` (create)

**Interfaces:**
- Produces: `teacher_timetable_on(assignments, on_date, year_is_instructional) -> list[dict] | None`. Same contract and ordering as today's function, evaluated for `on_date` (slots effective on `on_date`, `weekday=on_date.weekday()`). Each row is `{"period": label, "sequence": int, "section": Section, "subject": str}` (new key `sequence`).
- Produces: `todays_teacher_timetable(assignments, today, year_is_instructional)` unchanged signature and behaviour, now a one-line wrapper.

- [ ] **Step 1: Write failing tests** in `core/tests/test_teacher_timetable_page.py`, using `TimetableDashboardFixture` from `core.tests.test_ui_teacher_timetable`. Names and assertions:
  - `test_rows_for_a_given_date_match_that_dates_weekday`: Monday slot and Tuesday slot for `rao`; `teacher_timetable_on(assignments, TUESDAY, ...)` returns only the Tuesday row.
  - `test_rows_carry_the_period_sequence`: first row has `sequence == 1`.
  - `test_none_when_the_date_is_not_an_instructional_day`: `SUNDAY` returns `None`.
  - `test_todays_wrapper_still_returns_the_same_rows`: `todays_teacher_timetable` equals `teacher_timetable_on` for the same date.
- [ ] **Step 2: Run** `DJANGO_DEBUG=True python manage.py test core.tests.test_teacher_timetable_page`. Expected: FAIL, `teacher_timetable_on` not defined.
- [ ] **Step 3: Implement** `teacher_timetable_on` by moving the current body of `todays_teacher_timetable` into it with `today` renamed `on_date`, adding `"sequence": slot.period.sequence` to each row dict; make `todays_teacher_timetable` return `teacher_timetable_on(assignments, today, year_is_instructional)`.
- [ ] **Step 4: Run** the new tests plus `core.tests.test_ui_teacher_timetable` and `core.tests.test_phase5_teacher_home`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: teacher timetable rows for any date`.

### Task 2: Date parsing and the date strip

**Files:**
- Modify: `core/timetable.py`
- Test: `core/tests/test_teacher_timetable_page.py`

**Interfaces:**
- Produces: `parse_timetable_date(raw: str | None, today: date) -> date`. Returns the parsed ISO date when it lies within `today` plus or minus 366 days, otherwise `today`. Never raises.
- Produces: `date_strip(selected: date, today: date) -> list[dict]`. Chips for Monday to Saturday of the weeks from two weeks before to two weeks after the week of `selected` (30 chips, no Sundays). Each chip: `{"date": date, "weekday": "Mon", "day": 17, "is_today": bool, "is_selected": bool, "month_start": bool}` where `month_start` is true on the first chip of a new month.

- [ ] **Step 1: Write failing tests**:
  - `test_parse_accepts_a_valid_date_inside_the_window`.
  - `test_parse_falls_back_to_today_for_garbage_empty_none_and_out_of_window`: cover `"abc"`, `""`, `None`, `"2026-13-40"`, `"9999-12-31"`, `"0001-01-01"`, and one day past each edge of the window (edge days themselves accepted).
  - `test_strip_has_30_chips_monday_to_saturday_no_sundays`.
  - `test_strip_marks_exactly_one_selected_and_one_today_and_none_when_today_is_outside`.
  - `test_strip_for_a_sunday_selection_still_builds` (selected Sunday: no chip is selected, still 30 chips).
- [ ] **Step 2: Run** them. Expected: FAIL, names undefined.
- [ ] **Step 3: Implement both helpers**: use `datetime.date.fromisoformat` inside try/except `ValueError`/`TypeError`; build the strip from the Monday of `selected`'s week.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: timetable date parsing and strip`.

### Task 3: The page, route and navigation

**Files:**
- Modify: `core/views.py` (after `my_home`), `core/urls.py` (beside `path("my/", ...)`), `core/navigation.py:72-83`
- Create: `core/templates/core/my_timetable.html`
- Modify: `core/tests/route_permissions.json` (regenerate), `core/tests/test_ui_teacher_polish.py` (the pinned map test)
- Test: `core/tests/test_teacher_timetable_page.py`

**Interfaces:**
- Consumes: `teacher_timetable_on`, `parse_timetable_date`, `date_strip`, `current_teacher_assignments(user, on_date)`, `business_today()`.
- Produces: view `my_timetable(request)` decorated `@teacher_required`, URL name `core:my-timetable`, path `my/timetable/`. Context keys: `selected` (date), `today` (date), `is_today` (bool), `strip` (list from `date_strip`), `rows` (`None`, `[]` or list from `teacher_timetable_on`). Template emits `<a ... aria-current="date">` on the selected chip, a "Today" link to the bare route, and the sentences from Global Constraints.

- [ ] **Step 1: Write failing tests**:
  - `test_teacher_sees_own_periods_for_the_chosen_date` (Tuesday slot visible at `?date=2026-10-13`, absent on the Monday).
  - `test_default_date_is_today_with_no_query`.
  - Review Focus 1 to 5 as named tests: `test_bad_date_values_load_today_not_500`, `test_sunday_shows_non_school_sentence_and_strip`, `test_no_assignments_shows_empty_sentence`, `test_holiday_shows_non_school_sentence`, `test_past_date_uses_assignments_effective_then`, `test_other_teachers_slots_never_appear`, `test_non_teacher_gets_403` (administrator-only and guardian).
  - `test_selected_chip_has_aria_current_and_today_link_goes_to_bare_route`.
  - `test_today_tab_stays_active` (the "Today" teacher tab is active on this page).
- [ ] **Step 2: Run** them. Expected: FAIL (no such URL).
- [ ] **Step 3: Implement** `my_timetable`: parse `request.GET.get("date")` with `parse_timetable_date`; `assignments = list(current_teacher_assignments(request.user, selected).select_related("section__class_grade", "offering__subject"))`; a cached `year_is_instructional(year)` as in `my_home`; render `core/my_timetable.html`. Template extends the same base as `my_home.html`, uses the back link pattern from `my_attendance.html`, one `<h1>`, a `<nav aria-label="Pick a day">` strip of links, then cards (period number badge `sequence`, section bold, subject muted). Add `"my-timetable": "my-home"` to `TEACHER_TAB_PARENTS`.
- [ ] **Step 4: Update** the pinned map expectation in `test_ui_teacher_polish.py` (`test_map_covers_the_agreed_nested_pages`) to include `"my-timetable": "Today"`. Regenerate the route pin: `python core/tests/route_inventory.py --write`; confirm the diff adds only `core:my-timetable` with flag `teacher_required`.
- [ ] **Step 5: Run** `core.tests.test_teacher_timetable_page`, `core.tests.test_ui_teacher_polish`, `core.tests.test_security_gate4b_route_inventory`, `core.tests.test_403_neutral_shell`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: teacher timetable day page`.

### Task 4: Styling, strip centring and the My day entry link

**Files:**
- Modify: `static/css/erp.css` (append `.erp-tt-*` block), `static/js/erp.js`, `core/templates/core/my_home.html:38-55`
- Test: `core/tests/test_ui_teacher_timetable.py` (one case), plus the CSS-pinning tests

**Interfaces:**
- Consumes: template classes from Task 3 (`erp-tt-strip`, `erp-tt-chip`, `erp-tt-card`, `erp-tt-badge`). Strip chip markup carries `aria-current="date"` for the selected one.
- Produces: link `<a class="erp-tt-open" href="{% url 'core:my-timetable' %}">Full timetable ›</a>` placed directly after the closing `</section>` of "Today's timetable", shown whenever that section is shown (`timetable_rows is not None`).

- [ ] **Step 1: Write failing test** `test_full_timetable_link_sits_outside_the_plain_text_section` in `test_ui_teacher_timetable.py`: the page contains `href` to `reverse("core:my-timetable")` and the text "Full timetable", and `section_html(page)` still has no `<a ` or `href`. Also `test_link_hidden_when_the_section_is_hidden` (`timetable_rows is None`).
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Add the link** to `my_home.html`; **add CSS** using existing tokens (`--erp-accent`, `--erp-accent-wash`, `--erp-rule`, `--erp-space-*`): 44px minimum tap height, strip `display:flex; overflow-x:auto; scroll-snap-type:x proximity`, selected chip filled `--erp-accent` with white text, today chip ringed, card layout as in the mock-up. **Add JS** in `erp.js`: on `DOMContentLoaded`, find `.erp-tt-strip [aria-current="date"]` and set the strip's `scrollLeft` so it is centred (no smooth scrolling, no errors when absent).
- [ ] **Step 4: Run** the new tests, then `DJANGO_DEBUG=True python manage.py test --pattern="test_ui*.py" --parallel 4`. Expected: PASS (fix any pinned-CSS test by adding the new block, not by editing old text).
- [ ] **Step 5: Commit** `feat: timetable page styling and My day link`.

### Task 5: Verify on a phone width, full suite, PR

- [ ] **Step 1:** Start the local server (`DJANGO_DEBUG=True`, Docker up, run `collectstatic` and restart first, see the stale-staticfiles note). Sign in as the demo teacher at 390px and 360px. Check: no horizontal page scroll; selected chip centred and filled; tapping another date loads that day; Sunday and a far date show the sentences; Back goes to My day; "Today" tab is active; first period card is visible without scrolling (the title and the strip should fit above it).
- [ ] **Step 2:** Run the full suite once: `DJANGO_DEBUG=True python manage.py test --parallel 4`. Expected: all pass except the one known date-dependent failure; report it as pre-existing if it appears.
- [ ] **Step 3:** Push the branch and open the PR with a short summary, the phone screenshots and the test results. Then start the reviewer subagent, verify its findings, and report a verdict table. Fix only what the user picks. Wait for "merge #N".

## Self-Review

- Spec coverage: entry button or arrow (Task 4), scrollable date strip (Tasks 2, 3, 4), selecting a date shows that day (Task 3), "Mine" only (Task 3, assignments filter), Steps 2 and 3 explicitly out of scope.
- Types: `teacher_timetable_on` rows gain `sequence`; Task 3 reads `sequence`; `date_strip` chip keys match the template needs; `parse_timetable_date` returns `date` on every path.
- Conflict flagged for the user: ADR 0021 D10 and the existing test forbid links, free periods and placeholders inside the My day timetable section. This plan puts the new link outside that section and shows no free-period rows, so the free-period and dash ideas from earlier mock-ups are dropped. The weekly grid in Step 3 needs a decision on empty cells.
