#!/usr/bin/env bash
# Some CI runs take 25 minutes instead of 5, with no test running any slower.
# This prints what the test processes and the database are doing during such a
# stall. It only reads, it never fails the job, and a normal run ends before it
# wakes up. Remove it once the stall is fixed.
set -u

report() {
  echo "::group::Test stall report at $(date -u +%H:%M:%S)"
  echo "--- Python stacks"
  for pid in $(pgrep -f "manage.py test"); do
    echo "--- pid $pid"
    sudo "$(command -v py-spy)" dump --pid "$pid" || true
  done
  echo "--- Database sessions"
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c \
    "SELECT pid, datname, state, wait_event_type, wait_event,
            now() - query_start AS running_for, left(query, 160) AS query
     FROM pg_stat_activity WHERE datname LIKE 'test_%' ORDER BY query_start;" || true
  echo "--- Blocked sessions"
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c \
    "SELECT pid, pg_blocking_pids(pid) AS blocked_by, left(query, 160) AS query
     FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;" || true
  echo "--- Memory and load"
  free -m || true
  uptime || true
  echo "::endgroup::"
}

for delay in "$@"; do
  sleep "$delay"
  report
done
