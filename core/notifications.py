"""Phase 7 notifications: consent, outbox and ASSIST sending (ADR 0015).

Every rule lives here: consent is checked when a message is enqueued, when
the To send page loads and when a message is marked sent; parameters are
limited to NOTIFICATION_PARAMETERS; nothing here makes a network call.

Security Gate 3B: a prepared message is only a promise made at prepare time. The To send
page and "mark sent" each check again that the guardian can still open the portal for the
child (active grant, active login, unrevoked account link, no pending review) or, for a
notice, for a child in its audience. Marking sent decides from current data under the row
lock and never trusts what the page displayed.
"""

from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.imports import normalize_phone
from core.models import (
    NOTIFICATION_PARAMETERS,
    Announcement,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    School,
)

WHATSAPP = GuardianContactConsent.Channel.WHATSAPP
OPTED_IN = GuardianContactConsent.Status.OPTED_IN
PREPARED = Notification.Status.PREPARED
SKIPPED = Notification.Status.SKIPPED_NO_CONSENT
NO_ACCESS_REASON = "Guardian no longer has portal access"
_NOTICE_KEY_MARKER = ":-:announcement-"


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
        raise NotificationError("Only WhatsApp sent by office staff is available.")
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


def opted_in_count(guardian_ids):
    """How many of these guardians are currently opted in to WhatsApp."""
    return len(_opted_in_ids(set(guardian_ids)))


def _notice_pk(notification):
    """The announcement a message belongs to, read from its idempotency key, or None."""
    if notification.type != Notification.Type.ANNOUNCEMENT:
        return None
    tail = notification.idempotency_key.rpartition(_NOTICE_KEY_MARKER)[2]
    return int(tail) if tail.isdigit() else None


def _portal_ok_ids(rows):
    """Primary keys of these messages whose guardian can still open the portal for them.

    A message about a child needs a current, non-pending grant for that guardian and child.
    A notice message needs a live notice and a grant for that guardian to a child in its
    audience. Anything that cannot be tied to either is treated as not eligible.
    """
    from core import announcements, notification_producers  # both import this module

    rows = list(rows)
    reachable = {}
    student_ids = {row.student_id for row in rows if row.student_id}
    if student_ids:
        for grant in notification_producers.portal_grants_for_students(student_ids):
            link = grant.student_guardian
            reachable.setdefault(link.student_id, set()).add(link.guardian_id)
    notice_pks = {
        pk for row in rows if not row.student_id and (pk := _notice_pk(row)) is not None
    }
    live_notices = (
        [n for n in Announcement.objects.filter(pk__in=notice_pks) if not n.is_withdrawn]
        if notice_pks else []
    )
    audience = announcements.audience_guardian_ids(live_notices)  # fixed query count
    ok = set()
    for row in rows:
        if row.student_id:
            if row.guardian_id in reachable.get(row.student_id, ()):
                ok.add(row.pk)
            continue
        notice_pk = _notice_pk(row)
        if notice_pk is not None and row.guardian_id in audience.get(notice_pk, ()):
            ok.add(row.pk)
    return ok


def _dismiss_no_access(pks):
    """System dismissal of waiting messages whose guardian lost portal access."""
    now = timezone.now()
    Notification.objects.filter(pk__in=pks, status=PREPARED).update(
        status=Notification.Status.DISMISSED, dismissed_at=now,
        dismiss_reason=NO_ACCESS_REASON, updated_at=now,
    )


def to_send():
    """PREPARED messages, oldest first, after dropping any whose guardian no longer
    has current consent (skipped) or portal access (dismissed by the system)."""
    snapshot = list(Notification.objects.filter(status=PREPARED))
    allowed = _opted_in_ids({row.guardian_id for row in snapshot})
    blocked = [row.pk for row in snapshot if row.guardian_id not in allowed]
    if blocked:
        Notification.objects.filter(pk__in=blocked, status=PREPARED).update(
            status=SKIPPED, updated_at=timezone.now()
        )
    consented = [row for row in snapshot if row.guardian_id in allowed]
    reachable = _portal_ok_ids(consented)
    no_access = [row.pk for row in consented if row.pk not in reachable]
    if no_access:
        _dismiss_no_access(no_access)
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


def _refuse_if_ineligible(locked):
    """Apply the consent and portal-access rules to a locked PREPARED message.

    Returns the message after recording the refusal (SKIPPED for no consent, DISMISSED for
    lost portal access), or None when it is still eligible. Consent is checked first.
    """
    if not is_opted_in(locked.guardian):
        locked.status = SKIPPED
        locked.save(update_fields=["status", "updated_at"])
        return locked
    if locked.pk not in _portal_ok_ids([locked]):
        _dismiss_no_access([locked.pk])
        return Notification.objects.get(pk=locked.pk)
    return None


def can_open_whatsapp(notification):
    """Whether the guardian has a phone number the WhatsApp link can use (no URL is built)."""
    return bool(normalize_phone(notification.guardian.phone))


def open_whatsapp(notification):
    """Recheck, then give the WhatsApp URL for one waiting message. Returns (message, url).

    This is the only place the URL is handed out: the To send page never renders it, so a
    page opened while the message was eligible cannot be used to send it afterwards. When
    consent or portal access has gone, the refusal is recorded (SKIPPED or DISMISSED) and
    url is None; the caller must not redirect to WhatsApp.
    """
    with transaction.atomic():
        locked = _locked_prepared(notification)
        refused = _refuse_if_ineligible(locked)
        if refused is not None:
            return refused, None
        link = whatsapp_link(locked)
        if link is None:
            raise NotificationError("This guardian's phone number is missing or not usable.")
        return locked, link


def mark_sent(notification, *, user):
    """Record a message as sent, or record why it was not.

    Authoritative for recording the SENT state, not for preventing the manual send: it
    decides from current data under the row lock, whatever the To send page showed (no
    consent gives SKIPPED, lost portal access gives DISMISSED, otherwise SENT). Staff send
    from their own WhatsApp after open_whatsapp() has handed out the link, so a message
    can still be sent in the gap between that redirect and this call. That gap cannot be
    closed in ASSIST mode (nothing here sends or sees the message); it is documented in
    docs/OPERATIONS.md.
    """
    with transaction.atomic():
        locked = _locked_prepared(notification)
        refused = _refuse_if_ineligible(locked)
        if refused is not None:
            return refused
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
