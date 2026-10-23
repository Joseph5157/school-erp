# UI-D1-3D2 Guardian portal account create/link form - local screenshot evidence

Captured 23 October 2026 from branch `ui/admin-desktop-d1-3d2-guardian-account-form` (template and tests at `83f01f5`) with Playwright/Chromium against a local dev server (port 8014) on a throwaway Postgres database, after `collectstatic`. Local only; not staging, not CI.

## Security statement

**No valid Create or Link form was submitted and no credential slip or password was captured, saved or printed.** Only pre-submit (GET) pages and INVALID submissions were captured. Every invalid submit used a blank required field, the username `a b` (create) or `nobody.synthetic.absent` (link); the capture script asserted the username before each submit and that the form re-rendered with validation errors afterwards. Browser-native validation was disabled (`noValidate`) so the server-rendered errors are visible.

## Synthetic data

Throwaway database, one synthetic staff user in the School Administrators group (`shots_admin`), two guardians (`Asha Synthetic`; and one with a long hyphenated name ending in an unbroken 46-character token) and one synthetic existing login. No real people, usernames or credentials.

## Files (32 PNGs, full-page)

Naming: `<state>-<mode>-<width>.png`, mode is `create` or `link`.

- `create-*` and `link-*` pre-submit at 390, 768, 992, 1024, 1280, 1440 (12).
- `long-create-*` and `long-link-*` pre-submit with the long guardian name at 390 and 1280 (4).
- `error-blank-*` all three required fields blank, at 390 and 1280 (4).
- `error-invalid-username-create-*` (username `a b`) and `error-nonexistent-username-link-*` (username with no login), at 390 and 1280 (4).
- `long-error-*` long guardian name with blank required fields, at 390 and 1280 (4).
- `note200-error-*` a 200-character note typed, then an invalid submit (invalid username), at 390 and 1280 (4).

Images viewed: warning alert is visible above the form in both modes, the mode-specific instruction is correct, one H1, form intact with no blank or unstyled frame. The warning is a plain yellow alert with no close button.

## Overflow and visibility (Playwright, every capture state)

Pre-submit pages at six widths, both modes; the long-name and invalid states at 390 and 1280 were measured the same way.

| Mode | Widths | Page overflow (scrollWidth vs innerWidth) | H1 scrollWidth <= clientWidth | Cancel visible | Cancel size |
| --- | --- | --- | --- | --- | --- |
| Create | 1440, 1280, 1024, 992, 768, 390 | none (equal at every width) | yes | yes | 73x38 px desktop and 768, 73x44 px at 390 |
| Link | 1440, 1280, 1024, 992, 768, 390 | none | yes | yes | same |

All 32 measured states: one H1, one `form.erp-form`, no page-level horizontal overflow, H1 not clipped (long-name H1 at 390 is 358/358, at 1280 736/736).

Live DOM of the warning alert (all 12 pre-submit loads): exactly one `.alert`, no `role` attribute, no `aria-live`, no `tabindex`, no close button or `data-bs-dismiss`, not `alert-dismissible`, contains nothing focusable.

## Keyboard Tab order

Playwright, `Tab` from the top of the page, at 1280 and 390 (identical results for both modes).

| Mode | Width | Stops inside main content, in order | Stops before main (shared chrome) | Shift+Tab from Cancel |
| --- | --- | --- | --- | --- |
| Create | 1280 | Username, method select, Verification note, Create account, Cancel | 22 | Create account |
| Create | 390 | same | 4 | Create account |
| Link | 1280 | Existing login username, method select, Verification note, Link login, Cancel | 22 | Link login |
| Link | 390 | same | 4 | Link login |

- The warning alert and instruction text are never focusable. After Cancel, focus leaves the page content (wraps to the browser); no trap.
- Focus ring: inputs and the select get a 3 px solid outline rgb(11, 110, 79). Submit and Cancel get a 3.2 px box-shadow ring rgba(11, 110, 79, .3).
- Touch targets at 390: submit 358x44, Cancel 73x44.

## Known limits and observations

- Fixed in Task 3 (scoped rule `.erp-guardian-form-page .erp-page-purpose { overflow-wrap: break-word; min-width: 0; }` at the end of `static/css/erp.css`): a guardian name with an unbroken ~46-character token used to overflow the "Guardian: ..." purpose line at 390 (`.erp-page-purpose` scrollWidth 382 vs clientWidth 358) and was clipped at the viewport edge. After the fix the token wraps onto its own lines: purpose scrollWidth equals clientWidth at 390 (358/358) and at 360 (328/328), the H1 fits (358/358 and 328/328), and there is no page-level overflow, in Create and Link, on GET and on a blank invalid submit. Normal-name pages and the 1280 captures are unchanged. The four `long-*-390.png` captures (`long-create`, `long-link`, `long-error-create`, `long-error-link`) were retaken; the 1280 long-name captures are byte-identical and were not replaced. The 360px check was measured only (no screenshot).
- Error and long-name captures exist only at 390 and 1280, not all six widths.
- The note field is a single-line input with `maxlength=200`; 200 characters are visually clipped inside the box (see `note200-error-*`).
- The shared sidebar links show only a Bootstrap-blue box-shadow on focus (shared, unchanged).
- The desktop Cancel link is 38 px tall (shared button CSS, outside scope); 44 px on phone.
- Browser autofill behavior on the username field is unchanged and not re-tested; recorded as a risk.
- A user who has `core.add_guardianaccount` without `core.view_guardian` gets a 403 on the guardian detail Cancel target; deferred, unchanged.
- Local evidence only; no CI claim.
