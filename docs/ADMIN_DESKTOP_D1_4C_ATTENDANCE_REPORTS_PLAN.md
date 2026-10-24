# UI-D1-4C — Admin Attendance Reports

**Status:** **PLAN ONLY — awaiting design review.** No application code is changed by this document or its PR.
**Planning branch:** `plan/ui-admin-desktop-d1-4c-attendance-reports`, based on `main` `4d7d3fc` (docs closeout for PR #104; flaky-test fix merge `9aa08e4`).
**Parent:** `docs/ADMIN_DESKTOP_D1_PLAN.md` (D1-4). **Binding design:** `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, the accepted D0 / D1-3 / D1-4A / D1-4B patterns.
**Domain authority:** ADR 0006 (enrollment effective dating), ADR 0007 (attendance model; supersedes 0005 for Phase 2), ADR 0008 (school calendar), ADR 0012 (teacher attendance; corrections stay administrator-only), and `core/reports.py` (the single implementation of "reportable").

This is a **presentation-only** gate, like D1-4A and D1-4B. It makes the five existing administrator attendance report pages consistent with the accepted page-header, toolbar, panel and table system. It adds **no new report, metric, export, chart, filter or calculation**.

## 1. Audited baseline (read at `4d7d3fc`)

### 1.1 The five pages in scope

| Page | Route name / path | View | Permission | Template | Query authority |
| --- | --- | --- | --- | --- | --- |
| Reports index | `core:attendance-reports` `/attendance/reports/` | `attendance_reports` | `core.view_attendanceentry` | `attendance_reports.html` (17 lines) | none (static links + one explanatory paragraph) |
| Daily absent students | `core:report-daily-absentees` `.../absent/` | `report_daily_absentees` | `core.view_attendanceentry` | `report_daily_absentees.html` (26 lines) | `reports.daily_absentees(date)` |
| Missing attendance | `core:report-missing-attendance` `.../missing/` | `report_missing_attendance` | **`core.view_attendanceregister`** | `report_missing_attendance.html` | `reports.missing_attendance(start, end, section)` |
| Monthly Class/Section summary | `core:report-monthly-section` `.../monthly/` | `report_monthly_section` | `core.view_attendanceentry` | `report_monthly_section.html` | `reports.monthly_section_summary(section, year, month)` |
| Student attendance history | `core:student-attendance` `/students/<pk>/attendance/` | `student_attendance` | `core.view_attendanceentry` | `student_attendance.html` | `reports.student_summary(...)` plus a raw entry listing |

Forms (all in `core/forms.py`, unchanged by this gate): `AttendanceDateForm` (required `date`), `MissingAttendanceForm` (required `start`/`end`, optional `section`, max 400 days, start not after end), `MonthlySectionSummaryForm` (required `section`, required `month` as `YYYY-MM`), `AttendanceRangeForm` (optional `start`/`end`).

Reports are server-rendered GET pages with **no pagination, sorting or table helper**; none uses `build_table`. All five templates are bare: a `h3` title, an inline `row g-2` form, and an unstyled `table`.

### 1.2 Calculation rules that must survive untouched

`core/reports.py` is the single source. Its module docstring and ADR 0007/0008/0006 define "reportable" attendance:

1. The entry's register is **SUBMITTED** (missing and DRAFT registers never count).
2. The register date is **not in the future** (school-local `business_today()`).
3. The date is **instructional** in its Academic Year (weekly pattern plus `SchoolCalendarDay` exceptions; Saturday is a per-year setting).
4. The date lies **within the entry enrollment's effective range** (`start_date <= date`, `end_date` null or `>= date`).
5. Values are the **current accepted status after corrections**.
6. Percentage = `PRESENT / (PRESENT + ABSENT) * 100`, one decimal, or **`None` (shown as an em dash) when nothing is reportable**.
7. **Absent is an explicit recorded status. "Not recorded" (no register, or a Draft register) is never Absent** and is reported separately (Missing attendance). Phase 2 has exactly two statuses, PRESENT and ABSENT.
8. "Expected" register/date pairs (`expected_registers`) require an instructional, non-future date on which the Section has at least one enrollment effective.

These functions are also consumed outside this gate: the Teacher class-teacher views (`views.py` ~1250/1261), the Guardian portal (`portal.py`), the Overview dashboard missing card (`dashboard.py`), the Register List section summary (D1-4A) and the Attendance Summary document (`core/documents/attendance_summary.py`). **No function in `reports.py` may change.**

### 1.3 Existing tests that pin behaviour

`core/tests/test_authorization.py::AttendanceReportViewTests` (access matrix across index/absent/missing/monthly, absent note, draft ignored, missing report states), `StudentAttendanceAuthorizationTests`, `core/tests/test_models.py::AttendanceReportingTests` (the reportable semantics; Monday/Saturday/Sunday fixtures, enrollment boundaries, future dates, corrections) and `AttendanceQueryCountTests`, `test_ui_admin_phase2.py::OverviewCardTests` (missing card), `test_phase5_attendance_views.py`, `test_phase6_portal_attendance.py`. These must all keep passing unmodified.

## 2. UI/UX problems found

Ranked by user impact. Each is observable from the templates above; none requires a business change to fix.

1. **No page identity.** All five pages use a bare `h3` and none uses `partials/_page_header.html`. They do not match Attendance (D1-4A) or the register detail (D1-4B), which an administrator moves between constantly.
2. **No navigation context.** `core/breadcrumbs.py` has no rule for any report route or `student-attendance`. On these pages there are **no breadcrumbs and the sidebar does not highlight "Attendance reports"** (the `_link` active test needs the url name or the breadcrumb `nav_section`; the only attendance rules are register detail/correct). A user on "Missing attendance" cannot see where they are or step back to the index.
3. **The index is a bare list.** It mixes four report links, a link to the *register list* (not a report) and a plain sentence ("Student history and percentage: open a Student, then View Attendance") that is not a link. It gives no indication of what each report answers or what it needs as input.
4. **Inconsistent form handling.**
   - The forms are `row g-2` instead of `erp-toolbar`.
   - Form errors are shown inconsistently: the Missing report prints `non_field_errors` only (a missing required date shows nothing field-local); the Monthly report prints `month.errors` only (an invalid or missing Section shows nothing); Daily absentees prints **no errors at all**. An invalid submission therefore looks the same as the pristine "nothing selected yet" page.
   - No defaults, so each report opens as a blank form with no results and no guidance.
5. **Result tables lack structure.** No `caption`, no `scope="col"`, no labelled scroll region, no `erp-panel`. The monthly table has its `Total` row in `<tfoot>` but numeric columns are left-aligned. The Missing report renders a raw `{{ row.date }}` (locale long date) plus weekday, and a state that is plain text or a link with no status styling.
6. **Draft vs Not taken is not visually distinct.** The Missing report distinguishes `Draft` (a link to the register) from `Not taken` (text) only by whether a link is rendered. These are different follow-up actions (finish/submit vs open a register) and should read as different states without relying on link styling or colour alone.
7. **Student history mixes counted and uncounted entries.** The history table lists **every** entry (including entries on Draft registers, on non-instructional dates, outside the enrollment span, or on a future-dated register) with its Present/Absent label, while the Summary above counts only reportable entries. The only hint is the "Register" status column. A reader can add up the table and not match the summary.
8. **Summary semantics are buried.** The reportable-only caveat appears as muted body text, and "Present / Absent / Total" and "Attendance percentage" are not grouped as one summary.
9. **Zero and em dash are fine but unexplained.** An em dash percentage ("nothing reportable") is correct and must stay; it has no legend.
10. **Page-level layout.** Controls do not use the accepted toolbar so they do not stack consistently at 360–390px; the Missing table's date cell does not use `text-nowrap`.

### 2.1 Cross-permission facts (record, do not fix here)

- The **index** requires `view_attendanceentry`; **Missing attendance** requires `view_attendanceregister`. A user with only `view_attendanceentry` sees an index link that returns 403. The reverse also holds (the Attendance nav entry needs `view_attendanceregister`). This pre-dates D1-4C and was logged in D1-4A as a separate item. **D1-4C must not widen or narrow any permission.** It may hide an index card whose destination the viewer cannot open (`perms.core.view_attendanceregister` for Missing), since that is display only and views still enforce access; see decision D3.
- Absent-student rows link to `core:student-attendance` (needs `view_attendanceentry`) and to the register detail (needs `view_attendanceregister`). Keep both links; do not gate silently.
- The Student detail page links to Student attendance (`student_detail.html:90`). That entry point is unchanged.

## 3. Proposed scope: two implementation gates

Five templates in one PR would exceed the D1-4A/B review size. The pages group naturally; **recommended split** (decision D1):

- **D1-4C-1 — Reports hub and the two daily operational lists:** `attendance_reports.html`, `report_daily_absentees.html`, `report_missing_attendance.html`.
- **D1-4C-2 — Analytical summaries:** `report_monthly_section.html`, `student_attendance.html`.

Both gates follow the same component contract (section 4) so the second is a straight application of the first. If the reviewer prefers one PR, the acceptance matrix in section 8 applies to all five pages.

### 3.1 Allowed change set (each gate)

**Application templates only** (the ones named for that gate). **Optionally**, `core/breadcrumbs.py` rules for the report routes (decision D2) because the missing sidebar highlight is a navigation defect, not a domain change. **Optionally** a small, strictly `erp-attendance-report-*` prefixed CSS block in `static/css/erp.css` only if `erp-toolbar`, `erp-panel`, `erp-table-scroll`, `_status_badge.html` and Bootstrap utilities are demonstrably insufficient; prefer zero CSS. **Tests and evidence:** new `core/tests/test_ui_admin_desktop_d1_4c*_attendance_reports.py`, screenshots + README in `docs/ui-reviews/ui-d1-4c*/`, narrow status edits to this plan and the parent.

**CSS compatibility warning (carried from D1-4A):** an existing D1-3D1 regression test scans CSS after `/* UI-D1-3D1 review fix` and requires Guardian-wrapper-prefixed selectors there. Any new block goes **before** that comment; do not edit existing rules.

### 3.2 Forbidden

`core/reports.py` (every function), `core/views.py`, `core/forms.py`, `core/tables.py`, `core/models.py`, services, calendar/enrollment logic, migrations, permissions, routes, messages; `core/portal.py`, `core/dashboard.py`, `core/documents/*`; Teacher and Guardian templates; the register list, register detail, capture and correction pages; shared partials (`_page_header`, `_form_field`, `_table_head`, `_table_footer`, `_status_badge`, `_empty`, `_attendance_capture_table`); global layout CSS; JavaScript; CSV/PDF export; new charts; period/subject attendance; LATE/EXCUSED statuses; academic-year rollover; Railway or deployment; D1-5/D1-6; any Tabler dependency.

## 4. Target layout and reusable components

Reuse only what is accepted. Nothing new is invented.

| Need | Reuse | Notes |
| --- | --- | --- |
| Page title, eyebrow "Attendance", purpose, secondary action | `partials/_page_header.html` | One H1 per page. Index: eyebrow "Daily operations". Report pages: a secondary link back to the index (`core:attendance-reports`). |
| Parameter controls | `erp-toolbar erp-toolbar--inline` + `partials/_form_field.html` | Existing field names preserved: `date`; `start`,`end`,`section`; `section`,`month`; `start`,`end`. Button labels are verb + object per rules §4 ("Show absent students", "Show missing attendance", "Show summary"); GET submission unchanged. |
| Form errors | `erp-form-errors` `role="alert"`, once, plus `_form_field` field-local errors | Render `non_field_errors` and each field's errors on **every** report (fixes problem 4). Only when the form is bound (`request.GET` non-empty); the pristine page shows guidance, not errors. |
| Result surface | `erp-panel` with `erp-panel-head`, heading + `erp-note-text` for the reportable caveat | One panel per result set. No card-in-card. |
| Tables | real `<table class="table">` inside `erp-table-scroll` `role="region" aria-label="…" tabindex="0"`, `<caption class="visually-hidden">`, `<th scope="col">`, `<th scope="row">` for the identifying cell | Same pattern as the D1-4A summary/register tables. Numeric columns right-aligned with tabular numerals; use an existing utility if one exists, otherwise the scoped class. |
| Status | `partials/_status_badge.html` | Draft = existing `draft` tone; **Not taken** needs a neutral tone with the text visible. Never colour-only. |
| Empty / no-result states | `partials/_empty.html` | Four situations kept distinct (rules §7): *not yet run* (pristine, guidance), *no results* (valid query, zero rows), *invalid query* (errors, no table), *nothing reportable* (percentage em dash with legend). |
| Back / context | breadcrumbs (decision D2) and the header secondary action | "Back to Attendance reports" carries no lost state: these pages have no list state beyond the GET query, which the browser Back preserves. |

### 4.1 Page-by-page contract

**Reports index (`attendance_reports.html`).**
- Header: H1 `Attendance reports`, eyebrow `Daily operations`, purpose that states the reportable rule in one plain sentence (keep the existing wording of the rule: "Counts and percentages use only submitted attendance on instructional, non-future dates within each Student's enrollment. Missing and draft registers never count as absent. Percentage = Present / (Present + Absent).").
- A list of report entries, each a single navigation target (stretched link, one `<a>`, rules §1): name, one-line description of the question it answers, and the input it needs ("Choose a date", "Choose a date range", "Choose a Section and month"). Three report entries: Daily absent students, Missing attendance, Monthly Class/Section summary. The **Daily Section registers** link is the register list, not a report, so it becomes a separated "Registers" shortcut (decision D4). The non-link sentence about Student history becomes explanatory text: "Student history: open a Student from Students, then View attendance."
- No counts, KPIs, charts or "last run" claims (rules §16: never invent data). No placeholder numbers.

**Daily absent students.**
- Toolbar: `Date` (required). Pristine: guidance "Choose a date to list students recorded absent."; no table. Do not auto-select today (decision D5).
- Result: panel "Absent on {date}" with the caveat "Submitted attendance only. Sections whose register is missing or still a draft are listed in Missing attendance, not here." linked to that report. Table columns **exactly**: Section, Student, Absence note (order preserved; the existing ordering from `daily_absentees` is preserved: class, section, name). Section links to the register detail, Student links to Student attendance, both exactly as today.
- Zero rows: `No submitted absences on this date.` (existing wording; a valid, non-error state). It must not imply that attendance was taken: the caveat above and the Missing link carry that.
- A count line "N students absent" is allowed **only** as `|length` over the supplied queryset (no new query, no percentage).

**Missing attendance.**
- Toolbar: `Start`, `End` (required), `Section` (optional), in that order. Show **all** form errors (problem 4), including the 400-day limit and inverted range.
- Result: panel with the existing explanation (instructional dates up to today on which a Section had enrolled Students but no submitted register; holidays and non-working days never listed).
- Table columns exactly: Date (with weekday, `text-nowrap`), Section, State. State is a status badge with text: **Not taken** (no register) vs **Draft** (register exists, not submitted). The Draft state keeps its link to the register detail (as today); Not taken has no link (as today). Order preserved (date, then Section).
- Never display either state as Absent, and never show a count that could read as an absence count.
- Zero rows: `No missing attendance in this range.`

**Monthly Class/Section summary** (D1-4C-2).
- Toolbar: `Section`, `Month` (type `month`), field-local errors for both (problem 4).
- Result: a summary panel with the existing sentence as three labelled facts: *Instructional days with attendance expected*, *Submitted*, *Missing or draft* (values from `totals`, unchanged; never recomputed in the template). Then the student table: Student (link), Present, Absent, Attendance %, numeric columns right-aligned; the Total row stays in `<tfoot>` with `scope="row"`.
- Percentage: `{{ row.percentage }}%` or an em dash **with a visually hidden label** ("No reportable attendance") and a one-line legend ("— means no submitted attendance counts yet; it is not 0% and not absent.").
- Zero rows: `No Students enrolled in this Section during this month.`
- A Student with no reportable entries shows 0 / 0 / em dash, not Absent.

**Student attendance history** (D1-4C-2).
- Header: `Attendance for {student}`, eyebrow `Students`, back link to the Student detail page (decision D6).
- Toolbar: `Start`, `End` (optional) with `AttendanceRangeForm` errors shown (currently not shown).
- Summary panel: *Present*, *Absent*, *Total*, *Attendance percentage* from the supplied `summary`, `total`, `percentage` (unchanged). Caveat: "Submitted attendance only; missing or draft registers are not counted as absent."
- History table: columns exactly Date, Academic year, Section, Register, Status, Absence note (order preserved). Because the table lists entries the summary does not count, add a visible note under the heading: "This list shows every recorded entry. Only entries on submitted registers, on instructional dates within the Student's enrollment, and not in the future are counted in the summary above." The Register column shows Draft/Submitted via the status badge. **Do not** add a per-row "counted" flag in this gate (it requires a view/reports change; see decision D7 and section 11).
- Empty: `No attendance recorded.`

## 5. Responsive and accessibility requirements

- Desktop (>= 992px): content in the accepted workspace width; toolbar controls on one row; result panels full width; no page-level horizontal overflow at 992, 1024, 1280, 1440px.
- Tablet 768px: toolbar wraps; tables fit or scroll locally.
- Phone 360 / 390px: toolbar fields stack full width (`erp-toolbar--inline` already does below 576px); 3–4 column tables remain readable; wider tables scroll **only** inside their `erp-table-scroll` region (labelled, keyboard focusable). The accepted phone table rule applies: tables stack on phones unless marked `.erp-keep`; the Monthly table is a numeric grid and needs `.erp-keep`, which must be verified.
- Exactly one H1 per page; ordered headings; `caption` + `scope` on every table; result region labelled; status never colour-only (text in every badge); `aria-current="page"` on the active sidebar item (via the breadcrumb section); visible focus; 44px touch targets for the primary action and links in rows on phones; labels visible on all controls; errors associated with fields (`aria-describedby`/`aria-invalid`, from `_form_field`); a `role="status"` count where one is added; works with JavaScript off (no JS is added).
- 200% zoom: no clipped controls; no horizontal page scroll.

## 6. Permission boundaries (must not change)

| Route | Required | Anonymous | Non-admin / Teacher / Guardian |
| --- | --- | --- | --- |
| index, absentees, monthly, Student history | `core.view_attendanceentry` | redirect to login | 403 |
| missing | `core.view_attendanceregister` | redirect to login | 403 |

- All five remain read-only GET pages; no form posts, no writes, no new routes.
- Display gating may use `perms.*` only to hide links the viewer cannot use; views remain the authority. Do not broaden any link or action (for example do not show register links to a viewer without `view_attendanceregister`). Teachers reach their own Section summaries through the Teacher portal, which is **out of scope** and must not link into these admin pages.

## 7. Testing requirements

New focused tests (one module per gate) **plus** the existing suites unchanged.

1. **Structure:** exactly one H1; `_page_header` present; toolbar with `aria-label`; table `caption`, `scope="col"`, labelled `role="region"` scroll container; breadcrumbs / active sidebar (`aria-current`) on each report page if D2 is accepted.
2. **Query invariance:** for each page, compare the rendered context (`absentees`, `rows`, `summary`, `entries`, `totals`) before and after for representative GETs; identical rows, order and values.
3. **Semantics (re-asserted through the new templates):**
   - A Draft register with saved Absent entries is **not** listed as absent and **is** listed in Missing as Draft; an unopened register is listed as Not taken; neither is ever rendered with the word Absent in a state column.
   - A non-instructional date (holiday exception, Sunday, Saturday when off) never appears in Missing and contributes nothing.
   - An enrollment ending before the register date, starting after it, or a future-dated register does not count; boundary dates (start day, end day) do count.
   - A corrected entry is reported at its current value.
   - Monthly: a Student with no reportable entries shows 0, 0 and an em dash (not 0%); `Total` equals the sum of the rows' reportable counts; expected/submitted/missing day counts match `section_summary`.
   - Student history: a Draft-register entry appears in the list but not in the summary; the explanatory note is rendered; the summary equals `reports.student_summary`.
4. **Validation states:** each report renders field-local and non-field errors for missing/invalid/inverted/over-400-day input; the pristine page shows guidance, not errors; an invalid query does not render a results table or a claim of "no results".
5. **Permissions:** the existing matrix extended with the Student history page and a user holding only one of the two permissions (index link visibility; pages the user can open return 200, the other returns 403); anonymous redirect; Teacher and Guardian 403; no POST accepted (405 or unchanged behaviour).
6. **Responsive/a11y (scripted):** no horizontal overflow on `document.documentElement` at 360, 390, 768, 992, 1024, 1280, 1440px for pristine, results, empty and invalid states; local scroll region focusable; keyboard tab order; 200% zoom check.
7. **Query counts:** report pages do not add queries per row (existing `AttendanceQueryCountTests` unchanged; add `assertNumQueries` bounds for the new templates where a loop touches relations).
8. **Regression suites:** `manage.py check`; `AttendanceReportViewTests`, `StudentAttendanceAuthorizationTests`, `AttendanceReportingTests`, `AttendanceQueryCountTests`, D1-4A/B modules, Phase 5/6 attendance tests, the D1-3D1/D1-3D2 CSS tests; the full PostgreSQL suite with `--parallel 4` (no concurrent runner sharing test databases). SQLite is acceptable for focused UI tests but the authoritative run is PostgreSQL.
9. **Evidence:** synthetic screenshots only (never real or staging data) at 390, 768, 992, 1024, 1280, 1440px for: pristine, results, empty, invalid, Draft/Not taken mix, long Section/Academic Year names; README stating the environment and limits.

## 8. Acceptance matrix (all required, per gate)

| Check | Pass condition |
| --- | --- |
| Structural | Header via `_page_header`; single H1; `erp-toolbar` with visible labels; results in `erp-panel`; real tables with caption/scope; labelled keyboard-scrollable region; shared status badge and empty partials reused |
| Navigation | Report pages show breadcrumbs and keep "Attendance reports" active (if D2 accepted); Back to the index is one click |
| Calculations | Zero diff in `core/reports.py`; pre/post contexts identical for all test scenarios; no template arithmetic beyond `|length` and existing supplied values |
| Domain wording | The reportable caveat is visible on every counting page; Draft/Not taken never read as Absent; em dash always explained; "Absent" appears only for an explicit recorded Absent |
| Validation | All form errors visible once, field-local and summarised; pristine vs invalid vs no-results are visually and textually distinct |
| Permissions | Matrix in section 6 holds; no link shown that the viewer cannot open; no changed route, method or decorator |
| Responsive / a11y | No page overflow at 360–1440px; labelled local scroll; focus, keyboard, 200% zoom pass; status not colour-only |
| Regression | `check` clean; focused module; existing attendance/report suites; full PostgreSQL `--parallel 4` pass, exact counts and environment reported |
| PR hygiene | Template (and optional breadcrumb/CSS) diff only; no Python business logic; draft PR to `main`; no merge, deploy, or next-gate start without approval |

## 9. Decisions requested from the reviewer

- **D1 — One PR or two?** Recommended: two (D1-4C-1 hub + daily lists; D1-4C-2 monthly + Student history). All acceptance items apply to each.
- **D2 — Breadcrumbs.** Add rules in `core/breadcrumbs.py` so the five pages show breadcrumbs and the sidebar highlights "Attendance reports" (a pure navigation-configuration change, no authorization effect). Recommended: yes, as the only non-template edit, with a test. Alternative: defer and live with no highlight.
- **D3 — Index cards for unreachable reports.** Recommended: hide the Missing attendance card unless `perms.core.view_attendanceregister` (display only; the view still returns 403). Alternative: show all and leave the known 403 for a later permissions gate.
- **D4 — "Daily Section registers" on the index.** Recommended: keep as a clearly separated "Registers" shortcut (it is the register list, not a report) rather than a fourth report card.
- **D5 — Defaults.** Recommended: **no** pre-selected dates or Section (a default would change what the page computes on first load and could imply "today has no absences" before attendance is taken). Pristine pages show guidance only. Alternative: prefill the toolbar's date input with the business date **without** running the report.
- **D6 — Student history back link.** Recommended: link to Student detail only when `perms.core.view_student`.
- **D7 — Counted/uncounted marker on Student history.** The honest fix (a per-row "Counted" indicator) needs a view/report helper (`reportable_entries` membership) and is therefore a logic change. Recommended: ship the explanatory note now (template only) and log the marker as a follow-up gate with its own review.

## 10. Execution plan (after approval)

1. Fresh implementation branch from the latest approved `main`, including this plan.
2. Templates (and D2 breadcrumbs / zero-or-minimal CSS) for the gate's pages; reuse before adding.
3. Tests per section 7; run focused, then full PostgreSQL `--parallel 4` sequentially.
4. Synthetic screenshots and README under `docs/ui-reviews/ui-d1-4c*/`; scripted overflow/keyboard/zoom checks.
5. Open one draft PR, report branch/head SHA and results, and **stop** for design review. Do not mark ready, merge, deploy or start the next gate.

## 11. Explicit follow-ups — not in D1-4C

- Per-row "counted in summary" marker on Student history (D7).
- Reconciling `view_attendanceentry` vs `view_attendanceregister` across the index, nav and Missing report (permissions gate).
- Export (CSV/PDF), charts, trend or comparison views, scheduled reports (Phase 7 scope per ADR 0005).
- The Attendance Summary document / PDF issuance (Documents scope).
- Any LATE/EXCUSED/period attendance (new ADR required).
- Teacher and Guardian attendance surfaces; Academic-Year rollover; deployment of any UI-D1 gate.
