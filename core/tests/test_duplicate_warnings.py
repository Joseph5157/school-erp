"""Possible-duplicate warnings on Register Applicant and Create Guardian.

The warning asks staff to look before saving and never stops them: pressing the
"anyway" button always saves. Matches only ever come from records the user may view.
"""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.duplicate_checks import name_key, phone_key
from core.models import (
    Applicant,
    ApplicantGuardian,
    Guardian,
    RelationshipType,
    Student,
    StudentGuardian,
)
from core.tests.test_authorization import AuthorizationClientsMixin

WARNING = "Possible duplicate"


def limited_client(client_class, *codenames):
    user = get_user_model().objects.create_user("limited", password="pass-12345")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = client_class()
    client.force_login(user)
    return client


class ComparisonKeyTests(SimpleTestCase):
    def test_phone_formats_of_the_same_number_compare_equal(self):
        for phone in ("+91 98765 43210", "98765-43210", "(0) 9876543210", "919876543210"):
            self.assertEqual(phone_key(phone), "9876543210")

    def test_too_few_digits_never_match_anything(self):
        for phone in ("", "n/a", "12345"):
            self.assertEqual(phone_key(phone), "")

    def test_name_ignores_capitals_and_extra_spaces(self):
        self.assertEqual(name_key("  Asha   RAO "), name_key("asha rao"))

    def test_name_keeps_spelling_differences(self):
        self.assertNotEqual(name_key("Asha Rao"), name_key("Aasha Rao"))


class ApplicantWarningTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:applicant-create")
        self.existing = Applicant.objects.create(
            full_name="Asha Rao",
            date_of_birth=datetime.date(2015, 3, 4),
            phone="+91 98765 43210",
            email="rao.family@example.test",
        )

    def post(self, client=None, **data):
        return (client or self.administrator).post(self.url, {"full_name": "New Child", **data})

    def progress_existing(self, **fields):
        self.existing.admission_status = Applicant.AdmissionStatus.ACCEPTED
        self.existing.save()
        return Student.objects.create(applicant=self.existing, **fields)

    def assert_warned(self, response, *reasons):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, WARNING)
        for reason in reasons:
            self.assertContains(response, reason)

    def assert_saved(self, response, name="New Child"):
        self.assertRedirects(response, reverse("core:applicant-list"), fetch_redirect_response=False)
        self.assertTrue(Applicant.objects.filter(full_name=name).exclude(pk=self.existing.pk).exists())

    def test_no_match_saves_straight_away(self):
        self.assert_saved(self.post(phone="9000000001", email="other@example.test"))

    def test_same_name_and_birth_date_warns_and_does_not_save(self):
        response = self.post(full_name="  asha   RAO", date_of_birth="2015-03-04")
        self.assert_warned(response, "Same name and date of birth")
        self.assertEqual(Applicant.objects.count(), 1)

    def test_same_name_with_other_birth_date_is_not_a_match(self):
        self.assert_saved(self.post(full_name="Asha Rao", date_of_birth="2016-03-04"), "Asha Rao")

    def test_same_name_without_birth_date_is_not_a_match(self):
        self.assert_saved(self.post(full_name="Asha Rao"), "Asha Rao")

    def test_same_phone_in_another_format_warns_about_siblings(self):
        self.assert_warned(self.post(phone="9876543210"), "Same phone, may be a sibling")

    def test_same_email_in_other_capitals_warns_about_siblings(self):
        self.assert_warned(self.post(email="RAO.family@example.test"), "Same email, may be a sibling")

    def test_blank_contact_details_do_not_match_each_other(self):
        Applicant.objects.create(full_name="No Contact")
        self.assert_saved(self.post())

    def test_warning_keeps_what_was_typed(self):
        response = self.post(phone="9876543210")
        self.assertContains(response, 'value="New Child"')
        self.assertContains(response, 'value="9876543210"')

    def test_warning_links_to_the_existing_applicant(self):
        response = self.post(phone="9876543210")
        self.assertContains(response, reverse("core:applicant-detail", args=[self.existing.pk]))

    def test_anyway_button_always_saves(self):
        self.assert_saved(self.post(phone="9876543210", confirm_new="1"))

    def test_the_check_button_comes_first_so_enter_cannot_skip_the_warning(self):
        # A browser's Enter key presses the form's first submit button.
        content = self.post(phone="9876543210").content.decode()
        self.assertLess(content.index("Check again"), content.index('name="confirm_new"'))

    def test_invalid_form_shows_errors_without_a_warning(self):
        response = self.post(full_name="", phone="9876543210")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, WARNING)

    def test_rejected_applicant_shows_its_status(self):
        Applicant.objects.filter(pk=self.existing.pk).update(
            admission_status=Applicant.AdmissionStatus.REJECTED
        )
        self.assert_warned(self.post(phone="9876543210"), "Rejected")

    def test_existing_student_is_matched_and_opened_as_a_student(self):
        student = self.progress_existing(full_name="Asha Rao", phone="9111111111")
        response = self.post(phone="9111111111")
        self.assert_warned(response, "Same phone, may be a sibling")
        self.assertContains(response, reverse("core:student-detail", args=[student.pk]))

    def test_a_progressed_applicant_is_not_listed_as_well_as_its_student(self):
        self.progress_existing(full_name="Asha Rao", phone="9876543210")
        response = self.post(phone="9876543210")
        self.assertNotContains(response, reverse("core:applicant-detail", args=[self.existing.pk]))

    def test_records_the_user_cannot_view_are_never_revealed(self):
        self.progress_existing(full_name="Hidden Child", phone="9111111111")
        client = limited_client(self.client_class, "add_applicant", "view_applicant")
        self.assert_saved(self.post(client, phone="9111111111"))


class GuardianWarningTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:guardian-create")
        self.existing = Guardian.objects.create(
            full_name="Anil Patnaik", phone="+91 93252 72008", email="anil@example.test"
        )

    def post(self, client=None, url=None, **data):
        return (client or self.administrator).post(url or self.url, {"full_name": "New Parent", **data})

    def student_linked_to_existing(self, name="Linked Child", **link_fields):
        applicant = Applicant.objects.create(
            full_name=name, admission_status=Applicant.AdmissionStatus.ACCEPTED
        )
        student = Student.objects.create(applicant=applicant, full_name=name)
        StudentGuardian.objects.create(
            student=student,
            guardian=self.existing,
            relationship_type=RelationshipType.FATHER,
            **link_fields,
        )
        return student

    def test_no_match_saves_straight_away(self):
        response = self.post(phone="9000000001")
        self.assertRedirects(response, reverse("core:guardian-list"), fetch_redirect_response=False)

    def test_same_name_alone_warns_and_does_not_save(self):
        response = self.post(full_name=" anil  PATNAIK")
        self.assertContains(response, WARNING)
        self.assertContains(response, "Same name")
        self.assertEqual(Guardian.objects.count(), 1)

    def test_same_phone_in_another_format_warns(self):
        response = self.post(phone="9325272008")
        self.assertContains(response, "Same phone")
        self.assertEqual(Guardian.objects.count(), 1)

    def test_same_email_in_other_capitals_warns(self):
        response = self.post(email="ANIL@example.test")
        self.assertContains(response, "Same email")
        self.assertEqual(Guardian.objects.count(), 1)

    def test_warning_shows_contact_details_and_an_open_link(self):
        response = self.post(full_name="Anil Patnaik")
        self.assertContains(response, "+91 93252 72008")
        self.assertContains(response, "anil@example.test")
        self.assertContains(response, reverse("core:guardian-detail", args=[self.existing.pk]))

    def test_warning_shows_linked_student_and_applicant(self):
        self.student_linked_to_existing()
        applicant = Applicant.objects.create(full_name="Waiting Child")
        ApplicantGuardian.objects.create(
            applicant=applicant, guardian=self.existing, relationship_type=RelationshipType.FATHER
        )
        response = self.post(full_name="Anil Patnaik")
        self.assertContains(response, "Linked Child")
        self.assertContains(response, "Waiting Child")

    def test_warning_leaves_out_a_child_whose_link_has_ended(self):
        self.student_linked_to_existing(
            "Ended Child", ended_at=timezone.now(), ended_by=self.admin_user, end_reason="Wrong child"
        )
        response = self.post(full_name="Anil Patnaik")
        self.assertContains(response, WARNING)
        self.assertNotContains(response, "Ended Child")

    def test_anyway_button_always_saves(self):
        response = self.post(full_name="Anil Patnaik", confirm_new="1")
        self.assertRedirects(response, reverse("core:guardian-list"), fetch_redirect_response=False)
        self.assertEqual(Guardian.objects.filter(full_name="Anil Patnaik").count(), 2)

    def test_coming_from_an_add_guardian_page_offers_the_existing_guardian(self):
        applicant = Applicant.objects.create(full_name="Waiting Child")
        add_page = reverse("core:applicant-guardian-create", args=[applicant.pk])
        response = self.post(url=f"{self.url}?for_applicant={applicant.pk}", full_name="Anil Patnaik")
        self.assertContains(response, f"{add_page}?guardian={self.existing.pk}")
        self.assertContains(response, "Use this Guardian")

    def test_anyway_from_an_add_guardian_page_returns_with_the_new_guardian(self):
        applicant = Applicant.objects.create(full_name="Waiting Child")
        add_page = reverse("core:applicant-guardian-create", args=[applicant.pk])
        response = self.post(
            url=f"{self.url}?for_applicant={applicant.pk}", full_name="Anil Patnaik", confirm_new="1"
        )
        new = Guardian.objects.exclude(pk=self.existing.pk).get()
        self.assertRedirects(response, f"{add_page}?guardian={new.pk}", fetch_redirect_response=False)

    def test_plain_create_page_does_not_offer_use_this_guardian(self):
        self.assertNotContains(self.post(full_name="Anil Patnaik"), "Use this Guardian")

    def test_user_who_cannot_view_guardians_sees_no_matches(self):
        client = limited_client(self.client_class, "add_guardian")
        response = self.post(client, full_name="Anil Patnaik")
        self.assertRedirects(response, reverse("core:guardian-list"), fetch_redirect_response=False)
