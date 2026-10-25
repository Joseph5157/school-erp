"""The Academic Year the office treats as current (Students list and sidebar)."""

from django.urls import reverse

from core.models import AcademicYear


def current_academic_year(today):
    """The Academic Year containing `today`, else the most recent by start date.

    "Most recent by start date" alone would pick a future year that has been
    set up in advance and make every Student look unplaced, so prefer the year
    that is actually in progress. None when no Academic Year exists.
    """
    return (
        AcademicYear.objects.filter(start_date__lte=today, end_date__gte=today)
        .order_by("-start_date")
        .first()
        or AcademicYear.objects.order_by("-start_date").first()
    )


# Year-scoped pages (UI-04): the URL's `pk` kwarg is the Academic Year pk and no
# other kwargs are needed, so the year selector can reopen the same page for
# another year. Full namespaced names, as `resolver_match.view_name` gives them.
# A new `academic-years/<int:pk>/...` URL must be added here, to
# YEAR_SCOPED_SECTION_PAGES, or to the exclusion set in
# core/tests/test_ui_year_selector_context.py.
YEAR_SCOPED_ALLOW_LIST = frozenset(
    {
        "core:academic-year-calendar",
        "core:calendar-day-create",
        "core:academic-year-saturday-rule",
        "core:timetable-periods",
        "core:timetable-period-create",
        "core:timetable-issues",
        "core:timetable-sections",
        "core:academic-year-terms",
        "core:term-create",
        "core:academic-year-offerings",
        "core:offering-create",
        "core:academic-year-assignments",
        "core:assignment-copy",
        "core:academic-year-class-teachers",
        "core:class-teacher-assign",
        "core:academic-year-teacher-assignments",
        "core:teacher-assignment-create",
        "core:academic-year-assessments",
        "core:assessment-create",
        "core:report-subject-section-results",
        "core:academic-year-grading-scales",
        "core:grading-scale-create",
    }
)

# Year-scoped pages that also carry a section pk: switching year cannot reuse
# the section, so they open the other year's list page instead.
YEAR_SCOPED_SECTION_PAGES = {
    "core:timetable-grid": "core:timetable-sections",
    "core:timetable-slot-create": "core:timetable-sections",
}

YEAR_LIST_URL_NAME = "core:academic-year-list"


def is_year_scoped_page(resolver_match):
    """True when the request is an allow-listed page whose `pk` is the year pk."""
    return resolver_match is not None and resolver_match.view_name in YEAR_SCOPED_ALLOW_LIST


def viewed_year_pk(resolver_match):
    """The year pk of an allow-listed year-scoped page, else None."""
    if not is_year_scoped_page(resolver_match):
        return None
    return resolver_match.kwargs.get("pk")


def year_switch_url(resolver_match, year):
    """Where choosing `year` in the year selector should go.

    Allow-listed year-scoped pages reopen for `year` (query string dropped);
    section-level year pages open the year's sections list; everything else
    (child-object pages, year-independent pages, no match) opens the Academic
    Years list.
    """
    if resolver_match is not None:
        name = resolver_match.view_name
        if name in YEAR_SCOPED_ALLOW_LIST:
            return reverse(name, kwargs={**resolver_match.kwargs, "pk": year.pk})
        if name in YEAR_SCOPED_SECTION_PAGES:
            return reverse(YEAR_SCOPED_SECTION_PAGES[name], kwargs={"pk": year.pk})
    return reverse(YEAR_LIST_URL_NAME)
