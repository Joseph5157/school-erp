import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """U4-3A step 3 of 3: require the order and make it positive and unique per Grade/year."""

    dependencies = [
        ("core", "0082_backfill_subject_offering_display_order"),
    ]

    operations = [
        migrations.AlterField(
            model_name="academicsubjectoffering",
            name="display_order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                validators=[django.core.validators.MinValueValidator(1)],
                help_text=(
                    "Position of this Subject on report cards for the Class/Grade this year; "
                    "1 is shown first. Each Subject in a Class/Grade needs a different number. "
                    "Leave blank to place a new Subject last."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="academicsubjectoffering",
            constraint=models.UniqueConstraint(
                fields=("academic_year", "class_grade", "display_order"),
                name="subjectoffering_unique_year_grade_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="academicsubjectoffering",
            constraint=models.CheckConstraint(
                condition=models.Q(("display_order__gte", 1)),
                name="subjectoffering_display_order_positive",
            ),
        ),
    ]
