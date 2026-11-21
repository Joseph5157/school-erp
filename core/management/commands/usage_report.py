"""Weekly usage evidence for operators, run on the server (ADR 0027; spec sections 6.1 and 9).

There is no web page, route or Django admin entry for usage counters: this command, run from a
server shell, is the only way to read them (OD-B8). Output goes to stdout only, as text or
`--format csv`; no file is kept.

Counts are events, not people, grouped by ISO week. Any cell from 1 to 4 prints as `<5` after every
filter and grouping, and a second cell is hidden (`*`) wherever a printed total or split could
otherwise reveal a hidden one (core.usage_evidence). Section 9 review triggers are printed only for
an unfiltered report of at least 4 weeks; below its minimum denominator a figure is `n/a`, which is
neither met nor missed. A trigger opens a design gate only; it never approves a build.
"""

import csv

from django.core.management.base import BaseCommand

from core import usage, usage_evidence
from core.models import UsageCounter


class Command(BaseCommand):
    help = "Print aggregate usage evidence by ISO week, hiding small cells."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=4, choices=range(1, 27),
                            metavar="1-26", help="Number of ISO weeks, ending this week.")
        parser.add_argument("--area", choices=usage.AREAS)
        parser.add_argument("--workflow", choices=usage.WORKFLOWS)
        parser.add_argument("--device", choices=usage.DEVICES)
        parser.add_argument("--format", choices=("text", "csv"), default="text")

    def handle(self, *args, **options):
        today = usage.business_today()
        rows = UsageCounter.objects.all()
        filters = {f: options[f] for f in ("area", "workflow", "device") if options[f]}
        if filters:
            rows = rows.filter(**filters)
        try:
            report = usage_evidence.build_report(rows, today=today, weeks=options["weeks"],
                                                 filtered=bool(filters))
        except usage_evidence.ProtectionError:
            # Fails closed: print nothing rather than a figure that could reveal a small cell.
            self.stderr.write("The report could not be printed without revealing a cell under "
                              f"{usage_evidence.MIN_CELL}. Try more weeks or fewer filters.")
            return
        lines = list(usage_evidence.render(report))
        stale = usage.stale_rows_exist(today)
        if options["format"] == "csv":
            writer = csv.writer(self.stdout, lineterminator="\n")
            writer.writerow(["section", "period", "item", "value"])
            if stale:
                writer.writerow(["warning", "", "rows older than the 180-day retention cutoff",
                                 ""])
            for section, period, item, value, _ in lines:
                if section:
                    writer.writerow([section, period, item, value])
            return
        if stale:
            self.stdout.write(
                "Warning: some rows are older than the 180-day retention cutoff. Check that the "
                "daily purge_usage_counters cron step exists and succeeds."
            )
        shown = ", ".join(f"{k} {v}" for k, v in filters.items()) or "none"
        self.stdout.write(
            f"Usage evidence, ISO weeks from {report.start.isoformat()} ({options['weeks']} "
            f"weeks). Filters: {shown}. Counts are events, not people. Cells under "
            f"{usage_evidence.MIN_CELL} are shown as <{usage_evidence.MIN_CELL}; * marks a cell "
            "hidden so that a total cannot reveal a small one, and may be any value. Missing "
            "lines are zero."
        )
        if not report.weeks:
            self.stdout.write("No counts in this period.")
        for *_, text in lines:
            if text is not None:
                self.stdout.write(text)
        if filters:
            self.stdout.write("\nSection 9 review triggers are printed only for an unfiltered "
                              "report.")
        elif options["weeks"] < usage_evidence.WINDOW_WEEKS:
            self.stdout.write("\nSection 9 review triggers: the window needs at least 4 weeks.")
