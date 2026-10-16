"""Overview cards for the admin landing page (F04). Read-only; no HTTP here.

Each card reuses the data source of the list page it links to, so the
count and the destination cannot disagree. A card is omitted when the user
lacks the permission the destination page requires.
"""

from django.db.models import Min
from django.urls import reverse

from core import guardian_access, publication
from core import models as core_models
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    AttendanceRegister,
    Section,
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
    expected = (
        AcademicEnrollment.objects.effective_on(today)
        .values_list("section_id", flat=True)
        .distinct()
    )
    taken = AttendanceRegister.objects.filter(date=today).values_list("section_id", flat=True)
    missing = Section.objects.filter(pk__in=expected).exclude(pk__in=taken).count()
    return _card(
        "attendance", "Attendance today", missing,
        "Sections with no register opened today.",
        reverse("core:attendance-register-list"),
    )


def _applicants(today):
    pending = Applicant.objects.filter(admission_status=Applicant.AdmissionStatus.PENDING)
    oldest = pending.aggregate(oldest=Min("created_at"))["oldest"]
    detail = f"Oldest waiting since {oldest:%d %b %Y}." if oldest else ""
    return _card(
        "applicants", "Applicants awaiting decision", pending.count(),
        "Accept or reject pending applications.",
        reverse("core:applicant-list"), detail,
    )


def _publications(today):
    return _card(
        "publications", "Results to publish", publication.stale_publications().count(),
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


# (builder, permission required by the destination page)
_CARDS = (
    (_attendance, "core.view_attendanceregister"),
    (_applicants, "core.view_applicant"),
    (_publications, "core.view_termpublication"),
    (_access_reviews, "core.view_guardianaccessreview"),
)


def overview_cards(user):
    today = core_models.business_today()  # looked up late so tests can pin it
    return [build(today) for build, perm in _CARDS if user.has_perm(perm)]


def needs_setup():
    """True until the school has an Academic Year and at least one Section."""
    return not (AcademicYear.objects.exists() and Section.objects.exists())
