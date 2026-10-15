"""Serial numbers for issued documents. Call inside transaction.atomic()."""

from django.db import IntegrityError, transaction

from core.models import DocumentSerialCounter

PREFIXES = {"BONAFIDE": "BON", "REPORT_CARD": "RC", "ATTENDANCE_SUMMARY": "ATT"}


def next_serial(document_type, academic_year):
    if document_type not in PREFIXES:
        raise ValueError(f"Unknown document type: {document_type}")
    try:
        with transaction.atomic():
            DocumentSerialCounter.objects.get_or_create(
                document_type=document_type, academic_year=academic_year)
    except IntegrityError:
        pass  # a concurrent request created it first
    counter = DocumentSerialCounter.objects.select_for_update().get(
        document_type=document_type, academic_year=academic_year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{PREFIXES[document_type]}/{academic_year.name}/{counter.last_number:04d}"
