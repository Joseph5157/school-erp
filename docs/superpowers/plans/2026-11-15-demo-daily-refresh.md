# Demo School Daily Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A guarded, idempotent `refresh_demo_school` management command that keeps the staging demo school current every day (attendance, today's registers, open marks work, recent notices).

**Architecture:** Logic lives in a new module `core/demo_refresh.py` as small functions that take `today` explicitly and write only through domain methods; the command `core/management/commands/refresh_demo_school.py` is a thin wrapper that checks the guard, runs each step in its own transaction, reports, and exits non-zero if any step failed. Deterministic pseudo-randomness comes from hashing (student id, date).

**Tech Stack:** Django management command, Django `TestCase`, existing domain methods in `core/models.py` and `core/announcements.py`.

**Spec:** `docs/superpowers/specs/2026-11-15-demo-daily-refresh-design.md`

## Global Constraints

- Command name `refresh_demo_school`; env guard `EVERCLASS_DEMO_SCHOOL=1`; requires user `DEMO_ADMIN_USERNAME` (`core.management.commands.seed_demo`, value `demo_admin`); exactly one `AcademicYear`.
- Today outside the year → print a notice, exit 0, write nothing.
- All writes through domain methods: `AttendanceRegister(...).full_clean(); save()`, `register.capture(enrollment=, status=, absence_note=)`, `register.submit(actor=)`, `Assessment(...).full_clean(); save()`, `core.announcements.publish(title=, body=, audience=Announcement.Audience.ALL, actor=)`. No `bulk_create`, no queryset `update()` on these models, no deletes.
- Demo teacher username `srinivas.reddy` (constant `DEMO_TEACHER_USERNAME`); their class-teacher Sections stay NOT TAKEN today.
- Open assessment: name `"Unit Test N"`, `maximum_marks=Decimal(25)`, `pass_mark=Decimal(9)`, N = next unused number for (offering, section, term).
- Notice posted only when the newest non-withdrawn announcement is older than 7 days.
- Absent entries always have a non-empty note.
- Each step, and each backfilled day, in its own `transaction.atomic()`.
- All user-facing text English, ASCII.
- Tests pass `today` explicitly to `core.demo_refresh` functions. If a test must patch `business_today`, patch it on the command module, not `core.models` (repo note on parallel date capture).

## Review Focus

1. A non-instructional day (weekend or a `SchoolCalendarDay` holiday) must get no register, in backfill and for today. → Task 2 tests `test_backfill_skips_non_instructional_days`, `test_today_skipped_when_not_instructional`.
2. A Section with no class teacher on that date must still be submitted (fallback actor `demo_admin`). → Task 2 `test_submitter_falls_back_to_demo_admin`.
3. A register the presenter started today (DRAFT, any Section) must be left exactly as is. → Task 2 `test_today_leaves_started_register_alone`.
4. No current Term must skip the assessments step without error. → Task 3 `test_no_current_term_skips`.
5. A failure in one step must not stop later steps, and the command exits non-zero. → Task 4 `test_step_failure_does_not_stop_others`.

---

## File Structure

- Create `core/demo_refresh.py` — guard, attendance (drafts, backfill, today), open assessments, notices, realism helpers.
- Create `core/management/commands/refresh_demo_school.py` — CLI wrapper, per-step isolation, summary output.
- Create `core/tests/test_demo_refresh.py` — all tests; `setUpTestData` seeds via `seed_school_demo` + `seed_school_demo_results` + `seed_school_demo_extras` exactly as `core/tests/test_seed_school_demo_extras.py` does.
- Modify `README.md` — short ops section (Task 4).

Test helper (define once at the top of the test module):

```python
def last_instructional_day(year, on_or_before):
    day = on_or_before
    while not year.is_instructional_day(day):
        day -= datetime.timedelta(days=1)
    return day
```

Use `today = last_instructional_day(year, business_today())` wherever a test needs an instructional "today" (domain methods refuse future dates).

---

### Task 1: Guard and realism helpers

**Files:**
- Create: `core/demo_refresh.py`
- Test: `core/tests/test_demo_refresh.py`

**Interfaces:**
- Produces:
  - `DEMO_TEACHER_USERNAME = "srinivas.reddy"`, `ENV_FLAG = "EVERCLASS_DEMO_SCHOOL"`
  - `class NotInSeason(Exception)` — today outside the year.
  - `check_guard(today: date) -> tuple[User, AcademicYear]` — raises `CommandError` (env flag not `"1"`, no `demo_admin`, not exactly one year); raises `NotInSeason` when `today` outside `[year.start_date, year.end_date]`.
  - `is_absent(student_id: int, section_id: int, day: date) -> bool`
  - `absence_note(student_id: int, day: date) -> str` — never empty.

- [ ] **Step 1: Write failing tests**

```python
class GuardTests(TestCase):  # seeded school
    def test_refuses_without_env_flag(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": ""}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_refuses_without_demo_admin(self):
        get_user_model().objects.filter(username="demo_admin").update(username="someone_else")
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(CommandError):
                demo_refresh.check_guard(business_today())

    def test_out_of_season(self):
        year = AcademicYear.objects.get()
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            with self.assertRaises(demo_refresh.NotInSeason):
                demo_refresh.check_guard(year.end_date + datetime.timedelta(days=1))

    def test_passes_and_returns_admin_and_year(self):
        with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
            admin, year = demo_refresh.check_guard(business_today())
        self.assertEqual(admin.username, "demo_admin")

class RealismTests(SimpleTestCase):
    def test_deterministic(self):
        d = datetime.date(2026, 11, 2)
        self.assertEqual(demo_refresh.is_absent(5, 1, d), demo_refresh.is_absent(5, 1, d))

    def test_rates_are_believable(self):
        days = [datetime.date(2026, 7, 1) + datetime.timedelta(days=i) for i in range(120)]
        rates = [sum(demo_refresh.is_absent(s, 1, d) for d in days) / len(days) for s in range(1, 111)]
        self.assertTrue(0.02 <= sum(rates) / len(rates) <= 0.08)
        self.assertGreaterEqual(sum(r >= 0.09 for r in rates), 3)   # some frequent absentees
        self.assertLess(max(rates), 0.25)

    def test_note_never_empty(self):
        self.assertTrue(all(demo_refresh.absence_note(s, datetime.date(2026, 8, d))
                            for s in range(50) for d in range(1, 29)))
```

- [ ] **Step 2: Run, expect failure** — `python manage.py test core.tests.test_demo_refresh -v 2` → ImportError.
- [ ] **Step 3: Implement** in `core/demo_refresh.py`. Randomness from `hashlib.sha256(f"{a}:{b}:{c}".encode())` → float in [0,1). Per-student tendency: ~90% of students 0.02–0.05, ~10% 0.10–0.15 (bucket from hash of student id); per-Section offset ±0.01. Notes: `"Fever", "Family function", "Doctor's appointment", "Cold and cough", "Travelling with family"`.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(demo): guard and attendance realism helpers for demo refresh`

---

### Task 2: Attendance — finish drafts, backfill, today

**Files:**
- Modify: `core/demo_refresh.py`
- Test: `core/tests/test_demo_refresh.py`

**Interfaces:**
- Consumes: `is_absent`, `absence_note` (Task 1).
- Produces:
  - `finish_old_drafts(year, today, fallback_actor) -> int` — DRAFT registers dated `< today`: capture every not-yet-captured eligible enrollment, submit. Returns count.
  - `backfill_attendance(year, today, fallback_actor, since: date | None = None) -> int` — for each instructional day in `[max(since or year.start_date, year.start_date), today)`, each Section with no register that day: create, capture all eligible, submit. One `transaction.atomic()` per day. Returns registers created.
  - `prepare_today(year, today, fallback_actor) -> int` — if `today` instructional: for each Section except `DEMO_TEACHER_USERNAME`'s class-teacher Sections on `today`, and with no register yet today, create/capture/submit. Existing registers today (any status) untouched. Returns count.
  - Private `_submitter(section, day, fallback_actor)` — the Section's class teacher on `day` (the on-date filter on `SectionClassTeacherQuerySet`, `core/models.py:2499`), else `fallback_actor`.
  - Private `_fill_and_submit(register, actor)` — shared by all three.

- [ ] **Step 1: Write failing tests** (`AttendanceRefreshTests`, seeded school, `admin` = demo_admin)

```python
def test_finishes_old_drafts_without_losing_entries(self):
    # DRAFT register on an earlier instructional day with one captured entry
    demo_refresh.finish_old_drafts(year, today, admin)
    register.refresh_from_db()
    self.assertEqual(register.status, "SUBMITTED")
    self.assertEqual(register.entries.count(), len(register.eligible_enrollments()))
    # the originally captured entry keeps its status

def test_backfill_fills_every_section_every_instructional_day(self):
    since = today - datetime.timedelta(days=21)
    demo_refresh.backfill_attendance(year, today, admin, since=since)
    # for each instructional day in [since, today):
    #   SUBMITTED register count for that date == Section.objects.count()

def test_backfill_skips_non_instructional_days(self):
    # add a SchoolCalendarDay holiday on a weekday in range (domain path) first; range covers a weekend
    # assert no register on those dates

def test_backfill_is_idempotent(self):
    demo_refresh.backfill_attendance(year, today, admin, since=since)
    self.assertEqual(demo_refresh.backfill_attendance(year, today, admin, since=since), 0)

def test_submitter_is_class_teacher(self): ...      # submitted_by == that Section's class teacher
def test_submitter_falls_back_to_demo_admin(self): ...  # Section with no class teacher on that day → admin
def test_absent_entries_have_notes(self): ...       # every ABSENT entry created has absence_note != ""

def test_today_keeps_demo_teacher_sections_open(self):
    demo_refresh.prepare_today(year, today, admin)
    # demo teacher's class-teacher Sections: no register, or DRAFT; every other Section: SUBMITTED

def test_today_leaves_started_register_alone(self):
    # DRAFT register today for a non-demo Section with 1 entry
    demo_refresh.prepare_today(year, today, admin)
    # still DRAFT, still 1 entry

def test_today_skipped_when_not_instructional(self):
    self.assertEqual(demo_refresh.prepare_today(year, a_saturday_before_today_in_year, admin), 0)
```

Note: `seed_school_demo_results` already submits today's registers (except one Section) when seeding on an instructional day, and the base seeder makes the last 10 instructional days. Choose test dates so the assertions are honest (e.g. a `today` earlier than the seeded window, where nothing exists yet). Never delete registers to make room.

- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the three functions and two helpers.
- [ ] **Step 4: Run** `python manage.py test core.tests.test_demo_refresh -v 2` → pass.
- [ ] **Step 5: Commit** `feat(demo): attendance backfill and today's registers for demo refresh`

---

### Task 3: Open assessments and recent notices

**Files:**
- Modify: `core/demo_refresh.py`
- Test: `core/tests/test_demo_refresh.py`

**Interfaces:**
- Produces:
  - `current_term(year, today) -> AcademicTerm | None` — the Term whose dates contain `today`.
  - `ensure_open_assessments(year, today) -> int` — no current Term → 0. For each `AssessmentTeacherAssignment`: if no DRAFT `Assessment` for (offering, section, term), create `"Unit Test N"` (N = 1 + highest N among existing `"Unit Test <int>"` names for that triple, else 1), date = latest weekday `<= today` and `>= term.start_date`, max 25, pass 9. Returns count created.
  - `NOTICE_POOL: list[tuple[str, str]]` — 8 ASCII (title, body) generic notices: PTM, sports day, fee reminder, holiday, exam timetable, science fair, library week, uniform reminder.
  - `post_notice_if_stale(actor, now: datetime) -> Announcement | None` — newest non-withdrawn announcement's `published_at` older than 7 days (or none exists) → publish the pool entry after the one whose title matches the newest (start of pool if no match); else None.

- [ ] **Step 1: Write failing tests**

```python
def test_creates_one_open_unit_test_per_assignment(self):
    n = demo_refresh.ensure_open_assessments(year, today)
    self.assertEqual(n, AssessmentTeacherAssignment.objects.count())
    a = Assessment.objects.filter(term=term2, status="DRAFT").first()
    self.assertEqual((a.name, a.maximum_marks, a.pass_mark), ("Unit Test 1", Decimal(25), Decimal(9)))

def test_reuses_existing_open_assessment(self):
    demo_refresh.ensure_open_assessments(year, today)
    self.assertEqual(demo_refresh.ensure_open_assessments(year, today), 0)

def test_next_number_after_finalized(self):
    # finalize one "Unit Test 1" through the domain path (results as assigned teacher, finalize as admin)
    demo_refresh.ensure_open_assessments(year, today)
    # that triple now has a DRAFT "Unit Test 2"

def test_no_current_term_skips(self):
    with mock.patch.object(demo_refresh, "current_term", return_value=None):
        self.assertEqual(demo_refresh.ensure_open_assessments(year, today), 0)

def test_notice_posted_when_stale(self):
    now = Announcement.objects.latest("published_at").published_at + datetime.timedelta(days=8)
    a = demo_refresh.post_notice_if_stale(admin, now)
    self.assertEqual(a.audience, Announcement.Audience.ALL)

def test_no_notice_when_recent(self):
    now = Announcement.objects.latest("published_at").published_at + datetime.timedelta(days=3)
    self.assertIsNone(demo_refresh.post_notice_if_stale(admin, now))

def test_pool_cycles(self): ...   # two stale posts give two different titles, consecutive in NOTICE_POOL
```

Note: `term2` here means `current_term(year, today)`; if the chosen `today` is in Term 1, that Term has finalized Unit Test 1 and Half-Yearly, so N starts at 2. Write the assertions from the chosen date.

- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** `publish()` stamps `published_at` itself; `now` is only for the staleness check.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(demo): open unit tests and rotating notices for demo refresh`

---

### Task 4: The command, step isolation, ops note

**Files:**
- Create: `core/management/commands/refresh_demo_school.py`
- Modify: `README.md` — short "Demo school refresh" section: what it does; env flag; cron start command `sh -c "python manage.py expire_import_batches && python manage.py refresh_demo_school"`; one-off run `sh -c "EVERCLASS_DEMO_SCHOOL=1 python manage.py refresh_demo_school"`; reseed or rollover needed before 1 Apr 2027.
- Test: `core/tests/test_demo_refresh.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: `Command` with option `--since YYYY-MM-DD` (passed to `backfill_attendance`). `today = business_today()` read once (imported into the command module). Order: `finish_old_drafts`, `backfill_attendance`, `prepare_today`, `ensure_open_assessments`, `post_notice_if_stale(admin, timezone.now())`. `NotInSeason` → write a line containing "outside" and return. Each step wrapped in `try/except Exception`: record the step name, continue; after all steps, if any failed raise `CommandError` naming them. One summary line per step (e.g. `backfill: 312 registers`).

- [ ] **Step 1: Write failing tests**

```python
def test_command_refuses_without_flag(self):
    with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": ""}):
        with self.assertRaises(CommandError):
            call_command("refresh_demo_school", stdout=io.StringIO())

def test_command_runs_and_is_idempotent(self):
    since = str(today - datetime.timedelta(days=14))
    with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}):
        call_command("refresh_demo_school", since=since, stdout=io.StringIO())
        counts = (AttendanceRegister.objects.count(), Assessment.objects.count(), Announcement.objects.count())
        call_command("refresh_demo_school", since=since, stdout=io.StringIO())
    self.assertEqual(counts, (AttendanceRegister.objects.count(), Assessment.objects.count(),
                              Announcement.objects.count()))

def test_step_failure_does_not_stop_others(self):
    with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}), \
         mock.patch.object(demo_refresh, "backfill_attendance", side_effect=RuntimeError("boom")):
        with self.assertRaisesMessage(CommandError, "backfill"):
            call_command("refresh_demo_school", stdout=io.StringIO())
    self.assertTrue(Assessment.objects.filter(status="DRAFT").exists())  # later step still ran

def test_out_of_season_exits_cleanly(self):
    end = AcademicYear.objects.get().end_date
    with mock.patch.dict(os.environ, {"EVERCLASS_DEMO_SCHOOL": "1"}), \
         mock.patch("core.management.commands.refresh_demo_school.business_today",
                    return_value=end + datetime.timedelta(days=1)):
        out = io.StringIO()
        call_command("refresh_demo_school", stdout=out)
    self.assertIn("outside", out.getvalue())
```

The command must call `demo_refresh.backfill_attendance` through the module (not `from ... import`) so the patch in `test_step_failure_does_not_stop_others` takes effect.

- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the command and README section.
- [ ] **Step 4: Run** `python manage.py test core.tests.test_demo_refresh core.tests.test_seed_demo core.tests.test_seed_school_demo core.tests.test_seed_school_demo_extras -v 1` → all pass.
- [ ] **Step 5: Commit** `feat(demo): refresh_demo_school command`

---

## After the tasks (not code)

- Push, open the PR, run the PR reviewer subagent and report a verdict table (repo practice).
- After the user merges and it deploys: one-off run on staging, re-walk staging, then, only on the user's word, set `EVERCLASS_DEMO_SCHOOL=1` on `school-erp-cron` and change its start command.
