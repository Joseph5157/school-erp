# UI-D1-6A — Security operations: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Student "Asha Rao", Guardian "Meena Rao", usernames `demo.parent1`, `demo.parent2` and one very long unbroken `demo_family_account_…` username). The lockouts were produced by real failed sign-ins through the login view, and both review steps were reached by submitting the real Enrollment and Deactivate forms. Nothing is a mock-up, no real student, guardian or account data appears, and the database was deleted afterwards. It is not PostgreSQL, staging or production; the automated tests ran on PostgreSQL (see the PR).

Widths: 360, 390, 768, 1280, 1440 (full-page PNG).

| File prefix | URL / flow | What it shows |
| --- | --- | --- |
| `lockouts-empty-*` | `/sign-in-lockouts/` | Header with purpose, breadcrumb, "No usernames are locked." |
| `lockouts-populated-*` | same | Labelled Username / Action table, Clear per row with consequence text, long username wraps |
| `lockouts-after-clear-*` | after Clear | The unchanged success message and redirect |
| `lockouts-restricted-clear-only-*` | `clear_login_lockout` only | No sidebar, no breadcrumb trail, Clear still works |
| `lockouts-viewschool-trail-*` | `clear_login_lockout` + `view_school` | Overview > Sign-in lockouts trail |
| `lockouts-teacher-403-*` | Teacher | The unchanged 403 |
| `review-enroll-*` | Enrollment form, ends a current placement | Review step, trigger "Placement ended" |
| `review-status-*` | Deactivate form with a reason | Review step, trigger "Student made inactive" |
| `review-*-incomplete-error-*` | submit with no decision (browser validation bypassed) | Server refuses; nothing saved; the existing message on the existing page |
| `review-*-no-cancel-*` | no `view_student` | Cancel link is not shown |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 1280, 1440 in every state and for every user |
| H1 count | exactly 1 on every captured page |
| Lockouts table region at 390px | 356px client, 356px scroll: fits without scrolling (`erp-keep`) |

## Known limits

- The browser's own `required` validation bubble is not captured; the incomplete-decision screenshots bypass it (`novalidate`) to show the server-side refusal.
- The incomplete-decision outcome lands on the **unchanged** Enrollment form (enroll flow) or the Student detail page (status flow). Those pages are outside D1-6A.
- The review step has no breadcrumb trail: it is rendered by `student-enroll` and `student-status-change`, which have no breadcrumb rule, and a rule would also change the untouched Enrollment form.
- A manual screen-reader pass and PostgreSQL staging verification remain open (deferred-work ledger L8). Nothing is deployed.
