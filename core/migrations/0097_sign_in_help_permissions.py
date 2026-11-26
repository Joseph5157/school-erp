# Sign-in help spec §5.1 (ADR 0029 OD-G14, OD-H2): the "Can't sign in?" queue has its own view and
# change permissions. The staff who reset parent passwords also work the queue, so both go to the
# "Portal password resets" group when it exists. Never reuses core.reset_guardian_password.

from django.contrib.auth.management import create_permissions
from django.db import migrations

RESET_GROUP = "Portal password resets"
CODENAMES = ("view_signinhelprequest", "change_signinhelprequest")


def _permissions(apps, alias):
    # Permissions normally appear only after post_migrate; create them now, as core 0096 does.
    config = apps.get_app_config("accounts")
    config.models_module = True
    create_permissions(config, verbosity=0, using=alias, apps=apps)
    config.models_module = None
    Permission = apps.get_model("auth", "Permission")
    return list(
        Permission.objects.using(alias).filter(
            content_type__app_label="accounts", codename__in=CODENAMES
        )
    )


def grant_to_reset_group(apps, schema_editor):
    alias = schema_editor.connection.alias
    permissions = _permissions(apps, alias)
    group = apps.get_model("auth", "Group").objects.using(alias).filter(name=RESET_GROUP).first()
    if group is not None:  # without the group only superusers see the queue
        group.permissions.add(*permissions)


def remove_from_reset_group(apps, schema_editor):
    alias = schema_editor.connection.alias
    Permission = apps.get_model("auth", "Permission")
    group = apps.get_model("auth", "Group").objects.using(alias).filter(name=RESET_GROUP).first()
    if group is not None:
        group.permissions.remove(
            *Permission.objects.using(alias).filter(
                content_type__app_label="accounts", codename__in=CODENAMES
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0096_portal_password_resets_group"),
        ("accounts", "0013_sign_in_help"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(grant_to_reset_group, remove_from_reset_group)]
