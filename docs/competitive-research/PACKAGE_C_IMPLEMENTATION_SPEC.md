# Package C Implementation Specification: Admin Phone Coverage

- **Status:** Product-owner decisions OD-C1 to OD-C6 approved (23 November 2026, §3), with the
  clarifications in §2, §4, §5 and §7. Pending independent documentation review before the spec
  is marked Approved. No implementation PR starts until then.
- **Gap:** G-04 (ADM-08, MOB-01), recommended next in `OPTION_A_B_BENCHMARK_CLOSEOUT.md` §5.
- **Source audit:** `PACKAGE_C0_ADMIN_PHONE_AUDIT.md` (findings C0-01 to C0-09, route inventory).
- **Baseline:** `main` at `16e2341`. Line numbers refer to that commit.
- **Companion documents:** `docs/DESIGN_SYSTEM.md`, `docs/UI_DESIGN_RULES.md`,
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md`, `OPTION_B_IMPLEMENTATION_SPEC.md` §9.5.

## 1. Scope

Package C fixes the admin pages where a phone shows a table without its key value or its action,
plus the long lists and tall filters that slow phone work down. It is **layout only**: templates
and `static/css/erp.css`, and the tests that pin them.

| Finding | Level | Outcome |
| --- | --- | --- |
| C0-01 Assessment list | High | Each assessment on a phone shows name, subject, section, date, status and progress without sideways scrolling. |
| C0-02 Result tables | High (result sheet Medium) | Assessment detail, term report card, published report card and result sheet show marks, %, grade and pass/fail, plus the Correct action where it exists, without sideways scrolling. |
| C0-03 Off-screen row actions | Medium | Calendar, student record guardians, access reviews and stale publications show every row action inside the row on phones. |
| C0-04 Teacher assignments length | Medium | An administrator can reach one Class/Grade's slots on a phone without scrolling past every other grade. |
| C0-05 Tall filters | Medium (rest Low) | The first result on the Assessments and Attendance lists is visible on the first phone screen (780 px tall) with filters showing. |
| C0-06 Small tap targets | Medium | Student record pencil links are at least 24 × 24 px. |
| C0-07, C0-08, C0-09 | Low | Picked up in the PR that already touches the template; the rest go in the optional last PR (§6). |

### Out of scope

- Any change to views, URLs, forms, querysets, models, permissions, settings or dependencies.
  `core/tests/route_permissions.json` does not change, and
  `python manage.py makemigrations --check --dry-run` reports no changes.
- Teacher-area and guardian-portal templates, including the portal report card. Guardians see no
  change.
- Document PDFs and letterhead templates (`templates/documents/`), CSV and XLSX downloads, Django
  admin.
- Import batch detail/preview (not exercised in C0; needs its own look with real batches).
- PWA, service worker, offline behaviour and JavaScript changes. `static/js/erp.js` is not
  touched, so the ADR 0028 `js` job does not apply.
- A CI layout or visual test. ADR 0028 keeps browser tests to JavaScript behaviour and rules out
  template and visual tests (`docs/adr/0028-javascript-behaviour-testing.md:76`); a layout test
  would need its own ADR.
- Turning on usage measurement (operational, OD-B9) and desktop redesign.
- Low findings with no action: text links in table rows (spacing exception), and class detail
  Rename/Archive links (Archive opens a confirmation page).
- Removing Bootstrap from a template beyond the markup a PR rewrites.

## 2. Rules this spec must keep

1. **Server-side behaviour is unchanged.** Hiding or moving a control is not access control. Every
   action keeps its current guard (AGENTS.md, `docs/PERMISSIONS.md`).
2. **Same data on every width.** The phone layout shows the same rows and values as desktop. No
   value is dropped on phones, and none is rendered twice from a separate code path that could
   drift (the reason OD-C1 chose an opt-in CSS pattern over duplicate card markup).
3. **Desktop is unchanged at 576 px and wider.** All new rules sit inside
   `@media (max-width: 575.98px)`, the breakpoint the current phone table rule uses
   (`static/css/erp.css:1324`).
4. **Design system.** New markup uses only `erp-` classes (`docs/DESIGN_SYSTEM.md` rule 1). A new
   component is added to the component table there in the same PR.
5. **Accessibility is not cut.** The full requirements are in §4.1. In short: real table markup
   stays, headers stay available to assistive technology, every stacked value has a visible
   label, action names say what and whom, focus order follows visual order, status is never shown
   by colour alone, and important actions are 44 px tall on phones.
6. **Print is unchanged** for pages with print styles (`static/css/erp.css:2151`), in particular
   the report card and result sheet.

## 3. Product-owner decisions

All six were approved by the product owner on 23 November 2026.

| ID | Question | Decision |
| --- | --- | --- |
| **OD-C1** | How should wide tables look on phones? | **Approved: a shared, opt-in `erp-table--stack` style** (§4). A template adds the class to a table it chooses; it is **never applied automatically** to every table, and the existing `.erp-content table` phone rule stays for unconverted tables. Not chosen: separate phone cards per page, which render each value twice. |
| **OD-C2** | How should tall filters shrink? | **Approved: CSS-only compaction.** On phones, short fields (selects and dates) sit two to a row, and the buttons share a row. Every field stays visible with its label, and tap targets don't shrink. No hidden or collapsible filters in this package. |
| **OD-C3** | How should Teacher assignments be navigable on phones? | **Approved: group the cards by Class/Grade, with a short grade jump list at the top** (links to each grade's heading). Template only. The view already orders rows by `class_grade.display_order`, then subject, then section (`core/views.py:2573`), and `display_order` is unique (`classgrade_unique_display_order`), so each grade's slots are contiguous and `{% regroup %}` groups them correctly. If implementation finds that grouping needs a view or queryset change, stop and ask. |
| **OD-C4** | Which page is the Ponytail pilot? | **Approved: Grading scales**, PR C1 (§5). Ponytail is used for review only. |
| **OD-C5** | Which risk tier applies? | **Approved: Medium** for all Package C PRs, because the work is presentation-only. **Staging acceptance by the product owner is required** for pages with marks or results, correction links, or guardian-access actions and decisions: C3, C4, C5 and C6. |
| **OD-C6** | Commit the C0 audit sweep as a developer tool? | **Approved: no.** The one-off script stays out of the repository. The audit report and route inventory are the lasting evidence. Each PR does its own browser check (§8). |

## 4. Design: `erp-table--stack` (OD-C1)

The style is **opt-in**: only tables that carry the class change. Labels come from an explicit
`data-label` on each cell, written in the template next to the value. The CSS must not depend on
column position (`td:nth-child(...)` or similar), because that silently mislabels values when a
column is added, removed or hidden by permission.

**Markup (desktop unchanged):**

```html
<table class="table erp-table--stack ...existing classes">
  <thead>...unchanged...</thead>
  <tbody>
    <tr>
      <th scope="row">Ganesh Rao</th>
      <td data-label="Result">Marked</td>
      <td data-label="Score">72.00 / 100</td>
      ...
      <td class="erp-stack-actions"><a ...>Correct<span class="visually-hidden"> Half-Yearly Exam for Ganesh Rao</span></a></td>
    </tr>
  </tbody>
</table>
```

**Phone CSS (under 576 px only):**

- Undo the in-box scroll for this table (`.erp-content table.erp-table--stack` keeps
  `overflow: visible` and is not `width: max-content`), so the table never scrolls sideways.
- `thead` is visually hidden, not `display: none`, so it is still in the accessibility tree.
- Each `tr` is a block with the card border and spacing tokens already used by `.erp-student-card`.
- The row `th` is the block title (semibold, full width).
- Each `td` is a two-column grid: `attr(data-label)` in soft ink on the left, the value on the
  right, wrapping with `overflow-wrap: anywhere`.
- `.erp-stack-actions` spans the full width. Its links and buttons are at least 44 px tall
  (§4.1).
- The existing `.erp-row-context` spans are hidden inside stacked rows, because the row title
  already names the record.

### 4.1 Accessibility requirements (every converted table)

1. **Real table markup stays in the HTML:** `<table>`, `<thead>`, `<th scope="col">`,
   `<th scope="row">`, `<td>`. The phone layout is CSS only. There is no second, card-only copy
   of the data.
2. **Headers stay available to assistive technology.** `thead` is visually hidden on phones, never
   `display: none`. The C1 PR checks the Chromium accessibility tree at 360 px and records that the
   table, row, column-header and cell roles survive the phone layout. If any role is lost, add
   explicit ARIA table roles (`role="table"`, `row`, `columnheader`, `rowheader`, `cell`) to
   stacked tables only, and record this in `DESIGN_SYSTEM.md`.
3. **Every stacked value has a visible label** from its cell's `data-label`. The label repeats
   the column header text exactly. A cell without a label is allowed only for the row header and
   the actions cell.
4. **Action names say what and whom.** Each link or button has an accessible name with the action,
   the record and the person, for example "Correct Half-Yearly Exam for Ganesh Rao" or "End
   relationship with Anitha Varma". Use a visually hidden suffix where the visible text is short.
   Existing names that already meet this are kept.
5. **Focus order follows visual order.** No `order`, `flex-direction: *-reverse` or positioning
   that moves a control away from its place in the source. Tab through each converted table at
   360 px.
6. **Status is not shown by colour alone.** Status badges keep their text label (Finalized, Draft,
   Pass, Fail, Absent). Destructive actions keep their wording, not only red ink.
7. **Tap targets.** Every control is at least 24 × 24 px. Important actions are at least 44 px
   tall on phones and span the row width where they sit alone: Correct, Record (access decision),
   Change relationship, End, Edit, Delete, Review, Reassign.

**Guard.** A CSS string test pins the phone media query and the `erp-table--stack` rules (house
pattern, `test_ui_*`), and a template test checks that each converted table has the class and
that every body `td` has a `data-label` attribute.

## 5. Ponytail pilot

**Page: Grading scales (`core:academic-year-grading-scales`, `core/templates/core/grading_scales.html`, 40 lines).**

Why this page is the safest:

- GET-only list with no forms, POST or JavaScript, rendered by one view
  (`core/views.py:2470`) and included nowhere else.
- One table with 4 columns and one row per scale (one in the demo).
- Low finding only (C0-07): a mistake costs nothing in a daily workflow.
- Pinned by only two UI test modules (`test_ui_admin_desktop_d1_5a_grading_scales`,
  `test_ui_admin_structure_s3`).
- It exercises everything the High fixes need: a row-header link, a status badge, a long wrapping
  cell ("Applies to") and a dense list cell (Grade bands).

Runner-up: `publications_stale.html` (small, but its action column and 5 pinning modules make it
less isolated).

**Ponytail is review-only in C1.** C1 is built through the normal process
(`IMPLEMENTATION_WORKFLOW.md`) with Ponytail **off**. `/ponytail lite`, `full` and `ultra` are not
used to implement it. After the targeted tests pass:

1. Run `/ponytail-review branch` on the C1 branch.
2. Run the normal independent review as usual.
3. Record in the PR body, separately:
   - Ponytail findings;
   - normal reviewer findings;
   - valid findings that only one of them raised;
   - whether Ponytail proposed fewer lines or better reuse;
   - any simplification it suggested that was wrong or unsafe (for example dropping a
     `data-label`, a visually hidden name, the print rule or a test).
4. Fix only findings the product owner picks, as for any review (verdict table per finding).

The comparison is evidence for whether Ponytail review is worth using on later PRs. It does not
change what C1 must deliver.

**Pilot rule:** C1 is the smallest complete change that meets §4.1 and §7 for this page and
introduces `erp-table--stack`. If the pilot shows the pattern doesn't work (accessibility tree,
print, desktop regression), stop and bring OD-C1 back to the product owner before C2.

## 6. PR plan (worst workflows first, after the pilot)

Order: **C0** (this audit and spec, docs-only) → **C1** pilot → **C2–C4** High → **C5–C7** Medium →
**C8** Low, only if still worthwhile.

One PR at a time, each from a fresh worktree on the latest `origin/main`, opened as a draft,
reviewed, and merged only on the product owner's word for that head. All are Medium tier
(OD-C5). "Staging acceptance" means the product owner accepts the page on staging before closeout.

| PR | Findings | Templates and files | Staging acceptance | Pinned UI tests to update or extend |
| --- | --- | --- | --- | --- |
| **C1 Pilot: stack pattern + Grading scales** | C0-07 (grading) | `static/css/erp.css`; `core/templates/core/grading_scales.html`; `docs/DESIGN_SYSTEM.md` (Table row) | No (staging check only) | `test_ui_admin_desktop_d1_5a_grading_scales`, `test_ui_admin_structure_s3`; new `test_ui_phone_tables.py`; CSS guards |
| **C2 Assessment list** | C0-01 | `core/templates/core/assessment_list.html` | No (staging check; real Android check per §7) | `test_ui_admin_desktop_d1_5b_assessments`, `test_ui_admin_desktop_d1_5c_result_reports`, `test_ui_admin_structure_s3`, `test_ui_year_selector_context`, `test_ui_year_selector_ui`; `test_ui_phone_tables` |
| **C3 Assessment results + result sheet** | C0-02 | `core/templates/core/_assessment_results.html` (both tables; included only by `assessment_detail.html:60`), `core/templates/core/report_result_sheet.html` | **Yes** (marks, Correct links) | `test_ui_admin_desktop_d1_5b_assessments`, `test_ui_admin_desktop_d1_5c_result_reports`, `test_ui_admin_home_tabs`; `test_ui_phone_tables` |
| **C4 Report card + published report card** | C0-02 | `core/templates/core/report_term_report_card.html`, `core/templates/core/publication_detail.html` (both tables) | **Yes** (marks, results) | `test_ui_admin_desktop_d1_5c_result_reports`, `test_ui_admin_desktop_d1_5d_term_publication`; `test_ui_phone_tables` |
| **C5 Student record** | C0-03 (guardians), C0-06, C0-09 | `core/templates/core/student_detail.html`; `static/css/erp.css` (pencil link minimum size) | **Yes** (guardian relationship and access actions) | `test_ui_student_phone_cards`, `test_ui_student_history_phone`, `test_ui_tables_a11y`, `test_ui_admin_desktop_d1_3d1_guardian_forms`, `test_ui_admin_phase2`, `test_ui_wording` and the others listed by `grep -l "core:student-detail" core/tests/test_ui*.py` |
| **C6 Calendar, access reviews, stale publications** | C0-03 | `core/templates/core/academic_year_calendar.html`, `core/templates/core/guardian_access_reviews.html`, `core/templates/core/publications_stale.html` | **Yes** (access decisions, republish review) | `test_ui_admin_structure_s2`, `test_ui_year_cards`, `test_ui_admin_desktop_d1_3c_access_reviews`, `test_ui_admin_desktop_d1_5d_term_publication`, `test_ui_admin_phase3e`, `test_ui_admin_phase3f`, `test_ui_empty_states` |
| **C7 Filters + Teacher assignments** | C0-05, C0-04 | `static/css/erp.css` (phone filter grid); `core/templates/core/assessment_list.html`, `core/templates/core/attendance_register_list.html` (filter markup hooks, if needed); `core/templates/core/teacher_assignments.html` (grade groups with a jump list, template only per OD-C3) | No (staging check only) | `test_ui_admin_desktop_d1_4a_attendance_list`, `test_ui_admin_desktop_d1_5b_assessments`, `test_ui_year_assignments_phone`, `test_ui_admin_desktop_d1_2b`, `test_ui_admin_phase3d`, `test_ui_admin_setup_checklist`; CSS guards |
| **C8 (optional) Low leftovers** | C0-05 (Low lists), C0-07 (home button), C0-08 | The six other filter pages, `templates/partials/home/` (button label), `core/templates/core/teacher_detail.html`, `core/templates/core/import_list.html` | No | Modules found by `grep -l` on each route |

C7 can split into two PRs (filters; teacher assignments) if the diff grows past a quick review. If measurement is on before C5
(OPTION_B §9.5), C5–C8 may be reordered by admin phone views; C1–C4 stay first.

## 7. Acceptance criteria (every PR, for the pages it touches)

1. At **360 px and 390 px**:
   - the page does not scroll sideways (document `scrollWidth` equals the viewport width);
   - no converted table scrolls inside its box;
   - every value column and every row action is inside the viewport.
2. The finding's outcome in §1 is met (for example, C2: section and date are visible on every
   assessment row).
3. At **1366 px** the page matches its `main` screenshot apart from intended changes, and nothing
   overflows. At **576 px** (the breakpoint) the desktop table shows.
4. Every converted table meets §4.1: real table markup, headers in the accessibility tree,
   visible labels, meaningful action names, focus order follows visual order, status not by colour
   alone, controls at least 24 × 24 px, important actions at least 44 px tall.
5. Keyboard: focus is visible on every control in a stacked row.
6. Print preview of the report card and result sheet (C3, C4) is unchanged.
7. No change to views, URLs, forms, models, permissions or route inventory. The migration check
   reports no changes.
8. New markup uses only `erp-` classes. Any new component is listed in `DESIGN_SYSTEM.md`.
9. Full CI passes on the final PR head. The PR body has before/after screenshots at 360, 390 and
   1366 px for each touched page.
10. No new console errors on the touched pages at any checked width.
11. Permissions are unchanged around actions: the Correct link and guardian relationship and
    access actions appear only for users who could use them before, and the server still refuses
    users without the permission. Checked by the existing guard tests (§8), not by hiding
    controls.
12. **Real-device acceptance for the high-consequence pages in C2–C4:** Chromium at 360, 390 and
    1366 px, plus one check on a real Android phone. The check confirms no hidden values or
    actions, no desktop regression and no console errors. If no iPhone is available, record
    Safari/iPhone as a known limitation in the PR.

## 8. Test plan

**Per PR (local, per AGENTS.md; no full suite):**

```
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test core.tests.test_ui_phone_tables <pinned modules from §6> --parallel 4 --noinput
python manage.py test --pattern="test_ui*.py" --parallel 4 --noinput   # after any erp.css edit
```

**New `core/tests/test_ui_phone_tables.py`** (grows by PR), server-rendered like the existing
phone tests:

- each converted page renders its table with `erp-table--stack`;
- every `<td>` in the table body has a non-empty `data-label`, except the actions cell, which has
  `erp-stack-actions`;
- the row header is a `<th scope="row">`;
- for C3, the Correct link is inside `erp-stack-actions`, and its accessible name includes the
  action, the assessment and the student;
- each `data-label` equals the text of its column header (no position-based labels);
- a CSS test pins the `erp-table--stack` rules inside `@media (max-width: 575.98px)`, and that no
  `erp-table--stack` rule appears outside it.

**Permission regression.** No guard changes, so no new permission tests. C3, C4, C5 and C6 rerun
the existing guard and route-inventory tests for their routes to confirm nothing moved,
including that the Correct link and guardian actions are absent for users without the permission.

**Browser check (manual, every PR):** run the page at 360, 390 and 1366 px against a throwaway
seeded database (the C0 method). Record page overflow, hidden table width (must be 0 for converted
tables) and tap-target sizes in the PR body, with screenshots. For C1, also check the accessibility
tree. For C3 and C4, also check print preview.

**Staging:** after merge, check every touched page on staging at phone width. The product owner
accepts C3, C4, C5 and C6 on staging (OD-C5).

**CI:** targeted tests and browser checks locally; the full PostgreSQL suite runs in CI once the
PR is marked Ready, on its final approved head. The JavaScript `js` job runs under its own path
rules (ADR 0028). Package C does not touch `static/js/`, so its test step is expected to be
skipped. A skipped step is not required (AGENTS.md).

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| Stacked rows lose table semantics in some screen readers. | C1 checks the accessibility tree and adds ARIA table roles if needed (§4). |
| The phone rule leaks to desktop. | All rules inside the phone media query; CSS test pins it; 1366 and 576 px checks. |
| Many string tests pin the current markup (`test_ui_*`). | Each PR lists its pinned modules (§6) and runs `--pattern="test_ui*.py"` after CSS edits. |
| Stacked result rows make long pages on phones (a report card stacks one block per assessment, for every subject). | Acceptable: vertical scrolling is expected on phones, and every value is now visible. Re-check in C4 screenshots. |
| Emulated Chromium differs from real phones. | One real Android check for C2–C4 (§7 item 12). Safari/iPhone is recorded as a limitation if no device is available. |

**Rollback:** each PR is templates and CSS only, so revert the merge commit. There is no data or
migration to undo.

## 10. Definition of done for Package C

- C1–C7 merged with full CI green on each final head, owner staging acceptance recorded for C3–C6,
  and the C1 Ponytail comparison recorded (§5).
- The C0 route inventory re-run at 360 and 390 px shows no High or Medium finding left.
- ADM-08 and MOB-01 can then move from Partial to Implemented in a closeout note, with C8 and any
  measurement-led follow-ups listed as remaining.
