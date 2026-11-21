# Option A Implementation Specification: Make Existing Exceptions Actionable

- **Status:** Approved implementation specification
- **Baseline:** `main` at `d17d7fb437b00beb04d62a4723ea00827b5ea93c`
- **Source:** `CURRENT_STATE_BENCHMARK_AUDIT.md` (approved planning baseline), Option A, gaps G-02 and G-03
- **Not in this baseline:** `feature/admin-home` (PRs #270–#273). Section 7 covers how this spec interacts with it.

Placeholders such as `{teacher}`, `{date}` and `{term}` stand for values filled in at runtime.

## 1. Scope

| # | Item | Audit gap | Outcome |
| --- | --- | --- | --- |
| A1 | Make NOT_TAKEN attendance rows actionable | G-02 (ANA-01, ADM-06) | Every row says who is responsible and offers the next step the viewer is allowed to take. A missing or broken class-teacher assignment shows up as a configuration problem. |
| A2 | Consecutive-absence insight | G-03 (TEA-04, ANA-02) | Shows "absent N school days in a row" from one shared definition. The admin gets a report and class teachers get a card scoped to their own section. |
| A3 | Link unfinished assessments to their list | G-02 (ANA-03) | The current "Marks entered" ring (renamed "Assessments finalized"), or admin home's "Results to finish" count if that has merged, opens the assessments that are due but not yet finalized. The list matches the count. |

### Out of scope

- No new permissions, groups or roles.
- No change to teacher attendance powers: teachers still take today's register only (ADR 0012 D5) and cannot make corrections (D7).
- No schema changes or migrations.
- No notifications, messages or guardian exposure.
- No fee work.
- No change to the existing "frequent absentees" count (≥3 days in a period). It stays as it is.
- No change to the "Results published" ring.
- No offline or PWA changes.
- No substitute or cover-teacher workflow (ADR 0012 D6 still applies).

## 2. Rules this spec must keep

| Rule | Source | Effect on Option A |
| --- | --- | --- |
| No register means NOT_TAKEN. DRAFT is not official. A missing entry never counts as ABSENT. | ADR 0007; `AttendanceRegister` docstring, `core/models.py:1360` | DRAFT, NOT_TAKEN and missing entries are never counted as absence. |
| Only instructional days count: the weekly pattern plus `SchoolCalendarDay` exceptions. | ADR 0008; `reports.instructional_q`, `reports._year_calendars` | Weekends and holidays are skipped. They neither add to a run nor break it. |
| A class teacher assignment is dated and tied to one academic year. At most one is effective per section and year. | ADR 0011 D2/D3; `SectionClassTeacher`, `core/models.py:2523` | The responsible teacher is looked up by the row's section, date and academic year. |
| Losing teacher status removes access but leaves assignment rows unchanged. | ADR 0011 D14; `authorization.class_teacher_assignments` | If an assignment exists but its teacher is inactive or no longer in the Teachers group, that is a configuration problem. |
| A teacher takes today's register only. Earlier NOT_TAKEN or DRAFT registers are an administrator task. | ADR 0012 D5; `authorization.can_take_attendance`, `core/authorization.py:237` | Past rows are always the office's job. Only today's rows can be the teacher's. |
| Opening today's register when assignments overlap across years is refused for everyone. | Security Gate 3A; `authorization.sole_class_teacher_duty`, `core/authorization.py:203` | Overlapping assignments on today's date are a configuration problem. |
| A teacher sees history only for the section and dates they were assigned. | ADR 0012 D8/D9; `teacher_student_scope`, `core/authorization.py:252` | A teacher's run is clipped to their own section, academic year and assignment start date. |
| Data classes: register state needs `view_attendanceregister`; each student's status needs `view_attendanceentry`; marks need `view_studentresult`. | Security Gate 4B; `core/data_access.py` | Each link is gated by the permission of the page it opens. |
| A card's count and the page it links to must use the same data. | `core/dashboard.py:1-6` | The marks ring count must equal the filtered list. A future home-page count of runs must equal the report. |
| Every route is listed in the route inventory with its permission. | `core/tests/route_permissions.json`; `test_security_gate4b_route_inventory` | The new A2 report route must be added. |

## 3. Product-owner decisions

All decisions are settled. The rest of this spec follows them.

| ID | Decision | Outcome |
| --- | --- | --- |
| OD-1 | Who acts on a NOT_TAKEN row? | **Approved.** Today's row: the class teacher, with the office as fallback. Past rows: the office only (ADR 0012 D5). Any configuration problem: the office. |
| OD-2 | Default run length that gets flagged | **Approved.** 3 instructional days, matching `ABSENTEE_THRESHOLD_DAYS`. The admin report lets the viewer pick 3, 5 or 10. |
| OD-3 | Today's register is not submitted yet | **Approved.** The UNKNOWN grace applies to today only; see the anchor definition in 5.1. |
| OD-4 | A student changes section with no gap between enrollments | **Approved.** The run continues across back-to-back enrollments in the same academic year (admin view). A day with no enrollment breaks the run. A new academic year always breaks it. |
| OD-5 | Subject teachers | **Approved.** Not included in version 1. Only the class teacher sees runs for their own section. |
| OD-6 | Permission for the admin report | **Approved.** `core.view_attendanceentry`, the same as "Daily absent students". |
| OD-7 | Ring wording | **Changed.** The visible label becomes "Assessments finalized, `{term}`" (see 6.2). |
| OD-8 | Order relative to `feature/admin-home` | **Approved.** A1 and A2 on `main` now. A3 after the admin-home decision (section 7). |
| OD-9 | Should the consecutive-absence rule get an ADR? | **Approved.** A short ADR 0026, delivered in PR A2. |

Review decisions applied on top of these:

- A section with overlapping academic years shows only the configuration problem and "Review class teacher". It never offers "Take register".
- A new problem, `ARCHIVED_SECTION`, is added. It never offers a register link that cannot be used.
- The class-teacher link is "Review class teacher", shown with view permission. Assign and end actions on that page keep their existing add and change permissions.
- The anchor is the latest eligible instructional day on or before today. The UNKNOWN grace applies only to today.
- "30+" is shown only when the run may continue past the lookback boundary.
- Sections with overlapping academic years are excluded from the teacher card.
- The A3 acceptance criteria depend on whether admin home has merged.

## 4. A1: Make NOT_TAKEN rows actionable

### 4.1 Current behaviour

- `reports.missing_attendance` (`core/reports.py:204-246`) returns `{date, section, state, register}`. It drops the academic year even though `expected_registers` has it.
- On the Missing attendance report (`core/templates/core/report_missing_attendance.html`), DRAFT rows link to "Open register". NOT_TAKEN rows show only a grey badge, with no action.
- `attendance_register_create` (`core/views.py:4488`) ignores query parameters, so an action link cannot fill in the section and date.

### 4.2 Who is responsible for a row

Add a function `attendance_actions.resolve_missing(rows, today)` in the new module `core/attendance_actions.py`. It adds the following keys to each row, which is a backwards-compatible addition:

| Key | Values |
| --- | --- |
| `owner` | `TEACHER` or `OFFICE` |
| `teacher` | The responsible teacher (User) or `None` |
| `problem` | `None`, `ARCHIVED_SECTION`, `OVERLAPPING_YEARS`, `NO_CLASS_TEACHER` or `TEACHER_CANNOT_TAKE` |
| `problem_label` | Plain wording for the problem |
| `can_take` | Whether a "Take register" link may be offered at all, before the viewer's permission is checked |

The rules are checked in this order. The first one that matches decides the row:

1. **Archived section.** If the section, or its class, is archived (`archived_at` set; ADR 0025), set `problem = ARCHIVED_SECTION`, `owner = OFFICE` and `can_take = False`. A new register cannot use an archived section (`_refuse_archived_on_new`), so no create link is offered.
2. **Overlapping academic years.** If the section is ambiguous on the row's date, set `problem = OVERLAPPING_YEARS`, `owner = OFFICE` and `can_take = False`. The section is ambiguous when either:
   - it is expected on that date in more than one academic year; only one register can exist per section and date, so the cohort is ambiguous. The resolver reads this from the row's `expected_academic_year_ids` (see below), not from the other rows, because a year whose register was submitted no longer has a row; or
   - it has more than one effective class-teacher assignment across all academic years on that date (the `sole_class_teacher_duty` test).

   This applies to past dates as well as today.
3. **No class teacher.** Find the assignment effective on the row's date for its section and academic year (`SectionClassTeacher.objects.effective_on(date)`, filtered by `section_id` and `academic_year_id`). If there is none, set `problem = NO_CLASS_TEACHER`, `owner = OFFICE` and `can_take = True`.
4. **Teacher can't take attendance.** If the assigned teacher is inactive or not in the Teachers group (`is_teacher`), set `problem = TEACHER_CANNOT_TAKE`, `owner = OFFICE` and `can_take = True`. Keep the teacher's name as context.
5. **Past day.** If the date is earlier than today, set `owner = OFFICE` with no problem and `can_take = True`. The teacher is shown for context only, because ADR 0012 D5 means they cannot take a past register.
6. **Otherwise** (today, valid and unambiguous), set `owner = TEACHER` and `can_take = True`.

DRAFT rows go through the same rules, so they also show the teacher and any configuration problem. `can_take` only matters for NOT_TAKEN rows, because a DRAFT row already has a register.

To make this possible, `missing_attendance` changes in two ways:

- **Return the year and every year expected that day.** Each row gains two keys, which existing callers ignore:
  - `academic_year_id`: the row's own year.
  - `expected_academic_year_ids`: a sorted tuple of every academic year in which the section is expected on the row's date.

  The second key is calculated from the complete `expected_registers(...)` set, grouped by (date, section), **before** any submitted register removes rows. That matters because after year-aware matching, a year whose register was submitted has no row of its own. Without this field, `resolve_missing` would see a single row and miss the overlap. A row is overlapping when `len(expected_academic_year_ids) > 1`. Building the field is in-memory work on the set the function already computes, so it adds no query.

  When `missing_attendance` is called with `academic_year=` (Security Gate 3A), the returned rows are still limited to that year. But `expected_academic_year_ids` is taken from the unfiltered expected set, so the overlap stays visible.
- **Match registers by (date, section, academic year).** Today it builds `registers` keyed by `(date, section_id)` (`core/reports.py:223`). With overlapping years, one register can therefore satisfy both years' expected rows. The key becomes `(date, section_id, academic_year_id)`, so a register only satisfies the expected row for its own year.

Effect on counts:

- **Normal data, one academic year per section and date:** every count is unchanged. That covers the Missing attendance report, the dashboard "Attendance today" card (which counts distinct sections), the "Registers today" ring and admin home's not-taken rows. Each expected row matches the same register as before.
- **Invalid data, a section expected in two overlapping years on one date:** the year with no register of its own now produces an extra row on purpose, carrying the `OVERLAPPING_YEARS` problem. Before, that row was silently hidden by the other year's register. Counts built from these rows may therefore go up for that section, by design:
  - the report row count;
  - the dashboard card's distinct-section count, when the other year's register was already submitted;
  - admin home's not-taken rows.

  The extra row exists so the office can see the configuration problem. It only appears when the data is already invalid.

**Query limit.** The function must run a fixed number of queries no matter how many rows there are:

1. One query for the assignments covering every section in the rows across the date range, across all years, with `select_related("teacher")`. Rule 2's assignment test and rule 3 both read from it.
2. One query for Teachers-group membership of those teachers.
3. One query for the `AcademicYear` records named in the rows: the union of every row's `academic_year_id` and `expected_academic_year_ids`, loaded with `in_bulk`. The year-labelled "Review class teacher" links for `OVERLAPPING_YEARS` (4.3) use it. It is skipped when no row is overlapping.

That is at most three queries on top of `missing_attendance` itself, whatever the number of rows. Archive state comes from the `section__class_grade` rows the report already loads, and rule 2's expected-years test uses `expected_academic_year_ids`. Neither adds a query.

### 4.3 Next steps shown to the viewer

Each action appears only if the viewer has the permission required by the page it opens:

| Action | Shown when | Opens | Permission |
| --- | --- | --- | --- |
| "Waiting for `{teacher}`", as text | `owner = TEACHER` | — | `view_attendanceregister` (already needed for the report) |
| The teacher's name as a link | A teacher is known | `core:teacher-detail` | `accounts.manage_teacher_accounts` |
| "Take register" | The row is NOT_TAKEN **and** `can_take` is true. Never shown for `ARCHIVED_SECTION` or `OVERLAPPING_YEARS`. | `core:attendance-register-create?academic_year=…&class_grade=…&section=…&date=…` | `core.add_attendanceregister` |
| "Open register" (existing) | The row is DRAFT | `core:attendance-register-detail` (read access to an existing record, so it stays usable for archived sections too) | `view_attendanceregister` |
| "Review class teacher" | `NO_CLASS_TEACHER`, `TEACHER_CANNOT_TAKE` or `OVERLAPPING_YEARS` | `core:academic-year-class-teachers`, for the row's year | `core.view_sectionclassteacher` |

- A viewer without the permission for an action sees the status and owner text but not the action.
- "Review class teacher" only opens the existing list page. The assign, end and delete actions on that page keep their own permissions (`core.add_sectionclassteacher`, `core.change_sectionclassteacher`, `core.delete_sectionclassteacher`), and the page decides whether to show them. Option A changes nothing there.
- For `OVERLAPPING_YEARS`, there is one "Review class teacher" link per year in `expected_academic_year_ids`, labelled with that year's name. The names come from the year lookup in 4.2. When the overlap comes only from assignments (a single expected year), the link goes to each year that holds an effective assignment.
- `ARCHIVED_SECTION` has no class-teacher link and no register link, because the fix is to restore the section, not to change the assignment. The row text says the section is archived.
- Nothing is created from a GET request. "Take register" only opens the existing form with fields filled in. The admin still presses **Open register**, and the form and model checks run as they do today: instructional day, not in the future, section belongs to the class, and one register per section per date.

### 4.4 Pre-filling the register form

`attendance_register_create` must pass `initial` on GET using the four query values.

- Each value is converted to the right type (an integer ID or an ISO date). Values that cannot be converted are ignored, with no error shown.
- IDs must exist within each field's current queryset, so a hand-typed link to an archived class or section gives an empty field. The report never builds such a link (rule 1 in 4.2).
- POST handling does not change.

### 4.5 How the row looks

The table keeps its three columns (Date, Section, State). The next step goes inside the State cell, under the badge, so the table still fits a 360 px phone with the existing `.erp-keep` scroll. Example cells:

```
[Not taken]  Waiting for Priya Nair · Take register
[Not taken]  Past day: office to take · Take register        (teacher: Priya Nair)
[Not taken]  ⚠ No class teacher assigned · Review class teacher · Take register
[Not taken]  ⚠ Priya Nair can't sign in as a teacher · Review class teacher · Take register
[Not taken]  ⚠ Two academic years overlap for this section · Review class teacher
[Not taken]  ⚠ This section is archived
[Draft]      Open register · Waiting for Priya Nair
```

- Problem text uses the existing warning tone. Colour is never the only signal: the problem is always written out.
- Every link includes hidden text for screen readers giving the section and date, following the pattern of the existing "Open register" link.
- The dashboard card and the "Registers today" ring keep linking to this report. Their counts do not change.

### 4.6 Edge cases

| Case | Expected |
| --- | --- |
| Assignment ended yesterday and no new one starts today | `NO_CLASS_TEACHER` on today's row. Yesterday's row still shows the old teacher, as context only. |
| Assignment starts tomorrow | `NO_CLASS_TEACHER` today. |
| Open-ended assignment past its year's end | Not effective (`effective_on` stops at the year's end). The row shows `NO_CLASS_TEACHER`. |
| Section expected in two overlapping academic years on a date | `OVERLAPPING_YEARS` on that date, past or today. Only the problem and "Review class teacher" are shown; "Take register" is never offered. |
| Two class-teacher assignments across years effective on one date, even if only one year has enrollments | `OVERLAPPING_YEARS`, with the same display as above. |
| Overlap on one date but not the next | Each date is resolved separately. Rows without the overlap behave normally. |
| Teacher deactivated | `TEACHER_CANNOT_TAKE`. The assignment row is not changed. |
| Day becomes a holiday later | The row disappears (it is no longer expected). |
| Viewer has only `view_attendanceregister` | Sees owner and problem text, with no action links. |
| Section or class archived after the date, NOT_TAKEN | The row is still listed, matching today's report behaviour, with `ARCHIVED_SECTION` and no "Take register". |
| Section archived, DRAFT register exists | `ARCHIVED_SECTION`. "Open register" is still shown, because viewing an existing record works. Whether the register can be submitted is decided by the existing model rules, unchanged. |
| Archived and overlapping at once | `ARCHIVED_SECTION` (rule 1 comes first). |

## 5. A2: Consecutive-absence insight

### 5.1 Definition (the proposed ADR 0026 wording)

For a student, an **eligible day** meets all of the following:

- it is an instructional day in the academic year of the student's enrollment (ADR 0008);
- it is on or before the business date;
- the student has an enrollment effective that day in that year.

The status of an eligible day is:

| Status | Condition |
| --- | --- |
| `ABSENT` / `PRESENT` | The section has a SUBMITTED register for that date and year, and it has an entry for the student's effective enrollment. This is the same as `reports.reportable_entries`. |
| `UNKNOWN` | The register is missing or still DRAFT, or it is submitted but has no entry for this enrollment. |

**Anchor day.** The anchor is the latest eligible instructional day on or before today.

- If today is eligible, the anchor is today.
- If today is not an instructional day (a weekend or holiday) or the student has no effective enrollment today, the anchor is the latest earlier eligible day.
- **Today-only grace:** if the anchor is today and today's status is `UNKNOWN` (the register is not taken yet or still a draft), the anchor moves back to the previous eligible day and `as_of` records that day.
- The grace applies to today only. If the anchor is an earlier day and its status is `UNKNOWN`, there is no grace: the run is 0 days, stopped by `UNKNOWN`.

A **current run** is counted backwards from the anchor day:
- **Non-instructional days** (weekends, holidays, `SchoolCalendarDay` with `is_instructional=False`) are skipped. They do not count and do not break the run.
- **`ABSENT`** adds one day and the count continues backwards.
- **`PRESENT`** stops the count (`stopped_by = PRESENT`).
- **`UNKNOWN`** stops the count (`stopped_by = UNKNOWN`). The result is shown as "at least N".
- **No effective enrollment** that day stops the count (`ENROLLMENT_GAP`). Back-to-back enrollments in the same year do not count as a gap (OD-4).
- **The academic year's start** stops the count (`YEAR_START`).
- **The lookback limit** caps the count at 30 eligible days. When all 30 are ABSENT, the next earlier day decides what is shown. That day is found from the calendar, enrollment and scope alone, without loading more attendance data:
  - If an earlier eligible day exists inside the same academic year, enrollment chain and scope, the run might continue past the boundary. Set `stopped_by = LOOKBACK_LIMIT` and show "30+".
  - If the boundary is also the year start or an enrollment gap, the run cannot continue. Set `stopped_by` to that reason and show the exact count, 30.
  - If the boundary is the teacher's scope start, set `stopped_by = SCOPE_START` and show "at least 30". The run may continue before the teacher's assignment; the teacher just cannot see it.
- **The teacher's assignment start** stops the count in the teacher's view (`SCOPE_START`, ADR 0012 D9). This is never an exact boundary: it is always shown as "at least N", because the student may have been absent before the teacher's assignment began.
- **Future days** are never considered.

A student is flagged when `days ≥ threshold`. `days` counts only `ABSENT` days.

**Corrections and calendar edits.** The run is computed on every request from the current entry status. `AttendanceEntry.record_status_change` updates `status` in place and writes an `AttendanceCorrection`. A correction, or a new holiday, therefore changes the next result straight away.

**No caching.** The result must not be cached in `nav_badges` or anywhere else.

### 5.2 Result shape

`attendance_insights.absence_runs(enrollments, today, *, threshold, lookback=30, scope_start=None)` returns a list sorted by `days` (highest first), then by name. Each item has:

| Field | Meaning |
| --- | --- |
| `student_id`, `name`, `class_name`, `section_name` | Who the student is |
| `days` | Number of ABSENT days in the run |
| `first_date`, `last_date` | Earliest and latest ABSENT days in the run |
| `as_of` | The anchor day |
| `stopped_by` | One of the stop reasons in 5.1 |
| `at_least` | True when `stopped_by` is `UNKNOWN`, `LOOKBACK_LIMIT` or `SCOPE_START` |
| `unknown_date` | The day attendance was not taken, when `stopped_by = UNKNOWN` |

`scope_start` maps each enrollment to its earliest allowed date. The teacher view uses it.

### 5.3 How the queries work

The number of queries stays fixed regardless of student count, and the tests check this with `assertNumQueries`:

1. **Candidates:** students in scope with at least `threshold` reportable ABSENT entries in the lookback window, from one grouped query over `reports.reportable_entries`. Nobody else can reach the threshold, so the rest of the work stays small.
2. **Enrollments** of the candidates in the window: student, year, class, section, start date and end date.
3. **Year calendars** for the window, reusing `reports._year_calendars`. This is two queries.
4. **Registers** in the window for the sections involved: date, section, year and status.
5. **Entries** for those registers and enrollments, filtered to submitted registers: enrollment, date and status.
6. **Count in Python:** for each candidate, step back through calendar dates using the in-memory calendar and the lookups above. At most `lookback` eligible days are visited per candidate.

No raw SQL is needed. Behaviour must be the same on PostgreSQL 16, which CI uses, and on local SQLite. Week-day logic lives in Python, through `_YearCalendar.is_instructional`, so it cannot differ between databases.

### 5.4 Who sees what

| Viewer | Scope | Route or surface | Guard |
| --- | --- | --- | --- |
| Administrator | Enrollments effective today with student status ACTIVE, optionally filtered by section | New report `core:report-absence-runs` at `attendance/reports/absent-in-a-row/` | `administrator_required("core.view_attendanceentry")` (OD-6) |
| Class teacher | Enrollments effective today in sections where `class_teacher_assignments(user, today)` holds, matched by year. Sections with overlapping academic years today are excluded (see below). | A card on `my_home` | `teacher_required`. Clipped by `scope_start = max(enrollment.start_date, assignment.start_date)` |
| Subject teacher | None in version 1 (OD-5) | — | — |
| Guardian | None | — | — |

- The admin report is filtered by the user's permission only. There is no extra data scoping beyond what the existing attendance reports do.
- On the admin report, the student name links to `core:student-attendance`, which requires `view_attendanceentry`, the same permission as the report. The day-by-day history is there.
- On the teacher card, each row links to `core:my-student-detail`. That page already checks `teacher_student_scope`.
- **Ambiguous sections are left out of the teacher card.** A teacher's section is ambiguous today when either:
  - it has more than one effective class-teacher assignment across all academic years today (the `sole_class_teacher_duty` test fails); or
  - it has enrollments effective today in more than one academic year.

  Such a section contributes no rows, even for the year the teacher is assigned to. This matches the Gate 3A rule that an ambiguous cohort is refused for everyone until an administrator resolves it. The administrator report still lists these students, because the admin view is not scoped by class-teacher assignment.

### 5.5 How it looks

**Admin report (desktop and phone).** It is listed on the Attendance reports page as "Absent in a row".

- Filter bar: Section (optional) and "At least" (3, 5 or 10 school days). It uses the same toolbar pattern as Missing attendance.
- Table columns: Student, Class, School days in a row, Since. A note appears under the days when needed, for example "At least 4. Not taken on 12 Nov" or "30+".
- The table uses `.erp-keep` with a scroll region, like the other attendance reports.
- Empty state: "No student has been absent 3 or more school days in a row (as of 20 Nov 2026)."
- An explanation line under the heading says: "Weekends and holidays are skipped. A day whose register was not submitted stops the count."

**Teacher card on My Home (phone first).** It appears only when at least one student in the teacher's section meets the threshold. There is no empty card, which keeps the home page calm.

```
Absent in a row
  Arjun K        4 school days  ›
  Meera S   at least 3 days     ›
```

- The rows are tappable links at least 44 px high, using the existing menu-row pattern.
- The card sits after today's attendance card on My Home.

**Admin home page.** No change on `main` in A2. The home-page entry point ("N students absent 3+ school days in a row" linking to the report) is added in step A3, on whichever home page exists then. See section 7.

### 5.6 Edge cases

| Case | Expected |
| --- | --- |
| A A A then P (newest last) | 0 days. The run is over. |
| P A A A | 3 days, stopped by PRESENT. |
| A A [Sat, Sun] A | 3 days. The weekend is skipped. |
| A [holiday] A A | 3 days. |
| A [NOT_TAKEN] A A | 2 days, at least, with "not taken on `{date}`". |
| A [DRAFT] A A | Same as NOT_TAKEN. |
| Submitted register with no entry for the student (enrolled late, backdated) | Treated as UNKNOWN, which stops the count. |
| Today's register not taken; the last 3 school days ABSENT | 3 days, as of the previous school day. |
| Today's register submitted with the student PRESENT | 0 days. |
| A day later turned into a holiday | Skipped on the next request. The run can get longer. |
| ABSENT corrected to PRESENT in the middle of a run | The run shortens on the next request. |
| PRESENT corrected to ABSENT | The run can get longer. |
| Enrollment starts after a run of absences in a previous enrollment, with a gap day | Stops at the gap. |
| Transfer with back-to-back enrollments | The run continues across both (admin view). The teacher view is clipped to the teacher's own section. |
| New academic year | Stops at `YEAR_START`. Never crosses years. |
| Teacher assigned mid-run | The teacher sees "at least N" from their assignment start. The admin sees the whole run. |
| Student withdrawn (enrollment ended) | Not listed: they have no enrollment effective today. |
| Future-dated entries | Impossible by model rule, and excluded anyway by `≤ today`. |
| Today is Sunday; Fri, Thu and Wed ABSENT | 3 days. The anchor is Friday, the latest eligible day. |
| Today is Sunday; Friday's register never taken | 0 days, stopped by UNKNOWN. The grace is for today only. |
| Today is a school day, register not taken; yesterday NOT_TAKEN too | 0 days, stopped by UNKNOWN. Today is skipped by the grace; yesterday gets no grace. |
| 30 ABSENT days and an earlier eligible day exists | "30+" (`LOOKBACK_LIMIT`). |
| 30 ABSENT days and the 30th is the first school day of the year | "30" (`YEAR_START`), not "30+". |
| 30 ABSENT days and the 30th is the enrollment start | "30" (`ENROLLMENT_GAP`), not "30+". |
| Teacher view: 4 ABSENT days back to the teacher's assignment start | "at least 4" (`SCOPE_START`), never an exact 4. |
| Teacher view: 30 ABSENT days and the 30th is the teacher's assignment start | "at least 30" (`SCOPE_START`). |
| Teacher card: section with overlapping academic years today | Section left out of the card. The admin report still lists the students. |
| Saturday instructional in one year and not another | Each enrollment uses its own year's calendar. |

## 6. A3: Link unfinished assessments to their list

### 6.1 Current behaviour

`analytics.completion_rings` (`core/analytics.py:319-399`) counts the assessments in `ring_term` with `assessment_date ≤ today` and compares the FINALIZED ones with the total. It always sets `"url": None` (`core/analytics.py:364`). The assessments list (`academic_year_assessments`, `core/views.py:646`) can filter by term, section and status, but not by "due by today". A link with `status=DRAFT` alone would also list future drafts, so the count and the destination would disagree.

### 6.2 Change

Step 1 always applies. Steps 2 to 4 apply only if `feature/admin-home` has not merged when A3 starts. If it has merged, the ring no longer exists and step 5 applies instead.

1. **New filter.** Add `due = BooleanField(required=False, label="Due by today")` to `AssessmentFilterForm` (`core/forms.py:792`). The view calls `business_today()` once per request and stores it in a local `today`. When `due` is set, it filters `assessment_date__lte=today`, and passes the same `today` to any progress filter (step 5). It shows up in the filter bar and in the filter labels (`FilterLabelsMixin`), so the destination states what it is showing.
2. **Ring link.** `completion_rings` gets a new keyword argument `assessments_url=None`. `admin_overview` passes `reverse("core:academic-year-assessments", args=[term.academic_year_id])` only when the user has `core.view_assessment`. The ring URL becomes `{url}?term={term_pk}&status=DRAFT&due=1`.
   - The ring itself still needs `view_studentresult`.
   - The link needs `view_assessment`.
   - A viewer with only `view_studentresult` sees the ring without a link.
3. **Wording (OD-7).** The visible label changes from "Marks entered, `{term}`" to "Assessments finalized, `{term}`". The accessible name of the linked ring is "Assessments finalized, `{term}`: `{done}` of `{total}`. Open the `{remaining}` not finalized." The existing UI string tests that pin the old label are updated in the same PR.
4. **Count parity.** The count of the filtered list must equal `total − finalized` from the ring. A test enforces this. The ring counts every due DRAFT, including ones ready to finalize, so this link uses `status=DRAFT&due=1` without the progress filter from step 5.
5. **Admin home merged: a shared "marking in progress" filter.** `home_academics.results_to_finish` splits the term's due DRAFT assessments in two:
   - **Ready to finalize:** the assessment has a roster and every enrollment on it has a result.
   - **Marking in progress (`in_progress`):** everything else, meaning no roster yet, or at least one enrollment with no result.

   A generic `status=DRAFT&due=1` list contains both groups, so `due=1` alone cannot match the `in_progress` count. A3 therefore adds:

   - **A shared query module.** New `core/assessment_progress.py` holds one place for the rules:
     - `roster_subquery()`: today's `home_academics._roster()`, moved here unchanged. It returns enrollments in the assessment's year, class and section, effective on the assessment date.
     - `annotate_progress(queryset)`: adds `has_roster` and `has_unmarked`, using the same `Exists` subqueries as today's `_drafts()`.
     - `marking_in_progress(queryset, *, today)`: DRAFT assessments with `assessment_date__lte=today` and `~Q(has_roster=True) | Q(has_unmarked=True)`.
     - `ready_to_finalize(queryset, *, today)`: DRAFT assessments with `assessment_date__lte=today` and `has_roster=True, has_unmarked=False`.

     `today` is a required keyword argument with no default. Neither function calls `business_today()` itself, so "due" is always an explicit input, and tests pass a fixed date without patching.
   - **One date per request.** Each caller works out the business date once and passes that same value everywhere:
     - `results_to_finish(today, ...)` already takes `today` from its caller (`admin_overview`, which calls `business_today()` once). It passes that `today` to both functions.
     - `academic_year_assessments` calls `business_today()` once at the top, and uses that one `today` for both the `due` filter and the `progress` filter.

     Within one request, the count and the list therefore use the same date even across midnight.
   - **One source for the home tab.** `home_academics._drafts` and `results_to_finish` call these functions instead of their own copies. `in_progress` becomes `marking_in_progress(qs, today=today).count()` for the work term, and the ready rows come from `ready_to_finalize(qs, today=today)`.
   - **A matching list filter.** `AssessmentFilterForm` gets a `progress` choice field with options "" (any), `marking` ("Marking in progress") and `ready` ("Ready to finalize"). `academic_year_assessments` applies it through the same module, passing its single `today`, so the list and the count cannot drift apart. `progress` implies DRAFT and due by `today`. The form refuses `progress` combined with `status=FINALIZED`, showing a field error and applying no filter.
   - **The new link.** `in_progress_url` becomes `{url}?term={term_pk}&status=DRAFT&due=1&progress=marking`.
   - **Required count parity.** For the same term and date, `results_to_finish(...)["in_progress"]` equals the number of rows the list returns for `in_progress_url`. A test enforces this, and also checks that a ready-to-finalize assessment is excluded from that list.

The "Results published" ring stays without a link, which is out of scope.

### 6.3 Edge cases

| Case | Expected |
| --- | --- |
| All due assessments finalized | The ring shows 100% and the link opens an empty list with the existing empty state. |
| `ring_term` is a term that has ended and a new term has not started yet | The link points at that term, in the year that term belongs to. |
| Draft assessment dated in the future | Not counted and not listed (`due=1`). |
| Invalid `due` value | The form is invalid. The existing invalid-filter behaviour applies and no filter is used. |

## 7. Interaction with `feature/admin-home`

**State checked on 2026-11-21:**

- PR #270 is a draft umbrella and never merges to `main` on its own.
- #271 and #272 are merged into the branch; #273 is open into it.
- The branch tip is `1120153` (before #273).
- The branch adds migration `0094_school_register_cutoff`. Option A adds no migration, so there is no clash.

| Area | On the branch | Effect on Option A |
| --- | --- | --- |
| Today tab register rows | `core/home_today.py` builds unsubmitted rows from `reports.missing_attendance(today, today)`. It gets teacher names from `_class_teachers(today)`, a dictionary keyed by section only. That dictionary ignores the academic year, has the last row win when years overlap (Gate 3A), and ignores whether the teacher is still valid. `_register_url` sends NOT_TAKEN rows to an empty create form. | After both are on `main`, `home_today` should call `attendance_actions.resolve_missing` and use the pre-filled create URL from A1, replacing `_class_teachers` and `_register_url`. This should be one small follow-up change, in A3. |
| Register cut-off / late registers | `register_compliance` uses the school's `register_cutoff`. | No conflict. A1 does not use the cut-off. |
| Rings | The branch **removes** `completion_rings`, `_ring.html` and `_attendance_analytics.html`. | Changing the ring on `main` would be thrown away once admin-home merges. The lasting part of A3 is the `due` filter. |
| Academics tab "in progress" link | `home_academics.results_to_finish` counts only the due drafts that are still being marked (no roster, or an unmarked enrollment). Ready-to-finalize drafts are listed separately. But the link goes to `?term=…&status=DRAFT`, which lists every draft, including future and ready ones. | A3 moves the roster and unmarked rules into `core/assessment_progress.py`, adds the `due` and `progress` filters, and points `in_progress_url` at `status=DRAFT&due=1&progress=marking`. The count and the destination then come from the same query (6.2 step 5). |
| Absentees | `frequent_absentees` and `absent_day_counts` stay; the Attendance tab uses a month-to-date period. | A2 does not change them. The home-page entry for runs is added to the Attendance tab in A3. |
| Files touched by both | `core/views.py`, where A1 changes `attendance_register_create`, A2 adds a view and A2 changes `my_home`, all in functions the branch does not change. Also `core/forms.py` (a different class), `core/analytics.py` (A3 only) and `route_permissions.json` (a new key, an easy merge). | Conflicts are small and limited to those spots. |

**Recommended order (OD-8).** One PR at a time, following the existing working rule:

1. **PR A1:** missing-attendance actions and the pre-filled create form. Goes on `main` and touches nothing the branch reworks.
2. **PR A2:** ADR 0026, `core/attendance_insights.py`, the admin report, and the teacher My Home card. Goes on `main`.
3. Merge `feature/admin-home` to `main` when the product owner says so, after their local test.
4. **PR A3:** the `due` filter, plus home-page wiring on whichever home page exists then:
   - if admin-home has merged: the shared `core/assessment_progress.py`, the `progress` filter, `in_progress_url` with `status=DRAFT&due=1&progress=marking`, the Today tab using `resolve_missing`, and an "Absent in a row" row in the Attendance tab;
   - otherwise: the ring link on the current Overview.

## 8. Files affected

| File | PR | Change |
| --- | --- | --- |
| `core/reports.py` | A1 | `missing_attendance` rows gain `academic_year_id`, and registers are matched by (date, section, academic year). |
| `core/attendance_actions.py` (new) | A1 | `resolve_missing(rows, today)`. |
| `core/views.py` | A1 | `report_missing_attendance` calls `resolve_missing`. `attendance_register_create` takes GET `initial`. |
| `core/templates/core/report_missing_attendance.html` | A1 | Next-step line, action links and problem text inside the State cell. |
| `docs/adr/0026-consecutive-absence-definition.md` (new) | A2 | The rule from 5.1. |
| `core/attendance_insights.py` (new) | A2 | `absence_runs(...)`. |
| `core/views.py` | A2 | New view `report_absence_runs`. `my_home` adds the class-teacher card context. |
| `core/forms.py` | A2 | `AbsenceRunsForm` (section and threshold). |
| `core/urls.py` | A2 | `attendance/reports/absent-in-a-row/`. |
| `core/tests/route_permissions.json` | A2 | New route entry (`core.view_attendanceentry`). |
| `core/templates/core/report_absence_runs.html` (new) | A2 | The report page. |
| `core/templates/core/attendance_reports.html` | A2 | A link to the new report. |
| `core/templates/core/my_home.html` (or its partial) | A2 | The "Absent in a row" card. |
| `static/css/erp.css` | A2 (only if needed) | Reuse existing row and table classes. New CSS triggers the `test_ui*` string tests. |
| `core/forms.py` | A3 | The `due` field on `AssessmentFilterForm`. If admin home has merged, also the `progress` field and its check against `status`. |
| `core/assessment_progress.py` (new, only if admin home has merged) | A3 | The shared roster and unmarked rules: `roster_subquery`, `annotate_progress`, `marking_in_progress(queryset, *, today)`, `ready_to_finalize(queryset, *, today)`. |
| `core/tests/test_assessment_progress.py` (new, only if admin home has merged) | A3 | Tests for the shared rules, count parity, and the ready-to-finalize exclusion. |
| `core/views.py` | A3 | `academic_year_assessments` applies `due`. `admin_overview` passes `assessments_url` (if the ring still exists). |
| `core/analytics.py` or `core/home_academics.py` / `core/home_today.py` | A3 | Ring link, or the admin-home wiring (section 7). |
| `docs/ROADMAP.md`, `docs/PERMISSIONS.md` | A1–A3 | Note the new report route and its permission, and the teacher card scope. |

No changes to models, migrations, dependencies, settings, CI or deployment.

## 9. Test plan

Tests are written before the code in each PR. CI runs the full suite on PostgreSQL 16. Locally, run lint plus the changed test files; per the project rule, run the full local suite only for PR A2, because it changes the route inventory, which counts as a permissions change.

### PR A1: `core/tests/test_missing_attendance_actions.py`

**Resolver tests:**

- one test per rule in 4.2: valid teacher today gives TEACHER; past date gives OFFICE; no assignment; ended assignment; future-start assignment; teacher inactive; teacher removed from the Teachers group;
- `ARCHIVED_SECTION` for an archived section and for an archived class, with `can_take = False`;
- `OVERLAPPING_YEARS` with `can_take = False` in each case: section expected in two years on a past date; on today; two assignments across years with only one year enrolled;
- rule order: archived and overlapping at once gives `ARCHIVED_SECTION`;
- register matching by year:
  - a section expected in years X and Y on one date, with a submitted register for X only, gives exactly one row (for Y), carrying `OVERLAPPING_YEARS`;
  - with normal single-year data, the rows and the dashboard card count are identical before and after the change;
- DRAFT rows get the same resolution;
- a fixed number of queries for 1 row and for 20 rows.

**View tests:**

- for each permission combination (`view_attendanceregister` only; plus `add_attendanceregister`; plus `manage_teacher_accounts`; plus `view_sectionclassteacher`), each link appears only when that permission is held;
- "Take register" never appears on `OVERLAPPING_YEARS` or `ARCHIVED_SECTION` rows, even for a superuser;
- "Review class teacher" appears with `view_sectionclassteacher` alone. On the destination, assign and end controls still follow `add_sectionclassteacher` and `change_sectionclassteacher` (existing tests stay green);
- no link to a page the viewer would get a 403 on.

**Pre-fill tests:**

- valid parameters fill the form;
- an invalid ID or date is ignored with no error;
- an archived section is not pre-selected;
- GET creates no register;
- POST is unchanged, including the existing redirect when a register already exists.

**Regression:**

- With normal single-year data, the existing Missing attendance, dashboard and "Registers today" tests pass unchanged, and every count is unchanged.
- With overlapping-year data, the additional `OVERLAPPING_YEARS` row is produced on purpose. Counts built from those rows can change for the affected section: the report row count, the dashboard card's distinct-section count and admin home's not-taken rows. Tests assert the new values for that case, rather than the old ones.

**Overlap field:**

- `expected_academic_year_ids` lists both years on the remaining row even when the other year's register was submitted;
- it keeps both years when `missing_attendance` is called with `academic_year=`;
- the year lookup runs once, and only when an overlapping row exists, within the 4.2 query limit.

### PR A2

**`core/tests/test_absence_runs.py`:**

- every row in 5.6, using a fixed `business_today` (patch where the module imports it; see the note on date capture in parallel tests);
- correction recalculation through `record_status_change`;
- a holiday added after the fact;
- `SCOPE_START` clipping;
- anchor cases: today eligible; today a weekend or holiday; today not taken (grace); an earlier anchor UNKNOWN (no grace);
- lookback boundary: "30+" only when an earlier eligible day exists; an exact 30 at the year start and the enrollment start; "at least 30" at the scope start;
- `SCOPE_START` at any length is shown as "at least N", never as an exact count;
- a fixed number of queries with 5 and with 50 candidates.

**`core/tests/test_absence_runs_views.py`:**

- the admin report returns 403 without `view_attendanceentry`;
- filters (section, threshold) and the empty state;
- the student link goes to `student-attendance`.

**Teacher card tests:**

- a class teacher sees only their section's students, for their year;
- a subject teacher sees no card;
- a teacher whose assignment has ended sees no card;
- an overlapping-year cohort is not shown (Gate 3A);
- a section that is ambiguous today (two assignments across years, or enrollments in two years) contributes no rows, while the admin report still lists the same students;
- a deactivated teacher is refused (existing `teacher_required`).

**Inventory:** `test_security_gate4b_route_inventory` passes with the new route entry.

**Guardian:** a guardian session cannot reach the report (the existing route guard test pattern).

### PR A3

Which tests apply depends on whether `feature/admin-home` has merged into `main` when A3 starts. Only one of the two branches below is written.

**Always: `core/tests/test_assessment_due_filter.py`:**

- `due=1` excludes future drafts;
- combines with term, status and section;
- an invalid value applies no filter.

**Branch 1, admin home has not merged (the current Overview ring):**

- **Count parity:** for a fixture term containing future drafts, past drafts and finalized assessments, the ring's `total − done` equals the filtered list count.
- **Link permissions:** the ring link appears only with `view_assessment`; the ring is hidden without `view_studentresult` (existing behaviour).
- **Wording:** the label reads "Assessments finalized, `{term}`" and the accessible name matches 6.2.
- **Existing tests:** the `test_admin_overview_analytics` assertions that the marks ring has `url: None`, and any `test_ui*` strings pinning "Marks entered", are updated.

**Branch 2, admin home has merged (no ring exists):**

- **Fixture:** in the work term, include:
  - one finalized assessment;
  - one future-dated draft;
  - one due draft with no roster;
  - one due draft with an unmarked enrollment;
  - one due draft that is ready to finalize (roster present, every enrollment has a result).
- **Count parity:** `results_to_finish(...)["in_progress"]` equals the number of rows listed at `in_progress_url`. For the fixture, that is 2.
- **Ready-to-finalize exclusion:** the ready draft appears in `results_to_finish(...)["ready"]` and does **not** appear in the list at `in_progress_url`.
- **Destination:** `in_progress_url` includes `term`, `status=DRAFT`, `due=1` and `progress=marking`. The list excludes the future draft and the finalized assessment.
- **Explicit date:** a draft dated tomorrow is excluded with `today=D` and included with `today=D+1`, without patching `business_today`. Calling either function without `today` is a `TypeError`.
- **One date per request:** the assessment-list view, with `business_today` patched to D, applies D to both `due` and `progress`, so a draft dated D+1 is excluded from both.
- **Shared rules:** `core/tests/test_assessment_progress.py` checks `marking_in_progress` and `ready_to_finalize` directly:
  - an enrollment that ends before the assessment date is not on the roster;
  - an enrollment starting after the assessment date is not on the roster;
  - an ABSENT result counts as marked.
- **Form:** `progress=ready` lists only ready drafts. `progress` with `status=FINALIZED` is a form error and applies no filter.
- **Regression:** the existing admin-home `test_home_academics` tests pass unchanged after `_drafts` moves to the shared module.
- **Link permissions:** the link appears only with `view_assessment`.
- **Ring:** no ring tests are written, and the ring wording change (OD-7) is not applied, because the ring no longer exists.
- **Today tab:** if it is switched to `resolve_missing` in this PR, the A1 resolver cases are repeated through the Today tab rows: no "Take register" for `OVERLAPPING_YEARS` or `ARCHIVED_SECTION`.

**Phone check:** after each PR, a manual check at 360 px and 390 px of the changed pages. Screenshots come from a fresh `collectstatic` (see the note on stale static files).

## 10. Acceptance criteria

1. Every NOT_TAKEN and DRAFT row on Missing attendance shows who is responsible (class teacher or office), or a named configuration problem.
2. A NOT_TAKEN row offers "Take register" only when the row has no `ARCHIVED_SECTION` or `OVERLAPPING_YEARS` problem and the user has `core.add_attendanceregister`. The link opens the register form already filled in with year, class, section and date, and does not create anything until the form is submitted.
3. No user gains a power: teachers still cannot open past registers or correct submitted ones, and every link is hidden from users who would get a 403 at its destination.
4. Missing, ended, not-yet-started and invalid-teacher assignments each produce their own wording, a "Review class teacher" link for users with `view_sectionclassteacher`, and "Take register" where allowed.
5. A section with overlapping academic years on a date shows only the `OVERLAPPING_YEARS` problem and "Review class teacher", never "Take register". An archived section or class shows only `ARCHIVED_SECTION`, with no register-creation or class-teacher link.
6. Assign, end and delete actions on the class-teacher page keep their existing add, change and delete permissions.
7. For every case in 5.6, the consecutive-absence count follows 5.1:
   - the anchor is the latest eligible instructional day on or before today, with the UNKNOWN grace for today only;
   - weekends and holidays are skipped;
   - ABSENT extends the run;
   - PRESENT, UNKNOWN, an enrollment gap, the year start and the scope start stop it;
   - future days are never counted;
   - "30+" appears only when an earlier eligible day exists past the lookback boundary.
8. Correcting an attendance entry or changing the school calendar changes the next result with no manual refresh step.
9. Administrators with `view_attendanceentry` can open "Absent in a row" from Attendance reports. Class teachers see the card only for their own unambiguous section and assignment window. Sections with overlapping academic years are left out of the card. Subject teachers and guardians see nothing new.
10. A3, depending on the admin-home state when A3 starts:
    - **If admin home has not merged:** the current Overview ring is labelled "Assessments finalized, `{term}`" and links only for users with `view_assessment`. Its destination lists exactly the ring's not-finalized, due-by-today assessments for that term.
    - **If admin home has merged:** no ring work is done.
      - The Academics tab's "Results to finish" in-progress count and its destination list both come from `core/assessment_progress.marking_in_progress(queryset, today=...)`, each with a single `business_today()` value worked out once per request, and the counts are equal.
      - The link carries `status=DRAFT&due=1&progress=marking`.
      - A ready-to-finalize assessment is excluded from that list.
      - The link appears only for users with `view_assessment`.
11. Missing attendance matches registers by (date, section, academic year). With normal data, every existing count is unchanged. With overlapping-year data, the year without its own register appears as an extra row carrying `OVERLAPPING_YEARS`.
12. All new queries stay fixed in number regardless of row or student count, and tests prove it.
13. The pages work at 360 px with no horizontal page scroll beyond the existing table scroll regions. Links have accessible names that include the section and date, or the student.
14. No migrations, no new permissions, and route inventory and CI are green on the PR's latest commit before any merge.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| The run definition is read as "at least 3 calendar days" | The report explanation line and the ADR say "school days". The wording on screen says "school days in a row". |
| A run longer than the lookback is under-reported | "30+" is used only when the run may continue past the lookback boundary. When the boundary is the year start or an enrollment gap, the exact count is shown, because the run cannot be longer. At the teacher's scope start, it is shown as "at least N". |
| Names of teachers who can't sign in are shown on reports | Only to users who already see the report (`view_attendanceregister`). No contact details are shown. |
| Admin-home merge conflicts | Option A is split so that only A3 touches the home pages, and A3 waits for the merge decision. |
| Wrong dates in parallel test runs | Patch `business_today` where each new module imports it, as noted for earlier date-capture failures. |

Stop point: this specification is for review only. No code, tests or migrations have been written, and nothing has been committed.
