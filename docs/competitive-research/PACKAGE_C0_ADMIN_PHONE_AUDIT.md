# Package C0: Admin Phone Coverage Audit

- **Status:** Audit (documentation only). It approves no code change. The build plan is in
  `PACKAGE_C_IMPLEMENTATION_SPEC.md`.
- **Gap:** G-04 (ADM-08, MOB-01), ranked first in `OPTION_A_B_BENCHMARK_CLOSEOUT.md` §4–5.
- **Checked against:** `main` at `16e2341` (23 November 2026).
- **Method:** every administrator page loaded in headless Chromium at **360 px** and **390 px**
  (phone emulation, touch on) and at **1366 px** (desktop regression check), signed in as the demo
  administrator. Data came from a throwaway local Postgres database seeded with
  `seed_school_demo`, `seed_school_demo_extras` and `seed_school_demo_results` (110 students,
  10 teachers, 182 assessments, 333 timetable slots), plus one draft assessment and one draft
  register. Staging was not used. Each page was measured by script (§6), and the worst pages
  were also checked by eye from screenshots.
- **Not a real-device test.** Emulated Chromium only. Safari, Android browsers and real phones
  were not used.

## 1. Summary

What was checked, and how far each check went:

| Check | Coverage |
| --- | --- |
| **Page rendering and layout measurement** | **142 admin routes** loaded at 360, 390 and 1366 px. All of them rendered a page (HTTP 200): 126 their own page and 16 a redirect target. |
| **Workflows completed** (forms submitted) | **3 workflows**, at 360 px only: submit an attendance register, accept an applicant, preview and publish an announcement. |
| **Inspected from templates** | Pages whose tables were empty in the demo data (access reviews, stale publications, bulk imports); judged from the template markup. |
| **Not functionally exercised** | Every other page. They were rendered and measured, but their forms and actions were not submitted. "Works" in the inventory means no layout problem was found, not that the workflow was completed. |

- **No page scrolls sideways** at 360, 390 or 1366 px. Earlier work fixed page-level overflow
  everywhere (the `.erp-content table` phone rule, phone cards, the drawer).
- **No blocker was found in what was exercised.** The three workflows above finished without
  problems. The drawer has all 22 desktop sidebar links, each at least 40 px tall.
- **The remaining problem is inside tables.** On 12 pages a table scrolls inside its own box
  and hides the column that matters: the section that tells assessments apart, the marks on a
  report card, or the row's action button. Nothing on screen says more is to the right.
- After removing duplicates there are **9 findings**: 2 High (C0-01, C0-02), 4 Medium (C0-03 to
  C0-06) and 3 Low (C0-07 to C0-09). Some Medium findings have Low parts, and C0-02 has one
  Medium part.

| Status (at 360 px) | Routes | Meaning |
| --- | --- | --- |
| Works | 101 | No layout problem found (rendered and measured; not functionally exercised unless listed above). |
| Usable | 13 | Only Low findings. |
| Problem | 12 | At least one High or Medium finding. |
| Redirects | 16 | The URL is a POST action, needs a precondition, or is the home redirect. The page it lands on is counted. |

**Functional blockers vs visual inconvenience.** No finding stops a task that was exercised. The two High findings are
functional all the same: on a phone an administrator can open the wrong assessment (C0-01), or
can't see the marks they're checking or the Correct action (C0-02). Medium findings slow a task
down or hide a secondary action. Low findings are visual only.

## 2. Severity scale

| Level | Rule |
| --- | --- |
| **High** | The value or action the page exists for is off screen on a phone with no cue, so the administrator may act on the wrong record, or may think the action doesn't exist. |
| **Medium** | The task can be finished, but a row action or important data needs sideways scrolling inside a table; or the page needs heavy scrolling with no way to jump; or a control is below the 24 × 24 px minimum (WCAG 2.2 SC 2.5.8). |
| **Low** | Visual only: wrapping, tall rows, small read-only columns cut off, long but readable pages. |

## 3. Findings

Measurements are at 360 px; the figure in brackets is the same table at 390 px. "Hidden" means
the width of table content to the right of the visible box.

### C0-01 High: assessment rows can't be told apart on phones

- **Route:** `core:academic-year-assessments` (`core/templates/core/assessment_list.html`).
- **What happens:** the 8-column table shows only Assessment, Status and part of Subject. Section,
  Date, Term, Max and Pass are hidden (413 px [383 px]). In real data most rows read "Unit Test 1 ·
  Finalized · Computer Scien…", so the row you tap is a guess.
  Screenshot: `docs/ui-reviews/package-c0/assessments-list-360.png`.
- **Why High:** this list is the entry point for marks, finalizing, the result sheet and
  correction. Opening the wrong section's assessment leads to work on the wrong record.
- **Also here:** the filter form is 466 px tall (C0-05), so the first row starts below the first
  screen.

### C0-02 High: result tables hide the marks and the Correct action

One shared cause on four pages: a results table with 5–8 columns puts the student or subject first
and the value last, then falls back to scrolling inside its box on phones.

| Page | Template | Hidden at 360 px [390] | What is lost | Level |
| --- | --- | --- | --- | --- |
| Assessment detail (finalized) | `assessment_detail.html` | 421 [391] px | Score cut off ("72.00 / 100."), %, Grade, Pass/Fail, Entered by, and the **Correct** link on every row | High |
| Assessment detail (draft) | same | 300 [270] px | %, Grade, Pass/Fail, Entered by | High (same template) |
| Term report card | `report_term_report_card.html` | 238–275 [208–245] px × 5 tables | Marks cut off ("22.00 / 25.0"), %, Grade, Pass/Fail for every subject | High |
| Published report card | `publication_detail.html` | 389 [359] px, plus 266 [236] px | Date, Marks, %, Grade, Pass/Fail; version history columns. The office reviews this page before it republishes or withdraws. | High |
| Result sheet | `report_result_sheet.html` | 132 [102] px | Grade, Pass/Fail | Medium |

Screenshots: `assessment-detail-360.png`, `report-card-and-publication-360.png`.

**Why High:** the marks are the reason these pages exist, and correcting a result starts from the
hidden Correct link. The workflow can be finished by scrolling the table sideways, but nothing
says to.

### C0-03 Medium: row actions sit in an off-screen last column

Same root cause as C0-02 (action column last, phone scroll fallback), on non-result tables:

| Page | Template | Hidden | What is lost |
| --- | --- | --- | --- |
| Academic year calendar | `academic_year_calendar.html` | 211 [181] px | Type (partly), Label and the Edit/Delete links (8 rows in the demo) |
| Student record, Guardians table | `student_detail.html` | 143 [113] px | "Change relationship" and "End" for each guardian ("Change" is cut at the edge, "End" is fully hidden). Screenshot `student-detail-360.png`. |
| Guardian access reviews | `guardian_access_reviews.html` | 110 [80] px | Last placement and the **Decision** form (select + Record) |
| Stale publications | `publications_stale.html` | 25 px + Review column | Reason (partly) and the **Review** link |

The demo had no pending access reviews or stale publications, so those two were measured with
empty tables and read from the template (`guardian_access_reviews.html:11-29`,
`publications_stale.html:9-27`). Expect the action column to be fully off screen once there is
data.

### C0-04 Medium: very long assignment pages with no way to jump

| Page | Template | Page height at 390 px | Notes |
| --- | --- | --- | --- |
| Teacher assignments | `teacher_assignments.html` | **20,553 px** (91 cards) | One card per Subject/Section slot, about 220 px each; no filter, grouping or jump. A school with 30 sections and 8 subjects would have about 240 cards (over 50,000 px). Medium. |
| Class teachers | `academic_year_class_teachers.html` | 3,710 px | 15 sections; readable. Low. |
| Assignment overview | `academic_year_assignments.html` | 9,899 px | Read-only overview, compact cards. Low. |

The cards themselves are good on phones (`teacher-assignments-360.png`). The problem is finding
one slot.

### C0-05 Medium: filter forms take the first screen on lists

Phone viewport used: 780 px tall. Filter heights:

| Page | Filter height | Effect | Level |
| --- | --- | --- | --- |
| Assessments | 466 px | First result starts about 700 px down | Medium (fixed with C0-01) |
| Attendance registers | 422 px | First register card at about 710 px (`attendance-list-filters-360.png`) | Medium |
| Offerings, Student attendance | 246 px | | Low |
| Students | 236 px | | Low |
| Timetable issues | 230 px | | Low |
| Applicants, Announcements | 215 px | | Low |

Report pages whose filter *is* the entry form (Subject/Section results, Missing attendance,
Monthly, Attendance summary, Report cards; 158–334 px) aren't counted: nothing is shown until
you choose.

### C0-06 Medium (part Low): small tap targets

- **Medium:** student record pencil links for admission number (23 × 19 px) and roll number
  (21 × 17 px) (`student_detail.html`). Both are below the 24 × 24 px minimum and sit next to text.
- **Low:** text links inside table rows are 21 px tall (assessment rows, class list, applicants,
  register names, assignment overview, 106 on one page). Rows are at least 44 px tall and links
  don't crowd each other, so the WCAG spacing exception applies.
- **Low:** class detail puts "Rename" and red "Archive" side by side as 52 × 21 px links. Archive
  opens a confirmation page, so a mis-tap does no damage.

### C0-07 Low: wrapping

- Admin home: the primary button "Open Applicants awaiting decision" wraps to three lines (87 px).
- Grading scales: "Applies to" stacks ten grade names (a 265 px row) and the Grade bands column
  is cut off (62 [32] px) (`grading-scales-360.png`).

### C0-08 Low: secondary read-only tables cut off

- Teacher detail, security events: When and By hidden (168 [138] px).
- Bulk imports list: Academic year, Students and Status hidden (185 [155] px). The demo had no
  batches. Status matters once imports exist, but bulk import is an occasional office job.

### C0-09 Low (to confirm): section shortcut strip on the student record

The strip under the student's name ("Change status · Status history · Current pl…") is cut at
the right edge. The screenshot doesn't show whether it scrolls. Confirm in the PR that touches
`student_detail.html`.

## 4. Shared root causes

| Root cause | Findings | Fix direction (details in the spec) |
| --- | --- | --- |
| **R1. Wide tables fall back to in-box scrolling** (`static/css/erp.css:1324-1331`). That rule prevents page overflow, but on 12 pages it hides the key value or the action column, with no visual cue. | C0-01, C0-02, C0-03, C0-07 (grading), C0-08 | Give each affected table a phone layout that shows every column without sideways scrolling: one stacked-row table pattern, or phone cards as on Students. |
| **R2. Filter forms are one field per row on every width.** | C0-05 | Compact the filter layout on phones. |
| **R3. Long lists have no grouping or jump on phones.** | C0-04 | Group by Class/Grade with collapsible sections, as `academic_year_class_teachers.html` already does. |
| **R4. Inline icon links have no minimum size.** | C0-06 | Give the pencil links a 24 × 24 px minimum. |

R1 accounts for both High findings and most Medium ones, so it is the main lever.

## 5. What already works (keep unchanged)

- Shell and navigation: menu button on every page, drawer with full desktop link parity, no drawer
  overflow (`templates/base.html:18`, `templates/partials/_sidebar.html`).
- Phone cards on: Students, Teachers, Guardians, Attendance registers, Announcements, Academic years
  and terms, Class teachers, Teacher assignments, Assignment overview, Assignment copy.
- Attendance capture at 360 px: full-width Present/Absent buttons, sticky Save draft / Save and
  submit bar. Submitting a whole register worked.
- Timetable grid: day tabs, one period per row, Change/End/Add slot buttons at touch size.
- Every form page (create, edit, rename, confirm, end, revoke, reset): single column, no overflow,
  no control below 24 px.
- Desktop at 1366 px: no page overflows.

## 6. Method details and limits

**Metrics, per page and width:**

- page overflow: `scrollWidth − clientWidth` of the document;
- elements past the right edge that are not inside a scroll box;
- each visible table: column count, whether it scrolls, hidden width, and the header labels of
  columns that start outside the visible box;
- visible interactive controls under 24 px in either dimension (ignoring links inside paragraphs,
  checkboxes and radios), and under 40 px tall;
- buttons and headers taller than about 2.5 lines (excessive wrapping);
- height of the first GET form (filters) and of the whole page;
- buttons visible at 1366 px but not at 360 px (hidden actions). The only hit was the timetable
  grid, where the day tabs hold the other days' buttons; it was checked by eye and is not a
  defect.

**Exercised with form submission at 360 px:** attendance register submit, applicant accept, and
announcement preview + publish. All succeeded, with no overflow on the result pages.

**Not exercised:**

- import batch detail/preview, issued-document PDFs and CSV/XLSX downloads (no batches or
  documents in the demo; downloads aren't pages);
- a populated notification queue, access reviews or stale publications (judged from templates);
- teacher-area and guardian-portal routes (outside admin scope), Django admin, and the
  login/logout pages owned by the framework (the login page was redesigned and checked in
  #145/#269);
- real devices, iOS Safari, Android Chrome, landscape, and large text settings.

**Existing test coverage.** Phone behaviour is pinned by server-rendered markup tests
(`test_ui_student_phone_cards`, `test_ui_teacher_cards`, `test_ui_year_assignments_phone`,
`test_ui_year_cards`, `test_ui_student_history_phone`, `test_ui_guardian_attendance_phone`,
`test_ui_hamburger` and others). No test measures layout at phone width. The browser tests
under ADR 0028 cover JavaScript behaviour only and exclude template and visual testing
(`docs/adr/0028-javascript-behaviour-testing.md:76`).

**Evidence.** Seven screenshots are in `docs/ui-reviews/package-c0/`. They show only seeded demo
data (synthetic names). They show no passwords, session IDs, CSRF tokens or developer tools. The
demo administrator's username appeared in two of them (Finalized by / Published by), and it is
blacked out. The full screenshot set (284 images), raw measurements and the one-off audit scripts
are not committed (OD-C6). This report and the route inventory are the lasting evidence. The
throwaway audit database was dropped after the audit.

## 7. Route inventory

Columns: HTTP status at 360 / 390 / 1366 px (a `!` would mark page overflow; there is none), the
status from §1, and the finding. The path is the URL checked with demo IDs.

#### Home and navigation

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `root:home` | `/` | 200 / 200 / 200 | Redirects to Overview (admin home) | -  |
| `core:admin-overview` | `/overview/` | 200 / 200 / 200 | Usable | C0-07 (L) |
| `root:choose-area` | `/choose-area/` | 200 / 200 / 200 | Redirects to Overview (single-role admin) | - |
| `root:password_change` | `/accounts/password/change/` | 200 / 200 / 200 | Works | - |
| `root:pwa-install` | `/install/` | 200 / 200 / 200 | Works | - |

#### School setup

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:school-detail` | `/school/` | 200 / 200 / 200 | Works | - |
| `core:school-update` | `/school/edit/` | 200 / 200 / 200 | Works | - |
| `core:school-logo-remove` | `/school/logo/remove/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-list` | `/academic-years/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-create` | `/academic-years/create/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-terms` | `/academic-years/1/terms/` | 200 / 200 / 200 | Works | - |
| `core:term-create` | `/academic-years/1/terms/add/` | 200 / 200 / 200 | Works | - |
| `core:term-update` | `/terms/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-calendar` | `/academic-years/1/calendar/` | 200 / 200 / 200 | Problem | C0-03 (M) |
| `core:calendar-day-create` | `/academic-years/1/calendar/add/` | 200 / 200 / 200 | Works | - |
| `core:calendar-day-update` | `/calendar-days/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:calendar-day-delete` | `/calendar-days/1/delete/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-saturday-rule` | `/academic-years/1/calendar/saturdays/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:academic-year-offerings` | `/academic-years/1/subjects/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:offering-create` | `/academic-years/1/subjects/add/` | 200 / 200 / 200 | Works | - |
| `core:offering-update` | `/subject-offerings/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-grading-scales` | `/academic-years/1/grading-scales/` | 200 / 200 / 200 | Usable | C0-07 (L) |
| `core:grading-scale-create` | `/academic-years/1/grading-scales/add/` | 200 / 200 / 200 | Works | - |
| `core:grading-scale-detail` | `/grading-scales/1/` | 200 / 200 / 200 | Works | - |
| `core:grading-scale-update` | `/grading-scales/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:grade-boundary-create` | `/grading-scales/1/bands/add/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:grade-boundary-delete` | `/grade-bands/1/remove/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:class-grade-list` | `/classes/` | 200 / 200 / 200 | Works | - |
| `core:class-grade-create` | `/classes/create/` | 200 / 200 / 200 | Works | - |
| `core:class-grade-detail` | `/classes/1/` | 200 / 200 / 200 | Usable | C0-06 (L) |
| `core:class-grade-rename` | `/classes/1/rename/` | 200 / 200 / 200 | Works | - |
| `core:class-grade-archive` | `/classes/1/archive/` | 200 / 200 / 200 | Works | - |
| `core:section-create` | `/classes/1/sections/create/` | 200 / 200 / 200 | Works | - |
| `core:section-rename` | `/sections/1/rename/` | 200 / 200 / 200 | Works | - |
| `core:section-archive` | `/sections/1/archive/` | 200 / 200 / 200 | Works | - |
| `core:subject-list` | `/subjects/` | 200 / 200 / 200 | Works | - |
| `core:subject-create` | `/subjects/create/` | 200 / 200 / 200 | Works | - |
| `core:subject-update` | `/subjects/1/edit/` | 200 / 200 / 200 | Works | - |

#### Staffing

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:academic-year-class-teachers` | `/academic-years/1/class-teachers/` | 200 / 200 / 200 | Usable | C0-04 (L) |
| `core:class-teacher-assign` | `/academic-years/1/class-teachers/assign/` | 200 / 200 / 200 | Works | - |
| `core:class-teacher-end` | `/class-teachers/1/end/` | 200 / 200 / 200 | Works | - |
| `core:class-teacher-delete` | `/class-teachers/1/delete/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:academic-year-assignments` | `/academic-years/1/assignments/` | 200 / 200 / 200 | Usable | C0-04 (L) |
| `core:assignment-copy` | `/academic-years/1/assignments/copy/` | 200 / 200 / 200 | Works | - |
| `core:academic-year-teacher-assignments` | `/academic-years/1/teachers/` | 200 / 200 / 200 | Problem | C0-04 (M) |
| `core:teacher-assignment-create` | `/academic-years/1/teachers/add/` | 200 / 200 / 200 | Works | - |
| `core:teacher-assignment-end` | `/teacher-assignments/1/end/` | 200 / 200 / 200 | Works | - |
| `core:teacher-assignment-delete` | `/teacher-assignments/1/remove/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:teacher-list` | `/teachers/` | 200 / 200 / 200 | Works | - |
| `core:teacher-create` | `/teachers/new/` | 200 / 200 / 200 | Works | - |
| `core:teacher-detail` | `/teachers/2/` | 200 / 200 / 200 | Usable | C0-08 (L) |
| `core:teacher-load` | `/teachers/2/load/` | 200 / 200 / 200 | Works | - |
| `core:teacher-username` | `/teachers/2/username/` | 200 / 200 / 200 | Works | - |
| `core:teacher-reset-password` | `/teachers/2/reset-password/` | 200 / 200 / 200 | Works | - |
| `core:teacher-deactivate` | `/teachers/2/deactivate/` | 200 / 200 / 200 | Works | - |

#### Timetable

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:timetable-index` | `/timetable/` | 200 / 200 / 200 | Works | - |
| `core:timetable-periods` | `/academic-years/1/timetable/periods/` | 200 / 200 / 200 | Works | - |
| `core:timetable-period-create` | `/academic-years/1/timetable/periods/add/` | 200 / 200 / 200 | Works | - |
| `core:timetable-period-update` | `/timetable/periods/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:timetable-period-delete` | `/timetable/periods/1/delete/` | 200 / 200 / 200 | Works | - |
| `core:timetable-sections` | `/academic-years/1/timetable/sections/` | 200 / 200 / 200 | Works | - |
| `core:timetable-grid` | `/academic-years/1/timetable/sections/1/` | 200 / 200 / 200 | Works | - |
| `core:timetable-issues` | `/academic-years/1/timetable/issues/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:timetable-slot-change` | `/timetable/slots/1/change/` | 200 / 200 / 200 | Works | - |
| `core:timetable-slot-end` | `/timetable/slots/1/end/` | 200 / 200 / 200 | Works | - |
| `core:timetable-slot-delete` | `/timetable/slots/1/delete/` | 200 / 200 / 200 | Works | - |

#### Admissions and imports

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:applicant-list` | `/applicants/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:applicant-create` | `/applicants/create/` | 200 / 200 / 200 | Works | - |
| `core:applicant-detail` | `/applicants/111/` | 200 / 200 / 200 | Works | - |
| `core:applicant-edit` | `/applicants/111/edit/` | 200 / 200 / 200 | Works | - |
| `core:applicant-guardian-create` | `/applicants/111/guardians/add/` | 200 / 200 / 200 | Works | - |
| `core:applicant-admission-decision` | `/applicants/111/decision/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:applicant-decision-confirm` | `/applicants/111/decide/ACCEPTED/` | 200 / 200 / 200 | Works | - |
| `core:applicant-progress` | `/applicants/113/progress/` | 200 / 200 / 200 | Works | - |
| `core:import-list` | `/imports/` | 200 / 200 / 200 | Usable | C0-08 (L) |
| `core:import-upload` | `/imports/new/` | 200 / 200 / 200 | Works | - |

#### Students and guardians

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:student-list` | `/students/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:student-detail` | `/students/1/` | 200 / 200 / 200 | Problem | C0-03 (M), C0-06 (M), C0-09 (L) |
| `core:student-edit` | `/students/1/edit/` | 200 / 200 / 200 | Works | - |
| `core:student-admission-number` | `/students/1/admission-number/` | 200 / 200 / 200 | Works | - |
| `core:student-status-change` | `/students/1/status/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:student-deactivate-confirm` | `/students/1/deactivate/` | 200 / 200 / 200 | Works | - |
| `core:student-enroll` | `/students/1/enroll/` | 200 / 200 / 200 | Works | - |
| `core:student-attendance` | `/students/1/attendance/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:report-student-results` | `/students/1/results/` | 200 / 200 / 200 | Works | - |
| `core:report-term-report-card` | `/students/1/report-card/1/` | 200 / 200 / 200 | Problem | C0-02 (H) |
| `core:enrollment-roll-number` | `/enrollments/1/roll-number/` | 200 / 200 / 200 | Works | - |
| `core:student-guardian-add` | `/students/1/guardians/add/` | 200 / 200 / 200 | Works | - |
| `core:student-guardian-edit` | `/student-guardians/65/edit/` | 200 / 200 / 200 | Works | - |
| `core:student-guardian-end` | `/student-guardians/65/end/` | 200 / 200 / 200 | Works | - |
| `core:guardian-access-grant` | `/student-guardians/65/grant-access/` | 200 / 200 / 200 | Works | - |
| `core:guardian-list` | `/guardians/` | 200 / 200 / 200 | Works | - |
| `core:guardian-create` | `/guardians/create/` | 200 / 200 / 200 | Works | - |
| `core:guardian-detail` | `/guardians/208/` | 200 / 200 / 200 | Works | - |
| `core:guardian-edit` | `/guardians/208/edit/` | 200 / 200 / 200 | Works | - |
| `core:guardian-account-create` | `/guardians/159/account/create/` | 200 / 200 / 200 | Works | - |
| `core:guardian-account-link` | `/guardians/159/account/link/` | 200 / 200 / 200 | Works | - |
| `core:guardian-account-reset-password` | `/guardian-accounts/104/reset-password/` | 200 / 200 / 200 | Works | - |
| `core:guardian-account-revoke` | `/guardian-accounts/104/revoke/` | 200 / 200 / 200 | Works | - |
| `core:guardian-account-username` | `/guardian-accounts/104/username/` | 200 / 200 / 200 | Works | - |
| `core:guardian-access-revoke` | `/guardian-access/110/revoke/` | 200 / 200 / 200 | Works | - |
| `core:guardian-access-reviews` | `/guardian-access/reviews/` | 200 / 200 / 200 | Problem | C0-03 (M) |
| `core:guardian-access-review-decide` | `/guardian-access/110/review/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |

#### Attendance

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:attendance-register-list` | `/attendance/` | 200 / 200 / 200 | Problem | C0-05 (M) |
| `core:attendance-register-create` | `/attendance/create/` | 200 / 200 / 200 | Works | - |
| `core:attendance-register-detail` | `/attendance/136/` | 200 / 200 / 200 | Works | - |
| `core:attendance-register-detail#draft` | `/attendance/150/` | 200 / 200 / 200 | Works | - |
| `core:attendance-capture` | `/attendance/150/capture/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:attendance-register-submit` | `/attendance/150/submit/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:attendance-entry-correct` | `/attendance/entries/31/correct/` | 200 / 200 / 200 | Works | - |
| `core:attendance-reports` | `/attendance/reports/` | 200 / 200 / 200 | Works | - |
| `core:report-daily-absentees` | `/attendance/reports/absent/` | 200 / 200 / 200 | Works | - |
| `core:report-missing-attendance` | `/attendance/reports/missing/` | 200 / 200 / 200 | Works | - |
| `core:report-monthly-section` | `/attendance/reports/monthly/` | 200 / 200 / 200 | Works | - |
| `core:report-absence-runs` | `/attendance/reports/absent-in-a-row/` | 200 / 200 / 200 | Works | - |
| `core:attendance-summary` | `/documents/attendance/` | 200 / 200 / 200 | Works | - |

#### Assessments and results

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:academic-year-assessments` | `/academic-years/1/assessments/` | 200 / 200 / 200 | Problem | C0-01 (H), C0-05 (M) |
| `core:assessment-create` | `/academic-years/1/assessments/add/` | 200 / 200 / 200 | Works | - |
| `core:assessment-detail` | `/assessments/6/` | 200 / 200 / 200 | Problem | C0-02 (H) |
| `core:assessment-detail#draft` | `/assessments/184/` | 200 / 200 / 200 | Problem | C0-02 (H) |
| `core:assessment-update` | `/assessments/184/edit/` | 200 / 200 / 200 | Works | - |
| `core:assessment-delete` | `/assessments/184/delete/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:assessment-finalize` | `/assessments/184/finalize/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:report-result-sheet` | `/assessments/6/result-sheet/` | 200 / 200 / 200 | Problem | C0-02 (M) |
| `core:result-correct` | `/results/31/correct/` | 200 / 200 / 200 | Works | - |
| `core:report-subject-section-results` | `/academic-years/1/subject-results/` | 200 / 200 / 200 | Works | - |
| `core:term-publication` | `/terms/1/publication/` | 200 / 200 / 200 | Works | - |
| `core:publication-detail` | `/publications/31/` | 200 / 200 / 200 | Problem | C0-02 (H) |
| `core:publication-withdraw` | `/publications/31/withdraw/` | 200 / 200 / 200 | Works | - |
| `core:publications-stale` | `/publications/stale/` | 200 / 200 / 200 | Problem | C0-03 (M) |
| `core:term-remarks` | `/terms/1/remarks/` | 200 / 200 / 200 | Works | - |

#### Communication

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:announcement-list` | `/announcements/` | 200 / 200 / 200 | Usable | C0-05 (L) |
| `core:announcement-create` | `/announcements/new/` | 200 / 200 / 200 | Works | - |
| `core:announcement-detail` | `/announcements/1/` | 200 / 200 / 200 | Works | - |
| `core:announcement-prepare` | `/announcements/1/prepare/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |
| `core:announcement-withdraw` | `/announcements/1/withdraw/` | 200 / 200 / 200 | Works | - |
| `core:notifications-to-send` | `/notifications/to-send/` | 200 / 200 / 200 | Works | - |

#### Documents

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:document-index` | `/documents/` | 200 / 200 / 200 | Works | - |
| `core:bonafide-create` | `/documents/bonafide/` | 200 / 200 / 200 | Works | - |
| `core:document-report-cards` | `/documents/report-cards/` | 200 / 200 / 200 | Works | - |

#### Security

| Route | Path checked | 360 / 390 / 1366 | Status | Finding |
|---|---|---|---|---|
| `core:login-lockouts` | `/sign-in-lockouts/` | 200 / 200 / 200 | Works | - |
| `core:login-lockout-clear-confirm` | `/sign-in-lockouts/clear/` | 200 / 200 / 200 | Redirects (action needs POST or a precondition) | - |

**Excluded from the inventory:**

- POST-only endpoints with no page: reorder, restore, logo upload, consent, import commit/discard,
  notification dismiss/sent/WhatsApp;
- file responses: `document-pdf`, `document-report-card-pdf`, `import-issues-csv`,
  `import-template`, `school-logo`;
- `import-detail` (no data);
- framework and plumbing routes: `admin`, `login`, `logout`, `pwa-manifest`, `session-status`,
  `usage-beacon`;
- teacher-only and guardian-only routes.
