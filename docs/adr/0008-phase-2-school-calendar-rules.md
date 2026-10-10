# 0008. Phase 2 school calendar rules

## Status

Accepted

## Context

ADR 0007 requires a minimal Academic-Year-aware school calendar that decides
whether attendance is expected on a date, supports holidays/closures and
exceptional instructional dates such as working Saturdays, and is not a
timetable or event system. The Gate 2 plan left five operational questions
open; these were decided before implementation.

## Decision

FROZEN:

1. **Weekly pattern plus exceptions.** Each Academic Year has a weekly
   pattern. Only dates that differ from the pattern are stored, as
   SchoolCalendarDay exceptions. An exception that merely repeats the pattern
   is rejected.
2. **Weekly pattern.** Monday-Friday are instructional and Sunday is not.
   Saturday is a per-Academic-Year setting, off by default. The pattern belongs
   to the Academic Year, so one year's setting never changes another's
   history. The Saturday setting cannot change once the year has attendance
   registers, or while Saturday exceptions exist.
3. **Attendance protection.** A date cannot be made non-instructional while
   attendance exists on it. Until Gate 4 introduces SUBMITTED registers, any
   AttendanceRegister for that Academic Year and date counts; Gate 4 may narrow
   this to submitted registers only.
4. **Single-date entry.** Exceptions are recorded one date at a time in
   Phase 2. Range/bulk entry is deferred.
5. **Deletion.** An exception may be deleted only while no attendance register
   exists for that Academic Year and date. An exception's date and type are
   fixed once recorded; only its label may change. To change the type, delete
   it and record a new exception.

Lookup: `AcademicYear.is_instructional_day(date)` answers "is attendance
expected on date D for Academic Year Y?". Dates outside the year are never
instructional; an exception wins over the weekly pattern.

Calendar management (adding, relabelling and removing exceptions, and
changing the Saturday rule) is administrator-only through the shared
authorization foundation.

## Consequences

- An ordinary school year needs data entry only for holidays and working
  Saturdays.
- Attendance cannot be silently orphaned on a date later declared a holiday.
- A school that also closes on other weekdays every week, or that needs a
  different weekly pattern, would need a new decision.
- Calendar exceptions protect themselves at the application layer
  (`SchoolCalendarDay.delete()` and `clean()`); a bulk queryset delete
  bypasses that guard and must not be used for calendar data.

## Related requirements/domain decisions

- `docs/adr/0007-phase-2-attendance-model.md`
- `docs/PHASE_2_RECONCILIATION_PLAN.md` — Gate 2
- `docs/REQUIREMENTS.md` — Phase 2 scope, Attendance capture
- `docs/DOMAIN_MODEL.md` — Attendance
