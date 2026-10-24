# UI-D1-6B — Announcements: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Grade 6 / 7, Students and Guardians from the shared test fixture, invented notices). Every state was reached through the real pages and services: notices were published through the real form -> preview -> confirm flow and the real services, and withdrawn through the real Withdraw form. Nothing is a mock-up; no real student, guardian or contact data appears; the database was deleted afterwards. It is not PostgreSQL, staging or production; the automated tests ran on PostgreSQL (see the PR).

Widths: 360, 390, 768, 1280, 1440 (full-page PNG). `Whole school` has two guardians with portal access (both opted in); Grade 6 has two; Grade 7 and Grade 6 - B have none.

| File prefix | Flow | What it shows |
| --- | --- | --- |
| `list-empty-*` | `/announcements/` | Header, "New notice", empty state "No notices yet." with "Publish a notice" |
| `list-populated-*` | same | Labelled table (Published, Title as row header, Audience, Status badge); Live and Withdrawn are text badges; long title wraps; table scrolls inside its focusable region on phones |
| `form-*`, `form-js-class-selector-*` | `/announcements/new/` | Required legend, audience radio group (fieldset + legend), Class/Section selectors; with JavaScript only the chosen selector shows |
| `form-invalid-class-missing-*` | submit "One class" with no class | Error summary "Fix 1 problem before previewing" linking to the Class field, field error, entered values kept |
| `preview-all-*`, `preview-class-*` | preview | Notice in a panel, audience, the two counts from the existing service, Publish notice / Back to edit / Cancel |
| `preview-section-nobody-note-*` | Grade 6 - B (no guardians) | Counts 0 and the "Nobody can see this notice yet" status with a badge |
| `form-after-back-to-edit-*` | Back to edit | Form refilled without an error summary |
| `detail-live-after-publish-*` | Publish notice (double-clicked) | Success message, **exactly one** notice created (`data-erp-once`) |
| `detail-class-audience-live-*` | detail | Live badge, facts, counts, "Prepare WhatsApp messages" (ASSIST mode) with consequence text, labelled Withdraw reason with consequence text |
| `detail-withdraw-blank-reason-error-*` | Withdraw with no reason | The existing "Give a reason for withdrawing this notice." message; nothing withdrawn |
| `detail-withdrawn-*`, `detail-withdrawn-after-reason-*` | withdrawn notice | Withdrawn badge, who/when/reason, no Prepare or Withdraw controls |
| `detail-long-text-*` | long title and unbroken body | Wraps inside its panel; 0px page overflow |
| `nojs-*` | JavaScript **disabled** | Form shows both Class and Section selectors; preview and publish still work end to end (reached the new notice's detail page) |
| `restricted-add-only-*` | `add_announcement` only | Form and preview without a Cancel link (no `view_announcement`); the list is 403 |
| `restricted-view-only-*`, `restricted-sender-*` | `view_announcement` (+ `send_notification`) | View-only: no New notice, no Prepare, no Withdraw. Sender: Prepare only |
| `teacher-form-403-*` | Teacher | The unchanged 403 |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 1280, 1440 in every state and for every user |
| H1 count | exactly 1 on every captured page |
| List region at 360px | 326px visible, 727px content, `tabindex="0"`: scrolls locally, not the page |
| Double-click on Publish notice | 1 notice created |
| JavaScript disabled | form -> preview -> publish completes; both selectors visible |
| Back to edit | title kept |

## Known limits

- The audience group's legend/field rendering is the existing `as_field_group` output; its look is unchanged.
- The Withdraw reason is not marked `required` in HTML, so the existing server-side message and audit path stay in charge.
- A manual screen-reader pass and PostgreSQL staging verification remain open (ledger L8). Nothing is deployed.
