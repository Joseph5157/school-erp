"""U4-3A step 2 of 3: give every existing offering a deterministic `display_order`.

Rule: within each (academic_year, class_grade), offerings are numbered 1..n in
Subject name order (the order the system effectively used until now, because
report-card entries were released alphabetically by Subject), with the offering
id as the tie-break. This only assigns the new configuration; it never touches
TermPublicationEntry, so already released report cards are not reordered. The
school can edit the numbers afterwards.
"""

from django.db import migrations


def assign_order(apps, schema_editor):
    Offering = apps.get_model("core", "AcademicSubjectOffering")
    groups = {}
    for offering_id, year_id, grade_id in Offering.objects.order_by(
        "academic_year_id", "class_grade_id", "subject__name", "pk"
    ).values_list("pk", "academic_year_id", "class_grade_id"):
        groups.setdefault((year_id, grade_id), []).append(offering_id)
    for offering_ids in groups.values():
        for position, offering_id in enumerate(offering_ids, start=1):
            Offering.objects.filter(pk=offering_id).update(display_order=position)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0081_subject_offering_display_order"),
    ]

    operations = [
        migrations.RunPython(assign_order, migrations.RunPython.noop),
    ]
