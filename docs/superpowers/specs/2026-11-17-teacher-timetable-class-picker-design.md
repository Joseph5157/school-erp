# Teacher Timetable, Step 2: class picker (design)

Date: 2026-11-17. Status: design approved in conversation ("ok" to the proposed design, no mock-ups
first). Builds on Step 1 (Day view, PR #257) and Step 3 (Week view, PR #260).

## Intent and why

A teacher can look at any class's timetable from the Timetable page, read-only, on a phone. They do
it for three reasons (proposed by Claude, accepted by the user):

1. **Covering a class**: a colleague is absent; what does that class have, and when?
2. **Finding a colleague**: who teaches 7-B in period 3, so they know where that teacher is.
3. **Class teachers** checking their own class's whole day, including periods they do not teach.

So a class's timetable shows **subject and teacher** for each period.

## Goals

- A chip under the "Timetable" heading shows what is on screen: "My timetable" or the class name
  ("Grade 6 - A"). Tapping it opens a bottom sheet with three groups:
  - **My timetable** (the current teacher-own view);
  - **My classes**: the teacher's class-teacher Section(s) and the Sections they teach a subject in,
    on the selected date;
  - **All classes**: every Section that has timetable slots effective on the selected date, grouped by
    Class/Grade in display order, with a search box that filters the list as you type.
- Picking a class shows that class's timetable in the existing Day and Week views, keeping the
  current view (Day/Week) and date.
- **Day view for a class**: one card per period with the period number, the subject, and the teacher
  ("Mrs Rao"; full name or username as elsewhere). A slot with no teacher assigned that day shows
  "No teacher assigned" on the card.
- **Week view for a class**: the grid as today, but each box shows a short subject label (see rule)
  and the key under the grid maps short labels to full subject names. Boxes link to that day's Day
  view for the same class. Each box's aria-label carries the full subject and teacher, e.g.
  "Mathematics, Mrs Rao, period 3, Monday 16 November".
- The URL carries the class: `?section=<pk>` alongside `view` and `date`, so Back, refresh and a
  shared link keep it. The Day | Week toggle, week arrows, date strip and "Today" link all keep
  `section`.

## Non-goals

- Editing anything; substitutions; free-teacher finder; room or clock times (ADR 0021 D10 still
  holds: no clock times, no free periods, no placeholders; blank boxes stay empty).
- Student or guardian timetables.
- Teacher-to-teacher lookup ("Mrs Rao's timetable"): only classes are pickable.

## Anti-goals

- Showing a class timetable to anyone who is not a teacher (admins and guardians keep 403 on this
  page as today).
- Changing who can see the teacher's *own* view or any other page.
- Per-cell database queries.

## Constraints

- **Authorization change, recorded:** every active teacher (the existing `teacher_required` gate)
  may view every Section's timetable read-only. ADR 0021 currently scopes the teacher timetable to
  "the signed-in teacher's own periods" (D10, D11); add an amendment stating the read-only class view
  and its audience. Tests cover: non-teacher 403, logged-out redirect, unknown or malformed `section`
  falls back to "My timetable" (no 404/500 leak of which ids exist), and that the view writes
  nothing.
- **Teacher of a slot on a date** is derived exactly as everywhere else: the holder of the
  `AssessmentTeacherAssignment` for the slot's offering + Section effective that date (ADR 0018,
  ADR 0021 "a slot has no stored teacher"). Never guessed, never stored.
- **Days**: a class's day/week uses the same school-day rules as the teacher view (instructional
  days per Academic Year, Saturday hidden when not a school day, holiday column greyed with
  "Holiday"/"No school", Sunday opens the coming week).
- **Short subject label rule**: the first 3 characters of the subject name, title-cased as stored
  ("Mathematics" -> "Mat", "English" -> "Eng", "Hindi" -> "Hin"). Clashes are allowed because the
  key and aria-labels carry the full name.
- Phone first: grid fits 360/390 px with no page scroll; sheet rows and chip are at least 44 px tall;
  the sheet is a native `<dialog>` (pattern already used by the order dialogs in `erp.js`) and works
  without JS by the chip falling back to a plain link to a picker list (`?pick=1`) rendered in the
  page.
- Pinned-CSS tests: add a new CSS block, do not edit old text; avoid `overflow-wrap: anywhere`
  (forbidden after the UI-D1-1 marker by `test_ui_admin_desktop_d1`).
- Business date from `business_today()`; `date` parsed with `parse_timetable_date`.
- One PR; tests per the 2026-11-17 rule (targeted modules + `test_ui*` because CSS changes; CI runs
  the full suite); reviewer subagent after opening; wait for "merge #N".

## Approaches

1. **Chip + bottom sheet on the same page, `?section=` in the URL** (picked). Reuses the Day/Week
   views and their tests; one URL shape; matches the Mobbin reference the user chose earlier.
   Costs a small amount of JS for the dialog and search, with a no-JS fallback.
2. A `<select>` dropdown like My students' class picker. Cheapest, but a long list of every Section
   in a native select is hard to search on a phone and cannot show the three groups clearly.
3. A separate "Class timetables" page. Duplicates the Day/Week code paths and splits navigation.

The user specified the chip + bottom sheet shape when the feature was first discussed; approach 1
follows it.

## Decided (in conversation)

- Chip + bottom sheet with My timetable / My classes / All classes + search.
- Every teacher may see every Section, read-only.
- Class boxes show subject and teacher (Day) and short subject with key (Week); tapping a Week box
  opens that day.
- No mock-ups before building.

## Settled after the builder check (Claude's calls)

1. **A picked class with nothing on the chosen date or week** (shared link opened later, date moved
   outside its year, archived Section): the page stays on that class and shows the usual empty or
   non-school sentence. `section` is only checked to be an existing Section id; unknown or malformed
   ids fall back to "My timetable". All Section names are already visible to every teacher via the
   sheet, so staying on an existing id leaks nothing new.
2. **Whose school-day rules**: the same rule as the teacher view, applied to that Section's slots:
   a day is judged by the Academic Years that have the Section's slots effective that day
   (`is_instructional_day`). A Section has no calendar of its own, so the teacher-view day logic is
   reused, filtered to the Section instead of the teacher's assignments.
3. **Which dates the sheet lists for**: Day view uses the selected date; Week view uses the whole
   displayed week (a Section counts if it qualifies on any day of that week), for both "My classes"
   and "All classes".
4. **Teacher name when the account is now inactive**: the card shows the holder of the assignment
   effective that day regardless of account state, following ADR 0018 D9 (history follows the
   assignment rows; account state is an authorization question only).

## Left to the builder (Claude's calls, reviewable in the PR)

- Exact chip and sheet styling within `erp.css` tokens; caret glyph.
- Whether "My classes" lists class-teacher Sections first (proposed: yes, then subject Sections by
  grade order), and de-duplication when a teacher is both.
- Search matching: case-insensitive substring on the Section's full name ("6 - a" and "grade 6"
  both find Grade 6 - A).
- Function names and where the class-day builder lives (`core/timetable.py` alongside
  `teacher_timetable_on`).
