# Demo school daily refresh — design

Date: 2026-11-15. Status: draft for approval.

## Intent

We are reaching out to schools and giving live demos of Everclass ERP from the
seeded demo school on Railway staging (see `seed_school_demo`,
`seed_school_demo_results`, `seed_school_demo_extras`). Demos happen on any day,
with no fixed date, so the demo must look current whenever it is opened.

A walk of staging on 2026-11-15 (Sunday) found the data frozen at the seeding
date:

- Attendance is complete only up to 26 Oct. The Overview heatmap shows two empty
  weeks; a parent sees "11 of 11 recorded days" for the whole year.
- Four half-filled DRAFT registers left over from testing (27 Oct, 28 Oct,
  6 Nov) sit at the top of the Attendance list.
- All four announcements are dated 26 Oct.
- Every assessment is finalized, so a teacher has nothing to enter marks for
  ("Marks: Nothing waiting") and live mark entry cannot be shown.

A few polish issues were also found (below, separate PR).

## Goals

1. Opening the demo on any day shows attendance complete up to yesterday, a
   believable "today" state, recent notices, and open marks work for teachers.
2. It stays that way without anyone remembering to run anything.
3. The presenter can take a register live and enter marks live during a demo.

## Non-goals

- A separate demo server (option B). Chosen against for now on cost; moving later
  stays easy because everything is a management command.
- Self-serve demo logins for prospects.
- Report-card totals, overall % or rank. ADR 0009 forbids them; unchanged. The
  demo script will cover how to answer the question.
- Resetting what a presenter did during a demo (marks they typed stay).
- Academic-year rollover. The demo year ends 31 Mar 2027; from then the command
  exits quietly. The user will plan rollover (and other open questions) later;
  a reseed or rollover must happen before 1 Apr 2027.

## Anti-goals (would make this a failure even if it runs)

- The refresh ever touching a real school's data. It must refuse to run anywhere
  except the demo school.
- Writing rows directly and bypassing domain rules. All writes go through the same
  model methods the app uses (`AttendanceRegister.capture/submit`,
  `Assessment` creation via `full_clean`, the announcement publish path), like the
  existing seeders.
- Data that looks generated: every student 100%, every class identical, notices
  all with one timestamp.

## Approaches considered

- **A. Daily auto-refresh on staging (chosen by the user).** A new idempotent
  command, run on a schedule on the existing Railway cron service. Cheapest;
  demos still share the server with development.
- **B. Separate demo server + daily refresh.** Isolated from merges and test data,
  but roughly doubles Railway cost. Deferred.
- **C. Manual refresh before each demo.** Free but easy to forget; stale data in
  front of a school is the problem we are solving.

## Design

### New command: `refresh_demo_school`

`core/management/commands/refresh_demo_school.py`. Idempotent: running it twice
in a row changes nothing the second time (except what the clock moved).

**Safety guard.** Refuses with `CommandError` unless all hold:
- environment variable `EVERCLASS_DEMO_SCHOOL=1` is set (set only on staging);
- the `demo_admin` user (`DEMO_ADMIN_USERNAME`) exists;
- exactly one `AcademicYear` exists and `business_today()` falls inside it
  (otherwise it prints a notice and exits 0 so the cron run is not a failure).

Steps, in this order. Each step (and each backfilled day) runs in its own
transaction, so a failure in one step is reported (non-zero exit after the other
steps have run) without undoing or blocking the others, and the first large
backfill never holds long locks on the shared staging database:

1. **Finish leftover drafts.** Every DRAFT register dated before today gets its
   missing entries captured and is submitted. (No deletes.)
2. **Backfill attendance.** For every instructional day
   (`AcademicYear.is_instructional_day`) from the year's start up to yesterday,
   every Section without a register gets one, fully captured and submitted. The
   year starts 1 June, so the first run covers about 115 school days
   (~2,300 registers, one transaction per day); later runs only fill gaps.
   Registers are submitted by the Section's class teacher (believable name).
   `submit()` stamps the real time, so backfilled registers show a late submit
   time; accepted, because this happens once, and from then on each day's
   registers are submitted on the same day by the morning run.
3. **Today.** If today is instructional, submit today's register for every Section
   *except* the demo teacher's class-teacher Sections (`srinivas.reddy`: currently
   Grade 1-A and Grade 4-A), which are left NOT TAKEN so the presenter can take
   one live and the Overview shows a realistic "still to take" item. Registers the
   presenter already started today are left alone.
4. **Open marks work.** Ensure each teacher assignment has one non-finalized
   assessment in the current Term: if none exists, create "Unit Test N"
   (max 25, pass 9), where N is the next unused number for that subject, Section
   and Term (Term 2 currently has none, so the first is "Unit Test 1"; if a
   presenter's admin finalizes it, the next run opens "Unit Test 2", avoiding the
   unique-name clash). Dated the most recent weekday on or before today inside the
   Term, with no results entered. Never finalizes it.
5. **Recent notices.** If the newest live announcement is older than 7 days,
   publish the next one from a fixed rotating pool (about 8 generic school
   notices: PTM, sports day, fee reminder, holiday, exam timetable, etc.),
   audience ALL, published by `demo_admin`. The pool cycles, so notices always
   have spread-out dates.

**Realism of generated attendance.** Each student gets a stable absence tendency
derived from their id (most around 3–5%, a handful at 10–15% so "Frequent
absentees" and "Students needing attention" stay populated); Sections differ
slightly; Absent entries get a non-empty note (the existing `ABSENCE_NOTES` has an
empty string; use only its non-empty values, optionally extended). Randomness
is seeded from (student id, date) so re-runs and backfills are deterministic.

Prints a short summary (registers finished, created, today submitted, assessments
opened, notice posted).

### Schedule

Reuse the existing Railway cron service `school-erp-cron` (no new service). Change
its start command to run both jobs, keeping the current one first:

`sh -c "python manage.py expire_import_batches && python manage.py refresh_demo_school"`

Keep the schedule `0 */6 * * *` (UTC). The 00:00 UTC run is 05:30 IST, before
school, so each school day starts with yesterday complete and today set up; later
runs are no-ops. Add `EVERCLASS_DEMO_SCHOOL=1` to the cron service's variables
(staging only). These Railway changes are made only on the user's go-ahead, after
the command is merged and deployed.

### One-time run

After deploy, run it once by hand on staging, setting the variable for that one
command because the web service does not have it
(`railway ssh ... sh -c "EVERCLASS_DEMO_SCHOOL=1 python manage.py refresh_demo_school"`),
and re-walk staging to confirm.

### Separate small polish PR (independent)

- Guardian portal page title still says "School ERP"
  (`templates/portal/base.html:6`) → Everclass ERP.
- Section filter blank option `---------` → "All sections" on Attendance,
  Assessments and Missing attendance; drop trailing colons on those labels.
- Report-card marks show `85.00 / 100.00` → `85 / 100` (keep `.5` when present).
- Report card lists Half-Yearly above Unit Test 1 → oldest first.

### Demo script (after both land)

A one-page script for whoever gives the demo: admin on laptop → teacher on phone
→ parent on phone → close; ~15 minutes, with logins and answers to likely
questions (totals/rank, data separation, phone install).

## Tests

- Guard: refuses without the env var; refuses without `demo_admin`.
- Idempotency: second run creates nothing.
- Backfill: no instructional day before today is left without a SUBMITTED
  register per Section; non-instructional days get none.
- Leftover DRAFT before today ends SUBMITTED with no entries lost.
- Today: demo teacher's Sections are not taken; a register the presenter started
  today is untouched.
- Exactly one open assessment per assignment after the run; an existing open one
  is reused, not duplicated.
- Notice posted only when the newest is older than 7 days.
Use `business_today` patching per the repo's existing test patterns.

## Left to the builder

- Exact notice pool wording, absence-rate numbers, how the stable per-student
  tendency is derived.
- Whether steps share helpers with `seed_school_demo_results` or the command
  stands alone (prefer reuse where it is clean).
- Performance approach for the first backfill (~110 students × ~90 days); bulk
  paths are fine only if they still go through the domain rules.
