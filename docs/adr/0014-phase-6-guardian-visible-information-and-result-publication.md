# 0014. Phase 6 guardian-visible information and explicit result publication

## Status

Accepted (2026-10-11, Phase 6 planning PR #34) — implemented in Phase 6
(tag `phase-6-complete`).
Planning: `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md` (decisions P7–P12, OD-1,
OD-2).

## Context

Phase 2 attendance and Phase 4 results are already historically correct and
have clear official states (SUBMITTED registers, FINALIZED assessments).
Phase 4 explicitly excluded publication to parents and students (ADR 0009).
A guardian is outside the school: anything shown in the portal is effectively
released to the family, must not change silently afterwards, and must remain
reconstructable exactly as released.

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

**Profile (P7, OD-1)**
- Shown: Student name; admission number; Academic Year, Class/Grade, Section
  and roll number of the current placement; current enrolment status where
  appropriate. Admission number or roll number is simply omitted when not
  recorded.
- `Student.admission_number`: optional, administrator-entered, never
  generated; stored trimmed; unique across the school among recorded values,
  compared case-insensitively.
- `AcademicEnrollment.roll_number`: optional, administrator-entered positive
  integer, never generated; belongs to the yearly placement, not the Student;
  unique within the same Academic Year and Section among recorded values.
  A roll number is therefore not reused in that Section and Year, even after
  its holder leaves, and a Student placed again in the same Section and Year
  receives a new one.
- Never shown: date of birth, Student phone or email, internal database
  identifiers, other guardians or their contact details, staff-only notes,
  medical, disciplinary or other sensitive internal information.
- No editing and no change requests (later communication work).

**Attendance (P8)**
- Only SUBMITTED attendance: per-date status (the current, corrected value)
  and the Phase 2 summary/percentage.
- Never: DRAFT registers, absence notes, correction history, who corrected,
  or any teacher-only information. Missing attendance is not shown as absent.

**Results (P9, OD-2, revision 1)**
- Finalization (ADR 0009) and guardian publication are separate actions.
  Finalized results are not visible to guardians until published.
- Publication is per Student per Term and is allowed at any time, including
  before the Term ends. Only FINALIZED results can be published. A Term
  remark has no finalized state of its own; it is published as it stands at
  confirmation, and the administrator's confirmation of the preview is its
  approval.
- Publication runs per Term and Section through a preview that lists, for
  each Student, exactly which results and which remark would be published,
  or why the Student is skipped. Nothing is written before confirmation;
  confirming the same preview twice publishes nothing new.
- A Student whose Term record is incomplete (an assessment on their roster
  in that Term is not yet FINALIZED) is flagged in the preview and excluded
  unless the administrator individually includes them. An included
  incomplete publication is marked partial and the guardian sees that some
  results for the Term are not yet published. Ambiguous records (no single
  Term placement) are never publishable.
- Each publication version stores an immutable snapshot of exactly the
  fields the guardian report card displays: per result — Subject name,
  assessment name and date, maximum marks, pass mark, status, score,
  percentage, grade label and pass/fail label; the remark text; and the
  Term, Academic Year, Class/Grade and Section labels of the card header.
  Each snapshot row keeps a reference to its source result for
  traceability. No other Student data is copied.
- The portal renders a Term only from the current version's snapshot, and
  only while that version is PUBLISHED and a fingerprint of the live source
  values still equals the fingerprint stored with the snapshot.
- When a published result or remark is corrected or removed, that Student's
  current Term publication becomes STALE in the same transaction and
  disappears from the portal until an administrator reviews and
  republishes. Information already released is never silently changed, and
  every earlier version remains reconstructable from its snapshot.
- Publication history: every version (PUBLISHED, STALE, SUPERSEDED,
  WITHDRAWN) and its snapshot is permanent, never deleted or rewritten, and
  outside routine-event retention. Guardians see only the current PUBLISHED
  version with a matching fingerprint — never earlier, stale, superseded or
  withdrawn versions, version numbers or change history. Administrators can
  view every version exactly as released, with its publisher and every
  status change, actor and reason.

**Exclusions (P10–P12)**
- Fees: excluded while Phase 3 is deferred — no models, placeholders or
  navigation.
- Announcements: moved to Phase 7 Communication.
- Downloads/PDF: excluded; on-screen report cards only; no PDF library.

## Alternatives rejected

- Visible on FINALIZED: makes finalization a release decision and lets
  corrections change released information silently.
- Pointers and fingerprints only: cannot reconstruct what an earlier version
  showed once its source results have been corrected.
- Copying whole result or Student records: duplicates unrelated data.
- Showing live values after correction with a "changed" marker: still a
  silent change from the guardian's point of view.
- Publication only after Term end: delays legitimate mid-Term release and is
  replaced by the incomplete-record flag.

## Consequences

- Phase 4's "no publication" exclusion is replaced by this ADR for guardians
  only; Student publication remains future work (Phase 6B).
- Result corrections (ADR 0009) and Term remark edits (ADR 0012 D10) gain a
  side effect: they mark the affected Student's current Term publication
  stale.
- Phase 1 Student data gains an optional admission number; Phase 2
  enrollment data gains an optional roll number.

## Related

- `docs/PHASE_6_GUARDIAN_PORTAL_PLAN.md`
- `docs/adr/0006-academic-enrollment-effective-dating.md`
- `docs/adr/0007-phase-2-attendance-model.md`
- `docs/adr/0009-phase-4-assessment-and-results-model.md`
- `docs/adr/0012-phase-5-teacher-attendance-and-student-access.md`
- `docs/adr/0013-phase-6-guardian-accounts-and-access-grants.md`
