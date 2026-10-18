"""Navigation data for the page shell (U1). Display only: views still enforce access."""

from dataclasses import dataclass

from django.urls import reverse

from core.authorization import user_areas


@dataclass(frozen=True)
class NavLink:
    label: str
    url_name: str  # namespaced, e.g. "core:student-list"
    perm: str | None = None
    mobile_label: str | None = None  # shorter label for the phone bottom bar
    icon: str | None = None  # key into partials/_tab_icon.html


OFFICE_NAV = (
    ("Home", (
        NavLink("Overview", "core:admin-overview", "core.view_school"),
    )),
    ("School setup", (
        NavLink("School", "core:school-detail", "core.view_school"),
        NavLink("Academic Years", "core:academic-year-list", "core.view_academicyear"),
        NavLink("Classes/Grades", "core:class-grade-list", "core.view_classgrade"),
        NavLink("Subjects", "core:subject-list", "core.view_subject"),
        NavLink("Teachers", "core:teacher-list", "accounts.manage_teacher_accounts"),
    )),
    ("Admissions", (
        NavLink("Applicants", "core:applicant-list", "core.view_applicant"),
        NavLink("Students", "core:student-list", "core.view_student"),
        NavLink("Guardians", "core:guardian-list", "core.view_guardian"),
        NavLink("Import", "core:import-list", "core.view_importbatch"),
    )),
    ("Daily", (
        NavLink("Attendance", "core:attendance-register-list", "core.view_attendanceregister"),
        NavLink("Attendance reports", "core:attendance-reports", "core.view_attendanceentry"),
        NavLink("Announcements", "core:announcement-list", "core.view_announcement"),
        NavLink("To send", "core:notifications-to-send", "core.send_notification"),
        NavLink("Documents", "core:document-index", "core.issue_document"),
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
    NavLink("My day", "core:my-home", mobile_label="Today", icon="today"),
    NavLink("My students", "core:my-students", mobile_label="Students", icon="students"),
    NavLink("My assessments", "core:my-assessments",
            mobile_label="Assessments", icon="assessments"),
    NavLink("Results", "core:my-results", mobile_label="Results", icon="results"),
)

# Nested Teacher pages mapped to the bottom-nav destination they belong to
# (short URL names). The destinations themselves match on their own name.
TEACHER_TAB_PARENTS = {
    "my-attendance": "my-home",
    "my-attendance-history": "my-home",
    "my-attendance-assignment": "my-home",
    "my-attendance-register": "my-home",
    "my-student-detail": "my-students",
    "my-gradebook": "my-assessments",
    "assessment-marks-entry": "my-assessments",
    "my-subject-results": "my-results",
    "my-report-card": "my-results",
}

# Teacher pages whose URL name does not start with "my-".
_TEACHER_URL_NAMES = {"assessment-marks-entry"}


def _short(url_name):
    return url_name.split(":", 1)[-1]


def _link(link, url_name, section=None, counts=None):
    short = _short(link.url_name)
    return {
        "label": link.label,
        "mobile_label": link.mobile_label or link.label,
        "icon": link.icon,
        "url": reverse(link.url_name),
        "active": url_name == short or section == short,
        "badge": (counts or {}).get(link.url_name, 0),
    }


def office_nav(user, url_name, section=None, counts=None):
    """Office sidebar groups the user may see; empty groups are dropped.

    `counts` maps a link's namespaced URL name to a waiting-items number.
    """
    if not (user and user.is_authenticated):
        return []
    groups = []
    for title, links in OFFICE_NAV:
        visible = [
            _link(link, url_name, section, counts)
            for link in links
            if link.perm is None or user.has_perm(link.perm)
        ]
        if visible:
            groups.append({"title": title, "links": visible})
    return groups


def teacher_tabs(url_name):
    """Teacher tabs; a nested page keeps its parent destination active."""
    parent = TEACHER_TAB_PARENTS.get(url_name)
    return [_link(tab, url_name, parent) for tab in TEACHER_TABS]


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
