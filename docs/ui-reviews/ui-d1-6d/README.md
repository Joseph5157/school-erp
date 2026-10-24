# UI-D1-6D — Notification queue ("To send"): synthetic screenshot and accessibility evidence

**Local synthetic evidence only.** Captured with Playwright (Chromium) against a throwaway **SQLite** database seeded with invented data (Guardians "Meena Rao" and "Other Parent" with a synthetic phone number, Students "Asha Rao" and "Bina Other"). The messages were prepared by the real services (an absence alert, a published report card, an announcement), so every state is genuine data. One Student's name is deliberately hostile (`<b>Asha</b> "R&D" Rao`) to show escaping, and one Guardian's phone is unusable. No real contact data appears and the database was deleted afterwards. It is not PostgreSQL, staging or production; the automated tests ran on PostgreSQL (see the PR).

**Nothing is sent.** The `wa.me` links were never opened; Mark as sent and Dismiss were exercised through the real POSTs.

Widths: 360, 390, 768, 1280, 1440 (full-page PNG).

| File prefix | State | What it shows |
| --- | --- | --- |
| `queue-populated-*` | five prepared messages | Header with "5 waiting · 0 sent today", the "never sends" note, one record per message: Guardian, **Ready to send** / **Phone number missing** badge, type, Student first name or "School notice", prepared time, the **exact message text in a quoted block** (the hostile name appears as literal text), Send on WhatsApp / Mark as sent, and the labelled Dismiss form with consequence text |
| `dismiss-blank-reason-refused-*` | blank Dismiss reason (browser validation bypassed) | The existing "Give a reason for not sending this message." message; all five rows still waiting |
| `after-mark-sent-with-sent-today-*` | one message marked sent | "Marked as sent.", waiting count down, **Sent today** labelled table (Time, Guardian, Message, Marked sent by) |
| `queue-empty-with-sent-today-*` | everything handled | Legacy "Nothing to send." empty state and the Sent today table |
| `banner-portal-only-*`, `banner-portal-only-no-settings-link-*` | school on portal only | "WhatsApp messages are switched off…" notice; the School settings link only for a viewer who can open it |
| `banner-portal-address-missing-*` | ASSIST, no `PORTAL_BASE_URL` | The portal-address warning |
| `restricted-sender-only-*` | `send_notification` only | No sidebar or trail; missing-phone rows say "ask someone who can update the guardian" instead of linking to a page the viewer cannot open |
| `restricted-no-permission-403-*`, `teacher-403-*` | `view_school` only / Teacher | The unchanged 403 |

## Measurements

| Check | Result |
| --- | --- |
| Document horizontal overflow | **0px** at 360, 390, 768, 1280, 1440 in every state and for every user |
| H1 count | exactly 1 on every captured page |
| Send links | all three: `target="_blank"`, `rel="noopener"`, host `wa.me` |
| Control names | e.g. "Send on WhatsApp to Meena Rao (opens in a new tab)", "Mark as sent for Meena Rao", "Reason for not sending * (required)", "Dismiss message to Other Parent" |
| Blank dismiss | 5 rows before and after: nothing dismissed |

## Known limits

- Keyboard: every control is a native link, button or input in reading order after the shared sidebar. The page does not add a skip link past the sidebar (shared shell, unchanged).
- The browser's own `required` validation bubble is not captured; the blank-reason screenshot bypasses it to show the server's refusal.
- A manual screen-reader pass and PostgreSQL staging verification remain open (ledger L8). Nothing is deployed.
