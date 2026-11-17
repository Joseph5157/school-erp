"""Template data for the session warning (audit 15 NOTIF-01, audit 18 ERR-01)."""

from accounts.middleware import seconds_left


def session_limits(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not hasattr(request, "session"):
        return {}
    return {"session_limits": seconds_left(request.session)}
