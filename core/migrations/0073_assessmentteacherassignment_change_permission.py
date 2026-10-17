from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
# ADR 0018: ending an assignment is a "change"; reassigning used to be remove +
# add and needed none. add/view/delete were granted in 0026; re-adding is harmless.
PERMISSION_CODENAMES = [
    "add_assessmentteacherassignment",
    "change_assessmentteacherassignment",
    "delete_assessmentteacherassignment",
    "view_assessmentteacherassignment",
]
# Reversing removes only what this migration introduced.
ADDED_CODENAMES = ["change_assessmentteacherassignment"]


def add_permissions_to_group(apps, schema_editor):
    config = apps.get_app_config("core")
    config.models_module = True
    create_permissions(config, verbosity=0, using=schema_editor.connection.alias, apps=apps)
    config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.using(schema_editor.connection.alias).get_or_create(name=GROUP_NAME)
    permissions = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="core", codename__in=PERMISSION_CODENAMES
    )
    group.permissions.add(*permissions)


def remove_permissions_from_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.using(schema_editor.connection.alias).filter(name=GROUP_NAME).first()
    if group is None:
        return
    permissions = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="core", codename__in=ADDED_CODENAMES
    )
    group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0072_assessmentteacherassignment_effective_dating"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_permissions_to_group, remove_permissions_from_group),
    ]
