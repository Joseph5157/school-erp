"""Step 2 of 3: number existing Classes/Grades in academic order.

Pre-primary names come first, then everything else with numbers compared as numbers, so
Grade 2 precedes Grade 10. The rule is a starting point: schools can change the order on the
Classes/Grades page. It is copied here, not imported, so this migration never changes.
"""

import re

from django.db import migrations

PRE_PRIMARY = ("playgroup", "play group", "pre-nursery", "pre nursery", "nursery", "lkg", "ukg")


def backfill_key(name):
    cleaned = name.strip().lower()
    rank = PRE_PRIMARY.index(cleaned) if cleaned in PRE_PRIMARY else len(PRE_PRIMARY)
    parts = [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", cleaned)]
    return rank, parts


def assign_order(apps, schema_editor):
    ClassGrade = apps.get_model("core", "ClassGrade")
    grades = sorted(ClassGrade.objects.all(), key=lambda grade: (backfill_key(grade.name), grade.pk))
    for position, grade in enumerate(grades, start=1):
        # update(), so updated_at does not claim the school edited this Class/Grade.
        ClassGrade.objects.filter(pk=grade.pk).update(display_order=position)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0085_classgrade_display_order"),
    ]

    operations = [
        migrations.RunPython(assign_order, migrations.RunPython.noop),
    ]
