"""Security Gate 4B: the read-only `role_permission_gaps` command.

It lists custom groups and directly-assigned logins whose permissions leave a page limited or a
file refused (for example `view_student` without `view_guardian`). It is an inventory for the
operator, safe to run against a live database: it never writes, and it never prints passwords,
emails or other personal data, only group names, usernames and permission names.
"""

import io

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from core import permission_bundles
from core.tests.gate4b_support import User, permission_objects

NO_GAPS = "No incomplete permission combinations found."


class RefuseWrites:
    """A database wrapper that fails the test on any statement that is not a read."""

    def __call__(self, execute, sql, params, many, context):
        if not str(sql).lstrip().upper().startswith(("SELECT", "WITH")):
            raise AssertionError(f"The command wrote to the database: {sql[:80]}")
        return execute(sql, params, many, context)


def run(*args):
    out = io.StringIO()
    with connection.execute_wrapper(RefuseWrites()):
        call_command("role_permission_gaps", *args, stdout=out)
    return out.getvalue()


def group_with(name, *perms):
    group = Group.objects.create(name=name)
    group.permissions.add(*permission_objects(*perms))
    return group


class GapRulesTests(TestCase):
    def test_a_host_permission_without_its_companion_is_a_gap(self):
        gaps = permission_bundles.gaps_for({"core.view_student"})
        missing = {(held, needed) for held, needed, _ in gaps}
        self.assertIn(("core.view_student", "core.view_guardian"), missing)
        self.assertIn(("core.view_student", "core.view_attendanceentry"), missing)

    def test_holding_the_companions_leaves_no_gap(self):
        perms = {"core.view_student", "core.view_guardian", "core.view_applicant",
                 "core.view_attendanceentry"}
        self.assertEqual(permission_bundles.gaps_for(perms), [])

    def test_unrelated_permissions_have_no_gaps(self):
        self.assertEqual(permission_bundles.gaps_for({"core.view_subject"}), [])

    def test_every_rule_names_real_permissions(self):
        names = {
            perm for held, needed, _ in permission_bundles.COMPANIONS for perm in (held, needed)
        }
        known = {
            f"{p.content_type.app_label}.{p.codename}" for p in permission_objects(*names)
        }
        for held, needed, effect in permission_bundles.COMPANIONS:
            self.assertIn(held, known)
            self.assertIn(needed, known)
            self.assertTrue(effect)


class GroupReportTests(TestCase):
    def test_a_custom_group_with_a_gap_is_reported(self):
        group = group_with("Front desk", "core.view_student")
        group.user_set.add(User.objects.create_user("clerk", password="x-pass-12345"))
        output = run()
        self.assertIn("Front desk", output)
        self.assertIn("1 member", output)
        self.assertIn("core.view_student", output)
        self.assertIn("core.view_guardian", output)
        self.assertIn("core.view_attendanceentry", output)

    def test_a_custom_group_with_its_companions_is_not_reported(self):
        group_with("Registrar", "core.view_student", "core.view_guardian",
                   "core.view_applicant", "core.view_attendanceentry")
        self.assertNotIn("Registrar", run())

    def test_the_shipped_groups_are_never_listed(self):
        output = run()
        self.assertNotIn("School Administrators", output)
        self.assertNotIn("Teachers", output)

    def test_output_is_sorted_and_stable(self):
        group_with("Zeta role", "core.view_student")
        group_with("Alpha role", "core.view_student")
        output = run()
        self.assertLess(output.index("Alpha role"), output.index("Zeta role"))
        self.assertEqual(output, run())


class DirectUserReportTests(TestCase):
    def user(self, name, *perms, **extra):
        user = User.objects.create_user(name, password="x-pass-12345", **extra)
        user.user_permissions.add(*permission_objects(*perms))
        return user

    def test_a_login_with_direct_permissions_and_a_gap_is_reported(self):
        self.user("import.viewer", "core.view_importbatch")
        output = run()
        self.assertIn("import.viewer", output)
        self.assertIn("core.run_import", output)

    def test_a_group_can_supply_the_missing_companion(self):
        user = self.user("both.ways", "core.view_importbatch")
        user.groups.add(group_with("Importers", "core.run_import"))
        self.assertNotIn("both.ways", run())

    def test_a_login_with_only_a_group_is_covered_by_the_group_not_listed_itself(self):
        group = group_with("Partial role", "core.view_student")
        group.user_set.add(User.objects.create_user("member", password="x-pass-12345"))
        output = run()
        self.assertIn("Partial role", output)
        self.assertNotIn("member\n", output)

    def test_superusers_and_logins_without_direct_permissions_are_skipped(self):
        User.objects.create_superuser("root", password="x-pass-12345")
        User.objects.create_user("plain", password="x-pass-12345")
        output = run()
        self.assertNotIn("root", output)
        self.assertNotIn("plain", output)
        self.assertIn(NO_GAPS, output)

    def test_an_inactive_login_is_still_listed_and_marked(self):
        self.user("old.clerk", "core.view_student", is_active=False)
        output = run()
        self.assertIn("old.clerk", output)
        self.assertIn("inactive", output)

    def test_it_prints_names_only_never_emails_or_passwords(self):
        self.user("careful", "core.view_student", email="careful.private@example.test")
        output = run()
        self.assertIn("careful", output)
        self.assertNotIn("careful.private@example.test", output)
        self.assertNotIn("pbkdf2", output)


class ReadOnlyTests(TestCase):
    def test_it_changes_no_rows(self):
        group_with("Front desk", "core.view_student")
        User.objects.create_user("clerk", password="x-pass-12345").user_permissions.add(
            *permission_objects("core.view_importbatch")
        )
        before = (Group.objects.count(), User.objects.count(),
                  Group.permissions.through.objects.count(),
                  User.user_permissions.through.objects.count())
        run()
        after = (Group.objects.count(), User.objects.count(),
                 Group.permissions.through.objects.count(),
                 User.user_permissions.through.objects.count())
        self.assertEqual(before, after)

    def test_it_runs_cleanly_with_nothing_to_report(self):
        self.assertIn(NO_GAPS, run())
