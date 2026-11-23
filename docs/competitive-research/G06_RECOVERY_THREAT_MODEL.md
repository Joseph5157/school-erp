# G-06 threat model: guardian account recovery

- **Status:** draft for review. Docs only. Approves no code.
- **Baseline:** `origin/main` c6aad3d.
- **Risk tier:** Critical ("password and account recovery", "authentication and sessions",
  `docs/engineering/IMPLEMENTATION_WORKFLOW.md` §3). This document is the written threat model that tier
  requires before code. The accepted ADR is still missing: [ADR 0029](../adr/0029-guardian-account-recovery.md)
  is **Proposed**.
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
| Guardian contact data | Phone and email, unverified (`core/models.py:532-533`). Children's and families' personal data under DPDP. |
| Audit trail | `SecurityEvent` (`accounts/models.py:60-126`); needed to settle disputes. |
| School reputation and messaging number | A banned or spoofed school number harms every family (ADR 0015 Context). |

## 3. Actors

| Actor | Intent |
| --- | --- |
| Legitimate guardian | Get back in quickly. May have low literacy, a shared phone, a changing number. |
| Relative or estranged parent | Knows DOB, admission number, address, phone. May be in a custody dispute, may be restricted from the child. |
| Classmate or older sibling | Knows the child's details; may want to see marks or hide a report card. |
| The child | Uses the parent's phone; may reset to hide absences or results. |
| Office staff member | Legitimate resets; or an insider taking over an account. |
| Outside attacker | Credential stuffing, enumeration, SIM swap, phishing with a fake reset page. |
| Provider or carrier | Sees message content and numbers in transit. |

## 4. Trust boundaries

1. Browser to server (public internet, HTTPS, `config/settings.py:146-157`).
2. Server to messaging provider (email SMTP, SMS gateway, WhatsApp BSP): none exists today.
3. Provider to the guardian's device (carrier network, SIM, lock screen, shared inbox).
4. Office desk to guardian (paper slip, phone call, in-person check).
5. Staff role to guardian account (permission `core.reset_guardian_password`, `core/views.py:4138`).

## 5. Threats

Likelihood and impact: L, M, H. Residual risk is after the listed mitigations, for the recommended design
in ADR 0029 (improved office flow plus a "request help" form; no channel self-service).

| # | STRIDE | Threat | L | I | Mitigations | Residual |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | S | **Account takeover by a relative** who can answer identity questions (DOB, admission number, parent names, address). These are low-entropy and known to family and classmates. | H | H | Never accept knowledge facts as proof. Office verifies in person with documents or by callback to the number already on record; records method and note; owner notified when a channel exists. | M: callback to a shared family number still reaches the relative. Office judgement remains. |
| T2 | S | **Identity guessing at a self-service form** (enumerate DOBs, admission numbers). | H | H | No self-service reset on knowledge facts (option E rejected). The help form never resets anything and never confirms a match. | L |
| T3 | S/I | **Shared or lost phone.** A code or link sent to a phone reaches whoever holds it; notification previews show it on the lock screen. | H | H | No phone-delivered secret in the first step. If a channel is added later: short expiry, single use, no secret in preview text, owner notified on another channel or in-app. | L now; M if SMS or WhatsApp is added |
| T4 | I | **Account and username enumeration** through recovery responses, timing or rate-limit behaviour. | M | M | One generic response and same page for every input; same work path; throttle keyed by source and globally, not only by username. Sign-in already uses one generic error (`accounts/forms.py:10-25`) and hashes for unknown users (`accounts/backends.py:27-30`). | L |
| T5 | S/I | **Token theft or replay:** reset link in shared email, forwarded message, browser history, referrer, server logs; OTP read over the shoulder. | M | H | ≥128-bit link tokens or short codes with tight attempt limits; hashed at rest; single use; 15–30 min expiry (to confirm in OD-G6); never in logs or crash reports (Security Gate 4A allow-list); `Referrer-Policy` on the reset page; invalidate on use and on any newer issue. | L (no channel now) |
| T6 | S | **SMS interception and SIM swap.** SMS is not end-to-end protected; number recycling hands old numbers to strangers. | M | H | Do not use SMS as the only factor. If adopted, combine with office approval or a printed code; re-verify numbers yearly. Carrier SIM-swap signals are a provider feature to confirm. | M if SMS is used alone |
| T7 | E/T | **Staff misuse:** an office user resets a guardian password and signs in as them, or hands the slip to the wrong person. | M | H | Require reason and verification method at reset; record as a HISTORY event (today ROUTINE, purged after 365 days, `accounts/models.py:102-111`); show resets on the guardian profile; owner notification; restrict `reset_guardian_password` to few staff; periodic review of reset events; two-person rule as an option (OD-G7). Gate 1 already blocks resetting privileged logins (`core/guardian_accounts.py:43-60`). | M: one trusted insider can still act alone unless OD-G7 picks two-person approval. |
| T8 | D/S | **Brute force** on reset codes or the help form; flooding the office queue; SMS pumping (paying for attacker-triggered messages). | M | M | Per account, per source and global limits; codes with ≤5 attempts; CAPTCHA-free design preferred, so tight limits instead; office queue capped and de-duplicated; no message sent for an unknown account. Today sign-in has per-username limits only (`accounts/security.py:71-78`). | L |
| T9 | S | **Session fixation and old sessions after recovery.** A thief keeps an open session after the owner resets. | M | H | Every recovery bumps `session_version` (`accounts/models.py:54-57`), as the office reset does (`core/guardian_accounts.py:232`); rotate session key at sign-in (Django default); forced change after a temporary credential. | L |
| T10 | R | **Owner not told** that their password was reset or changed, so takeover goes unnoticed. | H | H | Today no notification exists (no channel). Interim: show "last password change" and "reset by school on <date>" on the guardian's own portal home after sign-in; office tells the guardian in person. With a channel: notify old and new contact on every reset and change. | M until a channel exists |
| T11 | S/E | **Custody dispute:** an estranged or restricted parent recovers or obtains access. | M | H | Access follows explicit grants, not relationship labels (ADR 0013, ADR 0024); recovery must never create or restore a grant; office checks the guardian record, not just a name; restricted relationships are not granted. | L for data access; M for social engineering of staff |
| T12 | I | **Sibling and multi-child accounts:** one recovered login exposes every granted child. | M | H | Same verification bar whatever the number of children; the list of children is visible to staff before the reset. | M (by design: one login per guardian) |
| T13 | T | **Child uses the parent's phone** to reset and hide absences or report cards. | H | M | No phone-only self-service; forced change and owner notification; office reset needs the guardian present or a callback. | M on shared devices |
| T14 | R | **Weak forensics:** cannot tell who reset, why, and what proof was seen. | M | M | HISTORY events for reset requests, approvals, refusals, issued codes and completions; actor, guardian, method, reason; never the secret or the typed values. | L |
| T15 | S | **Phishing with a fake "reset" page or message** once guardians expect reset messages. | M | M | No links in messages until a channel is decided; when added, a fixed sender, templates approved by the provider, and guidance that the school never asks for a password. | L now |
| T16 | I | **Unverified contact data** used as a channel sends a secret to a stranger (typo, old number). | M | H | A channel needs a verified contact (verified-at date, by whom, how); unverified numbers never receive a secret. No such field exists today (`core/models.py:532-533`). | L now |
| T17 | D | **Lost slip and expired-never access.** A temporary password that never expires is a bearer secret in a drawer. | M | M | Expiry on temporary passwords (OD-G5); never-signed-in list so the office follows up ([spec](G06_NEVER_SIGNED_IN_SPEC.md)). | L |

### Top five by residual risk (recommended design)

1. **T7 Staff misuse:** M. One trusted office user can still reset alone.
2. **T1 Relative takeover via a shared family number:** M.
3. **T10 Owner not notified:** M until a channel exists.
4. **T12 Multi-child exposure:** M, inherent in one login per guardian.
5. **T13 Child on the parent's phone:** M on shared devices.

## 6. India-specific context

These points are factual only where the repo documents them. Everything else is marked **to confirm** and
needs legal or provider confirmation before it is relied on.

| Topic | What is known | Status |
| --- | --- | --- |
| DPDP Act 2023 | Repo: substantive duties from 13 May 2027 (ADR 0015 Context; Phase 7 plan D3); consent must be clear and recorded. The Act has specific duties for children's personal data, including verifiable parental consent. Whether using a parent's phone or email for authentication needs separate consent, what notice is needed, and retention limits for contact and audit data. | Date: repo. Obligations for recovery: **to confirm** with counsel. |
| TRAI DLT (transactional SMS) | Commercial SMS in India is sent through a registered entity, header and template on a carrier DLT platform. Registration steps, timelines, whether an OTP template is "transactional" or "service", and fees. | **To confirm** with a provider and the TRAI rules in force. |
| WhatsApp Business templates | Repo: Meta bills per message since 1 Jul 2025; utility template about ₹0.115 excl. 18% GST, from one vendor blog (Phase 7 plan D2). Authentication-category templates, their price, approval time and any rules on OTP button format. | Utility price: repo, itself marked "verify". Authentication pricing and approval: **to confirm**. |
| SMS cost per message | No figure in the repo. | **To confirm** per provider. |
| Email | No provider configured (`config/deployment_safety.py:31-42`). Deliverability to common Indian free mail, sender authentication setup. | **To confirm**. |
| Number recycling and SIM swap | Indian carriers recycle numbers after inactivity. Recycling period and any SIM-swap check service. | **To confirm** with carriers or provider. |

## 7. Requirements any recovery implementation must meet

These are the minimum. ADR 0029 restates them as decisions.

1. **No account-existence leak:** identical response, status code, page and approximate timing for known
   and unknown accounts; throttles must not reveal existence.
2. **Secrets:** generated with `secrets`; link tokens ≥128 bits; codes short enough to read aloud only when
   paired with a strict attempt limit; stored only as a hash; single use; short expiry; all earlier
   secrets for the account invalidated on issue and on use.
3. **Rate limits:** per account, per hashed source and global, with office visibility like
   `sign-in-lockouts/` (`core/views.py:3679-3704`).
4. **Session revocation:** every reset and recovery calls `end_all_sessions()`; forced change after any
   temporary credential (existing flow, `accounts/middleware.py:177-180`).
5. **Owner notification** on every reset and password change, on a channel other than the one used to
   recover where possible; until a channel exists, an in-portal notice after sign-in.
6. **Audit:** HISTORY events for request, approval or refusal, issue, completion and expiry, with actor,
   guardian, method and reason; never the secret, the typed value or contact data (ADR 0013, ADR 0027,
   Security Gate 4A).
7. **CSRF** on every POST; `no-store` on any page showing a secret (as `_credential_slip`,
   `core/views.py:4007-4016`); `Referrer-Policy: no-referrer` on token pages.
8. **Logging hygiene:** no tokens, codes, phone numbers or emails in logs, crash reports, Telegram alerts
   or usage counters.
9. **No grant changes:** recovery restores a login, never a `GuardianStudentAccess` grant.
10. **Accessibility:** works on a basic Android phone, in plain words, without typing long tokens.

## 8. Open questions for the product owner

Listed as OD-G1 onward in [ADR 0029](../adr/0029-guardian-account-recovery.md#decisions-for-the-product-owner).
