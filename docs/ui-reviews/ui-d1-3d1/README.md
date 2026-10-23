# UI-D1-3D1 Guardian People Forms - local screenshot evidence

Captured 23 October 2026 from branch `ui/admin-desktop-d1-3d1-guardian-forms` (templates at `6e4657f`) with Playwright/Chromium against a local dev server on a throwaway Postgres database, after `collectstatic`. Local only; not staging.

## Synthetic data

All data is synthetic: one superuser `shots_admin`, applicants (pending), students progressed from accepted applicants, guardians and links with fictional names (including a 100+ character name, one unbroken 46-character surname token, and a very long email address). No real people or credentials.

## Files (50 PNGs, full-page)

Naming: `<state>-<page>-<width>.png`.

- `valid-*` at 390, 768, 992, 1024, 1280, 1440 (5 pages x 6 widths = 30):
  `guardian-create` (empty), `guardian-edit` (prefilled), `applicant-guardian` (empty, Associate Guardian with Applicant), `student-guardian-add` (empty, Associate Guardian with Student), `student-guardian-edit` (prefilled, Change relationship).
- `error-*` at 390 and 1280 (5 pages x 2 = 10): server-side validation shown by disabling browser-native validation before submit. Required/invalid email for Guardian create/edit, duplicate association for Applicant/Student links, blank relationship for Change relationship.
- `long-*` at 390 and 1280 (5 x 2 = 10): `guardian-create-error` (long name and long email retained), `guardian-edit`, `applicant-guardian-error`, `student-guardian-error` (duplicate with long names), `student-guardian-edit`.

## Checks (all 50 captures)

- Page-level horizontal overflow (`document.documentElement.scrollWidth <= innerWidth`): no failures at any width.
- Exactly one H1 and a `form.erp-form` on every capture; no blank or unstyled frame (each screenshot was viewed or spot-checked).
- Cancel link visible on every capture. Cancel tap area is 73x44 px at 390 and 73x38 px at desktop widths (checked at 390 and 1280).

## Known limits

- At 390 px the 46-character unbroken surname token in the long-name H1 is wider than the heading (heading content 453 px in a 358 px box) and its tail is clipped, with no page-level overflow. Normal multi-word long names wrap correctly. This comes from the shared page header, outside D1-3D1 scope, and was not changed.
- Browser-native HTML5 validation is bypassed for error captures so the server-rendered errors are visible.
- Keyboard focus order and touch behavior were not exercised beyond screenshots and the Cancel size check; permission denial is covered by tests, not screenshots.
