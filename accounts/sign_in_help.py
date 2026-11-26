"""The "Can't sign in?" requests: office queue, handling and cleanup (G-06 sign-in help spec, PR 1).

There is no public page yet (spec PR 2), so nothing here collects requests. What is here:

* the open count, drop counts and expired-row check behind the sidebar badge and Overview card;
* `handle`, the one way staff record an outcome;
* `purge`, the cleanup the cron step and `--all --yes` run.

Typed values are never logged, measured or put in a URL (spec §9). Every transaction that touches
these tables takes locks in one order (spec §4.4): today's day row (the gate), other day rows,
requests, hour rows. Deletes lock with `skip_locked`, so they never wait on a row someone else
holds.
"""

from datetime import timedelta

from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone

from accounts.models import SecurityEvent, SignInHelpDay, SignInHelpRequest, SignInHelpSourceHour

RETENTION_DAYS = 30
PURGE_BATCH = 1000
# Hour rows normally wait up to one cron interval (6 hours) after their hour ends; older than a day
# means the cleanup is not running (review PR1-SR-04).
HOUR_ROW_STALE = timedelta(days=1)
OPEN = ""


class AlreadyHandled(Exception):
    """The request already has an outcome; nothing was changed."""

    def __init__(self, row):
        super().__init__("already handled")
        self.row = row


def retention_cutoff(now=None):
    """Requests received at or before this moment are past the 30-day retention."""
    return (now or timezone.now()) - timedelta(days=RETENTION_DAYS)


def hour_start(now=None):
    """The start of the current clock hour, local time (spec §3.3)."""
    return timezone.localtime(now or timezone.now()).replace(minute=0, second=0, microsecond=0)


def set_local_timeouts():
    """PostgreSQL only: limits that end with the transaction, so they cannot leak (spec §4.4)."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '2s'")
            cursor.execute("SET LOCAL statement_timeout = '5s'")


# --- what staff see ---------------------------------------------------------------------------------


def live_requests(now=None):
    """Requests inside retention. Expired rows are never shown, even before the purge runs."""
    return SignInHelpRequest.objects.filter(received_at__gt=retention_cutoff(now))


def open_requests(now=None):
    return live_requests(now).filter(outcome=OPEN)


def handled_requests(now=None):
    return live_requests(now).exclude(outcome=OPEN)


def open_count(now=None):
    """The badge and Overview number: open requests inside retention."""
    return open_requests(now).count()


def drop_counts(today=None):
    """(today, last 7 days including today): requests not saved because of limits or repeats."""
    today = today or timezone.localdate()
    by_day = dict(
        SignInHelpDay.objects.filter(day__gt=today - timedelta(days=7), day__lte=today)
        .values_list("day", "dropped")
    )
    return by_day.get(today, 0), sum(by_day.values())


def expired_rows_exist(now=None):
    """True when rows past retention are still stored, so the cleanup is not running (spec §6)."""
    now = now or timezone.now()
    return (
        SignInHelpRequest.objects.filter(received_at__lte=retention_cutoff(now)).exists()
        or SignInHelpDay.objects.filter(
            day__lt=timezone.localdate(now) - timedelta(days=RETENTION_DAYS)
        ).exists()
        or SignInHelpSourceHour.objects.filter(hour_start__lt=now - HOUR_ROW_STALE).exists()
    )


# --- handling ---------------------------------------------------------------------------------------


def handle(request_id, *, actor, outcome, now=None):
    """Record one outcome for one open request, with its event, in one transaction (spec §5.2).

    Locks only that request row, so it cannot form a lock cycle with the submit or the purge.
    Raises Http404 if the row is missing or past retention, AlreadyHandled if it already has an
    outcome (an outcome is final), and ValueError for anything but one of the five outcomes.
    """
    if outcome not in SignInHelpRequest.Outcome.values:
        raise ValueError("unknown outcome")
    now = now or timezone.now()
    with transaction.atomic():
        row = (
            SignInHelpRequest.objects.select_for_update(of=("self",))  # this one row only
            .select_related("handled_by")
            .filter(pk=request_id, received_at__gt=retention_cutoff(now))
            .first()
        )
        if row is None:
            raise Http404("No such request.")
        if row.outcome != OPEN:
            raise AlreadyHandled(row)
        row.outcome = outcome
        row.handled_at = now
        row.handled_by = actor
        row.save(update_fields=["outcome", "handled_at", "handled_by"])
        # Outcome only: no typed names, no request id, no guardian link (spec §5.4).
        SecurityEvent.record(
            SecurityEvent.EventType.SIGN_IN_HELP_HANDLED, actor=actor, detail={"outcome": outcome}
        )
    return row


# --- cleanup ----------------------------------------------------------------------------------------


def _purge_targets(now, everything):
    """(label, queryset) in the shared lock order: day rows, requests, hour rows."""
    if everything:
        return (
            ("day rows", SignInHelpDay.objects.all()),
            ("requests", SignInHelpRequest.objects.all()),
            ("hour rows", SignInHelpSourceHour.objects.all()),
        )
    today = timezone.localdate(now)
    return (
        ("day rows", SignInHelpDay.objects.filter(day__lt=today - timedelta(days=RETENTION_DAYS))),
        ("requests", SignInHelpRequest.objects.filter(received_at__lte=retention_cutoff(now))),
        ("hour rows", SignInHelpSourceHour.objects.filter(hour_start__lt=hour_start(now))),
    )


def _delete_batch(queryset, today, limit):
    """One short transaction: lock today's gate row if it exists (never create it), then lock and
    delete up to `limit` rows by pk, skipping rows another transaction holds. Returns the count."""
    with transaction.atomic():
        set_local_timeouts()
        list(SignInHelpDay.objects.select_for_update().filter(day=today).values_list("pk", flat=True))
        pks = list(
            queryset.select_for_update(skip_locked=True)
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )
        if not pks:
            return 0
        deleted, _ = queryset.model.objects.filter(pk__in=pks).delete()
        return deleted


def purge(*, everything=False, now=None, batch=PURGE_BATCH):
    """Delete rows past retention, or every row with `everything`. Returns {label: deleted}.

    A database error (a lock or statement timeout under load, say) propagates, so the command fails
    loudly. Rows locked by another transaction are skipped and left for the next run.
    """
    now = now or timezone.now()
    today = timezone.localdate(now)
    deleted = {}
    for label, queryset in _purge_targets(now, everything):
        total = 0
        while True:
            count = _delete_batch(queryset, today, batch)
            total += count
            if count < batch:
                break
        deleted[label] = total
    return deleted


def row_counts():
    """{label: rows} in the three tables. Counts only."""
    return {
        "day rows": SignInHelpDay.objects.count(),
        "requests": SignInHelpRequest.objects.count(),
        "hour rows": SignInHelpSourceHour.objects.count(),
    }
