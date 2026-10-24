# Flaky test: `core.tests.test_u4_3a_subject_order` under `--parallel 4`

Test-only fix. No production code, migration, constraint or Guardian ordering rule changed.

## Symptom

`core.tests.test_u4_3a_subject_order` errored intermittently under `manage.py test --parallel 4` on
PostgreSQL (a different test each time) with

    IntegrityError: duplicate key value violates unique constraint "subjectoffering_unique_year_grade_order"
    DETAIL: Key (academic_year_id, class_grade_id, display_order)=(1, 1, 102) already exists.

It passed alone and in serial runs.

## Root cause

The `OrderFixture.order()` helper moved the offerings out of the way with a single statement:

    UPDATE ... SET display_order = display_order + 100

`subjectoffering_unique_year_grade_order` is a plain (non-deferrable) unique constraint, so PostgreSQL
checks it row by row, in the order it visits the rows. After a first `order()` call, the one subject
not named in the mapping is left at 102. A second `order()` call shifts every row by +100, so the row
at 2 wants to become 102. It collides if, and only if, that row is visited before the row already at
102 has moved to 202.

The visit order is the physical heap/plan order, which depends on tuple placement and on which tests
ran before in the same worker database. `--parallel 4` changes how test classes are partitioned
across workers, so the failure moved between tests and only appeared under parallel runs.

It is **not** a shared-identifier, cross-worker, or test-isolation problem. Each parallel worker has
its own cloned database and each test is wrapped in its own transaction. The collision is entirely
inside one statement in one transaction.

## Fix

`core/tests/test_u4_3a_subject_order.py`, helper only: shift by the current maximum instead of a
constant:

    shift = max(display_order)           # over the offerings being moved
    UPDATE ... SET display_order = display_order + shift

Every new value is then strictly greater than every old value (old values are >= 1), so no row can
collide with any other whatever order PostgreSQL visits them in. The production constraint is
unchanged, no retries were added, and the final mapping writes are unchanged.

## Regression test

`OrderHelperTests.test_reordering_twice_is_safe_when_the_unmentioned_row_is_visited_last` calls
`order()` twice, rewrites the left-over row's tuple and disables index/bitmap scans for the
transaction (`SET LOCAL`) so the left-over row is visited after the row that wants its value. It
makes the previously random failure deterministic.

## Verification

Commands (Postgres env vars loaded from the Windows user scope, `.venv` Python):

    # control: old "+ 100" helper with the new regression test
    python manage.py test core.tests.test_u4_3a_subject_order.OrderHelperTests --noinput
    # fixed
    python manage.py test core.tests.test_u4_3a_subject_order --noinput
    python manage.py test core.tests.test_u4_3a_subject_order --parallel 4 --noinput   # x10
    python manage.py test --parallel 4 --noinput                                       # full, x3

Results:

| Run | Result |
|---|---|
| Control: old `+ 100` helper + new regression test | `IntegrityError ... Key (1, 1, 102) already exists`, FAILED (errors=1) |
| Fixed, module, serial | 21 tests OK |
| Fixed, module, `--parallel 4` x10 | 10/10 OK (21 tests each) |
| Fixed, full suite, `--parallel 4` x3 | 3/3 OK, 2509 tests each (2508 before + 1 new) |

Date: 2026-10-24, Postgres 18, local `school_erp` environment.
