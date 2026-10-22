# UI-D1-3B — Applicant and Teacher Record Details

Status: **D1-3B COMPLETE — merged (PR #97, merge `12c3e10`, head `1fe47a1`, 22 October 2026); D1-3C not started**. See the completion record at the end of this file.
Branch: `ui/admin-desktop-d1-3b-record-details`.
Base: `main` at `51f2f0a2a4e44dc10c638d2b5951de631cc05936`, after D1-3A PR #96 merge `1fedaae` and docs closeout `51f2f0a`.
Parent: `docs/ADMIN_DESKTOP_D1_3_ADMISSIONS_PEOPLE_PLAN.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, `docs/UI_DESIGN_RULES.md`, `docs/UI_REFERENCES.md`.

## Scope

**Only two screens**:
- `core/templates/core/applicant_detail.html`
- `core/templates/core/teacher_detail.html`

Presentation-only, Tabler-inspired **project-owned** styling with existing Django/Bootstrap 5.3.3 and `erp-*` components. Allowed extra changes: tiny *scoped* rules in `static/css/erp.css` only if existing utilities are insufficient, focused tests, synthetic screenshots under `docs/ui-reviews/ui-d1-3b/`, and this plan's gate status. Do not change views, forms, services, models, migrations, URLs, queries, permissions, navigation, Guardian/Teacher portals, credential slips or confirmation flows. No new capabilities or fake data.

## Applicant detail — acceptance target

- Keep the existing shared person-name header, admissions status badge, every field (admission status, optional decision date/reason, DOB, email, phone), and their current data / ordering. Present summary as a readable, padded `erp-panel` with semantic `<dl>` / `dt` / `dd`; do not flatten the fields into generic cards.
- Preserve **Admission decision** Accept/Reject links only when `perms.core.change_applicant`, `applicant.admission_status == "PENDING"`, and `not student`, using the exact existing confirmation URLs and labels.
- Preserve **Student progression** as the exact same `method="post"` with CSRF and `core:applicant-progress` action only when `not student`, accepted status and `perms.core.add_student`.
- When `student` exists, preserve its name, status, link to the student record, and the warning (including reconciliation guidance) when `applicant.admission_status != "ACCEPTED"`. Do not suppress or downplay inconsistent records.
- Guardians: keep existing permission-gated **Associate Guardian**, linked Guardian names, relationship labels, row order, "No Guardians associated yet" message and Back to Applicants link. Use a panel and a labelled/keyboard-accessible table region with semantic column headings. No additional guardian account actions.

## Teacher detail — acceptance target

- Keep name and username header, textual Active/Inactive status, and existing username/email/last sign-in/must-change-password fields with identical values and labels. Present summary in a padded `erp-panel` using a semantic definition list.
- Group existing account actions (Reset password, Change username, Deactivate **or** Reactivate) without changing any link target, available action, visibility condition, or confirmation workflow. **Do not expose secret credential values** or make the links into direct POSTs.
- Preserve Subject assignments and Class Teacher assignments *in full* and in existing order, including year/section/date/open-end semantics and empty "None" states. Use quiet sections/panels, not fake counts or icons.
- Preserve **View full workload** only under `perms.core.view_sectionclassteacher`.
- Recent security events: wrap the existing table in `erp-panel`, keep its labelled `erp-table-scroll`, `<caption>`, semantic column headers, event values/timestamps/actor, original order and "No events recorded" state. Do not broaden exposure or add record-level security event detail.

## Shared acceptance / stop rule

1. **Scope review:** only named templates, focused tests, optional narrow CSS, synthetic screenshots, and gate documentation. No permission/backend changes.
2. **Regression fixtures:** applicant PENDING/ACCEPTED/REJECTED, accepted-without-student, linked student, inconsistent student/admission status requiring reconciliation, linked and absent guardians; teacher active/inactive, long name, optional fields, assignments/empty states, events/empty states. Verify role conditions, links, and POST+CSRF are unchanged. Preserve actual data semantics.
3. **Accessibility:** one `h1`, semantic sections/headings/description list, `scope="col"` on table headings, accessible region label and `tabindex="0"`, meaningful link names, keyboard focus, no status conveyed by color alone. If applying a new heading hierarchy, preserve content ordering.
4. **Responsive:** before/after screenshots at **390, 768, 992, 1024, 1280, 1440px**; admin and permission-limited states plus long-name/empty cases. Check no page-level sideways scrolling; tables may scroll inside their labelled region. For browser screenshots, refresh collected staticfiles, use disposable local Postgres and *synthetic* people only. Do not copy artifacts from previous accidental historical commits.
5. **Checks:** `python manage.py check`, targeted applicant/teacher/authorization and D0–D1-3A UI tests, newly added focused tests, full PostgreSQL suite where available. Report exact results and any limitations; no CI/staging claim without evidence.
6. **Git hygiene:** stage exact intended filenames only; never `git add docs` or broad directories; avoid touching unrelated local servers, databases or scratch worktrees.
7. **Stop:** commit and open **draft PR** against `main` with diff scope, screenshots, tests and known limits. Do **not** merge, deploy, start D1-3C, D1-3D or Academic Year Rollover. Design acceptance required separately.

## Outside scope / deferred

- Filtered-empty copy for Applicants/Teachers lists, Teacher list Add button visibility and Guardian list search/sort/pagination remain independently tracked in the parent D1-3 plan.
- Guardian detail/access reviews are D1-3C: **not authorized in this gate**.
- Password flows and credential slips are excluded; audit them separately.

## D1-3B completion record (22 October 2026)

- **Delivered:** `applicant_detail.html` and `teacher_detail.html` on `erp-panel`, semantic `<dl>` and labelled `erp-table-scroll` regions (`scope="col"`). Every permission gate, link target, the progression POST with CSRF, the reconciliation warning, Deactivate/Reactivate and the assignment and event data were verified identical to the original templates. No view, form, service, model, URL, permission or query change.
- **Focus-ring fix (`f55a62f`):** reviewer-identified clipping of the focus ring on focusable scroll regions fixed with one scoped rule, `.erp-table-scroll:focus-visible { outline: 3px solid var(--erp-focus-color); outline-offset: -3px; }`. It applies to every `.erp-table-scroll` region site-wide. Verified by keyboard Tab at 1280 and 390 on Applicant detail, Teacher detail and the Applicants, Guardians, Teachers and Students lists (ring visible and inside its panel in all 12); evidence in `docs/ui-reviews/ui-d1-3b-focus/`.
- **Review and merge:** draft PR #97 (head `1fe47a1`) merged with a merge commit as `12c3e10`. Per-task spec/quality reviews and a final whole-branch review found no Critical or Important issues. Not deployed.
- **Verification (local PostgreSQL 18, no CI exists):** `manage.py check` clean; full suite `--parallel 4` 2353 tests OK (18 applicant, 13 teacher and 2 focus-rule tests new). Synthetic before/after screenshots in `docs/ui-reviews/ui-d1-3b/`; page-level overflow 0 in all after shots. Seeded captures are not staging verification.

### Known minor limits (none started)

- Loose heading-to-table gap in the Guardians and Recent security events panels; "Back to Applicants" sits about 12px inside the panel edge.
- Long unbreakable guardian names scroll inside their region with no scroll hint.
- Some tests are loose: guardian row order, `aria-labelledby` pairs, a brittle panel-count assertion, and the workload link's positive case only via admin.
- Focus-ring screenshots cover the pages listed above, not every screen that uses `.erp-table-scroll`.

Next: D1-3C (Guardian detail/access reviews) not authorized or started.
