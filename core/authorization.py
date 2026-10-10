"""Centralized authorization: administrative permissions and Phase 4 teacher scope.

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


# --- Phase 4: assessment-scoped teacher authorization (ADR 0010) -----------


def is_teacher(user):
    """An authenticated, active login in the Teachers group."""
    from core.models import TEACHERS_GROUP_NAME

    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.groups.filter(name=TEACHERS_GROUP_NAME).exists()
    )


def teacher_assignments(user):
    """The AssessmentTeacherAssignments a user may enter results for."""
    from core.models import AssessmentTeacherAssignment

    if not is_teacher(user):
        return AssessmentTeacherAssignment.objects.none()
    return AssessmentTeacherAssignment.objects.filter(teacher=user).select_related(
        "offering__academic_year", "offering__class_grade", "offering__subject", "section"
    )


def can_enter_results(user, offering, section):
    """May `user` enter DRAFT results for this Subject offering and Section?

    True only for an active member of the Teachers group who is the assigned
    teacher for exactly this offering and Section. Administrator powers
    (configuration, finalization, corrections) are separate permissions and
    do not make someone a result-entering teacher.
    """
    return teacher_assignments(user).filter(offering=offering, section=section).exists()


def teacher_required(view_func):
    """Require an authenticated, active member of the Teachers group.

    Anonymous users are redirected to login; other users get 403. Views still
    check the specific assignment with `can_enter_results` (ADR 0010).
    """
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_teacher(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(wrapped)
