# ADR 0029: Guardian account recovery

Status: **Accepted**, 2026-11-23. The product owner approved OD-G1 to OD-G16 as recommended and
accepted the threat model's residual risks (see "Recorded decisions"). History: proposed in G-06 Phase 0;
r2 applied the independent security review of PR #301 (findings F1–F13); r3 applied its re-check
(N-A to N-D). Accepting this ADR approves the **design**, not code: each implementation still needs its
own Critical-tier spec and the remaining gates in "What would make this acceptable" (items 3–6).

## Context

- Guardians sign in with an office-created username and a temporary password handed over on a printed
  slip, then must change it (ADR 0013; `core/guardian_accounts.py:125-147`; `accounts/middleware.py:177-180`).
- A guardian who forgets the password, or loses the slip, has one path: the office reset
  (`core/views.py:4138-4163`). It ends all sessions and forces a change (`core/guardian_accounts.py:223-235`),
  but records no reason or verification method, is a ROUTINE event purged after 365 days
  (`accounts/models.py:102-111`), does not clear a sign-in lockout, and nobody tells the account owner.
- Temporary passwords never expire, and the forced change accepts the temporary password as the new one
  (`config/settings.py:177-190` has no rule against it). There is no guardian-facing "I can't sign in" path.
- `Guardian.phone` can be edited by anyone with `core.change_guardian` and no event is recorded
  (`core/views.py:3521-3532`; `accounts/models.py:72-100` has no contact-change event type).
- There is no guardian channel. Email is off without a provider (`config/deployment_safety.py:31-42`);
  Telegram is operator-only (`config/telegram_alerts.py:1-5`); WhatsApp is staff-sent ASSIST only and SMS
  is not built (ADR 0015). Guardian phone and email are optional and unverified (`core/models.py:532-533`).
- ADR 0013 froze "no self-service password recovery" and rejected phone or email as login because it
  "would create a reset channel the institution does not operate". Self-service recovery reverses that and
  must amend ADR 0013.
- Option B §9.3 says a self-service design opens only when the sign-in failure rate G ≥ 20% **and** the
  office confirms resets are a recurring burden. Measurement is off by default (ADR 0027), so neither
  condition has evidence yet.
- Risk tier is Critical. Threat model: `docs/competitive-research/G06_RECOVERY_THREAT_MODEL.md` (T1–T23).
  Current state: `docs/competitive-research/G06_PHASE0_GUARDIAN_ACCESS_RESEARCH.md`.

## Options

Ratings: + good, ~ mixed, − poor.

| | A. Office-assisted, improved | B. Email link or code | C. SMS OTP | D. WhatsApp OTP | E. Knowledge questions | F. Printed recovery codes | G. Hybrid: guardian request + office approval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Security** | + Identity checked by a person; risks are insider misuse and a tampered phone record (T7, T16) | ~ Only as strong as an unverified, often shared inbox (T5, T16) | − SIM swap, interception, recycled numbers, shared phones (T3, T6) | ~ Better transport than SMS; still the phone holder (T3, T13) | − Facts known to relatives and classmates (T1, T2) | ~ Strong if kept private; a found sheet is a bearer secret | ~ Office still decides; adds an anonymous public form to defend (T18) |
| **Privacy** | + No new data or processor | ~ New processor; email must be verified | − New processor; number shared with carrier and gateway | − Number and timing shared with Meta and a BSP | − Stores more family facts | + No new data | ~ New, short-lived personal data: a guardian name, a child's name and class from an unverified source; capped, purged, no phone field (R21) |
| **Cost** | + Staff time only | ~ Provider fee, low (to confirm) | − Per message plus DLT setup (to confirm) | − Per message plus BSP fee (to confirm) | + None | + Paper | + Staff time |
| **Operational burden** | − Each reset is a visit or call | ~ Bounce handling, email verification | − DLT registration, templates, number upkeep | − Business verification, template approval, number upkeep | ~ Reset disputes | ~ Reprints, lost sheets | ~ A queue to work and to defend from spam |
| **Dependency** | + None | − Email provider | − SMS gateway and DLT | − Meta and a BSP | + None | + None | + None |
| **Accessibility** | + Talk to a person in their language | − Many guardians lack or rarely check email | ~ Works on basic phones; reading a code | + Familiar app | − Literacy, recall | ~ Must keep paper safe | + Three short fields, then the office calls |
| **Low-literacy and shared-phone fit** | + Best | − Poor | ~ Fair, but shared phone defeats it | ~ Fair, same shared-phone flaw | − Poor | ~ Fair | + Good |
| **Fit with today's code** | + Extends `reset_guardian_password` and the slip | − Needs channel, verified email, ADR 0013 change | − Needs channel, verified phone, ADR 0013 and 0015 change | − Needs API mode (ADR 0015 Gate 4B) | − Contradicts ADR 0013 identity rule | ~ New secret type | + Extends A |
| **Verdict** | **Adopt first** | Defer | Defer | Defer | **Reject** | Defer; reconsider after A | **Adopt with A** |

Option A details: verification in person with documents; a callback to the number already on the
Guardian record only confirms the request and books the visit (Appendix A); method stored as a choice; a
one-time temporary password printed or shown **in person**, with a short expiry; forced change at first sign-in (exists); HISTORY audit shown on the guardian profile.

## Decision

**Adopt A + G now. Defer B, C, D and F. Reject E.**

1. **Improved office reset (A).** The reset form requires a verification method as a choice (OD-G16). The
   reset is a HISTORY event with actor, guardian and method, shown on the guardian profile. If the
   Guardian's phone changed in the last N days (OD-G13) the form warns and accepts only an in-person check.
   The reset clears any sign-in lockout. The temporary password expires (OD-G5). Sessions end and a change
   is forced, as today. After sign-in the guardian sees "Your password was reset by the school on <date>".
   That notice is **informational only**: it is not detection, because an attacker who used the temporary
   password has already changed it and the owner cannot sign in to see it (threat model T10).
2. **"Can't sign in?" request (G).** A public page linked from the sign-in form with three short fields
   (R21). It has **no phone field**: a number typed by an anonymous person is unverified and possibly the
   attacker's, and calling it would hand the reset path to whoever typed it or make staff call a stranger.
   The office already holds the number on the Guardian record; a guardian with no usable number on record
   comes in person. The page always answers the same way ("The school will contact you using the details
   it already has"), does no account lookup and never says whether an account exists. Nothing is reset
   and no message is sent. Staff match requests to records offline, call the number on record to confirm
   the request and book a visit, and reset when the guardian comes in. Requests are throttled and purged (OD-G4).
3. **Channel self-service (B, C, D) is deferred** until: the product owner picks a channel (OD-G2);
   provider due diligence and legal review are done (DPDP, DLT, template approval, cost); verified contact
   data exists; ADR 0013 and ADR 0015 are amended; and the Option B §9.3 evidence or an office interview
   shows the burden is real. Until then **there is no owner notification**, and T10 stays High.
4. **Knowledge-based questions are rejected.** DOB, admission number and parent names are low-entropy and
   known to relatives and classmates (threat model T1, T2).

**Rationale.** A and G close the clearest gaps (no reset record, no expiry, no guardian path, an
unaudited phone number) with no provider and no new trust boundary beyond a small public form. They keep a
person in the loop, which matters most for shared phones, low literacy and custody disputes. They also
produce the evidence (request and reset counts) needed to justify a channel later. They do not solve owner
notification; only a channel does.

## Security requirements for any implementation

Each must have a test before merge. "Live bug" marks a defect in today's code that a separate small fix PR
will address, outside this ADR.

| # | Requirement |
| --- | --- |
| R1 | **No account-existence leak.** For known, unknown and throttled input: the same response body, status and page, and the same database queries and writes. Tests assert query and write counts and the response, not wall-clock timing. **Request page:** equality means the same response and the same lookups, which are none (R21). Writes may differ: a request refused by a cap (R6) is not stored. That reveals nothing about accounts, because the cap ignores what was typed. |
| R2 | **Entropy.** Generated with `secrets`. Temporary passwords at least the current 12 characters over 31 symbols (`core/guardian_accounts.py:63-66`). Any link token ≥128 bits. Any short code only with ≤5 attempts and expiry ≤15 minutes. |
| R3 | **Expiry of temporary passwords.** Separate limits for office resets and account-creation slips (OD-G5). Store the issue time on the login. Enforce in `NormalizedUsernameBackend.authenticate` (`accounts/backends.py:15-33`) after the password check: an expired temporary password returns `None`, so the sign-in form shows the same generic error (`accounts/forms.py:10`). Backfill: logins with `must_change_password` set and no issue time get the deploy time as issue time and the **creation** window (14 days), including temporary passwords from resets issued before deploy, since their kind is not recorded; logins without the flag need nothing. **Deploy step:** before the expiry ships, the office runs the never-signed-in list (both views) and re-issues or contacts families as needed, so slips that expire 14 days after deploy do not lock families out silently. Callback-delivered passwords, if OD-G3 allows them, expire after 1 hour. |
| R4 | **Single use.** A secret works once; issuing a new one invalidates older ones. |
| R5 | **Hashed at rest.** Secrets stored only as a hash; shown once with `no-store` (as `core/views.py:4007-4016`). |
| R6 | **Rate limits, starting numbers to tune on staging (OD-G15), each with a test.** Sign-in per account: keep Rule A (5 per username + source in 15 min) and Rule B (20 per username in 15 min) (`accounts/security.py:26-29`). Sign-in per hashed source across usernames: 30 failures in 15 min. Request page per hashed source: 5 per hour. Request page global: 200 per day (a starting value and a deliberate trade-off, because a flood can push real requests out). Past the cap the page shows the same generic answer and stores nothing. The office queue then shows a notice with the number of requests dropped that day, an aggregate count only, with a test that a capped request is not stored, the response is unchanged and the count rises. Trade-off: mobile carriers put many people behind few addresses, so per-source caps can block a whole carrier area; keep them loose and watch them. Per-source limits depend on `DJANGO_TRUSTED_PROXIES` (`config/settings.py:163`): if the proxy is not configured, every request looks like the proxy's address and a per-source cap becomes a global one. |
| R7 | **Generic responses** in the UI and messages; no "no such user" or "number not found". |
| R8 | **Session revocation.** Every reset or recovery calls `end_all_sessions()` (`accounts/models.py:54-57`); forced change after any temporary credential. |
| R9 | **Reset notice is informational.** After sign-in, a guardian whose password was reset sees the date. It is not owner notification and must not be described as detection. Owner notification needs a channel (OD-G2). |
| R10 | **Audit events** (HISTORY class): request handled or refused, reset issued (method as a choice), first sign-in after reset, temporary password expired, lockout cleared by reset, contact field changed. Never the secret, typed values or contact data. Any note is short and structured (OD-G16), contains no personal data beyond what the record already holds, and lives where a retention rule can delete it. |
| R11 | **No grant changes.** Recovery never creates, restores or alters a `GuardianStudentAccess` grant. |
| R12 | **CSRF and clickjacking.** Already handled site-wide: `X_FRAME_OPTIONS = "DENY"` (`config/settings.py:158`), `CsrfViewMiddleware` (`config/settings.py:58`) and the custom failure view (`config/settings.py:144`). Tests pin both on every new route. `Referrer-Policy: no-referrer` on any page carrying a token. |
| R13 | **Logging hygiene.** Nothing secret or personal in logs, crash reports, Telegram alerts or usage counters (ADR 0027, Security Gate 4A), with a test on the reset and request paths. |
| R14 | **Route inventory.** New routes in `core/tests/route_permissions.json`; the request page is the only anonymous one. |
| R15 | **Privileged logins excluded.** Keep `is_portal_manageable` (`core/guardian_accounts.py:43-60`) on every path. |
| R16 | **Reset clears lockout.** The office reset calls `security.clear_lockout` and records `LOCKOUT_CLEARED`. Today it does not (`core/guardian_accounts.py:223-235`). **Live bug.** |
| R17 | **Contact changes are audited at one choke point.** Every write of `Guardian.phone` or `Guardian.email` goes through one service function (or the model's `save`) that writes a HISTORY event naming the field and actor, never the old or new value. No such event type exists today (`accounts/models.py:72-100`). Known write paths: `guardian_create` and `guardian_edit` through `GuardianForm` (`core/views.py:3498-3532`); bulk import, which creates guardians with a phone and email (`core/imports.py:779-781`, columns at `:80-85`); the demo seed commands (`core/management/commands/seed_demo.py:199`, `seed_school_demo.py:175`). The Django admin does not register `Guardian` today (`core/admin.py:1-7`); the implementing spec re-checks this and a test keeps it unregistered. Tests cover the form path and the import path. |
| R18 | **Callback rules.** Staff call only the number on the Guardian record, using Appendix A. By default a callback only confirms the request and books an office visit; the temporary password is handed over in person (OD-G3). If that number changed in the last N days (OD-G13), the reset form warns and accepts only an in-person check. "Known to staff" is not accepted as proof. |
| R19 | **New password differs from the current one.** The password change rejects a new password equal to the current one, with a test. Today `PasswordChangeForm` allows it. **Live bug.** |
| R20 | **Future codes.** Cap issues per account per day (start: 3). Re-issuing does not grant extra attempts: the attempt count is per account per window, not per code. |
| R21 | **Request page fields and purge.** Exactly three fields: guardian's full name (max 100 characters), child's full name (max 100), child's class and section (max 30). No phone, email or free-text message. Stored with a received time and the hashed source only. The submit path does **no account lookup**; staff match requests offline. Rendered to staff with Django autoescape, pinned by a test that submitted HTML shows as text. A daily purge job deletes requests older than OD-G4's period, with an expiry test. |
| R22 | **Request queue permission.** A dedicated permission (OD-G14); teachers and guardians get 403; queue previews show no child data beyond what the guardian list already shows to that viewer (`core/views.py:3390-3398`). |

## Decisions for the product owner

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD-G1 | First recovery design | A only; A + G; a channel option now | A + G |
| OD-G2 | Channel for later self-service | None for now; email; SMS; WhatsApp API | None for now; revisit with evidence. Note: without one there is no owner notification (T10 High). |
| OD-G3 | How identity is checked and how the temporary password is delivered | (a) In person with documents; the password is handed over in person. (b) A callback to the number on record confirms the request and books a visit; the password is still handed over in person. (c) Callback delivery: the password is read aloud on the callback, only with a second staff member on the call and a 1-hour expiry for that password. (d) "Known to staff". | (a) and (b). Not (c): reading a bearer secret to whoever answers a shared family number raises T1 and T13 residual risk, and is weaker than the slip's "hand it over in person". Not (d). |
| OD-G4 | "Can't sign in?" request page | Build (three fields, no phone); skip and print the office number on the sign-in page | Build, purge after 30 days (period to confirm with counsel) |
| OD-G5 | Temporary password expiry | None (today); one limit for all; separate limits | Separate: 72 hours for office resets, 14 days for account-creation slips; backfill per R3 |
| OD-G6 | Expiry for any future link or code | 15, 30 or 60 minutes | 15 minutes for codes, 30 for links |
| OD-G7 | Who may reset | Any holder of `reset_guardian_password`; named staff only; two-person approval | Named staff only; two-person approval as a later option |
| OD-G8 | Reset event class | Keep ROUTINE (365 days); make HISTORY (permanent) | HISTORY, as for account creation, subject to the DPDP retention check |
| OD-G9 | In-portal reset notice | Show (informational only); none | Show, labelled informational; it is not owner notification |
| OD-G10 | Collect verified contact data now | No; yes, with verified-at fields and recorded consent | No, until OD-G2 picks a channel |
| OD-G11 | Legal and provider review | Before any channel work; skip | Before any channel work, and before HISTORY retention of reset records |
| OD-G12 | Amend ADR 0013 | Narrow amendment for A + G only; full rewrite later | Narrow amendment if A + G need it (expiry and reset fields keep "no self-service"; the request page resets nothing) |
| OD-G13 | Phone-change window N for R18 | 14, 30 or 90 days | 30 days |
| OD-G14 | Request queue permission | Reuse `reset_guardian_password`; a dedicated permission | Dedicated: the request model's own view and change permissions, given to named staff |
| OD-G15 | Starting rate limits | Accept R6 numbers; set others | Accept R6 as starting values; tune on staging |
| OD-G16 | Reset note | Method choice only; choice plus free note; choice plus short note in a separate deletable table | Method choice only; a note only for "Other", max 100 characters, no personal data, in a separate deletable table |

### Recorded decisions (2026-11-23)

The product owner approved **every recommendation above, as written** ("approve all as recommended"):
OD-G1 to OD-G16 take the value in the Recommendation column. In particular: the A + G design, no
channel for now (OD-G2), identity by (a) in person or (b) a callback that only books a visit, never (c)
or (d) (OD-G3), and the 72-hour / 14-day temporary password expiry (OD-G5).

The product owner also accepted in writing the threat model's top residual risks under this design:
T10 High (no owner notification until a channel exists); T7, T1, T20 and T12 Medium; T13 and T22 Medium.

## Consequences

- No provider, cost or new contact channel. The office keeps doing resets, with a better record.
- Owner notification stays absent until a channel exists. That is the main residual risk (T10, High).
- Model changes are likely: a temporary-password issue time and kind on `User`, the reset method, a
  request model, and new `SecurityEvent` types. Each needs a migration and a spec at Critical tier.
- Moving `PASSWORD_RESET_BY_ADMIN` to HISTORY changes `SecurityEvent.ROUTINE_TYPES`; existing events keep
  their class.
- R16 and R19 are live bugs. A separate small fix PR addresses them; it does not wait for this ADR.
- Guardians still cannot recover alone at night or on holidays until a channel decision.
- The never-signed-in list (`docs/competitive-research/G06_NEVER_SIGNED_IN_SPEC.md`) does not depend on
  this ADR. Its reset link waits for the improved reset.

## What would make this acceptable

1. The product owner records OD-G1 to OD-G16. **Done** (2026-11-23, "Recorded decisions").
2. The threat model is reviewed by someone other than its author, and its top residual risks (T10 High;
   T7, T1, T20, T12 Medium) are accepted in writing. **Done**: independent security review on PR #301
   (two rounds), risks accepted by the product owner on 2026-11-23.
3. A security-focused review of the spec that follows, in addition to the normal review
   (`IMPLEMENTATION_WORKFLOW.md` §3, Critical).
4. A migration and data-recovery plan, and a staged rollout with a tested rollback.
5. Counsel confirms the DPDP retention and children's-data items marked "to confirm" in the threat model §6.
6. For any channel option later: written provider due diligence and legal confirmation of the provider
   items in the threat model §6.

## Appendix A: callback script

For staff verifying a guardian by phone before a reset.

1. Open the guardian's profile. If the phone number changed in the last N days (OD-G13), stop: the guardian
   must come in person.
2. Call **only** the number on the Guardian record. Never a number given in a request, by the caller, or
   by anyone else.
3. Say: "This is <name> from <school>. We received a request to help with your parent portal sign-in. Did
   you ask for this?"
4. If they did not ask, do not reset. Record "refused: not requested".
5. If they did, book a time for them to come to the office with an identity document. Do not reset during
   the call and do not read any password aloud. The reset and the slip happen at the visit (OD-G3 (a), (b)).
   Only if the owner has chosen OD-G3 (c): with a second staff member on the call, reset, read the
   temporary password to the person on the call, and set the 1-hour expiry. Never send it by message.
6. Record the outcome (visit booked, or refused). At the visit, record the method "In person, with identity
   documents"; under OD-G3 (c), record "Callback to number on record" and the second staff member. Do not write the number or personal details in any
   note.

## Related

ADR 0013, ADR 0014, ADR 0015, ADR 0024, ADR 0027; `docs/competitive-research/OPTION_B_IMPLEMENTATION_SPEC.md`
§9.3; `docs/competitive-research/PACKAGE_C_CLOSEOUT.md` §7. Implementation specs: option A
`docs/competitive-research/G06_OFFICE_RESET_SPEC.md`; option G
`docs/competitive-research/G06_SIGN_IN_HELP_SPEC.md` (draft r3).
