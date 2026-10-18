# TDB-0 Teacher Dashboard — Design / Spec Freeze

**Date:** 2026-10-18
**Baseline:** `main` at `0a3a947`
**Status:** Proposed. Documentation only; no code, template, CSS, model or test changes.
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
- The page `<h1>` stays "My day" (U3.1 rule: headings keep their long label while the tab says Today). The greeting is a line below it, not a second h1.

### 2. Today overview

Two compact tiles side by side on mobile (they stay two columns at 360px; content wraps, never overflows). Each tile is one tap target to an existing page. Each tile has one dominant element (the state), one secondary line, no second control.

**Attendance tile.** Scope: only current class-teacher responsibilities (`class_teacher_assignments(user, today)`).

| State | When | Secondary line | Link target |
|---|---|---|---|
| Not taken | at least one class register missing on an instructional day | "Grade 6-A" or "N classes" | `core:my-attendance` for the one Section, or the Attendance list below when several |
| Draft | register open, not submitted | Section | `core:my-attendance` |
| Submitted | register submitted | Section | `core:my-attendance` |
| Not required | no class-teacher duty today, or the date is not an instructional day for that duty's year | "Not a school day" or "No class assigned" | none (non-interactive, no pill/button affordance) |

With several class-teacher Sections the tile shows the most urgent state (Not taken, then Draft, then Submitted) with real counts ("2 of 3 submitted"). Per-Section rows stay available on the page (see "Reuse"). Wording of states reuses `AttendanceRegister.AttendanceState` and today's pill text.

**Marks tile.** Scope: current subject-teacher responsibilities across all Classes and Sections (`current_teacher_assignments(user, today)`), via the existing `_open_assessments_needing_marks` rule (DRAFT, date not after today, at least one roster Student unmarked).

| State | When | Secondary line | Link target |
|---|---|---|---|
| N unmarked | at least one assessment still needs marks | "N students across M assessments" if both are real sums of `unmarked_count` and the list length | `core:assessment-marks-entry` for a single assessment, otherwise `core:my-assessments` |
| Nothing waiting | subject-teacher duty exists, no assessment waits | "No open assessments are waiting" | `core:my-assessments` |
| Not required | no current subject assignment | "No subjects assigned" | none |

### 3. Today's timetable — FUTURE GATE, not built in TDB-1/2

- Sits immediately after Today overview once it exists. Period-based, not time-first. Target format:

  ```
  P1  Grade 6-A · Mathematics
  P2  Grade 7-B · Mathematics
  P3  Grade 8-A · Science
  ```
- **The repo has no timetable or period domain model** (no Period, Slot, Timetable or Routine model; `AssessmentTeacherAssignment` states it "is not a timetable, workload, substitution or HR record"). A timetable needs proper domain design and admin setup first (gates TDB-3 and TDB-4), then integration (TDB-5).
- Until TDB-5 ships the dashboard renders **no timetable section, no placeholder rows and no "coming soon" card**. Never derive periods from assignments, class order or any heuristic. Never show fake rows.

### 4. Teaching assignments (major section)

Two clearly separated groups, both built from effective-dated rows for the business date:

- **Class teacher** — `class_teacher_assignments(user, today)` (ADR 0011). One row per Section: "Grade 6-A", with the Academic Year as secondary text. Empty text: "You are not a class teacher today."
- **Subjects I teach** — `current_teacher_assignments(user, today)` (ADR 0018). One row per Section + Subject: "Grade 7-B · Mathematics", grouped by Section or by Subject (choose in TDB-2 against real data; no extra query per row). Empty text: "No subjects are assigned to you today."

A teacher may be class teacher of one Section and subject teacher for several others; the two groups are independent and a Section may legitimately appear in both. No merging, no "primary role" inference. Rows are informational by default; link a row only to an existing page that already accepts it (for example My students for the Section) and only if one link per row stays unambiguous. Empty-state copy points to the school office, as today.

### 5. Term remarks (optional, secondary)

- Lowest visual priority, last on the page, compact (single-line rows, no card per row if avoidable).
- Content is today's truthful data only: `TermRemark` written count versus the expected roster count per started Term and class-teacher Section ("12 of 32 written"), linking to `core:term-remarks`.
- Hidden entirely when there is nothing to show. The `<progress>` bar currently used is a real-count bar and is allowed by the "truthful, earned progress" rule, but TDB-2 may drop it for plain text to keep this section quiet.

## Header status rule (School day / Not a school day)

Truth source: `AcademicYear.is_instructional_day(date)` (weekly pattern plus `SchoolCalendarDay` exceptions, ADR 0008). There is **no global current Academic Year**; `business_today()` is a bare date. So the status is derived from the teacher's own context only:

1. Collect the distinct Academic Years of the teacher's current class-teacher rows and current subject assignments (`offering.academic_year`).
2. Exactly one year: show "School day" or "Not a school day" from `is_instructional_day(today)`.
3. No year (no assignments), or years that disagree: **show no status.** Do not guess, do not default to "School day", do not look up an unrelated year.

The Attendance tile's "Not required" state uses the same per-duty check as today's page and stays consistent with the header.

## Reuse versus new work (inspection of baseline `0a3a947`)

| Area | Reusable as is | Needs new work |
|---|---|---|
| `core/views.py::my_home` | Class-teacher duties, per-Section register state with `is_instructional_day` (3 states plus NOT_INSTRUCTIONAL), `_open_assessments_needing_marks` (constant queries, unmarked counts), term remarks roster logic (`term.section_rosters`), `business_today()` | A summary reduction of the attendance rows into one tile state; sums for the Marks tile; the header-status derivation; a Subjects-I-teach query (`current_teacher_assignments` already exists and is select_related-ready); greeting name |
| `core/authorization.py` | `class_teacher_assignments`, `current_teacher_assignments`, `is_teacher`, `teacher_required` | Nothing |
| `core/models.py` | `SectionClassTeacher`, `AssessmentTeacherAssignment`, `AcademicYear.is_instructional_day`, `TermRemark` | **Timetable / Period model: does not exist** (TDB-3) |
| `core/templates/core/my_home.html` | Wrapper `.erp-day`, `.erp-card`, `.erp-pill` states, `partials/_empty.html`, stretched-link marks cards, remarks link card | Restructure into header, two tiles, assignments groups; today's per-Section Attendance cards and "Marks to enter" list become detail rows below the overview rather than the whole page |
| `core/navigation.py` | `teacher_tabs`, `TEACHER_TAB_PARENTS` (attendance pages map to `my-home`) | Unchanged |
| `static/css/erp.css` | `.erp-teacher .erp-day*` rules, `.erp-pill` variants, `.erp-progress`, tokens | A two-column tile grid, header status styles, compact assignment rows; all scoped under `.erp-teacher` |
| Tests | `test_phase5_teacher_home.py` (state, scope, hand-over, lost status, query count `test_queries_do_not_grow_with_duties`), `test_ui_teacher_daily.py`, `test_ui_teacher_polish.py` (My day heading and date kept, section dominant) | New tests per gate for tile states, header rule (single year / none / disagreeing years), the two assignment groups, and a query-count guard |

Existing tests that assert the current My day markup (card titles, "Marks to enter", "Not a class teacher today") will need deliberate updates in the gate that changes that markup. Authorization behaviour must not change.

## Proposed gates

| Gate | Scope | Domain / migration? |
|---|---|---|
| **TDB-0** | This design / spec freeze | No |
| **TDB-1** | Header plus Today overview from existing data | No |
| **TDB-2** | Teaching assignments section, plus optional compact Term remarks | No |
| **TDB-3** | Timetable / period domain design (ADR): periods, slots, effective dating, relation to class teacher and subject assignments, substitution out of scope unless decided | Design only |
| **TDB-4** | Timetable admin setup (office screens, validation, permissions, tests) | Yes (migration) |
| **TDB-5** | Today's timetable dashboard integration, period-based | No new models |
| **TDB-6** | Responsive, accessibility and final verification at 360/390px, JS off, focus, 44px targets | No |

Each gate ships separately and is reviewed before the next starts. TDB-1 and TDB-2 must not edit models, migrations, URLs or authorization.

## Acceptance (applies to TDB-1, TDB-2, TDB-6)

- No horizontal page scroll at 360px and 390px; tiles stay side by side at 360px.
- Every interactive element at least 44x44 with visible `:focus-visible`; tiles with no action are not styled as tappable.
- Each state has text, not only colour.
- JS off: everything renders and works.
- No timetable section or fake rows anywhere before TDB-5.
- Query count does not grow with the number of assignments (extend the existing guard).

## Questions / conflicts for review

1. **No global "current year".** The header status is therefore derived only from the teacher's assignments and is hidden when none or when years disagree. Confirm this is acceptable, or decide whether a school-level "current Academic Year" concept should be designed separately (out of scope here).
2. **Tile link with several targets.** When a teacher is class teacher of several Sections, or has several assessments waiting, the tile links to a list rather than a single page. Confirm the list target (the per-Section rows remain on the page) is preferred over adding a new aggregate page.
3. **Marks tile "Not required" versus the full assessment list.** The tile counts only DRAFT assessments dated on or before today with unmarked students, per the existing rule. Assessments scheduled for later are not "waiting". Confirm that is the intended meaning.
4. **Term remarks scope.** The existing logic lists every started Term for each class-teacher Section, including past Terms. Confirm TDB-2 may limit it to the Term containing today (or drop the section) without changing remark rules.
5. **Current page content.** Today's per-Section attendance cards and Marks list are fuller than the tiles. This spec keeps them as detail beneath the overview. Confirm that, rather than replacing them with tiles only, matches the intent of "compact dashboard".
6. **Branch tracking.** The local `ui/teacher-dashboard` branch was created tracking `origin/main`. Pushing must name the remote branch explicitly.
