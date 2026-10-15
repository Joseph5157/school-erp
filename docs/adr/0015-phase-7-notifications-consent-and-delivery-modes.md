# 0015. Phase 7 notifications, guardian consent and delivery modes

## Status

Accepted (2026-10-15, Phase 7 planning PR #45) — FROZEN.
Planning: `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (decisions D1-D5, D8).

## Context

Guardians now have a read-only portal (ADR 0013, ADR 0014) but only learn of
events by logging in. Many schools already message parents from an ordinary
WhatsApp account and do not want to contract a WhatsApp Business API provider.
Sending from an ordinary account through automation breaks WhatsApp's rules and
risks losing the school's main contact number. India's DPDP Act (substantive
duties from 13 May 2027) expects clear, recorded consent and minimal data.

## Decision

**Delivery modes (per-school setting)**
- ASSIST (first version): the ERP prepares each message; a staff member opens
  WhatsApp from the ERP through a click-to-chat link with the guardian's number
  and text pre-filled, sends it, and confirms it in the ERP.
- API: WhatsApp Business API through a provider behind an adapter (optional,
  later gate). SMS and PORTAL_ONLY are also valid settings.
- The ERP never automates a normal WhatsApp account.

**Consent**
- Messaging requires an explicit, recorded opt-in per guardian per channel
  (who recorded it, when, how). No consent means no message and no
  "To send" entry. Opt-out is honored immediately.
- Consent records are append-only history; the current state is derived.

**Content**
- A message contains at most the student's first name, a date, and a portal
  link. Never marks, grades, reasons for absence, or correction details.

**Sending**
- Messages are written to a database outbox. No network call is made inside a
  web request or a database transaction.
- Each notification has a unique idempotency key (guardian, student, type,
  date) so resubmitting or correcting a register never double-sends.
- Statuses: QUEUED, PREPARED, SENT, DELIVERED, FAILED, SKIPPED_NO_CONSENT.
  Failures are visible to administrators; nothing is dropped silently.
- Notification templates are versioned; an approved template body is never
  edited in place.

**Triggers**
- Absence alert: when a register is SUBMITTED, for ABSENT entries only.
  Later corrections do not send automatic retractions.
- Result published: when a TermPublication becomes PUBLISHED; says a report
  card is available, never its contents.
- Announcements: published in the portal first; sending is a separate,
  explicit administrator step with an audience count preview.
- Fee reminders: the type system is generic, but the fee reminder itself is
  built with Phase 3. No fee code or placeholder is added in Phase 7.

## Consequences

- Schools can start with no provider contract or per-message cost.
- Staff do a manual tap per message in ASSIST mode; acceptable for the usual
  daily volume of absence alerts.
- Parent phone numbers must be stored with a country code for links to work.
- Consent must be collected in the real world (paper form or portal tick-box)
  before alerts reach any parent.
- API mode adds provider template approval, cost and an INR-billed account.

## Amendment (Gate 1, 2026-10-15)

- Status `DISMISSED` added: a staff member may decide not to send a PREPARED message, with a required reason, recorded with who and when.
- Consent is re-checked when the To send page loads and when a message is marked sent; a PREPARED message whose guardian has opted out becomes `SKIPPED_NO_CONSENT`.
- Gate 1 offers only PORTAL_ONLY (default) and ASSIST in the school settings; API and SMS wait for Gate 4B.

## Related

ADR 0013, ADR 0014; `docs/REQUIREMENTS.md` Phase 7 scope.
