"""Search for a Guardian instead of picking from a dropdown of every Guardian.

Applicant and Student share the flow, so most behaviour runs against both through
the mixin. Linking the wrong person is the risk being reduced: results show enough
to tell two people with the same name apart, and nothing is saved until Save.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    RelationshipType,
    Student,
    StudentGuardian,
)
from core.tests.test_authorization import AuthorizationClientsMixin


class LookupFlowMixin:
    """Subclasses set `url_name`, `link_model`, `target_field`, `create_param`, `detail_name`."""

    def setUp(self):
        super().setUp()
        self.target = self.make_target()
        self.url = reverse(self.url_name, args=[self.target.pk])
        self.first = Guardian.objects.create(
            full_name="Anil Patnaik", phone="9325272008", email="first.anil@example.test"
        )
        self.second = Guardian.objects.create(
            full_name="Anil Patnaik", phone="9000000001", email="second.anil@example.test"
        )
        self.other = Guardian.objects.create(full_name="Meena Iyer", phone="9811111111")

    def link(self, guardian):
        return self.link_model.objects.create(
            guardian=guardian,
            relationship_type=RelationshipType.FATHER,
            **{self.target_field: self.target},
        )

    def search(self, query):
        response = self.administrator.get(self.url, {"q": query})
        self.assertEqual(response.status_code, 200)
        return response

    def test_page_has_no_dropdown_of_guardians(self):
        response = self.administrator.get(self.url)
        self.assertNotContains(response, 'name="guardian"')
        self.assertNotContains(response, "Anil Patnaik")
        self.assertContains(response, 'name="q"')

    def test_results_tell_same_named_guardians_apart(self):
        response = self.search("Anil")
        for text in ("9325272008", "first.anil@example.test", "9000000001", "second.anil@example.test"):
            self.assertContains(response, text)
        self.assertNotContains(response, "Meena Iyer")

    def test_card_name_has_no_overlay_that_would_block_select(self):
        # .erp-guardian-card-name stretches a link over its whole card (see erp.css), which
        # on these cards sat on top of Select and swallowed every tap.
        self.assertNotContains(self.search("Anil"), "erp-guardian-card-name")

    def test_search_matches_phone_and_email(self):
        self.assertEqual(self.search("9811111111").context["results"], [self.other])
        self.assertEqual(self.search("second.anil").context["results"], [self.second])

    def test_search_matches_child_name(self):
        child = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Pavani Rao"),
            full_name="Pavani Rao",
        )
        StudentGuardian.objects.create(
            student=child, guardian=self.other, relationship_type=RelationshipType.MOTHER
        )
        response = self.search("Pavani")
        self.assertEqual(response.context["results"], [self.other])
        self.assertContains(response, "Pavani Rao")

    def test_already_linked_guardian_is_marked_and_cannot_be_selected(self):
        self.link(self.first)
        response = self.search("Anil")
        self.assertContains(response, "Already linked")
        self.assertNotContains(response, f"guardian={self.first.pk}")
        self.assertContains(response, f"guardian={self.second.pk}")

    def test_selecting_saves_nothing_and_shows_who_was_chosen(self):
        response = self.administrator.get(self.url, {"guardian": self.second.pk, "q": "Anil"})
        self.assertEqual(self.link_model.objects.count(), 0)
        self.assertContains(response, "9000000001")
        self.assertNotContains(response, "9325272008")
        self.assertContains(response, f'type="hidden" name="guardian" value="{self.second.pk}"')
        self.assertContains(response, 'name="relationship_type"')
        self.assertContains(response, "Choose someone else")

    def test_save_links_the_chosen_guardian(self):
        response = self.administrator.post(
            f"{self.url}?guardian={self.second.pk}",
            {"guardian": self.second.pk, "relationship_type": RelationshipType.MOTHER},
        )
        self.assertRedirects(response, reverse(self.detail_name, args=[self.target.pk]))
        link = self.link_model.objects.get()
        self.assertEqual(link.guardian, self.second)
        self.assertEqual(link.relationship_type, RelationshipType.MOTHER)

    def test_missing_relationship_keeps_the_chosen_guardian(self):
        response = self.administrator.post(
            f"{self.url}?guardian={self.second.pk}", {"guardian": self.second.pk}
        )
        self.assertEqual(self.link_model.objects.count(), 0)
        self.assertContains(response, "9000000001")
        self.assertContains(response, f'type="hidden" name="guardian" value="{self.second.pk}"')

    def test_unknown_or_malformed_selection_falls_back_to_search(self):
        for value in (str(self.other.pk + 999), "abc", "9" * 40):
            with self.subTest(value=value):
                response = self.administrator.get(self.url, {"guardian": value})
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="guardian"')
                self.assertContains(response, 'name="q"')

    def test_selecting_an_already_linked_guardian_by_address_is_refused(self):
        self.link(self.first)
        response = self.administrator.get(self.url, {"guardian": self.first.pk})
        self.assertNotContains(response, 'name="guardian"')
        self.assertContains(response, "already linked")

    def test_results_stop_at_twenty_and_ask_for_a_narrower_search(self):
        Guardian.objects.bulk_create(
            Guardian(full_name=f"Common Name {i:02}", phone=f"90000{i:05}") for i in range(25)
        )
        response = self.search("Common Name")
        self.assertEqual(len(response.context["results"]), 20)
        self.assertContains(response, "Showing the first 20")

    def test_exactly_twenty_results_do_not_ask_for_a_narrower_search(self):
        Guardian.objects.bulk_create(Guardian(full_name=f"Common Name {i:02}") for i in range(20))
        response = self.search("Common Name")
        self.assertEqual(len(response.context["results"]), 20)
        self.assertNotContains(response, "Showing the first 20")

    def test_query_count_does_not_grow_with_results(self):
        def count():
            with CaptureQueriesContext(connection) as captured:
                self.search("Common Name")
            return len(captured)

        Guardian.objects.bulk_create(Guardian(full_name=f"Common Name {i}") for i in range(2))
        few = count()
        Guardian.objects.bulk_create(Guardian(full_name=f"Common Name X{i}") for i in range(10))
        self.assertEqual(count(), few)

    def test_no_match_offers_create_new_guardian(self):
        response = self.search("Nobody Here")
        self.assertContains(response, "No guardians match this search")
        self.assertContains(response, f'{reverse("core:guardian-create")}?{self.create_param}={self.target.pk}')

    def test_search_text_is_escaped(self):
        response = self.search("<script>x</script>")
        self.assertNotContains(response, "<script>x</script>")

    def test_new_guardian_returns_here_with_that_person_selected(self):
        create_url = f'{reverse("core:guardian-create")}?{self.create_param}={self.target.pk}'
        response = self.administrator.post(create_url, {"full_name": "New Parent"})
        guardian = Guardian.objects.get(full_name="New Parent")
        self.assertRedirects(response, f"{self.url}?guardian={guardian.pk}")
        self.assertEqual(self.link_model.objects.count(), 0)

    def test_create_page_cancel_returns_here(self):
        response = self.administrator.get(
            reverse("core:guardian-create"), {self.create_param: self.target.pk}
        )
        self.assertContains(response, f'<a class="btn btn-link" href="{self.url}">Cancel</a>')

    def test_create_ignores_a_target_that_does_not_exist(self):
        for value in (str(self.target.pk + 999), "https://example.test/", "abc"):
            with self.subTest(value=value):
                response = self.administrator.post(
                    f'{reverse("core:guardian-create")}?{self.create_param}={value}',
                    {"full_name": f"Parent {value}"},
                )
                self.assertRedirects(response, reverse("core:guardian-list"))

    def test_needs_permission_to_see_guardian_details(self):
        user = get_user_model().objects.create_user("limited", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename=self.add_codename))
        client = self.client_class()
        client.force_login(user)
        self.assertEqual(client.get(self.url, {"q": "Anil"}).status_code, 403)


class ApplicantGuardianLookupTests(LookupFlowMixin, AuthorizationClientsMixin, TestCase):
    url_name = "core:applicant-guardian-create"
    link_model = ApplicantGuardian
    target_field = "applicant"
    create_param = "for_applicant"
    detail_name = "core:applicant-detail"
    add_codename = "add_applicantguardian"

    def make_target(self):
        return Applicant.objects.create(full_name="Ravi Rao")


class StudentGuardianLookupTests(LookupFlowMixin, AuthorizationClientsMixin, TestCase):
    url_name = "core:student-guardian-add"
    link_model = StudentGuardian
    target_field = "student"
    create_param = "for_student"
    detail_name = "core:student-detail"
    add_codename = "add_studentguardian"

    def make_target(self):
        applicant = Applicant.objects.create(admission_status="ACCEPTED", full_name="Ravi Rao")
        return Student.objects.create(applicant=applicant, full_name="Ravi Rao")


class GuardianCreateWithoutLookupTests(AuthorizationClientsMixin, TestCase):
    def test_plain_create_still_returns_to_the_list(self):
        response = self.administrator.post(reverse("core:guardian-create"), {"full_name": "Plain"})
        self.assertRedirects(response, reverse("core:guardian-list"))
