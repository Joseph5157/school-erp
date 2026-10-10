from core.authorization import is_teacher


def roles(request):
    """Expose role flags to templates (navigation only; views enforce access)."""
    return {"user_is_teacher": is_teacher(getattr(request, "user", None))}
