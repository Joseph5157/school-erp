from django.db import migrations, models


class Migration(migrations.Migration):
    """Tie the captured name to the status, after the backfill (ADR 0019 D2)."""

    dependencies = [
        ("core", "0075_backfill_assessment_subject_label"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="assessment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "DRAFT"), ("subject_label", "")),
                    models.Q(
                        ("status", "FINALIZED"),
                        models.Q(("subject_label", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="assessment_subject_label_matches_status",
            ),
        ),
    ]
