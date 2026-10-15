"""Issue and reprint serial-numbered documents (spec 2026-10-15)."""

from django.db import transaction
from django.http import HttpResponse

from accounts.models import SecurityEvent
from core.documents import serials
from core.documents.engine import render_pdf
from core.models import IssuedDocument, School

Event = SecurityEvent.EventType

TEMPLATES = {
    "BONAFIDE": "documents/bonafide.html",
    "REPORT_CARD": "documents/report_card.html",
    "ATTENDANCE_SUMMARY": "documents/attendance_summary.html",
}


def letterhead(school=None):
    school = school or School.objects.first()
    if school is None:
        return {"school_name": "", "address": "", "affiliation_number": "",
                "principal_name": ""}
    return {
        "school_name": school.name,
        "address": school.address,
        "affiliation_number": school.affiliation_number,
        "principal_name": school.principal_name,
    }


def issue(*, document_type, academic_year, payload, actor, student=None, publication=None):
    with transaction.atomic():
        document = IssuedDocument.objects.create(
            document_type=document_type,
            serial=serials.next_serial(document_type, academic_year),
            academic_year=academic_year,
            student=student,
            publication=publication,
            payload={**payload, "letterhead": letterhead()},
            issued_by=actor if getattr(actor, "pk", None) else None,
        )
        SecurityEvent.record(
            Event.DOCUMENT_ISSUED, actor=actor, student=student,
            detail={"serial": document.serial, "document_type": document_type},
        )
    return document


def pdf_for(document, *, actor):
    """Render from the stored snapshot; every call is audited."""
    pdf = render_pdf(TEMPLATES[document.document_type], {
        "doc": document, "payload": document.payload, "serial": document.serial,
    })
    SecurityEvent.record(
        Event.DOCUMENT_DOWNLOADED, actor=actor, student=document.student,
        detail={"serial": document.serial, "document_type": document.document_type},
    )
    return pdf


def pdf_response(document, *, actor):
    response = HttpResponse(pdf_for(document, actor=actor), content_type="application/pdf")
    name = document.serial.replace("/", "-")
    response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response
