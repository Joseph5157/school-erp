"""Expire stale bulk-import batches and clear their parsed rows (ADR 0017).

Parsed personal data in a pending import batch is kept for 24 hours at most.
The web views expire stale batches when an import page is used, but a batch
nobody revisits would otherwise keep its rows; run this on a schedule
(for example hourly) so retention does not depend on page visits.
"""

from django.core.management.base import BaseCommand

from core import imports


class Command(BaseCommand):
    help = "Expire pending import batches older than 24 hours and clear their parsed rows."

    def handle(self, *args, **options):
        expired = imports.expire_stale_batches()
        self.stdout.write(f"Expired {expired} import batch(es).")
