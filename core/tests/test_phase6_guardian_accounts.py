"""Phase 6 Gate 1: guardian accounts, explicit access grants, password change (ADR 0013)."""

import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.admin import ERPUserChangeForm, ERPUserCreationForm
from accounts.models import SecurityEvent
from accounts.usernames import normalize_username
from core import guardian_accounts as ga
from core.models import (
    Applicant,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Student,
    StudentGuardian,
)

User = get_user_model()
Event = SecurityEvent.EventType
METHOD = GuardianAccount.VerificationMethod.IN_PERSON_DOCUMENTS


class GuardianFixture:
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="admin", password="pass-12345")
        self.guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450-12345")
        self.asha = self.student("Asha Rao")
        self.ravi = self.student("Ravi Rao")
        self.asha_link = StudentGuardian.objects.create(
            student=self.asha, guardian=self.guardian, relationship_type="MOTHER"
        )
        self.ravi_link = StudentGuardian.objects.create(
            student=self.ravi, guardian=self.guardian, relationship_type="MOTHER"
        )

    @staticmethod
    def student(name):
        return Student.objects.create(applicant=Applicant.objects.create(full_name=name),
                                      full_name=name)

    def create_account(self, username="meena.rao"):
        return ga.create_guardian_account(guardian=self.guardian, username=username,
                                          method=METHOD, note="Aadhaar card seen by office",
                                          actor=self.admin)

    def raw(self, sql, params):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)


class UsernameRuleTests(GuardianFixture, TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_username("  Meena.RAO "), "meena.rao")
        self.assertEqual(normalize_username("ｍｅｅｎａ"), "meena")  # NFKC full-width

    def test_create_user_normalizes(self):
        self.assertEqual(User.objects.create_user(username=" Kapoor ").username, "kapoor")

    def test_database_rejects_case_only_duplicates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="ADMIN")

    def test_workflow_rejects_case_only_duplicate_and_bad_form(self):
        for username in ("ADMIN", "Admin", "me", "meena rao", "meena@rao"):
            with self.subTest(username=username), self.assertRaises(ValidationError):
                self.create_account(username)
        self.assertFalse(GuardianAccount.objects.exists())

    def test_sign_in_with_any_case(self):
        account, password = self.create_account()
        client = self.client_class()
        self.assertTrue(client.login(username="MEENA.Rao", password=password))

    def test_existing_mixed_case_username_signs_in_without_rewrite(self):
        legacy = User.objects.create(username="Legacy.User")
        legacy.set_password("pass-12345")
        legacy.save()
        self.assertTrue(self.client_class().login(username="legacy.user", password="pass-12345"))
        legacy.refresh_from_db()
        self.assertEqual(legacy.username, "Legacy.User")

    def test_site_admin_forms_use_the_same_rule(self):
        form = ERPUserCreationForm(data={"username": "ADMIN", "password1": "Zx9!long-pass",
                                         "password2": "Zx9!long-pass"})
        self.assertFalse(form.is_valid())
        form = ERPUserCreationForm(data={"username": " New.User ", "password1": "Zx9!long-pass",
                                         "password2": "Zx9!long-pass"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["username"], "new.user")

    def test_migration_precheck_stops_on_nonconforming_usernames(self):
        module = importlib.import_module("accounts.migrations.0002_phase6_user_security")

        class Editor:
            connection = connection

        module.check_existing_usernames(django_apps, Editor())  # all conform
        User.objects.create(username="bad name")
        with self.assertRaises(RuntimeError) as raised:
            module.check_existing_usernames(django_apps, Editor())
        self.assertIn("bad name", str(raised.exception))


class AccountCreationTests(GuardianFixture, TestCase):
    def test_recorded_guardian_has_no_access_until_granted(self):
        self.create_account()
        self.assertFalse(GuardianStudentAccess.objects.exists())

    def test_create_through_view_shows_password_once_with_no_store(self):
        url = reverse("core:guardian-account-create", args=[self.guardian.pk])
        response = self.client.post(url, {
            "username": "Meena.Rao", "identity_verification_method": METHOD,
            "identity_verification_note": "Aadhaar seen"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        password = response.context["password"]
        account = GuardianAccount.objects.get()
        self.assertEqual(account.user.username, "meena.rao")
        self.assertTrue(account.user.must_change_password)
        self.assertTrue(account.user.check_password(password))
        self.assertNotIn(password, account.user.password)
        detail = self.client.get(reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertNotContains(detail, password)
        for event in SecurityEvent.objects.all():
            self.assertNotIn(password, str(event.detail))

    def test_verification_is_required_and_recorded(self):
        with self.assertRaises(ValidationError):
            ga.create_guardian_account(guardian=self.guardian, username="meena", method=METHOD,
                                       note="  ", actor=self.admin)
        account, _ = self.create_account()
        self.assertEqual((account.identity_verified_by, account.identity_verification_method),
                         (self.admin, METHOD))

    def test_one_active_account_per_guardian(self):
        self.create_account()
        with self.assertRaises(ValidationError):
            self.create_account("meena.two")
        self.assertEqual(User.objects.filter(username="meena.two").count(), 0)

    def test_no_self_registration_route(self):
        for name in ("signup", "register", "password_reset", "django_registration_register"):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)


class LinkExistingLoginTests(GuardianFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user(username="rao", password="teacher-pass-1")
        self.teacher.groups.add(Group.objects.get(name="Teachers"))

    def test_teacher_login_is_linked_not_duplicated(self):
        users_before = User.objects.count()
        account = ga.link_existing_login(guardian=self.guardian, username="RAO", method=METHOD,
                                         note="Staff member, known", actor=self.admin)
        self.assertEqual(account.user, self.teacher)
        self.assertEqual(User.objects.count(), users_before)
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password("teacher-pass-1"))
        self.assertFalse(self.teacher.must_change_password)

    def test_never_guesses(self):
        for username in ("ra", "rao2", "Meena Rao", "98450-12345"):
            with self.subTest(username=username), self.assertRaises(ValidationError):
                ga.link_existing_login(guardian=self.guardian, username=username,
                                       method=METHOD, note="x", actor=self.admin)

    def test_login_linked_to_one_guardian_only(self):
        ga.link_existing_login(guardian=self.guardian, username="rao", method=METHOD,
                               note="x", actor=self.admin)
        other = Guardian.objects.create(full_name="Other")
        with self.assertRaises(ValidationError):
            ga.link_existing_login(guardian=other, username="rao", method=METHOD, note="x",
                                   actor=self.admin)

    def test_inactive_login_cannot_be_linked(self):
        self.teacher.is_active = False
        self.teacher.save()
        with self.assertRaises(ValidationError):
            ga.link_existing_login(guardian=self.guardian, username="rao", method=METHOD,
                                   note="x", actor=self.admin)


class GrantTests(GuardianFixture, TestCase):
    def test_grants_are_explicit_per_relationship(self):
        self.client.post(reverse("core:guardian-access-grant", args=[self.asha_link.pk]))
        grants = GuardianStudentAccess.objects.all()
        self.assertEqual([g.student_guardian for g in grants], [self.asha_link])
        self.assertEqual(SecurityEvent.objects.filter(event_type=Event.ACCESS_GRANTED).count(), 1)

    def test_double_grant_refused(self):
        ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        with self.assertRaises(ValidationError):
            ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)

    def test_revoke_requires_reason_and_regrant_is_new_row(self):
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        with self.assertRaises(ValidationError):
            ga.revoke_student_access(grant=grant, actor=self.admin, reason=" ")
        url = reverse("core:guardian-access-revoke", args=[grant.pk])
        self.client.post(url, {"reason": "Court order on file"})
        grant.refresh_from_db()
        self.assertFalse(grant.is_active)
        again = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        self.assertNotEqual(again.pk, grant.pk)
        self.assertNotEqual(again.public_id, grant.public_id)
        self.assertEqual(GuardianStudentAccess.objects.count(), 2)

    def test_relationship_type_never_grants(self):
        self.assertFalse(GuardianStudentAccess.objects.exists())
        page = self.client.get(reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertContains(page, "Not granted", count=2)


class RevocationAndSessionTests(GuardianFixture, TestCase):
    def guardian_client(self):
        account, password = self.create_account()
        client = self.client_class()
        client.login(username="meena.rao", password=password)
        client.post(reverse("password_change"), {
            "old_password": password, "new_password1": "Garden-Path-2026",
            "new_password2": "Garden-Path-2026"})
        return account, client

    def signed_in(self, client):
        return client.get(reverse("password_change")).status_code == 200

    def test_revoking_the_link_ends_sessions(self):
        account, client = self.guardian_client()
        self.assertTrue(self.signed_in(client))
        ga.revoke_account_link(account=account, actor=self.admin, reason="Requested by school")
        self.assertFalse(self.signed_in(client))

    def test_password_reset_ends_sessions_and_forces_change(self):
        account, client = self.guardian_client()
        url = reverse("core:guardian-account-reset-password", args=[account.pk])
        response = self.client.post(url)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(self.signed_in(client))
        account.user.refresh_from_db()
        self.assertTrue(account.user.must_change_password)
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=Event.PASSWORD_RESET_BY_ADMIN,
            event_class=SecurityEvent.EventClass.ROUTINE).exists())

    def test_revoked_link_cannot_be_reset_or_renamed(self):
        account, _ = self.guardian_client()
        ga.revoke_account_link(account=account, actor=self.admin, reason="x")
        with self.assertRaises(ValidationError):
            ga.reset_guardian_password(account=account, actor=self.admin)
        with self.assertRaises(ValidationError):
            ga.change_guardian_username(account=account, new_username="new.name",
                                        actor=self.admin)

    def test_username_change_uses_the_rule(self):
        account, _ = self.guardian_client()
        with self.assertRaises(ValidationError):
            ga.change_guardian_username(account=account, new_username="ADMIN", actor=self.admin)
        self.client.post(reverse("core:guardian-account-username", args=[account.pk]),
                         {"username": "Meena.R"})
        account.user.refresh_from_db()
        self.assertEqual(account.user.username, "meena.r")
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.USERNAME_CHANGED).exists())

    def test_session_version_is_part_of_the_session_hash(self):
        user = User.objects.get(username="admin")
        before = user.get_session_auth_hash()
        user.end_all_sessions()
        self.assertNotEqual(before, user.get_session_auth_hash())


class ForcedPasswordChangeTests(GuardianFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.account, self.password = self.create_account()
        self.guardian_client = self.client_class()
        self.guardian_client.login(username="meena.rao", password=self.password)

    def test_everything_redirects_to_password_change(self):
        change = reverse("password_change")
        for url in (reverse("home"), reverse("core:school-detail"), "/admin/",
                    reverse("core:my-home")):
            with self.subTest(url=url):
                self.assertRedirects(self.guardian_client.get(url), change,
                                     fetch_redirect_response=False)

    def test_allowed_endpoints(self):
        self.assertEqual(self.guardian_client.get(reverse("password_change")).status_code, 200)
        self.assertEqual(self.guardian_client.get("/no/such/page/").status_code, 404)
        response = self.guardian_client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], reverse("password_change"))

    def test_changing_clears_the_flag_and_is_audited(self):
        response = self.guardian_client.post(reverse("password_change"), {
            "old_password": self.password, "new_password1": "Garden-Path-2026",
            "new_password2": "Garden-Path-2026"})
        self.assertEqual(response.status_code, 302)
        self.account.user.refresh_from_db()
        self.assertFalse(self.account.user.must_change_password)
        self.assertEqual(self.guardian_client.get(reverse("password_change")).status_code, 200)
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.PASSWORD_CHANGED).exists())


class SiteAdministrationTests(GuardianFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.account, _ = self.create_account()
        self.superuser = User.objects.create_superuser(username="root", password="pass-12345")
        self.root = self.client_class()
        self.root.login(username="root", password="pass-12345")

    def test_guardian_password_cannot_be_changed_in_site_admin(self):
        url = reverse("admin:auth_user_password_change", args=[self.account.user.pk])
        self.assertEqual(self.root.get(url).status_code, 403)
        self.assertEqual(self.root.post(url, {"password1": "x", "password2": "x"}).status_code,
                         403)
        # Other logins still reach Django's own password view (not rendered here:
        # admin static files are not collected in tests).
        from unittest import mock

        from django.contrib import admin as site
        from django.contrib.auth.admin import UserAdmin
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.superuser
        with mock.patch.object(UserAdmin, "user_change_password",
                               return_value="django-view") as original:
            result = site.site._registry[User].user_change_password(request, str(self.admin.pk))
        self.assertEqual(result, "django-view")
        original.assert_called()

    def test_guardian_username_is_read_only_in_site_admin(self):
        form = ERPUserChangeForm(instance=self.account.user)
        self.assertTrue(form.fields["username"].disabled)
        self.assertFalse(ERPUserChangeForm(instance=self.admin).fields["username"].disabled)


class HistoryProtectionTests(GuardianFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.account, _ = self.create_account()
        self.grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)

    def test_links_and_grants_cannot_be_deleted(self):
        for table, pk in (("core_guardianaccount", self.account.pk),
                          ("core_guardianstudentaccess", self.grant.pk)):
            with self.subTest(table=table), self.assertRaises(IntegrityError):
                self.raw(f"DELETE FROM {table} WHERE id = %s", [pk])

    def test_identity_columns_cannot_be_rewritten(self):
        other = User.objects.create_user(username="other.user")
        cases = (
            ("core_guardianaccount", "user_id", other.pk, self.account.pk),
            ("core_guardianaccount", "identity_verification_note", "changed", self.account.pk),
            ("core_guardianstudentaccess", "student_guardian_id", self.ravi_link.pk,
             self.grant.pk),
        )
        for table, column, value, pk in cases:
            with self.subTest(column=column), self.assertRaises(IntegrityError):
                self.raw(f"UPDATE {table} SET {column} = %s WHERE id = %s", [value, pk])

    def test_revocation_is_final(self):
        ga.revoke_student_access(grant=self.grant, actor=self.admin, reason="x")
        with self.assertRaises(IntegrityError):
            self.raw("UPDATE core_guardianstudentaccess SET revoked_at = NULL, "
                     "revoked_by_id = NULL, revocation_reason = '' WHERE id = %s",
                     [self.grant.pk])
        with self.assertRaises(IntegrityError):
            self.raw("UPDATE core_guardianstudentaccess SET revocation_reason = 'other' "
                     "WHERE id = %s", [self.grant.pk])

    def test_incomplete_revocation_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuardianStudentAccess.objects.filter(pk=self.grant.pk).update(
                revoked_at=timezone.now())

    def test_second_active_link_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuardianAccount.objects.create(
                user=User.objects.create_user(username="second"), guardian=self.guardian,
                identity_verified_by=self.admin, identity_verification_method=METHOD,
                identity_verification_note="x", created_by=self.admin)


class SecurityEventTests(GuardianFixture, TestCase):
    def test_every_action_is_audited_in_the_right_class(self):
        account, _ = self.create_account()
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        ga.revoke_student_access(grant=grant, actor=self.admin, reason="x")
        ga.reset_guardian_password(account=account, actor=self.admin)
        ga.revoke_account_link(account=account, actor=self.admin, reason="x")
        classes = dict(SecurityEvent.objects.values_list("event_type", "event_class"))
        self.assertEqual(classes, {
            Event.ACCOUNT_CREATED: "HISTORY", Event.ACCESS_GRANTED: "HISTORY",
            Event.ACCESS_REVOKED: "HISTORY", Event.PASSWORD_RESET_BY_ADMIN: "ROUTINE",
            Event.ACCOUNT_LINK_REVOKED: "HISTORY"})

    def test_events_are_append_only(self):
        event = SecurityEvent.record(Event.LOGIN_SUCCEEDED, subject_user=self.admin)
        with self.assertRaises(IntegrityError):
            self.raw("UPDATE accounts_securityevent SET detail = %s WHERE id = %s",
                     ['{"x": 1}', event.pk])

    def test_retention_purge_rule(self):
        old = timezone.now() - timedelta(days=400)
        recent_routine = SecurityEvent.record(Event.LOGIN_FAILED)
        recent_history = SecurityEvent.record(Event.ACCOUNT_CREATED, guardian=self.guardian)
        old_routine = SecurityEvent.objects.create(event_type=Event.LOGIN_FAILED,
                                                   event_class="ROUTINE", occurred_at=old)
        old_history = SecurityEvent.objects.create(event_type=Event.ACCOUNT_CREATED,
                                                   event_class="HISTORY", occurred_at=old)
        self.raw("DELETE FROM accounts_securityevent WHERE id = %s", [old_routine.pk])
        self.assertFalse(SecurityEvent.objects.filter(pk=old_routine.pk).exists())
        for event in (old_history, recent_routine, recent_history):
            with self.subTest(event=event.event_type), self.assertRaises(IntegrityError):
                self.raw("DELETE FROM accounts_securityevent WHERE id = %s", [event.pk])


class AdminViewAuthorizationTests(GuardianFixture, TestCase):
    def test_teachers_and_plain_users_are_forbidden(self):
        account, _ = self.create_account()
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        plain = User.objects.create_user(username="plain", password="pass-12345")
        plain.groups.add(Group.objects.get(name="Teachers"))
        client = self.client_class()
        client.login(username="plain", password="pass-12345")
        urls = [
            reverse("core:guardian-account-create", args=[self.guardian.pk]),
            reverse("core:guardian-account-link", args=[self.guardian.pk]),
            reverse("core:guardian-account-revoke", args=[account.pk]),
            reverse("core:guardian-account-username", args=[account.pk]),
            reverse("core:guardian-account-reset-password", args=[account.pk]),
            reverse("core:guardian-access-grant", args=[self.ravi_link.pk]),
            reverse("core:guardian-access-revoke", args=[grant.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)
                self.assertEqual(client.post(url).status_code, 403)
