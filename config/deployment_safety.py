"""Fail-closed handling of deployment settings (Security Gate 2).

Used by config/settings.py. A missing or insecure production secret, an unrecognised
transport-security flag or a malformed proxy list stops startup with a message that names
the variable. None of these messages ever includes the value that was rejected.
"""

import ipaddress

from django.core.exceptions import ImproperlyConfigured

INSECURE_KEY_PREFIX = "django-insecure-"
_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def check_secret_key(key, *, debug, testing):
    """Refuse a blank key or the committed development default outside debug and tests."""
    if debug or testing:
        return
    cleaned = (key or "").strip()
    if not cleaned or cleaned.startswith(INSECURE_KEY_PREFIX):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a unique, secret value in production. It is "
            "missing, blank or still the insecure development default. Set it on the "
            "service (see docs/OPERATIONS.md). For local development set DJANGO_DEBUG=True."
        )


def parse_flag(name, raw, default=False):
    """Read an on/off environment variable; refuse a value that is not clearly one or the other.

    A flag such as DJANGO_HTTPS used to be compared with the exact text "True", so a value
    like "true" or a typo silently switched the protection off.
    """
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(
        f"{name} must be True or False (also accepted: true, false, 1, 0, yes, no, on, off)."
    )


def parse_trusted_proxies(raw):
    """Split DJANGO_TRUSTED_PROXIES and refuse any entry that is not an address or CIDR range."""
    entries = [value.strip() for value in raw.split(",") if value.strip()]
    for position, entry in enumerate(entries, start=1):
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise ImproperlyConfigured(
                f"DJANGO_TRUSTED_PROXIES entry {position} is not an IP address or CIDR range."
            ) from None
    return entries
