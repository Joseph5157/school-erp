"""Shared helpers for the Security Gate 4B tests (data-class permissions).

A custom role is a login holding some permissions but not others. Permissions reach a login
two ways, directly or through a group, and both must be honoured, so every helper builds the
same permission set both ways.
"""

import itertools

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

User = get_user_model()
_counter = itertools.count(1)

# Synthetic markers that must (or must not) show up on a page.
GUARDIAN_PHONE = "9876501234"
GUARDIAN_EMAIL = "meena.rao@example.test"


def permission_objects(*perms):
    found = []
    for perm in perms:
        app_label, codename = perm.split(".")
        found.append(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return found


def client_with(client_class, *perms, via="direct"):
    """A signed-in client whose login holds exactly `perms`, directly or through a group."""
    number = next(_counter)
    user = User.objects.create_user(f"gate4b-{via}-{number}", password="pass-12345")
    objects = permission_objects(*perms)
    if via == "group":
        group = Group.objects.create(name=f"Gate 4B custom role {number}")
        group.permissions.add(*objects)
        user.groups.add(group)
    else:
        user.user_permissions.add(*objects)
    client = client_class()
    assert client.login(username=user.username, password="pass-12345")
    return client


def holders(client_class, *perms):
    """[(how, client), ...]: the same permission set held directly and through a group."""
    return [(via, client_with(client_class, *perms, via=via)) for via in ("direct", "group")]
