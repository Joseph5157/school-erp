# Phase 7 Gates 2 and 4 (ADR 0015): the first approved message texts.
# Template rows cannot be deleted (history guards), so reversing is a no-op.

from django.db import migrations

TEXTS = {
    "absence-alert": (
        "Dear parent, {first_name} was marked absent at school on {date}. "
        "Attendance details: {portal_url}"
    ),
    "report-card-published": (
        "Dear parent, {first_name}'s report card is now available on the school portal: "
        "{portal_url}"
    ),
}


def seed(apps, schema_editor):
    NotificationTemplate = apps.get_model("core", "NotificationTemplate")
    alias = schema_editor.connection.alias
    for key, body in TEXTS.items():
        NotificationTemplate.objects.using(alias).get_or_create(
            key=key, channel="WHATSAPP", language="en", version=1,
            defaults={"body": body, "approved": True},
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0058_add_notification_permissions_to_group")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
