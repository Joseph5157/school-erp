"""The Academic Year the office treats as current (Students list and sidebar)."""

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
