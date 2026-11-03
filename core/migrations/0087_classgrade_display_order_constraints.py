import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """Step 3 of 3: require the position, make it positive and unique, and sort by it."""

    dependencies = [
        ("core", "0086_backfill_classgrade_display_order"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="classgrade",
            options={
                "ordering": ["display_order"],
                "verbose_name": "Class/Grade",
                "verbose_name_plural": "Classes/Grades",
            },
        ),
        migrations.AlterField(
            model_name="classgrade",
            name="display_order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                validators=[django.core.validators.MinValueValidator(1)],
                help_text=(
                    "Position of this Class/Grade in lists; 1 is shown first. Leave blank to place it last."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="classgrade",
            constraint=models.UniqueConstraint(fields=("display_order",), name="classgrade_unique_display_order"),
        ),
        migrations.AddConstraint(
            model_name="classgrade",
            constraint=models.CheckConstraint(
                condition=models.Q(("display_order__gte", 1)),
                name="classgrade_display_order_positive",
            ),
        ),
    ]
