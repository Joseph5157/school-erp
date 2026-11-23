# G-06 threat model: guardian account recovery

- **Status:** **Accepted**, 2026-11-23. Independently reviewed on PR #301 (findings F1–F13 applied in r2,
  re-check N-A to N-D in r3). The product owner accepted the residual risks recorded in ADR 0029. Docs only:
  it approves no code.
- **Baseline:** `origin/main` c6aad3d.
- **Risk tier:** Critical ("password and account recovery", "authentication and sessions",
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3). This document is the written threat model that tier
  requires before code. Its ADR, [ADR 0029](../adr/0029-guardian-account-recovery.md), is **Accepted**.
- **Current state:** [G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md](G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md).

## 1. Scope

Any way a guardian who cannot sign in gets back in: the office reset that exists today
(`core/guardian_accounts.py:223-235`) and every option in ADR 0029 (improved office flow, email, SMS,
WhatsApp, questions, printed codes, hybrids). Staff and teacher recovery are out of scope but share the
same login and should follow the result.

## 2. Assets

| Asset | Why it matters |
| --- | --- |
| A guardian's portal session | Shows each granted child's profile, attendance, published report cards and notices (ADR 0014). Children's data. |
| The guardian login itself | One login per guardian covers every granted child (`core/models.py:3575-3623`). A teacher who is also a parent uses one login for both roles (ADR 0013). |
| Temporary passwords and any recovery secret | Bearer secrets. Today they never expire (research §2.1). |
| Guardian contact data | Phone and email, unverified and editable without an audit event (`core/models.py:532-533`; `core/views.py:3522-3532`). The callback control depends on the phone being right. |
| Audit trail | `SecurityEvent` (`accounts/models.py:60-126`); needed to settle disputes. |
| Office time and attention | A help-request queue can be flooded or used to harass staff. |
| School reputation and messaging number | A banned or spoofed school number harms every family (ADR 0015 Context). |

## 3. Actors

| Actor | Intent |
| --- | --- |
| Legitimate guardian | Get back in quickly. May have low literacy, a shared phone, a changing number. |
| Relative or estranged parent | Knows DOB, admission number, address, phone. May be in a custody dispute, may be restricted from the child. |
| Classmate or older sibling | Knows the child's details; may want to see marks or hide a report card. |
| The child | Uses the parent's phone; may reset to hide absences or results. |
| Office staff member | Legitimate resets; or an insider taking over an account or editing a phone number first. |
| Outside attacker | Credential stuffing, enumeration, lockout abuse, request spam, SIM swap, phishing with a fake reset page. |
| Provider or carrier | Sees message content and numbers in transit. |

## 4. Trust boundaries

1. Browser to server (public internet, HTTPS, `config/settings.py:146-158`).
2. Server to messaging provider (email SMTP, SMS gateway, WhatsApp BSP): none exists today.
3. Provider to the guardian's device (carrier network, SIM, lock screen, shared inbox).
4. Office desk to guardian (paper slip, phone call, in-person check).
5. Staff role to guardian account (permission `core.reset_guardian_password`, `core/views.py:4138`).
6. Anonymous request page to staff screen (proposed option G): untrusted text crosses into the office UI.

## 5. Threats

Likelihood and impact: L, M, H. Residual risk is after the listed mitigations, for the recommended design
in ADR 0029 (improved office flow plus a "can't sign in" request; no channel self-service). Requirement
numbers (R1…) refer to ADR 0029.

| # | STRIDE | Threat | L | I | Mitigations | Residual |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | S | **Account takeover by a relative** who can answer identity questions (DOB, admission number, parent names, address). These are low-entropy and known to family and classmates. | H | H | Never accept knowledge facts as proof. Office verifies in person with documents. A callback goes **only** to the number on the Guardian record and only confirms the request and books a visit; the password is handed over in person (ADR 0029 Appendix A, OD-G3). A phone change writes a HISTORY event at one choke point; a change in the last N days forces an in-person check (R17, R18). | M with in-person delivery. **Rises to H** if OD-G3 (c) callback delivery is chosen: the password then goes to whoever answers a shared family number. |
| T2 | S | **Identity guessing at a self-service form** (enumerate DOBs, admission numbers). | H | H | No self-service reset on knowledge facts (option E rejected). The request page never resets anything, does no account lookup and never confirms a match (R21). | L |
| T3 | S/I | **Shared or lost phone.** A code or link sent to a phone reaches whoever holds it; notification previews show it on the lock screen. | H | H | No phone-delivered secret in the first step. If a channel is added later: short expiry, single use, no secret in preview text. | L now; M if SMS or WhatsApp is added |
| T4 | I | **Account and username enumeration** through recovery responses, query patterns or rate-limit behaviour. | M | M | One generic response; the same queries and writes for every input (R1); throttles keyed by source and globally, not only by username. Sign-in already uses one generic error (`accounts/forms.py:10-25`) and hashes for unknown users (`accounts/backends.py:27-30`). | L |
| T5 | S/I | **Token theft or replay:** reset link in shared email, forwarded message, browser history, referrer, server logs; OTP read over the shoulder. | M | H | ≥128-bit link tokens or short codes with tight attempt limits; hashed at rest; single use; short expiry (OD-G6); never in logs (R13); `Referrer-Policy: no-referrer`; older secrets invalidated on issue and use. | L (no channel now) |
| T6 | S | **SMS interception and SIM swap.** SMS is not end-to-end protected; number recycling hands old numbers to strangers. | M | H | Do not use SMS as the only factor. If adopted, combine with office approval or a printed code; re-verify numbers yearly. Carrier SIM-swap signals are a provider feature to confirm. | M if SMS is used alone |
| T7 | E/T | **Staff misuse:** an office user resets a guardian password and signs in as them, edits the phone first so a callback reaches them, or hands the slip to the wrong person. | M | H | Reset method stored as a choice and the reset recorded as a HISTORY event shown on the guardian profile (R10, OD-G8); phone changes audited (R17); named staff only (OD-G7); "known to staff" needs a second person (OD-G3); periodic review of reset events. Gate 1 already blocks resetting privileged logins (`core/guardian_accounts.py:43-60`). | M: one trusted insider can still act alone unless OD-G7 picks two-person approval. |
| T8 | D/S | **Brute force** on reset codes or the request page; SMS pumping (paying for attacker-triggered messages). | M | M | Today sign-in has two rules, both keyed on the username: Rule A, 5 failures per username + source; Rule B, 20 per username from any source (`accounts/security.py:9-12`, `:71-78`). **Gap:** no cap per source across usernames, so one address can spray many usernames, and no global cap. R6 adds per-source and global caps with starting numbers; codes ≤5 attempts per issue and capped issues per day (R2, R20); no message for an unknown account. | L |
| T9 | S | **Session fixation and old sessions after recovery.** A thief keeps an open session after the owner resets. | M | H | Every recovery bumps `session_version` (`accounts/models.py:54-57`), as the office reset does (`core/guardian_accounts.py:232`); session key rotated at sign-in (Django default); forced change after a temporary credential. | L |
| T10 | R | **Owner not told** that their password was reset. An attacker who gets the temporary password signs in, is forced to change it, and the owner is then locked out, so an in-portal notice never reaches the owner. | H | H | The in-portal "reset by the school" notice is **informational only, not detection**. The real controls are the callback only to the number on record (R18), the reset as a HISTORY event visible on the guardian profile (R10), and the owner contacting the school when their password stops working. True owner notification needs a channel (OD-G2). | **H until a channel exists** |
| T11 | S/E | **Custody dispute:** an estranged or restricted parent recovers or obtains access. | M | H | Access follows explicit grants, not relationship labels (ADR 0013, ADR 0024); recovery never creates or restores a grant (R11); the office checks the guardian record, not just a name. | L for data access; M for social engineering of staff |
| T12 | I | **Sibling and multi-child accounts:** one recovered login exposes every granted child. | M | H | Same verification bar whatever the number of children; the list of children is visible to staff before the reset. | M (by design: one login per guardian) |
| T13 | T | **Child uses the parent's phone** to reset and hide absences or report cards. | H | M | No phone-only self-service; forced change; the temporary password is handed over in person. | M on shared devices. **Rises** with OD-G3 (c) callback delivery, since a child answering the parent's phone could receive the password. |
| T14 | R | **Weak forensics:** cannot tell who reset, why, and what proof was seen. | M | M | HISTORY events for request handling, resets (method as a choice), first sign-in after reset, expiry and contact-field changes; never the secret, typed values or contact data (R10, R17). | L |
| T15 | S | **Phishing with a fake "reset" page or message** once guardians expect reset messages. | M | M | No links in messages until a channel is decided; when added, a fixed sender, provider-approved templates, and guidance that the school never asks for a password. | L now |
| T16 | I | **Unverified or tampered contact data** used as a channel or for a callback reaches a stranger (typo, old number, insider edit). | M | H | Callback only to the Guardian record, never to a number typed into a request (option G has no phone field, R21); phone changes audited and recent changes force an in-person check (R17, R18). No verified-contact field exists today (`core/models.py:532-533`). | L now |
| T17 | D | **Lost slip and never-expiring access.** A temporary password that never expires is a bearer secret in a drawer. | M | M | Expiry on temporary passwords, shorter for resets (R3, OD-G5); never-signed-in list so the office follows up ([spec](G06_NEVER_SIGNED_IN_SPEC.md)). | L |
| T18 | D/T | **Request-page abuse:** flooding the office queue; harassing staff; anonymous free text (links, scripts, abuse) shown to staff; spam that makes the office call real parents who asked for nothing. | H | M | Short fixed fields with length caps and no phone field (R21); past the global cap nothing is stored and the office sees a count of dropped requests (R6); template autoescape pinned by a no-HTML test; per-source and global caps (R6); no account lookup on submit; matching done offline by staff; a dedicated queue permission (R22); purge after OD-G4's period with a test. Staff call only the number on the record and say the school is returning a request. | L for the system; M for office time under a flood |
| T19 | E | **Forced-change bypass:** the guardian (or a thief) sets the new password equal to the temporary one, so the slip stays a working password. Today nothing forbids it: `AUTH_PASSWORD_VALIDATORS` has no such rule (`config/settings.py:177-190`) and Django's `PasswordChangeForm` allows it. **Live bug.** | M | M | Reject new == current with a test (R19). Fixed by a separate small PR. | L after the fix |
| T20 | D | **Lockout denial of service:** anyone who knows a username triggers Rule B (20 failures from any source). Throttled attempts also call `record_failure` (`accounts/forms.py:41-46`, line 44), so continued attempts keep the lockout alive. The office reset does not clear it (`core/guardian_accounts.py:223-235`), so a freshly reset guardian may still be locked out. **Live bug** for the reset part. | M | M | Reset calls `clear_lockout` and records `LOCKOUT_CLEARED` (R16), fixed by a separate small PR. Per-source caps (R6) slow single-source abuse. The office can clear lockouts (`core/views.py:3679-3704`). | M: a distributed attacker can still re-lock a known username |
| T21 | I | **Log leakage:** temporary passwords, tokens, request text or phone numbers in application logs, crash reports, Telegram alerts or usage counters. | L | H | Allow-lists of Security Gate 4A and ADR 0027 apply; no secret or request contents in any log line (R13); a test that the reset and request paths log nothing sensitive. | L |
| T22 | I | **Insider sees a temporary password on screen or on a slip left on a desk or printer.** | M | M | Shown once with `no-store` (`core/views.py:4007-4016`); slip handed over in person; short expiry for resets (R3); forced change at first sign-in. | M: physical handling remains |
| T23 | I | **Timing differences** reveal whether an account exists on the request page or sign-in. | L | M | The same queries, writes and response for known, unknown and throttled input (R1), tested by query and write counts, not wall-clock timing. Sign-in already hashes for unknown users. | L |

### Top residual risks (recommended design)

1. **T10 Owner not notified:** **H** until a channel exists. The in-portal notice is not detection.
2. **T7 Staff misuse:** M. One trusted office user can still reset alone unless OD-G7 picks two-person approval.
3. **T1 Relative takeover through a shared family number:** M with in-person delivery; H if OD-G3 (c) callback delivery is chosen.
4. **T20 Lockout DoS:** M. Distributed re-locking of a known username stays possible.
5. **T12 Multi-child exposure:** M, inherent in one login per guardian.

T13 (child on a shared phone) and T22 (slip handling) are also M.

## 6. India-specific context

These points are factual only where the repo documents them. Everything else is marked **to confirm** and
needs legal or provider confirmation before it is relied on.

| Topic | What is known | Status |
| --- | --- | --- |
| DPDP Act 2023 | Repo: substantive duties from 13 May 2027 (ADR 0015 Context; Phase 7 plan D3); consent must be clear and recorded. The Act has specific duties for children's personal data. Whether a guardian's own phone and email count as children's data when held by a school because of the child; whether using them for authentication needs separate consent or notice. | Date: repo. Everything else: **to confirm** with counsel. |
| DPDP retention | How long to keep reset records, verification method and note, help-request contents and contact-change events; whether HISTORY (permanent) retention of reset events is acceptable. ADR 0029 keeps reset notes short and structured, or in a separate deletable table, so a retention rule can be applied. | **To confirm** with counsel. |
| TRAI DLT (transactional SMS) | Commercial SMS in India is sent through a registered entity, header and template on a carrier DLT platform. Registration steps, timelines, whether an OTP template is "transactional" or "service", and fees. | **To confirm** with a provider and the TRAI rules in force. |
| WhatsApp Business templates | Repo: Meta bills per message since 1 Jul 2025; utility template about ₹0.115 excl. 18% GST, from one vendor blog (Phase 7 plan D2). Authentication-category templates, their price, approval time and any rules on OTP button format. | Utility price: repo, itself marked "verify". Authentication pricing and approval: **to confirm**. |
| SMS cost per message | No figure in the repo. | **To confirm** per provider. |
| Email | No provider configured (`config/deployment_safety.py:31-42`). Deliverability to common Indian free mail, sender authentication setup. | **To confirm**. |
| Number recycling and SIM swap | Indian carriers recycle numbers after inactivity. Recycling period and any SIM-swap check service. | **To confirm** with carriers or provider. |
| Shared carrier addresses | Mobile carriers often put many users behind few addresses (carrier-grade NAT), which affects per-source limits (R6). | **To confirm** by measuring on staging once limits exist. |

## 7. Requirements

The requirements any implementation must meet are R1–R22 in
[ADR 0029](../adr/0029-guardian-account-recovery.md#security-requirements-for-any-implementation). They are
kept in one place so the two documents cannot drift.

## 8. Open questions for the product owner

Listed as OD-G1 onward in [ADR 0029](../adr/0029-guardian-account-recovery.md#decisions-for-the-product-owner).
