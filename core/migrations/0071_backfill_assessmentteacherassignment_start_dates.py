# ADR 0018 migration baseline. Step 2 of 3: every surviving assignment starts
# on the first day of its offering's Academic Year, which keeps today's access
# exactly as it is. This is a legacy assumption, not a claim that the teacher
# taught the Subject for the whole past year; history deleted before this
# migration cannot be reconstructed.

from django.db import migrations


def backfill(apps, schema_editor):
    Assignment = apps.get_model("core", "AssessmentTeacherAssignment")
    for row in Assignment.objects.filter(start_date__isnull=True).select_related(
        "offering__academic_year"
    ):
        row.start_date = row.offering.academic_year.start_date
        row.save(update_fields=["start_date"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0070_assessmentteacherassignment_dates_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
