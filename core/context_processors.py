from core.authorization import is_guardian, is_teacher, user_areas
from core.breadcrumbs import breadcrumb_context
from core.nav_badges import queue_counts
from core.navigation import current_area, office_nav, teacher_tabs


def roles(request):
    """Expose role flags and navigation to templates (display only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match is not None else None
    area = current_area(request)
    if area == "admin":
        trail = breadcrumb_context(match)
        nav = office_nav(user, url_name, trail["nav_section"], queue_counts(user))
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
    }
