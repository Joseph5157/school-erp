"""Per-request account security (ADR 0013, Phase 6).

Placed immediately after Django's AuthenticationMiddleware. Resolving
`request.user` makes Django verify the session hash on every request, which
includes `User.session_version`, so a bumped version or an inactive login is
signed out at once. A login that must change its password reaches only the
password-change page, sign-out, static files and error responses.
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

ALLOWED_WHILE_CHANGE_REQUIRED = {"password_change", "logout"}


class AccountSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and getattr(user, "must_change_password", False):
            if not self._allowed(request.path_info):
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
