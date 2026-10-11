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
    """Administrators, or the Section's class teacher for the Term (ADR 0012 D10).

    The class teacher is the one effective on the Term's end date, or on the
    business date while the Term is still running. Subject teacher
    assignments no longer grant remark writing (this replaced the Phase 4
    rule of ADR 0010).
    """
    if not (user and user.is_authenticated and user.is_active):
        return False
    if user.has_perm("core.change_termremark"):
        return True
    return class_teacher_on(user, section, term_remark_date(term))


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


def teacher_student_scope(user, on_date):
    """AcademicEnrollments effective on `on_date` that a teacher may look up.

    Per ADR 0012 D8/D9: enrollments in a Section where the user is class
    teacher on that date, or in a Section where the user holds a subject
    teacher assignment for that enrollment's Academic Year and Class/Grade.
    """
    from django.db.models import Q

    from core.models import AcademicEnrollment

    if not is_teacher(user):
        return AcademicEnrollment.objects.none()
    scope = Q(section_id__in=class_teacher_assignments(user, on_date).values("section_id"))
    for academic_year_id, class_grade_id, section_id in teacher_assignments(user).values_list(
        "offering__academic_year_id", "offering__class_grade_id", "section_id"
    ):
        scope |= Q(
            academic_year_id=academic_year_id,
            class_grade_id=class_grade_id,
            section_id=section_id,
        )
    return AcademicEnrollment.objects.effective_on(on_date).filter(scope)


def can_view_student_as_teacher(user, student, on_date):
    return teacher_student_scope(user, on_date).filter(student=student).exists()


def guardian_contact_visible(user, enrollment, on_date):
    """Guardian names and contacts: only the Student's class teacher (D8)."""
    return enrollment is not None and class_teacher_on(user, enrollment.section, on_date)


def term_remark_date(term):
    """The date whose class teacher owns a Term's remarks (ADR 0012 D10).

    The Term's end date once it has ended; while it is running, the business
    date; before it starts, its first day.
    """
    from core import models

    today = models.business_today()
    if today >= term.end_date:
        return term.end_date
    return max(today, term.start_date)


def term_remark_sections(user, term):
    """Sections whose remarks for `term` the teacher may write."""
    return class_teacher_sections(user, term_remark_date(term)).filter(
        class_teacher_assignments__academic_year_id=term.academic_year_id
    ).distinct()


def can_view_report_card_as_teacher(user, student, term):
    """Class teacher of the Student's Term placement Section (D8, D10)."""
    placement = term.enrollment_for(student)
    return placement is not None and class_teacher_on(
        user, placement.section, term_remark_date(term)
    )


# --- Phase 6: guardian scope (ADR 0013, ADR 0014) ----------------------------


def guardian_account(user):
    """The user's active GuardianAccount, or None.

    Requires an authenticated, active login. Administrator permissions never
    make someone a guardian.
    """
    from core.models import GuardianAccount

    if not (user and user.is_authenticated and user.is_active):
        return None
    return (
        GuardianAccount.objects.filter(user=user, revoked_at__isnull=True)
        .select_related("guardian")
        .first()
    )


def is_guardian(user):
    return guardian_account(user) is not None


def guardian_grants(user):
    """Active grants of the user's guardian (including ones under review)."""
    from core.models import GuardianStudentAccess

    account = guardian_account(user)
    if account is None:
        return GuardianStudentAccess.objects.none()
    return GuardianStudentAccess.objects.filter(
        student_guardian__guardian=account.guardian, revoked_at__isnull=True
    ).select_related("student_guardian__student", "student_guardian__guardian")


def guardian_visible_grant(user, public_id):
    """The grant behind a portal identifier, or None if the user may not see it.

    None when: not an active guardian, no active grant with that identifier
    for the user's guardian, or a date-based access review is pending (fails
    closed, OD-8). Portal views turn None into 404.
    """
    from django.core.exceptions import ValidationError

    from core.guardian_access import is_review_pending

    try:
        grant = guardian_grants(user).filter(public_id=public_id).first()
    except ValidationError:
        return None
    if grant is None or is_review_pending(grant):
        return None
    return grant


def guardian_can_view(user, student):
    """May this login see this Student in the Guardian Portal right now?"""
    from core.guardian_access import is_review_pending

    grant = guardian_grants(user).filter(student_guardian__student=student).first()
    return grant is not None and not is_review_pending(grant)
