# UI-D1-4C — Admin Attendance Reports

**Status:** **COMPLETE — both gates implemented and merged.** Plan merged in PR #105 (merge `64809e5`; decisions D1–D7 approved with clarifications, 2026-10-24). **D1-4C-1 MERGED** (PR #106, merge `6ef74be`, head `c0d073c`; full PostgreSQL suite 2,558 OK; evidence `docs/ui-reviews/ui-d1-4c1/`). **D1-4C-2 MERGED** (PR #107, merge `aedfd33`, head `00c113c`; full PostgreSQL suite 2,593 OK; evidence `docs/ui-reviews/ui-d1-4c2/`). Neither gate is deployed. The text below is the approved plan as written; the open follow-ups are listed in section 11.
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

**Application templates only** (the ones named for that gate), **plus** the navigation-configuration change approved as D2: report-route rules in `core/breadcrumbs.py`, made **permission-aware** (section 4.2), and the single call-site edit in `core/context_processors.py` that passes the user to `breadcrumb_context`. These are display-only: no view, decorator, route or permission changes, and `breadcrumb_context(match)` keeps working unchanged for every existing caller and test. D1-4C-1 adds the permission-aware mechanism and the rules for its three routes; D1-4C-2 adds the rules for the monthly and Student-history routes. **Optionally** a small, strictly `erp-attendance-report-*` prefixed CSS block in `static/css/erp.css` only if `erp-toolbar`, `erp-panel`, `erp-table-scroll`, `_status_badge.html` and Bootstrap utilities are demonstrably insufficient; prefer zero CSS. **Tests and evidence:** new `core/tests/test_ui_admin_desktop_d1_4c*_attendance_reports.py`, screenshots + README in `docs/ui-reviews/ui-d1-4c*/`, narrow status edits to this plan and the parent.

**CSS compatibility warning (carried from D1-4A):** an existing D1-3D1 regression test scans CSS after `/* UI-D1-3D1 review fix` and requires Guardian-wrapper-prefixed selectors there. Any new block goes **before** that comment; do not edit existing rules.

### 3.2 Forbidden

`core/reports.py` (every function), `core/views.py` (including the Student-history invalid-filter fallback, which is presented honestly in the template instead, section 4.1), `core/forms.py` (so `FieldAccessibilityMixin` is **not** applied to the report forms; see section 5.1), `core/tables.py`, `core/models.py`, services, calendar/enrollment logic, migrations, permissions, routes, messages; `core/portal.py`, `core/dashboard.py`, `core/documents/*`; Teacher and Guardian templates; the register list, register detail, capture and correction pages; shared partials (`_page_header`, `_form_field`, `_table_head`, `_table_footer`, `_status_badge`, `_empty`, `_attendance_capture_table`); global layout CSS; JavaScript; CSV/PDF export; new charts; period/subject attendance; LATE/EXCUSED statuses; academic-year rollover; Railway or deployment; D1-5/D1-6; any Tabler dependency.

## 4. Target layout and reusable components

Reuse only what is accepted. Nothing new is invented.

| Need | Reuse | Notes |
| --- | --- | --- |
| Page title, eyebrow "Attendance", purpose, secondary action | `partials/_page_header.html` | One H1 per page. Index: eyebrow "Daily operations". Report pages: a secondary link back to the index (`core:attendance-reports`). |
| Parameter controls | `erp-toolbar erp-toolbar--inline` + `partials/_form_field.html` **for every field** | Existing field names preserved: `date`; `start`,`end`,`section`; `section`,`month`; `start`,`end`. Never render a bare `{{ form.x }}`: Django already writes `aria-describedby="id_x_error"` on an errored input, and only the partial emits that id (section 5.1). Button labels are verb + object per rules §4 ("Show absent students", "Show missing attendance", "Show summary"); GET submission unchanged. |
| Form errors | `partials/_form_error_summary.html` (`role="alert"`, lists non-field errors and links to each errored field) **plus** `_form_field` field-local errors | Both appear on **every** report (fixes problem 4). Rules §6: the summary may list errors but never replaces the field-local message, so each message appears at most once per location. Only when the form is bound with errors; the pristine page shows guidance, not errors. Pass `action_text` ("showing the report", "showing the summary"). |
| Result surface | `erp-panel` with `erp-panel-head`, heading + `erp-note-text` for the reportable caveat | One panel per result set. No card-in-card. |
| Tables | real `<table class="table">` inside `erp-table-scroll` `role="region" aria-label="…" tabindex="0"`, `<caption class="visually-hidden">`, `<th scope="col">`, `<th scope="row">` for the identifying cell | Same pattern as the D1-4A summary/register tables. Numeric columns right-aligned with tabular numerals; use an existing utility if one exists, otherwise the scoped class. |
| Status | `partials/_status_badge.html` | Draft = existing `draft` tone; **Not taken** needs a neutral tone with the text visible. Never colour-only. |
| Empty / no-result states | `partials/_empty.html` | Four situations kept distinct (rules §7): *not yet run* (pristine, guidance), *no results* (valid query, zero rows), *invalid query* (errors, no table), *nothing reportable* (percentage em dash with legend). |
| Back / context | breadcrumbs (decision D2) and the header secondary action | "Back to Attendance reports" carries no lost state: these pages have no list state beyond the GET query, which the browser Back preserves. |

### 4.1 Page-by-page contract

**Reports index (`attendance_reports.html`).**
- Header: H1 `Attendance reports`, eyebrow `Daily operations`, purpose that states the reportable rule in one plain sentence (keep the existing wording of the rule: "Counts and percentages use only submitted attendance on instructional, non-future dates within each Student's enrollment. Missing and draft registers never count as absent. Percentage = Present / (Present + Absent).").
- A list of report entries, each a single navigation target (stretched link, one `<a>`, rules §1): name, one-line description of the question it answers, and the input it needs ("Choose a date", "Choose a date range", "Choose a Section and month"). Three report entries: Daily absent students, Monthly Class/Section summary (both always reachable from this page, since the page itself needs `view_attendanceentry`), and **Missing attendance, rendered only when `perms.core.view_attendanceregister`** (D3; the view still returns 403 otherwise). The **Daily Section registers** link is the register list, not a report, so it becomes a separated "Registers" shortcut, **rendered only when `perms.core.view_attendanceregister`** (D4; it is the permission the list requires). The non-link sentence about Student history becomes explanatory text: "Student history: open a Student from Students, then View attendance." (the "View Attendance" button on Student detail needs `view_attendanceentry`; do not link to Students from this sentence unless `perms.core.view_student`). An index viewer holding only `view_attendanceentry` therefore sees two report cards and no Registers shortcut. Never assume a register-only user can open this index (they cannot; it needs `view_attendanceentry`).
- No counts, KPIs, charts or "last run" claims (rules §16: never invent data). No placeholder numbers.

**Daily absent students.**
- Toolbar: `Date` (required). Pristine: guidance "Choose a date to list students recorded absent."; no table. **No automatic date** (D5: no automatic date or Section on Daily, Missing or Monthly).
- Result: panel "Absent on {date}" with the caveat "Submitted attendance only. Sections whose register is missing or still a draft are listed in Missing attendance, not here." **"Missing attendance" is a link only when `perms.core.view_attendanceregister`; otherwise it is plain text.** Table columns **exactly**: Section, Student, Absence note (order preserved; the existing ordering from `daily_absentees` is preserved: class, section, name). The **Section cell links to the Register Detail only when `perms.core.view_attendanceregister`; otherwise it shows the Section as plain text** (Register Detail needs that permission). The Student cell links to Student attendance (always permitted on this page, which needs `view_attendanceentry`).
- Zero rows: `No submitted absences on this date.` (existing wording; a valid, non-error state). It must not imply that attendance was taken: the caveat above and the Missing link carry that.
- A count line "N students absent" is allowed **only** as `|length` over the supplied queryset (no new query, no percentage).

**Missing attendance.**
- Toolbar: `Start`, `End` (required), `Section` (optional), in that order, **no automatic dates or Section** (D5). Show **all** form errors (problem 4), including the 400-day limit and inverted range.
- Header action: this page needs only `view_attendanceregister`, so a viewer may lack the Reports index. The secondary action is **"Attendance reports" when `perms.core.view_attendanceentry`, otherwise "Attendance" (the register list, which this permission opens)**. Cross-link "Daily absent students" in the explanatory text only when `perms.core.view_attendanceentry`, else plain text.
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
- Header: `Attendance for {student}`, eyebrow `Students`. Two header actions: **"Back to student" to the Student detail page only when `perms.core.view_student`** (D6), and **"Attendance reports"** (always authorized here, since this page needs `view_attendanceentry`). No back link is rendered that the viewer may be denied; the browser Back button still works for a viewer who arrived from a report.
- Toolbar: `Start`, `End` (optional) rendered through `_form_field.html`, with `AttendanceRangeForm` errors shown (currently not shown). **First load stays exactly as today: unbound form, the full unfiltered history and summary** (D5 explicitly preserves this; no default range is introduced).
- **Invalid date filter (bad date or Start after End).** The untouched view applies a filter only when the whole form is valid; when it is invalid it renders the **complete, unfiltered** history and summary alongside the errors. The template must therefore not present that as a filtered result: show the error summary and field-local errors, keep the entered values, and place a visible note immediately above the Summary and again above the History table: **"The date filter was not applied; showing all recorded attendance."** The Summary and History headings use "All recorded attendance" in that state. A valid filtered request labels both with the applied range ("From {start} to {end}", using `form.cleaned_data`); a valid unfiltered request keeps the existing headings. `core/views.py` is not changed.
- Summary panel: *Present*, *Absent*, *Total*, *Attendance percentage* from the supplied `summary`, `total`, `percentage` (unchanged). Caveat: "Submitted attendance only; missing or draft registers are not counted as absent."
- History table: columns exactly Date, Academic year, Section, Register, Status, Absence note (order preserved). Because the table lists entries the summary does not count, add a visible note under the heading: "This list shows every recorded entry. Only entries on submitted registers, on instructional dates within the Student's enrollment, and not in the future are counted in the summary above." The Register column shows Draft/Submitted via the status badge. **Do not** add a per-row "counted" flag in this gate (it requires a view/reports change; see decision D7 and section 11).
- Empty: `No attendance recorded.`

### 4.2 Breadcrumbs and permission-aware links (D2 as approved)

`core/breadcrumbs.py` today holds static `Rule`/`Crumb` data: every crumb is shown to every administrator regardless of permission, and it is the only source of both the trail and the sidebar section (`nav_section`). Report pages have no rule, and a naive rule `Overview > Attendance reports > Missing attendance` would hand a register-only viewer a crumb that returns 403. Approved mechanism (no authorization effect, display only):

- `Crumb` gains an optional `perm`. `breadcrumb_context(match, user=None)` omits any crumb whose `perm` the user lacks; with `user=None` it behaves exactly as today, so existing rules and tests are untouched. `context_processors.py` passes `request.user`. The current page (last crumb) is never gated.
- Rules (the permission each parent crumb needs is what its destination view requires):

| Route | Trail (after "Overview") | Sidebar section | Crumb permission |
| --- | --- | --- | --- |
| `attendance-reports` (C-1) | current page "Attendance reports" | `attendance-reports` | none (page itself needs `view_attendanceentry`) |
| `report-daily-absentees` (C-1) | `Attendance reports` → "Daily absent students" | `attendance-reports` | `core.view_attendanceentry` |
| `report-missing-attendance` (C-1) | `Attendance reports` → "Missing attendance" | `attendance-reports` | `core.view_attendanceentry` (a register-only viewer sees `Overview > Missing attendance`, no dead crumb) |
| `report-monthly-section` (C-2) | `Attendance reports` → "Monthly summary" | `attendance-reports` | `core.view_attendanceentry` |
| `student-attendance` (C-2) | `Students` → `Student` → "Attendance" | `student-list` | `core.view_student` on both parent crumbs |

- Student history keeps its **logical** parent chain (the Student), not the Reports index, because the common entry points are the Student detail page and report rows; the header's "Attendance reports" action (always authorized) provides the other path. A viewer without `view_student` sees `Overview > Attendance` with no unauthorized parent links.
- The sidebar highlights a link only if that link is in the viewer's navigation; a register-only viewer on Missing attendance has no "Attendance reports" link to highlight, which is acceptable and recorded as a known limit rather than worked around.
- Display gating uses `perms.*` in templates and `user.has_perm` in `breadcrumb_context`; views remain the only authority. Where a destination is not permitted, render **plain text, not a link**.

## 5. Responsive and accessibility requirements

- Desktop (>= 992px): content in the accepted workspace width; toolbar controls on one row; result panels full width; no page-level horizontal overflow at 992, 1024, 1280, 1440px.
- Tablet 768px: toolbar wraps; tables fit or scroll locally.
- Phone 360 / 390px: toolbar fields stack full width (`erp-toolbar--inline` already does below 576px); 3–4 column tables remain readable; wider tables scroll **only** inside their `erp-table-scroll` region (labelled, keyboard focusable). The accepted phone table rule applies: tables stack on phones unless marked `.erp-keep`; the Monthly table is a numeric grid and needs `.erp-keep`, which must be verified.
- Exactly one H1 per page; ordered headings; `caption` + `scope` on every table; result region labelled; status never colour-only (text in every badge); `aria-current="page"` on the active sidebar item (via the breadcrumb section); visible focus; 44px touch targets for the primary action and links in rows on phones; labels visible on all controls; errors associated with fields (`aria-describedby`/`aria-invalid`, from `_form_field`); a `role="status"` count where one is added; works with JavaScript off (no JS is added).
- 200% zoom: no clipped controls; no horizontal page scroll.

### 5.1 Form accessibility: verified, not assumed

Checked by rendering the four report forms bound with errors (Django 5.2.17, no `FieldAccessibilityMixin`), and by reading `templates/partials/_form_field.html`, `_form_error_summary.html` and `FieldAccessibilityMixin`:

| Requirement | Finding | Consequence for the plan |
| --- | --- | --- |
| Visible label per input | Partial renders `label_tag`; required fields get an `aria-hidden` `*` plus visually hidden "(required)". Inputs also carry native `required`. | OK when every field goes through the partial. |
| Error linked to input (`aria-describedby`) and invalid flag (`aria-invalid`) | The partial does **not** set these. **Django 5.2 sets them itself** on bound, errored fields: `aria-invalid="true" aria-describedby="id_start_error"` (and `id_month_helptext id_month_error` where help text exists). The ids match the partial's `<id>_error` / `<id>_helptext` elements. | The association works **only if the field is rendered through the partial**. The current report templates print bare `{{ form.x }}` and show no error list, so today the attribute would point at a missing element. Tests must assert that every `aria-describedby` token resolves to an element in the response. |
| Error announced | The partial's field error `<ul>` has no `role`/`aria-live`. `_form_error_summary.html` has `role="alert"`. | Use the summary partial on every report so a failed submit is announced. |
| Focus moved to first invalid field or summary after a failed submit (rules §6) | `autofocus` and `focus_summary` are produced **only** by `FieldAccessibilityMixin`, which these forms do not use; `core/forms.py` is out of scope. The summary partial adds `tabindex="-1" autofocus` only when `form.focus_summary` is set. | **Gap, recorded.** Without the mixin there is no automatic focus move. The gate ships the live-region summary with links to the fields as the mitigation and does not claim the focus rule. Follow-up: apply the mixin to the report forms in a forms-scoped gate. |
| Select field (`section`) association | Not rendered in the check (needs database rows). Same Django mechanism applies. | Verify in the focused tests with a real Section; do not assume. |
| Non-field errors (inverted range, 400-day limit) | Not tied to any input; shown by the summary partial's list. | Rendered once in the summary; no field-local copy. |

## 6. Permission boundaries (must not change)

| Route | Required | Anonymous | Non-admin / Teacher / Guardian |
| --- | --- | --- | --- |
| index, absentees, monthly, Student history | `core.view_attendanceentry` | redirect to login | 403 |
| missing | `core.view_attendanceregister` | redirect to login | 403 |

Display gating (links shown as plain text when the viewer lacks the destination's permission):

| Link / card | Shown when |
| --- | --- |
| Index: Missing attendance card | `perms.core.view_attendanceregister` |
| Index: Registers shortcut | `perms.core.view_attendanceregister` |
| Daily absentees: Section → Register Detail | `perms.core.view_attendanceregister` |
| Daily absentees / Missing: cross-links between reports | destination's permission (`view_attendanceregister` for Missing, `view_attendanceentry` for Daily absentees) |
| Missing: Draft state → Register Detail | always (the page needs `view_attendanceregister`) |
| Missing: header action | Reports index if `view_attendanceentry`, else the register list |
| Student history: Back to student, Students/Student crumbs | `perms.core.view_student` |
| Student history: Attendance reports action | always (the page needs `view_attendanceentry`) |
| Breadcrumb "Attendance reports" parent | `perms.core.view_attendanceentry` |

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
4. **Validation states:** each report renders field-local errors, the `role="alert"` summary (with working `#id` field links) and non-field errors for missing/invalid/inverted/over-400-day input; the pristine page shows guidance, not errors; an invalid query does not render a results table or a claim of "no results". **Association checks (section 5.1):** for each errored field the response contains `aria-invalid="true"` and every token in `aria-describedby` resolves to an element id in the same response, including the `section` select with a real Section and the `month` field's help-text id.
   - **Student history (C-2):** bad date, and Start after End: errors visible; the "date filter was not applied; showing all recorded attendance" note rendered above both the Summary and the History; the Summary and History equal the unfiltered `student_summary` / full entry list; entered values retained; first load (unbound) unchanged from today. A valid range is labelled with the applied range.
5. **Permissions (explicit matrix):** anonymous redirect; Teacher and Guardian 403; no POST accepted (405 or unchanged behaviour); and users holding exactly one of `view_attendanceentry`, `view_attendanceregister`, `view_student` and combinations, asserting for each:
   - which pages return 200 / 403 (unchanged from today);
   - index: Missing card and Registers shortcut present only with `view_attendanceregister`; a user with `view_attendanceentry` only sees two report cards;
   - Daily absentees: Section cell is a Register Detail link only with `view_attendanceregister`, plain text otherwise; the Missing cross-link follows the same rule;
   - Missing (register-only user): no link to the Reports index anywhere on the page (header action is the register list; breadcrumb has no "Attendance reports" crumb);
   - Student history: "Back to student" and Students/Student crumbs only with `view_student`; "Attendance reports" action always present;
   - no page contains an `href` to a route the viewer cannot open (scan the response for the report/register/student URLs and compare with the matrix).
   - Breadcrumbs: with `user=None` the existing rules and tests are byte-identical in output; permission filtering has its own unit tests.
6. **Responsive/a11y (scripted):** no horizontal overflow on `document.documentElement` at 360, 390, 768, 992, 1024, 1280, 1440px for pristine, results, empty and invalid states; local scroll region focusable; keyboard tab order; 200% zoom check.
7. **Query counts:** report pages do not add queries per row (existing `AttendanceQueryCountTests` unchanged; add `assertNumQueries` bounds for the new templates where a loop touches relations).
8. **Regression suites:** `manage.py check`; `AttendanceReportViewTests`, `StudentAttendanceAuthorizationTests`, `AttendanceReportingTests`, `AttendanceQueryCountTests`, D1-4A/B modules, Phase 5/6 attendance tests, the D1-3D1/D1-3D2 CSS tests; the full PostgreSQL suite with `--parallel 4` (no concurrent runner sharing test databases). SQLite is acceptable for focused UI tests but the authoritative run is PostgreSQL.
9. **Evidence:** synthetic screenshots only (never real or staging data) at 390, 768, 992, 1024, 1280, 1440px for: pristine, results, empty, invalid, Draft/Not taken mix, long Section/Academic Year names; README stating the environment and limits.

## 8. Acceptance matrix (all required, per gate)

| Check | Pass condition |
| --- | --- |
| Structural | Header via `_page_header`; single H1; `erp-toolbar` with visible labels; results in `erp-panel`; real tables with caption/scope; labelled keyboard-scrollable region; shared status badge and empty partials reused |
| Navigation | Report pages show permission-aware breadcrumbs and keep "Attendance reports" active for viewers who have that link; no breadcrumb, header action or cross-link points at a page the viewer cannot open |
| Calculations | Zero diff in `core/reports.py`; pre/post contexts identical for all test scenarios; no template arithmetic beyond `|length` and existing supplied values |
| Domain wording | The reportable caveat is visible on every counting page; Draft/Not taken never read as Absent; em dash always explained; "Absent" appears only for an explicit recorded Absent |
| Validation | Every error shown field-local and in the `role="alert"` summary (once per location); `aria-describedby` tokens all resolve; pristine vs invalid vs no-results are visually and textually distinct; Student history never presents unfiltered data as filtered |
| Permissions | Matrix in section 6 holds; no link shown that the viewer cannot open; no changed route, method or decorator |
| Responsive / a11y | No page overflow at 360–1440px; labelled local scroll; focus, keyboard, 200% zoom pass; status not colour-only |
| Regression | `check` clean; focused module; existing attendance/report suites; full PostgreSQL `--parallel 4` pass, exact counts and environment reported |
| PR hygiene | Template (and optional breadcrumb/CSS) diff only; no Python business logic; draft PR to `main`; no merge, deploy, or next-gate start without approval |

## 9. Decisions (APPROVED at PR #105 review, 2026-10-24, with clarifications)

- **D1 — Two implementation gates, C-1 and C-2.** C-1: hub, Daily absentees, Missing attendance (plus the permission-aware breadcrumb mechanism). C-2: Monthly summary and Student history. C-2 is not started until C-1 is reviewed. All acceptance items apply to each gate.
- **D2 — Breadcrumb rules, permission-aware.** Approved with the clarification that Student History keeps its logical navigation (Students → Student → Attendance, with the always-authorized "Attendance reports" action) and that **no breadcrumb or back link may point at a page the viewer cannot open**. A register-only viewer is never assumed to reach the Reports index. Mechanism and matrix: section 4.2.
- **D3 — Permission-gated Missing attendance card** (`perms.core.view_attendanceregister`), with plain text instead of a link in cross-references.
- **D4 — Registers is a separate shortcut**, shown only with `view_attendanceregister`.
- **D5 — No automatic date or Section** on Daily, Missing or Monthly. Pristine pages show guidance only. **Student History keeps its existing unfiltered first-load behaviour.**
- **D6 — Student Detail back link only with `perms.core.view_student`.**
- **D7 — Per-row "counted" indicator deferred.** The page instead carries an accurate explanation of why a listed entry may not contribute to the summary (register not submitted, date not instructional, date outside the enrollment span, date in the future). Listing the entry is not a claim that it is counted.
- **Additional (review):** Register Detail links in Daily absent students and any cross-link to Missing attendance are permission-gated, with non-link text otherwise; Student History's invalid-filter state shows errors and never presents unfiltered data as a filtered result; `core/views.py` and `core/reports.py` stay unchanged; the shared form partial was verified rather than assumed (section 5.1).

## 10. Execution plan (after this plan is merged)

Start with **D1-4C-1 only** (hub, Daily absent students, Missing attendance, and the permission-aware breadcrumb mechanism with the three C-1 route rules). D1-4C-2 is a separate later gate.

1. Fresh implementation branch from the latest `main` containing this plan.
2. Templates (and D2 breadcrumbs / zero-or-minimal CSS) for the gate's pages; reuse before adding.
3. Tests per section 7; run focused, then full PostgreSQL `--parallel 4` sequentially.
4. Synthetic screenshots and README under `docs/ui-reviews/ui-d1-4c*/`; scripted overflow/keyboard/zoom checks.
5. Open one draft PR, report branch/head SHA and results, and **stop** for design review. Do not mark ready, merge, deploy or start the next gate.

## 11. Explicit follow-ups — not in D1-4C

- Per-row "counted in summary" marker on Student history (D7).
- Apply `FieldAccessibilityMixin` to the report forms (automatic focus to the first invalid field or summary, rules §6), a forms-scoped gate (section 5.1).
- Reconciling `view_attendanceentry` vs `view_attendanceregister` across the index, nav and Missing report (permissions gate).
- Export (CSV/PDF), charts, trend or comparison views, scheduled reports (Phase 7 scope per ADR 0005).
- The Attendance Summary document / PDF issuance (Documents scope).
- Any LATE/EXCUSED/period attendance (new ADR required).
- Teacher and Guardian attendance surfaces; Academic-Year rollover; deployment of any UI-D1 gate.
