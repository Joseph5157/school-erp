"""Centralized Phase 1 administrative authorization.

Per docs/adr/0004-phase-1-authorization-foundation.md, authorization logic
must be centralized and reusable rather than reimplemented per view. Every
Phase 1 administrative view in this project applies `administrator_required`
instead of checking authentication/permissions independently.
"""

from django.contrib.auth.decorators import login_required, permission_required


def administrator_required(perm):
    """Require authentication and a specific Django permission.

    - Anonymous users are redirected to `settings.LOGIN_URL`.
    - Authenticated users lacking `perm` receive a 403 (PermissionDenied).
    - Superusers automatically satisfy any permission check (Django's
      default `User.has_perm` behavior) with no special-casing here.
    """

    def decorator(view_func):
        return login_required(permission_required(perm, raise_exception=True)(view_func))

    return decorator
