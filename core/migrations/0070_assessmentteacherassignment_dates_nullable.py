# ADR 0018: subject teacher assignments become effective-dated. Step 1 of 3:
# add the date columns as nullable. Backfill and constraints follow in 0071
# and 0072, kept as separate migrations so PostgreSQL does not meet "pending
# trigger events" when a data update and a table alteration share one
# transaction.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0069_studentguardian_permissions_to_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessmentteacherassignment",
            name="start_date",
            field=models.DateField(
                null=True, help_text="First date this assignment is effective."
            ),
        ),
        migrations.AddField(
            model_name="assessmentteacherassignment",
            name="end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Last date this assignment is effective (inclusive).",
            ),
        ),
    ]
