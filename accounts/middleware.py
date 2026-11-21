"""Per-request account security (ADR 0013, Phase 6).

Placed immediately after Django's AuthenticationMiddleware. Resolving
`request.user` makes Django verify the session hash on every request, which
includes `User.session_version`, so a bumped version or an inactive login is
signed out at once. A login that must change its password reaches only the
password-change page, sign-out, static files and error responses.
"""

import time
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect, resolve_url
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import patch_cache_control

from accounts import request_cache
from accounts.return_path import return_path
from core import usage

# The logo is shown in the header of the password-change page itself.
# session-status: the sign-out warning also runs on the password-change page.
ALLOWED_WHILE_CHANGE_REQUIRED = {"password_change", "logout", "school-logo", "session-status"}
# A literal, not reverse(): this runs on every request, including under a test URLconf that has no
# such route. config/urls.py routes this same path; a test keeps the two in step.
MANIFEST_PATH = "/manifest.webmanifest"
# The session warning asks how long is left with a GET here; that GET must not count as activity.
SESSION_STATUS_PATH = "/accounts/session/"
# Usage beacons (ADR 0027) are sent by the page, not the person: they must not count as activity,
# or a page left open would never expire. A test keeps this in step with config/urls.py.
USAGE_BEACON_PATH = "/u/"
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


def is_background_request(request):
    """An HTMX or script request (Option B OD-B3): it must never be answered with a page."""
    return (
        request.headers.get("HX-Request") == "true"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def signed_out_reply(reason):
    """401 for a background request from a signed-out session (Option B §4.7, finding F-1).

    XHR and fetch follow a redirect silently, so the sign-in page would arrive with status 200 and a
    script could read it as a successful save. `reason` is "idle", "limit" or None (no expiry seen).
    """
    response = JsonResponse({"error": "signed-out", "expired": reason}, status=401)
    patch_cache_control(response, no_store=True)
    return response


def _redirects_to_login(response):
    if response.status_code not in (301, 302, 303, 307, 308) or "Location" not in response:
        return False
    return urlsplit(response["Location"]).path == resolve_url(settings.LOGIN_URL)


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


def _is_passive(request):
    """Requests that check on the session without being activity by the person."""
    if request.path_info == SESSION_STATUS_PATH and request.method == "GET":
        return True
    return request.path_info == USAGE_BEACON_PATH and request.method == "POST"


def _record_expiry(request, area, reason):
    """Session-expiry signals (ADR 0027): counts by the requested route's surface, no person.

    Runs after logout(), so the expiry marker lands in the new anonymous session. Measurement
    failures are swallowed by usage.record().
    """
    if not usage.active(request):
        return
    usage.mark_expired(request)
    if area is None:
        return
    usage.record(request, area=area, workflow="session", step=f"expired_{reason}")
    # A beacon or a Stay-signed-in POST carries no change by the person, so nothing was lost.
    background_check = request.path_info in (USAGE_BEACON_PATH, SESSION_STATUS_PATH)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not background_check:
        usage.record(request, area=area, workflow="session", step="expired_unsaved")


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
            reason = None
            if now - started > settings.SESSION_ABSOLUTE_SECONDS:
                reason = "limit"
            elif now - seen > settings.SESSION_IDLE_SECONDS:
                reason = "idle"
            if reason:
                area = usage.area_of_route(user, request.path_info)
                logout(request)
                _record_expiry(request, area, reason)
                if is_background_request(request):
                    return signed_out_reply(reason)
                return expired_redirect(request, reason)
            request.session[STARTED_KEY] = started
            if not _is_passive(request):
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
        response = self.get_response(request)
        # Signed out without an expiry (another tab, cleared cookie): a guarded view sends the
        # browser to sign in. A background request gets 401 instead (Option B §4.7, part 2).
        if is_background_request(request) and _redirects_to_login(response):
            return signed_out_reply(None)
        return response

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
