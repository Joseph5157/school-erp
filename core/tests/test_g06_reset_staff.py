"""G-06 reset spec PR 2b (§6a): the "Password reset staff" page."""
import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import guardian_accounts as ga
from core import reset_staff
from core.models import Guardian, GuardianAccount

Event = SecurityEvent.EventType
User = get_user_model()
LIST = reverse("core:reset-staff")
ADD = reverse("core:reset-staff-add")


def remove_url(user):
    return reverse("core:reset-staff-remove", args=[user.pk])


class Fixture:
    def setUp(self):
        super().setUp()
        self.admins = Group.objects.get(name="School Administrators")
        self.group = Group.objects.get(name=reset_staff.RESET_GROUP)
        self.root = User.objects.create_superuser("root", password="pass-12345")
        self.office = self.admin_user("office", "Asha", "Office")
        self.root_client = self.client_for("root")
        self.office_client = self.client_for("office")

    def admin_user(self, username, first="", last="", **extra):
        user = User.objects.create_user(username=username, password="pass-12345",
                                        first_name=first, last_name=last, **extra)
        user.groups.add(self.admins)
        return user

    def client_for(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def parent_link(self, user):
        return GuardianAccount.objects.create(
            user=user, guardian=Guardian.objects.create(full_name="Parent"),
            identity_verified_by=self.root, identity_verification_method="OTHER",
            identity_verification_note="x", created_by=self.root)

    def events(self, event_type):
        return SecurityEvent.objects.filter(event_type=event_type)


class AccessTests(Fixture, TestCase):
    def test_administrator_sees_the_list_without_controls(self):
        response = self.office_client.get(LIST)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ADD)
        self.assertNotContains(response, ">Remove<")

    def test_administrator_posts_are_refused(self):
        self.assertEqual(self.office_client.post(ADD, {"user": self.office.pk}).status_code, 403)
        member = self.admin_user("member")
        self.group.user_set.add(member)
        response = self.office_client.post(remove_url(member), {"reason": "LEFT_SCHOOL"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.group.user_set.filter(pk=self.office.pk).exists())
        self.assertTrue(self.group.user_set.filter(pk=member.pk).exists())

    def test_teacher_refused_and_anonymous_redirected(self):
        teacher = User.objects.create_user("teach", password="pass-12345")
        teacher.groups.add(Group.objects.get(name="Teachers"))
        self.assertEqual(self.client_for("teach").get(LIST).status_code, 403)
        anonymous = self.client_class().get(LIST)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("login"), anonymous["Location"])
        self.assertEqual(self.client_class().post(ADD).status_code, 302)

    def test_get_on_post_routes(self):
        self.assertEqual(self.root_client.get(ADD).status_code, 405)
        self.assertEqual(self.office_client.get(ADD).status_code, 403)  # superuser check first

    def test_superuser_sees_controls(self):
        self.assertContains(self.root_client.get(LIST), ADD)


class AddRemoveTests(Fixture, TestCase):
    def test_superuser_adds_and_removes_with_events(self):
        self.assertRedirects(self.root_client.post(ADD, {"user": self.office.pk}), LIST)
        self.assertTrue(self.group.user_set.filter(pk=self.office.pk).exists())
        added = self.events(Event.RESET_STAFF_ADDED).get()
        self.assertEqual((added.actor, added.subject_user), (self.root, self.office))
        self.assertEqual(added.event_class, SecurityEvent.EventClass.ROUTINE)
        self.root_client.post(remove_url(self.office), {"reason": "CHANGED_ROLE"})
        self.assertFalse(self.group.user_set.filter(pk=self.office.pk).exists())
        removed = self.events(Event.RESET_STAFF_REMOVED).get()
        self.assertEqual(removed.detail, {"reason": "CHANGED_ROLE"})
        self.assertEqual(removed.event_class, SecurityEvent.EventClass.ROUTINE)

    def test_membership_applies_from_the_next_request(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        account, _ = ga.create_guardian_account(guardian=guardian, username="meena.rao",
                                                method="IN_PERSON_DOCUMENTS", note="Seen",
                                                actor=self.root)
        url = reverse("core:guardian-account-reset-password", args=[account.pk])
        self.assertEqual(self.office_client.get(url).status_code, 403)
        reset_staff.add(self.office, actor=self.root)
        self.assertEqual(self.office_client.get(url).status_code, 200)
        reset_staff.remove(self.office, actor=self.root, reason="LEFT_SCHOOL")
        self.assertEqual(self.office_client.get(url).status_code, 403)  # same session, no sign-out

    def test_ineligible_users_are_not_offered_and_are_refused(self):
        inactive = self.admin_user("inactive", is_active=False)
        staff = self.admin_user("staffer", is_staff=True)
        outsider = User.objects.create_user("outsider")
        member = self.admin_user("member")
        self.group.user_set.add(member)
        parent = self.admin_user("parentadmin")
        self.parent_link(parent)
        self.assertEqual(set(reset_staff.eligible_users()), {self.office})
        for user in (inactive, staff, outsider, member, parent, self.root):
            with self.subTest(user=user.username):
                with self.assertRaises(ValidationError):
                    reset_staff.add(user, actor=self.root)
                self.assertRedirects(self.root_client.post(ADD, {"user": user.pk}), LIST)
        self.assertFalse(self.events(Event.RESET_STAFF_ADDED).exists())

    def test_remove_non_member_is_404_and_records_nothing(self):
        direct = self.admin_user("direct")
        direct.user_permissions.add(Permission.objects.get(codename="reset_guardian_password"))
        for user in (self.office, self.root, direct):
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.root_client.post(remove_url(user), {"reason": "OTHER"}).status_code, 404)
        self.assertFalse(self.events(Event.RESET_STAFF_REMOVED).exists())
        self.assertTrue(direct.user_permissions.filter(codename="reset_guardian_password").exists())

    def test_second_remove_changes_nothing(self):
        reset_staff.add(self.office, actor=self.root)
        self.assertTrue(reset_staff.remove(self.office, actor=self.root, reason="OTHER"))
        self.assertFalse(reset_staff.remove(self.office, actor=self.root, reason="OTHER"))
        self.assertEqual(self.events(Event.RESET_STAFF_REMOVED).count(), 1)

    def test_remove_needs_a_valid_reason(self):
        reset_staff.add(self.office, actor=self.root)
        self.root_client.post(remove_url(self.office), {"reason": "because"})
        self.assertTrue(self.group.user_set.filter(pk=self.office.pk).exists())

    def test_missing_group_on_remove_redirects_with_a_message(self):
        self.group.delete()
        response = self.root_client.post(remove_url(self.office), {"reason": "OTHER"})
        self.assertRedirects(response, LIST)

    def test_lost_remove_race_says_already_removed(self):
        reset_staff.add(self.office, actor=self.root)
        with mock.patch.object(reset_staff, "remove", return_value=False):
            response = self.root_client.post(remove_url(self.office), {"reason": "OTHER"},
                                             follow=True)
        self.assertContains(response, "Already removed.")

    def test_missing_group_fails_closed(self):
        self.group.delete()
        with self.assertRaises(ValidationError):
            reset_staff.add(self.office, actor=self.root)
        self.assertFalse(Group.objects.filter(name=reset_staff.RESET_GROUP).exists())


class PageContentTests(Fixture, TestCase):
    def test_empty_warning_and_can_also_reset(self):
        direct = self.admin_user("direct")
        direct.user_permissions.add(Permission.objects.get(codename="reset_guardian_password"))
        page = self.office_client.get(LIST)
        self.assertContains(page, "No staff can reset parent passwords.")
        self.assertContains(page, "root (root) &middot; superuser")
        self.assertContains(page, "granted outside this page")

    def test_marks_and_unknown_added_by(self):
        member = self.admin_user("member")
        self.group.user_set.add(member)  # added outside the page: no event
        self.parent_link(member)
        page = self.office_client.get(LIST)
        self.assertContains(page, "now has a parent login")
        self.assertContains(page, "Added more than a year ago or outside this page")

    def test_member_with_a_parent_login_cannot_reset_their_own(self):
        member = self.admin_user("member")
        self.group.user_set.add(member)
        account = self.parent_link(member)
        with self.assertRaises(ValidationError):
            ga.reset_guardian_password(account=account, actor=member, method="IN_PERSON_DOCUMENTS")

    def test_recent_changes_last_twenty(self):
        for _ in range(11):
            reset_staff.add(self.office, actor=self.root)
            reset_staff.remove(self.office, actor=self.root, reason="OTHER")
        page = self.office_client.get(LIST)
        self.assertEqual(len(page.context["changes"]), 20)
        self.assertContains(page, "(Other)")

    def test_no_email_addresses_shown(self):
        self.office.email = "asha.office@example.com"
        self.office.save()
        reset_staff.add(self.office, actor=self.root)
        self.assertNotContains(self.office_client.get(LIST), "asha.office@example.com")


class GuardTests(TestCase):
    def test_post_routes_carry_superuser_required(self):
        inventory = json.loads(Path("core/tests/route_permissions.json").read_text(encoding="utf-8"))
        for name in ("core:reset-staff-add", "core:reset-staff-remove"):
            with self.subTest(route=name):
                self.assertIn("superuser_required", inventory[name]["flags"])
                self.assertIn("require_POST", inventory[name]["flags"])

    def test_no_shipped_group_can_edit_users_or_groups(self):
        risky = Permission.objects.filter(
            codename__in=["change_user", "change_group", "change_permission"],
            content_type__app_label__in=["auth", "accounts"],
        )
        self.assertFalse(Group.objects.filter(permissions__in=risky).exists())
