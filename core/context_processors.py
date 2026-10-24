from django.urls import reverse

from core.academic_years import current_academic_year
from core.authorization import is_guardian, is_teacher, user_areas
from core.breadcrumbs import breadcrumb_context
from core.models import School, SchoolLogo, business_today
from core.nav_badges import queue_counts
from core.navigation import current_area, office_nav, teacher_tabs


def _brand_logo(user):
    """URL of the current school logo for the header, or None (ADR 0020).

    Signed-in users only: the logo is served to signed-in users alone.
    """
    if not (user and user.is_authenticated):
        return None
    school = School.objects.first()
    logo = SchoolLogo.current_for(school) if school is not None else None
    if logo is None:
        return None
    return {"url": f"{reverse('core:school-logo')}?v={logo.pk}", "school_name": school.name}


def roles(request):
    """Expose role flags and navigation to templates (display only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match is not None else None
    area = current_area(request)
    if area == "admin":
        trail = breadcrumb_context(match, user)
        nav = office_nav(
            user, url_name, trail["nav_section"], queue_counts(user),
            current_academic_year(business_today()),
        )
    else:
        trail = {"breadcrumbs": [], "nav_section": None}
        nav = []
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
        "brand_logo": _brand_logo(user),
    }
