# TDB-0 Teacher Dashboard — Design / Spec Freeze

**Date:** 2026-10-18
**Baseline:** `main` at `0a3a947`
**Status:** Accepted / Implemented. TDB-0 itself was documentation only; TDB-1 to TDB-6 are implemented and accepted, including the Today timetable (ADR 0021, TDB-3 to TDB-5). This document keeps its TDB-0 baseline and decision history; statements written as of TDB-0 are marked as such.
**Rules:** `docs/UI_DESIGN_RULES.md`. **Builds on:** U2 teacher daily screens and U3.1 Teacher Mobile Polish (`2026-10-18-ui-u3-1-teacher-mobile-polish-design.md`).
**Domain sources of truth:** ADR 0011 (class teacher), ADR 0018 (effective-dated subject teacher assignments), ADR 0008 (school calendar), ADR 0012 (teacher attendance).

## Goal

Turn the Teacher "My day" page (`core:my-home`, nav label **Today**) into a compact dashboard: who am I today, what needs doing today, what do I teach. It reorganises data the app already holds. It adds no domain behaviour.

## Constraints

- Django + Bootstrap, server-rendered, no build step, works with JS off.
- Reuse existing URLs, permissions (`teacher_required`) and effective-dating helpers. No new URL is needed for TDB-1 or TDB-2.
- Mobile-first: 360px and 390px with no page-level horizontal scroll, touch targets at least 44x44, visible focus, status never colour-only.
- Calm institutional ERP style, restrained green accent (`--erp-accent`), no decorative analytics or charts.
- No fake statistics, averages, ranks or percentages. A number appears only if it is a real count from existing data.
- Teacher bottom navigation stays `Today · Students · Assessments · Results`. Nested pages keep mapping to their parent via `TEACHER_TAB_PARENTS`.

## Approved structure (top to bottom)

### 1. Header

- Greeting, then today's business date (`business_today()`, formatted like today's `l, j F Y`).
- **School day / Not a school day** pill, shown only when it can be derived truthfully (see "Header status rule").
- Greeting name: `get_full_name`, falling back to `username`, the convention already used in `my_attendance*.html`. No first-name guessing.
- **Accepted in TDB-1 (supersedes the TDB-0 wording):** the greeting is the single visible page `<h1>`. The visible "My day" heading was removed. "My day" and "Today" remain only as the document title and navigation label (`core:my-home`, tab **Today**).

### 2. Today overview

Two compact tiles side by side on mobile (they stay two columns at 360px; content wraps, never overflows). Each tile is one tap target to an existing page. Each tile has one dominant element (the state), one secondary line, no second control.

**Attendance tile.** Scope: only current class-teacher responsibilities (`class_teacher_assignments(user, today)`).

| State | When | Secondary line | Link target |
|---|---|---|---|
| Not taken | at least one class register missing on an instructional day | "Grade 6-A" or "N classes" | `core:my-attendance` for the one Section, or the Attendance list below when several |
| Draft | register open, not submitted | Section | `core:my-attendance` |
| Submitted | register submitted | Section | `core:my-attendance` |
| Not required | no class-teacher duty today, or the date is not an instructional day for that duty's year | "Not a school day" or "No class assigned" | none (non-interactive, no pill/button affordance) |

**Link behaviour.**
- Exactly one class-teacher Section: the tile is a single direct link to `core:my-attendance` for that Section.
- Several class-teacher Sections: the tile is a **non-interactive summary** (no link, no button affordance). It shows the most urgent state (Not taken, then Draft, then Submitted) with real counts ("2 of 3 submitted"). Section-specific actions (Take attendance, Continue, View) live in **compact detail rows** directly beneath the overview, one row per Section, each linking to `core:my-attendance` for that Section.
- Wording of states reuses `AttendanceRegister.AttendanceState` and today's pill text.

**Marks tile.** Scope: current subject-teacher responsibilities across all Classes and Sections (`current_teacher_assignments(user, today)`), via the existing `_open_assessments_needing_marks` behaviour, unchanged: Assessment status DRAFT, assessment date on or before today, at least one unmarked roster entry. Future-dated assessments are not "waiting".

**Wording rule.** The sum of `unmarked_count` over assessments counts *marks*, not students: one Student can be unmarked in several assessments. The tile therefore says "N marks remaining across M assessments" (or "N marks remaining" for one assessment) and never "N students". A per-assessment "N unmarked" is acceptable because it is within one roster.

| State | When | Secondary line | Link target |
|---|---|---|---|
| N marks remaining | at least one assessment still needs marks | "across M assessments" | `core:assessment-marks-entry` when M = 1, otherwise `core:my-assessments` |
| Nothing waiting | subject-teacher duty exists, no assessment waits | "No open assessments are waiting" | `core:my-assessments` |
| Not required | no current subject assignment | "No subjects assigned" | none |

### 3. Today's timetable — implemented in TDB-5 (ADR 0021)

- Sits immediately after Today overview once it exists. Period-based, not time-first. Target format:

  ```
  P1  Grade 6-A · Mathematics
  P2  Grade 7-B · Mathematics
  P3  Grade 8-A · Science
  ```
- **At TDB-0 the repo had no timetable or period domain model** (no Period, Slot, Timetable or Routine model; `AssessmentTeacherAssignment` states it "is not a timetable, workload, substitution or HR record"). A timetable needs proper domain design and admin setup first (gates TDB-3 and TDB-4), then integration (TDB-5). All three have since shipped.
- **TDB-3 decision (ADR 0021, Accepted):** `TimetablePeriod` (per Academic Year; only `sequence` and `label` like P1, no clock times) and effective-dated `TimetableSlot` (period, weekday, Section, `AcademicSubjectOffering`). The teacher is **derived** from the existing ADR 0018 assignment, not stored, so the timetable never becomes a second authorization source. TDB-5 reads today's slots for the teacher's current assignments, ordered by period, on instructional days only, with no free-period or placeholder rows. When the day is instructional, a timetable exists and the teacher has no row, the section shows "No periods scheduled for you today."; with no timetable configured, or on a non-instructional day, the section is hidden. This section changes if ADR 0021 changes.
- Before TDB-5 the dashboard rendered no timetable section, placeholder rows or "coming soon" card; TDB-5 now renders the section as described above. Never derive periods from assignments, class order or any heuristic. Never show fake rows.

### 4. Teaching assignments (major section)

Two clearly separated groups, both built from effective-dated rows for the business date:

- **Class teacher** — `class_teacher_assignments(user, today)` (ADR 0011). One row per Section: "Grade 6-A", with the Academic Year as secondary text. Empty text: "You are not a class teacher today."
- **Subjects I teach** — `current_teacher_assignments(user, today)` (ADR 0018). One row per Section + Subject: "Grade 7-B · Mathematics", grouped by Section or by Subject (choose in TDB-2 against real data; no extra query per row). Empty text: "No subjects are assigned to you today."

A teacher may be class teacher of one Section and subject teacher for several others; the two groups are independent and a Section may legitimately appear in both. No merging, no "primary role" inference. **Row links.** A row is a link only where an existing URL gives an unambiguous destination for that row. Today that means: a Class teacher row may link to `core:my-attendance` for its Section (that URL is Section-specific). Subjects I teach rows are **plain text**: no existing teacher URL is specific to a Section + Subject (`core:my-students` and `core:my-assessments` take no Section parameter), and a link to them would falsely imply a Section-specific destination. A Section-specific destination for these rows would be new URL work and is out of scope for TDB-2. Empty-state copy points to the school office, as today.

### 5. Term remarks (optional, secondary)

- Lowest visual priority, last on the page, compact (single-line rows, no card per row if avoidable).
- **TDB-2 must not change Term selection or any TermRemark domain semantics.** It keeps the existing eligible terms (every started Term for each current class-teacher Section, per the current `my_home` logic) and the existing real counts (written versus expected, e.g. "12 of 32 written"), linking to `core:term-remarks` as today. Only its visual priority is reduced (compact rows, secondary position). Any filtering of terms is a separate, later decision.
- Hidden entirely when there is nothing to show. The `<progress>` bar is a real-count bar and is allowed by the "truthful, earned progress" rule, but TDB-2 may replace it with plain text to keep the section quiet.

## Header status rule (School day / Not a school day)

Truth source: `AcademicYear.is_instructional_day(date)` (weekly pattern plus `SchoolCalendarDay` exceptions, ADR 0008). There is **no global current Academic Year**; `business_today()` is a bare date. So the status is derived from the teacher's own context only:

1. Collect the distinct Academic Years of the teacher's current class-teacher rows and current subject assignments (`offering.academic_year`).
2. Exactly one year: show "School day" or "Not a school day" from `is_instructional_day(today)`.
3. No year (no assignments), or years that disagree: **show no status.** Do not guess, do not default to "School day", do not look up an unrelated year.

This feature does **not** introduce a global or school-level "current Academic Year". The status is hidden whenever it cannot be truthfully derived from the teacher's assignment context.

The Attendance tile's "Not required" state uses the same per-duty check as today's page and stays consistent with the header.

## Reuse versus new work (inspection of baseline `0a3a947`)

| Area | Reusable as is | Needs new work |
|---|---|---|
| `core/views.py::my_home` | Class-teacher duties, per-Section register state with `is_instructional_day` (3 states plus NOT_INSTRUCTIONAL), `_open_assessments_needing_marks` (constant queries, unmarked counts), term remarks roster logic (`term.section_rosters`), `business_today()` | A summary reduction of the attendance rows into one tile state; sums for the Marks tile; the header-status derivation; a Subjects-I-teach query (`current_teacher_assignments` already exists and is select_related-ready); greeting name |
| `core/authorization.py` | `class_teacher_assignments`, `current_teacher_assignments`, `is_teacher`, `teacher_required` | Nothing |
| `core/models.py` | `SectionClassTeacher`, `AssessmentTeacherAssignment`, `AcademicYear.is_instructional_day`, `TermRemark` | **Timetable / Period model: did not exist at TDB-0**; added by TDB-4A under ADR 0021 |
| `core/templates/core/my_home.html` | Wrapper `.erp-day`, `.erp-card`, `.erp-pill` states, `partials/_empty.html`, stretched-link marks cards, remarks link card | Restructure into header, two tiles, assignments groups. The large Attendance cards and "Marks to enter" list are transitioned away (see "End state") |
| `core/navigation.py` | `teacher_tabs`, `TEACHER_TAB_PARENTS` (attendance pages map to `my-home`) | Unchanged |
| `static/css/erp.css` | `.erp-teacher .erp-day*` rules, `.erp-pill` variants, `.erp-progress`, tokens | A two-column tile grid, header status styles, compact assignment rows; all scoped under `.erp-teacher` |
| Tests | `test_phase5_teacher_home.py` (state, scope, hand-over, lost status, query count `test_queries_do_not_grow_with_duties`), `test_ui_teacher_daily.py`, `test_ui_teacher_polish.py` (My day heading and date kept, section dominant) | New tests per gate for tile states, header rule (single year / none / disagreeing years), the two assignment groups, and a query-count guard |

Existing tests that assert the current My day markup (card titles, "Marks to enter", "Not a class teacher today") will need deliberate updates in the gate that changes that markup. Authorization behaviour must not change.

## End state: no duplicated large sections

The two tiles are the dashboard's Attendance and Marks summary. The existing large "Attendance" card list and "Marks to enter" assessment list are **not** kept permanently underneath the overview.

- **TDB-1 may transition them** (for example keep them temporarily, or reduce them to compact rows) so the gate stays small and reviewable.
- **Final state (by TDB-2/TDB-6):** any needed detail is either (a) compact rows (Section-specific attendance actions when there are several Sections), or (b) left to the existing destination pages (`core:my-attendance`, `core:my-attendance-history`, `core:my-assessments`, `core:assessment-marks-entry`). No second, full-size copy of the same information below the tiles.
- Existing tests that assert the old card markup are updated deliberately in the gate that changes it. No authorization or business-rule change.

## Proposed gates

| Gate | Scope | Domain / migration? |
|---|---|---|
| **TDB-0** | This design / spec freeze | No |
| **TDB-1** | Header plus Today overview from existing data | No |
| **TDB-2** | Teaching assignments section, plus optional compact Term remarks | No |
| **TDB-3** | Timetable / period domain design: `docs/adr/0021-timetable-periods-and-weekly-slots.md` (Accepted 2026-10-18). Substitutions, special days, exams, rooms, electives, year copy deferred | Design only |
| **TDB-4** | Timetable office setup as outlined in ADR 0021: models and migration, permissions for School Administrators, period list and per-Section weekly grid, integrity rules R1-R7, conflicts report, tests | Yes (migration) |
| **TDB-5** | Today's timetable dashboard integration, period-based | No new models |
| **TDB-6** | Responsive, accessibility and final verification at 360/390px, JS off, focus, 44px targets | No |

Each gate ships separately and is reviewed before the next starts. TDB-1 and TDB-2 must not edit models, migrations, URLs or authorization.

## Acceptance (applies to TDB-1, TDB-2, TDB-6)

- No horizontal page scroll at 360px and 390px; tiles stay side by side at 360px.
- Every interactive element at least 44x44 with visible `:focus-visible`; tiles with no action are not styled as tappable.
- Each state has text, not only colour.
- JS off: everything renders and works.
- No timetable section or fake rows anywhere before TDB-5 (TDB-5 shipped the real section; fake rows remain forbidden).
- Query count does not grow with the number of assignments (extend the existing guard).

## Review decisions (resolved)

1. Header status is hidden when it cannot be truthfully derived from the teacher's assignment context; no global current Academic Year is introduced.
2. Attendance tile: one Section, direct link; several Sections, non-interactive summary with compact per-Section detail rows. Marks tile: My assessments when several assessments, the marks entry page when exactly one.
3. Marks scope is the existing `_open_assessments_needing_marks` behaviour (DRAFT, date on or before today, at least one unmarked roster entry); future assessments are not waiting. Aggregate wording counts marks, not students.
4. TDB-2 does not change Term selection or TermRemark semantics; it only lowers the section's visual priority. Filtering terms is a later, separate decision.
5. Old large Attendance and Marks sections are transitioned away; see "End state".
6. Teaching-assignment rows link only where an existing URL is unambiguous; Subjects I teach rows are plain text.

## Note

The local `ui/teacher-dashboard` branch was created tracking `origin/main`; it now tracks `origin/ui/teacher-dashboard`. Always push with an explicit remote branch name.
