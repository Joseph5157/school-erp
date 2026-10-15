# Phase 7 Gate 1 — Consent, Notification Outbox and ASSIST "To send" — Design

**Date:** 2026-10-15
**Authority:** `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (approved, §3 D1–D5, §4, §5.1, §6, §7 Gate 1) and `docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md`. This spec only fills in what those leave open.

## Goal

Lay the foundation every later notification gate uses: recorded guardian consent, a per-school channel setting, an idempotent notification outbox with minimal message content, and the ASSIST "To send" page where office staff send prepared messages from the school's own WhatsApp. Gate 1 creates no messages by itself; Gates 2–4 add the producers (absence, announcements, result published).

## Decisions (owner, 2026-10-15)

| Topic | Decision |
|---|---|
| Recording consent | Office administrators record opt-in / opt-out on the guardian page, with a source (paper form, in person, phone call, other). A guardian portal tick-box is later. |
| Channel modes offered | ASSIST and PORTAL_ONLY only. API and SMS exist as values for Gate 4B but cannot be selected. Default PORTAL_ONLY, so nothing is prepared until the school chooses ASSIST. |
| Language | English templates now. Templates carry a `language` field; Telugu versions can be added later without code changes. |
| Who sends | School Administrators only (new permission). |

## Decisions made in this spec (review these)

1. **DISMISSED status (addition to ADR 0015's list).** §5.1 says unsent items stay "until done or dismissed", but the ADR's status list has no dismissed state. Add `DISMISSED` with `dismissed_by`, `dismissed_at` and a required short reason. ADR 0015 gets a one-line amendment.
2. **Consent is checked twice.** At enqueue (no current opt-in → `SKIPPED_NO_CONSENT`) and again whenever the To send page loads or a message is marked sent: a PREPARED message whose guardian has since opted out becomes `SKIPPED_NO_CONSENT` and is never offered.
3. **Unusable phone numbers.** The WhatsApp link needs an international number. The link uses the existing `normalize_phone` rule from bulk import (10-digit Indian mobiles become +91…; numbers written with + are kept). If a guardian's phone cannot be normalised, the row shows "Phone number missing or not usable — update the guardian" with a link to the guardian page and no Send button. The message stays PREPARED so it can be sent once the number is fixed. Gate 1 does not rewrite stored phone numbers.
4. **Minimal content is enforced in code (D4).** Notification parameters may only use the keys `first_name`, `date` and `portal_url`; anything else raises an error. Templates may only reference those placeholders, checked when a template is saved.
5. **Idempotency key** = `"{type}:{guardian_pk}:{student_pk or '-'}:{subject}"`, where `subject` is chosen by the producer (for an absence alert, the register date). Enqueueing the same key twice returns the existing notification and creates nothing.
6. **PORTAL_ONLY mode** creates no notifications at all (enqueue returns `None`). Switching to ASSIST does not back-fill earlier events.
7. **History rules.** Consent records: append-only (database triggers refuse UPDATE and DELETE). Notifications: never deleted; content fields immutable; status may only move forward along the allowed transitions below; final states are frozen. Templates: never deleted; `key`, `channel`, `language`, `version` and `body` are immutable; `approved` may go from false to true only.
8. **No new security events.** The consent table and the notification rows are themselves the audit trail.

## Model

All in `core` (project convention).

- `School.notification_channel` — `CharField` choices `PORTAL_ONLY` (default), `ASSIST`, `API`, `SMS`.
- `GuardianContactConsent` — `guardian` (FK PROTECT), `channel` (`WHATSAPP` only for now), `status` (`OPTED_IN` / `OPTED_OUT`), `source` (`PAPER_FORM` / `IN_PERSON` / `PHONE_CALL` / `OTHER`), `note` (≤ 200 chars, optional), `recorded_by` (FK user, PROTECT), `recorded_at` (default now). Current state = latest row per (guardian, channel) by `recorded_at`, then `pk`. No row = not opted in.
- `NotificationTemplate` — `key` (slug, e.g. `absence_alert`), `channel`, `language` (`en`), `version` (positive int), `body` (text with `{first_name}`, `{date}`, `{portal_url}` placeholders), `approved` (bool), `created_at`. Unique (`key`, `channel`, `language`, `version`). Enqueue uses the highest approved version for the key, channel and language.
- `Notification` — `guardian` (FK PROTECT), `student` (FK PROTECT, nullable), `type` (`ABSENCE`, `RESULT_PUBLISHED`, `ANNOUNCEMENT`), `template` (FK PROTECT), `parameters` (JSON), `channel_mode` (`ASSIST` / `API` / `SMS`), `status`, `idempotency_key` (unique), `attempts`, `error_code`, `provider_message_id`, `marked_sent_by` / `marked_sent_at`, `dismissed_by` / `dismissed_at` / `dismiss_reason`, `created_at`, `updated_at`.
  - Statuses: `QUEUED`, `PREPARED`, `SENT`, `DELIVERED`, `FAILED`, `SKIPPED_NO_CONSENT`, `DISMISSED`.
  - Allowed transitions: QUEUED → PREPARED / FAILED / SKIPPED_NO_CONSENT; PREPARED → SENT / DISMISSED / SKIPPED_NO_CONSENT / FAILED; SENT → DELIVERED. Everything else is refused by a trigger. ASSIST enqueue creates rows directly as PREPARED (or SKIPPED_NO_CONSENT).

## Service — `core/notifications.py`

- `current_consent(guardian, channel="WHATSAPP") -> GuardianContactConsent | None` and `is_opted_in(guardian, channel="WHATSAPP") -> bool`.
- `record_consent(*, guardian, status, source, note, user) -> GuardianContactConsent`.
- `enqueue(*, guardian, student, type, template_key, parameters, subject) -> Notification | None` — validates parameter keys; returns `None` in PORTAL_ONLY; looks up the approved template; consent check; creates PREPARED or SKIPPED_NO_CONSENT; idempotent on the key (race-safe: `IntegrityError` → fetch existing).
- `render(notification) -> str` — template body formatted with the parameters.
- `whatsapp_link(notification) -> str | None` — `https://wa.me/<digits>?text=<url-encoded render>`, or `None` when the phone cannot be normalised.
- `to_send() -> QuerySet` — first moves PREPARED rows without current consent to SKIPPED_NO_CONSENT, then returns PREPARED rows oldest first, with guardian and student loaded.
- `mark_sent(notification, *, user)` and `dismiss(notification, *, user, reason)` — re-check status (and consent for `mark_sent`) under `select_for_update`; raise `NotificationError` with a plain message on a stale or invalid action.

No network calls anywhere in Gate 1.

## Pages

1. **Guardian page (office)** — new "WhatsApp messages" card: current state ("Opted in on 3 Oct 2026 · paper form · by admin" / "Opted out …" / "No consent recorded — messages will not be prepared"), the history list (newest first), and, with `core.add_guardiancontactconsent`, a small form: Opt in / Opt out, source, optional note.
2. **School settings** — the existing School form gains "Messages to guardians" with two choices: "Portal only (no WhatsApp messages)" and "WhatsApp, sent by office staff (ASSIST)".
3. **To send** (`/notifications/to-send/`, permission `core.send_notification`) — U1 shell, office sidebar link "To send" in the Daily group.
   - Header line: "N waiting · M sent today".
   - One card per PREPARED message, oldest first: guardian name, student first name, type label, message text as it will be sent, and:
     - **Send on WhatsApp** — opens the `wa.me` link in a new tab (plain link; works without JS).
     - **Mark as sent** — POST; moves to SENT with the user and time.
     - **Dismiss** — POST with a required reason (≤ 200 chars); moves to DISMISSED.
     - If the phone is unusable: the warning text and a link to the guardian page instead of Send.
   - Empty state: "Nothing to send. Messages appear here when the school prepares them."
   - When the school's mode is PORTAL_ONLY, a notice says WhatsApp messages are switched off, with a link to School settings.
   - Below: "Sent today" list (guardian, student first name, type, time, by whom).

## Permissions

New: `core.send_notification` (on Notification) and the default `core.view_notification`, `core.add_guardiancontactconsent`, `core.view_guardiancontactconsent`. A data migration grants them to "School Administrators" (same pattern as `0055`). Teachers and guardians get none.

## Tests (new `core/tests/test_phase7_notifications.py`)

- Consent: no row → not opted in; latest row wins; opt-out after opt-in → not opted in; consent rows refuse UPDATE and DELETE (triggers, SQLite and PostgreSQL).
- Enqueue: PORTAL_ONLY → `None`, no rows; ASSIST + opted in → PREPARED; not opted in → SKIPPED_NO_CONSENT; same subject twice → one row; disallowed parameter key → error; no approved template → error; uses the highest approved version.
- Templates: placeholder outside the allowed three → validation error; approved body cannot change; approved cannot go back to false.
- Notifications: allowed transitions succeed; refused ones raise `DatabaseError`; no DELETE; content fields immutable.
- `to_send()`: guardian opted out after PREPARED → row becomes SKIPPED_NO_CONSENT and is not listed.
- `whatsapp_link`: "98765 43210" → `https://wa.me/919876543210?text=...`; text is URL-encoded; unusable phone → `None` and the page shows the fix-phone warning.
- Views: To send lists PREPARED only; Mark as sent and Dismiss work once and refuse a second time with a message; dismiss needs a reason; teacher and guardian users get 403; anonymous users are redirected; guardian page shows the consent card and the form only with permission; School form offers exactly two channel choices.
- Guardian portal pages unchanged (existing forbidden-word test still passes).

## Out of scope (later gates)

Producers (absence alerts — Gate 2; announcements — Gate 3; result published — Gate 4); API/SMS sending, worker command, retries and delivery receipts (Gate 4B); guardian portal consent switch; Telugu templates; phone number clean-up tools.
