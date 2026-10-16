"""Phase 3C (audit F08): applicant/student state reconciliation, guard and visibility."""

from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from core.models import Applicant, Student, reconcile_applicant

Status = Applicant.AdmissionStatus


def make_mismatch(name="Mismatch Child", status=Status.PENDING, reason=""):
    """A Student next to a non-accepted Applicant, bypassing the insert guard."""
    applicant = Applicant.objects.create(full_name=name)
    Student.objects.bulk_create([Student(applicant=applicant, full_name=name)])
    Applicant.objects.filter(pk=applicant.pk).update(
        admission_status=status, admission_decision_reason=reason
    )
    applicant.refresh_from_db()
    return applicant, Student.objects.get(applicant=applicant)


def accepted_applicant(name="Fine Child"):
    applicant = Applicant.objects.create(full_name=name)
    applicant.record_admission_decision(Status.ACCEPTED)
    return applicant


def snapshot():
    return (
        list(Applicant.objects.order_by("pk").values()),
        list(Student.objects.order_by("pk").values()),
    )


def run(*args):
    out = StringIO()
    call_command("reconcile_applicants", *args, stdout=out)
    return out.getvalue()


class ReconcileFunctionTests(TestCase):
    def test_reconciles_pending_with_student(self):
        applicant, student = make_mismatch()
        self.assertTrue(reconcile_applicant(applicant))
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.ACCEPTED)
        self.assertEqual(applicant.admission_decided_at, student.created_at)
        self.assertEqual(
            applicant.admission_decision_reason,
            "Reconciled: Student record already existed.",
        )

    def test_second_call_changes_nothing(self):
        applicant, _ = make_mismatch()
        reconcile_applicant(applicant)
        before = snapshot()
        self.assertFalse(reconcile_applicant(applicant))
        self.assertEqual(snapshot(), before)

    def test_without_student_or_accepted_untouched(self):
        lonely = Applicant.objects.create(full_name="Lonely")
        fine = accepted_applicant()
        before = snapshot()
        self.assertFalse(reconcile_applicant(lonely))
        self.assertFalse(reconcile_applicant(fine))
        self.assertEqual(snapshot(), before)

    def test_rejected_needs_flag_and_keeps_old_reason(self):
        applicant, _ = make_mismatch(status=Status.REJECTED, reason="No places")
        self.assertFalse(reconcile_applicant(applicant))
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.REJECTED)
        self.assertTrue(reconcile_applicant(applicant, include_rejected=True))
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.ACCEPTED)
        self.assertEqual(
            applicant.admission_decision_reason,
            "Reconciled: Student record already existed (was rejected: No places).",
        )


class ReconcileCommandTests(TestCase):
    def test_dry_run_lists_and_changes_nothing(self):
        pending, student = make_mismatch("Pending Pat")
        make_mismatch("Rejected Rae", status=Status.REJECTED, reason="Full")
        before = snapshot()
        output = run()
        self.assertEqual(snapshot(), before)
        self.assertIn("Pending Pat", output)
        self.assertIn("Rejected Rae", output)
        self.assertIn("Dry run", output)
        self.assertIn("Rejected applicants with a student — not changed", output)
        self.assertIn(f"{pending.pk}", output)
        self.assertIn(f"{student.pk}", output)

    def test_apply_reconciles_pending_and_is_idempotent(self):
        applicant, student = make_mismatch()
        output = run("--apply")
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.ACCEPTED)
        self.assertEqual(applicant.admission_decided_at, student.created_at)
        self.assertIn("reconciled: 1", output.lower())
        before = snapshot()
        again = run("--apply")
        self.assertEqual(snapshot(), before)
        self.assertIn("nothing to reconcile", again.lower())

    def test_accepted_and_studentless_untouched(self):
        accepted_applicant()
        Applicant.objects.create(full_name="No Student")
        make_mismatch()
        untouched = list(
            Applicant.objects.exclude(student__isnull=False)
            .order_by("pk")
            .values()
        )
        fine = Applicant.objects.get(full_name="Fine Child")
        fine_values = Applicant.objects.filter(pk=fine.pk).values().get()
        run("--apply")
        self.assertEqual(
            list(Applicant.objects.exclude(student__isnull=False).order_by("pk").values()),
            untouched,
        )
        self.assertEqual(Applicant.objects.filter(pk=fine.pk).values().get(), fine_values)

    def test_rejected_only_reported_by_default(self):
        applicant, _ = make_mismatch(status=Status.REJECTED, reason="Full")
        output = run("--apply")
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.REJECTED)
        self.assertEqual(applicant.admission_decision_reason, "Full")
        self.assertIn("reported only: 1", output.lower())

    def test_include_rejected_reconciles_with_old_reason(self):
        applicant, _ = make_mismatch(status=Status.REJECTED, reason="Full")
        run("--apply", "--include-rejected")
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, Status.ACCEPTED)
        self.assertIn("was rejected: Full", applicant.admission_decision_reason)


class StudentInsertGuardTests(TestCase):
    def test_pending_and_rejected_applicants_blocked(self):
        for status in (Status.PENDING, Status.REJECTED):
            applicant = Applicant.objects.create(full_name=f"A {status}")
            if status == Status.REJECTED:
                applicant.record_admission_decision(status, "No")
            with self.assertRaisesMessage(
                ValidationError, "A Student can only be created for an accepted Applicant."
            ):
                Student.objects.create(applicant=applicant, full_name="X")
        self.assertFalse(Student.objects.exists())

    def test_accepted_applicant_allowed(self):
        applicant = accepted_applicant()
        Student.objects.create(applicant=applicant, full_name="Fine Child")
        self.assertEqual(Student.objects.count(), 1)

    def test_progress_to_student_still_works(self):
        student = accepted_applicant().progress_to_student()
        self.assertTrue(student.pk)

    def test_existing_mismatched_student_can_still_be_saved(self):
        _, student = make_mismatch()
        student.record_status_change(Student.Status.INACTIVE, reason="Left school")
        student.full_name = "Renamed"
        student.save()
        student.refresh_from_db()
        self.assertEqual(student.full_name, "Renamed")
        self.assertEqual(student.status, Student.Status.INACTIVE)
