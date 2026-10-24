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
    perm: str | None = None  # shown only to users holding it (display only)


@dataclass(frozen=True)
class Rule:
    section: str  # short URL name of the sidebar link to keep active
    trail: tuple  # ancestor Crumbs, outermost first (after "Overview")
    label: str  # current page


_STUDENTS = Crumb("Students", "core:student-list")
_APPLICANTS = Crumb("Applicants", "core:applicant-list")
_ATTENDANCE = Crumb("Attendance", "core:attendance-register-list")
_ANNOUNCEMENTS = Crumb("Announcements", "core:announcement-list", perm="core.view_announcement")
_TEACHERS = Crumb("Teachers", "core:teacher-list")
_TEACHER = Crumb("Teacher", "core:teacher-detail", True)
_TIMETABLE = Crumb("Timetable", "core:timetable-index")
_ATTENDANCE_REPORTS = Crumb(
    "Attendance reports", "core:attendance-reports", perm="core.view_attendanceentry"
)

_DOCUMENTS = Crumb("Documents", "core:document-index", perm="core.issue_document")

_ACADEMIC_YEARS = Crumb("Academic Years", "core:academic-year-list", perm="core.view_academicyear")

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
    "attendance-reports": Rule("attendance-reports", (), "Attendance reports"),
    "report-daily-absentees": Rule(
        "attendance-reports", (_ATTENDANCE_REPORTS,), "Daily absent students"
    ),
    "report-missing-attendance": Rule(
        "attendance-reports", (_ATTENDANCE_REPORTS,), "Missing attendance"
    ),
    "report-monthly-section": Rule(
        "attendance-reports", (_ATTENDANCE_REPORTS,), "Monthly summary"
    ),
    # Student history keeps its logical parents (the Student), shown only to viewers who may open them.
    "student-attendance": Rule(
        "student-list",
        (
            Crumb("Students", "core:student-list", perm="core.view_student"),
            Crumb("Student", "core:student-detail", True, perm="core.view_student"),
        ),
        "Attendance",
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
    "timetable-issues": Rule("timetable-index", (_TIMETABLE,), "Issues"),
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
    # Grading scales (D1-5A). The list and create routes take the Academic Year's pk, but the detail and
    # edit routes take the scale's pk, so those two never reuse `pk` for the year's scale list (their
    # page header links back with the real year id instead).
    "academic-year-grading-scales": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Grading scales"),
    "grading-scale-create": Rule(
        "academic-year-list",
        (
            _ACADEMIC_YEARS,
            Crumb("Grading scales", "core:academic-year-grading-scales", True, perm="core.view_gradingscale"),
        ),
        "Add grading scale",
    ),
    "grading-scale-detail": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Grading scale"),
    "grading-scale-update": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Edit grading scale"),
    # Assessments (D1-5B). Same pk discipline as above: the list and create routes take the Academic Year's pk,
    # the detail and edit routes take the assessment's pk, and the correction route takes a result's pk, so
    # only a crumb for the same model may reuse `pk` (edit -> its own assessment). Those pages link back to
    # the year's list with the real year id from their page header.
    "academic-year-assessments": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Assessments"),
    "assessment-create": Rule(
        "academic-year-list",
        (
            _ACADEMIC_YEARS,
            Crumb("Assessments", "core:academic-year-assessments", True, perm="core.view_assessment"),
        ),
        "Plan an assessment",
    ),
    "assessment-detail": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Assessment"),
    "assessment-update": Rule(
        "academic-year-list",
        (_ACADEMIC_YEARS, Crumb("Assessment", "core:assessment-detail", True, perm="core.view_assessment")),
        "Edit assessment",
    ),
    "result-correct": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Correct result"),
    # Result reports (D1-5C). Only administrator routes are listed; the teacher report card (my-report-card) has
    # no rule and keeps the teacher shell. Crumbs reuse `pk` only for the same model: the result sheet's pk is an
    # assessment (-> its detail), the Student reports' pk is a Student (-> Student, Student results), and the
    # matrix's pk is an Academic Year (-> its assessment list).
    "report-result-sheet": Rule(
        "academic-year-list",
        (_ACADEMIC_YEARS, Crumb("Assessment", "core:assessment-detail", True, perm="core.view_assessment")),
        "Result sheet",
    ),
    "report-student-results": Rule(
        "student-list",
        (
            Crumb("Students", "core:student-list", perm="core.view_student"),
            Crumb("Student", "core:student-detail", True, perm="core.view_student"),
        ),
        "Results",
    ),
    "report-term-report-card": Rule(
        "student-list",
        (
            Crumb("Students", "core:student-list", perm="core.view_student"),
            Crumb("Student", "core:student-detail", True, perm="core.view_student"),
            Crumb("Results", "core:report-student-results", True, perm="core.view_studentresult"),
        ),
        "Report card",
    ),
    "report-subject-section-results": Rule(
        "academic-year-list",
        (
            _ACADEMIC_YEARS,
            Crumb("Assessments", "core:academic-year-assessments", True, perm="core.view_assessment"),
        ),
        "Subject/Section results",
    ),
    # Term publication (D1-5D). The preview's pk is a Term (not an Academic Year), so it shows only the no-id
    # "Academic Years" ancestor and links back to the year's Terms from its header with the real year id. The
    # publication routes use a publication's pk, so the only pk reuse is Publication detail from Withdraw.
    "term-publication": Rule("academic-year-list", (_ACADEMIC_YEARS,), "Publish to guardians"),
    "publications-stale": Rule("publications-stale", (), "Stale publications"),
    "publication-detail": Rule(
        "publications-stale",
        (Crumb("Stale publications", "core:publications-stale", perm="core.view_termpublication"),),
        "Publication",
    ),
    "publication-withdraw": Rule(
        "publications-stale",
        (
            Crumb("Stale publications", "core:publications-stale", perm="core.view_termpublication"),
            Crumb("Publication", "core:publication-detail", True, perm="core.view_termpublication"),
        ),
        "Withdraw",
    ),
    # Documents (D1-6C). The index is the sidebar link itself; the three issuing/list pages show it as a parent only to
    # viewers who can open it (all need issue_document). The two PDF routes are responses, not pages, and have no rule.
    "document-index": Rule("document-index", (), "Documents"),
    "bonafide-create": Rule("document-index", (_DOCUMENTS,), "Bonafide certificate"),
    "attendance-summary": Rule("document-index", (_DOCUMENTS,), "Attendance summary"),
    "document-report-cards": Rule("document-index", (_DOCUMENTS,), "Report card PDFs"),
    # Announcements (D1-6B). The list is the sidebar link itself; the form/preview (one route) and the detail show it as
    # a parent only to viewers who can open it. The prepare and withdraw routes are POST-only redirects.
    "announcement-list": Rule("announcement-list", (), "Announcements"),
    # Security operations (D1-6A). `section` is the sidebar link's route name, not its "Access and security" group label.
    "login-lockouts": Rule("login-lockouts", (), "Sign-in lockouts"),
}

_EMPTY = {"breadcrumbs": [], "nav_section": None}


OVERVIEW_PERM = "core.view_school"  # what core:admin-overview requires


def breadcrumb_context(match, user=None):
    """The trail and sidebar section for `match`.

    With `user=None` every crumb is shown, as before. With a user, a crumb whose
    destination the user cannot open is left out (the Overview crumb included),
    so the trail never contains a link that ends in a 403. A trail left with
    only the current page is dropped; the sidebar section is kept either way.
    """

    def allowed(perm):
        return user is None or perm is None or user.has_perm(perm)

    if match is None or match.namespace != "core":
        return dict(_EMPTY)
    rule = RULES.get(match.url_name)
    if rule is None:
        return dict(_EMPTY)
    try:
        crumbs = []
        if allowed(OVERVIEW_PERM):
            crumbs.append({"label": "Overview", "url": reverse("core:admin-overview")})
        for crumb in rule.trail:
            if not allowed(crumb.perm):
                continue
            kwargs = {"pk": match.kwargs["pk"]} if crumb.uses_pk else {}
            crumbs.append({"label": crumb.label, "url": reverse(crumb.url_name, kwargs=kwargs)})
    except (NoReverseMatch, KeyError):
        return dict(_EMPTY)
    crumbs.append({"label": rule.label, "url": None})
    if user is not None and len(crumbs) == 1:
        crumbs = []
    return {"breadcrumbs": crumbs, "nav_section": rule.section}
