# 0014. Phase 6 guardian-visible information and explicit result publication

## Status

Proposed — becomes Accepted when the Phase 6 planning PR is approved.
Planning: `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md` (decisions P7–P12).

## Context

Phase 2 attendance and Phase 4 results are already historically correct and
have clear official states (SUBMITTED registers, FINALIZED assessments).
Phase 4 explicitly excluded publication to parents and students (ADR 0009).
A guardian is outside the school: anything shown in the portal is effectively
released to the family and must not change silently afterwards.

## Decision

FROZEN once accepted:

**General**
- The Guardian Portal is read-only and lives in its own area with its own
  templates and navigation; no administrative or teacher page is reused or
  exposed (PRODUCT.md, FROZEN).
- Portal pages identify a Student through an opaque, non-sequential
  identifier tied to the access grant, never through internal database ids.
- A Student outside the guardian's active grants responds exactly like a
  Student that does not exist (404), so other families' records cannot be
  probed.

**Profile (P7)**
- Shown: Student name; the approved public Student identifier and roll
  number (see plan decision OD-1: these fields do not exist yet); Academic
  Year, Class/Grade and Section of the current placement; current enrolment
  status where appropriate.
- Never shown: date of birth, Student phone or email, internal database
  identifiers, other guardians or their contact details, staff-only notes,
  medical, disciplinary or other sensitive internal information.
- No editing and no change requests (later communication work).

**Attendance (P8)**
- Only SUBMITTED attendance: per-date status (the current, corrected value)
  and the Phase 2 summary/percentage.
- Never: DRAFT registers, absence notes, correction history, who corrected,
  or any teacher-only information. Missing attendance is not shown as absent.

**Results (P9)**
- Finalization (ADR 0009) and guardian publication are separate actions.
  Finalized results are not visible to guardians until published.
- Publication is per Student per Term, controlled by administrators, in bulk
  for a Term and Section through a preview that lists exactly which Students
  and which results and remarks would be published, and which Students are
  skipped and why. Nothing is written before confirmation; confirming the
  same preview twice publishes nothing new.
- A Student is skipped, never published silently, when their Term record is
  incomplete or ambiguous (plan, section 6).
- A published Term report card may include the class teacher's Term remark
  (ADR 0012 D10) as it stood at publication.
- Publication is a record/version that references the published results and
  remark and stores a fingerprint of their released values; result data is
  not copied. The portal shows a Term only while its current publication is
  valid and the live values still match the fingerprint.
- When a published result or remark is corrected or removed, that Student's
  Term publication becomes STALE in the same transaction and disappears from
  the portal until an administrator reviews and republishes it. Information
  already released is never silently changed. Superseded and stale versions
  are kept as history.

**Exclusions (P10–P12)**
- Fees: excluded while Phase 3 is deferred — no models, placeholders or
  navigation.
- Announcements: moved to Phase 7 Communication.
- Downloads/PDF: excluded; on-screen report cards only; no PDF library.

## Alternatives rejected

- Visible on FINALIZED: makes finalization a release decision and lets
  corrections change released information silently.
- Copying results into the publication: duplicates academic data and creates
  a second source of truth to keep consistent.
- Showing live values after correction with a "changed" marker: still a
  silent change from the guardian's point of view.

## Consequences

- Phase 4's "no publication" exclusion is replaced by this ADR for guardians
  only; Student publication remains future work (Phase 6B).
- Result corrections (ADR 0009) and Term remark edits (ADR 0012 D10) gain a
  side effect: they mark the affected Student's Term publication stale.

## Related

- `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`
- `docs/adr/0007-phase-2-attendance-model.md`
- `docs/adr/0009-phase-4-assessment-and-results-model.md`
- `docs/adr/0012-phase-5-teacher-attendance-and-student-access.md`
- `docs/adr/0013-phase-6-guardian-accounts-and-access-grants.md`
