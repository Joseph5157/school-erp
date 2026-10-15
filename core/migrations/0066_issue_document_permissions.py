# Phase 7 piece C: School Administrators may issue documents and see the register
# of issued documents.

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
CODENAMES = ["issue_document", "view_issueddocument"]


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


def backwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    group = Group.objects.using(alias).filter(name=GROUP_NAME).first()
    if group is not None:
        group.permissions.remove(*_permissions(apps, alias))


class Migration(migrations.Migration):
    dependencies = [("core", "0065_issued_document_history_guards")]

    operations = [migrations.RunPython(forwards, backwards)]
