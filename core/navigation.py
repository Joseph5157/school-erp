"""Navigation data for the page shell (U1). Display only: views still enforce access."""

from dataclasses import dataclass

from django.urls import reverse

from core.authorization import user_areas


@dataclass(frozen=True)
class NavLink:
    label: str
    url_name: str  # namespaced, e.g. "core:student-list"
    perm: str | None = None


OFFICE_NAV = (
    ("School setup", (
        NavLink("School", "core:school-detail", "core.view_school"),
        NavLink("Academic Years", "core:academic-year-list", "core.view_academicyear"),
        NavLink("Classes/Grades", "core:class-grade-list", "core.view_classgrade"),
        NavLink("Subjects", "core:subject-list", "core.view_subject"),
    )),
    ("Admissions", (
        NavLink("Applicants", "core:applicant-list", "core.view_applicant"),
        NavLink("Students", "core:student-list", "core.view_student"),
        NavLink("Guardians", "core:guardian-list", "core.view_guardian"),
    )),
    ("Daily", (
        NavLink("Attendance", "core:attendance-register-list", "core.view_attendanceregister"),
        NavLink("Attendance reports", "core:attendance-reports", "core.view_attendanceentry"),
    )),
    ("Results", (
        NavLink("Stale publications", "core:publications-stale", "core.view_termpublication"),
    )),
    ("Access and security", (
        NavLink("Access reviews", "core:guardian-access-reviews",
                "core.view_guardianaccessreview"),
        NavLink("Sign-in lockouts", "core:login-lockouts", "accounts.clear_login_lockout"),
    )),
)

TEACHER_TABS = (
    NavLink("My day", "core:my-home"),
    NavLink("My students", "core:my-students"),
    NavLink("My assessments", "core:my-assessments"),
    NavLink("Results", "core:my-results"),
)

# Teacher pages whose URL name does not start with "my-".
_TEACHER_URL_NAMES = {"assessment-marks-entry"}


def _short(url_name):
    return url_name.split(":", 1)[-1]


def _link(link, url_name):
    return {
        "label": link.label,
        "url": reverse(link.url_name),
        "active": url_name == _short(link.url_name),
    }


def office_nav(user, url_name):
    """Office sidebar groups the user may see; empty groups are dropped."""
    if not (user and user.is_authenticated):
        return []
    groups = []
    for title, links in OFFICE_NAV:
        visible = [
            _link(link, url_name)
            for link in links
            if link.perm is None or user.has_perm(link.perm)
        ]
        if visible:
            groups.append({"title": title, "links": visible})
    return groups


def teacher_tabs(url_name):
    return [_link(tab, url_name) for tab in TEACHER_TABS]


def current_area(request):
    """Which area the current page belongs to: "guardian", "teacher", "admin" or None."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    match = getattr(request, "resolver_match", None)
    if match is not None and match.namespace == "portal":
        return "guardian"
    url_name = match.url_name if match is not None else None
    if url_name and (url_name.startswith("my-") or url_name in _TEACHER_URL_NAMES):
        return "teacher"
    keys = [key for key, _, _ in user_areas(user)]
    if "admin" in keys:
        return "admin"
    return keys[0] if keys else None
