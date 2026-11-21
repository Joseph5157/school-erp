"""Weekly usage counts for operators, run on the server (ADR 0027, Option B2 foundation).

There is no web page, route or Django admin entry for usage counters: this command, run from a
server shell, is the only way to read them (OD-B8). Counts are grouped by ISO week and any cell
under 5 is printed as "<5" after every filter and grouping (OD-B12). Output goes to stdout only.

B3 extends this report with the workflow sections, ratios and CSV output of spec section 6.1.
This foundation deliberately prints no totals or subtotals, so no hidden cell can be recovered by
subtraction. Any total added later must first apply complementary suppression (spec 6.1): hide a
second contributing cell, or omit the total.
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand

from core import usage
from core.models import UsageCounter

MIN_CELL = 5


def cell(value):
    return str(value) if value >= MIN_CELL else f"<{MIN_CELL}"


class Command(BaseCommand):
    help = "Print aggregate usage counts by ISO week, hiding any cell under 5."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=4, choices=range(1, 27),
                            metavar="1-26", help="Number of ISO weeks, ending this week.")
        parser.add_argument("--area", choices=usage.AREAS)
        parser.add_argument("--workflow", choices=usage.WORKFLOWS)
        parser.add_argument("--device", choices=usage.DEVICES)

    def handle(self, *args, **options):
        today = usage.business_today()
        if usage.stale_rows_exist(today):
            self.stdout.write(
                "Warning: some rows are older than the 180-day retention cutoff. Check that the "
                "daily purge_usage_counters cron step exists and succeeds."
            )
        monday = today - timedelta(days=today.weekday())
        start = monday - timedelta(weeks=options["weeks"] - 1)
        rows = UsageCounter.objects.filter(day__gte=start, day__lte=today)
        for field in ("area", "workflow", "device"):
            if options[field]:
                rows = rows.filter(**{field: options[field]})

        weeks = defaultdict(lambda: defaultdict(int))
        for day, workflow, step, count in rows.values_list("day", "workflow", "step", "count"):
            year, week, _ = day.isocalendar()
            weeks[(year, week)][(workflow, step)] += count

        self.stdout.write(f"Usage counts, ISO weeks from {start.isoformat()}. "
                          f"Cells under {MIN_CELL} are shown as <{MIN_CELL}.")
        if not weeks:
            self.stdout.write("No counts in this period.")
        for (year, week) in sorted(weeks):
            self.stdout.write(f"\n{year}-W{week:02d}")
            for (workflow, step), count in sorted(weeks[(year, week)].items()):
                self.stdout.write(f"  {workflow:<24} {step:<24} {cell(count)}")
