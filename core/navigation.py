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
    year_arg: bool = False  # URL takes the current Academic Year pk; hidden when there is none


OFFICE_NAV = (
    ("Home", (
        NavLink("Overview", "core:admin-overview", "core.view_school"),
    )),
    ("School setup", (
        NavLink("School", "core:school-detail", "core.view_school"),
        NavLink("Academic Years", "core:academic-year-list", "core.view_academicyear"),
        NavLink("Classes/Grades", "core:class-grade-list", "core.view_classgrade"),
        NavLink("Subjects", "core:subject-list", "core.view_subject"),
        NavLink("Timetable", "core:timetable-index", "core.view_timetableperiod"),
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
        NavLink("Message queue", "core:notifications-to-send", "core.send_notification"),
        NavLink("Documents", "core:document-index", "core.issue_document"),
    )),
    ("Assessments & Results", (
        NavLink("Assessments", "core:academic-year-assessments", "core.view_assessment", year_arg=True),
        NavLink("Subject/Section results", "core:report-subject-section-results",
                "core.view_studentresult", year_arg=True),
        NavLink("Grading scales", "core:academic-year-grading-scales", "core.view_gradingscale",
                year_arg=True),
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


def _link(link, url_name, section=None, counts=None, year=None):
    short = _short(link.url_name)
    args = [year.pk] if link.year_arg else []
    return {
        "label": link.label,
        "mobile_label": link.mobile_label or link.label,
        "icon": link.icon,
        "url": reverse(link.url_name, args=args),
        "active": url_name == short or section == short,
        "badge": (counts or {}).get(link.url_name, 0),
    }


def office_nav(user, url_name, section=None, counts=None, year=None):
    """Office sidebar groups the user may see; empty groups are dropped.

    `counts` maps a link's namespaced URL name to a waiting-items number. `year` is the
    current Academic Year: links that need one are left out when there is none. A group
    is `open` when it holds the active link (and always for Home); `badge` totals its links.
    """
    if not (user and user.is_authenticated):
        return []
    groups = []
    for title, links in OFFICE_NAV:
        visible = [
            _link(link, url_name, section, counts, year)
            for link in links
            if (link.perm is None or user.has_perm(link.perm)) and (year is not None or not link.year_arg)
        ]
        if visible:
            groups.append({
                "title": title,
                "links": visible,
                "open": title == "Home" or any(item["active"] for item in visible),
                "badge": sum(item["badge"] for item in visible),
            })
    return groups


def teacher_tabs(url_name):
    """Teacher tabs; a nested page keeps its parent destination active."""
    parent = TEACHER_TAB_PARENTS.get(url_name)
    return [_link(tab, url_name, parent) for tab in TEACHER_TABS]


def current_area(request):
    """Which area the current page belongs to: "guardian", "teacher", "admin" or None.

    The requested URL only chooses between areas the signed-in user is entitled to
    (user_areas, ADR 0013). A denied page (403) therefore never borrows another area's
    navigation: a Guardian sent to a Teacher URL stays in the "guardian" area.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    keys = [key for key, _, _ in user_areas(user)]
    match = getattr(request, "resolver_match", None)
    if match is not None and match.namespace == "portal" and "guardian" in keys:
        return "guardian"
    url_name = match.url_name if match is not None else None
    if (
        url_name
        and (url_name.startswith("my-") or url_name in _TEACHER_URL_NAMES)
        and "teacher" in keys
    ):
        return "teacher"
    if "admin" in keys:
        return "admin"
    return keys[0] if keys else None
