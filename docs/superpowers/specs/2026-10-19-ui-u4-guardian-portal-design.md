# U4 Guardian Portal — Design Freeze

**Status:** Approved design direction; implementation not started.

**Baseline:** `main` at 2d383c91eba7ced2d2b1b9c2a840a82292a5e6c2

## Goal

Redesign the existing Guardian Portal into a parent-first, child-first, calm and mobile-friendly experience while preserving all existing Phase 6 authorization, publication, attendance and read-only rules.

No new guardian domain capability is introduced by this redesign.

## Design principles

- Parent-first, child-first.
- Phone-first for guardians.
- Server-rendered Django remains authoritative.
- Read-only Guardian Portal remains read-only.
- No fake data, no inferred attendance, no fake upcoming report cards.
- "Not recorded" attendance must never imply absence.
- Published report cards remain snapshot-only.
- No totals, weighting or ranks are introduced.
- Existing Guardian authorization and access-grant boundaries remain unchanged.
- Keep the existing bottom navigation concept.
- Calm institutional visual language: off-white page, white cards, restrained green/blue washes, no gradients, no heavy shadows, 44px targets.

## 1. Guardian Home

Header:
- Guardian Portal / profile account area.
- Friendly greeting/subtitle such as "Here’s the latest for your children."

Child cards:
- One card per visible child.
- Name dominant.
- Current placement/year if available.
- Attendance summary if available.
- Latest published report card if available.
- Whole card or clear action opens the child overview.
- Missing data must be shown honestly, not as 0%.

Notices:
- Latest notices remain below child cards.
- Notices are secondary to the child summary.
- "View all notices" remains available.

## 2. Child Overview

Header:
- Back to children/home.
- Child name.
- Current Grade/Section/Academic Year summary.

Primary summary cards:
- Attendance summary.
- Latest report card summary.

Details section:
- Admission number when available.
- Academic Year.
- Class/Grade.
- Section.
- Roll number when available.
- Enrolment status.

The current plain definition-list-only presentation should be replaced with a stronger visual hierarchy.

## 3. Child Switcher

For guardians with multiple visible children:
- Child identity in the Guardian child context becomes switchable.
- Mobile: bottom-sheet style interaction.
- Desktop: compact dropdown/popover is acceptable.
- Only children already visible through the user's valid grants may appear.
- Switching changes Overview / Attendance / Reports to the selected child.

Do not create new permissions or access behavior.

## 4. Attendance

Header:
- Attendance.
- Child identity.
- Academic Year selector if multiple years exist.

Summary:
- Attendance percentage when it can be truthfully calculated.
- Present count.
- Absent count.
- Recorded school-day count.
- Explicit note that only officially recorded attendance is shown.

Month navigation:
- Previous / current / next month as applicable.

Calendar:
- Month grid.
- Present = restrained green treatment.
- Absent = restrained red treatment.
- Not recorded = neutral treatment.
- Non-school day = neutral/no-status treatment.
- Legend must explain Present / Absent / Not recorded.

Do not infer absence from missing records.

Optional detail below calendar:
- Recorded absence dates for the month if helpful and supported by current data.

## 5. Report Cards List

Replace the plain unordered list with clear term cards/rows:
- Term label.
- Academic Year.
- Published date if available from the existing snapshot/publication.
- Clear "View" affordance.
- Newest first.
- Honest empty state if no publications exist.

Do not show fake future/upcoming terms.

## 6. Individual Report Card

### Mobile

Do not force the current 7-column table.

Header:
- Term label.
- Child.
- Grade/Section/Academic Year.
- Download PDF.
- Partial-publication notice when applicable.

Content:
- Present mobile results assessment-first, not as one subject group spanning the whole report.
- Show the latest assessment first.
- Within each assessment, show subjects in the school's fixed academic order:
  - first language;
  - second language;
  - third language;
  - remaining subjects in the existing fixed school order.
- Each subject row/block shows only values already present in the published snapshot:
  - Marks.
  - Percentage when present in snapshot.
  - Grade with existing "Not graded" fallback.
  - Pass/Fail when present in snapshot.
- Do not recalculate or derive totals, weighting, averages, ranks or comparisons.

Bottom:
- Class teacher remark when present.
- Existing explanation remains: each assessment is separate; no totals, weighting or ranks.

### Desktop

Use a clean table:
- Subject.
- Assessment.
- Date.
- Marks.
- Percentage.
- Grade.
- Result.

Improve spacing/typography but do not change result calculations or publication semantics.

## 7. Navigation

Keep Guardian mobile destinations:
- Home
- Notices
- Overview
- Attendance
- Reports

Current-child destinations must remain consistent.

Do not add extra tabs during U4.

## Implementation sequence

### U4-1 — Home + Child Overview + Child Switcher
- Redesign Guardian Home child cards.
- Redesign Child Overview.
- Add safe child switcher using existing visible grants.

### U4-2 — Attendance Calendar
- Month calendar UI.
- Summary + legend.
- Year/month navigation.
- Preserve all current attendance truthfulness and access rules.

### U4-3 — Report Cards
- Redesign report-card list.
- Mobile subject blocks.
- Desktop table.
- Preserve snapshot-only semantics.

### U4-4 — Acceptance / Hardening
- 360px, 390px, 1280px.
- JS-off behavior where applicable.
- Keyboard/focus/labels.
- No horizontal page overflow.
- Authorization/access regression tests.
- Guardian with zero/one/multiple children.
- Access-under-review behavior.
- Empty attendance/report-card states.

## Out of scope

- Fees.
- Guardian timetable.
- Messaging/chat.
- New document types.
- New Guardian write actions.
- New permissions.
- New models/migrations unless an implementation blocker is discovered and separately approved.
- Any new frontend framework.

## Approval

This document freezes the approved U4 visual/interaction direction. Implementation should not expand beyond it without explicit review.
