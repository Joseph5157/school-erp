# UI-D1-3D1 — Guardian People Forms (scoped implementation specification)

Status: **IMPLEMENTED on `ui/admin-desktop-d1-3d1-guardian-forms`; draft PR pending review** (23 October 2026). Screenshot evidence: `docs/ui-reviews/ui-d1-3d1/`.
Branch: `ui/admin-desktop-d1-3d1-guardian-forms`.
Base: `main` at `0bccbfb0f74b80a3ae1dd999872fa3d81b682bb4` (D1-3C PR #98 merge `7cbf201` and docs-only closeout `0bccbfb`).
Parent: `docs/ADMIN_DESKTOP_D1_3_ADMISSIONS_PEOPLE_PLAN.md`; design: `docs/UI_DESIGN_RULES.md`, `docs/ADMIN_DESKTOP_TABLER_REFERENCE.md`, accepted D1-3A/B/C and existing Applicant/Teacher forms.

## Why this gate

Source audit of `main` on 23 October 2026 found that `applicant_form.html` and `teacher_form.html` already use the standard shared page header, `erp-form`, required legend, field rendering, form-level errors and action bar. The three Guardian relationship/contact forms below still use a raw H1 and `{{ form.as_p }}`. Migrate only these legacy layouts, leaving the two already-compliant forms alone.

## Allowed scope — three templates only

1. `core/templates/core/guardian_form.html` (Create Guardian and Edit Guardian)
2. `core/templates/core/applicant_guardian_form.html` (Associate Guardian with Applicant)
3. `core/templates/core/student_guardian_form.html` (Associate Guardian with Student **or** Change relationship)

May additionally add focused UI/template tests and synthetic screenshots under `docs/ui-reviews/ui-d1-3d1/`, update this and the parent plan's status, and use **small template-scoped** CSS in `static/css/erp.css` only if truly necessary. Reuse the pre-existing form styles, tokens and partials first.

**Forbidden:** views, forms Python classes, model/service/database behavior, queries, validation rules, URL config, permissions/authorization, navigation, Student/Teacher/Guardian portal pages, school base shell, shared partial rewrites, imports, credential/password screens, global CSS refactor, and unrelated Admin UI. No Tabler runtime. No D1-3D2, D1-4, Academic Year Rollover or deployment.

## Required visual/markup outcome

- Replace raw H1 on all three pages with `partials/_page_header.html`: appropriate eyebrow (People / Admissions), concise accurate title and, where useful, a short purpose line. Maintain **one H1**; display relevant Applicant/Guardian/Student names with wrapping and escaped Django template values.
- Use `<form method="post" class="erp-form">` and preserve `{% csrf_token %}`, POST target semantics (no new `action` value if original relied on the current URL), all field names/values, order, required flags, field types, help text and prefilled/invalid values.
- Use `partials/_form_required_legend.html`, then render `form.non_field_errors` in the existing `erp-form-errors` with `role="alert"` **when present**, and each field with `partials/_form_field.html`. Avoid duplicate non-field errors and duplicate field rendering. Do not change the shared partial.
- Group Submit and Cancel in `erp-form-actions`. Preserve exact submit button text per existing mode: Guardian `Save guardian`; Applicant Guardian `Save guardian link`; Student Guardian create `Save guardian link`; Student Guardian relationship edit `Save relationship`.
- **Cancel destinations:** Create Guardian -> existing `core:guardian-list` (currently no Cancel; add conventional escape), Edit Guardian -> existing `core:guardian-detail` for that guardian (existing Cancel), Associate Applicant Guardian -> existing `core:applicant-detail` for that applicant (currently no Cancel; add conventional escape), Student Guardian create/edit -> existing `core:student-detail` for that student (existing Cancel). All Cancel controls remain GET links, never data-mutating actions.
- Keep the create/edit branch conditions (`guardian`, `link`) and existing mode-specific text; don't expose a Guardian-edit link to an unauthorized user. View-level authorization must remain exactly as is.
- For Applicant Guardian, keep the Applicant fixed from URL/context; **do not** add an editable Applicant field or alter guardian matching/duplicate-validation logic.
- For Student Guardian, keep Student fixed from URL/context; when editing an existing relationship the form must continue to edit **relationship type only** (not select/change Guardian or Student). No new guardian access grants or implied Portal access.
- Keep the behavior of successful submissions and server-side errors unchanged; a displayed Guardian relationship is **not** a Portal access grant.

## Acceptance matrix (test and visual evidence)

1. **Rendering:** one H1, correct title/purpose, shared header, `erp-form`, CSRF, required legend, field labels and help, `erp-form-errors`, `erp-form-actions`; verify actual form fields in correct order and modes.
2. **Modes and actions:** Guardian create vs edit; Applicant Guardian create; Student Guardian create vs change-relationship. Exact submit labels and Cancel targets. Guardian create form must preserve all three contact fields; student edit must have relationship-only field.
3. **Security/workflows:** the original GET and POST URLs/methods, domain-side duplicate association validation, valid success destinations, no writes on GET, existing route permission restrictions. No direct/implicit Student Portal data access or password/credential disclosure. Focused regression tests should assert denied/limited role outcomes.
4. **Invalid submissions:** submit missing required fields, bad values, and duplicate association when applicable; assert unchanged server validation outcomes, retained submitted values, visible field-local and non-field errors (existing partials), no double rendering.
5. **Responsive/accessibility:** screenshots with **synthetic** data at 390, 768, 992, 1024, 1280, 1440px for create/edit paths, valid and error states, long Guardian/Student/Applicant names; no page-level overflow, logical keyboard focus, visible labels and readable touch targets, usable Cancel. Browser evidence is local only, not staging.
6. **Checks:** `python manage.py check`, focused Guardian/Applicant/Student relationship + auth tests, newly added UI tests, existing D0–D1-3C UI regression tests, and full local PostgreSQL suite (`--parallel 4`). Report actual counts/results and any limits. No CI claim without CI evidence.
7. **Hygiene:** use a fresh worktree or clean branch from exact main baseline. Stage explicit filenames only (never `git add docs` or entire dirs); use throwaway Postgres database and synthetic fixtures. Do not remove/stop old scratch DBs, servers, worktrees or `.superpowers/sdd`.
8. **STOP:** open **draft PR** targeting `main` with diff, tests, screenshots and known limits. No ready-for-review, merge, deploy, D1-3D2, D1-4 or any unrelated follow-on without separate review and authorization.

## Deferred / separate decisions

- **D1-3D2:** `core/templates/core/guardian_account_form.html` (Create/Link Guardian Portal login) needs a separate, security-sensitive form UI gate for identity verification and one-time-password instructions; **not authorized by D1-3D1**.
- **Shared `_form_field.html` accessibility:** explicit `aria-invalid` / `aria-describedby` is not guaranteed by the current rendering partial. Do not alter site-wide component behavior in this gate; log a separate targeted shared-component accessibility review.
- Existing Admin People Lists copy, Teacher Add button, Guardian List search/sort/pagination, consent UI and credential/confirmation pages are separate future work.
