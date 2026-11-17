"""Per-request account security (ADR 0013, Phase 6).

Placed immediately after Django's AuthenticationMiddleware. Resolving
`request.user` makes Django verify the session hash on every request, which
includes `User.session_version`, so a bumped version or an inactive login is
signed out at once. A login that must change its password reaches only the
password-change page, sign-out, static files and error responses.
"""

import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import patch_cache_control

from accounts import request_cache
from accounts.return_path import return_path

# The logo is shown in the header of the password-change page itself.
# session-status: the sign-out warning also runs on the password-change page.
ALLOWED_WHILE_CHANGE_REQUIRED = {"password_change", "logout", "school-logo", "session-status"}
# A literal, not reverse(): this runs on every request, including under a test URLconf that has no
# such route. config/urls.py routes this same path; a test keeps the two in step.
MANIFEST_PATH = "/manifest.webmanifest"
# The session warning asks how long is left with a GET here; that GET must not count as activity.
SESSION_STATUS_PATH = "/accounts/session/"
STARTED_KEY = "_auth_started_at"
SEEN_KEY = "_auth_last_seen"


def mark_session_started(sender, request, user, **kwargs):
    """user_logged_in receiver: start the absolute and idle clocks."""
    now = time.time()
    request.session[STARTED_KEY] = now
    request.session[SEEN_KEY] = now


def seconds_left(session, now=None):
    """Seconds until the idle and the absolute limit, for the session warning (audit 15 NOTIF-01)."""
    now = time.time() if now is None else now
    idle = settings.SESSION_IDLE_SECONDS - (now - session.get(SEEN_KEY, now))
    absolute = settings.SESSION_ABSOLUTE_SECONDS - (now - session.get(STARTED_KEY, now))
    return {"idle": max(0, round(idle)), "absolute": max(0, round(absolute))}


def expired_redirect(request, reason):
    """Sign-in page that says why, and whether a submitted change was lost (audit 18 ERR-01).

    Only the reason goes in the URL, never posted values. The browser is told to drop its cached
    copies of signed-in pages (ERR-03).
    """
    params = {"next": return_path(request, reverse("home")), "expired": reason}
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        params["unsaved"] = "1"
    response = redirect(f"{reverse('login')}?{urlencode(params)}")
    response["Clear-Site-Data"] = '"cache"'
    return response


class AccountSecurityMiddleware:
    """Session limits and forced password change, checked on every request.

    Order: resolving request.user verifies the session hash (password and
    session_version) and inactivity of the login; then the 30-minute idle and
    8-hour absolute limits (OD-5); then forced password change.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == MANIFEST_PATH:
            # Public install metadata (PWA Gate 1). Exactly this path, before request.user is read:
            # it neither moves the idle clock nor redirects a forced password change.
            return self.get_response(request)
        user = request.user
        if user.is_authenticated:
            now = time.time()
            started = request.session.get(STARTED_KEY, now)
            seen = request.session.get(SEEN_KEY, now)
            if now - started > settings.SESSION_ABSOLUTE_SECONDS:
                logout(request)
                return expired_redirect(request, "limit")
            if now - seen > settings.SESSION_IDLE_SECONDS:
                logout(request)
                return expired_redirect(request, "idle")
            request.session[STARTED_KEY] = started
            if not (request.path_info == SESSION_STATUS_PATH and request.method == "GET"):
                request.session[SEEN_KEY] = now
            if getattr(user, "must_change_password", False) and not self._allowed(
                request.path_info
            ):
                return redirect(reverse("password_change"))
            request_cache.enable(user)  # role lookups are asked once per request (audit 08)
            response = self.get_response(request)
            # Signed-in pages carry student and account data: a shared browser must not keep a copy
            # after logout (audit 18 ERR-03). A view that set its own policy keeps it.
            if "Cache-Control" not in response and response.get("Content-Type", "").startswith("text/html"):
                patch_cache_control(response, no_store=True, private=True)
            return response
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
