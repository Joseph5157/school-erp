"""Bonafide certificate: confirms current enrolment (spec decision 7)."""

from django.core.exceptions import ValidationError

from core import models as core_models
from core.documents import service
from core.models import AcademicEnrollment, IssuedDocument

PURPOSES = [
    ("BANK", "Opening a bank account"),
    ("PASSPORT", "Passport application"),
    ("SCHOLARSHIP", "Scholarship application"),
    ("OTHER", "Other"),
]


def current_enrollment(student):
    """Enrollment effective today and inside its academic year (the Gate 3 rule)."""
    today = core_models.business_today()
    return (
        AcademicEnrollment.objects.effective_on(today)
        .filter(student=student, academic_year__end_date__gte=today)
        .select_related("academic_year", "class_grade", "section")
        .first()
    )


def issue_bonafide(*, student, purpose_key, purpose_text, actor):
    enrollment = current_enrollment(student)
    if enrollment is None:
        raise ValidationError("This student has no current enrolment.")
    labels = dict(PURPOSES)
    if purpose_key == "OTHER":
        purpose = (purpose_text or "").strip()[:120]
        if not purpose:
            raise ValidationError("Say what the certificate is for.")
    elif purpose_key in labels:
        purpose = labels[purpose_key]
    else:
        raise ValidationError("Choose a purpose.")
    payload = {
        "student_name": student.full_name,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else "",
        "admission_number": student.admission_number or "",
        "class_label": enrollment.class_grade.name,
        "section_label": enrollment.section.name,
        "academic_year_label": enrollment.academic_year.name,
        "purpose": purpose,
        "issued_on": core_models.business_today().isoformat(),
    }
    return service.issue(
        document_type=IssuedDocument.DocumentType.BONAFIDE,
        academic_year=enrollment.academic_year, payload=payload, actor=actor, student=student,
    )
