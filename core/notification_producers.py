"""Phase 7 Gates 2 and 4: absence alerts and report-card notices (ADR 0015).

Spec: docs/superpowers/specs/2026-10-15-phase7-gate2-4-alerts-design.md.
Recipients are guardians who can open the portal for the student right now.
Producers never block the action that triggers them: a message that cannot
be prepared is logged (ids only) and skipped.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.urls import reverse

from core import guardian_access, notifications
from core import models as core_models
from core.models import (
    AttendanceStatus,
    GuardianAccount,
    GuardianStudentAccess,
    Notification,
    School,
)

logger = logging.getLogger(__name__)

ABSENCE_TEMPLATE = "absence-alert"
REPORT_CARD_TEMPLATE = "report-card-published"
CORRECTED_REASON = "Attendance corrected to Present"


def _assist():
    return notifications.school_mode() == School.NotificationMode.ASSIST


def portal_grants(student):
    """Active, non-pending grants whose guardian has an active portal login."""
    active_login = GuardianAccount.objects.filter(
        guardian=OuterRef("student_guardian__guardian"),
        revoked_at__isnull=True, user__is_active=True,
    )
    grants = list(
        GuardianStudentAccess.objects.filter(
            student_guardian__student=student, revoked_at__isnull=True
        )
        .filter(Exists(active_login))
        .select_related("student_guardian__guardian", "student_guardian__student")
        .order_by("pk")
    )
    pending = guardian_access.pending_map(grants)
    return [grant for grant in grants if not pending[grant.pk][0]]


def portal_url(url_name, grant):
    if not settings.PORTAL_BASE_URL:
        raise notifications.NotificationError("The portal address is not set.")
    return settings.PORTAL_BASE_URL + reverse(url_name, args=[grant.public_id])


def first_name(student):
    words = (student.full_name or "").split()
    return words[0] if words else ""


def _display_date(on_date):
    return f"{on_date.day} {on_date:%b %Y}"


def _prepare(*, kind, template_key, grant, student, subject, url_name, extra=None):
    guardian = grant.student_guardian.guardian
    try:
        parameters = {"first_name": first_name(student),
                      "portal_url": portal_url(url_name, grant), **(extra or {})}
        with transaction.atomic():
            notifications.enqueue(
                guardian=guardian, student=student, type=kind, template_key=template_key,
                parameters=parameters, subject=subject,
            )
    except notifications.NotificationError as problem:
        logger.warning("%s message not prepared (student %s, guardian %s): %s",
                       kind, student.pk, guardian.pk, problem)


def _absence_alert(student, on_date):
    for grant in portal_grants(student):
        _prepare(kind=Notification.Type.ABSENCE, template_key=ABSENCE_TEMPLATE, grant=grant,
                 student=student, subject=on_date.isoformat(), url_name="portal:attendance",
                 extra={"date": _display_date(on_date)})


def absence_alerts_for_register(register):
    """Called inside AttendanceRegister.submit(): one alert per absent student."""
    on_date = core_models._as_date(register.date)
    if not _assist() or on_date != core_models.business_today():
        return
    entries = register.entries.filter(status=AttendanceStatus.ABSENT).select_related(
        "academic_enrollment__student"
    )
    for entry in entries:
        _absence_alert(entry.academic_enrollment.student, on_date)


def absence_corrected(entry, *, actor):
    """Called inside AttendanceEntry.record_status_change() after the new status is saved.

    To Present: waiting absence alerts for that student and date are dismissed
    (sent ones are never retracted). To Absent: an alert, same day only.
    """
    register = entry.register
    student = entry.academic_enrollment.student
    on_date = core_models._as_date(register.date)
    if entry.status == AttendanceStatus.PRESENT:
        waiting = Notification.objects.filter(
            type=Notification.Type.ABSENCE, student=student,
            status=Notification.Status.PREPARED,
            idempotency_key__endswith=f":{student.pk}:{on_date.isoformat()}",
        )
        for notification in waiting:
            try:
                notifications.dismiss(notification, user=actor, reason=CORRECTED_REASON)
            except notifications.NotificationError:
                pass  # sent or dismissed meanwhile; nothing to retract
    elif _assist() and on_date == core_models.business_today():
        _absence_alert(student, on_date)


def report_card_notices(publications):
    """Called inside confirm_publication(): one notice per student, once per Term."""
    if not _assist():
        return
    for publication in publications:
        student = publication.student
        for grant in portal_grants(student):
            _prepare(kind=Notification.Type.RESULT_PUBLISHED,
                     template_key=REPORT_CARD_TEMPLATE, grant=grant, student=student,
                     subject=f"term-{publication.term_id}", url_name="portal:report-cards")
