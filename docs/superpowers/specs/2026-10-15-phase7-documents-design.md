# Phase 7 Piece C — Documents (Gates 5, 6 and the attendance summary) — Design

**Date:** 2026-10-15
**Authority:** `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (§5.2, §6, §7 Gates 5, 6, 7, D6, risks). The branch is cut after PR #51 and #52 are merged, or stacked on them.

## Goal

The office can issue a bonafide certificate, print a report card PDF and produce an attendance summary. Guardians can download the PDF of their own child's current published report card. Telugu and English both render correctly.

## Decisions (owner, 2026-10-15)

| Topic | Decision |
|---|---|
| Letterhead | School settings gain address, affiliation number, principal's name and an optional logo; documents use them and omit what is blank. |
| Bonafide purpose | Short list (bank account, passport, scholarship) plus Other with typed text. |
| Report card PDF | Guardians (own child, current published card) and office staff with the issue-documents permission. |

## Decisions made in this spec (review these)

1. **Engine.** WeasyPrint renders HTML templates to PDF. A Telugu font (Noto Sans Telugu, OFL licence) is bundled in the repo and referenced by `@font-face`, so output does not depend on server fonts. A spike proves Telugu conjuncts shape correctly before any document is built. If the engine cannot render on the target platform, work stops and returns to planning; no silent engine swap.
2. **`IssuedDocument` model.** Fields: `public_id`, `document_type` (BONAFIDE, REPORT_CARD, ATTENDANCE_SUMMARY), `serial` (unique), `student` (FK, null for summaries), `academic_year`, `payload` (JSON snapshot of exactly what is printed), `issued_by` (null for a guardian's first download of a report card), `issued_at`. Immutable: database triggers on PostgreSQL and SQLite refuse DELETE and any UPDATE, as for announcements.
3. **Serial numbers.** `<PREFIX>/<academic-year>/<0001>`, with prefixes `BON`, `RC`, `ATT`, numbered per type and academic year. Allocated under a row lock on a counter row so concurrent issues never collide.
4. **Reprint = same snapshot.** Reprinting renders from `payload`, never from live data, so a reprint equals the original. Each reprint and each download writes a security event; only the first issue consumes a serial.
5. **Report card PDF.** Rendered from the immutable `TermPublication` snapshot. STALE or WITHDRAWN publications produce no PDF (404 for guardians, a plain message for office). The first PDF for a publication creates its `IssuedDocument`; later downloads reuse the same serial.
6. **Authorization.** New permission `core.issue_document`, granted to School Administrators by migration. Guardians use the portal's existing visibility rule (own visible child, current published, not withdrawn); no permission needed. Teachers get nothing.
7. **Bonafide eligibility.** The student must have an academic enrollment effective today and within its academic year (the Gate 3 rule). Otherwise no certificate, and the page says why.
8. **Attendance summary.** Per section and date range; counts only submitted, eligible entries (the Phase 2 rule). Shown on screen and downloadable as PDF. The PDF records an `IssuedDocument` of type ATTENDANCE_SUMMARY.
9. **Security event** on every issue and download, using the existing audit mechanism.

## Model and settings

- `School`: add `address` (text), `affiliation_number` (char 50), `principal_name` (char 120), `logo` (image, optional); all blank-able. School form updated.
- `IssuedDocument` plus a small per-type-per-year counter model (`DocumentSerialCounter`), with migrations: models, history-guard triggers, permission to group.

## Components

- `core/documents/` (new package): `engine.py` (`render_pdf(template, context) -> bytes`, font setup), `serials.py` (`next_serial(type, academic_year)`), `bonafide.py`, `report_card.py`, `attendance_summary.py` (each builds a payload and exposes `issue(...)`).
- Templates under `templates/documents/` (shared letterhead partial; one template per document).
- Office views: issue bonafide, print report card, attendance summary page, issued-documents list. Portal view: report card PDF download.
- `core/navigation.py`: office link "Documents" (`core.issue_document`).
- Docs: Phase 7 plan implementation notes; deploy note listing system packages for WeasyPrint.

## Testing

- Engine: output starts with `%PDF`, and the extracted text contains the Telugu and English test strings (the spike is kept as a regression test).
- Serials: format, per-type-per-year numbering, uniqueness under concurrent issue.
- Bonafide: eligible student issues; no current enrollment refused; purpose list and Other validation; blank letterhead fields omitted.
- Report card: STALE and WITHDRAWN give nothing; another guardian's child gives 404; reprint equals the stored snapshot; serial reused.
- Attendance summary: only submitted, eligible entries counted.
- History guards refuse edit and delete; non-administrators get 403; every issue and download writes a security event.

## Out of scope

Transfer Certificate (blocked on the school's format), dues-cleared checks (Fees), digital signatures, QR verification, bulk issue, email delivery of PDFs, translated documents.
