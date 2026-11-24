"""G-06: guardians who have never signed in (G06_NEVER_SIGNED_IN_SPEC.md)."""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core import guardian_activation as activation
from core.models import (
    AcademicEnrollment,
    ClassGrade,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Section,
    StudentGuardian,
)
from core.tests.test_admin_overview_analytics import AnalyticsFixture

User = get_user_model()
URL = reverse("core:guardian-never-signed-in")


class Fixture(AnalyticsFixture):
    def parent(self, *enrollments, name=None, last_login=None, must_change=True, active=True):
        """A guardian with a login, linked and granted to each enrollment's student."""
        n = Guardian.objects.count() + 1
        guardian = Guardian.objects.create(full_name=name or f"Parent {n}")
        user = User.objects.create_user(
            username=f"parent{n}", is_active=active, must_change_password=must_change
        )
        User.objects.filter(pk=user.pk).update(last_login=last_login)
        account = GuardianAccount.objects.create(
            user=user, guardian=guardian, identity_verified_by=self.admin_user,
            identity_verification_method="OTHER", identity_verification_note="x",
            created_by=self.admin_user,
        )
        account.grants = [
            GuardianStudentAccess.objects.create(
                student_guardian=StudentGuardian.objects.create(
                    student=e.student, guardian=guardian, relationship_type="MOTHER"
                ),
                granted_by=self.admin_user,
            )
            for e in enrollments
        ]
        return account

    def listed(self, chip=activation.NEVER, student_ids=None):
        return set(activation.unused_accounts(chip, student_ids))

    def login_with(self, *perms):
        user = User.objects.create_user(username=f"staff{User.objects.count()}", password="pw-12345")
        for perm in perms:
            app, codename = perm.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app, codename=codename)
            )
        client = self.client_class()
        client.login(username=user.username, password="pw-12345")
        return client

    def end_placement(self, enrollment):
        AcademicEnrollment.objects.filter(pk=enrollment.pk).update(
            status="COMPLETED", end_date=datetime.date(2026, 7, 1)
        )

    def revoke(self, grant):
        GuardianStudentAccess.objects.filter(pk=grant.pk).update(
            revoked_at=timezone.now(), revoked_by=self.admin_user, revocation_reason="x"
        )


class WhichAccountsCountTests(Fixture, TestCase):
    def test_never_signed_in_is_listed_and_signed_in_is_not(self):
        never = self.parent(self.s1)
        self.parent(self.s2, last_login=timezone.now(), must_change=False)
        self.assertEqual(self.listed(), {never})

    def test_temporary_password_chip(self):
        temp = self.parent(self.s1, last_login=timezone.now(), must_change=True)
        never = self.parent(self.s2)
        self.assertEqual(self.listed(activation.TEMPORARY), {temp})
        self.assertEqual(self.listed(), {never})

    def test_inactive_login_is_excluded(self):
        self.parent(self.s1, active=False)
        self.assertEqual(self.listed(), set())

    def test_revoked_link_excluded_and_new_link_listed_on_its_own(self):
        old = self.parent(self.s1)
        GuardianAccount.objects.filter(pk=old.pk).update(
            revoked_at=timezone.now(), revoked_by=self.admin_user, revocation_reason="wrong person"
        )
        self.assertEqual(self.listed(), set())
        new = GuardianAccount.objects.create(
            user=User.objects.create_user(username="fresh"), guardian=old.guardian,
            identity_verified_by=self.admin_user, identity_verification_method="OTHER",
            identity_verification_note="x", created_by=self.admin_user,
        )
        self.assertEqual(self.listed(), {new})

    def test_all_grants_revoked_excluded_one_active_listed(self):
        account = self.parent(self.s1, self.s2)
        self.revoke(account.grants[0])
        self.assertEqual(self.listed(), {account})
        self.revoke(account.grants[1])
        self.assertEqual(self.listed(), set())

    def test_ended_relationship_is_excluded(self):
        account = self.parent(self.s1)
        StudentGuardian.objects.filter(pk=account.grants[0].student_guardian_id).update(
            ended_at=timezone.now(), ended_by=self.admin_user, end_reason="moved away"
        )
        self.assertEqual(self.listed(), set())

    def test_login_that_signed_in_elsewhere_is_not_listed(self):
        # A teacher-parent: last_login belongs to the login, so a teacher sign-in hides it (§2).
        self.parent(self.s1, last_login=timezone.now(), must_change=False)
        self.assertEqual(self.listed(), set())
        self.assertEqual(self.listed(activation.TEMPORARY), set())

    def test_office_reset_after_use_shows_under_temporary(self):
        account = self.parent(self.s1, last_login=timezone.now(), must_change=False)
        User.objects.filter(pk=account.user_id).update(must_change_password=True)
        self.assertEqual(self.listed(activation.TEMPORARY), {account})


class PermissionTests(Fixture, TestCase):
    def test_both_permissions_allowed(self):
        client = self.login_with("core.view_guardianaccount", "core.view_guardian")
        self.assertEqual(client.get(URL).status_code, 200)

    def test_only_account_permission_refused(self):
        self.assertEqual(self.login_with("core.view_guardianaccount").get(URL).status_code, 403)

    def test_only_guardian_permission_refused(self):
        self.assertEqual(self.login_with("core.view_guardian").get(URL).status_code, 403)

    def test_teacher_refused_and_anonymous_redirected(self):
        self.assertEqual(self.non_admin.get(URL).status_code, 403)
        response = self.anonymous.get(URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_guardian_login_refused(self):
        account = self.parent(self.s1, must_change=False)
        account.user.set_password("pw-12345")
        account.user.save()
        client = self.client_class()
        client.login(username=account.user.username, password="pw-12345")
        self.assertEqual(client.get(URL).status_code, 403)

    def test_post_not_allowed(self):
        self.assertEqual(self.administrator.post(URL).status_code, 405)

    def test_without_view_student_no_children_and_filters_ignored(self):
        self.parent(self.s1, name="Asha Mother")
        other_grade = ClassGrade.objects.create(name="Grade 9")
        client = self.login_with("core.view_guardianaccount", "core.view_guardian")
        response = client.get(URL, {"class": other_grade.pk})
        self.assertContains(response, "Asha Mother")
        self.assertNotContains(response, "Children with access")
        self.assertNotContains(response, 'name="class"')

    def test_no_reset_link_in_v1(self):
        account = self.parent(self.s1)
        response = self.superuser_client.get(URL)
        self.assertContains(response, account.guardian.full_name)
        self.assertNotContains(
            response, reverse("core:guardian-account-reset-password", args=[account.pk])
        )
        self.assertNotContains(response, "Reset password")


class PageTests(Fixture, TestCase):
    def test_lists_child_first_name_class_and_no_review_flag(self):
        self.parent(self.s1, name="Meena Mother")
        response = self.administrator.get(URL)
        self.assertContains(response, "Meena Mother")
        self.assertContains(response, self.s1.student.full_name.split()[0])
        self.assertContains(response, f"{self.class_grade.name} {self.section.name}")
        self.assertNotContains(response, "Access under review")

    def test_grant_pending_review_is_listed_with_flag(self):
        account = self.parent(self.s1)
        self.end_placement(self.s1)
        self.assertEqual(self.listed(), {account})
        self.assertContains(self.administrator.get(URL), "Access under review")

    def test_class_and_section_filters(self):
        grade = ClassGrade.objects.create(name="Grade 2")
        section_b = Section.objects.create(class_grade=grade, name="B")
        other = self.enroll_student("Other Child", grade, section_b)
        self.parent(self.s1, name="First Parent")
        self.parent(other, name="Second Parent")
        by_class = self.administrator.get(URL, {"class": grade.pk})
        self.assertContains(by_class, "Second Parent")
        self.assertNotContains(by_class, "First Parent")
        by_section = self.administrator.get(URL, {"section": self.section.pk})
        self.assertContains(by_section, "First Parent")
        self.assertNotContains(by_section, "Second Parent")

    def test_two_children_two_sections_match_either_and_appear_once(self):
        grade = ClassGrade.objects.create(name="Grade 2")
        section_b = Section.objects.create(class_grade=grade, name="B")
        other = self.enroll_student("Other Child", grade, section_b)
        account = self.parent(self.s1, other)
        for section in (self.section, section_b):
            response = self.administrator.get(URL, {"section": section.pk})
            self.assertEqual(list(response.context["accounts"]), [account])

    def test_unplaced_student_listed_without_filter_not_with_class_filter(self):
        self.parent(self.s1, name="Unplaced Parent")
        self.end_placement(self.s1)
        self.assertContains(self.administrator.get(URL), "Unplaced Parent")
        self.assertNotContains(
            self.administrator.get(URL, {"class": self.class_grade.pk}), "Unplaced Parent"
        )

    def test_empty_states(self):
        self.assertContains(self.administrator.get(URL), "No guardian portal accounts yet.")
        self.parent(self.s1, last_login=timezone.now(), must_change=False)
        self.assertContains(
            self.administrator.get(URL),
            "Every guardian with portal access has signed in at least once.",
        )
        grade = ClassGrade.objects.create(name="Grade 2")
        self.parent(self.s2)
        self.assertContains(
            self.administrator.get(URL, {"class": grade.pk}),
            "No guardians in this class or section are waiting to sign in.",
        )

    def test_query_count_does_not_grow_with_rows(self):
        self.parent(self.s1)
        with CaptureQueriesContext(connection) as one:
            self.administrator.get(URL)
        for _ in range(3):
            self.parent(self.s1, self.s2)
        with CaptureQueriesContext(connection) as many:
            self.administrator.get(URL)
        self.assertEqual(len(one), len(many))


class LinkTests(Fixture, TestCase):
    def test_parents_tab_shows_count_only_for_permitted_users(self):
        self.parent(self.s1)
        self.parent(self.s2)
        home = reverse("core:admin-overview")
        response = self.administrator.get(home, {"tab": "parents"})
        self.assertContains(response, "2 accounts never signed in")
        self.assertContains(response, URL)
        client = self.login_with("core.view_school", "core.view_guardian")
        self.assertNotContains(client.get(home, {"tab": "parents"}), URL)

    def test_guardian_list_link_only_with_account_permission(self):
        self.assertContains(self.administrator.get(reverse("core:guardian-list")), URL)
        client = self.login_with("core.view_guardian")
        self.assertNotContains(client.get(reverse("core:guardian-list")), URL)
