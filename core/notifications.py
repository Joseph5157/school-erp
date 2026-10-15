"""Phase 7 notifications: consent, outbox and ASSIST sending (ADR 0015).

Every rule lives here: consent is checked when a message is enqueued, when
the To send page loads and when a message is marked sent; parameters are
limited to NOTIFICATION_PARAMETERS; nothing here makes a network call.
"""

from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.imports import normalize_phone
from core.models import (
    NOTIFICATION_PARAMETERS,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    School,
)

WHATSAPP = GuardianContactConsent.Channel.WHATSAPP
OPTED_IN = GuardianContactConsent.Status.OPTED_IN
PREPARED = Notification.Status.PREPARED
SKIPPED = Notification.Status.SKIPPED_NO_CONSENT


class NotificationError(Exception):
    """An action that cannot be done; the message is safe to show to staff."""


def current_consent(guardian, channel=WHATSAPP):
    return (
        guardian.contact_consents.filter(channel=channel).order_by("-recorded_at", "-pk").first()
    )


def is_opted_in(guardian, channel=WHATSAPP):
    consent = current_consent(guardian, channel)
    return consent is not None and consent.status == OPTED_IN


def record_consent(*, guardian, status, source, note="", user):
    return GuardianContactConsent.objects.create(
        guardian=guardian, channel=WHATSAPP, status=status, source=source,
        note=(note or "").strip()[:200], recorded_by=user,
    )


def school_mode():
    school = School.objects.first()
    return school.notification_channel if school else School.NotificationMode.PORTAL_ONLY


def enqueue(*, guardian, student, type, template_key, parameters, subject):
    """Prepare one message, or return the existing one for the same key.

    Returns None when the school sends nothing (PORTAL_ONLY).
    """
    if set(parameters) - set(NOTIFICATION_PARAMETERS):
        raise NotificationError(
            "Messages may only contain: " + ", ".join(NOTIFICATION_PARAMETERS) + "."
        )
    mode = school_mode()
    if mode == School.NotificationMode.PORTAL_ONLY:
        return None
    if mode != School.NotificationMode.ASSIST:
        raise NotificationError("Only WhatsApp sent by office staff (ASSIST) is available.")
    template = (
        NotificationTemplate.objects.filter(
            key=template_key, channel=WHATSAPP, language="en", approved=True
        )
        .order_by("-version")
        .first()
    )
    if template is None:
        raise NotificationError(f'There is no approved "{template_key}" message text.')
    key = f"{type}:{guardian.pk}:{student.pk if student else '-'}:{subject}"
    existing = Notification.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Notification.objects.create(
                guardian=guardian, student=student, type=type, template=template,
                parameters=dict(parameters), channel_mode=mode,
                status=PREPARED if is_opted_in(guardian) else SKIPPED,
                idempotency_key=key,
            )
    except IntegrityError:
        return Notification.objects.get(idempotency_key=key)


def render(notification):
    values = dict.fromkeys(NOTIFICATION_PARAMETERS, "")
    values.update(notification.parameters)
    return notification.template.body.format_map(values)


def whatsapp_link(notification):
    phone = normalize_phone(notification.guardian.phone)
    if not phone:
        return None
    return f"https://wa.me/{phone.lstrip('+')}?text={quote(render(notification), safe='')}"


def _opted_in_ids(guardian_ids):
    latest = {}
    for guardian_id, status in (
        GuardianContactConsent.objects.filter(guardian_id__in=guardian_ids, channel=WHATSAPP)
        .order_by("guardian_id", "recorded_at", "pk")
        .values_list("guardian_id", "status")
    ):
        latest[guardian_id] = status
    return {guardian_id for guardian_id, status in latest.items() if status == OPTED_IN}


def to_send():
    """PREPARED messages, oldest first, after skipping any without current consent."""
    pending = Notification.objects.filter(status=PREPARED)
    allowed = _opted_in_ids(set(pending.values_list("guardian_id", flat=True)))
    pending.exclude(guardian_id__in=allowed).update(status=SKIPPED, updated_at=timezone.now())
    return (
        Notification.objects.filter(status=PREPARED)
        .select_related("guardian", "student", "template")
        .order_by("created_at", "pk")
    )


def _locked_prepared(notification):
    locked = Notification.objects.select_for_update().get(pk=notification.pk)
    if locked.status != PREPARED:
        raise NotificationError("This message is no longer waiting to be sent.")
    return locked


def mark_sent(notification, *, user):
    with transaction.atomic():
        locked = _locked_prepared(notification)
        if not is_opted_in(locked.guardian):
            locked.status = SKIPPED
            locked.save(update_fields=["status", "updated_at"])
            return locked
        locked.status = Notification.Status.SENT
        locked.marked_sent_by = user
        locked.marked_sent_at = timezone.now()
        locked.save(update_fields=["status", "marked_sent_by", "marked_sent_at", "updated_at"])
        return locked


def dismiss(notification, *, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise NotificationError("Give a reason for not sending this message.")
    with transaction.atomic():
        locked = _locked_prepared(notification)
        locked.status = Notification.Status.DISMISSED
        locked.dismissed_by = user
        locked.dismissed_at = timezone.now()
        locked.dismiss_reason = reason[:200]
        locked.save(update_fields=[
            "status", "dismissed_by", "dismissed_at", "dismiss_reason", "updated_at",
        ])
        return locked
