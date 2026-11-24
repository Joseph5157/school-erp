"""System checks for the core app."""
from django.core.checks import Tags, Warning, register
from django.db import DatabaseError


def reset_holders():
    """Active logins that can reset guardian passwords (G-06 reset spec §6): superusers, and
    anyone holding the permission through a group or directly."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    return get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True)
        | Q(groups__permissions__codename="reset_guardian_password",
            groups__permissions__content_type__app_label="core")
        | Q(user_permissions__codename="reset_guardian_password",
            user_permissions__content_type__app_label="core")
    ).distinct()


@register(Tags.database)
def check_someone_can_reset(app_configs=None, **kwargs):
    """Warn (never an error: fresh installs and test databases have nobody yet)."""
    try:
        if reset_holders().exists():
            return []
    except DatabaseError:  # not migrated yet
        return []
    return [
        Warning(
            "No active login can reset guardian passwords.",
            hint='Add staff on the "Password reset staff" page, or as a superuser in the '
                 'Django admin group "Portal password resets".',
            id="core.W001",
        )
    ]
