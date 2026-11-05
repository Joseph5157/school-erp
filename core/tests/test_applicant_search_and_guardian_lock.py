"""Find an Applicant by name, phone or email, and stop Guardian changes that would be lost.

Once a Student exists its Guardian links are separate from the Applicant's, so a change
on the Applicant would never reach the Student. Rejected Applicants need no new Guardians.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, ApplicantGuardian, Guardian, RelationshipType, Student
from core.tests.test_authorization import AuthorizationClientsMixin


class ApplicantSearchTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:applicant-list")
        self.asha = Applicant.objects.create(
            full_name="Asha Rao", phone="9811111111", email="asha@example.test",
            date_of_birth=date(2015, 3, 9),
        )
        self.twin = Applicant.objects.create(
            full_name="Asha Rao", phone="9822222222", admission_status="ACCEPTED"
        )
        self.ravi = Applicant.objects.create(full_name="Ravi Iyer", email="ravi@example.test")

    def found(self, **params):
        response = self.administrator.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return set(response.context["table"].page.object_list)

    def test_search_matches_name_phone_and_email(self):
        self.assertEqual(self.found(q="asha r"), {self.asha, self.twin})
        self.assertEqual(self.found(q="98222"), {self.twin})
        self.assertEqual(self.found(q="ravi@example"), {self.ravi})

    def test_search_combines_with_status(self):
        self.assertEqual(self.found(q="Asha", status="ACCEPTED"), {self.twin})

    def test_blank_search_lists_everyone(self):
        self.assertEqual(self.found(q="   "), {self.asha, self.twin, self.ravi})

    def test_results_tell_same_named_applicants_apart(self):
        response = self.administrator.get(self.url, {"q": "Asha"})
        for text in ("9811111111", "asha@example.test", "9822222222", "9 Mar 2015"):
            self.assertContains(response, text)

    def test_unfiltered_list_stays_compact(self):
        self.assertNotContains(self.administrator.get(self.url), "9811111111")

    def test_no_match_says_so_and_offers_clear(self):
        response = self.administrator.get(self.url, {"q": "Nobody"})
        self.assertContains(response, "No applicants match this search.")
        self.assertNotContains(response, "No applicants yet")
        self.assertContains(response, "Clear filters")

    def test_search_text_is_kept_and_escaped(self):
        response = self.administrator.get(self.url, {"q": '"><script>x</script>'})
        self.assertNotContains(response, "<script>x</script>")
        self.assertContains(response, "&lt;script&gt;x")

    def test_paging_keeps_the_search(self):
        Applicant.objects.bulk_create(Applicant(full_name=f"Common {i:03}") for i in range(60))
        response = self.administrator.get(self.url, {"q": "Common"})
        self.assertIn("q=Common", response.context["table"].next_url)


class ApplicantGuardianLockTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="9811111111")
        self.payload = {"guardian": self.guardian.pk, "relationship_type": RelationshipType.MOTHER}

    def add_url(self, applicant):
        return reverse("core:applicant-guardian-create", args=[applicant.pk])

    def detail_url(self, applicant):
        return reverse("core:applicant-detail", args=[applicant.pk])

    def progressed(self):
        applicant = Applicant.objects.create(full_name="Asha Rao", admission_status="ACCEPTED")
        return applicant, Student.objects.create(applicant=applicant, full_name="Asha Rao")

    def test_pending_and_accepted_without_student_can_still_add(self):
        for status in ("PENDING", "ACCEPTED"):
            with self.subTest(status=status):
                applicant = Applicant.objects.create(full_name="Ravi Iyer", admission_status=status)
                self.assertContains(self.administrator.get(self.detail_url(applicant)), "Associate guardian")
                response = self.administrator.post(self.add_url(applicant), self.payload)
                self.assertRedirects(response, self.detail_url(applicant))
                self.assertTrue(applicant.guardian_links.exists())

    def test_progressed_applicant_refuses_new_guardian_on_every_method(self):
        applicant, _ = self.progressed()
        for response in (
            self.administrator.get(self.add_url(applicant)),
            self.administrator.post(self.add_url(applicant), self.payload),
        ):
            self.assertRedirects(response, self.detail_url(applicant))
        self.assertFalse(ApplicantGuardian.objects.exists())

    def test_progressed_applicant_points_to_the_student_record(self):
        applicant, student = self.progressed()
        response = self.administrator.get(self.detail_url(applicant))
        self.assertNotContains(response, "Associate guardian")
        self.assertContains(response, "Manage guardians on the")
        self.assertContains(response, reverse("core:student-detail", args=[student.pk]))

    def test_refusal_explains_why(self):
        applicant, _ = self.progressed()
        response = self.administrator.get(self.add_url(applicant), follow=True)
        self.assertContains(response, "already has a Student record")

    def test_rejected_applicant_refuses_new_guardian_and_keeps_history(self):
        applicant = Applicant.objects.create(full_name="Ravi Iyer", admission_status="REJECTED")
        ApplicantGuardian.objects.create(
            applicant=applicant, guardian=self.guardian, relationship_type=RelationshipType.FATHER
        )
        other = Guardian.objects.create(full_name="Kumar Iyer")
        response = self.administrator.post(
            self.add_url(applicant), {"guardian": other.pk, "relationship_type": RelationshipType.FATHER}
        )
        self.assertRedirects(response, self.detail_url(applicant))
        self.assertEqual(applicant.guardian_links.count(), 1)
        detail = self.administrator.get(self.detail_url(applicant))
        self.assertNotContains(detail, "Associate guardian")
        self.assertContains(detail, "Meena Rao")

    def test_creating_a_guardian_for_a_locked_applicant_goes_to_the_list(self):
        applicant, _ = self.progressed()
        response = self.administrator.post(
            f'{reverse("core:guardian-create")}?for_applicant={applicant.pk}', {"full_name": "New Parent"}
        )
        self.assertRedirects(response, reverse("core:guardian-list"))
