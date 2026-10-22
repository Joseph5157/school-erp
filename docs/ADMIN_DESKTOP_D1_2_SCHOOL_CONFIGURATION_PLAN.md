# UI-D1-2 — School Configuration Desktop Adoption

Status: **D1-2A ACCEPTED and MERGED** (PR #94, merge `19fd57b`, 22 October 2026). **D1-2B planning opened**, no application code started; see `docs/ADMIN_DESKTOP_D1_2B_CLASS_TEACHER_MAPPING_PLAN.md`.
Implementation branch: `ui/admin-desktop-d1-school-configuration`.
Base: `main` at merge commit `45b00883b095a7cb04f3c0a8c25afd8450aabeea` (PR #93, D1-1).
Design sources: `docs/ADMIN_DESKTOP_D1_PLAN.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, `docs/UI_DESIGN_RULES.md`, `docs/UI_REFERENCES.md`.
A draft PR and explicit acceptance are required before merge. Do **not** merge or deploy autonomously.

## Goal and approach

Apply the approved Tabler-inspired School ERP desktop components from D0 to existing **school configuration** list screens. This is a **presentation-only** gate, not a new feature. Use `templates/partials/_page_header.html`, `erp-panel`, `erp-table-scroll`, existing empty-state/status components and the School ERP green design tokens. Retain Django server-rendering, Bootstrap 5.3.3, existing roles and view authorization. Do not add Tabler as a dependency or duplicate reusable components.

One tightly bounded implementation PR for **D1-2A** below, then stop. **D1-2B** is an explicitly deferred follow-up requiring separate acceptance and implementation work, even if it shares the same UI-D1-2 theme.

## D1-2A — Class, Subject, Term and Offering lists (ACCEPTED / MERGED)

**Outcome (PR #94, approved at `f4f4306`, merged `19fd57b`):** presentation-only; four templates plus a 6-line `.erp-offerings-table` rule in `erp.css`. Full PostgreSQL suite 2,292 passing. Accepted decisions: Section + Term lookup stays below the table and now shows its validation errors; table-local horizontal scroll for Subject Offerings on phones and stacked Term actions at 1024px are accepted trade-offs. Screenshots (seeded throwaway data): `docs/ui-reviews/ui-d1-2a/`.

### Exactly four existing pages in scope

1. `core/templates/core/class_grade_list.html` — use the shared page header and permission-gated **Create Class/Grade** action; present Class/Grade and real `sections.count` in a scoped, labelled table/panel. Preserve class-detail navigation, actual row order, and permission-aware empty state.
2. `core/templates/core/subject_list.html` — shared header with permission-gated **Add Subject**; present Name, Code, and Active/Inactive status as truthful, accessible text/badge; keep the Edit link gated by `change_subject`. Keep the established subject order and empty-state behavior. **Do not add a nonfunctional search or new filters**: these would need view/URL work and are not approved for this presentation gate.
3. `core/templates/core/academic_year_terms.html` — shared header with year in subtitle/context and permission-gated **Add Term**; a labelled term table that retains `display_order`, explicit start/end dates, Edit, Publish to guardians, and Remarks links with their existing permission tests. Do **not** infer publication status, rewrite academic term ordering or blur the meaning of term dates.
4. `core/templates/core/academic_year_offerings.html` — shared header and permission-gated **Offer a Subject** action; improve the table of Class/Grade, **Report card position**, Subject, Sections, and Edit order and Sections. Keep existing `display_order` values, Section link scope (including the exact meaning of **All Sections**), and the read-only **Which Subjects does a Section take?** GET lookup (Section + Term). Adapt the existing lookup as a visibly labelled filter strip only if it preserves submissions and errors without JS. **Do not change ordering, membership, report cards, grades, or publish behavior.**

### Implementation constraints

- Allowed changes: the four templates above; small clearly scoped rules within `static/css/erp.css` **only when existing D0 utilities are insufficient**; focused tests; screenshot evidence and this plan.
- No changes to models, migrations, forms, views, services, URLs, database queries, `core/navigation.py`, authentication, authorization, teacher/guardian portals, global app shell, or academic business rules.
- Do not restyle creation/edit forms in this gate; they are linked destinations, not D1-2A targets.
- Do not introduce sorting, searching, filtering, counts, or indicators not currently supported by real view data. Do not invent sample data, statuses or new route destinations.
- Render actions with the existing permission conditions. A user with view-only permissions must not see write actions, but still must see permitted data. An authorized user must keep exactly the existing target URLs and methods.
- Prefer genuine HTML `table` semantics: a caption or labelled scroll region, `th scope="col"`, an accessible final Actions header when relevant, and `tabindex="0"` on independently scrollable regions.
- Full-width *desktop table* presentation is fine; longer prose and forms keep sensible reading widths. At narrow widths, table-local horizontal scroll is acceptable, **page-level horizontal overflow is not**. Protect dates, subject codes and compact identifiers from mid-token line breaks while avoiding clipping longer subject names.
- Use page-header action layout consistent with D0 Academic Years and D1-1. Avoid wrapping a card inside a card. Do not change the teacher or guardian navigation/shell.

### UI-D1-2A acceptance

1. **Functional equivalence:** identical school/academic year, class, subject, term, offering, Section-scope and result-publication behavior before/after; untouched GET/POST signatures.
2. **Permission matrix:** confirm add/edit/term-publication/remarks links still appear only with existing perms and no unauthorized route is introduced.
3. **Visual consistency:** all four pages follow the same approved header, spacing, table panel, actions, and empty-state patterns; no new theme layer.
4. **Responsive:** browser screenshots (seeded, disposable data) at **390, 768, 992, 1024, 1280, 1440px** for all four pages. Include long subject names/codes, two academic years, several terms, multiple class/section offerings, and empty/view-only states where feasible. Annotate any table-local scrolling and ensure no document-level sideways scroll.
5. **Accessibility:** keyboard focus and skip link, table column headers, readable statuses not color-only, visible focus ring, usable responsive controls, and labelled Section + Term lookup.
6. **Data integrity regression:** test explicit Term order, Subject Offering `display_order` (the report-card order), Sections versus All Sections, and safe link rendering. **Do not alter or recompute any ordering.**
7. **Test evidence:** run `python manage.py check`, targeted school configuration, assessment/offering and authorization tests, new focused template tests, and full PostgreSQL suite if available. Report real totals and failures; do not claim tests were run if skipped. Browser screenshots use a throwaway demo DB, not staging.
8. **Stop:** commit D1-2A changes to this branch and open a **draft PR**, with file list, before/after images, regressions, tests and limitations. No merge, no deployment, no D1-2B or D1-3 work.

## D1-2B — Teacher-mapping adjacent screens (PLANNED; not implemented)

After **D1-2A review/merge**, open a fresh branch for class teacher mapping and assignment overview, scoped to:
- `core/templates/core/academic_year_class_teachers.html`
- `core/templates/core/academic_year_assignments.html`

Do not duplicate the D1-1 `teacher_assignments.html` change or copy subject-assignment rules blindly. Preserve class-teacher effective dating, permission gating, planned deletion constraints, teacher-gap indicators, and existing Copy from another year rules. Assess responsive history entries and table-local scroll separately.

## Later gates

D1-3 Admissions/People, D1-4 Attendance Administration, D1-5 Assessments/Results, D1-6 Communication/Operations remain future separate work. `docs/ACADEMIC_YEAR_ROLLOVER_PLAN.md` remains queued for a **Rollover 0 domain ADR freeze**, not part of any D1 UI branch.
