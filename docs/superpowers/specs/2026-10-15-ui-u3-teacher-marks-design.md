# U3 Teacher Marks and Students — Design

**Date:** 2026-10-15
**Roadmap:** `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md` (U3)
**Spec sources:** `docs/UI_REFERENCES.md` picks 3.3 Yazio (marks entry), 5.2 Google Classroom (gradebook), 3.4 Cash App (students list), 5.4 SchoolAI (class overview)
**Builds on:** U1 shell (merged) and U2 components (PR #47: `.erp-card`, `.erp-toggle`, `.erp-actionbar`, `.erp-initials`, `.erp-section-title`). The U3 branch starts from `ui/u2-teacher-daily` and is rebased onto `main` once #47 merges.

## Goal

A subject teacher can enter a class's marks quickly on a phone, see all marks for a Subject and Section at a glance on a larger screen, and a class teacher can see today's attendance of their students at a glance.

## Decisions (owner, 2026-10-15)

| Topic | Decision |
|---|---|
| Phone marks entry | All students on one page, one card each: large numeric score box (number keypad) and an Absent choice; the keypad's Next moves to the next student. Same form as today; works without JS. |
| Gradebook | Included: a new read-only page per teaching assignment (Subject + Section), students × assessments. One new teacher URL; same access rule as marks entry. |
| Chips on My students | Today's attendance (Present / Absent) for the class teacher's Sections, only from a submitted register. |

## Constraints

- No model, migration or permission changes. New: one view and one URL (gradebook). Marks entry POST is unchanged (`status_<pk>` = "" / MARKED / ABSENT, `score_<pk>`).
- Blank means "not marked yet", never zero and never absent — in entry, gradebook and every count.
- No totals, averages, weighting or ranks anywhere (report-card rule applies to teacher views too).
- Works with JS off; 360 px without horizontal page scroll (the gradebook grid scrolls inside its own box).
- Draft vs finalized is always visible.

## Design

### 1. Marks entry — `core/assessment_marks_entry.html`

- Header: Subject, Section, assessment name; meta line: term · date · "out of N" · pass mark; status pill (Draft entry open / Finalized / Opens on date).
- Rule line kept: "Leave a row blank if you have not marked that Student yet — blank is not absent."
- Static counts (same pattern as U2): "All 32 · Not marked 5 · Marked 26 · Absent 1"; JS turns them into filter tabs with live counts. A new form helper `ResultEntryForm.counts()` (keys `all`, `marked`, `absent`, `unmarked`) — a row counts as marked when its status is MARKED or it has a score.
- One card per student (`fieldset`, visually hidden legend with the name, visible name + initials):
  - Score input: `inputmode="decimal"`, `enterkeyhint="next"`, large (min 44 px tall), label "Score out of N" (visually hidden name suffix).
  - Status as a three-way toggle (same `.erp-toggle` style): **Not marked** (value ""), **Marked**, **Absent**. Typing a score selects Marked (JS; the server already treats a score with no status as Marked). Choosing Absent clears and disables the score box (JS only; without JS the server rejects Absent + score with the existing message).
  - Field errors shown under the card.
- Sticky action bar: "N not marked" + **Save draft** (existing single action). After POST the existing messages show via U1's live region.
- Finalized / not yet open: the existing results partial `core/_assessment_results.html` restyled as cards (name, score or "Absent", nothing for blank → "Not marked").

### 2. Gradebook — new `my_gradebook` view, `core/my_gradebook.html`

- URL: `my/gradebook/<int:pk>/` where `pk` is the teacher's `AssessmentTeacherAssignment`. 404 unless the row belongs to `teacher_assignments(request.user)`; `@teacher_required`.
- Context: the assignment; its assessments (same offering and Section, ordered by date then name); rows = students on any of those assessments' rosters, ordered by name, each with one cell per assessment.
- Cell values: score (e.g. "18"), "Abs" for ABSENT, empty for no result. Draft cells are styled (italic + "draft" in the screen-reader text); finalized cells plain. Column header: short name, date, "/ max", and a status pill. Clicking a column header opens marks entry for that assessment.
- No totals, averages, percentages or ranks; no colour scale by score.
- Layout: a real `<table>` with a sticky first column, inside a horizontally scrolling box (`.erp-grid-scroll`); caption "Marks for Mathematics, Grade 6 - A". On phones the same table scrolls sideways.
- Entry points: on "My assessments", each duty becomes a card with "Gradebook" and its assessments listed below; on My day nothing changes.

### 3. My students — `core/my_students.html`

- Grouped by Section as now; each group is a section header (Section + "Class teacher" pill) followed by rows: initials avatar, full name (link to the student page), and — for class-teacher Sections only — today's chip:
  - Present / Absent pill when today's register for that Section is **submitted**;
  - nothing per row, and one line under the header "Today's attendance not submitted yet" when the register is missing or still a draft.
- View context addition in `my_students`: `today_status` dict `{enrollment_pk: "PRESENT" | "ABSENT"}` and `submitted_sections` set, built from today's submitted registers of the class-teacher Sections (one query each).
- Empty state via `partials/_empty.html` with the existing text.

### Components (CSS/JS)

- CSS: `.erp-score` (large numeric input), `.erp-grid-scroll`, `.erp-grid` (sticky first column, compact cells, draft styling), reuse `.erp-toggle`, `.erp-roster-row`, `.erp-actionbar`, `.erp-count-tabs`, `.erp-initials`, `.erp-pill`.
- JS (one block keyed off `[data-erp-marks]`): live counts/filter tabs (reusing the U2 roster logic generalised to read a row's status from `data-erp-status-of`), score-typed → Marked, Absent → clear and disable score.

## Testing (new `core/tests/test_ui_teacher_marks.py`)

- Marks entry POST names/values unchanged; score input has `inputmode="decimal"` and `enterkeyhint="next"`; each row is a fieldset named by the student.
- `ResultEntryForm.counts()` for saved results and for bound data (score without status counts as marked; blank is not marked).
- Blank stays "Not marked" on the finalized results cards; ABSENT shows "Absent", never 0.
- Gradebook: 404 for another teacher's assignment and for a non-teacher; cells show score / "Abs" / empty; draft vs finalized distinguishable; no "Total", "Average", "%" or "Rank" text; students ordered by name; header links to marks entry.
- My students: chips only for class-teacher Sections and only from a submitted register; draft register → "not submitted yet" line and no chips; subject-only Sections have no chips.
- Existing marks-entry and teacher tests keep passing.

## Out of scope

Changing finalization or correction flows; office gradebooks (U6); per-student mark history on the student page; offline entry.
