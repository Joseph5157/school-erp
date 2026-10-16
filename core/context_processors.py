from core.breadcrumbs import breadcrumb_context
from core.authorization import is_guardian, is_teacher, user_areas
from core.navigation import current_area, office_nav, teacher_tabs


def roles(request):
    """Expose role flags and navigation to templates (display only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match is not None else None
    area = current_area(request)
    trail = breadcrumb_context(match) if area == "admin" else {"breadcrumbs": [], "nav_section": None}
    return {
        "user_is_teacher": is_teacher(user),
        "user_is_guardian": is_guardian(user),
        "user_areas": areas,
        "user_has_several_areas": len(areas) > 1,
        "current_area": area,
        "office_nav": office_nav(user, url_name, trail["nav_section"]) if area == "admin" else [],
        "breadcrumbs": trail["breadcrumbs"],
        "nav_section": trail["nav_section"],
        "teacher_tabs": teacher_tabs(url_name),
    }
