# UI-D1-3D2 — Guardian Portal Account Create/Link Form (planning specification)

Status: **PROPOSED / AWAITING DESIGN APPROVAL — documentation-only planning, no implementation authorized** (23 October 2026).
Planning branch: `plan/ui-admin-desktop-d1-3d2-guardian-account-form`, from `main` `af550ea8ae5db459975537a8074d9d1a4bbe2f89` (D1-3D1 PR #99 merged as `de63dd6`, docs closeout `af550ea`).
Parent: `docs/ADMIN_DESKTOP_D1_3_ADMISSIONS_PEOPLE_PLAN.md`. Visual references: `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, and accepted UI-D1-3D1. This plan does **not** authorize merge, deployment, D1-4 or rollover work.

## 1. Current source audit and purpose

The sole target template, `core/templates/core/guardian_account_form.html`, is shared by two administrator workflows and currently uses a raw H1, `form.as_p`, raw non-field errors and an ungrouped submit/Cancel row. Its distinct identity-verification warnings are valuable and **must be preserved**.

- **Create**: GET/POST `core:guardian-account-create` (`guardians/<pk>/account/create/`), view `guardian_account_create`, `mode="create"`, form `GuardianAccountCreateForm`. On successful POST, service generates a new login and temporary password, requires change on first sign-in, records verification/audit, and returns a **one-time, no-store credential slip** rendered by `_credential_slip`. Not a redirect.
- **Link**: GET/POST `core:guardian-account-link` (`guardians/<pk>/account/link/`), view `guardian_account_link`, `mode="link"`, form `GuardianAccountLinkForm`. On successful POST, links an **existing active** login by exact normalized username, records verification/audit and redirects to `guardian-detail` with a success message. **No password is generated or changed**.
- Both views require `@administrator_required("core.add_guardianaccount")`; POST includes CSRF. Each form has **exactly three fields in order**: `username`, `identity_verification_method`, `identity_verification_note`. The link-mode username is labelled "Existing login username" with existing exact-username help; create-mode uses the existing username rules. Verification method choices are In person with documents / Against school records / Other (described in note). Verification note is mandatory with existing help advising **no document numbers**.
- Services `core/guardian_accounts.py` reject existing active account for Guardian, invalid/reused usernames as applicable, inactive existing login, and login already linked to another guardian. They maintain atomicity and `SecurityEvent` records; Guardian accounts and Student data-access grants are **separate**.
- `core/templates/core/guardian_credential_slip.html` and `_credential_slip` are **outside this gate**. The slip has `Cache-Control: no-store, no-cache, must-revalidate, private`; password only passes to that one response. Do not capture, print, commit or log even synthetic credential-slip screenshots in this UI gate.

## 2. Proposed single-gate scope and exclusions

**Allow only after this plan is approved:** one modified template `core/templates/core/guardian_account_form.html`; focused presentation/regression tests; synthetic **pre-submit/invalid** screenshots in `docs/ui-reviews/ui-d1-3d2/`; plan status/doc closeout; at most a tiny, scoped CSS addition in `static/css/erp.css` if unavoidable. Prefer reusing `erp-guardian-form-page` from D1-3D1 (verify no negative impact) and the existing `erp-*` design tokens, without changing shared partials.

**No changes to:** `core/views.py`, `core/forms.py`, `core/guardian_accounts.py`, accounts, models, migrations, query scopes, audit, URLs, permissions, templates/base shell, Student/Teacher/Guardian portals, credential-slip template or response headers, shared `_form_field.html` or `_page_header.html`, lockouts, password reset, revoke/username operations, D1-4, Academic Year Rollover. No Tabler runtime and no new JS requirement.

## 3. Proposed design contract

1. Use shared `partials/_page_header.html` with one H1, mode-accurate titles: **Create portal account** / **Link an existing login**. Eyebrow "People" or "Guardian Portal". Show the Guardian's name as escaped readable context below the heading; wrap very long names and unbroken identifiers at 390px (and 360px where feasible); no real account usernames or secrets hard-coded.
2. Preserve the explicit human identity verification warning in both modes, adjacent to the instructions and above the form. State that the verification method and note must reflect an identity check **already carried out**; do not imply the software verifies identity. Keep the prohibition on document numbers in the existing help text; do not add ID-number, document upload or evidence fields.
3. For **Create**, preserve explanatory text: a temporary password appears once on the next page, for offline delivery, and must be changed on first sign-in. Avoid asserting that simply creating the account permits viewing any Student. Clarify if helpful that Student Portal access is granted independently.
4. For **Link**, preserve explanatory text: use the **exact existing username** of the already-active login; use for a person who also has another role (e.g., teacher/parent); the existing password is not changed. **Never** add username search/suggestions, auto-complete from student/phone/email/name, account-existence previews, or password inputs in this visual gate.
5. Use `<form method="post" class="erp-form">`, unchanged same-URL POST target, `{% csrf_token %}`, `partials/_form_required_legend.html`, `form.non_field_errors` **once** inside `erp-form-errors` with `role="alert"` when present, and iterate unchanged `form` fields through `partials/_form_field.html` in the supplied order. Maintain submitted values and field errors on invalid POST. No shared component refactor.
6. Use `erp-form-actions` for exact existing labels **Create account** / **Link login**, and a Cancel GET link to `core:guardian-detail` with the same `guardian.pk`. No destructive styling for standard actions and no additional irreversible confirmation step. Keep one submit button and one Cancel link; do not accidentally submit on Cancel.
7. Preserve view-/service-enforced outcomes and authorization. Link creates a link only: no password change or Student access grant. Create goes to the unchanged one-time slip; link redirects to Guardian detail. Errors are shown, not swallowed. Do not display a temporary password before a successful Create POST or anywhere on Link pages.
8. Do not replace the server form with JavaScript, client-side identity checks, live username existence tests or new browser storage. Native validation and keyboard usage remain usable with JavaScript off.

## 4. Verification and acceptance before design signoff

| Test area | Required evidence |
| --- | --- |
| Modes and markup | Create and Link GET render one H1, correct Guardian context, distinct accurate warning, shared form/header/legend/errors/action bar, exactly three expected fields in order, unchanged labels/help/required flags, exact buttons and Cancel href; no password input or student-grant action |
| Invalid POST | Missing username/method/note, invalid create username, unavailable/duplicate create username, nonexistent/inactive link username, already-linked login/Guardian; errors presented once, original values retained and no unintended account/link/audit creation |
| Valid POST | Create still returns password slip **only to the authorized POST response**, no-store headers and must-change-password; Link still redirects and keeps existing credentials; SecurityEvents and identity-verification audit fields remain correct; no Student access grant in either mode; use isolated synthetic users |
| Authorization | Admin permitted; teacher/guardian/view-only/anonymous denied for both GET and POST, with no writes on denial. Preserve `core.add_guardianaccount` (do not assume `view_guardian` permission). Record existing Cancel-to-detail 403 issue for add-without-view permission as a separate workflow question |
| Visual and accessibility | Synthetic **pre-submit and invalid** states at 390/768/992/1024/1280/1440px for both modes; long names, 200-char verification note and error cases at 390 and 1280; page horizontal overflow zero and heading readable; keyboard Tab/Shift+Tab order, visible focus, touch target at phone width. Never capture the successful credential-slip response |
| Test quality | `manage.py check`; new focused D1-3D2 UI tests and existing `test_phase6_guardian_accounts`, security, authorization and relevant UI-D1 tests; final full local PostgreSQL suite (`--parallel 4`). Report actual counts, DB, environment and what was **not** independently verified; do not claim CI/staging without evidence |
| Hygiene | Use fresh branch/worktree from **current updated main after user approval**; stage exact named files; keep old worktrees, servers, ignored SDD state and unrelated databases intact. Use only throwaway synthetic screenshots and test data. Open **draft PR** and stop for design review; merge and deploy require separate authorization |

## 5. Known issues explicitly deferred

- **Permission asymmetry:** A user may have `core.add_guardianaccount` and submit Create/Link but lack `core.view_guardian`, so Cancel or Link success destination may 403. Do not silently broaden roles or change destination in a template-only gate; document a separate workflow/permissions decision.
- **Shared form-field ARIA associations** (`aria-invalid` / `aria-describedby`) are not guaranteed by `_form_field.html`. Separate shared-component accessibility review only.
- **Guardian credential slips, reset and revoke screens** remain outside scope. Their sensitive response behavior is protected by regression checks, not UI migration here.
- **Sidebar keyboard focus styling** and desktop Cancel height are global/shared UI follow-ups, not reasons to widen this gate.

## 6. Gate review checkpoint

Planning outcome: **UI-D1-3D2 should be one small template-only gate**, not a new authentication feature. Await explicit **plan approval** to create the implementation branch and hand a narrow prompt to Claude Code. Never interpret approval of this plan as merge or deployment authorization.
