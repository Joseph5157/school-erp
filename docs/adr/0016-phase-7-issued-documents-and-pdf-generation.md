# 0016. Phase 7 issued documents and PDF generation

## Status

Proposed (Phase 7 Gate 0) — awaiting owner approval. Becomes FROZEN once accepted.
Planning: `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (decisions D6, D7).

## Context

Schools issue printed documents: term report cards, transfer certificates,
bonafide (study) certificates and attendance summaries. Phase 6 excluded PDF
and downloadable report cards (ADR 0014); that exclusion is deliberately
reversed here, but only for output that can be traced to an immutable source.

## Decision

- Every issued document is an `IssuedDocument` record: type, student, serial
  number (per type and Academic Year), issuer, time, an immutable data
  snapshot and a content hash. Records are append-only (database triggers
  refuse UPDATE and DELETE except defined status fields).
- Report card PDF is rendered only from the current PUBLISHED TermPublication
  snapshot (ADR 0014). STALE, SUPERSEDED or WITHDRAWN versions produce no PDF.
  The PDF therefore always equals what the guardian saw.
- Bonafide uses the current academic enrollment. Attendance summary uses
  submitted, eligible entries only (Phase 2 rules).
- Transfer Certificate requires fields not yet held (leaving date, reason,
  last class, conduct, promotion status). Its layout depends on the board and
  state; the school's current TC format must be collected before design.
  A re-issue is a new serial marked DUPLICATE and linked to the original.
  A dues-cleared check waits for Phase 3.
- Guardians may download only the PDF of their own child's current published
  report card. Other documents are staff-issued.
- PDF engine: HTML-to-PDF with an embedded Telugu-capable font. A spike in
  Gate 5 must show correct Telugu and English output before an engine is
  chosen. If the candidate fails, return to planning.
- Every issuance records a security event.

## Consequences

- Printable documents without weakening the "nothing released changes
  silently" principle.
- Server may need extra system packages for text shaping.
- TC work is blocked on the school's format and board requirements.

## Related

ADR 0014 (reversed in part: PDF exclusion), ADR 0013; Phase 2 and Phase 4
requirements.
