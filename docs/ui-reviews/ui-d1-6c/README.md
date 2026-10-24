# UI-D1-6C — Documents: synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Students "Asha Rao", "Bina Other", "Ravi Rao", Grade 6 Sections, a Term 1 publication). Documents were issued and report cards published through the real services, so every state is genuine data, not a mock-up. No real student, guardian or contact data appears, and the database was deleted afterwards. It is not PostgreSQL, staging or production; the automated tests ran on PostgreSQL (see the PR).

**No PDF is opened, rendered or embedded.** The screenshots stop at the page that links to a PDF; issuing was never submitted from the browser. PDF behaviour (status, `Content-Type`, `Content-Disposition`, authorization, exactly-once issuance and the audit event) is proved by automated tests instead.

Widths: 360, 390, 768, 1280, 1440 (full-page PNG).

| File prefix | URL | What it shows |
| --- | --- | --- |
| `index-empty-*` | `/documents/` | Header, the three document types with a description under each link, "Nothing issued yet." |
| `index-populated-*` | same | "Recently issued" labelled table: serial as row header, type, Student, issued; **descriptive PDF links** ("PDF for BON/2026-27/0001"); scrolls inside its focusable region on phones |
| `bonafide-form-*`, `bonafide-invalid-no-student-*` | `/documents/bonafide/` | Shared form chrome, required legend, serial-number consequence text; invalid submit shows the error summary linked to the Student field (browser validation bypassed) |
| `summary-unbound-*` | `/documents/attendance/` | Section / Start / End toolbar only; no issue control |
| `summary-populated-*` | `?section=..&start=..&end=..` | Summary table (counts right-aligned, Section total row) and the separate "Issue the PDF" step with consequence text and the unchanged POST form |
| `summary-empty-range-*`, `summary-invalid-range-*`, `summary-missing-dates-*` | variations | Legacy empty text; the service's refusal in the error summary with no issue control; "Fix 2 problems" summary for missing dates |
| `cards-unbound-*` | `/documents/report-cards/` | Student picker and the prompt |
| `cards-populated-*`, `cards-populated-after-issue-*` | `?student=<Asha>` | Current published report card with a descriptive PDF link |
| `cards-empty-*` | a Student with no publication | "No published report cards for this student." |
| `cards-stale-excluded-*` | `?student=<Bina>` after her released result was corrected | The stale card is **not listed** |
| `restricted-issuer-only-*` | `issue_document` only | No sidebar; trail starts at Documents; pages still work |
| `restricted-no-issue-permission-403-*`, `teacher-403-*` | `view_school` only / Teacher | The unchanged 403 |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 1280, 1440 in every state and for every user |
| H1 count | exactly 1 on every captured page |
| Index table region at 360px | 326px visible, 522px content, `tabindex="0"`: scrolls locally, not the page |
| PDF link names | "PDF for RC/2026-27/0001", "PDF for ATT/2026-27/0001", "PDF for BON/2026-27/0002", "PDF for BON/2026-27/0001" |

## Known limits

- The browser's own `required` validation bubble is not captured; the invalid Bonafide screenshot bypasses it to show the server-side summary.
- Opening a report card PDF still creates (or reuses) its audited issued document on first view; that is existing behaviour and unchanged. Rendering the list issues nothing (tested).
- A manual screen-reader pass and PostgreSQL staging verification remain open (ledger L8). Nothing is deployed.
