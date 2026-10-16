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
