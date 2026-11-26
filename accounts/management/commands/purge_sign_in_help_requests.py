"""Delete "Can't sign in?" rows past retention, or wipe them all (G-06 sign-in help spec §6).

    python manage.py purge_sign_in_help_requests              # the cron step
    python manage.py purge_sign_in_help_requests --all        # prints the counts, deletes nothing
    python manage.py purge_sign_in_help_requests --all --yes  # deletes every row in the three tables

Requests go 30 days after they arrive, handled or not; hour rows once their hour has ended; day rows
after 30 days. It never touches security events. It prints counts only, never a typed value, and
needs no --by: these are short-lived rows, not audit records (like purge_usage_counters).

Any database error makes it exit non-zero. `--all --yes` repeats until a pass deletes nothing and
exits non-zero if rows remain (switch the page off first when retiring the feature).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from accounts import sign_in_help

MAX_WIPE_PASSES = 20


def _summary(counts):
    return ", ".join(f"{count} {label}" for label, count in counts.items())


class Command(BaseCommand):
    help = "Delete sign-in help requests past the 30-day retention (or every row with --all --yes)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", dest="everything",
                            help="Delete every row in the three tables, not only expired ones.")
        parser.add_argument("--yes", action="store_true",
                            help="Confirm --all. Without it, --all only prints the counts.")

    def handle(self, *args, everything=False, yes=False, **options):
        if yes and not everything:
            raise CommandError("--yes only confirms --all.")
        try:
            if everything and not yes:
                self.stdout.write(f"Would delete {_summary(sign_in_help.row_counts())}. "
                                  "Nothing deleted; add --yes to delete.")
                return
            if everything:
                self._wipe()
                return
            deleted = sign_in_help.purge()
        except DatabaseError as error:  # class only: a message can quote values
            raise CommandError(f"Cleanup failed ({type(error).__name__}); run it again.") from None
        self.stdout.write(f"Deleted {_summary(deleted)}.")

    def _wipe(self):
        totals = dict.fromkeys(sign_in_help.row_counts(), 0)
        for _ in range(MAX_WIPE_PASSES):
            deleted = sign_in_help.purge(everything=True)
            for label, count in deleted.items():
                totals[label] += count
            if not any(deleted.values()):
                break
        self.stdout.write(f"Deleted {_summary(totals)}.")
        remaining = sign_in_help.row_counts()
        if any(remaining.values()):
            raise CommandError(f"Rows remain: {_summary(remaining)}. Switch the page off, then run "
                               "it again.")
        self.stdout.write("No sign-in help rows remain.")
