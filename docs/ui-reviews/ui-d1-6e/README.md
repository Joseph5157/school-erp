# UI-D1-6E — Bulk imports: synthetic screenshot, measurement and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (synthetic Students such as "Clean Student" and "Student 000 Longname…", Guardians "Existing 000" to "Existing 199", a synthetic workbook). Batches were created through the real import service and committed, discarded, expired or failed through the real service calls, so every state is genuine data. No real student or guardian data appears and the database was deleted afterwards. It is not PostgreSQL, staging or production; the automated tests ran on PostgreSQL (see the PR). Nothing was committed from the browser.

Widths: 360, 390, 768, 992, 1024, 1280, 1440 (full-page PNG). Restricted-user states are captured at 390 and 1440. After review, the list and upload screenshots were refreshed at 390 and 1440 only for the corrected explanatory text.

| File prefix | Batch / state | What it shows |
| --- | --- | --- |
| `list-empty-*` | no batches | Header with Download template / New import (purpose text: checking a file keeps a batch for review and no school records are imported until confirmation), legacy "No imports yet." and "Start an import" |
| `list-populated-*` | all statuses | Labelled table with a text badge per status (Validated, Rejected, Imported, Discarded, Expired, Failed), `#` as row header |
| `upload-form-*`, `upload-invalid-file-*` | `/imports/new/` | Shared form chrome, required legend, accurate explanation (checking creates a batch for review; no Student, Guardian, Class or Section records are imported until confirmation; a rejected file keeps its batch and imports nothing), "what happens next" note; a `.csv` upload shows the error summary linked to the file field |
| `detail-validated-clean-*` | pending, no warnings | Status badge in the header, facts panel, preview counts strip and Students region, Confirm and Discard with consequence text, the 24-hour note |
| `detail-validated-with-warnings-*` | pending with a warning | Warnings table (severity badge, caption, scopes), CSV link, the required "I have reviewed the warnings." checkbox |
| `detail-live-errors-confirm-hidden-*` | records changed after the check | The exact "School records changed since this file was checked" notice; **no Confirm**, Discard only |
| `detail-rejected-*` | has errors | "Nothing was imported" notice, Errors table, no actions |
| `detail-committed-*`, `detail-discarded-*`, `detail-expired-*`, `detail-failed-*` | final states | Status badge, facts (including the failure reason), no actions |
| `big-200-pending-preview-and-warnings-*` | **200 Students, 200 warnings, long names** | Every row in two labelled local-scroll regions; the page stays short |
| `big-200-rejected-long-errors-*` | **200 errors with long messages and a long file name** | Every error row in one region; long messages wrap, the table scrolls locally |
| `restricted-view-only-*` | `view_importbatch` only | List without actions; detail with warnings but **no Confirm, Discard or checkbox** |
| `restricted-run-only-*` | `run_import` only | Upload without a Cancel link; the list is 403 |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 992, 1024, 1280, 1440 in every captured state |
| H1 count | exactly 1 on every captured page |
| 200-row pages (page height) | pending 2,401px at 390 and 2,123px at 1440; rejected 1,514px and 1,268px: the page does not grow with the rows |
| Rows rendered | 200 of 200 in the Students, Warnings and Errors regions; no pagination |
| Keyboard (390px) | each region takes focus; PageDown scrolled it 1,176px and ArrowRight 40px sideways (Students 356px visible of 1,424px; Warnings 1,228px; Errors 3,624px) |
| Keyboard (1440px) | PageDown scrolled each region 1,176px vertically |
| Review checkbox | `name="reviewed_warnings"`, `value="yes"`, `required`; the form is invalid until it is checked |
| Query count | identical for 20-row and 200-row batches (asserted by the automated tests) |

## Known limits

- The browser's own `required` validation bubble is not captured; the invalid state is measured (`checkValidity()` is false).
- Pre-existing and unchanged (ledger L11, mandatory workflow review before production): a user holding `run_import` without `view_importbatch` is redirected to a 403 after upload, commit or discard.
- Discard is still the existing unconfirmed POST, with consequence text only (ledger L3).
- Import detail pagination, search and sorting remain out of scope (ledger L6).
- A manual screen-reader pass and PostgreSQL staging verification remain open (ledger L8). Nothing is deployed.
