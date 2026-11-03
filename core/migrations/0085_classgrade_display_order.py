from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 1 of 3: add the position, empty until the backfill fills it."""

    dependencies = [
        ("core", "0084_english_student_names"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="classgrade",
            options={"verbose_name": "Class/Grade", "verbose_name_plural": "Classes/Grades"},
        ),
        migrations.AddField(
            model_name="classgrade",
            name="display_order",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
