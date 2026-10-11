from core.authorization import is_guardian, is_teacher, user_areas


def roles(request):
    """Expose role flags to templates (navigation only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    return {
        "user_is_teacher": is_teacher(user),
        "user_is_guardian": is_guardian(user),
        "user_areas": areas,
        "user_has_several_areas": len(areas) > 1,
    }
