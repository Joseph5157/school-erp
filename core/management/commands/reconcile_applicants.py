"""Report (and optionally fix) Applicants that disagree with their Student.

Every real path creates a Student only from an ACCEPTED Applicant, but old
demo data may have a Student next to a PENDING or REJECTED Applicant. Dry run
by default; `--apply` marks PENDING ones ACCEPTED. REJECTED ones are only
reported unless `--include-rejected` is also given.
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import Applicant, reconcile_applicant


class Command(BaseCommand):
    help = (
        "List Applicants that are not ACCEPTED but have a Student. Dry run unless "
        "--apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Reconcile PENDING applicants."
        )
        parser.add_argument(
            "--include-rejected",
            action="store_true",
            help="With --apply, also reconcile REJECTED applicants (keeps the old reason).",
        )

    def _safe(self, text):
        """Make text printable on a non-UTF-8 console (replace unencodable characters)."""
        encoding = getattr(self.stdout._out, "encoding", None) or "utf-8"
        return str(text).encode(encoding, "replace").decode(encoding)

    def _table(self, applicants):
        write = self.stdout.write
        write(f"{'Applicant':>9}  {'Name':<30}  {'Status':<9}  {'Student':>7}  Student status")
        for applicant in applicants:
            student = applicant.student
            write(
                f"{applicant.pk:>9}  {self._safe(applicant.full_name[:30]):<30}  "
                f"{applicant.admission_status:<9}  {student.pk:>7}  {student.status}"
            )

    def _mismatched(self, status):
        return list(
            Applicant.objects.filter(admission_status=status, student__isnull=False)
            .select_related("student")
            .order_by("pk")
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        include_rejected = options["include_rejected"]
        write = self.stdout.write
        pending = self._mismatched(Applicant.AdmissionStatus.PENDING)
        rejected = self._mismatched(Applicant.AdmissionStatus.REJECTED)
        found = len(pending) + len(rejected)

        write("Applicants that are not accepted but have a Student record")
        if pending:
            self._table(pending)
        if rejected:
            write("")
            write("Rejected applicants with a student - not changed"
                  if not (apply and include_rejected)
                  else "Rejected applicants with a student")
            self._table(rejected)
        if not found:
            write("None found.")

        reconciled = 0
        failed = 0
        if apply:
            targets = pending + (rejected if include_rejected else [])
            # One transaction per applicant (inside reconcile_applicant): a
            # failure on one row never rolls back or blocks the others.
            for applicant in targets:
                try:
                    if reconcile_applicant(applicant, include_rejected=include_rejected):
                        reconciled += 1
                except Exception as error:  # noqa: BLE001 - report and continue
                    failed += 1
                    message = getattr(error, "messages", [str(error)])[0]
                    write(f"FAILED: {applicant.pk} {self._safe(applicant.full_name)}: {message}")
        reported_only = len(rejected) if not (apply and include_rejected) else 0

        write("")
        if not apply:
            write("Dry run: nothing was changed. Use --apply to reconcile.")
        elif reconciled == 0:
            write("Nothing to reconcile; no changes were made.")
        write(
            f"Found: {found}  Reconciled: {reconciled}  Reported only: {reported_only}"
            f"  Failed: {failed}"
        )
        if failed:
            raise CommandError(f"{failed} applicant(s) could not be reconciled.")
