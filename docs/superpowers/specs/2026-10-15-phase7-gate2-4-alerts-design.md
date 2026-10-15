# Phase 7 Gates 2 and 4 — Absence Alerts and Report-Card Notices — Design

**Date:** 2026-10-15
**Authority:** `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (§5.1, §7 Gates 2 and 4) and `docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md` (with its Gate 1 amendment). Builds on Gate 1 (`core/notifications.py`, PR #49). This spec only fills in what those leave open.

## Goal

Create the first real messages in the Gate 1 outbox: an absence alert when a register is submitted, and a "report card available" notice when a Term result is published. Office staff send them from the existing To send page (ASSIST mode). Nothing changes for staff except that messages now appear.

## Decisions (owner, 2026-10-15)

| Topic | Decision |
|---|---|
| Recipients | Only guardians with **portal access** to that student: an active `GuardianStudentAccess` grant (not revoked) whose access review is not pending, held by a guardian with an active portal login (account not revoked, user active) — exactly who can open the link. Consent rules from Gate 1 apply on top (no current WhatsApp opt-in → `SKIPPED_NO_CONSENT`). A guardian on record without portal access gets nothing — no row at all. |
| Correction Absent → Present | A waiting (PREPARED) absence alert for that student and date is dismissed automatically, reason "Attendance corrected to Present", `dismissed_by` = the correcting user. SENT alerts are never retracted (ADR 0015). |

## Decisions made in this spec (review these)

1. **Same-day only.** Absence alerts are prepared only when the register date equals `business_today()` at submission or correction time. A register submitted late for an earlier date prepares nothing.
2. **Correction Present → Absent** on the register's own date prepares an alert (same key, so it cannot duplicate one already sent or dismissed — see 4).
3. **Hook points.** Absence: inside `AttendanceRegister.submit()` and `AttendanceEntry.record_status_change()`, in the same transaction, so every submit path is covered. Report card: inside `confirm_publication()`, for each publication it creates.
4. **Idempotency subjects** (key = `type:guardian:student:subject`, Gate 1): absence → the register date (ISO); report card → `term-<term pk>`. So republishing, or withdrawing and republishing, never sends a second notice for the same Term; an absence that was corrected away and back the same day does not re-prepare a dismissed alert.
5. **Never blocks the main action.** Each enqueue runs in its own savepoint; a `NotificationError` (missing approved text, missing portal address) is logged at WARNING with the type and ids only (no personal data) and the register submission or publication still succeeds.
6. **Message texts, version 1, English**, seeded by a data migration that runs `full_clean()` on each and marks them approved:
   - `absence-alert`: `Dear parent, {first_name} was marked absent at school on {date}. Attendance details: {portal_url}`
   - `report-card-published`: `Dear parent, {first_name}'s report card is now available on the school portal: {portal_url}`
7. **Parameters.** `first_name` = first word of `Student.full_name` (stripped). `date` = register date formatted like `15 Oct 2026` (absence only; the report-card text has no date, so the parameter is omitted). `portal_url` = `PORTAL_BASE_URL` + the child's portal page: attendance page for absence, report cards page for the notice (`portal:attendance` / `portal:report-cards`, by the recipient's own `GuardianStudentAccess.public_id`, as the portal's URLs already work).
8. **Portal address.** New setting `PORTAL_BASE_URL` from the environment variable of the same name (trailing slash stripped; empty by default).
   - The school settings form refuses ASSIST when it is empty: "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."
   - If it is empty while the school is in ASSIST, producers prepare nothing (logged, per 5) and the To send page shows a warning line.
9. **PORTAL_ONLY** prepares nothing (Gate 1 behaviour, unchanged). Switching to ASSIST does not back-fill.

## Components

- `core/notification_producers.py` (new): `absence_alerts_for_register(register)`, `absence_corrected(entry, *, actor)`, `report_card_notices(publications)`, plus `portal_grants(student)` (active, non-pending grants whose guardian has an active login) and `portal_url(url_name, grant)`. All rules for Gates 2 and 4 live here; `core/notifications.py` keeps the outbox mechanics.
- `core/notifications.py`: the automatic dismissal reuses `dismiss()` (only from PREPARED).
- `core/models.py`: two call sites (local import to avoid a cycle). `core/publication.py`: one call site.
- `config/settings.py`: `PORTAL_BASE_URL`. `core/forms.py`: school form check. `core/templates/core/notifications_to_send.html`: warning line.
- Migration: seed the two templates.
- `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`: implementation notes for Gates 2 and 4. ADR 0015 needs no amendment (recipients and the same-day rule refine it).

## Testing (new `core/tests/test_phase7_alerts.py`)

- Submit with one absent student: one PREPARED alert per opted-in portal-access guardian; SKIPPED for portal-access guardians without consent; nothing for linked guardians without access, with revoked access, or with a pending access review; nothing for present students.
- Register for an earlier date: nothing. PORTAL_ONLY: nothing. Empty `PORTAL_BASE_URL`: nothing, submit still succeeds; same for a missing approved template.
- Correction Absent → Present dismisses the PREPARED alert (reason, user); a SENT alert stays SENT. Present → Absent same day prepares one; on a later day prepares nothing.
- Publish: one notice per recipient; republish and withdraw + republish create nothing new.
- Rendered text contains only first name, date and link — no marks, no absence note; link points at that child's portal page.
- School form refuses ASSIST without `PORTAL_BASE_URL`; To send page shows the warning.
- Existing Gate 1, attendance and publication tests keep passing.

## Out of scope

Announcements (Gate 3), API/SMS sending (Gate 4B), Telugu texts, notices for corrected results, guardian self-service consent.
