"""Progress steps on the Import and Admissions flows."""

import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import Applicant, Student
from core.progress_steps import admission_steps, import_steps
from core.tests.test_authorization import AuthorizationClientsMixin


def states(steps):
    return [step["state"] for step in steps]


class ImportStepsTests(SimpleTestCase):
    def test_labels(self):
        self.assertEqual([s["label"] for s in import_steps()], ["Upload file", "Check preview", "Import records"])

    def test_states_follow_the_batch_status(self):
        cases = {
            None: ["current", "upcoming", "upcoming"],
            "VALIDATED": ["done", "current", "upcoming"],
            "REJECTED": ["done", "stopped", "upcoming"],
            "COMMITTED": ["done", "done", "done"],
            "DISCARDED": ["done", "done", "stopped"],
            "EXPIRED": ["done", "done", "stopped"],
            "FAILED": ["done", "done", "stopped"],
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                self.assertEqual(states(import_steps(status)), expected)

    def test_stopped_steps_say_why(self):
        self.assertEqual(import_steps("REJECTED")[1]["note"], "Has errors")
        self.assertEqual(import_steps("DISCARDED")[2]["note"], "Discarded")
        self.assertEqual(import_steps("EXPIRED")[2]["note"], "Expired")
        self.assertEqual(import_steps("FAILED")[2]["note"], "Failed")


class AdmissionStepsTests(TestCase):
    def test_states_follow_the_applicant(self):
        self.assertEqual(states(admission_steps()), ["current", "upcoming", "upcoming"])
        applicant = Applicant.objects.create(full_name="Asha Rao")
        self.assertEqual(states(admission_steps(applicant)), ["done", "current", "upcoming"])
        applicant.admission_status = "ACCEPTED"
        self.assertEqual(states(admission_steps(applicant)), ["done", "done", "current"])
        applicant.admission_status = "REJECTED"
        rejected = admission_steps(applicant)
        self.assertEqual(states(rejected), ["done", "stopped", "upcoming"])
        self.assertEqual(rejected[1]["note"], "Rejected")

    def test_linked_student_means_enrolled(self):
        applicant = Applicant.objects.create(full_name="Asha Rao", admission_status="ACCEPTED")
        student = Student.objects.create(applicant=applicant, full_name="Asha Rao")
        self.assertEqual(states(admission_steps(applicant, student)), ["done", "done", "done"])


class StepsOnPagesTests(AuthorizationClientsMixin, TestCase):
    def assert_current_step(self, response, label):
        html = response.content.decode()
        self.assertIn('<ol class="erp-steps"', html)
        current = re.findall(r'<li class="erp-step erp-step--current" aria-current="step">.*?</li>', html, re.S)
        self.assertEqual(len(current), 1)
        self.assertIn(label, current[0])
        self.assertIn('<span class="visually-hidden">, current step</span>', current[0])

    def test_import_upload_page(self):
        response = self.administrator.get(reverse("core:import-upload"))
        self.assertContains(response, 'aria-label="Import progress"')
        self.assert_current_step(response, "Upload file")

    def test_register_applicant_page(self):
        response = self.administrator.get(reverse("core:applicant-create"))
        self.assertContains(response, 'aria-label="Admission progress"')
        self.assert_current_step(response, "Register applicant")

    def test_pending_applicant_page(self):
        applicant = Applicant.objects.create(full_name="Asha Rao")
        response = self.administrator.get(reverse("core:applicant-detail", args=[applicant.pk]))
        self.assert_current_step(response, "Decide admission")

    def test_rejected_applicant_page_shows_the_stop(self):
        applicant = Applicant.objects.create(full_name="Asha Rao", admission_status="REJECTED")
        response = self.administrator.get(reverse("core:applicant-detail", args=[applicant.pk]))
        self.assertContains(response, "erp-step--stopped")
        self.assertContains(response, '<span class="erp-step-note">Rejected</span>')
        self.assertNotContains(response, 'aria-current="step"')
