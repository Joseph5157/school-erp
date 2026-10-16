from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
CODENAME = "manage_teacher_accounts"


def add_permission_to_group(apps, schema_editor):
    config = apps.get_app_config("accounts")
    config.models_module = True
    create_permissions(config, verbosity=0, using=schema_editor.connection.alias, apps=apps)
    config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.using(schema_editor.connection.alias).get_or_create(name=GROUP_NAME)
    permission = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="accounts", codename=CODENAME
    )
    group.permissions.add(*permission)


def remove_permission_from_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.using(schema_editor.connection.alias).filter(name=GROUP_NAME).first()
    if group is None:
        return
    permission = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="accounts", codename=CODENAME
    )
    group.permissions.remove(*permission)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0067_phase0_decision_reasons"),
        ("accounts", "0007_teacher_accounts_permission_events"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_permission_to_group, remove_permission_from_group),
    ]
