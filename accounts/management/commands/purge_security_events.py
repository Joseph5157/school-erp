"""Authorized retention purge of routine security events (ADR 0013, OD-7).

Deletes only ROUTINE events older than 365 days; the database trigger
refuses anything else. HISTORY events are never purged. The operator must
name a login holding accounts.purge_securityevent; the purge itself is
recorded as a HISTORY event.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import SecurityEvent

RETENTION_DAYS = 365


class Command(BaseCommand):
    help = "Purge routine security events older than 365 days."

    def add_arguments(self, parser):
        parser.add_argument("--by", required=True, help="Username of the authorizing operator.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username__iexact=options["by"].strip()).first()
        if actor is None or not actor.is_active or not actor.has_perm(
            "accounts.purge_securityevent"
        ):
            raise CommandError("That login may not purge security events.")
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS, minutes=1)
        events = SecurityEvent.objects.filter(
            event_class=SecurityEvent.EventClass.ROUTINE, occurred_at__lt=cutoff
        )
        count = events.count()
        if options["dry_run"]:
            self.stdout.write(f"{count} routine event(s) would be purged.")
            return
        with transaction.atomic():
            deleted = events.delete()[0]
            SecurityEvent.record(SecurityEvent.EventType.SECURITY_EVENTS_PURGED, actor=actor,
                                 detail={"count": deleted, "older_than_days": RETENTION_DAYS})
        self.stdout.write(f"Purged {deleted} routine event(s).")
