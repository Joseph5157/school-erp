"""Backfill `Assessment.subject_label` for already finalized assessments (ADR 0019 D6).

Legacy recovery assumption (not a correction of history): the name a finalized
assessment showed is taken from the EARLIEST published entry of any of its
results, ordered by publication `published_at`, then publication id, then
entry id, so the choice is deterministic. If an assessment was published under
several different labels, the earliest one wins; later labels are not
inferred, merged or "fixed". An assessment that was never published gets the
Subject's current name. Drafts are left empty.
"""

import sys

from django.db import migrations


def backfill(apps, schema_editor):
    Assessment = apps.get_model("core", "Assessment")
    Entry = apps.get_model("core", "TermPublicationEntry")
    from_publication = from_live_name = conflicting = 0
    for assessment in Assessment.objects.filter(status="FINALIZED", subject_label="").select_related(
        "offering__subject"
    ):
        labels = list(
            Entry.objects.filter(result__assessment=assessment)
            .exclude(subject_label="")
            .order_by("publication__published_at", "publication_id", "pk")
            .values_list("subject_label", flat=True)
        )
        if labels:
            label = labels[0]
            from_publication += 1
            conflicting += len(set(labels)) > 1
        else:
            label = assessment.offering.subject.name
            from_live_name += 1
        Assessment.objects.filter(pk=assessment.pk).update(subject_label=label)
    if from_publication or from_live_name:
        sys.stdout.write(
            f"\n  subject_label backfill: {from_publication} from the earliest published "
            f"entry ({conflicting} with conflicting published labels), "
            f"{from_live_name} from the current Subject name.\n"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0074_assessment_subject_label"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
