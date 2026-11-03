"""Credential slips: a refresh never issues a new password, and printing shows only the card."""

import pathlib
import re

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core import teacher_accounts
from core.models import Guardian, GuardianAccount, School
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS


def token_in(response):
    return re.search(r'name="one_time_token" value="([^"]+)"', response.content.decode()).group(1)


def password_in(response):
    return re.search(r'id="credential-password">([^<]+)<', response.content.decode()).group(1)


def message_in(response):
    return " ".join(str(message) for message in get_messages(response.wsgi_request))


class TeacherResetTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher, self.first_password = teacher_accounts.create_teacher(
            actor=self.admin_user, first_name="Asha", last_name="Rao", username="asha.rao", email=""
        )
        self.url = reverse("core:teacher-reset-password", args=[self.teacher.pk])

    def events(self):
        return SecurityEvent.objects.filter(subject_user=self.teacher).count()

    def signs_in(self, password):
        return authenticate(username="asha.rao", password=password) is not None

    def test_a_refresh_keeps_the_password_already_issued(self):
        token = token_in(self.administrator.get(self.url))
        issued = password_in(self.administrator.post(self.url, {"one_time_token": token}))
        events = self.events()

        refreshed = self.administrator.post(self.url, {"one_time_token": token})

        self.assertRedirects(refreshed, reverse("core:teacher-detail", args=[self.teacher.pk]))
        self.assertIn("no new password was made", message_in(refreshed))
        self.assertTrue(self.signs_in(issued))
        self.assertEqual(self.events(), events)

    def test_opening_the_page_again_allows_a_real_new_reset(self):
        token = token_in(self.administrator.get(self.url))
        issued = password_in(self.administrator.post(self.url, {"one_time_token": token}))
        token = token_in(self.administrator.get(self.url))
        again = password_in(self.administrator.post(self.url, {"one_time_token": token}))
        self.assertNotEqual(issued, again)
        self.assertTrue(self.signs_in(again))
        self.assertFalse(self.signs_in(issued))

    def test_an_old_token_is_refused_after_a_newer_page_opened(self):
        old = token_in(self.administrator.get(self.url))
        issued = password_in(self.administrator.post(self.url, {"one_time_token": old}))
        self.administrator.get(self.url)
        self.assertEqual(self.administrator.post(self.url, {"one_time_token": old}).status_code, 302)
        self.assertTrue(self.signs_in(issued))

    def test_a_token_belongs_to_one_teacher(self):
        other, _ = teacher_accounts.create_teacher(
            actor=self.admin_user, first_name="Ravi", last_name="Das", username="ravi.das", email=""
        )
        other_url = reverse("core:teacher-reset-password", args=[other.pk])
        token = token_in(self.administrator.get(self.url))
        self.administrator.get(other_url)
        self.assertEqual(self.administrator.post(other_url, {"one_time_token": token}).status_code, 302)
        self.assertTrue(authenticate(username="ravi.das", password=_) is not None)

    def test_a_post_without_a_token_still_works(self):
        self.assertEqual(self.administrator.post(self.url).status_code, 200)

    def test_the_token_is_not_the_password_and_no_password_is_in_the_session(self):
        token = token_in(self.administrator.get(self.url))
        issued = password_in(self.administrator.post(self.url, {"one_time_token": token}))
        self.assertNotEqual(token, issued)
        self.assertNotIn(issued, str(dict(self.administrator.session)))


class TeacherCreateTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:teacher-create")
        self.data = {"first_name": "Asha", "last_name": "Rao", "username": "asha.rao", "email": ""}

    def post(self, token, **overrides):
        return self.administrator.post(self.url, {**self.data, **overrides, "one_time_token": token})

    def test_a_refresh_explains_instead_of_saying_the_username_is_taken(self):
        token = token_in(self.administrator.get(self.url))
        issued = password_in(self.post(token))
        refreshed = self.post(token)
        self.assertRedirects(refreshed, reverse("core:teacher-list"))
        self.assertIn("no new password was made", message_in(refreshed))
        self.assertTrue(authenticate(username="asha.rao", password=issued))
        self.assertEqual(User.objects.filter(username="asha.rao").count(), 1)

    def test_a_form_error_can_be_corrected_and_submitted(self):
        token = token_in(self.administrator.get(self.url))
        invalid = self.post(token, first_name="")
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('id="credential-password"', self.post(token_in(invalid)).content.decode())

    def test_a_taken_username_can_be_corrected_and_submitted(self):
        teacher_accounts.create_teacher(
            actor=self.admin_user, first_name="A", last_name="B", username="asha.rao", email=""
        )
        taken = self.post(token_in(self.administrator.get(self.url)))
        self.assertEqual(taken.status_code, 200)
        corrected = self.post(token_in(taken), username="asha.r")
        self.assertIn('id="credential-password"', corrected.content.decode())


class GuardianSlipTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.guardian = Guardian.objects.create(full_name="Meena Rao")

    def existing_account(self):
        return ga.create_guardian_account(
            guardian=self.guardian, username="meena.rao", method=METHOD, note="Seen", actor=self.admin_user
        )

    def test_a_reset_refresh_keeps_the_password_already_issued(self):
        account, _ = self.existing_account()
        url = reverse("core:guardian-account-reset-password", args=[account.pk])
        token = token_in(self.administrator.get(url))
        issued = password_in(self.administrator.post(url, {"one_time_token": token}))
        refreshed = self.administrator.post(url, {"one_time_token": token})
        self.assertRedirects(refreshed, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertIn("no new password was made", message_in(refreshed))
        self.assertTrue(authenticate(username="meena.rao", password=issued))

    def test_a_create_refresh_explains_and_makes_nothing(self):
        url = reverse("core:guardian-account-create", args=[self.guardian.pk])
        data = {"username": "meena.rao", "identity_verification_method": METHOD,
                "identity_verification_note": "Seen"}
        token = token_in(self.administrator.get(url))
        issued = password_in(self.administrator.post(url, {**data, "one_time_token": token}))
        refreshed = self.administrator.post(url, {**data, "one_time_token": token})
        self.assertRedirects(refreshed, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertIn("no new password was made", message_in(refreshed))
        self.assertTrue(authenticate(username="meena.rao", password=issued))
        self.assertEqual(GuardianAccount.objects.filter(guardian=self.guardian).count(), 1)


class SlipPageTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        School.objects.create(name="Demo Public School")
        self.teacher, _ = teacher_accounts.create_teacher(
            actor=self.admin_user, first_name="Asha", last_name="Rao", username="asha.rao", email=""
        )
        url = reverse("core:teacher-reset-password", args=[self.teacher.pk])
        self.response = self.administrator.post(url)
        self.content = self.response.content.decode()

    def test_card_has_school_person_and_date_and_is_never_cached(self):
        card = self.content[self.content.index("erp-credential-card"):]
        self.assertIn("Demo Public School", card)
        self.assertIn("Asha Rao", card)
        self.assertIn("Issued ", card)
        self.assertIn("no-store", self.response["Cache-Control"])

    def test_copy_buttons_start_hidden_and_stay_off_paper(self):
        self.assertRegex(self.content, r'data-erp-copy="credential-username"[^>]*\bhidden\b')
        self.assertRegex(self.content, r'data-erp-copy="credential-password"[^>]*\bhidden\b')
        self.assertIn('aria-live="polite" data-erp-copy-status', self.content)

    def test_the_refresh_warning_is_gone_because_a_refresh_is_now_safe(self):
        self.assertNotIn("Do not refresh", self.content)

    def test_page_never_prints_by_itself(self):
        self.assertNotIn("window.print();", self.content)

    def test_print_rules_show_only_the_card(self):
        css = pathlib.Path(settings.BASE_DIR, "static/css/erp.css").read_text("utf-8")
        rules = css[css.index("@media print"):]
        self.assertIn(".erp-credential-card", rules)
        self.assertIn("visibility: hidden", rules)
