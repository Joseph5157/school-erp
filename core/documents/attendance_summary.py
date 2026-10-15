"""Attendance summary for one section and date range (spec decision 8)."""

from django.core.exceptions import ValidationError

from core import models as core_models
from core import reports
from core.documents import service
from core.models import AcademicYear, AttendanceEntry, IssuedDocument


def _plain(counts):
    return {
        "present": counts["present"],
        "absent": counts["absent"],
        "total": counts["total"],
        "percentage": "" if counts["percentage"] is None else str(counts["percentage"]),
    }


def build(section, start, end):
    """Counts for a section over a range; only submitted, eligible entries count."""
    if end < start:
        raise ValidationError("The end date is before the start date.")
    year = AcademicYear.objects.filter(start_date__lte=start, end_date__gte=start).first()
    if year is None:
        raise ValidationError("No academic year contains the start date.")
    if end > year.end_date:
        raise ValidationError("The range must stay inside one academic year.")
    entries = reports.reportable_entries(AttendanceEntry.objects.filter(
        academic_enrollment__section=section,
        register__date__gte=start, register__date__lte=end))
    students = entries.order_by().values_list(
        "academic_enrollment__student_id", "academic_enrollment__student__full_name"
    ).distinct()
    rows = []
    for student_id, name in sorted(students, key=lambda item: item[1]):
        counts = reports.counts(entries.filter(academic_enrollment__student_id=student_id))
        rows.append({"student_name": name, **_plain(counts)})
    return {
        "academic_year": year,
        "section_label": section.name,
        "class_label": section.class_grade.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rows": rows,
        "totals": _plain(reports.counts(entries)),
    }


def issue_summary(section, start, end, *, actor):
    data = build(section, start, end)
    year = data.pop("academic_year")
    data["issued_on"] = core_models.business_today().isoformat()
    return service.issue(
        document_type=IssuedDocument.DocumentType.ATTENDANCE_SUMMARY,
        academic_year=year, payload=data, actor=actor,
    )
