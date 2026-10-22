# UI-D1-3C — Guardian Detail and Access Reviews

Status: **COMPLETE — design accepted and merged (PR #98, merge `7cbf201`, implementation head `bc08a8d`, 22 October 2026); not deployed** (22 October 2026). Final evidence: 87 screenshots (40 before, 47 after), full PostgreSQL suite 2,420 tests OK; CSS additive only (`.erp-review-*`, `.erp-panel-head`, `.erp-row-context`, phone-only name-column caps). Evidence: `docs/ui-reviews/ui-d1-3c/` (synthetic data, local only — not staging verification). Known limits: on phones the tables scroll locally and row context scrolls out of view with the Decision/Actions column; no scroll hint; the pre-existing `_guardian_consent.html` include is unstyled (out of scope).
Implementation branch: `ui/admin-desktop-d1-3c-guardian-access`, created from `main` at `daeab47b8ddfb405c5b4080257236f568400b0ee` (D1-3B PR #97 merged `12c3e10`, documentation closeout `daeab47`).
Parent: `docs/ADMIN_DESKTOP_D1_3_ADMISSIONS_PEOPLE_PLAN.md`; use the established D0/D1-3A/B visual system, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md` and `docs/UI_DESIGN_RULES.md`.

## Objective and strict scope

Restyle **exactly two admin templates** with existing Django/Bootstrap 5.3.3 School ERP primitives (`partials/_page_header.html`, `erp-panel`, `erp-table-scroll`, `erp-*` tokens):
- `core/templates/core/guardian_detail.html`
- `core/templates/core/guardian_access_reviews.html`

Allowed additional files: narrowly scoped UI/template tests, fully synthetic before/after screenshots in `docs/ui-reviews/ui-d1-3c/`, this plan/status, and minimal scoped `static/css/erp.css` only if necessary. Reuse the D1-3B inset `.erp-table-scroll:focus-visible` rule.

**Forbidden:** views, services, models, migrations, queries, URL routing, forms modules, authorization rules, school calendar/enrolment logic, Guardian/Teacher portals, navigation or base shell, account/credential/password/confirmation pages, `core/_guardian_consent.html` internals, and actual data writes or functional change. Do not introduce Tabler runtime/dependencies. If a functional/security bug is found, report separately rather than changing domain logic in this UI gate.

## Guardian Detail — design outcome and parity contract

The page currently uses a raw H1, permission-controlled Edit contact details link, `partials/_section_nav.html` with `profile_sections`, contact `<dl>`, and conditional sections keyed by `profile_section_ids`. Preserve all field values and conditional visibility.

1. Replace raw H1 with a **single shared page header**, eyebrow "People", Guardian full name. Keep `Edit contact details` visible **only** for `perms.core.change_guardian`, same `core:guardian-edit` URL.
2. Contact details: use an accessible semantic definition list (Phone, Email) within a quiet `erp-panel`; keep exact default dash values. Keep section navigation, anchors, headings, and section-order semantics stable; section IDs `applicants`, `portal-account`, `student-access`, `history` must remain unchanged, as must their `aria-labelledby` relationships.
3. **Associated Applicants**: panel + labelled keyboard-focusable table scroll region; preserve name/detail links, relationship labels, original row ordering, and "Not associated with any Applicant." empty state.
4. **Guardian Portal account** appears only when `"portal-account" in profile_section_ids`. Preserve the real active-account state, username, verification actor/method/date, badges **must change password** and **login inactive**, all earlier revoked-account history and reasons. Maintain all original predicates/URLs:
   - `perms.core.reset_guardian_password` -> reset password link.
   - `perms.core.change_guardian_username` -> change username link.
   - `perms.core.change_guardianaccount` -> revoke account link.
   - With no active account, retain warning "Recording a Guardian grants no access." and Create/Link actions only under `perms.core.add_guardianaccount`.
   No account actions become direct submissions; keep confirmation/password screens outside scope.
5. **Student access** appears only when `"student-access" in profile_section_ids`. Keep explanatory text stating relationships do **not** themselves grant portal access. Panel + labelled focusable four-column table, semantic headings including visually-hidden Actions if necessary. For each relationship preserve student identity, relationship, active grant date/by, `under review — no data shown` explanation and existing review link, all revoked grant dates/by/reasons, not-granted and empty states, and view-supplied order. Retain:
   - Revoke link **only** when `row.active_grant` and `perms.core.change_guardianstudentaccess`, unchanged URL.
   - Grant form **only** when no active grant and `perms.core.add_guardianstudentaccess`, same action, `method="post"` and CSRF; never turn into GET/button with JavaScript.
   - No invented grant/review status or auto-grant; don't hide warning messages in tooltips, badges-only color, or scroll cut-offs.
6. **Account and access history** appears only when `"history" in profile_section_ids`. Preserve event ordering, timestamps, type, optional actor, and "None." empty state in a readable panel.
7. Preserve `Back to Guardians` link and the **unchanged** conditional `{% if consents is not None %}{% include "core/_guardian_consent.html" %}{% endif %}`; do not move or alter its access rules. Do not expose new data by relaxing section conditions.

## Guardian Access Reviews — design outcome and parity contract

1. Convert raw H1 to shared page header (one H1). Preserve the **full** instructional paragraph: missing current enrolment suppresses Guardian Portal data; human decision required; nothing automatically decided.
2. Panel + labelled/keyboard-focusable pending reviews table. Keep four columns (Student, Guardian, Last placement, Decision), existing rows and order, Guardian detail links, fallbacks ("No enrollment", "No pending access reviews."), and view-supplied `decisions` options without modification.
3. Inside Decision cell preserve `perms.core.add_guardianaccessreview` predicate and the per-row `method="post"` / `{% csrf_token %}` form with exact `core:guardian-access-review-decide` action, `name="decision"` required select, `name="note"` optional text input `maxlength="200"`, and "Record" submit. Provide accessible select/input names with table-row context without changing field names/values, POST behavior, or choice semantics. Ensure responsive controls are usable with keyboard and on phones (local table scroll acceptable).
4. "Recent decisions": separate quiet panel/section, preserve all events in existing order, student/guardian identities, trigger/decision, decision maker, optional note, and "None yet." message. Do not collapse/hide history or add filters or automatic actions.

## Security, regressions and evidence — mandatory

- **Permission/visibility matrix:** admin, `view_guardian`-only and a user with selectively granted account/grant/review permissions; ensure scoped sections and actions appear only as before. Never assume a display predicate implies a new route permission.
- **Fixture coverage:** Guardian with/without active portal account; disabled login; must-change-password; revoked earlier account; active, revoked, pending-review, not-granted student access; applicant links and empty states; populated/empty review queue; populated/empty decision history; optional consent include. Rendered text/URLs/HTML must match original semantics. For POST+CSRF check actual HTML and existing functional authorization tests, and ensure no mutation from GET.
- **Accessibility:** one H1, semantic H2 sections and anchored `aria-labelledby`, `th scope="col"`, visually-hidden actions heading if blank, labelled `erp-table-scroll` with `tabindex="0"` and visible D1-3B keyboard focus ring, discernible per-row action names/labels. Preserve navigation and skip links; color never the only information.
- **Responsive/browser:** synthetic local PostgreSQL fixture, before/after at 390, 768, 992, 1024, 1280, 1440 px, including admin, permission-limited user, long names, active/inactive/review/empty states and a scrolled table capture at 390. Refresh `collectstatic`; no **page-level** horizontal overflow. Local table scrolling acceptable. Use synthetic credentials and names only; screenshots are not staging verification.
- **Checks:** `python manage.py check`, focused guardian portal/admin access-control and UI regressions, new focused tests, full PostgreSQL suite (`--parallel 4`) when available. Report real totals; no claimed CI/staging results.
- **Git hygiene:** stage explicit filenames, not directories (especially never `git add docs`); keep local servers, demo databases, scratch worktrees and `.superpowers/sdd` untouched unless separately authorized.
- **Subagents:** independent Guardian Detail, Access Reviews and read-only security/a11y reviewers may collaborate; one main agent owns integration and final diff. Reviewers must inspect permission/POST parity, not just aesthetics.
- **STOP:** commit scoped changes and open **draft PR** against `main` with tests, diff, screenshots and known limitations. Do not mark ready, merge, deploy, implement D1-3D, start D1-4, or touch Rollover. Wait for final design acceptance.

## Deferred outside D1-3C

Filtered-empty copy correction on Applicants/Teachers; Teacher Add button visibility; Guardian List backend search/sort/pagination; credential slips and password flows; Admin Operations/lockouts; broader accessibility audit.
