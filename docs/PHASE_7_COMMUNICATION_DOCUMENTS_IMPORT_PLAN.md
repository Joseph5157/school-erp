# Phase 7 — Communication, Documents and Bulk Import

## Status

APPROVED (Gate 0 accepted 2026-10-15, PR #45). Decisions in section 3 are
recorded in ADRs 0015-0017. Implementation order: import (Gates 8-9) first.

Scope chosen by the owner:
- WhatsApp notifications (ASSIST mode first, API optional later): absence alerts, announcements,
  "result published" notices, fee reminders (see D8: fee reminders ship with Phase 3).
- Printable documents: Term report card PDF, Transfer Certificate, Bonafide /
  study certificate, attendance summary.
- Bulk Excel import: classes, sections, students, guardians and academic enrollment.

## Implementation notes (Gates 8-9, bulk import)

- Workbook: a "Students" sheet (one row per student, up to two guardians) and
  an optional "Classes" sheet. A student row may only name a Class/Section
  that already exists or is listed on the Classes sheet, so a typo never
  creates a class. Names match without regard to case or extra spaces.
  The template is downloadable from the Import page.
- The Academic Year and one enrollment start date are chosen on the upload
  form; the date must fall in the year and not be in the future (the
  existing `Student.enroll` rule).
- Clarification of ADR 0017 guardian matching: a guardian is reused when the
  normalised phone number and the name both match (an existing guardian or
  another row). Phone alone is not enough, because parents often share one
  phone; matching on phone alone would merge father and mother. A phone that
  belongs to a guardian with a different name produces a warning and a new
  record. Guardians without phone or email are never matched.
- Phone numbers are stored as +91XXXXXXXXXX (10-digit mobiles, with or
  without 0, 91 or +91) or +<digits> when written with a leading +.
- Dates: date cells, YYYY-MM-DD or day-first DD/MM/YYYY.
- Warnings (possible duplicates, shared phone, guardian without contact)
  never block, but confirming requires ticking "I have reviewed the warnings".
- A checked batch keeps its parsed rows only until it is committed,
  discarded, fails, or expires after 24 hours; then the rows are cleared and
  only the counts and row messages remain. Messages never contain personal
  data.
- Commit re-validates against current records, then runs Applicant ->
  accepted decision -> `progress_to_student()` -> admission number ->
  `enroll()` -> roll number for each row in one transaction. Any failure
  rolls back everything and marks the batch FAILED. A successful commit
  records an `IMPORT_COMMITTED` security event (history class).
- Permissions: `core.run_import` and `core.view_importbatch`, granted to the
  School Administrators group. New dependency: openpyxl.

---

# 1. Goals

1. Tell guardians what matters (absence, new report card, school notices) on
   the channel they actually read, without exposing more data than needed.
2. Let the school issue official-looking documents that always match the
   recorded data and can be traced afterwards.
3. Let a school with existing Excel records start without retyping every student.

# 2. Out of scope

- Two-way chat, parent replies, chatbots, marketing campaigns.
- SMS and email delivery (the provider adapter is built so they can be added).
- Fee code of any kind (Phase 3 stays deferred; no placeholders).
- Digital signatures and e-sign; QR verification pages (optional later).
- Importing historical attendance or marks (separate decision; hard to do correctly).
- Student accounts (Phase 6B).
- Government formats and APAAR/UDISE+ fields (the next planning round).

# 3. Decisions required (Gate 0)

| ID | Decision | Proposal |
|----|----------|----------|
| D1 | Channel | Per-school setting with four modes: ASSIST (first version), API, SMS, PORTAL_ONLY. ASSIST: the ERP prepares each message and staff send it from the school's own WhatsApp via a click-to-chat link with the text pre-filled. API: WhatsApp Business API through a Business Solution Provider (BSP), hidden behind an adapter (built after ASSIST). The ERP never automates a normal WhatsApp account (ban risk, breaks WhatsApp rules). |
| D1b | Coexistence | Vendor sources say WhatsApp lets the Business app and the API share one number. Not confirmed for India; verify with a BSP before relying on it. |
| D2 | Message cost model | Meta bills per message since 1 Jul 2025; utility templates ~₹0.115 excl. 18% GST (one vendor blog, Jan 2026 rate; verify on the school's own rate card) plus the BSP's fee. Create the account with INR billing. |
| D3 | Consent | Explicit, recorded opt-in per guardian per channel (who, when, how). No consent = no message. Opt-out honored immediately. Required in spirit now, in law from 13 May 2027 (DPDP). |
| D4 | Message content | Minimum data: student first name, date, and a portal link. Never marks, never grades, never reasons for absence. |
| D5 | Sending model | Database outbox plus a management-command worker run by cron. No network call inside a web request or inside a transaction. Idempotent per (guardian, student, type, date). |
| D6 | PDF engine | HTML-to-PDF (WeasyPrint candidate) with an embedded Telugu-capable font. A spike in Gate 5 must prove Telugu and English render correctly before committing. |
| D7 | Reverses an earlier decision | Phase 6 excluded PDFs. Report-card PDFs for guardians reverse that and need their own ADR. |
| D8 | Fee reminders | The notification type system is generic, but the fee reminder itself is built with Phase 3. |
| D9 | Import creation path | Student requires an Applicant (OneToOne, ADR 0002). Import must go through Applicant, admission decision and `progress_to_student()`, not bypass them. Needs an ADR for a "migrated applicant" marker. |
| D10 | Import safety | Upload, validate (dry run), preview with row errors, explicit confirm, then one atomic commit. Whole batch succeeds or none of it does. |

# 4. Proposed model (additions)

- `GuardianContactConsent`: guardian, channel, status (OPTED_IN / OPTED_OUT),
  recorded_by, recorded_at, source. Append-only history; current state derived.
- `NotificationTemplate`: key, channel, provider_template_name, language, version,
  approved flag. Approved template bodies are immutable; edits create a new version.
- `Notification`: guardian, student, type, template, parameters (minimal),
  channel mode, status (QUEUED / PREPARED / SENT / DELIVERED / FAILED /
  SKIPPED_NO_CONSENT), provider message id (API mode), marked_sent_by and
  marked_sent_at (ASSIST mode), attempts, error code, timestamps, idempotency
  key (unique). PREPARED means the message is ready and awaiting a staff member.
- `Announcement`: title, body, audience (ALL / CLASS GRADE / SECTION),
  published_by, published_at, withdrawn flag. Shown in the portal; optionally sent.
- `IssuedDocument`: type (REPORT_CARD / TC / BONAFIDE / ATTENDANCE_SUMMARY), student,
  serial number (per type, per academic year, gap-free where required), issued_by,
  issued_at, immutable data snapshot, content hash, duplicate-of reference.
- `ImportBatch` / `ImportRowResult`: uploader, file name, file hash, mode
  (DRY_RUN / COMMITTED), per-row outcome and message. Retained for audit.

All new history tables follow the project rule: database triggers refuse UPDATE
and DELETE except for defined status fields.

# 5. Design notes

## 5.1 Notifications

- Absence alert: raised when a class teacher or administrator submits a
  register, only for ABSENT entries, only to guardians with consent. Later
  corrections do not send automatic retractions; they are logged.
- Result published: raised when a TermPublication becomes PUBLISHED. The message
  says a report card is available and links to the portal. No results in the message.
- Announcements: published in the portal first; WhatsApp sending is an explicit
  second step by an administrator, with an audience count preview.
- Templates must be approved by the provider before use. Utility-style wording
  (transactional, no promotion) is the safest route; announcements may be
  classified as marketing by the provider, which costs more (about ₹0.86 excl. GST
  per one blog) and needs stricter consent. This must be confirmed with the BSP.
- Failure handling: retry with backoff, then FAILED; an administrator view shows
  failures. No silent drops.
- Provider adapter has a console/fake backend for development and tests.
- ASSIST mode: a "To send" page lists prepared messages (for example today's
  absentees). Each row has a Send button that opens WhatsApp with the parent's
  number and text pre-filled, then the staff member confirms it was sent. Parent
  phone numbers are stored with country code (+91) so the link works. Staff see
  only guardians who have opted in. Unsent items stay visible until done or
  dismissed, and the page shows a daily count.
- The consent, minimal-content and audit rules are identical in every mode.

## 5.2 Documents

- Report card PDF is rendered from the immutable TermPublication snapshot, so the
  PDF always equals what the guardian saw. STALE or WITHDRAWN publications produce
  no PDF.
- Bonafide: current academic enrollment, purpose line, serial number, date.
- Attendance summary: submitted, eligible entries only (existing Phase 2 rule).
- Transfer Certificate: needs fields the system does not hold yet (leaving date,
  reason, last class, conduct, promotion status). Layout and mandatory fields
  differ by board and state, so the school's current TC format must be collected
  before design. Re-issues are marked DUPLICATE and linked to the original.
  Dues-cleared check waits for Fees.
- Every issued document gets a serial number and a security event.

## 5.3 Import

- Template workbook per entity, downloadable, with a notes sheet.
- Dependency order: Academic year and classes, sections, guardians, applicants and
  students, guardian links, academic enrollment.
- Duplicate handling: match guardians by phone to share one record across
  siblings; flag same name plus date of birth for human review; never auto-merge.
- Upload limits: file size, row count and sheet count caps; read-only parsing;
  ignore formulas and macros; reject .xlsm.
- Errors are reported by row and column, downloadable as a file.
- Exports that include user data must neutralize cells starting with =, +, -, @.

# 6. Authorization

New permissions: manage consent, send notifications, publish announcements, issue
documents, issue TC, run import. Guardians can download only the PDF of their own
child's current published report card. Teachers get no import or TC rights.

# 7. Gates

- Gate 0: ADRs 0015-0017, requirements, this plan approved.
- Gate 1: consent records, notification outbox, per-school channel setting, ASSIST "To send" page.
- Gate 2: absence alerts (ASSIST mode).
- Gate 3: announcements (portal first, then ASSIST send).
- Gate 4: result-published notice.
- Gate 4B (optional, later): API mode with a BSP, worker command, real sandbox test.
- Gate 5: document foundation, PDF spike (Telugu and English), bonafide.
- Gate 6: report card PDF and guardian download.
- Gate 7: attendance summary and Transfer Certificate.
- Gate 8: import parsing, validation and preview.
- Gate 9: import commit, batch audit, rollback rules.
- Gate 10: hardening, DPDP review, documentation, `phase-7-complete` release.

Import (Gates 8-9) has no dependency on Gates 1-7 and can run in parallel.

# 8. Risks

- Provider template rejection or reclassification changes cost and wording.
- Telugu text shaping in PDFs may need a different engine or system packages
  (Pango) on the server.
- TC legal format unknown until the school provides it.
- Guardian phone numbers in existing data may be wrong or shared, so consent
  collection needs a real-world process (paper form or portal tick-box).
- Import of messy real data will surface duplicates and invalid dates.
- Student creation via Applicant makes import more complex than a simple load.

# 9. Stop-and-return-to-planning conditions

- Any need to send marks or reasons for absence in a message.
- Any need to bypass Applicant to Student progression.
- PDF output that cannot be traced to a published snapshot.
- Sending without recorded consent.
