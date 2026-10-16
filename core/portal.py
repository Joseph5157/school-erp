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


def visible_publications(student):
    """Current PUBLISHED versions whose released values are unchanged (ADR 0014)."""
    from core import publication
    from core.models import TermPublication

    publications = list(
        TermPublication.objects.filter(
            student=student, status=TermPublication.Status.PUBLISHED
        )
        .select_related("term")
        .order_by("-term__start_date")
    )
    visible = publication.guardian_visible_many(publications)
    return [pub for pub in publications if visible[pub.pk]]


def child_summaries(children):
    """One batched, read-only dashboard summary per visible child (G-07).

    A constant number of queries regardless of how many children the guardian
    has: placements and attendance counts are fetched in bulk, never per child.
    Report cards come from the existing published snapshot
    (visible_publications semantics), never recomputed.
    """
    from django.db.models import Count

    from core import guardian_access, publication, reports
    from core.models import (
        AcademicEnrollment,
        AttendanceEntry,
        AttendanceStatus,
        TermPublication,
        business_today,
    )

    visible = [item for item in children if item["visible"]]
    students = [item["student"] for item in visible]
    if not students:
        return []

    today = business_today()
    by_student = {}
    newest_year = {}
    for enrollment in (
        AcademicEnrollment.objects.filter(student__in=students)
        .select_related("academic_year", "class_grade", "section")
        .order_by("student_id", "-start_date")
    ):
        by_student.setdefault(enrollment.student_id, []).append(enrollment)
        newest_year.setdefault(enrollment.student_id, enrollment.academic_year_id)

    placements = {}
    for student_id, rows in by_student.items():
        for enrollment in rows:
            if guardian_access._effective_within_year(enrollment, today):
                placements[student_id] = {
                    "academic_year": enrollment.academic_year.name,
                    "class_grade": enrollment.class_grade.name,
                    "section": enrollment.section.name,
                    "roll_number": enrollment.roll_number,
                }
                break

    present = {}
    absent = {}
    for row in (
        reports.reportable_entries(
            AttendanceEntry.objects.filter(
                academic_enrollment__student__in=students,
                register__academic_year_id__in=set(newest_year.values()),
            )
        )
        .values(
            "academic_enrollment__student_id",
            "register__academic_year_id",
            "status",
        )
        .annotate(n=Count("id"))
    ):
        student_id = row["academic_enrollment__student_id"]
        if row["register__academic_year_id"] != newest_year.get(student_id):
            continue
        if row["status"] == AttendanceStatus.PRESENT:
            present[student_id] = present.get(student_id, 0) + row["n"]
        else:
            absent[student_id] = absent.get(student_id, 0) + row["n"]

    latest = {}
    cards = list(
        TermPublication.objects.filter(
            student__in=students, status=TermPublication.Status.PUBLISHED
        )
        .select_related("term")
        .order_by("student_id", "-term__start_date", "-pk")
    )
    visible_cards = publication.guardian_visible_many(cards)
    for card in cards:
        if card.student_id not in latest and visible_cards[card.pk]:
            latest[card.student_id] = card

    summaries = []
    for item in visible:
        student = item["student"]
        student_id = student.pk
        present_n = present.get(student_id, 0)
        absent_n = absent.get(student_id, 0)
        total = present_n + absent_n
        summaries.append(
            {
                "name": student.full_name,
                "placement": placements.get(student_id),
                "status": student.get_status_display(),
                "attendance": {
                    "present": present_n,
                    "absent": absent_n,
                    "total": total,
                    "percentage": reports.percentage(present_n, absent_n),
                }
                if total
                else None,
                "latest_report_card": latest.get(student_id),
                "grant": item["grant"],
            }
        )
    return summaries
