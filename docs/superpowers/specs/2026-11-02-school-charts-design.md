# School charts: design

Status: **Approved by the product owner 2026-11-02. Decisions D1-D4 made.**
Date: 2026-11-02
Mockups: `.superpowers/brainstorm/2755-1793591243/content/combined-v1.html` (placement) and `chart-ideas.html` (chart types). Sample data only.
Visual reference: Figma community file "59 Charts UI" (`nc72XY7SkTh9SaZYtmPHsu`), for its card layout only.

## Why

The Overview's sideways bars stretch across the screen when the sidebar closes, which looks wrong. The product owner also wants a richer set of charts that help admins and teachers act: progress rings, horizontal bars, vertical columns, a bullet chart for one student, a radar of one student's strengths across subjects, donuts and a gauge.

Success means every chart answers one clear question, looks right at any screen width, and leads to something the reader can do.

## Goals

1. Rebuild the Admin Overview with the approved charts, on desktop and phone.
2. Add a progress section to the admin student page: bullet chart, radar, attendance by month.
3. Add a "Needs attention" list to the Overview.
4. Add a Term 1 vs Term 2 comparison to the radar.
5. Bring the same charts to the teacher area, limited to what each teacher may already see.
6. Add a printable one-page progress summary for parent meetings.

## Non-goals

- No personal-skill ratings (teamwork and so on). "Strengths" means strengths across subjects, from existing marks. Nothing new is recorded by teachers.
- No charts in the Guardian Portal.
- No change to official report cards, `TermPublication` snapshots or the report-card PDF.
- No rank, GPA, position or weighting.
- No fee or homework charts, because that data doesn't exist.
- No "late" attendance. The only statuses are PRESENT and ABSENT.

## Failure even if it technically works

- Any chart stretches or distorts as the window widens.
- A missing value is drawn as 0%, or an ABSENT result counts as zero.
- A teacher can work out marks they couldn't see before, or someone without marks permission sees marks data.
- A parent could mistake the printed summary for the official report card.
- The Overview gets noticeably slower.

## Decisions already made by the product owner

- Chart types and their placement as shown in `combined-v1.html`.
- Radar axes are subjects, using existing marks.
- Bullet chart uses minimal colours: dark grey for the student, one blue marker for the comparison, light grey for the below-pass area.
- The four extras are in scope: Needs attention, term comparison, teacher version, printable summary.
- Gauge target starts at a fixed 80%, shown as a target until the school can set its own.

- **D1, subject number:** the plain average of each finalized test's percentage in that term, for display only. It's never stored and never appears on official report cards. A new ADR records this as a narrow analytics exception to ADR 0009 ("separate assessments remain separate; no weighted term percentage is invented"). The Overview's `marks_snapshot` already averages this way.
- **D2, teacher averages:** `docs/UI_DESIGN_RULES.md` line 183 ("No totals, weighting, averages or ranks on teacher or guardian result views") gets one exception: the charts on the teacher's student page (`my_student_detail`), using only results that teacher may already see. Gradebook, marks entry and guardian views keep the rule. The same ADR records this and the rules doc is updated.
- **D3, printed marks:** the summary can only be printed for a term once the student has a current, up-to-date PUBLISHED term publication. It never reveals unreleased marks.
- **D4, printed comparison:** no section average on the printed page. Only the student's own marks and the pass mark.

## Data rules

These apply everywhere and follow the existing analytics rules:

- Attendance uses `reports.reportable_entries()`: submitted registers and instructional days only, and a day with no data is left out, never 0%.
- Marks use FINALIZED assessments and MARKED results only. Each score is a percentage of its own assessment's maximum. ABSENT is left out and shown only as a count.
- Dates use `business_today()`.
- Figures are calculated when the page loads. No marks are copied or stored, and no new model or migration is needed.

### Subject score

Per D1. Group by Subject using the existing subject display grouping, so a subject renamed mid-year behaves as the report card does.

### Comparison group

Compare within the student's own section for the same term, since assessments belong to a section. The label is "Section average". *(Designer's call: the mockups say "Class average", but "section" is what's being measured.)* Hide the marker when fewer than 5 students in that section have marks in that subject, so a small section can't reveal one student's marks. *(Designer's call.)*

### Pass mark

`pass_mark` is optional and set per assessment. Convert it to a percentage of that assessment's maximum. For one student, compare like with like: use only the tests that student was MARKED on and that have a pass mark, and apply the D1 rule to both the student's score and the pass mark across exactly those tests. *(Designer's call, so nobody is flagged because of tests they never sat or tests with no pass mark.)* The bullet bar still shows the full subject score, so the bar and the below-pass test can differ slightly. If no such test exists in a subject, draw no below-pass area and leave that subject out of Needs attention.

### Which term

A "reporting term" helper is shared by these features: the term running today if it already has finalized marks for this purpose, otherwise the most recently started term that does. Cards always name the term they show. *(Designer's call.)*

## Admin Overview

Layout on a wide screen, using the existing period controls at the top:

| Row | Cards |
|---|---|
| 1 | Term attendance gauge; Today donut; "Still to finish" rings |
| 2 | Daily attendance line (wide); Heatmap |
| 3 | Attendance by class, upright columns (wide); Frequent absentees |
| 4 | Needs attention (wide); Marks by subject, horizontal bars |
| 5 | Score bands, upright columns |

Row 4 and 5 widths are left to the builder, as long as no row leaves an awkward gap. The "Marks by class" bars and desktop "Today" tiles are replaced. Their figures remain available: Today's register count moves into the ring.

### Card details

- **Gauge:** attendance % for the current term against `ATTENDANCE_TARGET_PERCENT = 80`, a code constant for now. Hidden when no term is running or there's no data.
- **Donut:** today's present and absent counts. Show "No school day today" or "No attendance yet" instead of an empty ring.
- **Rings** (each hidden if the viewer lacks the permission its data needs):
  - *Registers today:* submitted out of expected, from `today_strip`. Links to the missing attendance report.
  - *Marks entered:* in the current term, assessments dated today or earlier that are FINALIZED, out of all assessments dated today or earlier.
  - *Results published:* students with a current PUBLISHED term publication, out of students actively enrolled in that term.
  - *Between terms:* these two rings use the most recently ended term and name it, because publishing usually happens after a term ends. They're hidden only if no term has started. *(Designer's call.)*
- **Attendance by class:** columns ordered by class, not by performance. Under 80% is red and also labelled with its value. Each column links to that class's page.
- **Marks by subject:** school average per subject for the latest term with results, lowest first. Long subject names get horizontal bars, with a maximum width so they can't stretch.
- **Score bands:** existing `marks_snapshot` bands drawn as columns.

## Needs attention

Lists active students who are below the pass mark in 2 or more subjects, or below it in 1 subject and also a frequent absentee in the selected period. *(Designer's call on how the two tests combine.)*

- Marks come from the reporting term and absences from the selected period. They are independent, and the row wording names each, for example "Below pass in Maths and Science (Term 1); absent 4 days (last 14 days)". *(Designer's call.)*
- Each row shows the student, class, and the reason in words, and links to the student page.
- Ordered by class, then name, because `docs/UI_DESIGN_RULES.md` says rows are never ranked by performance.
- Shows up to 10 with the true total, like the absentee list.
- Requires both `core.view_student` and `core.view_studentresult`.
- Empty state: "No students need attention right now."

## Student page (admin)

A new "Progress" section on `student_detail`, added to the existing section navigation. Marks charts require `core.view_studentresult`. Attendance by month requires only `core.view_student`.

- **Term selector:** defaults to the latest term with this student's results.
- **Bullet chart:** one row per subject, in stable subject order, not sorted by score. It shows the student's score, section average marker and below-pass area.
- **Radar:** 3 to 8 subjects, always 0-100, stable order. With fewer than 3 or more than 8, show a short note and rely on the bullet chart.
- **Term comparison:** a plain link (`?compare=previous`) swaps the grey outline from section average to the student's previous term. It only appears when both terms share at least 3 subjects, and only those subjects are drawn. Never show more than two outlines.
- **Attendance by month:** upright columns for the student's enrollment in the current academic year. Months with no data are left out.

## Teacher version

Everything comes from what the teacher can already see. The rule is strict: **use the same scope functions as the teacher pages** (`teacher_student_scope`, `_teacher_visible_results`, `can_view_report_card_as_teacher`, `current_teacher_assignments`). Nothing here widens access.

- **`my_home`:** a "Marks entered" ring for the teacher's own assignments, and a class-teacher-only attendance summary for their section.
- **Assessment results page:** a pass and fail donut for one finalized assessment that has a pass mark.
- **`my_student_detail`:** bullet chart and radar built only from results that teacher may see. If that leaves fewer than 3 subjects, a subject teacher simply sees the bullet chart. The section average marker appears only for subjects within that teacher's scope.

The earlier teacher-marks specs say gradebook screens must not show "Total", "Average", "%" or "Rank". Those screens stay as they are, and no charts go on them. Per D2, `my_student_detail` is the only teacher result view that may show averages. The pass and fail donut shows counts, not averages.

## Printable progress summary

A new page, one per student and term, for administrators with `core.view_studentresult` and teachers who pass `can_view_report_card_as_teacher`.

- **Shows:** school name and logo, student, section, term, bullet chart, radar, term attendance, and the teacher's remark if any.
- **Prints** on one A4 page using the browser's print and a print stylesheet. No new PDF generator.
- **Header wording:** "Progress summary. Not an official report card."
- **Colour:** must stay readable in black and white.
- **Comparison:** none (D4). The radar shows the student's outline only.
- **Availability:** per D3, the print link only appears when the term has a current, up-to-date publication. Requesting the page directly without one returns a clear "not available yet" page, not marks.
- **Source of marks and remark:** the published version, so the page always agrees with what guardians see. If `is_partial` is set, the page says some results are still pending.

It is reached from the student page. It's never created, stored or sent automatically, and doesn't touch publication.

## How charts are built

- Server-drawn inline SVG with no chart library and no new JavaScript, like the existing `_trend_svg.html`. Calculation helpers live beside `core/analytics.py`, for example a new `core/charts.py`; templates live in `templates/partials/`.
- **No stretching:** charts keep a fixed height. Bars and columns have a maximum thickness of 24px and horizontal bars have a maximum width. A chart's card can grow, but the marks stay in proportion. SVG text must not scale up with the card.
- **Card layout:** title and period on top, big figure, one-line note, chart, then legend, as in the Figma file.
- **Colours:** existing tokens. Attendance blue `--erp-viz-attendance`, marks orange `--erp-viz-marks`, red `--erp-viz-low` only for attendance under 80%. Bullet and radar use grey plus attendance blue. Run the dataviz palette validator for any new colour.
- **Hover:** a `<title>` on each mark gives the exact value, matching existing charts.
- **Accessibility:** every chart has `role="img"`, a text alternative and a visually hidden list of its values, as the current analytics do. Colour is never the only signal.
- **Clicks:** a link's target must be one the viewer can open. Otherwise, it isn't a link.

## Phones

Must work at 360 and 390 px. No sideways page scroll, and tap targets stay 44px.

- **Admin order:** gauge and donut side by side, rings in one row, Needs attention, attendance by class as horizontal bars (5 lowest, with a link to all), then the existing trend, heatmap, absentees and marks sections. *(Designer's call: existing phone sections stay, so nothing is lost.)*
- **Student page:** bullet chart, then radar, then attendance by month.
- **Printable summary:** reachable on phones, but not designed for phone printing.

## Speed

Add query-count ceiling tests for the Overview and the student progress section, following the existing analytics tests. Calculations use ORM aggregation with no per-student or per-subject query loops. Needs attention has the highest risk, and must stay a constant number of queries however many students there are.

## Constraints

- No migrations and no new dependencies.
- Follow existing permissions (`administrator_required`, `teacher_required`).
- `core/tests/test_ui_*.py` pin exact CSS text, so run `--pattern="test_ui*.py"` after CSS edits.
- Run `collectstatic` and restart the server before UI screenshots.
- Merge only on green CI and the product owner's say-so.
- Existing behaviour stays unless replaced above, including the period filter and the 14-day default.

## Delivery stages

Each stage is its own PR, checked at 360, 390, 1440 and 1920 px with the sidebar open and closed.

0. **Check staging** after the recent Overview merges, before changing anything.
1. **Foundations and Overview attendance:** chart helpers and partials, card layout, gauge, donut, rings, class columns. Fixes the stretching.
2. **Overview marks and Needs attention:** the new ADR and rules doc change (D1, D2), subject score, marks by subject, score band columns, Needs attention.
3. **Student page:** bullet chart, radar, attendance by month.
4. **Term comparison.**
5. **Teacher version.**
6. **Printable summary.**

## Left to the builder

File names, exact card widths on medium screens, class names, how helper functions are divided, and test structure.
