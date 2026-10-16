"""Phase 7 Gate 3: announcements (ADR 0015).

Spec: docs/superpowers/specs/2026-10-15-phase7-gate3-announcements-design.md.
Saving publishes; a published notice never changes and is withdrawn, not
deleted. Guardians with portal access to a student in the audience read it in
the portal; preparing WhatsApp messages is a separate administrator step.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from core import models as core_models
from core import notification_producers, notifications
from core.models import AcademicEnrollment, Announcement, Notification, School, Student
from core.portal import portal_children

TEMPLATE_KEY = "announcement"
WITHDRAWN_REASON = "Announcement withdrawn"

logger = logging.getLogger(__name__)


def publish(*, title, body, audience, class_grade=None, section=None, actor):
    announcement = Announcement(
        title=(title or "").strip(),
        body=(body or "").strip(),
        audience=audience,
        class_grade=class_grade if audience == Announcement.Audience.CLASS else None,
        section=section if audience == Announcement.Audience.SECTION else None,
        published_by=actor,
    )
    announcement.full_clean()
    announcement.save()
    return announcement


def withdraw(announcement, *, actor, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Give a reason for withdrawing this notice.")
    with transaction.atomic():
        locked = Announcement.objects.select_for_update().get(pk=announcement.pk)
        if locked.is_withdrawn:
            raise ValidationError("This notice has already been withdrawn.")
        locked.withdrawn_at = timezone.now()
        locked.withdrawn_by = actor
        locked.withdrawal_reason = reason[:200]
        locked.save(update_fields=["withdrawn_at", "withdrawn_by", "withdrawal_reason"])
        waiting = Notification.objects.filter(
            type=Notification.Type.ANNOUNCEMENT, status=Notification.Status.PREPARED,
            idempotency_key__endswith=f":-:announcement-{locked.pk}",
        )
        for message in waiting:
            try:
                notifications.dismiss(message, user=actor, reason=WITHDRAWN_REASON)
            except notifications.NotificationError:
                pass  # sent or dismissed meanwhile; nothing to retract
    return locked


def _current_enrollments(on_date):
    """Enrollments effective on the date and inside their academic year (an open-ended
    enrollment does not outlive its year, matching the portal review rule)."""
    return AcademicEnrollment.objects.effective_on(on_date).filter(
        academic_year__end_date__gte=on_date
    )


def _enrollments(announcement, on_date):
    enrollments = _current_enrollments(on_date)
    if announcement.audience == Announcement.Audience.CLASS:
        return enrollments.filter(class_grade_id=announcement.class_grade_id)
    if announcement.audience == Announcement.Audience.SECTION:
        return enrollments.filter(section_id=announcement.section_id)
    return enrollments


def audience_students(announcement, on_date=None):
    """Students in the audience: enrollment effective on the date (default today)."""
    on_date = on_date or core_models.business_today()
    return Student.objects.filter(
        pk__in=_enrollments(announcement, on_date).values("student_id")
    ).order_by("pk")


def recipient_grants(announcement):
    """One portal grant per guardian who can read this notice (lowest grant pk)."""
    student_ids = list(audience_students(announcement).values_list("pk", flat=True))
    chosen = {}
    for grant in notification_producers.portal_grants_for_students(student_ids):
        chosen.setdefault(grant.student_guardian.guardian_id, grant)
    return list(chosen.values())


def audience_counts(announcement):
    guardian_ids = [g.student_guardian.guardian_id for g in recipient_grants(announcement)]
    return {"guardians": len(guardian_ids),
            "opted_in": notifications.opted_in_count(guardian_ids)}


def preview_counts(*, audience, class_grade=None, section=None):
    """Recipient counts for a notice that is not saved yet (same rules as publish())."""
    draft = Announcement(
        audience=audience,
        class_grade=class_grade if audience == Announcement.Audience.CLASS else None,
        section=section if audience == Announcement.Audience.SECTION else None,
    )
    return audience_counts(draft)


def visible_announcements(user):
    """Live notices whose audience includes one of the user's visible children."""
    students = [item["student"] for item in portal_children(user) if item["visible"]]
    placements = list(
        _current_enrollments(core_models.business_today())
        .filter(student__in=students)
        .values_list("class_grade_id", "section_id")
    )
    if not placements:
        return []
    return list(
        Announcement.objects.filter(withdrawn_at__isnull=True)
        .filter(
            Q(audience=Announcement.Audience.ALL)
            | Q(audience=Announcement.Audience.CLASS,
                class_grade_id__in={grade for grade, _ in placements})
            | Q(audience=Announcement.Audience.SECTION,
                section_id__in={section for _, section in placements})
        )
        .order_by("-published_at", "-pk")
    )


def notice_url(announcement):
    if not settings.PORTAL_BASE_URL:
        raise ValidationError(
            "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."
        )
    return settings.PORTAL_BASE_URL + reverse("portal:notice", args=[announcement.public_id])


def prepare_messages(announcement):
    """One link-only message per guardian; repeating prepares nothing new.

    Counts describe the audience's messages: `prepared` are waiting on the To
    send page, `done` were already sent, delivered or dismissed, `skipped` had no
    WhatsApp consent, and `failed` could not be prepared (or are queued/failed).
    """
    with transaction.atomic():
        # Serialise with withdraw(): re-read the notice under a row lock.
        announcement = Announcement.objects.select_for_update().get(pk=announcement.pk)
        if announcement.is_withdrawn:
            raise ValidationError("This notice has been withdrawn.")
        if notifications.school_mode() != School.NotificationMode.ASSIST:
            raise ValidationError("WhatsApp sending is switched off for this school.")
        parameters = {"portal_url": notice_url(announcement)}
        result = {"prepared": 0, "done": 0, "skipped": 0, "failed": 0}
        for grant in recipient_grants(announcement):
            guardian = grant.student_guardian.guardian
            try:
                with transaction.atomic():
                    message = notifications.enqueue(
                        guardian=guardian, student=None, type=Notification.Type.ANNOUNCEMENT,
                        template_key=TEMPLATE_KEY, parameters=parameters,
                        subject=f"announcement-{announcement.pk}",
                    )
            except notifications.NotificationError as problem:
                logger.warning(
                    "ANNOUNCEMENT message not prepared (announcement %s, guardian %s): %s",
                    announcement.pk, guardian.pk, problem,
                )
                result["failed"] += 1
                continue
            status = message.status
            if status == Notification.Status.PREPARED:
                result["prepared"] += 1
            elif status in (Notification.Status.SENT, Notification.Status.DELIVERED,
                            Notification.Status.DISMISSED):
                result["done"] += 1
            elif status == Notification.Status.SKIPPED_NO_CONSENT:
                result["skipped"] += 1
            else:
                result["failed"] += 1
        return result
