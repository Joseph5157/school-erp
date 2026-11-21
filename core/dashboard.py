"""Overview cards for the admin landing page (F04). Read-only; no HTTP here.

Each card reuses the data source of the list page it links to, so the
count and the destination cannot disagree. A card is omitted when the user
lacks the permission the destination page requires.
"""

from django.contrib.auth import get_user_model
from django.db.models import Min
from django.urls import reverse

from core import analytics, nav_badges
from core import models as core_models
from core.models import (
    TEACHERS_GROUP_NAME,
    Applicant,
    ClassGrade,
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


def _applicants(today, user):
    pending = Applicant.objects.filter(admission_status=Applicant.AdmissionStatus.PENDING)
    oldest = pending.aggregate(oldest=Min("created_at"))["oldest"]
    detail = f"Oldest waiting since {oldest:%d %b %Y}." if oldest else ""
    return _card(
        "applicants", "Applicants awaiting decision", pending.count(),
        "Accept or reject pending applications.",
        reverse("core:applicant-list") + "?status=PENDING", detail,
    )


def _publications(today, user):
    return _card(
        "publications", "Results to publish", nav_badges.cached_count(user, "core:publications-stale"),
        "Published results that are out of date.",
        reverse("core:publications-stale"),
    )


def _notifications(today, user):
    return _card(
        "notifications", "Messages to send", nav_badges.cached_count(user, "core:notifications-to-send"),
        "Prepared messages waiting to be sent.",
        reverse("core:notifications-to-send"),
        "May include messages that will be skipped for missing consent.",
    )


def _lockouts(today, user):
    return _card(
        "lockouts", "Sign-in lockouts", nav_badges.cached_count(user, "core:login-lockouts"),
        "Usernames locked after failed sign-ins.",
        reverse("core:login-lockouts"),
    )


# (builder, permission required by the destination page)
_CARDS = (
    (_applicants, "core.view_applicant"),
    (_publications, "core.view_termpublication"),
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
    return [build(today, user) for build, perm in _CARDS if user.has_perm(perm)]


def _glance_card(key, title, count, summary, url, user, perm):
    # The headline figure is shown to every administrator; only the link needs the permission.
    return {
        "key": key, "title": title, "count": count, "summary": summary,
        "url": url if user.has_perm(perm) else "", "detail": "", "tone": "glance",
    }


def glance_cards(user, today=None):
    """School-at-a-glance headline figures (read-only; a handful of aggregate queries)."""
    today = core_models.business_today() if today is None else today
    teachers = (
        get_user_model().objects.filter(groups__name=TEACHERS_GROUP_NAME, is_active=True).count()
    )
    term = analytics.current_term(today)
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
            "classes", "Classes", ClassGrade.objects.active().count(), "Classes set up for the school.",
            reverse("core:class-grade-list"), user, "core.view_classgrade",
        ),
        _glance_card(
            "term", "Current term", term.name if term else "-",
            "Running today." if term else "No term is running today.",
            reverse("core:academic-year-list"), user, "core.view_academicyear",
        ),
    ]
