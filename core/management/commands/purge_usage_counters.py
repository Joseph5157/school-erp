"""Delete usage counters past the 180-day retention (ADR 0027, Option B2).

Run daily on the cron service as its own step, whether or not measurement is switched on, so
switching measurement off never strands old rows. Idempotent; needs no setting; prints only the
number of rows deleted.
"""

from django.core.management.base import BaseCommand

from core import usage


class Command(BaseCommand):
    help = "Delete usage counter rows older than the 180-day retention window."

    def handle(self, *args, **options):
        deleted = usage.purge()
        self.stdout.write(f"Deleted {deleted} usage counter rows.")
