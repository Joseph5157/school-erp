# Phase 6 Gate 1 (ADR 0013): administrators manage guardian accounts, access
# grants and password resets, and may view security events.

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
PERMISSIONS = {
    "core": [
        "add_guardianaccount",
        "change_guardianaccount",
        "view_guardianaccount",
        "reset_guardian_password",
        "change_guardian_username",
        "add_guardianstudentaccess",
        "change_guardianstudentaccess",
        "view_guardianstudentaccess",
    ],
    "accounts": ["view_securityevent"],
}


def _permissions(apps, alias):
    Permission = apps.get_model("auth", "Permission")
    found = []
    for app_label, codenames in PERMISSIONS.items():
        found += list(
            Permission.objects.using(alias).filter(
                content_type__app_label=app_label, codename__in=codenames
            )
        )
    return found


def add_permissions_to_group(apps, schema_editor):
    alias = schema_editor.connection.alias
    for app_label in PERMISSIONS:
        config = apps.get_app_config(app_label)
        config.models_module = True
        create_permissions(config, verbosity=0, using=alias, apps=apps)
        config.models_module = None
    Group = apps.get_model("auth", "Group")
    group, _ = Group.objects.using(alias).get_or_create(name=GROUP_NAME)
    group.permissions.add(*_permissions(apps, alias))


def remove_permissions_from_group(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    group = Group.objects.using(alias).filter(name=GROUP_NAME).first()
    if group is not None:
        group.permissions.remove(*_permissions(apps, alias))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_phase6_guardian_accounts"),
        ("accounts", "0002_phase6_user_security"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_permissions_to_group, remove_permissions_from_group),
    ]
