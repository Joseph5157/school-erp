# UI-D1-3D1 Guardian People Forms - local screenshot evidence

Captured 23 October 2026 from branch `ui/admin-desktop-d1-3d1-guardian-forms` (templates at `6e4657f`, scoped H1 wrap fix at `d450a66`; re-captured after that fix) with Playwright/Chromium against a local dev server on a throwaway Postgres database, after `collectstatic`. Local only; not staging.

## Synthetic data

All data is synthetic: one superuser `shots_admin`, applicants (pending), students progressed from accepted applicants, guardians and links with fictional names (including a 100+ character name, one unbroken 46-character surname token, and a very long email address). No real people or credentials.

## Files (55 PNGs, full-page)

Naming: `<state>-<page>-<width>.png`.

- `valid-*` at 390, 768, 992, 1024, 1280, 1440 (5 pages x 6 widths = 30):
  `guardian-create` (empty), `guardian-edit` (prefilled), `applicant-guardian` (empty, Associate Guardian with Applicant), `student-guardian-add` (empty, Associate Guardian with Student), `student-guardian-edit` (prefilled, Change relationship).
- `error-*` at 390 and 1280 (5 pages x 2 = 10): server-side validation shown by disabling browser-native validation before submit. Required/invalid email for Guardian create/edit, duplicate association for Applicant/Student links, blank relationship for Change relationship.
- `long-*` at 390 and 1280 (7 x 2 = 14): `guardian-create-error` (long name and long email retained), `guardian-edit`, `applicant-guardian`, `applicant-guardian-error`, `student-guardian-add`, `student-guardian-error` (duplicate with long names), `student-guardian-edit`. The long variants use a 46-character unbroken surname token inside the page title (and a long email where relevant).
- `focus-guardian-create-cancel-1280.png`: Cancel focused by keyboard (visible focus ring).

## Checks (re-run on the fixed build, 74 page loads)

Playwright/Chromium, throwaway Postgres DB, fresh `collectstatic` and a fresh dev server. Each of the five modes was loaded at 390, 768, 992, 1024, 1280 and 1440 px, with normal data and (for the four modes that put names in the title) long unbroken-token data; error states at 390 and 1280.

| Mode | Loads | Max page overflow (scrollWidth - clientWidth) | H1 scrollWidth <= clientWidth | Cancel visible | Long-name H1 at 390 |
| --- | --- | --- | --- | --- | --- |
| Guardian create | 14 | 0 px | yes | yes | n/a (static title; long name and email sit in the inputs) |
| Guardian edit | 14 | 0 px | yes | yes | 358 / 358 |
| Applicant-guardian | 16 | 0 px | yes | yes | 358 / 358 |
| Student-guardian add | 16 | 0 px | yes | yes | 358 / 358 |
| Student-guardian change relationship | 14 | 0 px | yes | yes | 358 / 358 |

- Exactly one H1 and a `form.erp-form` on every load. The 390 long-name screenshots were viewed: the unbroken token wraps over several lines inside the heading, nothing is clipped, and the form below is intact.
- Cancel tap area is 73x44 px at 390 and 73x38 px at desktop widths.

## Keyboard Tab order

Playwright, `Tab` from the top of each page with normal data, at 1280 and 390 px. The identical sequence appeared at both widths, except that 390 adds a Menu button before the brand link.

| Mode | Stops inside main content, in order | Shift+Tab from Cancel |
| --- | --- | --- |
| Guardian create | Full name, Phone, Email, Save guardian, Cancel | Save guardian |
| Guardian edit | Full name, Phone, Email, Save guardian, Cancel | Save guardian |
| Applicant-guardian | Guardian, Relationship type, Save guardian link, Cancel | Save guardian link |
| Student-guardian add | Guardian, Relationship type, Save guardian link, Cancel | Save guardian link |
| Student-guardian change relationship | Relationship type, Save relationship, Cancel | Save relationship |

- Field order matches the form's field order, then the submit button, then Cancel. After Cancel focus leaves the document (wraps to the browser); there is no focus trap.
- Before main content: Skip to content, brand link, the account menu and, at 1280, 19 sidebar links (Menu button first at 390, where there is no sidebar). These are shared and unchanged.
- Focus ring: inputs and selects get a 3 px solid green outline (rgb(11, 110, 79)); the Save button and Cancel link get a 3.2 px green box-shadow ring (rgba(11, 110, 79, .3)) and a green border, read after the 150 ms transition. Cancel focus state is captured in `focus-guardian-create-cancel-1280.png`.
- Observation, outside D1-3D1 scope and not changed: the shared sidebar links show only a Bootstrap-blue box-shadow (rgba(13, 110, 253, .25)) and no green outline when focused.

## Known limits

- The desktop Cancel control is 38 px tall, below the 44 px target. This comes from shared button CSS, outside D1-3D1 scope, and was not changed. On phone it is 44 px.
- Error-state and long-name screenshots exist only at 390 and 1280 px, not at all six widths. Valid-state screenshots cover all six widths.
- Browser-native HTML5 validation is bypassed (`noValidate`) for error captures so the server-rendered errors are visible.
- Keyboard order was checked with normal data at 1280 and 390 only; touch behavior was not exercised beyond screenshots and the Cancel size check. Permission denial is covered by tests, not screenshots.
- Local evidence only; not staging and not CI.
