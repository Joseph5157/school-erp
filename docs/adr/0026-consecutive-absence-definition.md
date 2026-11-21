# ADR 0026: Consecutive-absence definition ("absent N school days in a row")

Status: accepted, 2026-11-21 (Option A2; spec `docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md`, section 5).

## Context
Schools want to spot a student who has stopped coming before it becomes a long absence. The existing "frequent absentees" count (3 or more absent days in a period) does not say whether the days were in a row. A run must follow the attendance rules already in place: a missing or DRAFT register is never an absence (ADR 0007), only instructional days count (ADR 0008), and a teacher sees only their own Section and dates (ADR 0012 D8/D9, Security Gate 3A).

## Decision
- **Eligible day:** an instructional day of the enrollment's academic year, on or before the business date, on which the student has an enrollment effective in that year.
- **Status of an eligible day:** ABSENT or PRESENT when a SUBMITTED register holds an entry for that enrollment (the `reports.reportable_entries` rule). Otherwise UNKNOWN: no register, a DRAFT, or a submitted register without the student's entry.
- **Anchor:** the latest eligible day on or before today. If that is today and today is UNKNOWN, the anchor moves to the previous eligible day. This grace is for today only.
- **Counting backwards from the anchor:** non-instructional days are skipped. ABSENT adds a day. PRESENT, UNKNOWN, a day with no enrollment, the year start and (in the teacher view) the assignment start each stop the count. Back-to-back enrollments in the same year continue the run; a new academic year always stops it. Future days are never considered.
- **Lookback:** at most 30 days are counted. "30+" is shown only when an earlier eligible day exists past that boundary. At the year start or an enrollment gap the exact 30 is shown.
- **"At least":** a run stopped by UNKNOWN, the lookback limit or the teacher's assignment start is shown as "at least N". The assignment start is never an exact boundary, because the student may have been absent before it.
- **Flagged:** `days >= threshold`; 3 by default, and the administrator report offers 3, 5 or 10.
- **Who sees it:** administrators with `core.view_attendanceentry` get the "Absent in a row" report. A class teacher gets a card on My Home for their own Section and year, clipped to their assignment. A Section that is ambiguous today (two effective class-teacher assignments across years, or enrollments in two years) is left out of the card. Subject teachers and guardians see nothing.
- **Freshness:** computed on every request from the current entry status and calendar, with a fixed number of queries. Never cached.

## Consequences
- A correction (`AttendanceEntry.record_status_change`) or a calendar change alters the next result straight away.
- The existing "frequent absentees" count is unchanged and answers a different question.
- No schema change, migration or new permission.
