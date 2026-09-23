from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_add_attendance_permissions_to_group"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="attendanceregister",
            name="attendanceregister_unique_section_date",
        ),
        migrations.AddConstraint(
            model_name="attendanceregister",
            constraint=models.UniqueConstraint(
                fields=("section", "date"),
                name="attendanceregister_unique_section_date",
            ),
        ),
    ]
