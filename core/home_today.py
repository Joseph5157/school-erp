"""Admin home Today tab data. Read-only; no HTTP here."""
import datetime
from collections import defaultdict

from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.utils import timezone

from core import analytics, charts, reports
from core.charts import natural_key
from core.models import (
    AcademicEnrollment,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    School,
    SectionClassTeacher,
    Student,
)

DEFAULT_REGISTER_CUTOFF = datetime.time(10, 0)


def register_cutoff():
    """The school's register cut-off time, or 10:00 when no School row exists."""
    school = School.objects.first()
    return school.register_cutoff if school else DEFAULT_REGISTER_CUTOFF


def _user_name(user):
    return (user.get_full_name() or user.username) if user else ""


def _class_teachers(today):
    """{section_id: display name of the class teacher effective today}, in one query."""
    rows = SectionClassTeacher.objects.effective_on(today).select_related("teacher")
    return {row.section_id: _user_name(row.teacher) for row in rows}


def _section_order(section):
    grade = section.class_grade
    return (grade.display_order, natural_key(grade.name), natural_key(section.name))


def _register_url(register, can):
    """An existing register opens on its page (view_attendanceregister); a missing one on the
    create page (add_attendanceregister). Without the target's permission there is no link."""
    can_view, can_create = can
    if register is not None:
        return reverse("core:attendance-register-detail", args=[register.pk]) if can_view else None
    return reverse("core:attendance-register-create") if can_create else None


def _row(section, register, state, teachers, can):
    return {
        "class_name": section.class_grade.name,
        "section_name": section.name,
        "teacher_name": teachers.get(section.pk, ""),
        "state": state,
        "url": _register_url(register, can),
    }


def _unsubmitted_rows(today, teachers, can):
    items = sorted(
        reports.missing_attendance(today, today), key=lambda item: _section_order(item["section"])
    )
    return [_row(item["section"], item["register"], item["state"], teachers, can) for item in items]


def attendance_today(
    today, *, include_rows=False, can_view_registers=False, can_create_registers=False
):
    """Today's present/absent split and the registers still not submitted.

    The counts are school-wide aggregates. The not-taken rows name sections and their class
    teachers, so they are built only with `include_rows` (the caller may view registers);
    otherwise `not_taken` is None.
    """
    school_day = bool(reports.expected_registers(today, today))
    strip = analytics.today_strip(today)
    rows = None
    if include_rows:
        rows = []
        if school_day:
            rows = _unsubmitted_rows(
                today, _class_teachers(today), (can_view_registers, can_create_registers)
            )
    return {
        "school_day": school_day,
        "donut": charts.donut([("Present", strip["present"]), ("Absent", strip["absent"])]),
        "present": strip["present"],
        "absent": strip["absent"],
        "not_taken": rows,
    }


def register_compliance(
    today, now, cutoff, *, can_view_registers=False, can_create_registers=False
):
    """Registers submitted after the cut-off today, and ones still missing once it has passed."""
    local_now = timezone.localtime(now)
    before_cutoff = local_now.time() <= cutoff
    result = {"late": [], "missing": [], "before_cutoff": before_cutoff}
    if not reports.expected_registers(today, today):
        return result
    teachers = _class_teachers(today)
    can = (can_view_registers, can_create_registers)
    submitted = (
        AttendanceRegister.objects.filter(
            date=today, status=AttendanceRegister.Status.SUBMITTED, submitted_at__isnull=False
        )
        .select_related("section__class_grade")
    )
    late = []
    for register in submitted:
        stamp = timezone.localtime(register.submitted_at)
        if stamp.time() > cutoff:
            row = _row(
                register.section, register, AttendanceRegister.Status.SUBMITTED,
                teachers, can,
            )
            row["submitted_at"] = stamp
            late.append((_section_order(register.section), row))
    result["late"] = [row for _, row in sorted(late, key=lambda pair: pair[0])]
    if not before_cutoff:
        result["missing"] = _unsubmitted_rows(today, teachers, can)
    return result


def overdue_marks(today, days=15, *, can_open=False):
    """DRAFT assessments left open for more than `days` days, oldest first."""
    cutoff = today - datetime.timedelta(days=days)
    assessments = list(
        Assessment.objects.filter(status=Assessment.Status.DRAFT, assessment_date__lt=cutoff)
        .select_related("section__class_grade", "offering__subject", "offering__academic_year")
        .order_by("assessment_date", "pk")
    )
    if not assessments:
        return []
    assignments = defaultdict(list)
    for item in AssessmentTeacherAssignment.objects.filter(
        offering_id__in={a.offering_id for a in assessments},
        section_id__in={a.section_id for a in assessments},
    ).select_related("teacher"):
        assignments[(item.offering_id, item.section_id)].append(item)
    rows = []
    for assessment in assessments:
        on = assessment.assessment_date
        year_end = assessment.offering.academic_year.end_date
        teacher = None
        for item in assignments[(assessment.offering_id, assessment.section_id)]:
            ends = item.end_date or year_end
            if item.start_date <= on <= ends:
                teacher = item.teacher
        rows.append(
            {
                "name": assessment.name,
                "class_name": assessment.section.class_grade.name,
                "section_name": assessment.section.name,
                "subject": assessment.offering.subject.name,
                "teacher_name": _user_name(teacher),
                "days_late": (today - on).days - days,
                "url": (
                    reverse("core:assessment-detail", args=[assessment.pk]) if can_open else None
                ),
            }
        )
    return rows


def week_range(today):
    """(today, the Sunday on or after today)."""
    return today, today + datetime.timedelta(days=6 - today.weekday())


def week_assessments(today, *, can_open=False):
    """All assessments dated today (`today`) or tomorrow through Sunday (`later`)."""
    _, sunday = week_range(today)
    items = list(
        Assessment.objects.filter(assessment_date__range=(today, sunday))
        .select_related("section__class_grade", "offering__subject")
    )
    items.sort(key=lambda a: (a.assessment_date, _section_order(a.section), a.name, a.pk))
    result = {"today": [], "later": []}
    for assessment in items:
        row = {
            "name": assessment.name,
            "subject": assessment.offering.subject.name,
            "class_name": assessment.section.class_grade.name,
            "section_name": assessment.section.name,
            "date": assessment.assessment_date,
            "url": reverse("core:assessment-detail", args=[assessment.pk]) if can_open else None,
        }
        result["today" if assessment.assessment_date == today else "later"].append(row)
    return result


def _birthday_in_year(dob, year):
    try:
        return dob.replace(year=year)
    except ValueError:  # 29 Feb in a non-leap year
        return datetime.date(year, 2, 28)


def _next_birthday(dob, today):
    on = _birthday_in_year(dob, today.year)
    return on if on >= today else _birthday_in_year(dob, today.year + 1)


def week_birthdays(today, *, can_see_names=False):
    """Active students whose birthday falls from today to Sunday."""
    _, sunday = week_range(today)
    active = AcademicEnrollment.objects.filter(
        student_id=OuterRef("pk"), status=AcademicEnrollment.Status.ACTIVE
    )
    students = Student.objects.filter(
        status=Student.Status.ACTIVE, date_of_birth__isnull=False
    ).annotate(
        class_name=Subquery(active.values("class_grade__name")[:1]),
        class_order=Subquery(active.values("class_grade__display_order")[:1]),
    ).values("pk", "full_name", "date_of_birth", "class_name", "class_order")
    found = []
    for student in students:
        on = _next_birthday(student["date_of_birth"], today)
        if on <= sunday:
            found.append((student, on))
    result = {"today": [], "later": [], "count": len(found)}
    if not can_see_names:
        return result
    found.sort(
        key=lambda pair: (
            pair[1],
            pair[0]["class_order"] if pair[0]["class_order"] is not None else 0,
            natural_key(pair[0]["class_name"] or ""),
            pair[0]["full_name"],
        )
    )
    for student, on in found:
        row = {
            "name": student["full_name"],
            "class_name": student["class_name"] or "",
            "date": on,
            "age": on.year - student["date_of_birth"].year,
            "url": reverse("core:student-detail", args=[student["pk"]]),
        }
        result["today" if on == today else "later"].append(row)
    return result
