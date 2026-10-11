"""Phase 6 Guardian Portal read models (ADR 0014).

Portal views never reuse administrative or teacher pages. They build their
own, minimal context from the guardian's active grants.
"""

from core import guardian_access
from core.authorization import guardian_grants


def portal_children(user):
    """[{grant, student, visible}] for the user's active grants, in two queries.

    `visible` is False while a date-based access review is pending (OD-8,
    fail closed): the Student is listed only as under review, with no data.
    """
    grants = list(guardian_grants(user).order_by("student_guardian__student__full_name", "pk"))
    states = guardian_access.pending_map(grants)
    return [
        {
            "grant": grant,
            "student": grant.student_guardian.student,
            "visible": not states[grant.pk][0],
        }
        for grant in grants
    ]


def student_profile(student, on_date=None):
    """Exactly the P7 fields, nothing else (ADR 0014).

    Name, admission number, current placement (Academic Year, Class/Grade,
    Section, roll number) and enrolment status. Never date of birth, Student
    contact details, internal ids, other guardians or staff-only data.
    """
    from core import models as core_models

    on_date = on_date or core_models.business_today()
    placement = None
    for enrollment in core_models.AcademicEnrollment.objects.filter(
        student=student
    ).select_related("academic_year", "class_grade", "section").order_by("-start_date"):
        if guardian_access._effective_within_year(enrollment, on_date):
            placement = {
                "academic_year": enrollment.academic_year.name,
                "class_grade": enrollment.class_grade.name,
                "section": enrollment.section.name,
                "roll_number": enrollment.roll_number,
            }
            break
    return {
        "name": student.full_name,
        "admission_number": student.admission_number,
        "placement": placement,
        "status": student.get_status_display(),
    }


def attendance_years(student):
    """Academic Years in which the Student had a placement, newest first."""
    from core.models import AcademicYear

    return list(
        AcademicYear.objects.filter(enrollments__student=student)
        .distinct()
        .order_by("-start_date")
    )


def submitted_attendance(student, academic_year):
    """Reportable (SUBMITTED, instructional, in-placement) entries and summary.

    Only the date and the current accepted status are exposed: never absence
    notes, correction history, correctors or DRAFT registers (ADR 0014, P8).
    Missing attendance is simply absent from the list, never shown as absent.
    """
    from core import reports
    from core.models import AttendanceEntry

    entries = reports.reportable_entries(
        AttendanceEntry.objects.filter(
            academic_enrollment__student=student, register__academic_year=academic_year
        )
    )
    days = [
        {"date": on_date, "status": status}
        for on_date, status in entries.order_by("-register__date").values_list(
            "register__date", "status"
        )
    ]
    return {"days": days, "summary": reports.counts(entries)}
