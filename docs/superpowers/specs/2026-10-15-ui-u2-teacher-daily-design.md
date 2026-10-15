# U2 Teacher Daily Screens — Design

**Date:** 2026-10-15
**Roadmap:** `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md` (U2)
**Spec sources:** `docs/UI_REFERENCES.md` picks 3.1 Insight Timer (My day), 3.2 Luma (take attendance), 5.13 Luma (feedback)
**Builds on:** U1 foundation (`ui/u1-foundation`, PR #44): tokens in `static/css/erp.css`, `static/js/erp.js`, teacher tab bar, live-region messages, empty-state partial, `.erp-pill`.

## Goal

A class teacher can take today's attendance quickly and correctly on a phone (360 px), and see their day and attendance history without horizontal scrolling.

## Constraints

- Templates, CSS, JS and view context only. No model, migration, URL, form-field or permission changes. Every existing test keeps passing.
- Works with JS off. JS only adds filtering, live counts and hints.
- Domain rules stay visible: an unanswered student is unmarked, never present or absent; draft vs submitted is always shown; submit requires every student marked (enforced by the server, unchanged).
- Attendance lists stay ordered by student name; nothing is ranked by percentage.
- Every changed page usable at 360 px and 1280 px.

## Decisions (agreed 2026-10-15)

| Topic | Decision |
|---|---|
| Absence note | Inline field revealed under a row when Absent is chosen (no bottom sheet). |
| Count tabs | All / Unmarked / Present / Absent tabs filter the rows on the page with JS and update counts live; without JS they are a static count line and every row is shown. |
| Week strip on My day | Not in U2. |
| Office register page | Shares the new capture partial; keeps its own permission checks on Submit. |
| Submit button | Stays enabled; JS shows "Mark all students to submit" and the unmarked count. Server check unchanged. |
| My day | Cards with one action each for attendance, marks to enter, and term remarks. |
| History | Assignment list as cards; month page with summary line, prev/next month arrows, compact per-student rows, register cards. |
| Bottom bars | While a draft register is shown, the teacher tab bar is hidden and the sticky Save/Submit bar takes its place. |
| Per-student summary | Compact rows: name, then "18 P · 2 A · 90%". |
| Month picker | "‹ September 2026 ›" plain links to previous/next allowed months. |

## Design

### 1. Take attendance — `core/_attendance_capture_table.html` (shared), `core/my_attendance.html`, `core/attendance_register_detail.html`

Controls stay the existing `AttendanceCaptureForm` radio inputs and note text inputs (same names `status_<pk>`, `note_<pk>`, same values), restyled with CSS. The POST is unchanged for both views.

- **Header:** Section, date, Draft pill (`.erp-pill.is-draft`) or Submitted pill.
- **Count tabs** (`.erp-count-tabs`): buttons `All n`, `Unmarked n`, `Present n`, `Absent n`. The server renders initial counts from the form's initial values; JS recounts on each change and hides non-matching rows (`hidden` attribute) when a tab is chosen. Without JS: a static count line, no buttons, all rows visible. Buttons use `aria-pressed`, so screen readers hear "Unmarked 5, pressed".
- **"Mark unanswered as present"** moves into the tab row; behaviour unchanged (never overrides a choice). It is rendered hidden and shown by JS, since it only works with JS.
- **Student row** (`.erp-roster-row`): a `fieldset` whose `legend` is the student's full name; an initials avatar (decorative, `aria-hidden`); the two radio inputs rendered as large toggle labels `Present` / `Absent` (min 44 px tall, splitting the row width on phones); the note input below, labelled "Absence note for <name>".
  - The note is shown when Absent is checked (CSS `.erp-roster-row:has(input[value="ABSENT"]:checked) .erp-note`) inside `@supports selector(:has(*))`; browsers without `:has` simply show the note all the time. A note that already has a value, or has a validation error, is always visible.
- **Sticky action bar** (`.erp-actionbar`): fixed to the bottom on phones, sticky at the end of the form on wide screens; shows the unmarked count, `Save draft` and the submit button. Buttons keep their current text and `name="action"` values. On the office page the submit button still renders only with `perms.core.change_attendanceregister`.
  - JS hint next to submit: "Mark all students to submit (5 unmarked)" while any row is unmarked; hidden when complete. Submit is never disabled.
- **Tab bar hidden:** `base.html` wraps the tab bar include in `{% block tabbar %}` and the `has-tabbar` body class in `{% block tabbar_class %}`; `my_attendance.html` overrides both as `{% if register is None or register.is_submitted %}{{ block.super }}{% endif %}`, so they are empty while a draft register is shown (no view change). "Back to My day" moves to the top of the page.
- **Feedback:** the existing Django messages ("Draft saved.", "Attendance saved and submitted.", errors) through U1's live region; no new toast component.
- **Submitted view (teacher):** card list, one row per student: name, Present/Absent pill, note. The text "Submitted attendance can only be changed by an administrator, through a correction." stays.
- **No register yet / not a school day:** existing texts kept, shown in the empty-state partial, with "Start today's register" as its action.

### 2. My day — `core/my_home.html`

Kept texts: "My day", "You are not a class teacher today.", "My assessments" (via the "All my assessments" link).

- Date line under the heading.
- **Attendance cards** (`.erp-card`), one per duty: Section name, state pill (Not taken / Draft — not yet submitted / Submitted / Not a school day), one action: `Take attendance` (primary), `Continue` (outline) or `View` (link); none when not a school day. Empty state as today. Link "Attendance history for my Sections" below.
- **Marks to enter:** a card per assessment: name (link to marks entry), subject · section · date, and "12 unmarked". Empty: "Nothing waiting." with the link to all my assessments.
- **Term remarks:** a card per term and section: "Year Term · Section", "18 of 32 written" with a `<progress>` bar, linking to the remarks page.
- No view change.

### 3. Attendance history — `core/my_attendance_history.html`, `core/my_attendance_assignment.html`, `core/my_attendance_register.html`

- **History list:** a card per class teacher assignment: Section, Academic Year, "From <date> until <date or now>", `Open` link. Empty text kept.
- **Month page:**
  - Header: Section, year, "showing <start> to <end>".
  - Month nav: `‹ Previous` · **September 2026** · `Next ›`, plain `?month=YYYY-MM` links, each omitted at its end of the allowed range. **View context addition** in `my_attendance_assignment`: `previous_month`, `next_month` (`"YYYY-MM"` or `None`) and `chosen_label` (e.g. "September 2026"), computed from the existing `months` list. The `month` query handling is unchanged.
  - Summary line: "Expected 20 · Submitted 18 · Missing 2 · 92% present" (percentage omitted when None).
  - Per-student rows: name, then "18 P · 2 A · 90%" ("–" when None), ordered by name as now.
  - Registers: a card per register: date (link), status pill, "Present 30 · Absent 2".
  - Not taken: dates with weekday as warning pills.
- **Read-only register page:** the same card list as the submitted view in section 1.

### Components added to `erp.css` / `erp.js`

- CSS: `.erp-card`, `.erp-count-tabs`, `.erp-roster-row`, `.erp-toggle` (radio as button), `.erp-note`, `.erp-actionbar`, `.erp-month-nav`, `.erp-stat-line`, `.erp-initials`.
- JS: one block in `erp.js` keyed off `[data-erp-roster]`: live counts, tab filtering, submit hint, and the mark-unanswered-present behaviour moved out of the partial's inline script.

## Testing

New `core/tests/test_ui_teacher_daily.py`:

- Capture POST names and values unchanged: for each roster enrollment the page has `name="status_<pk>"` radios with values PRESENT and ABSENT, and `name="note_<pk>"`, on both teacher and office pages.
- Each roster row is a `fieldset` with the student's name as `legend`.
- Static counts are correct for a draft with mixed entries (Present 1, Absent 1, Unmarked 1).
- A saved absence note is in the markup and not hidden.
- Teacher tab bar is not rendered on `my_attendance` while a draft is open, and is rendered on My day.
- Office page: no submit button without `change_attendanceregister`.
- My day renders the right pill and single action for NOT_TAKEN, DRAFT, SUBMITTED and NOT_INSTRUCTIONAL.
- Month page: `previous_month` / `next_month` correct for the first, a middle and the last month; links omitted at the ends.
- Per-student rows stay ordered by name.

Plus the roadmap definition of done: full suite, `ruff check .`, manual check at 360 px and 1280 px as a teacher and an office user from `seed_demo`.

## Out of scope

Week strip on My day; bottom-sheet absence note; marks entry (U3); office attendance grid (U6); any change to submit or correction rules.
