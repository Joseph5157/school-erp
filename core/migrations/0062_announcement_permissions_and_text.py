# Phase 7 Gate 3 (ADR 0015): administrators publish and withdraw announcements;
# the link-only WhatsApp text. Template rows cannot be deleted, so the text is
# left in place on reverse.

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
CODENAMES = ["add_announcement", "view_announcement", "withdraw_announcement"]
TEXT = "Dear parent, there is a new notice from the school. Read it here: {portal_url}"


def _permissions(apps, alias):
    Permission = apps.get_model("auth", "Permission")
    return list(Permission.objects.using(alias).filter(
        content_type__app_label="core", codename__in=CODENAMES))


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    config = apps.get_app_config("core")
    config.models_module = True
    create_permissions(config, verbosity=0, using=alias, apps=apps)
    config.models_module = None
    Group = apps.get_model("auth", "Group")
    group, _ = Group.objects.using(alias).get_or_create(name=GROUP_NAME)
    group.permissions.add(*_permissions(apps, alias))
    NotificationTemplate = apps.get_model("core", "NotificationTemplate")
    NotificationTemplate.objects.using(alias).get_or_create(
        key="announcement", channel="WHATSAPP", language="en", version=1,
        defaults={"body": TEXT, "approved": True},
    )


def backwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    group = Group.objects.using(alias).filter(name=GROUP_NAME).first()
    if group is not None:
        group.permissions.remove(*_permissions(apps, alias))


class Migration(migrations.Migration):
    dependencies = [("core", "0061_announcement_history_guards")]

    operations = [migrations.RunPython(forwards, backwards)]
