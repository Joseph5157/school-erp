# Stage 1 of 2 for docs/adr/0006-academic-enrollment-effective-dating.md.
#
# Adds the business-effective date fields as nullable so existing rows are
# never given guessed dates. Stage 2 (0018) makes `start_date` required and adds
# the database constraints, and refuses to run while any existing row still
# lacks the dates it needs.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_attendanceregister_unique_section_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="academicenrollment",
            name="start_date",
            field=models.DateField(
                null=True,
                help_text="First date this placement is effective (inclusive).",
            ),
        ),
        migrations.AddField(
            model_name="academicenrollment",
            name="end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Last date this placement is effective (inclusive). Empty while ACTIVE.",
            ),
        ),
    ]
