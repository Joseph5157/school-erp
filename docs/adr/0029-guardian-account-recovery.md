# ADR 0029: Guardian account recovery

Status: **Proposed**, 2026-11-23 (G-06 Phase 0). Not accepted. No recovery code may be written on the
strength of this document. Acceptance needs the product owner's decisions below and the conditions in
"What would make this acceptable".

## Context

- Guardians sign in with an office-created username and a temporary password handed over on a printed
  slip, then must change it (ADR 0013; `core/guardian_accounts.py:125-147`; `accounts/middleware.py:177-180`).
- A guardian who forgets the password, or loses the slip, has one path: the office reset
  (`core/views.py:4138-4163`). It ends all sessions and forces a change (`core/guardian_accounts.py:223-235`),
  but records no reason or verification method, is a ROUTINE event purged after 365 days
  (`accounts/models.py:102-111`), and nobody tells the account owner.
- Temporary passwords never expire. There is no guardian-facing "I can't sign in" path.
- There is no guardian channel. Email is off without a provider (`config/deployment_safety.py:31-42`);
  Telegram is operator-only (`config/telegram_alerts.py:1-5`); WhatsApp is staff-sent ASSIST only and SMS
  is not built (ADR 0015). Guardian phone and email are optional and unverified (`core/models.py:532-533`).
- ADR 0013 froze "no self-service password recovery" and rejected phone or email as login because it
  "would create a reset channel the institution does not operate". Self-service recovery reverses that and
  must amend ADR 0013.
- Option B §9.3 says a self-service design opens only when the sign-in failure rate G ≥ 20% **and** the
  office confirms resets are a recurring burden. Measurement is off by default (ADR 0027), so neither
  condition has evidence yet.
- Risk tier is Critical. Threat model: `docs/competitive-research/G06_RECOVERY_THREAT_MODEL.md`.
  Current state: `docs/competitive-research/G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md`.

## Options

Ratings: + good, ~ mixed, − poor.

| | A. Office-assisted, improved | B. Email link or code | C. SMS OTP | D. WhatsApp OTP | E. Knowledge questions | F. Printed recovery codes | G. Hybrid: guardian request + office approval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Security** | + Identity checked by a person who knows the family; risk is insider misuse (T7) | ~ Only as strong as an unverified, often shared inbox (T5, T16) | − SIM swap, interception, recycled numbers, shared phones (T3, T6) | ~ Better transport than SMS; still the phone holder (T3, T13) | − Facts known to relatives and classmates (T1, T2) | ~ Strong if kept private; a found sheet is a bearer secret | + Office still decides; the request adds a trail and rate limits |
| **Privacy** | + No new data or processor | ~ New processor; email must be verified | − New processor; number shared with carrier and gateway | − Number and timing shared with Meta and a BSP | − Stores more family facts | + No new data | + No new data if the request carries no contact details |
| **Cost** | + Staff time only | ~ Provider fee, low (to confirm) | − Per message plus DLT setup (to confirm) | − Per message plus BSP fee (to confirm) | + None | + Paper | + Staff time |
| **Operational burden** | − Each reset is a visit or call | ~ Bounce handling, email verification | − DLT registration, templates, number upkeep | − Business verification, template approval, number upkeep | ~ Reset disputes | ~ Reprints, lost sheets | ~ A queue to work, but less back-and-forth |
| **Dependency** | + None | − Email provider | − SMS gateway and DLT | − Meta and a BSP | + None | + None | + None |
| **Accessibility** | + Talk to a person in their language | − Many guardians lack or rarely check email | ~ Works on basic phones; reading a code | + Familiar app | − Literacy, recall | ~ Must keep paper safe | + A short form, then the office calls |
| **Low-literacy and shared-phone fit** | + Best | − Poor | ~ Fair, but shared phone defeats it | ~ Fair, same shared-phone flaw | − Poor | ~ Fair | + Good |
| **Fit with today's code** | + Extends `reset_guardian_password` and the slip | − Needs channel, verified email, ADR 0013 change | − Needs channel, verified phone, ADR 0013 and 0015 change | − Needs API mode (ADR 0015 Gate 4B) | − Contradicts ADR 0013 identity rule | ~ New secret type | + Extends A |
| **Verdict** | **Adopt first** | Defer | Defer | Defer | **Reject** | Defer; reconsider after A | **Adopt with A** |

Option A details: verification in person with documents, or a callback to the number already on record;
reason and method captured; a one-time temporary password printed or shown, with an expiry; forced change
at first sign-in (exists); an in-portal notice to the owner after sign-in; HISTORY audit.

## Proposed decision

**Adopt A + G now. Defer B, C, D and F. Reject E.**

1. **Improved office reset (A).** The reset form requires a verification method (the same choices as
   account creation, `core/models.py:3509-3512`) and a reason. The reset is recorded as a HISTORY event
   with actor, guardian, method and reason, and appears on the guardian profile. The temporary password
   expires (OD-G5). Sessions end and a change is forced, as today. After sign-in the guardian sees "Your
   password was reset by the school on <date>. If this was not you, contact the school."
2. **"Can't sign in?" request (G).** A public page linked from the sign-in form. The guardian types a name,
   a child's name and class, and optionally a callback number. The page always answers the same way ("The
   school will contact you using the details it already has") and never says whether an account exists.
   Nothing is reset and no message is sent. The office sees a queue, verifies by callback to the number
   **already on record** or in person, then uses the improved reset. Requests are throttled per source and
   globally, purged after a short period (OD-G4), and never logged with their contents.
3. **Channel self-service (B, C, D) is deferred** until: the product owner picks a channel (OD-G2);
   provider due diligence and legal review are done (DPDP, DLT, template approval, cost); verified contact
   data exists; ADR 0013 and ADR 0015 are amended; and the Option B §9.3 evidence or an office interview
   shows the burden is real.
4. **Knowledge-based questions are rejected.** DOB, admission number and parent names are low-entropy and
   known to relatives and classmates (threat model T1, T2).

**Rationale.** A and G remove the worst gaps (no reset record, no expiry, no guardian path, no owner
notice) with no provider, no new personal data and no new trust boundary. They keep a person in the loop,
which matters most for shared phones, low literacy and custody disputes. They also produce the evidence
(request counts, reset counts) needed to justify a channel later.

## Security requirements for any implementation

Each must have a test before merge.

| # | Requirement |
| --- | --- |
| R1 | **No account-existence leak.** Same response, status, page and close timing for known and unknown input, and for throttled requests. |
| R2 | **Entropy.** Generated with `secrets`. Temporary passwords at least the current 12 characters over 31 symbols (`core/guardian_accounts.py:63-66`). Any link token ≥128 bits. Any short code only with ≤5 attempts and expiry ≤15 minutes. |
| R3 | **Expiry.** Temporary passwords and any recovery secret expire (OD-G5). An expired temporary password fails like a wrong password. |
| R4 | **Single use.** A secret works once; issuing a new one invalidates older ones. |
| R5 | **Hashed at rest.** Secrets stored only as a hash; shown once with `no-store` (as `core/views.py:4007-4016`). |
| R6 | **Rate limits.** Per account, per hashed source (`accounts/security.py:61-63`) and global, on every public recovery endpoint. |
| R7 | **Generic responses** in the UI and messages; no "no such user" or "number not found". |
| R8 | **Session revocation.** Every reset or recovery calls `end_all_sessions()` (`accounts/models.py:54-57`); forced change after any temporary credential. |
| R9 | **Owner notification** after every reset and password change: in-portal now; on a channel when one exists. |
| R10 | **Audit events** (HISTORY class): request received (no contents), request handled or refused, reset issued (method, reason), first sign-in after reset, secret expired. Never the secret, typed values or contact data. |
| R11 | **No grant changes.** Recovery never creates, restores or alters a `GuardianStudentAccess` grant. |
| R12 | **CSRF** on every POST; `Referrer-Policy: no-referrer` on pages carrying a token. |
| R13 | **Logging hygiene.** Nothing secret or personal in logs, crash reports, Telegram alerts or usage counters (ADR 0027, Security Gate 4A). |
| R14 | **Route inventory.** New routes in `core/tests/route_permissions.json`; the public request page is the only anonymous one. |
| R15 | **Privileged logins excluded.** Keep `is_portal_manageable` (`core/guardian_accounts.py:43-60`) on every path. |

## Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-G1 | First recovery design | A only; A + G; a channel option now | A + G |
| OD-G2 | Channel for later self-service | None for now; email; SMS; WhatsApp API | None for now; revisit with evidence |
| OD-G3 | Accepted proof at the office | In person with documents only; also callback to the number on record; also "known to staff" | In person or callback to the number on record; "known to staff" only with a note |
| OD-G4 | "Can't sign in?" request page | Build; skip (office phone number on the sign-in page instead) | Build, with request contents purged after 30 days (period to confirm) |
| OD-G5 | Temporary password expiry | None (today); 7 days; 14 days; 30 days | 14 days, so slips sent home still work |
| OD-G6 | Expiry for any future link or code | 15, 30 or 60 minutes | 15 minutes for codes, 30 for links |
| OD-G7 | Who may reset | Any holder of `reset_guardian_password`; named staff only; two-person approval | Named staff only; two-person approval as a later option |
| OD-G8 | Reset event class | Keep ROUTINE (365 days); make HISTORY (permanent) | HISTORY, as for account creation |
| OD-G9 | Owner notice before a channel exists | In-portal notice after sign-in; none | In-portal notice |
| OD-G10 | Collect verified contact data now | No; yes, with verified-at fields and recorded consent | No, until OD-G2 picks a channel |
| OD-G11 | Legal and provider review | Before any channel work; skip | Before any channel work |
| OD-G12 | Amend ADR 0013 | Narrow amendment for A + G only; full rewrite later | Narrow amendment if A + G need it (expiry and reset fields do not change the "no self-service" rule; the request page does not reset anything) |

## Consequences

- No provider, cost or new contact data. The office keeps doing resets, with a better record and fewer
  wasted visits.
- A model change is likely: a temporary-password issue time on `User`, reset method and reason, and a
  request model for G. Each needs its own migration and a spec at Critical tier.
- Moving `PASSWORD_RESET_BY_ADMIN` to HISTORY changes `SecurityEvent.ROUTINE_TYPES`; existing events keep
  their class.
- Guardians still cannot recover alone at night or on holidays. That stays true until a channel decision.
- The never-signed-in list (`docs/competitive-research/G06_NEVER_SIGNED_IN_SPEC.md`) does not depend on
  this ADR and can proceed at High tier.

## What would make this acceptable

1. The product owner records OD-G1 to OD-G12.
2. The threat model is reviewed by someone other than its author, and its top five residual risks are
   accepted in writing.
3. A security-focused review of the spec that follows, in addition to the normal review
   (`IMPLEMENTATION_WORKFLOW.md` §3, Critical).
4. A migration and data-recovery plan, and a staged rollout with a tested rollback.
5. For any channel option later: written provider due diligence and legal confirmation of the items marked
   "to confirm" in the threat model §6.

## Related

ADR 0013, ADR 0014, ADR 0015, ADR 0024, ADR 0027; `docs/competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md`
§9.3; `docs/competitive-research/PACKAGE_C_CLOSEOUT.md` §7.
