"""Per-request account security (ADR 0013, Phase 6).

Placed immediately after Django's AuthenticationMiddleware. Resolving
`request.user` makes Django verify the session hash on every request, which
includes `User.session_version`, so a bumped version or an inactive login is
signed out at once. A login that must change its password reaches only the
password-change page, sign-out, static files and error responses.
"""

import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

ALLOWED_WHILE_CHANGE_REQUIRED = {"password_change", "logout"}
STARTED_KEY = "_auth_started_at"
SEEN_KEY = "_auth_last_seen"


def mark_session_started(sender, request, user, **kwargs):
    """user_logged_in receiver: start the absolute and idle clocks."""
    now = time.time()
    request.session[STARTED_KEY] = now
    request.session[SEEN_KEY] = now


class AccountSecurityMiddleware:
    """Session limits and forced password change, checked on every request.

    Order: resolving request.user verifies the session hash (password and
    session_version) and inactivity of the login; then the 30-minute idle and
    8-hour absolute limits (OD-5); then forced password change.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            now = time.time()
            started = request.session.get(STARTED_KEY, now)
            seen = request.session.get(SEEN_KEY, now)
            if (now - seen > settings.SESSION_IDLE_SECONDS
                    or now - started > settings.SESSION_ABSOLUTE_SECONDS):
                logout(request)
                return redirect(f"{reverse('login')}?next={request.path}")
            request.session[STARTED_KEY] = started
            request.session[SEEN_KEY] = now
            if getattr(user, "must_change_password", False) and not self._allowed(
                request.path_info
            ):
                return redirect(reverse("password_change"))
        return self.get_response(request)

    @staticmethod
    def _allowed(path):
        static_url = "/" + settings.STATIC_URL.lstrip("/")
        if path.startswith(static_url):
            return True
        try:
            match = resolve(path)
        except Resolver404:
            return True  # let the normal 404 response happen
        return match.url_name in ALLOWED_WHILE_CHANGE_REQUIRED
