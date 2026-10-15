# Phase 7 Gate 3 — Announcements — Design

**Date:** 2026-10-15
**Authority:** `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (§4 Announcement, §5.1, §6, §7 Gate 3) and `docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md` ("Announcements: published in the portal first; sending is a separate, explicit administrator step with an audience count preview"). Builds on Gate 1 (outbox) and Gates 2/4 (PR #51: `core/notification_producers.py`, `PORTAL_BASE_URL`). The branch is stacked on `phase-7/gate-2-4-alerts`.

## Goal

Administrators publish school notices that guardians read in the portal, and can then prepare a WhatsApp message per guardian that links to the notice.

## Decisions (owner, 2026-10-15)

| Topic | Decision |
|---|---|
| WhatsApp text | Link only: `Dear parent, there is a new notice from the school. Read it here: {portal_url}`. No title or body in the message; ADR 0015's parameter list is unchanged. |
| Who publishes | School administrators only. No teacher posting. |
| Drafts | None: saving publishes. |

## Decisions made in this spec (review these)

1. **Immutable once published.** Title, body and audience never change; a mistake is withdrawn (reason required) and a new notice published. Database triggers refuse DELETE and changes to everything except the withdrawal fields, which may be set once (null → value) and never cleared.
2. **Audience** is one of: `ALL` (whole school), `CLASS` (one `ClassGrade`), `SECTION` (one `Section`). Exactly the matching FK is set (check constraint). No academic-year field: a notice is about "now".
3. **Who it reaches** (portal and WhatsApp): guardians with portal access — the Gate 2/4 rule, `notification_producers.portal_grants(student)` (active grant, not review-pending, active login) — to at least one student in the audience. Membership: the student's academic enrollment effective on `business_today()`; for `ALL`, any student with an effective enrollment. Computed live for the portal and at the moment messages are prepared.
4. **Portal.** New "Notices" tab: `portal/notices/` lists non-withdrawn notices whose audience includes any of the guardian's *visible* children (same visibility as the rest of the portal), newest first; `portal/notices/<uuid:public_id>/` shows one (404 if not visible to this guardian or withdrawn). Home shows the latest 3 above the student list. Body is shown as plain text with line breaks (`linebreaksbr`, autoescaped).
5. **Prepare WhatsApp messages** (ASSIST only, permission `core.send_notification`, POST): one `Notification` per recipient guardian, `type=ANNOUNCEMENT`, `student=None`, subject `announcement-<pk>`, parameters `{"portal_url": PORTAL_BASE_URL + notice URL}`. Same guardian with two children in the audience → one message. Repeating does nothing new (Gate 1 idempotency). Refused for a withdrawn notice. Uses the same never-raise rule as Gates 2/4 (`NotificationError` → logged, counted as not prepared) and shows "N messages prepared".
6. **Audience preview** on the notice page: number of guardians with portal access, and how many of them are currently opted in to WhatsApp. Shown before and after preparing.
7. **Withdraw** (permission `core.withdraw_announcement`, POST, reason required): hides from the portal at once and dismisses every PREPARED message for that notice with reason `Announcement withdrawn` (dismissed_by = the withdrawing user). Sent messages are not retracted.
8. **Lengths.** Title up to 120 characters, body up to 2000, both required (stripped).
9. **To send page.** Announcement rows have no student; the row shows the type and "School notice" instead of a first name. No other change.
10. **Permissions.** `add_announcement`, `view_announcement` and new `withdraw_announcement`, granted to School Administrators by migration. Office nav link "Announcements" (`core.view_announcement`).
11. **Seeded text** `announcement` v1 (approved), seeded by migration like Gates 2/4.

## Model

`Announcement`: `public_id` (UUID, unique), `title`, `body`, `audience` (ALL/CLASS/SECTION), `class_grade` (FK, null), `section` (FK, null), `published_by`, `published_at`, `withdrawn_at`, `withdrawn_by`, `withdrawal_reason`. Ordering newest first. Constraints: audience valid; FK set exactly for its audience; withdrawal fields all set or all empty.

## Components

- `core/models.py`: `Announcement` (+ migrations: model, history-guard triggers for PostgreSQL and SQLite, permissions to group, seeded template).
- `core/announcements.py` (new): `publish(...)`, `withdraw(...)`, `audience_students(announcement, on_date=None)`, `recipient_grants(announcement)` (grants per guardian), `audience_counts(announcement)`, `visible_announcements(user)`, `prepare_messages(announcement)`.
- `core/forms.py`: `AnnouncementForm` (title, body, audience, class_grade, section; clean enforces the matching choice).
- Office views + templates: list, create, detail (preview, prepare, withdraw). Portal views + templates: notices list, notice detail, home block, tab.
- `core/navigation.py`: office link. `notifications_to_send.html`: "School notice" label.
- Docs: Phase 7 plan implementation notes for Gate 3.

## Testing (new `core/tests/test_phase7_announcements.py`)

- Publish: valid for each audience; wrong FK combinations refused; non-admins get 403; history guards refuse edit/delete and clearing a withdrawal.
- Audience: ALL / CLASS / SECTION reach exactly the right guardians; guardians without portal access, revoked, pending review or inactive login are excluded; a student whose enrollment has ended is excluded.
- Portal: notices list and detail show only matching, non-withdrawn notices for visible children; another guardian's notice → 404; body escaped; home shows latest 3.
- Prepare: ASSIST only; one message per guardian (two children → one); repeat creates nothing; consent → PREPARED / SKIPPED; text equals the approved wording with the notice link; withdrawn notice refused; missing portal address → nothing prepared, page still works.
- Withdraw: reason required; hides from portal; dismisses PREPARED messages, leaves SENT.
- To send shows "School notice" for an announcement row.

## Out of scope

Attachments, scheduling and expiry, teacher posting, editing after publishing, read receipts, translations, SMS/API sending.
