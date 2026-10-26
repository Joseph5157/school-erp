"""Overview cards for the admin landing page (F04). Read-only; no HTTP here.

Each card reuses the data source of the list page it links to, so the
count and the destination cannot disagree. A card is omitted when the user
lacks the permission the destination page requires.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, Min, Q
from django.urls import reverse

from core import guardian_access, nav_badges, reports
from core import models as core_models
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicEnrollment,
    Applicant,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    ClassGrade,
    GuardianAccount,
    Student,
)


def _card(key, title, count, summary, url, detail=""):
    return {
        "key": key,
        "title": title,
        "count": count,
        "summary": summary,
        "url": url,
        "detail": detail,
        "tone": "attention" if count else "clear",
    }


def _attendance(today):
    """Same authority as the Missing attendance report, for today only.

    Skips non-instructional dates and treats a DRAFT register as still missing.
    """
    missing = reports.missing_attendance(today, today)
    sections = {row["section"].pk for row in missing}
    detail = ""
    if not missing and not reports.expected_registers(today, today) and (
        AcademicEnrollment.objects.effective_on(today).exists()
    ):
        detail = "No school day today."
    return _card(
        "attendance", "Attendance today", len(sections),
        "Sections whose register is not yet submitted today.",
        reverse("core:report-missing-attendance")
        + f"?start={today:%Y-%m-%d}&end={today:%Y-%m-%d}",
        detail,
    )


def _applicants(today):
    pending = Applicant.objects.filter(admission_status=Applicant.AdmissionStatus.PENDING)
    oldest = pending.aggregate(oldest=Min("created_at"))["oldest"]
    detail = f"Oldest waiting since {oldest:%d %b %Y}." if oldest else ""
    return _card(
        "applicants", "Applicants awaiting decision", pending.count(),
        "Accept or reject pending applications.",
        reverse("core:applicant-list") + "?status=PENDING", detail,
    )


def _publications(today):
    return _card(
        "publications", "Results to publish", nav_badges.stale_publication_count(),
        "Published results that are out of date.",
        reverse("core:publications-stale"),
    )


def _access_reviews(today):
    return _card(
        "access_reviews", "Pending access reviews",
        len(guardian_access.pending_reviews(today)),
        "Guardian access that needs an explicit decision.",
        reverse("core:guardian-access-reviews"),
    )


def _notifications(today):
    return _card(
        "notifications", "Messages to send", nav_badges.prepared_notification_count(),
        "Prepared messages waiting to be sent.",
        reverse("core:notifications-to-send"),
        "May include messages that will be skipped for missing consent.",
    )


def _lockouts(today):
    return _card(
        "lockouts", "Sign-in lockouts", nav_badges.locked_username_count(),
        "Usernames locked after failed sign-ins.",
        reverse("core:login-lockouts"),
    )


# (builder, permission required by the destination page)
_CARDS = (
    (_attendance, "core.view_attendanceregister"),
    (_applicants, "core.view_applicant"),
    (_publications, "core.view_termpublication"),
    (_access_reviews, "core.view_guardianaccessreview"),
    (_notifications, "core.send_notification"),
    (_lockouts, "accounts.clear_login_lockout"),
)


def split_cards(cards):
    """(attention, clear): cards with something waiting first-class, zero cards for a compact row.

    Each group keeps the order of `_CARDS`.
    """
    return [c for c in cards if c["count"]], [c for c in cards if not c["count"]]


def overview_cards(user):
    today = core_models.business_today()  # looked up late so tests can pin it
    return [build(today) for build, perm in _CARDS if user.has_perm(perm)]


def _glance_card(key, title, count, summary, url, user, perm):
    # The headline figure is shown to every administrator; only the link needs the permission.
    return {
        "key": key, "title": title, "count": count, "summary": summary,
        "url": url if user.has_perm(perm) else "", "detail": "", "tone": "glance",
    }


def glance_cards(user):
    """School-at-a-glance headline figures (read-only; a handful of aggregate queries)."""
    today = core_models.business_today()
    teachers = (
        get_user_model().objects.filter(groups__name=TEACHERS_GROUP_NAME, is_active=True).count()
    )
    taken = AttendanceEntry.objects.filter(
        register__date=today, register__status=AttendanceRegister.Status.SUBMITTED
    ).aggregate(
        total=Count("pk"), present=Count("pk", filter=Q(status=AttendanceStatus.PRESENT)),
    )
    attendance = f"{round(100 * taken['present'] / taken['total'])}%" if taken["total"] else "-"
    return [
        _glance_card(
            "students", "Active students",
            Student.objects.filter(status=Student.Status.ACTIVE).count(),
            "Students currently enrolled with the school.",
            reverse("core:student-list"), user, "core.view_student",
        ),
        _glance_card(
            "teachers", "Teachers", teachers, "Active teacher logins.",
            reverse("core:teacher-list"), user, "accounts.manage_teacher_accounts",
        ),
        _glance_card(
            "classes", "Classes", ClassGrade.objects.count(), "Classes set up for the school.",
            reverse("core:class-grade-list"), user, "core.view_classgrade",
        ),
        _glance_card(
            "guardians", "Guardians with portal access",
            GuardianAccount.objects.filter(revoked_at__isnull=True).count(),
            "Guardians who can sign in to the portal.",
            reverse("core:guardian-list"), user, "core.view_guardian",
        ),
        _glance_card(
            "attendance", "Attendance today", attendance,
            "present across registers submitted today." if taken["total"]
            else "No register submitted today.",
            reverse("core:attendance-register-list"), user, "core.view_attendanceregister",
        ),
    ]
