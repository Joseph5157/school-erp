"""Keep the staging demo school current: run once a day on a schedule.

Finishes old draft registers, backfills attendance, prepares today's
registers, keeps one open unit test per class and subject, and posts a
rotating notice. Each step runs in its own transaction; one failing step does
not stop the others, but the command exits non-zero naming the failed steps.
Refuses to run unless EVERCLASS_DEMO_SCHOOL=1 (demo environment only).
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core import demo_refresh
from core.models import business_today


class Command(BaseCommand):
    help = "Refresh the demo school's attendance, unit tests and notices up to today."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            help="Backfill attendance from this date (YYYY-MM-DD); default is the year start.",
        )

    def handle(self, *args, **options):
        since = None
        if options.get("since"):
            try:
                since = datetime.date.fromisoformat(options["since"])
            except ValueError:
                raise CommandError("--since must be a date like 2026-09-01.")
        today = business_today()
        try:
            admin, year = demo_refresh.check_guard(today)
        except demo_refresh.NotInSeason as exc:
            self.stdout.write(f"Nothing to do: {exc}")
            return

        steps = (
            ("drafts", "old drafts finished",
             lambda: demo_refresh.finish_old_drafts(year, today, admin)),
            ("backfill", "registers",
             lambda: demo_refresh.backfill_attendance(year, today, admin, since=since)),
            ("today", "registers prepared",
             lambda: demo_refresh.prepare_today(year, today, admin)),
            ("assessments", "unit tests opened",
             lambda: demo_refresh.ensure_open_assessments(year, today)),
            ("notice", "notice posted",
             lambda: 1 if demo_refresh.post_notice_if_stale(admin, timezone.now()) else 0),
        )
        failed = []
        for name, label, run in steps:
            try:
                with transaction.atomic():
                    count = run()
            except Exception as exc:  # keep going; report at the end
                failed.append(name)
                self.stderr.write(f"{name}: failed: {exc!r}")
                continue
            self.stdout.write(f"{name}: {count} {label}")
        if failed:
            raise CommandError("Failed steps: " + ", ".join(failed))
