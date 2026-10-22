# UI-D1-3 — Admissions and People (implementation specification and gate plan)

Status: **D1-3A COMPLETE — design accepted and merged (PR #96, merge `1fedaae`, implementation `5c8f0a8`, 22 October 2026); D1-3B COMPLETE — merged (PR #97, merge `12c3e10`, 22 October 2026); D1-3C authorized on a dedicated branch (planning only so far); D1-3D deferred**.
Planning branch: `ui/admin-desktop-d1-admissions-people` (from `main` `9a77ef3`, after D1-2B merge `e43d477`).
Parent decisions: `docs/ADMIN_DESKTOP_D1_PLAN.md` (D1-3 line), `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, `docs/UI_DESIGN_RULES.md`, accepted gates D0 (#92), D1-1 (#93), D1-2A (#94), D1-2B (#95).

## Purpose / gate discipline

Bring the remaining **People/Admissions admin pages** onto the accepted project-owned Tabler-inspired pattern: `partials/_page_header.html`, `erp-panel`, `erp-toolbar`, labelled `erp-table-scroll` regions, `erp-status` badges, existing `erp-*` tokens. Django server-rendered templates and Bootstrap 5.3.3 only; **no Tabler runtime**.

Each sub-gate below is its own branch/draft PR, implemented and accepted separately (as D1-1, D1-2A, D1-2B were). **Nothing in this document authorizes implementation.** Students (`student_list.html`) were done in D0 and are the reference pattern; do not redo them.

Forbidden in every sub-gate (same as D1-2B): views, forms, models, migrations, URL config, services, queries, auth/permissions, navigation, portals (Guardian/Teacher), base shell, data writes or workflow changes. A functional defect found along the way is reported separately, not fixed silently.

## Current state (code review, 22 Oct 2026)

| Page (template) | Header | Panel/scroll region | Toolbar | Notes |
|---|---|---|---|---|
| `applicant_list.html` | shared | scroll region, **no panel** | plain `input-group` form | sortable head + footer partials already; status filter only |
| `guardian_list.html` | shared | **none** (bare table) | none | view passes an unpaginated queryset; Create button sits outside the header; extra links line (access reviews, lockouts) |
| `teacher_list.html` | shared | scroll region, **no panel** | plain `input-group` form | search + status, sortable, paginated |
| `applicant_detail.html` | shared (+status) | bare `<dl>` and table | – | decision links, progress POST form, reconciliation alert, Guardians table |
| `guardian_detail.html` | **raw `h1.h3`** | bare tables | – | `_section_nav`, four permission-gated sections, consent include, many action buttons |
| `teacher_detail.html` | shared | events table has scroll region | – | `<dl>`, action row, assignment `<ul>`s |
| `guardian_access_reviews.html` | **raw `h1.h3`** | bare table with inline POST form per row | – | pending rows + "Recent decisions" `<ul>` |

Out of scope on purpose: credential slip pages (`teacher_credential_slip`, `guardian_credential_slip`: one-time passwords, print layout — separate review), confirm/reset/username/revoke forms, `student_detail`/`student_*` (D0 and later), import pages and lockouts (D1-6), `_guardian_consent.html` internals (notification module).

## Sub-gates

### D1-3A — People lists (Applicants, Guardians, Teachers)

Templates: `applicant_list.html`, `guardian_list.html`, `teacher_list.html`.

Outcome:
- Wrap each table in `erp-panel` + labelled `erp-table-scroll` (`role="region" aria-label`, `tabindex="0"`, `th scope="col"`), matching `student_list.html`.
- Convert the Applicants status filter and Teachers search/status form to the `erp-toolbar` row/column layout used by Students (labels visible, Search/Clear actions, hidden `sort` input preserved, same field names and query semantics). **No** new filters, chips or counts.
- Guardians: keep the unpaginated, unsorted data exactly as supplied. Move "Create Guardian" into the page header primary action under the existing `perms.core.add_guardian` gate; keep the access-reviews / lockouts links under their existing permissions, as quiet header-adjacent links. If search/sort/pagination is desired, that is a **separate functional gate**, not D1-3A.
- Keep empty-state meanings (including the add/register shortcut buttons and their permissions) unchanged.
- Preserve status tones (`erp-status`) and table order/pagination footer.

Acceptance: authorization parity (add/register/create links only under today's permissions; `manage_teacher_accounts` empty-state link), filter query state kept through sort and pagination, empty and filtered-empty states, one `h1`, labelled regions, no page-level overflow at 390/768/992/1024/1280/1440.

### D1-3B — Record detail pages (Applicant, Teacher)

**Implementation authority (22 October 2026):** D1-3B only; follow the binding [D1-3B gate specification](ADMIN_DESKTOP_D1_3B_APPLICANT_TEACHER_DETAIL_PLAN.md) on `ui/admin-desktop-d1-3b-record-details`. D1-3C and D1-3D remain unauthorized. The shared stop rules still apply.

Templates: `applicant_detail.html`, `teacher_detail.html`.

Outcome: summary as a panel (`erp-panel` with the existing `<dl>` fields in a tidy two-column description list), actions grouped in the existing `erp-form-actions` / toolbar idiom, related tables (Applicant Guardians, Teacher security events) in labelled panels, assignment lists kept in full. Preserve: decision links gating (`change_applicant`, PENDING, no student), Progress-to-Student POST + CSRF, reconciliation alert text, Reset/Username/Deactivate/Reactivate links and their confirm pages, workload link permission, event rows.

Acceptance: every conditional block verified with a fixture (pending/accepted/rejected applicant, with and without Student record; active/inactive teacher), long-name stress, permission parity, no sensitive data added to the page.

### D1-3C — Guardian detail and access reviews

**Implementation authority (22 October 2026):** D1-3C only, from cleaned main `daeab47`, on `ui/admin-desktop-d1-3c-guardian-access`. Follow the [binding D1-3C specification](ADMIN_DESKTOP_D1_3C_GUARDIAN_ACCESS_PLAN.md); preserve every permission, POST+CSRF, and guardian data-access rule. D1-3D/D1-4 remain unauthorized.

Templates: `guardian_detail.html`, `guardian_access_reviews.html`.

Highest-risk sub-gate (portal accounts and access grants), therefore separate:
- Replace raw `h1` with the shared header (eyebrow "People"), keep `_section_nav` and the anchored `<section>` ids/ARIA headings.
- Put each section (Applicants, Portal account, Student access, History) in a panel; tables get labelled scroll regions; per-row Grant (POST + CSRF) / Revoke links and account actions keep exact permission checks and URLs; "under review — no data shown" and revoked/earlier-link text must remain visible (no tooltip-only or color-only information).
- Access reviews: panelled pending table with the inline decision form kept as POST + CSRF (same `decision`/`note` field names and `required` select), "Recent decisions" list preserved in order; no auto-decision semantics.
- `_guardian_consent.html` is included unchanged.

Acceptance: fixtures with and without active account, inactive login, must-change-password, revoked grant, under-review grant, viewer without portal permissions; POST behavior and CSRF verified; credential-bearing pages untouched.

### Optional D1-3D — People forms (deferred; only if D1-3A–C accepted)

`applicant_form`, `guardian_form`, `teacher_form`, `applicant_guardian_form`, `student_guardian_form`, `guardian_account_form`. Most already use `erp-form`; audit first and propose only if real inconsistencies remain.

## Shared acceptance contract (each sub-gate)

1. **Diff scope:** named templates + at most small scoped `static/css/erp.css` rules (reuse `erp-assignment-*`, `erp-toolbar`, `erp-panel` first), UI tests, screenshots in `docs/ui-reviews/ui-d1-3a|3b|3c/`, plan status line. No backend/permission/route change.
2. **Authorization parity tests:** administrator and view-only user per page; every action link/form appears only under its pre-existing permission; POST forms keep method and CSRF.
3. **Data fidelity:** same rows, order, filters, counts and empty-state meaning; nothing hidden or truncated; no invented statuses.
4. **Accessibility:** single `h1`, `th scope="col"`, hidden "Actions" headings where unlabeled, labelled keyboard-focusable scroll regions, visible status text (never color-only), strong link names (hidden context text where needed), skip link intact.
5. **Responsive evidence:** before/after on a seeded disposable Postgres DB at 390, 768, 992, 1024, 1280, 1440px (admin + view-only + empty states), scrolled captures where Actions start off-screen, page-level overflow measured (contained table scroll acceptable). Run `collectstatic` and restart `runserver` first (stale `staticfiles/` bit D1-2A). Seeded screenshots are not staging verification.
6. **Tests:** `manage.py check`, focused People/authorization tests, existing D0/D1/D1-2A/D1-2B UI tests, new focused tests, full PostgreSQL suite (`--parallel 4`). Report real totals and DB; no claimed CI (none exists).
7. **Hygiene:** stage **exact files only** (never `git add docs` or directories; the working tree holds unrelated untracked files). Draft PR, merge-commit style, no merge/deploy without separate go-ahead.
8. **Stop** after each sub-gate for design acceptance.

## Risks and decisions for review

- **Guardian list functionality gap** (no search/sort/pagination, unlike Applicants/Teachers/Students): a UI-only gate cannot fix it. Decide whether to log it as a separate backend/UX gate.
- **Sensitive screens:** credential slips and password flows are excluded; propose their own review (print CSS, one-time-secret handling).
- **Sequencing:** recommend A (lists) → B (applicant/teacher detail) → C (guardian detail/access reviews).
- **Seed data:** screenshots must use synthetic names/phones/emails only; never real student or guardian data.
- Academic Year Rollover remains separate and starts with its Rollover 0 ADR freeze.

## Review decisions (22 October 2026)

- **D1-3A approved for implementation as a standalone gate only**, after normal branch hygiene; D1-3B, D1-3C, D1-3D remain unapproved for implementation. Each requires its own review and acceptance. The implementation PR must remain draft until accepted.
- **Guardian list search/sort/pagination:** DEFER to a separate **functional** design/implementation gate. Existing unpaginated row order and exact data scope must not change in D1-3A. Do not add decorative/nonfunctional search or fake pagination. Record this as a known scalability/usability gap, not a D1-3A acceptance failure.
- **Existing permission gates are binding:** the Guardian Access Reviews and nested Login Lockouts links must keep their exact current predicates; the Teacher Create action must not be changed silently to a new permission predicate. Verify actual current route-level authorization and rendered behavior in the test matrix.
- **Public-repository artifact hygiene:** use entirely synthetic fixtures for screenshots and tests. The earlier accidental Guardian retest images/HTML were removed from the current tree, but remain in Git history of this public repository. A separate privacy triage should assess whether those historic artifacts show real identifiable people, contact details, session material, or school records. Do not copy them forward, do not assume a keyword scan of HTML can inspect screenshot pixels, and do not rewrite shared history without a reviewed remediation plan.
- **Branch sequencing:** create a fresh implementation branch from this accepted planning branch (which is one documentation commit ahead of `main`); keep the sub-gate changes and evidence in a draft PR targeting `main`. Do not use a stale or unrelated local working tree. After D1-3A merge, start D1-3B from updated `main`.

## D1-3A completion record (22 October 2026)

- **Delivered:** Applicants, Guardians and Teachers lists on `erp-panel` / `erp-toolbar` / labelled `erp-table-scroll`; Guardian "Create Guardian" in the page header under the existing `add_guardian` gate; access-reviews and lockouts links keep their exact predicates. No view, form, model, URL, permission, query or CSS change.
- **Review and merge:** draft PR #96 design-accepted at `5c8f0a8`; merged with a merge commit as `1fedaae`. Not deployed.
- **Verification (local PostgreSQL 18, no CI exists):** `manage.py check` clean; full suite `--parallel 4` 2323 tests OK; 93 focused tests OK (20 new in `core/tests/test_ui_admin_desktop_d1_3a.py`). Synthetic before/after screenshots in `docs/ui-reviews/ui-d1-3a/`; page-level overflow 0 at 390/768/992/1024/1280/1440. Seeded captures are not staging verification.

### Deferred follow-ups (none started)

1. **Filtered-empty copy correction (small task).** Filtered results on Applicants and Teachers still read "No Applicants yet." / "No teachers yet." Change to wording such as "No applicants match these filters" (Students already does this) and update the pinned assertions in `test_ui_admin_phase3a.py` and `test_ui_admin_phase3e.py` in the same change.
2. **Teacher "Add teacher" button visibility.** The header action is unconditional in `teacher_list.html`; the page and `teacher-create` route both require `accounts.manage_teacher_accounts`, so behavior is equivalent today. Review explicit permission-gated visibility separately, without silently changing the predicate.
3. **Guardian list search, sort and pagination.** Functional gate: the list remains unpaginated and unsorted. Needs its own design and implementation gate.

Next: D1-3B is complete and merged (PR #97, merge `12c3e10`). D1-3C has a fresh implementation branch and accepted scoped specification; no application code started. Implement only D1-3C, open draft PR, stop for separate design acceptance.
