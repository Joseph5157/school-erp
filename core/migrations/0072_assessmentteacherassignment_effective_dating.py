# ADR 0018. Step 3 of 3: start_date becomes required and the one-row-per-slot
# constraint gives way to dated history (unique per start date, end not
# before start). Overlap is enforced by the model under a lock; there is no
# database range-exclusion constraint, by decision.

from django.db import migrations, models


def refuse_if_history(apps, schema_editor):
    """Reverse guard: never collapse real hand-over history (ADR 0018)."""
    Assignment = apps.get_model("core", "AssessmentTeacherAssignment")
    crowded = (
        Assignment.objects.values("offering_id", "section_id")
        .annotate(rows=models.Count("pk"))
        .filter(rows__gt=1)
    )
    if crowded.exists():
        raise RuntimeError(
            "Cannot reverse: some Subject offerings + Sections have more than one "
            "teacher assignment (hand-over history). Restore from a backup instead "
            "of collapsing history."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0071_backfill_assessmentteacherassignment_start_dates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assessmentteacherassignment",
            name="start_date",
            field=models.DateField(help_text="First date this assignment is effective."),
        ),
        migrations.RemoveConstraint(
            model_name="assessmentteacherassignment",
            name="assessmentteacherassignment_one_teacher_per_offering_section",
        ),
        # On reverse this runs before the old constraint is restored.
        migrations.RunPython(migrations.RunPython.noop, refuse_if_history),
        migrations.AlterModelOptions(
            name="assessmentteacherassignment",
            options={"ordering": ["offering", "section", "start_date"]},
        ),
        migrations.AddConstraint(
            model_name="assessmentteacherassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(("end_date__isnull", True), ("end_date__gte", models.F("start_date")), _connector="OR"),
                name="assessmentteacherassignment_end_not_before_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="assessmentteacherassignment",
            constraint=models.UniqueConstraint(
                fields=("offering", "section", "start_date"),
                name="assessmentteacherassignment_unique_offering_section_start",
            ),
        ),
    ]
