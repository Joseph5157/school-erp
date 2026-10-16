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
