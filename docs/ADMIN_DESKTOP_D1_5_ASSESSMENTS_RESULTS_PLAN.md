# UI-D1-5 — Admin Assessments and Results

**Status:** **PLAN ONLY — awaiting planning review.** This document and its PR are documentation only; no application code is changed and nothing is implemented. The audit behind it is read-only.
**Planning branch:** `plan/ui-admin-desktop-d1-5-assessments-results`, based on `main` `6d19bcf` (docs closeout for PR #107; UI-D1-4 complete).
**Parent:** `docs/ADMIN_DESKTOP_D1_PLAN.md` (D1-5). **Binding design:** `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, and the accepted D0 / D1-3 / D1-4 patterns (page header, toolbar, panel, status badge, labelled table region, permission-aware breadcrumbs, error summary).
**Domain authority:** ADR 0009 (assessment and results model), ADR 0010 (teacher authorization), ADR 0014 (guardian-visible information and result publication), ADR 0019 (Subject name captured at finalization), ADR 0004 (authorization foundation), `core/assessment_reports.py`, `core/publication.py`, `docs/PHASE_4_ASSESSMENTS_PLAN.md`, `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`.

D1-5 is, like D1-3 and D1-4, a **presentation-only** programme: it brings the administrator assessment, grading, result-review and publication pages into the accepted admin-desktop system. It adds **no new calculation, report, export, filter, permission, route or workflow**. It is split into four independent gates (section 7), each its own draft PR and review, in risk-ascending order.

## 1. Scope

**In scope (administrator pages):** grading scales, assessments (list, planning form, detail with finalization, result corrections), the four result reports (assessment result sheet, Student results, Subject/Section matrix, Term report card), and Term publication (preview and confirm, stale list, publication detail, withdraw).

**Out of scope (and why):**

- **Guardian Portal** (`templates/portal/*`, `core/portal*.py`): a separate area with its own templates (ADR 0014, FROZEN). Untouched; its tests must pass unmodified. The portal templates extend only `portal/base.html` and share three common partials with the admin shell (`partials/_empty.html`, `_messages.html`, `_account_menu.html`), so **those shared partials must not change** in any D1-5 gate.
- **Teacher pages** (`my_assessments`, `my_gradebook`, `assessment_marks_entry`, `my_results`, `my_subject_results`, `my_student_detail`, the teacher dashboard): Phase 5 / U3 teacher area. Untouched, but two templates are **shared** with them (section 3.3), so those need teacher regression coverage.
- **Term remarks** (`term_remarks`): a shared `login_required` page used by administrators *and* class teachers; treated as a teacher workflow (decision E2).
- **Report card PDFs and the Documents module** (`document_report_cards`, `document_report_card_pdf`): belongs to the Documents / D1-6 gate (parent plan). They only list already-published versions.
- **Exports:** there is **no results export** today (only import templates/CSV for the import workflow). D1-5 adds none.
- No models, migrations, services, calculations, authorization decorators or routes.

## 2. Audited inventory (read at `6d19bcf`)

| Page | Route name | Permission | Template (lines) | Shared with |
| --- | --- | --- | --- | --- |
| Grading scales list | `academic-year-grading-scales` | `view_gradingscale` | `grading_scales.html` (24) | none |
| Grading scale detail + bands | `grading-scale-detail` | `view_gradingscale` (add/remove band: `add_gradeboundary` / `delete_gradeboundary`) | `grading_scale_detail.html` (44) | none |
| Grading scale add / edit | `grading-scale-create`, `-update` | `add_gradingscale`, `change_gradingscale` | `grading_scale_form.html` (12) | none |
| Band add / remove | `grade-boundary-create`, `-delete` | POST only | (form lives on scale detail) | none |
| Assessment list | `academic-year-assessments` | `view_assessment` | `assessment_list.html` (36) | none |
| Assessment plan / edit | `assessment-create`, `-update` | `add_assessment`, `change_assessment` | `assessment_form.html` (15) | none |
| Assessment detail | `assessment-detail` | `view_assessment` (Finalize `finalize_assessment`, Delete `delete_assessment`) | `assessment_detail.html` (50) + `_assessment_results.html` (30) | none |
| Finalize / delete | `assessment-finalize`, `-delete` | POST only | (buttons on detail) | none |
| Result correction | `result-correct` | `correct_studentresult` | `result_correction_form.html` (35) | none |
| Result sheet | `report-result-sheet` | `view_studentresult` | `report_result_sheet.html` (23) + `_result_cells.html` | `_result_cells.html` |
| Student results | `report-student-results` | `view_studentresult` | `report_student_results.html` (27) | `_result_cells.html` |
| Subject/Section results | `report-subject-section-results` | `view_studentresult` | `report_subject_section_results.html` (36) | none |
| Term report card | `report-term-report-card` | `view_studentresult` | `report_term_report_card.html` (23) | **Teacher `my-report-card` renders the same template** |
| Term publication preview/confirm | `term-publication` | `view_termpublication` (confirm: `publish_termpublication`) | `term_publication.html` (63) | none |
| Stale publications | `publications-stale` | `view_termpublication` | `publications_stale.html` (9) | none |
| Publication detail | `publication-detail` | `view_termpublication` | `publication_detail.html` (28) | none |
| Withdraw | `publication-withdraw` | `publish_termpublication` | `publication_withdraw.html` (13) | none |

Entry points today (unchanged by this programme): Academic Years list links "Assessments" and "Grading" per year; the Terms page links "Publish to guardians" and "Remarks" per Term (already migrated in D1-2A); Student detail links "Results and report cards"; the sidebar "Results" group holds only "Stale publications" (with a waiting badge, also surfaced on the Overview). `core/breadcrumbs.py` has **no rules** for any of these routes, so none of them shows a trail or keeps a sidebar item active.

Forms (`core/forms.py`): `GradingScaleForm`, `GradeBoundaryForm`, `AssessmentForm`, `AssessmentFilterForm`, `ResultCorrectionForm`, `RevocationForm`. **None uses `FieldAccessibilityMixin`**, so, as in D1-4, automatic focus to the first invalid field is not available (Django 5.2 still writes `aria-invalid` and `aria-describedby`, which resolve only when fields render through `_form_field.html`). The Subject/Section matrix and the publication Section picker are **hand-built `<select>`s outside any Django form**.

Existing tests that pin behaviour: `test_phase4_{structure,assessments,results,finalization,corrections,grading,remarks,reports,teachers,acceptance}.py`, `test_phase5_results_remarks.py`, `test_phase6_{publication,acceptance,access_boundary,portal_shell}.py` (publication, stale and guardian boundary), `test_ui_admin_phase2.py`, plus the D1 CSS-scoping tests.

## 3. Rules that must not change

### 3.1 Calculations and records (ADR 0009, 0019)

- **Marks are canonical.** Percentage, grade and pass/fail are derived; a grade is never an editable source of truth. Pass/fail exists only when a pass mark exists; **ABSENT is never zero and never FAIL**.
- **A missing result means "entry incomplete", never ABSENT.** The roster note "A Student without a result is not absent" and the "Not entered" cell must remain.
- **No totals, weighting, averages or ranks** on any result view; the report card shows each assessment separately.
- **Roster** is derived from enrollment effective on the assessment date; finalization requires exactly one valid result per eligible enrollment.
- **Finalized results** change only through the audited correction (previous value, new value, administrator, time, required reason); correcting one Student never reopens the assessment. The grading context is frozen at finalization.
- **Subject display** uses `Assessment.subject_display` everywhere (live name for DRAFT, captured label once FINALIZED); the Term report card groups by `SubjectGroup(subject, name)`.
- Reports show finalized values **after corrections**, never a second stored copy.

### 3.2 Teacher workflows and publication (ADR 0010, 0014)

- Teachers enter and edit only DRAFT results for assigned Subject/Section; finalizing, correcting and publishing are administrator-only. Nothing in D1-5 may widen any of this.
- **Finalization and guardian publication are separate actions.** Only FINALIZED results are publishable; the preview lists exactly what will be released and writes nothing until confirmed.
- **Confirmation recomputes the plan under locks and writes exactly the previewed versions, or nothing (stale token); confirming twice publishes nothing new.** The token and the hidden `section` / `include` fields in the confirm form are part of that contract.
- An incomplete Student (a roster assessment not finalized) is **excluded unless individually included**, and then published **marked partial**. A Student without a single Term placement is never publishable.
- Each published version is an immutable snapshot with a fingerprint. A correction marks the current version **STALE in the same transaction**; guardians stop seeing it until an administrator reviews and republishes or withdraws. Every version (PUBLISHED, STALE, SUPERSEDED, WITHDRAWN) is permanent and reconstructable.
- Withdrawal requires a reason and takes effect at once. `view_termpublication` and `publish_termpublication` stay separate.

### 3.3 Shared templates (the main regression hazard)

- `report_term_report_card.html` is rendered for administrators (`report-term-report-card`) **and for class teachers** (`my-report-card`, same context, teacher shell and bottom bar). Any change must keep the teacher rendering correct; permission-conditional chrome must use `perms`, not the URL (the template already gates its "All results" link on `perms.core.view_studentresult`).
- `_result_cells.html` is included by the result sheet, Student results, the report card **and the teacher `my_student_detail`**.
- The Guardian Portal includes **no `core/` template**; it extends `portal/base.html` and uses the shared partials named in section 1. Every D1-5 gate must prove, with before/after response comparison, that portal pages are unchanged.

## 4. UI/UX gaps found

Observable from the templates; none needs a business change.

1. **No page identity.** Every page uses a bare `h3`; none uses `partials/_page_header.html`, so none matches Attendance, Students or the D1-2 configuration pages.
2. **No navigation context.** No breadcrumb rules: no trail, no active sidebar item, and no Back path other than ad-hoc text links ("All assessments", "All grading scales", "Back to Student").
3. **Assessment list.** Two unstyled buttons above a hand-laid filter row; table has no `caption`, `scope`, labelled region, count or empty-state distinction ("No assessments." for both no data and no matches); `Max` and `Pass` figures are left-aligned and unlabelled as numbers; status is plain text, not a badge; **an invalid filter silently falls back to all assessments** (`AssessmentFilterForm` errors are never shown), the same latent problem D1-4A fixed for registers.
4. **Assessment detail.** The facts are a `dl.row`, the actions bare buttons; **Delete is an unconfirmed POST** (blocked only once results exist); Finalize is an in-page card whose consequence text is good and must survive; "no teacher assigned" is red text only; the roster table has eight unstructured columns and a Bootstrap `bg-warning` "corrected" badge.
5. **Result correction.** Plain `form.as_p`; correction history table unstructured. (The page's own warning copy is accurate and must stay.)
6. **Grading.** Scales table and detail unstyled; **"Remove band" is an unconfirmed POST**; completeness is conveyed by red text and an alert ("Needs a band from 0%").
7. **Result reports.** Four bare tables. The **Subject/Section matrix** (N assessment columns) has no sticky Student column and no local scroll region, so on narrow widths it widens the page; its three selects are hand-built with no labels tied to inputs, no error association, and an invalid id resets the page with a transient message.
8. **Report card.** Teacher-facing wording ("Teacher's remark") fine; per-subject tables are `table-sm` with no region or caption; header facts are `lead` text.
9. **Publication preview.** The densest page: a Section picker (hand-built `select`), then one table whose "Preview" cell mixes Bootstrap `badge bg-primary / bg-warning` states, a conditional checkbox ("Publish the finalized results anyway") and a "replaces version N" note, and whose "Will be released" cell prints raw entries in `small` text; a second GET form ("Update preview") is the only way to apply an include selection; the confirm button is a separate form below. There is **no summary of how many Students will publish, republish, are incomplete or skipped**, and no phone layout.
10. **Stale publications.** A bare `ul` with no status, reason column or link to the Term/Section context.
11. **Publication detail / withdraw.** Facts as prose; version list as `ul`; the Withdraw / Republish actions are small outline buttons with no visible consequence text; the withdraw form is `form.as_p`.
12. **Errors and accessibility.** No error summary, no `caption`/`scope`, unlabelled regions, no required legend, no associated help or errors on the hand-built selects.

## 5. Permission boundaries and display gating (must not change)

Existing view decorators are authoritative (section 2). Display gating only hides links the viewer cannot use; where a destination is not permitted the text stays but is **not a link**.

| Link / control | Shown when (existing, unchanged) |
| --- | --- |
| "Plan an assessment" | `add_assessment` |
| "Subject/Section results" (from the assessment list) | `view_studentresult` |
| Assessment Edit | `change_assessment` and not finalized |
| Assessment Delete | `delete_assessment`, not finalized and not locked |
| Finalize card | `finalize_assessment` and not finalized |
| "Result sheet" (from detail) | finalized and `view_studentresult` |
| "Correct" per result | finalized and `correct_studentresult` (and not read-only) |
| Add / remove grade band | `add_gradeboundary` / `delete_gradeboundary` |
| "Edit name and Grades" | `change_gradingscale` |
| "Add grading scale" | `add_gradingscale` |
| "Publish the finalized results anyway" checkbox and the confirm form | `publish_termpublication` |
| Publication Withdraw / Review and republish | current version and `publish_termpublication` |
| Report card "All results for …" | `view_studentresult` |

Rules for the new chrome: header actions and breadcrumb parents reuse the **destination's** permission (as in D1-4C); the Overview crumb needs `core.view_school`; users without `view_school` get no admin sidebar or trail (existing `user_areas` behaviour). **No page gains an action, link or data field that its viewer could not already use.** Teachers, Guardians and anonymous users keep today's 403 / redirect outcomes for every route in section 2.

## 6. Reusable components and lessons from D1-4

Reuse, do not reinvent: `partials/_page_header.html`; `erp-toolbar erp-toolbar--inline` (+ the scoped one-row modifier pattern from C-1); `erp-panel` with `erp-panel-head mb-3`; `partials/_status_badge.html` (existing tones `draft`, `pending`, `submitted`, `finalized`, `published`, `stale`, `inactive`, `info`, default neutral); labelled `erp-table-scroll` regions with `caption`, `scope="col"`/`row`; `partials/_form_field.html` plus `partials/_form_error_summary.html`; `partials/_empty.html`; permission-aware `Crumb(perm=…)` rules in `core/breadcrumbs.py`; the `erp-keep` + scoped padding approach for tables that must fit phones.

Carried lessons: render every field through `_form_field.html` (Django's `aria-describedby` then resolves); scoped CSS goes **before** the `/* UI-D1-4B` marker and must not use `overflow-wrap: anywhere` (an existing D1-1 test forbids it); numeric columns use `.erp-num`; a status is never colour-only; the **first-load-unfiltered / invalid-filter-disclosed** pattern from D1-4A and D1-4C-2 applies to the assessment list and the matrix; automatic focus to the first invalid field remains a recorded gap until the forms adopt `FieldAccessibilityMixin` (a forms gate, out of scope).

## 7. Proposed implementation gates

Four independent draft PRs, each stopping for design review. Order is risk-ascending (decision E1).

### D1-5A — Grading scales (configuration)

**Pages:** `grading_scales.html`, `grading_scale_detail.html`, `grading_scale_form.html`. **Also:** breadcrumb rules (`academic-year-grading-scales`, `grading-scale-detail`, `-create`, `-update`) with parents Academic Years (`view_academicyear`) and the scale list (`view_gradingscale`).
**Contract:** header with the year name and purpose; scales table (Scale / Applies to / Bands / Status) with a **status badge** ("Complete" vs "Needs a band from 0%" with text), bands rendered as a labelled list; detail page bands table (From % right-aligned, Grade, Remove) with the explanation that **finalized assessments keep the bands they were finalized with**; the add-band form as a toolbar through `_form_field.html`; "Remove" keeps its POST and gains adjacent text stating the consequence (decision E5). No change to band maths or completeness rules.
**Tests:** structure; status badge text for complete and incomplete scales; permission gating of every control; POSTs unchanged (same URLs, CSRF, fields); band ordering and the "highest starting point at or below" copy; context equality with the unchanged view; breadcrumbs matrix.

### D1-5B — Assessments, finalization and corrections

**Pages:** `assessment_list.html`, `assessment_form.html`, `assessment_detail.html` + `_assessment_results.html`, `result_correction_form.html`. **Also:** breadcrumb rules for `academic-year-assessments`, `assessment-create`, `-update`, `assessment-detail`, `result-correct` (parents: Academic Years, Assessments of that year).
**Contract:**
- *List:* header with the permission-gated primary "Plan an assessment" and secondary "Subject/Section results"; the filter as a labelled toolbar (Term, Section, Status) through `_form_field.html`, **invalid filters disclosed** ("Filters were not applied; showing all assessments") with errors shown; a table region (Date, Term, Subject, Section, Assessment, Max, Pass, Status) with `caption`, right-aligned numeric columns, **status badges** (Draft = draft tone, Finalized = finalized tone), the assessment name as the only row link; empty states distinguish *no assessments yet* from *no matches*. No new counts (decision E4).
- *Detail:* header (subject and assessment name; status badge), a context panel (year/term, Section, date, max, pass, grading with "frozen at finalization", finalized by/at) as a description list, actions grouped and gated exactly as today; the Finalize panel keeps its readiness list and consequence text and its single POST; Delete keeps its conditions and gains consequence text; the roster table keeps every column and the "not absent" note, with a `corrected` **badge with text**; the unassigned-teacher warning gets a text label, not colour alone.
- *Correction form:* header, read-only context panel, form via `_form_field.html` with required legend and error summary, history table with `caption`/`scope`.
- *Form:* `_form_field.html`, required legend, locked-context notice kept.
**Tests:** list filter states (first load unfiltered, valid, invalid disclosed); status badge and `Not entered`/`Absent` distinctions preserved (missing result is not ABSENT); finalize/delete/correct POST behaviour byte-for-byte unchanged; permission gating matrix per control; roster and results context equality; breadcrumbs; the whole `test_phase4_*` set unmodified.

### D1-5C — Result reports (shared with teacher pages)

**Pages:** `report_result_sheet.html`, `report_student_results.html`, `report_subject_section_results.html`, `report_term_report_card.html`, `_result_cells.html`. **Also:** breadcrumb rules for the four report routes (`report-student-results` keeps its logical parent, the Student, gated by `view_student`).
**Contract:** headers; result tables as labelled regions with `caption`/`scope` and `.erp-num` columns; the **Subject/Section matrix** gets a labelled filter toolbar (Subject, Section, Term; either a thin wrapper in the template or the existing selects relabelled and associated — no view/form change, decision E3b), invalid-choice disclosure, a local scroll region with a **sticky Student column** (the established gradebook grid pattern) and a legend that "—" means no finalized result and "Absent" is never zero; the report card keeps its per-assessment tables, "no weighting, totals or rank" note and Teacher's remark.
**Shared-template rule (decision E3):** `_result_cells.html` and `report_term_report_card.html` must render correctly in the teacher shell (`my-report-card`, `my-student-detail`). Chrome that differs by role is chosen with `perms.core.view_studentresult`, never by URL name; the teacher pages are screenshot-tested too.
**Tests:** existing `test_phase4_reports`, `test_phase5_results_remarks`, teacher report-card and Student-detail tests unmodified; new template tests for both admin and teacher rendering of the report card; "Absent / Not graded / —" semantics; no totals, ranks or weights anywhere; context equality with `assessment_reports`.

### D1-5D — Term publication (highest risk)

**Pages:** `term_publication.html`, `publications_stale.html`, `publication_detail.html`, `publication_withdraw.html`. **Also:** breadcrumb rules for `term-publication` (parents: Academic Years → Terms of that year), `publications-stale` (sidebar section already "Stale publications"), `publication-detail`, `publication-withdraw`.
**Contract (layout only; the exact mechanics are frozen):**
- *Preview:* header with Term and year; Section picker as a labelled toolbar through a form-field wrapper (no change to GET parameters `section`, `include`); a **summary strip** derived in the template with `{% regroup plan.rows by action %}` (will publish / will republish / incomplete / already published / nothing to publish / no single Term placement) so the administrator sees counts before reading rows; each Student as a record row with a **status badge with text** (replacing `badge bg-primary`/`bg-warning`), the "replaces version N, <status>" note, the include checkbox exactly as today (only with `publish_termpublication`), and the **fully visible** list of released entries and remark (no collapsing; decision E8).
- *Confirm:* the same POST form, token, hidden `section` and `include` fields; the button keeps its dynamic label "Confirm and publish N report card(s)" and its disabled state when nothing is selected; adjacent text states that nothing is written until confirmed and that guardians will see the report cards at once.
- *Stale, detail, withdraw:* stale list as a table (Student, Term, version, reason, link) with a stale badge; detail with a status badge, "source results or remark changed since release" notice, entries table, versions as a table with statuses; Withdraw / Republish actions kept, gated, with consequence text; the withdraw form via `_form_field.html`.
**Tests:** the full `test_phase6_publication`, `test_phase6_acceptance` and `test_phase6_access_boundary` sets unmodified; new tests that the preview HTML contains the same entries as `plan_publication` for every action state, the same hidden fields and token, the confirm button label and disabled state, the include checkbox gating, that GET never writes (query/row counts), that a stale token still publishes nothing, and that Guardian Portal responses are byte-identical before and after.

### Cross-gate requirements

- **Breadcrumbs:** each gate adds its routes to `core/breadcrumbs.py` with the destination's permission on every parent crumb; tests cover the `view_school` and per-parent permission matrix, as in D1-4C.
- **Responsive and accessible:** no page-level horizontal overflow at 360, 390, 768, 992, 1024, 1280, 1440px; wide tables scroll only inside labelled, keyboard-focusable regions; one H1; `caption` and `scope` on every table; status never colour-only; errors summarised and associated through `_form_field.html`; works with JavaScript off; no JS added.
- **Evidence:** synthetic data only, never real student or guardian data; before/after screenshots at 390, 768, 992, 1024, 1280, 1440px for every state in the gate, including restricted-permission users and the teacher renderings of shared templates; measurements and README under `docs/ui-reviews/ui-d1-5<x>/`; focused tests, then the full PostgreSQL suite with `--parallel 4` on the final head.
- **Forbidden in every gate:** `core/models.py`, migrations, `core/publication.py`, `core/assessment_reports.py`, `core/views.py`, `core/forms.py` and every calculation or workflow service; authorization decorators and routes; the Guardian Portal and teacher templates; the shared partials `_empty`, `_messages`, `_account_menu`; `term_remarks.html`; Documents; any new export, chart, total, rank or weighting; deployment.

## 8. Testing and acceptance (every gate)

| Check | Pass condition |
| --- | --- |
| Query and context invariance | Rendered contexts and querysets identical before and after for every state the gate touches; no per-row query growth |
| Calculations and semantics | Marks, percentage, grade, pass/fail, "Not entered", ABSENT, "Not graded", corrected values, subject labels and publication fingerprints unchanged; no totals/ranks/weights introduced |
| Mutations unchanged | Every POST keeps its URL, method, CSRF, field names, validation and redirect; GETs never write |
| Permissions | Section 5 matrix holds; anonymous redirects; teacher and guardian 403 where today; no link shown that the viewer cannot open |
| Guardian boundary | Portal responses compared before and after are identical; the existing Phase 6 boundary suites pass unmodified |
| Teacher regression | Teacher results, gradebook, marks entry, report card and Student detail pass unmodified (and render correctly in D1-5C) |
| Accessibility | Section 7 "Cross-gate requirements" |
| Regression | `manage.py check`; focused module; the Phase 4, 5 and 6 modules listed in section 2; full PostgreSQL `--parallel 4`, exact counts reported |
| PR hygiene | Template (plus breadcrumbs and minimal scoped CSS) diff only; draft PR; no merge, deploy or next gate without approval |

## 9. Decisions requested from the reviewer

- **E1 — Gate split and order.** Recommended: A grading, B assessments, C reports, D publication (risk ascending; D last because it controls what guardians see). Alternative: do D earlier because it carries the only waiting-work badge (stale publications).
- **E2 — Term remarks.** Recommended: exclude (shared with class teachers; a teacher-workflow page). Alternative: a narrow later gate that restyles only the administrator view with teacher regression tests.
- **E3 — Shared report-card template.** Recommended: keep one template and one set of tests covering both shells, with role chrome chosen by `perms.core.view_studentresult`. Alternative: add a teacher-only template (a view change, so a separate approved gate). **E3b — Matrix filters:** recommended template-only re-labelling and association of the existing selects; the cleaner fix (a real Django form) needs a forms/view change and is a follow-up.
- **E4 — List counts.** "N of M results entered" per assessment needs a view annotation. Recommended: not in D1-5 (template only); log as a follow-up gate.
- **E5 — Confirmation for destructive actions** (assessment Delete, band Remove). A real confirm page needs a new view and URL. Recommended: consequence text adjacent to the control now (no view change) and a follow-up gate for confirm pages; the Finalize panel already explains itself.
- **E6 — Navigation.** Recommended: no sidebar restructure; add permission-aware breadcrumbs only, and keep entry points (Academic Years, Terms, Student detail). A "Results" group of Assessments and Grading links would need a year-selection step and is a follow-up.
- **E7 — Report card PDFs / Documents.** Recommended: leave to the Documents (D1-6) gate; D1-5D must not change what `visible_publications` lists.
- **E8 — Publication preview density.** Recommended: keep the released entries **fully visible** per Student (the preview is the approval); improve density with structure (record rows, badges, summary strip), not collapsing. Alternative: native `<details>` per Student, which hides content by default and is therefore **not** recommended.

## 10. Execution plan (after approval of this plan)

1. Merge this documentation PR; fresh branch from `main` for the first approved gate (recommended D1-5A) in the separate clean worktree.
2. Templates, breadcrumb rules and scoped CSS only; tests per section 8; focused then full PostgreSQL `--parallel 4`.
3. Synthetic screenshots, measurements and README under `docs/ui-reviews/ui-d1-5a/` and so on.
4. One draft PR per gate, report head SHA and results, and **stop** for design review. No merge, no deployment, no next gate without approval.

## 11. Explicit follow-ups — not in D1-5

- Per-assessment "N of M entered" counts (view annotation) and any list sort/pagination changes.
- Confirmation pages for assessment Delete and band Remove; a real form for the Subject/Section matrix.
- `FieldAccessibilityMixin` on the assessment, grading, correction and revocation forms (automatic error focus).
- Term remarks administrator view; teacher-only report-card template.
- Results export (CSV/PDF) and any chart, trend or comparison: none exist today and ADR 0009 forbids rank/GPA/weighting.
- Sidebar "Results" group of Assessments and Grading; Documents report-card PDF listing (D1-6).
- Deployment of any UI-D1 gate.
