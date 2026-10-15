"""Phase 7 Gate 3: announcements (ADR 0015).

Spec: docs/superpowers/specs/2026-10-15-phase7-gate3-announcements-design.md.
Saving publishes; a published notice never changes and is withdrawn, not
deleted. Guardians with portal access to a student in the audience read it in
the portal; preparing WhatsApp messages is a separate administrator step.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Announcement

TEMPLATE_KEY = "announcement"
WITHDRAWN_REASON = "Announcement withdrawn"


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
    return locked
