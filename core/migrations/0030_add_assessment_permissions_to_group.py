# Phase 4 Gate 4: School Administrators plan assessments (ADR 0009).

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
PERMISSION_CODENAMES = [
    "add_assessment",
    "change_assessment",
    "delete_assessment",
    "view_assessment",
]


def add_permissions_to_group(apps, schema_editor):
    # Permission rows are normally created by a post_migrate signal that
    # fires only after the whole `migrate` run finishes, so the permissions
    # for the newly added models do not exist yet inside this migration.
    # Create them explicitly first -- create_permissions() is idempotent.
    core_app_config = apps.get_app_config("core")
    core_app_config.models_module = True
    create_permissions(
        core_app_config, verbosity=0, using=schema_editor.connection.alias, apps=apps
    )
    core_app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.using(schema_editor.connection.alias).get_or_create(name=GROUP_NAME)
    permissions = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="core",
        codename__in=PERMISSION_CODENAMES,
    )
    group.permissions.add(*permissions)


def remove_permissions_from_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.using(schema_editor.connection.alias).filter(name=GROUP_NAME).first()
    if group is None:
        return
    permissions = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="core",
        codename__in=PERMISSION_CODENAMES,
    )
    group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0029_assessments"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_permissions_to_group, remove_permissions_from_group),
    ]
