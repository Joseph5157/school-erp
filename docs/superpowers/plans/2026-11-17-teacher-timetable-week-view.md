# Teacher Timetable, Step 3 (done before Step 2): Week view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the teacher Timetable page, a Day | Week toggle shows the teacher's own week as a grid (periods down, school days across), with week arrows, short class labels and a key.

**Architecture:** Same page and route, `core:my-timetable`, with `?view=week&date=YYYY-MM-DD` (any date inside the wanted week). A new pure helper builds the week from the existing per-date helper `teacher_timetable_on`, one call per weekday, so assignments and calendars are judged per day exactly as the Day view does. No model change, no new route.

**Tech Stack:** Django templates, `erp.css` tokens, Django `TestCase`.

**Spec:** this plan. Decisions from the 2026-11-17 discussion: mock-up `docs/audits/img/mock-tt-week-mine-fixed.png`; weekly view comes before the class picker (Step 2), "Mine" only for now; blank cells, never a "Free" label; Saturday column hidden when it is not a school day; tapping a cell opens that day; holidays are a greyed column with a label on the day header; the date line is dropped in Week view; short class labels with a key under the grid. Starts only after PR #257 is merged and the user says go.

## Global Constraints

- Phone first: grid fills the content width at 360px and 390px (`erp-keep` on the table so the phone table rule does not turn it into a scroll box); no horizontal page scroll; filled cells are tap targets at least 44px tall.
- ADR 0021 D10: no clock times, no free periods, no placeholders. A blank cell is an empty `<td>` with no text. A day that is not a school day may carry a header label ("Holiday" or "No school"), which describes the day, not a period. Record this in a short ADR 0021 amendment.
- "Mine" = slots whose offering and section match the teacher's subject assignments effective ON THAT DAY (ADR 0018), so a mid-week hand-over is shown correctly.
- Business date from `business_today()`. `?date=` parsed with the existing `parse_timetable_date` (today +/- 366 days, never raises). Unknown `view` values mean Day.
- Short class label rule, exact:
  - class part: if the Class/Grade name ends in a number, that number ("Grade 2" -> "2", "Class 10" -> "10"); otherwise its first 3 characters ("Nursery" -> "Nur", "LKG" -> "LKG");
  - section part: the section name if it is 1 or 2 characters, otherwise its first 3 characters ("Rose" -> "Ros");
  - joined with "-": "2-B", "10-A", "LKG-A", "Nur-Ros".
- Every filled cell is a link to that day's Day view, with `aria-label="<full section name>, period <n>, <weekday> <j F>"` (for example "Grade 2 - B, period 3, Monday 16 November").
- Key under the grid: one entry per distinct section shown that week, "<short> <full section name>", sorted like the grid (class display order, then section name).
- Copy: toggle "Day" / "Week"; week heading "16 – 21 Nov 2026" with "This week" under it when the week contains today; arrow labels "Previous week" / "Next week"; hint "Tap a class to open that day."; empty-week sentence "No periods for you this week."
- Run tests with `DJANGO_DEBUG=True` and `--noinput`, one test process at a time; pinned-CSS tests: add a new CSS block, do not edit old text. New branch from main after #257 merges; one PR; wait for "merge #N".

## Review Focus

1. A week where the teacher's assignment starts or ends mid-week: each day shows that day's own rows.
2. A week containing a holiday, and a week with an instructional Saturday (calendar override or `saturdays_instructional`): the holiday column is greyed with its label; Saturday appears only when it is a school day in at least one of the teacher's years.
3. Class names without a trailing number and long section names ("Nursery" / "Lotus"): labels follow the rule and stay inside the cell; two sections that shorten to the same label are still told apart by the key and the aria-labels.
4. `?view=week` with a garbage or far `date`, and week arrows at the edge of the +/- 366 day window: page loads, no 500.
5. Another teacher's slots never appear; non-teachers get 403; query count stays bounded (no per-cell queries).

## File Structure

- Modify `core/timetable.py`: add `short_section_label(section) -> str` and `teacher_week(user, any_date, today, year_is_instructional) -> dict`.
- Modify `core/views.py` (`my_timetable`): read `view`; build Day or Week context.
- Modify `core/templates/core/my_timetable.html`: toggle, week header with arrows, grid, key; Day view unchanged apart from the toggle.
- Modify `static/css/erp.css`: new `.erp-tt-week*` / `.erp-tt-toggle` block placed next to the existing `.erp-tt-*` block (before the `/* UI-D1-4B` marker).
- Modify `docs/adr/0021-timetable-periods-and-weekly-slots.md`: amendment for blank cells and day-header labels.
- Tests in `core/tests/test_teacher_timetable_page.py`.

---

### Task 1: Short labels and the week builder

**Interfaces:**
- `short_section_label(section) -> str` (rule in Global Constraints).
- `teacher_week(user, any_date, today, year_is_instructional) -> dict` with keys: `monday` (date), `days` (list, Monday to Saturday, each `{"date", "weekday": "Mon", "is_today", "is_school_day": bool, "label": "" | "Holiday" | "No school", "rows": list}`; Saturday omitted when it is not a school day), `periods` (sorted list of period sequence numbers that appear in any day of the week), `cells` (dict `(sequence, date) -> row`), `key` (list of `{"short", "full"}`), `is_empty` (bool). Uses `current_teacher_assignments(user, day)` and `teacher_timetable_on` per day.

- [ ] Tests first: label rule table (the six examples above plus a 1-character class name and a 100-character section name); mid-week hand-over; holiday column; instructional Saturday shown, ordinary Saturday omitted; empty week; other teacher's slots absent; bounded query count (compare a 1-row and a 6-row week).
- [ ] Implement; run `core.tests.test_teacher_timetable_page`; commit `feat: teacher week builder and short class labels`.

### Task 2: Week view on the page

**Interfaces:** consumes `teacher_week`, `parse_timetable_date`. Context adds `view` ("day" | "week"), `week` (from `teacher_week`), `prev_week_date`, `next_week_date`.

- [ ] Tests first: toggle links keep the date (`?view=week&date=…` / `?date=…`); Week shows no date line and no strip; header text and "This week"; arrows go +/- 7 days; filled cells link to that day with the exact aria-label; blank cells contain no text; key entries; holiday header label; empty-week sentence; Review Focus 4 (bad dates, window edges) and 5 (403, scoping); the Day view output is unchanged apart from the toggle.
- [ ] Implement view, template (table with `class="erp-keep"`, visually hidden caption, `scope` on headers), CSS block, ADR amendment; run the page tests and `--pattern="test_ui*.py" --parallel 4`; commit `feat: week view on the teacher timetable page`.

### Task 3: Verify and PR

- [ ] `collectstatic`, restart the worktree server, check at 360px and 390px: grid fills the width, no page scroll, today's column highlighted, Saturday hidden for the demo school, holiday column greyed (add a calendar override in the dev data only if needed and remove it after), cell tap opens that day, Back works.
- [ ] Full suite once (`DJANGO_DEBUG=True python manage.py test --parallel 4 --noinput`), push, open the PR, one reviewer pass, report a verdict table, wait for "merge #N".
