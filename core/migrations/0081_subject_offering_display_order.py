import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """U4-3A step 1 of 3: add the configured report-card order (nullable until backfilled)."""

    dependencies = [
        ("core", "0080_timetable_permissions_to_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="academicsubjectoffering",
            name="display_order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                help_text=(
                    "Position of this Subject on report cards for the Class/Grade this year; "
                    "1 is shown first. Each Subject in a Class/Grade needs a different number. "
                    "Leave blank to place a new Subject last."
                ),
            ),
        ),
    ]
