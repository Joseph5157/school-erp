"""Guardian contact history for the reset rules (G-06 reset spec §4.3, OD-G13, OD-R3). Read-only."""
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from accounts.models import SecurityEvent

PHONE_WINDOW = timedelta(days=30)
Event = SecurityEvent.EventType


@dataclass(frozen=True)
class PhoneHistory:
    recent: bool
    changed_at: object = None  # latest phone change inside the window, if any
    changed_by: object = None
    audit_started_at: object = None  # set while the audit itself is younger than the window


def phone_changed_recently(guardian, now=None):
    """Whether this guardian's phone counts as recently changed.

    Recent means a phone change in the last 30 days, or the contact audit (PR 1's anchor event)
    started less than 30 days ago: history before it is unknown, so it fails closed (OD-R3).
    Once the anchor is purged (after 365 days) only the phone events count.
    """
    now = now or timezone.now()
    since = now - PHONE_WINDOW
    change = (
        SecurityEvent.objects.filter(
            event_type=Event.GUARDIAN_PHONE_CHANGED, guardian_id_ref=guardian.pk,
            occurred_at__gte=since,
        )
        .select_related("actor")
        .order_by("-occurred_at", "-pk")
        .first()
    )
    anchor = (
        SecurityEvent.objects.filter(event_type=Event.CONTACT_AUDIT_STARTED)
        .order_by("occurred_at")
        .values_list("occurred_at", flat=True)
        .first()
    )
    audit_started_at = anchor if anchor is not None and anchor >= since else None
    return PhoneHistory(
        recent=change is not None or audit_started_at is not None,
        changed_at=change.occurred_at if change else None,
        changed_by=change.actor if change else None,
        audit_started_at=audit_started_at,
    )
