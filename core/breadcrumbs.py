"""Breadcrumb trails and sidebar sections for deep admin pages (F05).

One declarative map, so views never build trails by hand. A page that is
not listed gets no trail and keeps exact-match sidebar highlighting.
"""

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class Crumb:
    label: str
    url_name: str
    uses_pk: bool = False  # reverse with the current page's `pk`


@dataclass(frozen=True)
class Rule:
    section: str  # short URL name of the sidebar link to keep active
    trail: tuple  # ancestor Crumbs, outermost first (after "Overview")
    label: str  # current page


_STUDENTS = Crumb("Students", "core:student-list")
_APPLICANTS = Crumb("Applicants", "core:applicant-list")
_ATTENDANCE = Crumb("Attendance", "core:attendance-register-list")
_ANNOUNCEMENTS = Crumb("Announcements", "core:announcement-list")
_TEACHERS = Crumb("Teachers", "core:teacher-list")
_TEACHER = Crumb("Teacher", "core:teacher-detail", True)
_TIMETABLE = Crumb("Timetable", "core:timetable-index")

RULES = {
    "student-detail": Rule("student-list", (_STUDENTS,), "Student"),
    "student-deactivate-confirm": Rule(
        "student-list", (_STUDENTS, Crumb("Student", "core:student-detail", True)), "Deactivate"
    ),
    "applicant-detail": Rule("applicant-list", (_APPLICANTS,), "Applicant"),
    "applicant-decision-confirm": Rule(
        "applicant-list",
        (_APPLICANTS, Crumb("Applicant", "core:applicant-detail", True)),
        "Decision",
    ),
    "attendance-register-detail": Rule("attendance-register-list", (_ATTENDANCE,), "Register"),
    "attendance-entry-correct": Rule("attendance-register-list", (_ATTENDANCE,), "Correct entry"),
    "announcement-create": Rule("announcement-list", (_ANNOUNCEMENTS,), "New announcement"),
    "teacher-create": Rule("teacher-list", (_TEACHERS,), "New teacher"),
    "teacher-detail": Rule("teacher-list", (_TEACHERS,), "Teacher"),
    "teacher-reset-password": Rule("teacher-list", (_TEACHERS, _TEACHER), "Reset password"),
    "teacher-username": Rule("teacher-list", (_TEACHERS, _TEACHER), "Change username"),
    "teacher-deactivate": Rule("teacher-list", (_TEACHERS, _TEACHER), "Deactivate"),
    "teacher-reactivate": Rule("teacher-list", (_TEACHERS, _TEACHER), "Reactivate"),
    "teacher-load": Rule("teacher-list", (_TEACHERS, _TEACHER), "Workload"),
    "timetable-periods": Rule("timetable-index", (_TIMETABLE,), "Periods"),
    "timetable-period-create": Rule(
        "timetable-index",
        (_TIMETABLE, Crumb("Periods", "core:timetable-periods", True)),
        "Add period",
    ),
    "timetable-period-update": Rule("timetable-index", (_TIMETABLE,), "Edit period"),
    "timetable-period-delete": Rule("timetable-index", (_TIMETABLE,), "Delete period"),
    "timetable-sections": Rule("timetable-index", (_TIMETABLE,), "Sections"),
    "timetable-grid": Rule(
        "timetable-index",
        (_TIMETABLE, Crumb("Sections", "core:timetable-sections", True)),
        "Weekly timetable",
    ),
    "timetable-slot-create": Rule(
        "timetable-index",
        (_TIMETABLE, Crumb("Sections", "core:timetable-sections", True)),
        "Add slot",
    ),
    "timetable-slot-change": Rule("timetable-index", (_TIMETABLE,), "Change slot"),
    "timetable-slot-end": Rule("timetable-index", (_TIMETABLE,), "End slot"),
    "timetable-slot-delete": Rule("timetable-index", (_TIMETABLE,), "Delete slot"),
    "announcement-detail": Rule("announcement-list", (_ANNOUNCEMENTS,), "Announcement"),
}

_EMPTY = {"breadcrumbs": [], "nav_section": None}


def breadcrumb_context(match):
    if match is None or match.namespace != "core":
        return dict(_EMPTY)
    rule = RULES.get(match.url_name)
    if rule is None:
        return dict(_EMPTY)
    try:
        crumbs = [{"label": "Overview", "url": reverse("core:admin-overview")}]
        for crumb in rule.trail:
            kwargs = {"pk": match.kwargs["pk"]} if crumb.uses_pk else {}
            crumbs.append({"label": crumb.label, "url": reverse(crumb.url_name, kwargs=kwargs)})
    except (NoReverseMatch, KeyError):
        return dict(_EMPTY)
    crumbs.append({"label": rule.label, "url": None})
    return {"breadcrumbs": crumbs, "nav_section": rule.section}
