"""UI-D1-3B (T1): Applicant detail adopts panels, a definition list and a labelled guardians region.

Data, links, permissions and the progression POST are unchanged. All names are synthetic.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, ApplicantGuardian, Guardian, Student
from core.tests.phase4_fixtures import Phase4Fixture

LONG_NAME = "Venkataraghavan Subramaniam Ramachandran-Krishnamurthy Iyengar"


class ApplicantDetailD13BTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")

    def client_with(self, username, *codenames):
        user = self.make_user(username)
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def applicant(self, status="PENDING", name="Asha Testfield", **extra):
        return Applicant.objects.create(full_name=name, admission_status=status, **extra)

    def get(self, applicant, client=None):
        response = (client or self.client).get(reverse("core:applicant-detail", args=[applicant.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def accept_url(self, a):
        return reverse("core:applicant-decision-confirm", args=[a.pk, "ACCEPTED"])

    def reject_url(self, a):
        return reverse("core:applicant-decision-confirm", args=[a.pk, "REJECTED"])

    def progress_url(self, a):
        return reverse("core:applicant-progress", args=[a.pk])

    def make_student_for(self, applicant, name="Asha Testfield"):
        """Create a Student; for a non-accepted Applicant, create it while accepted then force the
        status back (the inconsistent state the reconciliation warning exists for)."""
        status = applicant.admission_status
        if status != "ACCEPTED":
            Applicant.objects.filter(pk=applicant.pk).update(admission_status="ACCEPTED")
            applicant.refresh_from_db()
        student = Student.objects.create(applicant=applicant, full_name=name)
        if status != "ACCEPTED":
            Applicant.objects.filter(pk=applicant.pk).update(admission_status=status)
            applicant.refresh_from_db()
        return student

    # Shell and markup
    def test_panel_region_and_semantic_markup(self):
        a = self.applicant(date_of_birth="2015-04-05", email="a@example.test", phone="555-0101")
        content = self.get(a)
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-page-header"', content)
        self.assertIn("erp-panel", content)
        self.assertIn('role="region" aria-label="Guardians" tabindex="0"', content)
        self.assertIn('<th scope="col">Guardian</th>', content)
        self.assertIn('<th scope="col">Relationship</th>', content)
        self.assertNotIn("<th>", content)
        for label in ("Admission status", "Date of birth", "Email", "Phone"):
            self.assertIn(f'<dt class="col-sm-3">{label}</dt>', content)
        self.assertIn("<dl", content)
        self.assertIn("a@example.test", content)
        self.assertIn("555-0101", content)
        self.assertIn(f'href="{reverse("core:applicant-list")}">Back to Applicants', content)

    def test_empty_optional_fields_show_dash(self):
        content = self.get(self.applicant())
        self.assertIn('<dd class="col-sm-9">-</dd>', content)
        self.assertNotIn("Decision recorded", content)
        self.assertNotIn("Decision reason", content)

    def test_decision_details_shown_when_recorded(self):
        a = self.applicant()
        a.record_admission_decision(Applicant.AdmissionStatus.REJECTED, reason="Capacity reached")
        content = self.get(a)
        self.assertIn("Decision recorded", content)
        self.assertIn("Decision reason", content)
        self.assertIn("Capacity reached", content)

    def test_long_name_not_truncated(self):
        self.assertIn(LONG_NAME, self.get(self.applicant(name=LONG_NAME)))

    # Status display
    def test_status_text_for_each_status(self):
        for status, label in (("PENDING", "Pending"), ("ACCEPTED", "Accepted"), ("REJECTED", "Rejected")):
            content = self.get(self.applicant(status, name=f"{label} Person"))
            self.assertIn(label, content)
            self.assertIn(f"{label} Person", content)

    # Decision links
    def test_decision_links_only_for_pending_without_student(self):
        pending = self.applicant("PENDING")
        content = self.get(pending)
        self.assertIn("Admission decision", content)
        self.assertIn(f'href="{self.accept_url(pending)}">Accept applicant', content)
        self.assertIn(f'href="{self.reject_url(pending)}">Reject applicant', content)
        for status in ("ACCEPTED", "REJECTED"):
            other = self.applicant(status, name=f"{status} Person")
            content = self.get(other)
            self.assertNotIn("Admission decision", content)
            self.assertNotIn(self.accept_url(other), content)

    def test_decision_links_hidden_with_student(self):
        a = self.applicant("PENDING")
        self.make_student_for(a)
        content = self.get(a)
        self.assertNotIn("Admission decision", content)
        self.assertNotIn(self.accept_url(a), content)
        self.assertNotIn(self.reject_url(a), content)

    def test_decision_links_hidden_for_limited_user(self):
        a = self.applicant("PENDING")
        viewer = self.client_with("viewer", "view_applicant")
        content = self.get(a, viewer)
        self.assertNotIn("Admission decision", content)
        self.assertNotIn(self.accept_url(a), content)
        self.assertNotIn(self.reject_url(a), content)

    # Progression
    def test_progress_form_for_accepted_without_student(self):
        a = self.applicant("ACCEPTED")
        content = self.get(a)
        self.assertIn("Student progression", content)
        self.assertIn(f'method="post" action="{self.progress_url(a)}"', content)
        self.assertIn("csrfmiddlewaretoken", content)
        self.assertIn("Progress to Student", content)

    def test_progress_form_hidden_otherwise(self):
        for status in ("PENDING", "REJECTED"):
            a = self.applicant(status, name=f"{status} Person")
            content = self.get(a)
            self.assertNotIn(self.progress_url(a), content)
            self.assertNotIn("Student progression", content)
        accepted = self.applicant("ACCEPTED", name="Has Student")
        self.make_student_for(accepted, "Has Student")
        self.assertNotIn(self.progress_url(accepted), self.get(accepted))
        lonely = self.applicant("ACCEPTED", name="Limited View")
        viewer = self.client_with("viewer", "view_applicant")
        content = self.get(lonely, viewer)
        self.assertNotIn(self.progress_url(lonely), content)
        self.assertNotIn("Progress to Student", content)

    # Linked student and reconciliation
    def test_linked_student_shows_name_status_and_link(self):
        a = self.applicant("ACCEPTED", name="Bala Sample")
        student = self.make_student_for(a, "Bala Sample")
        content = self.get(a)
        self.assertIn("Student record exists: Bala Sample, Active.", content)
        self.assertIn(f'href="{reverse("core:student-detail", args=[student.pk])}">View Student record', content)
        self.assertNotIn("Needs reconciliation", content)

    def test_inconsistent_student_shows_reconciliation_warning(self):
        for status, label in (("PENDING", "Pending"), ("REJECTED", "Rejected")):
            a = self.applicant(status, name=f"{label} Linked")
            self.make_student_for(a, f"{label} Linked")
            content = self.get(a)
            self.assertIn('role="status"', content)
            self.assertIn(
                f"Needs reconciliation: this Applicant is still {label} but a Student record exists.", content
            )
            self.assertIn("manage.py reconcile_applicants", content)

    # Guardians
    def test_guardians_linked(self):
        a = self.applicant()
        zed = Guardian.objects.create(full_name="Zed Example")
        amy = Guardian.objects.create(full_name="Amy Example")
        ApplicantGuardian.objects.create(applicant=a, guardian=zed, relationship_type="FATHER")
        ApplicantGuardian.objects.create(applicant=a, guardian=amy, relationship_type="MOTHER")
        content = self.get(a)
        self.assertIn(f'href="{reverse("core:guardian-detail", args=[zed.pk])}">Zed Example', content)
        self.assertIn(f'href="{reverse("core:guardian-detail", args=[amy.pk])}">Amy Example', content)
        self.assertIn("Father", content)
        self.assertIn("Mother", content)
        self.assertNotIn("No Guardians associated yet.", content)

    def test_guardians_absent(self):
        self.assertIn("No Guardians associated yet.", self.get(self.applicant()))

    def test_associate_guardian_permission_gating(self):
        a = self.applicant()
        create = reverse("core:applicant-guardian-create", args=[a.pk])
        self.assertIn(f'href="{create}">Associate Guardian', self.get(a))
        viewer = self.client_with("viewer", "view_applicant")
        content = self.get(a, viewer)
        self.assertNotIn(create, content)
        self.assertNotIn("Associate Guardian", content)
        adder = self.client_with("adder", "view_applicant", "add_applicantguardian")
        self.assertIn(create, self.get(a, adder))
