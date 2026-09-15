from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
PERMISSION_CODENAMES = [
    "add_school",
    "change_school",
    "view_school",
    "add_academicyear",
    "view_academicyear",
]


def create_school_administrators_group(apps, schema_editor):
    # Permission rows are normally created by a post_migrate signal that
    # fires only after the whole `migrate` run finishes, so they do not
    # exist yet inside this migration. Create them explicitly first --
    # create_permissions() is itself idempotent.
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
    group.permissions.set(permissions)


def remove_school_administrators_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            create_school_administrators_group, remove_school_administrators_group
        ),
    ]
