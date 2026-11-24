# G-06 reset spec §6 (ADR 0029 OD-G7): only named staff reset guardian passwords. The permission
# moves from School Administrators to its own group, chosen later on the "Password reset staff"
# page (spec §6a). Until someone is added, only superusers can reset.

from django.contrib.auth.management import create_permissions
from django.db import migrations

RESET_GROUP = "Portal password resets"
ADMIN_GROUP = "School Administrators"
CODENAME = "reset_guardian_password"


def _permission(apps, alias):
    config = apps.get_app_config("core")
    config.models_module = True
    create_permissions(config, verbosity=0, using=alias, apps=apps)
    config.models_module = None
    Permission = apps.get_model("auth", "Permission")
    return Permission.objects.using(alias).get(content_type__app_label="core", codename=CODENAME)


def move_to_reset_group(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    permission = _permission(apps, alias)
    group = Group.objects.using(alias).filter(name=RESET_GROUP).first()
    if group is None:
        group = Group.objects.using(alias).create(name=RESET_GROUP)
    elif set(group.permissions.values_list("pk", flat=True)) - {permission.pk}:
        raise RuntimeError(
            f'A group named "{RESET_GROUP}" already exists with other permissions. Rename it, '
            "then run the migration again."
        )
    group.permissions.add(permission)
    admins = Group.objects.using(alias).filter(name=ADMIN_GROUP).first()
    if admins is not None:
        admins.permissions.remove(permission)


def back_to_administrators(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    permission = _permission(apps, alias)
    admins, _ = Group.objects.using(alias).get_or_create(name=ADMIN_GROUP)
    admins.permissions.add(permission)
    group = Group.objects.using(alias).filter(name=RESET_GROUP).first()
    # Delete the group only when it is still exactly what this migration made and nobody is in it.
    if (
        group is not None
        and not group.user_set.exists()
        and set(group.permissions.values_list("pk", flat=True)) == {permission.pk}
    ):
        group.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0095_usagecounter"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(move_to_reset_group, back_to_administrators)]
