"""Where to send someone back to after an interrupted request (audit 18 ERR-01/ERR-02).

A GET returns to itself, query string included. A POST may go to an action-only URL (require_POST)
that answers a GET with 405, so it returns to the same-origin page that showed the form (Referer),
falling back to the posted path, which for most forms is that same page. Never another site.
"""

from urllib.parse import urlsplit

from django.utils.http import url_has_allowed_host_and_scheme


def return_path(request, fallback):
    if request.method in ("GET", "HEAD"):
        candidate = request.get_full_path()
    else:
        referer = request.META.get("HTTP_REFERER", "")
        if referer and url_has_allowed_host_and_scheme(
            referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            parts = urlsplit(referer)
            candidate = parts.path + (f"?{parts.query}" if parts.query else "")
        else:
            candidate = request.path
    if not candidate.startswith("/") or candidate.startswith(("//", "/\\")):
        return fallback
    return candidate
