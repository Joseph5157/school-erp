# Admin Desktop — Structure & Navigation (plan)

Status: **PLAN, awaiting approval.** No code written. Branch `feat/admin-desktop-structure-nav` from `origin/main` (`50fdd09`).
Source: the 24-page Admin Desktop UI/UX audit (24 Oct 2026), items UI-03, UI-04, UI-02, UI-05, UI-09, UI-13.
Out of scope: colours/palette (UI-10), Overview (UI-01/12), icons, Teacher/Guardian, mobile/tablet layout, any model/migration/permission/route change.

## Gates (one PR each, each revertible alone)

### S1 — Quick fixes (UI-13, UI-05, UI-09 labels)
- **UI-13** `timetable_periods.html`: when there are no periods show only the empty-state CTA; keep the header "Add period" once data exists.
- **UI-05** `erp.css` desktop block: `.erp-content { max-width: 96rem }` → `90rem` (1440px) and centre it (`margin-inline: auto`). Update the pinned assertion in `test_ui_admin_desktop_d0.py:69`.
- **UI-09** rename sidebar/breadcrumb/H1 "To send" → "Message queue" (`navigation.py`, `breadcrumbs.py`, `notifications_to_send.html`). URL name and path unchanged. Update tests that assert the label.

### S2 — Legacy pages onto the shared shell (UI-03)
Convert 23 templates from `<h1 class="h3 mb-3">` to `partials/_page_header.html` + `.erp-form` / `.erp-panel` + a `breadcrumbs.RULES` entry (so they also get an active sidebar item). Pattern = `teacher_username_form.html`. Context variables, form handling and URLs untouched.

Batches (separate commits, one PR):
1. School & calendar: `school_form`, `academic_year_calendar`, `calendar_day_form`, `term_form`, `term_remarks`
2. Classes & subjects: `class_grade_detail`, `class_grade_form`, `section_form`, `subject_form`, `offering_form`
3. Assignments: `class_teacher_form`, `class_teacher_end_form`, `teacher_assignment_form`, `teacher_assignment_end_form`, `assignment_copy`, `teacher_load`
4. Account confirms: `teacher_reset_confirm`, `teacher_reactivate_confirm`, `guardian_reset_confirm`, `guardian_revoke_form`, `guardian_username_form`, `identifier_form`
5. Deletes: `timetable_period_delete`, `timetable_slot_delete`

Left alone (not Admin-shell pages or print slips): `assessment_marks_entry`, `choose_area`, `*_credential_slip` (need owner check; slips are print-style).
Tests: each batch asserts the page header/breadcrumb trail, `aria-current` on the right sidebar link, and that the form still posts/validates exactly as before.

### S3 — Sidebar navigation (UI-04, UI-02)
- **UI-04** new group **"Assessments & Results"** in `OFFICE_NAV`: Assessments, Subject/Section results, Grading scales, Stale publications (moved from "Results"). These year-scoped URLs need a year id → new read-only context value `nav_year` (see decision 1).
- **UI-02** each group becomes a `<details>` (works without JS). Group containing the active link is open; others collapsible. Sticky group labels; active link scrolled into view by a few lines in `erp.js`.
- Tests: update `test_ui_foundation.py:64` (group titles), add permission-visibility tests for the new links, active-state tests for year-scoped pages, and a no-year (no AcademicYear exists) case where the links are hidden rather than broken.

## Decisions needed (my recommendation first)
1. **Which year do the new sidebar links open?** Recommend `_current_academic_year(today)` (year containing today, else latest) — it already exists with a documented rationale; move it to a small shared module so the context processor can use it. The setup checklist's "latest by start date" stays as is.
2. **Group names:** "Assessments & Results" (audit wording). Keep the other five group titles unchanged in this gate; regrouping Import is deferred.
3. **Collapsing:** open the active group + Home by default, others collapsed, remembered per browser via `localStorage` (progressive enhancement only).
4. **Sidebar row height:** audit says both 40px and 44px. Recommend keeping current rows in S3 (collapsing already fixes the scroll); revisit with the visual redesign.

## Verification (every gate)
`manage.py check`, full suite (`--parallel 4`), `collectstatic`, then screenshots at 1366×768, 1440×900, 1920×1080 for Admin, and 390/768/1280 for Teacher & Guardian (must be unchanged). Rollback = revert the PR; no migrations.
