"""'Set up your school' checklist for the admin Overview page.

Eight setup steps, each carrying a status. A step that is not done shows a
count (the number of things still missing) and a button to the page that
fixes it. The class-teacher and subject-teacher counts reuse
`assignments.overview` -- the same source as the Assignment overview page --
so the two cannot disagree. Read-only; no HTTP here, no new models.

The checklist is recomputed on every request, so it hides once every step is
done and reappears automatically if something breaks later (a teacher is
deactivated, a placement ends, and so on).
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from core import assignments
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicEnrollment,
    AcademicYear,
    ClassGrade,
    School,
    Section,
    Student,
    Subject,
    business_today,
)


def _step(key, label, done, count, problem, url, action):
    return {
        "key": key,
        "label": label,
        "done": done,
        "count": count,
        "problem": problem,
        "url": url,
        "action": action,
    }


def _year():
    """The Academic Year the checklist targets: the most recent by start date."""
    return AcademicYear.objects.order_by("-start_date").first()


def _unplaced_students():
    """Active Students with no ACTIVE enrollment (i.e. no placement)."""
    return (
        Student.objects.filter(status=Student.Status.ACTIVE)
        .exclude(enrollments__status=AcademicEnrollment.Status.ACTIVE)
        .distinct()
    )


def setup_steps(today=None):
    """All eight setup steps in order, with `done`, `count`, `problem` and a fix `url`."""
    if today is None:
        today = business_today()
    year = _year()

    school = School.objects.first()
    has_classes = ClassGrade.objects.exists()
    has_sections = Section.objects.exists()
    has_subjects = Subject.objects.filter(is_active=True).exists()
    has_teachers = get_user_model().objects.filter(
        groups__name=TEACHERS_GROUP_NAME, is_active=True
    ).exists()

    if year is not None:
        overview = assignments.overview(year, today)
        class_gaps = overview["class_gaps"]
        subject_gaps = overview["subject_gaps"]
        class_url = reverse("core:academic-year-class-teachers", args=[year.pk])
        subject_url = reverse("core:academic-year-teacher-assignments", args=[year.pk])
    else:
        class_gaps = subject_gaps = 0
        class_url = subject_url = reverse("core:academic-year-list")

    unplaced = _unplaced_students().count()

    return [
        _step(
            "school", "School profile", school is not None,
            0 if school is not None else 1,
            "Add the school's name and details.",
            reverse("core:school-create"), "Fix",
        ),
        _step(
            "academic-year", "Academic year", year is not None,
            0 if year is not None else 1,
            "Create the first academic year.",
            reverse("core:academic-year-list"), "Fix",
        ),
        _step(
            "classes", "Classes and sections", has_classes and has_sections,
            0 if has_classes and has_sections else 1,
            "Add at least one Class/Grade and Section.",
            reverse("core:class-grade-list"), "Fix",
        ),
        _step(
            "subjects", "Subjects offered", has_subjects,
            0 if has_subjects else 1,
            "Add at least one Subject.",
            reverse("core:subject-list"), "Fix",
        ),
        _step(
            "teachers", "Teacher accounts", has_teachers,
            0 if has_teachers else 1,
            "Create at least one teacher account.",
            reverse("core:teacher-list"), "Fix",
        ),
        _step(
            "class-teachers", "A class teacher for every section", class_gaps == 0,
            class_gaps,
            f"{class_gaps} Section(s) without a class teacher.",
            class_url, "Assign",
        ),
        _step(
            "subject-teachers", "A subject teacher for every subject", subject_gaps == 0,
            subject_gaps,
            f"{subject_gaps} Subject/Section(s) without a teacher.",
            subject_url, "Assign",
        ),
        _step(
            "students-placed", "Every student placed in a section", unplaced == 0,
            unplaced,
            f"{unplaced} Student(s) not placed in a Section.",
            reverse("core:student-list"), "Fix",
        ),
    ]


def setup_complete(steps):
    """True when every step is done, so the Overview can hide the checklist."""
    return all(step["done"] for step in steps)
