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


def can_write_term_remarks(user, term, section):
    """Administrators, or a teacher assigned to any Subject in this Section that year."""
    if not (user and user.is_authenticated and user.is_active):
        return False
    if user.has_perm("core.change_termremark"):
        return True
    return (
        teacher_assignments(user)
        .filter(offering__academic_year_id=term.academic_year_id, section=section)
        .exists()
    )


# --- Phase 5: class teacher scope (ADR 0011, ADR 0012) ----------------------


def class_teacher_assignments(user, on_date=None):
    """SectionClassTeacher rows that currently grant `user` class teacher rights.

    Empty unless the user is an active Teachers-group login (ADR 0011 D14):
    losing teacher status removes access without touching the rows. With
    `on_date`, only assignments effective on that date.
    """
    from core.models import SectionClassTeacher

    if not is_teacher(user):
        return SectionClassTeacher.objects.none()
    rows = SectionClassTeacher.objects.filter(teacher=user)
    if on_date is not None:
        rows = rows.effective_on(on_date)
    return rows


def class_teacher_on(user, section, on_date):
    """Is `user` the class teacher of `section` on `on_date`?"""
    return class_teacher_assignments(user, on_date).filter(section=section).exists()


def class_teacher_sections(user, on_date):
    """Sections of which `user` is class teacher on `on_date`."""
    from core.models import Section

    return Section.objects.filter(
        pk__in=class_teacher_assignments(user, on_date).values("section_id")
    ).select_related("class_grade")


def can_take_attendance(user, section, on_date):
    """May a teacher take or submit `section`'s register for `on_date`? (ADR 0012)

    Only the class teacher effective on that date, and only for the
    school-local business date (D5). Whether the date is instructional is
    enforced by the register itself. Administrators use the Phase 2
    administrator workflow and permissions instead.
    """
    from core import models

    if on_date != models.business_today():
        return False
    return class_teacher_on(user, section, on_date)
