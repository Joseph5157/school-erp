"""Report custom roles whose permissions leave a page limited or a file refused (Security Gate 4B).

    python manage.py role_permission_gaps

READ-ONLY: it only reads groups, users and permissions, never writes, and prints names only (group
names, usernames, permission names), never emails, passwords or personal data. It is safe to run
against a live database, for example to take an inventory of a deployment.

It lists, with what each missing permission costs:

* every custom group (the shipped "School Administrators" and "Teachers" groups are skipped);
* every login with permissions assigned to it directly, judged on its effective permissions
  (its own plus those from its groups). Superusers are skipped: they hold everything.

A gap is information, not an error. See docs/PERMISSIONS.md for the recommended combinations.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db.models import Count

from core import checks, permission_bundles, reset_staff
from core.models import TEACHERS_GROUP_NAME

SHIPPED_GROUPS = {"School Administrators", TEACHERS_GROUP_NAME}
NO_GAPS = "No incomplete permission combinations found."


def _names(permissions):
    return {f"{p.content_type.app_label}.{p.codename}" for p in permissions}


class Command(BaseCommand):
    help = "Read-only: list custom groups and directly-permissioned logins with incomplete permission combinations."

    def handle(self, *args, **options):
        self._reset_section()
        groups = self._group_sections()
        users = self._user_sections()
        if not groups and not users:
            self.stdout.write(NO_GAPS)
            return
        if groups:
            self.stdout.write("Custom groups with incomplete permission combinations:")
            for line in groups:
                self.stdout.write(line)
        if users:
            if groups:
                self.stdout.write("")
            self.stdout.write("Logins with directly assigned permissions and incomplete combinations:")
            for line in users:
                self.stdout.write(line)

    def _reset_section(self):
        """Who can reset guardian passwords (G-06 reset spec §6), for the periodic access review."""
        # Superusers hold everything and are never named in this report (see the module docstring).
        holders = checks.reset_holders().filter(is_superuser=False).order_by("username")
        self.stdout.write("Who can reset guardian passwords (plus every active superuser):")
        if not holders:
            self.stdout.write("  no staff yet (add them on the Password reset staff page)")
        for user in holders:
            how = "direct permission" if user.user_permissions.filter(
                codename="reset_guardian_password").exists() else "Portal password resets group"
            self.stdout.write(f"  {user.get_username()} ({how})")
        self.stdout.write("")
        self._queue_section()

    def _queue_section(self):
        """Who can see "Can't sign in?" requests (sign-in help spec §5.1). Superusers left out."""
        holders = reset_staff.queue_holders().filter(is_superuser=False).order_by("username")
        self.stdout.write("Who can see sign-in help requests (plus every active superuser):")
        if not holders:
            self.stdout.write("  no staff yet (members of Portal password resets see them)")
        for user in holders:
            how = "direct permission" if user.user_permissions.filter(
                codename__in=reset_staff.QUEUE_CODENAMES).exists() else "group permission"
            self.stdout.write(f"  {user.get_username()} ({how})")
        self.stdout.write("")

    def _gap_lines(self, permissions):
        return [
            f"    holds {held} but not {needed}: {effect}"
            for held, needed, effect in permission_bundles.gaps_for(permissions)
        ]

    def _group_sections(self):
        lines = []
        groups = (
            Group.objects.exclude(name__in=SHIPPED_GROUPS)
            .annotate(member_count=Count("user"))
            .prefetch_related("permissions__content_type")
            .order_by("name")
        )
        for group in groups:
            gaps = self._gap_lines(_names(group.permissions.all()))
            if gaps:
                members = f"{group.member_count} member" + ("" if group.member_count == 1 else "s")
                lines.append(f"  {group.name} ({members})")
                lines.extend(gaps)
        return lines

    def _user_sections(self):
        lines = []
        users = (
            get_user_model()
            .objects.filter(user_permissions__isnull=False, is_superuser=False)
            .distinct()
            .order_by("username")
        )
        for user in users:
            direct = _names(user.user_permissions.select_related("content_type"))
            from_groups = _names(
                Permission.objects.filter(group__user=user).select_related("content_type")
            )
            gaps = self._gap_lines(direct | from_groups)
            if gaps:
                suffix = "" if user.is_active else " (inactive)"
                lines.append(f"  {user.get_username()}{suffix}")
                lines.extend(gaps)
        return lines
