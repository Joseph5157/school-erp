# ADR 0025: Archiving Classes/Grades and Sections

Status: accepted, 2026-11-05.

## Context
Classes/Grades and Sections are reused across years and referenced by past placements, attendance, marks and report cards, so they cannot be deleted. A school that drops a class or section had no way to stop it being offered.

## Decision
- **Archived, not deleted:** both gain `archived_at` and `archived_by`. A check constraint requires both or neither.
- **New work only:** lists for new work use `.active()`. New enrollments, registers, teacher assignments, assessments and timetable slots are also refused in `Model.clean`, for paths that do not use those lists.
- **History stays:** filters, reports and existing records keep using the whole list. Editing an existing record keeps what it already uses (`active_or`).
- **Refused while in use:** students placed in a year that has not ended, and running teacher assignments or timetable slots, must move first. The page lists them.
- **A Class/Grade with its Sections:** archiving a Class/Grade archives its active Sections at the same moment. Restoring it restores those, and leaves Sections archived earlier. An archived Class/Grade has only archived Sections, so no Section can be added or restored into one.
- **Names stay taken:** an archived name is still unique, so restore it rather than creating it again.

## Consequences
- Code offering a Class/Grade or Section for new work must use `.active()`.
- Enrolment does not take these locks, so an enrolment at the very moment of archiving could still succeed. It would show on the class page and could be moved.
- Applied imports fail validation if they name an archived record, and the year-to-year copy of teacher assignments skips archived Sections and says why.
