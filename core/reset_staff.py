"""Who may reset guardian passwords: the "Portal password resets" group (G-06 reset spec §6, §6a).

Superusers choose the members; every change made here is recorded. The group itself is created
only by migration core 0096, never here.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef

from accounts.models import SecurityEvent
from core.models import GuardianAccount

RESET_GROUP = "Portal password resets"
ADMIN_GROUP = "School Administrators"
CODENAME = "reset_guardian_password"
# Sign-in help spec §5.1: group members also work the "Can't sign in?" queue (core 0097).
QUEUE_CODENAMES = ("view_signinhelprequest", "change_signinhelprequest")
REMOVE_REASONS = (
    ("LEFT_SCHOOL", "Left the school"),
    ("CHANGED_ROLE", "Changed role"),
    ("OTHER", "Other"),
)
Event = SecurityEvent.EventType
User = get_user_model()


def reset_group():
    group = Group.objects.filter(name=RESET_GROUP).first()
    if group is None:
        raise ValidationError(
            f'The "{RESET_GROUP}" group is missing. It is created by the database migrations.'
        )
    return group


def _active_guardian_account():
    return Exists(GuardianAccount.objects.filter(user=OuterRef("pk"), revoked_at__isnull=True))


def eligible_users():
    """Active School Administrators who are not superusers or Django admin staff, not already
    members, and not linked to a guardian account (spec §6a)."""
    return (
        User.objects.filter(is_active=True, is_superuser=False, is_staff=False,
                            groups__name=ADMIN_GROUP)
        .exclude(groups__name=RESET_GROUP)
        .exclude(_active_guardian_account())
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def members():
    """Current members with "added on / by" and any reason they would no longer be eligible."""
    group = Group.objects.filter(name=RESET_GROUP).first()
    if group is None:
        return []
    users = list(
        group.user_set.annotate(has_guardian_account=_active_guardian_account())
        .prefetch_related("groups")
        .order_by("first_name", "last_name", "username")
    )
    added = {}
    for event in SecurityEvent.objects.filter(
        event_type=Event.RESET_STAFF_ADDED, subject_user__in=users
    ).select_related("actor").order_by("occurred_at", "pk"):
        added[event.subject_user_id] = event  # the latest wins
    rows = []
    for user in users:
        marks = []
        if not user.is_active:
            marks.append("inactive")
        if ADMIN_GROUP not in {g.name for g in user.groups.all()}:
            marks.append("not an administrator")
        if user.is_staff:
            marks.append("Django admin staff")
        if user.has_guardian_account:
            marks.append("now has a parent login")
        rows.append({"user": user, "added": added.get(user.pk), "marks": marks})
    return rows


def also_can_reset():
    """Everyone else who can reset, shown read-only: active superusers, direct grants, and any
    other group that was given the permission outside this page."""
    superusers = User.objects.filter(is_active=True, is_superuser=True).order_by("username")
    direct = (
        User.objects.filter(is_active=True, is_superuser=False,
                            user_permissions__codename=CODENAME,
                            user_permissions__content_type__app_label="core")
        .distinct()
        .order_by("username")
    )
    other_groups = (
        Group.objects.filter(permissions__codename=CODENAME,
                             permissions__content_type__app_label="core")
        .exclude(name=RESET_GROUP)
        .distinct()
        .order_by("name")
    )
    return {"superusers": list(superusers), "direct": list(direct), "groups": list(other_groups)}


def also_can_see_queue():
    """Everyone outside the group who can see sign-in help requests, shown read-only: active
    superusers, direct grants and other groups holding either queue permission (spec §5.1)."""
    queue = {"codename__in": QUEUE_CODENAMES, "content_type__app_label": "accounts"}
    superusers = User.objects.filter(is_active=True, is_superuser=True).order_by("username")
    direct = (
        User.objects.filter(is_active=True, is_superuser=False,
                            user_permissions__in=Permission.objects.filter(**queue))
        .distinct()
        .order_by("username")
    )
    other_groups = (
        Group.objects.filter(permissions__in=Permission.objects.filter(**queue))
        .exclude(name=RESET_GROUP)
        .distinct()
        .order_by("name")
    )
    return {"superusers": list(superusers), "direct": list(direct), "groups": list(other_groups)}


def queue_holders():
    """Active logins, superusers included, that can see sign-in help requests."""
    from django.db.models import Q

    queue = Permission.objects.filter(codename__in=QUEUE_CODENAMES,
                                      content_type__app_label="accounts")
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__permissions__in=queue) | Q(user_permissions__in=queue)
    ).distinct()


def recent_changes(limit=20):
    return list(
        SecurityEvent.objects.filter(
            event_type__in=[Event.RESET_STAFF_ADDED, Event.RESET_STAFF_REMOVED]
        )
        .select_related("actor", "subject_user")
        .order_by("-occurred_at", "-pk")[:limit]
    )


def add(user, *, actor):
    """Add an eligible administrator to the reset staff and record it."""
    with transaction.atomic():
        group = reset_group()
        user = User.objects.select_for_update().get(pk=user.pk)
        if not eligible_users().filter(pk=user.pk).exists():
            raise ValidationError("That login cannot be added to the password reset staff.")
        group.user_set.add(user)
        SecurityEvent.record(Event.RESET_STAFF_ADDED, actor=actor, subject_user=user)
    return user


def remove(user, *, actor, reason):
    """Remove a member and record why. Returns False, recording nothing, if they were not one.

    Only the group membership changes: direct grants and superuser status are untouched.
    """
    if reason not in {value for value, _ in REMOVE_REASONS}:
        raise ValidationError("Choose a reason.")
    with transaction.atomic():
        group = reset_group()
        user = User.objects.select_for_update().get(pk=user.pk)
        if not group.user_set.filter(pk=user.pk).exists():
            return False
        group.user_set.remove(user)
        SecurityEvent.record(Event.RESET_STAFF_REMOVED, actor=actor, subject_user=user,
                             detail={"reason": reason})
    return True
