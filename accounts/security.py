"""Phase 6 Gate 7: sign-in throttling and network-source handling (ADR 0013).

Source address (OD-3): REMOTE_ADDR, unless the request comes from an address
in settings.TRUSTED_PROXIES, in which case the right-most X-Forwarded-For
entry that is not a trusted proxy. With no trusted proxies configured,
forwarded headers are ignored. The canonical address is stored only as an
HMAC under settings.SOURCE_HASH_KEY.

Throttling (plan §8):
- Rule A: 5 failures for the same username + source within 15 minutes;
- Rule B: 20 failures for the same username from any sources within 15 minutes.
Refusals look exactly like a wrong password. Failures expire after 24 hours.
"""

import hashlib
import hmac
import ipaddress
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import LoginFailure
from accounts.usernames import normalize_username

WINDOW = timedelta(minutes=15)
RETENTION = timedelta(hours=24)
RULE_A_LIMIT = 5
RULE_B_LIMIT = 20


def _networks():
    networks = []
    for value in getattr(settings, "TRUSTED_PROXIES", []):
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _parse(value):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def client_address(request):
    """The canonical client address string (OD-3)."""
    remote = _parse(request.META.get("REMOTE_ADDR"))
    networks = _networks()
    if remote is not None and networks and any(remote in net for net in networks):
        hops = [_parse(part) for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
        for hop in reversed([h for h in hops if h is not None]):
            if not any(hop in net for net in networks):
                return hop.compressed
    return remote.compressed if remote is not None else "unknown"


def source_key(request):
    key = settings.SOURCE_HASH_KEY.encode()
    return hmac.new(key, client_address(request).encode(), hashlib.sha256).hexdigest()


def purge_expired(now=None):
    now = now or timezone.now()
    LoginFailure.objects.filter(occurred_at__lt=now - RETENTION).delete()


def is_throttled(username, source, now=None):
    now = now or timezone.now()
    recent = LoginFailure.objects.filter(
        username_key=normalize_username(username), occurred_at__gte=now - WINDOW
    )
    if recent.filter(source_key=source).count() >= RULE_A_LIMIT:
        return True
    return recent.count() >= RULE_B_LIMIT


def record_failure(username, source, now=None):
    LoginFailure.objects.create(
        username_key=normalize_username(username)[:150], source_key=source,
        occurred_at=now or timezone.now(),
    )


def clear_source_failures(username, source):
    LoginFailure.objects.filter(
        username_key=normalize_username(username), source_key=source
    ).delete()


def locked_usernames(now=None):
    """Usernames currently refused by Rule A (any source) or Rule B.

    One grouped query over the 15-minute window; rows are distinct (username, source)
    pairs, so a spray of many sources against one username grows the result set.
    """
    from django.db.models import Count

    now = now or timezone.now()
    per_source = (
        LoginFailure.objects.filter(occurred_at__gte=now - WINDOW)
        .values("username_key", "source_key").annotate(n=Count("pk"))
    )
    locked = set()
    per_username = {}
    for row in per_source:  # one query: rows are distinct (username, source) pairs
        key = row["username_key"]
        per_username[key] = per_username.get(key, 0) + row["n"]
        if row["n"] >= RULE_A_LIMIT:
            locked.add(key)
    locked |= {key for key, total in per_username.items() if total >= RULE_B_LIMIT}
    return sorted(locked)


def clear_lockout(username):
    return LoginFailure.objects.filter(username_key=normalize_username(username)).delete()[0]


def clear_lockout_on_reset(user, actor):
    """An office reset must not hand over a password the lockout still refuses (ADR 0029 R16).

    Failures for the login are always wiped; LOCKOUT_CLEARED is recorded only when it was locked.
    """
    from accounts.models import SecurityEvent

    was_locked = normalize_username(user.username)[:150] in locked_usernames()
    clear_lockout(user.username)
    if was_locked:
        SecurityEvent.record(SecurityEvent.EventType.LOCKOUT_CLEARED, actor=actor,
                             subject_user=user, detail={"username": user.username})


# --- G-06 reset spec §5: temporary passwords expire ---------------------------------------

CREATED_WINDOW = timedelta(days=14)  # account slip (OD-G5)
RESET_WINDOW = timedelta(hours=72)  # office reset (OD-G5)
FIRST_USE_GRACE = timedelta(hours=1)  # a used slip stops working an hour later (S-07)
_WINDOWS = {"CREATED": CREATED_WINDOW, "RESET": RESET_WINDOW}


def issue_temporary_password(user, kind):
    """Stamp a newly issued temporary password; the caller saves TEMPORARY_PASSWORD_FIELDS."""
    user.temporary_password_issued_at = timezone.now()
    user.temporary_password_kind = kind
    user.temporary_password_first_used_at = None


TEMPORARY_PASSWORD_FIELDS = [
    "temporary_password_issued_at", "temporary_password_kind", "temporary_password_first_used_at",
]


def temporary_password_expires_at(user, *, ignore_first_use=False):
    """When this login's temporary password stops working, or None if it does not expire.

    Off until TEMP_PASSWORD_EXPIRY_FROM is set. Expiry needs the forced change, an issue time
    and a kind; with any of them missing the password never expires and nothing raises (S-04).
    Counting from the later of the issue time and the switch-on gives every slip outstanding at
    switch-on a full window (S-02).
    """
    switch_on = getattr(settings, "TEMP_PASSWORD_EXPIRY_FROM", None)
    issued = getattr(user, "temporary_password_issued_at", None)
    window = _WINDOWS.get(getattr(user, "temporary_password_kind", ""))
    if switch_on is None or not user.must_change_password or issued is None or window is None:
        return None
    expires = max(issued, switch_on) + window
    first_used = getattr(user, "temporary_password_first_used_at", None)
    if first_used is not None and not ignore_first_use:
        expires = min(expires, first_used + FIRST_USE_GRACE)
    return expires


def temporary_password_expired(user, now=None):
    expires = temporary_password_expires_at(user)
    return expires is not None and (now or timezone.now()) >= expires


def _active_guardian(user):
    from core.models import GuardianAccount

    account = GuardianAccount.objects.filter(user=user, revoked_at__isnull=True).first()
    return account.guardian if account else None


def record_expired_temporary_password(user):
    """One TEMPORARY_PASSWORD_EXPIRED event per issued password (duplicates are harmless)."""
    from accounts.models import SecurityEvent

    Event = SecurityEvent.EventType
    if SecurityEvent.objects.filter(
        event_type=Event.TEMPORARY_PASSWORD_EXPIRED, subject_user=user,
        occurred_at__gte=user.temporary_password_issued_at,
    ).exists():
        return
    SecurityEvent.record(Event.TEMPORARY_PASSWORD_EXPIRED, subject_user=user,
                         guardian=_active_guardian(user),
                         detail={"kind": user.temporary_password_kind})


def note_successful_sign_in(user):
    """After a sign-in a door accepted: start the one-hour grace of a temporary password, and
    record the first guardian sign-in after an office reset (spec §4.6, §5.4)."""
    from accounts.models import SecurityEvent, User

    if not user.must_change_password or user.temporary_password_issued_at is None:
        return
    if user.temporary_password_first_used_at is None:
        User.objects.filter(pk=user.pk, temporary_password_first_used_at__isnull=True).update(
            temporary_password_first_used_at=timezone.now()
        )
    Event = SecurityEvent.EventType
    if user.temporary_password_kind != "RESET":
        return
    guardian = _active_guardian(user)
    if guardian is None:
        return
    if SecurityEvent.objects.filter(
        event_type=Event.FIRST_SIGN_IN_AFTER_RESET, subject_user=user,
        occurred_at__gte=user.temporary_password_issued_at,
    ).exists():
        return
    SecurityEvent.record(Event.FIRST_SIGN_IN_AFTER_RESET, actor=user, subject_user=user,
                         guardian=guardian)
