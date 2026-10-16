"""Phase 3D: teacher login workflows (audit F09).

A teacher is an active login in the Teachers group; classes and subjects come
from the existing assignment pages. Every workflow is atomic and audited with
a SecurityEvent, and works only on Teachers-group logins that are not
superusers, staff or administrators. Temporary passwords are returned once to the caller for display
on a slip and are never stored in plain text, logged or put in an audit
detail.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count

from accounts.models import SecurityEvent
from accounts.usernames import clean_new_username
from core.guardian_accounts import generate_temporary_password
from core.models import TEACHERS_GROUP_NAME, GuardianAccount

Event = SecurityEvent.EventType
NOT_A_TEACHER = "That login is not a teacher account."


def _manageable_teachers(queryset):
    """Plain teacher logins only: the single predicate for the list, detail and lock.

    A target is in the Teachers group and is not a superuser or staff, holds no
    direct permission, belongs to no other group (so never School Administrators
    or any other role) and has no active Guardian Portal link. Anyone with
    another role is managed in the Django admin: letting one manager reset
    their password would be privilege escalation or a portal takeover.
    Subqueries keep the Count annotations in teacher_queryset unaffected.
    """
    user_model = get_user_model()
    return (
        queryset.filter(groups__name=TEACHERS_GROUP_NAME, is_superuser=False, is_staff=False)
        .exclude(pk__in=user_model.user_permissions.through.objects.values("user_id"))
        .exclude(
            pk__in=user_model.groups.through.objects.exclude(
                group__name=TEACHERS_GROUP_NAME
            ).values("user_id")
        )
        .exclude(
            pk__in=GuardianAccount.objects.filter(revoked_at__isnull=True).values("user_id")
        )
    )


def teacher_queryset():
    """Manageable Teachers-group logins (active and inactive)."""
    return (
        _manageable_teachers(get_user_model().objects.all())
        .annotate(
            assignment_count=Count("assessment_assignments", distinct=True)
            + Count("class_teacher_assignments", distinct=True)
        )
    )


def _lock_teacher(user):
    """The row-locked Teachers-group login, or ValidationError. Use inside atomic()."""
    if not _manageable_teachers(get_user_model().objects.all()).filter(pk=user.pk).exists():
        raise ValidationError(NOT_A_TEACHER)
    locked = get_user_model().objects.select_for_update().filter(pk=user.pk).first()
    # Re-check on the locked row: status may have changed while we waited.
    if locked is None or not _manageable_teachers(
        get_user_model().objects.filter(pk=locked.pk)
    ).exists():
        raise ValidationError(NOT_A_TEACHER)
    return locked


def create_teacher(*, username, first_name, last_name, email, actor):
    """Create a Teachers-group login. Returns (user, temporary password)."""
    username = clean_new_username(username)
    password = generate_temporary_password()
    try:
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=username,
                password=password,
                first_name=(first_name or "").strip(),
                last_name=(last_name or "").strip(),
                email=(email or "").strip(),
            )
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])
            group, _ = Group.objects.get_or_create(name=TEACHERS_GROUP_NAME)
            user.groups.add(group)
            SecurityEvent.record(Event.TEACHER_ACCOUNT_CREATED, actor=actor, subject_user=user)
    except IntegrityError as error:
        raise ValidationError("That username is not available.") from error
    return user, password


def reset_teacher_password(*, user, actor):
    """New temporary password, forced change, every session ended. Returns the password."""
    password = generate_temporary_password()
    with transaction.atomic():
        locked = _lock_teacher(user)
        if getattr(actor, "pk", None) == locked.pk:
            raise ValidationError("You cannot reset your own password here.")
        locked.set_password(password)
        locked.must_change_password = True
        locked.save(update_fields=["password", "must_change_password"])
        locked.end_all_sessions()
        SecurityEvent.record(Event.TEACHER_PASSWORD_RESET, actor=actor, subject_user=locked)
    return password


def change_teacher_username(*, user, new_username, actor):
    """Mirror core.guardian_accounts.change_guardian_username for a teacher."""
    with transaction.atomic():
        locked = _lock_teacher(user)
        if getattr(actor, "pk", None) == locked.pk:
            raise ValidationError("You cannot change your own username here.")
        username = clean_new_username(new_username, exclude_user=locked)
        locked.username = username
        try:
            locked.save(update_fields=["username"])
        except IntegrityError as error:
            raise ValidationError("That username is not available.") from error
        SecurityEvent.record(Event.TEACHER_USERNAME_CHANGED, actor=actor, subject_user=locked)
    return username


def deactivate_teacher(*, user, reason, actor):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    with transaction.atomic():
        locked = _lock_teacher(user)
        if getattr(actor, "pk", None) == locked.pk:
            raise ValidationError("You cannot deactivate your own login.")
        if not locked.is_active:
            raise ValidationError("This teacher is already inactive.")
        locked.is_active = False
        locked.save(update_fields=["is_active"])
        locked.end_all_sessions()
        SecurityEvent.record(
            Event.TEACHER_DEACTIVATED, actor=actor, subject_user=locked,
            detail={"reason": reason[:200]},
        )
    return locked


def reactivate_teacher(*, user, actor):
    with transaction.atomic():
        locked = _lock_teacher(user)
        if locked.is_active:
            raise ValidationError("This teacher is already active.")
        locked.is_active = True
        locked.save(update_fields=["is_active"])
        SecurityEvent.record(Event.TEACHER_REACTIVATED, actor=actor, subject_user=locked)
    return locked
