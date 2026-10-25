from django.urls import reverse

from core.academic_years import (
    current_academic_year,
    is_year_scoped_page,
    viewed_year_pk,
    year_switch_url,
)
from core.authorization import is_guardian, is_teacher, user_areas
from core.breadcrumbs import breadcrumb_context
from core.models import AcademicYear, School, SchoolLogo, business_today
from core.nav_badges import queue_counts
from core.navigation import current_area, office_nav, teacher_tabs


def _brand_logo(user, school):
    """URL of the current school logo for the header, or None (ADR 0020).

    Signed-in users only: the logo is served to signed-in users alone.
    """
    if not (user and user.is_authenticated):
        return None
    logo = SchoolLogo.current_for(school) if school is not None else None
    if logo is None:
        return None
    return {"url": f"{reverse('core:school-logo')}?v={logo.pk}", "school_name": school.name}


def _year_selector(match, current_year):
    """Year-selector context for the office header (UI-04): one query for all years."""
    years = list(AcademicYear.objects.order_by("-start_date", "-pk"))
    scoped = is_year_scoped_page(match)
    viewing = None
    if scoped:
        viewing = next((y for y in years if y.pk == viewed_year_pk(match)), None)
    shown = viewing or current_year
    return {
        "year_choices": [
            {
                "name": y.name,
                "url": year_switch_url(match, y),
                "selected": shown is not None and y.pk == shown.pk,
            }
            for y in years
        ],
        "viewing_year_name": viewing.name if viewing is not None else "",
        "viewing_year_is_current": (
            viewing is None or current_year is None or viewing.pk == current_year.pk
        ),
        "year_is_scoped_page": viewing is not None,
    }


def roles(request):
    """Expose role flags and navigation to templates (display only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match is not None else None
    area = current_area(request)
    signed_in = bool(user and user.is_authenticated)
    school = School.objects.first() if signed_in else None
    year = None
    selector = {
        "year_choices": [],
        "viewing_year_name": "",
        "viewing_year_is_current": True,
        "year_is_scoped_page": False,
    }
    if area == "admin":
        trail = breadcrumb_context(match, user)
        year = current_academic_year(business_today())
        selector = _year_selector(match, year)
        nav = office_nav(user, url_name, trail["nav_section"], queue_counts(user), year)
    else:
        trail = {"breadcrumbs": [], "nav_section": None}
        nav = []
        if area == "teacher":
            year = current_academic_year(business_today())
    # Header context (UI-11): office and teacher areas only; the Guardian portal has its own shell.
    in_header_area = area in ("admin", "teacher")
    return {
        "user_is_teacher": is_teacher(user),
        "user_is_guardian": is_guardian(user),
        "user_areas": areas,
        "user_has_several_areas": len(areas) > 1,
        "current_area": area,
        "office_nav": nav,
        "breadcrumbs": trail["breadcrumbs"],
        "nav_section": trail["nav_section"],
        "teacher_tabs": teacher_tabs(url_name),
        "brand_logo": _brand_logo(user, school),
        "school_name": (school.name if school is not None else "") if in_header_area else "",
        "current_year_name": (year.name if year is not None else "") if in_header_area else "",
        **selector,
    }
