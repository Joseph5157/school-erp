"""Report card PDF from the immutable publication snapshot (spec decision 5)."""

from django.db import IntegrityError, transaction

from core import models as core_models
from core import publication as publication_rules
from core.documents import service
from core.models import IssuedDocument, TermPublication


def _text(value):
    return "" if value is None else str(value)


def _payload(pub):
    return {
        "student_name": pub.student.full_name,
        "admission_number": pub.student.admission_number or "",
        "term_label": pub.term_label,
        "academic_year_label": pub.academic_year_label,
        "class_label": pub.class_grade_label,
        "section_label": pub.section_label,
        "is_partial": pub.is_partial,
        "remark_text": pub.remark_text or "",
        "entries": [
            {
                "subject": e.subject_label,
                "assessment": e.assessment_label,
                "date": e.assessment_date.isoformat(),
                "status": e.status,
                "score": _text(e.score),
                "maximum_marks": _text(e.maximum_marks),
                "percentage": _text(e.percentage),
                "grade": _text(e.grade_label),
                "pass_fail": _text(e.pass_fail_label),
            }
            for e in pub.entries.all()
        ],
        "issued_on": core_models.business_today().isoformat(),
    }


def document_for(pub, *, actor):
    """The issued document for a publication, issuing it on first use.

    Returns None unless the publication is PUBLISHED and unchanged since release.
    """
    if pub.status != TermPublication.Status.PUBLISHED:
        return None
    if not publication_rules.guardian_visible(pub):
        return None
    existing = IssuedDocument.objects.filter(publication=pub).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return service.issue(
                document_type=IssuedDocument.DocumentType.REPORT_CARD,
                academic_year=pub.term.academic_year, payload=_payload(pub),
                actor=actor, student=pub.student, publication=pub,
            )
    except IntegrityError:
        # two first downloads at once: the other request issued it
        return IssuedDocument.objects.filter(publication=pub).first()
