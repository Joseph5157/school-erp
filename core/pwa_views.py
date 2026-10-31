"""Installable web app (docs/PWA_GATE_1_PLAN.md): public manifest and the install help page.

Online-only: there is deliberately no service worker, offline page or client-side storage.
The manifest holds public install metadata only (no user, role, student or host name) and every
path in it is origin-relative, so one build serves staging and production.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

APP_NAME = "School ERP"
# Cobalt is the design system's info blue (--erp-info in static/css/erp.css); the bar is the white topbar.
ICON_COLOUR = "#1d5fa8"
THEME_COLOR = "#ffffff"
BACKGROUND_COLOR = "#f5f6f3"  # --erp-paper


def _icon(name, sizes, purpose):
    return {"src": static(f"pwa/{name}"), "sizes": sizes, "type": "image/png", "purpose": purpose}


@require_safe
@cache_control(public=True, max_age=3600)
def manifest(request):
    """Web app manifest. Public: AccountSecurityMiddleware lets this exact path through."""
    return JsonResponse(
        {
            "id": "/",
            "name": APP_NAME,
            "short_name": APP_NAME,
            "description": "School ERP for staff, teachers and guardians. Needs an internet connection.",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "theme_color": THEME_COLOR,
            "background_color": BACKGROUND_COLOR,
            "icons": [
                _icon("icon-192.png", "192x192", "any"),
                _icon("icon-512.png", "512x512", "any"),
                _icon("icon-maskable-512.png", "512x512", "maskable"),
            ],
        },
        content_type="application/manifest+json",
    )


@login_required
def install_help(request):
    """How to install the app on this device. Plain instructions; the button is script-enhanced."""
    return render(request, "pwa/install.html", {"app_name": APP_NAME})
