from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the column first (ADR 0019 D2).

    Additive and safe to deploy before the code that reads it: until the
    backfill and constraint land, readers fall back to the live Subject name.
    """

    dependencies = [
        ("core", "0073_assessmentteacherassignment_change_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="subject_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Subject name captured at finalization (ADR 0019); empty while a draft.",
                max_length=100,
            ),
        ),
    ]
