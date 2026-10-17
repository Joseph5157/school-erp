"""Overview cards for the admin landing page (F04). Read-only; no HTTP here.

Each card reuses the data source of the list page it links to, so the
count and the destination cannot disagree. A card is omitted when the user
lacks the permission the destination page requires.
"""

from django.db.models import Min
from django.urls import reverse

from core import guardian_access, nav_badges, reports
from core import models as core_models
from core.models import (
    AcademicEnrollment,
    Applicant,
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


def overview_cards(user):
    today = core_models.business_today()  # looked up late so tests can pin it
    return [build(today) for build, perm in _CARDS if user.has_perm(perm)]
