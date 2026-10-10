# Stage 2 of 2 for docs/adr/0006-academic-enrollment-effective-dating.md.
#
# Business-effective dates must not be guessed from created_at/updated_at or
# invented. If a database already holds AcademicEnrollment rows from before
# 0017, this migration stops with instructions instead of backfilling:
#
#   1. python manage.py migrate core 0017
#   2. Enter the real dates for each listed enrollment, e.g. in
#      `python manage.py shell`:
#        from core.models import AcademicEnrollment
#        AcademicEnrollment.objects.filter(pk=<id>).update(
#            start_date="YYYY-MM-DD",   # every enrollment
#            end_date="YYYY-MM-DD",     # COMPLETED enrollments only
#        )
#      Periods for one Student must not overlap, and end_date >= start_date.
#   3. python manage.py migrate
#
# Disposable development data may instead be discarded (recreate the database).

from django.db import migrations, models


def require_effective_dates(apps, schema_editor):
    AcademicEnrollment = apps.get_model("core", "AcademicEnrollment")
    missing_start = AcademicEnrollment.objects.filter(start_date__isnull=True)
    completed_missing_end = AcademicEnrollment.objects.filter(
        status="COMPLETED", end_date__isnull=True
    )
    problem_ids = sorted(
        set(missing_start.values_list("pk", flat=True))
        | set(completed_missing_end.values_list("pk", flat=True))
    )
    if problem_ids:
        raise RuntimeError(
            "AcademicEnrollment rows are missing business-effective dates and will not be "
            "guessed (ADR 0006). Enter the real start_date (and end_date for COMPLETED rows) "
            f"for enrollment ids {problem_ids}, then re-run migrate. See the header of "
            "core/migrations/0018_academicenrollment_effective_dates_required.py."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_academicenrollment_effective_dates"),
    ]

    operations = [
        migrations.RunPython(require_effective_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="academicenrollment",
            name="start_date",
            field=models.DateField(
                help_text="First date this placement is effective (inclusive).",
            ),
        ),
        migrations.AddConstraint(
            model_name="academicenrollment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("end_date__isnull", True), ("status", "ACTIVE")),
                    models.Q(("end_date__isnull", False), ("status", "COMPLETED")),
                    _connector="OR",
                ),
                name="academicenrollment_end_date_matches_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="academicenrollment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("end_date__isnull", True),
                    ("end_date__gte", models.F("start_date")),
                    _connector="OR",
                ),
                name="academicenrollment_end_date_not_before_start_date",
            ),
        ),
    ]
