"""Fail-closed handling of deployment settings (Security Gate 2).

Used by config/settings.py. A missing or insecure production secret, an unrecognised
transport-security flag, a malformed proxy list or a half-configured Telegram alert pair
stops startup with a message that names the variable. None of these messages ever includes
the value that was rejected.
"""

import ipaddress

from django.core.exceptions import ImproperlyConfigured

INSECURE_KEY_PREFIX = "django-insecure-"
_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


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


def mail_backend_for(host, *, debug):
    """Mail goes out only when an SMTP host is configured.

    Without one, production discards mail (so crash emails stay off until a provider is
    chosen and its credentials are set) and local development prints it to the console.
    """
    if (host or "").strip():
        return "django.core.mail.backends.smtp.EmailBackend"
    if debug:
        return "django.core.mail.backends.console.EmailBackend"
    return "django.core.mail.backends.dummy.EmailBackend"


def parse_flag(name, raw, default=False):
    """Read an on/off environment variable; refuse a value that is not clearly one or the other.

    A flag such as DJANGO_HTTPS used to be compared with the exact text "True", so a value
    like "true" or a typo silently switched the protection off. A blank value counts as
    unset and uses the flag's own default, so an empty `EMAIL_USE_TLS=` cannot switch
    encryption off either.
    """
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(
        f"{name} must be True or False (also accepted: true, false, 1, 0, yes, no, on, off)."
    )


def resolve_https(raw, *, debug, testing):
    """The DJANGO_HTTPS setting for this run, so HTTPS is never silently lost in production.

    Debug and test runs keep the plain-HTTP default, because local servers and the test
    client have no TLS. In production an unset or blank variable means HTTPS on (Secure
    cookies, HTTPS redirect, HSTS), and an explicit false is refused rather than honoured.
    """
    if debug or testing:
        return parse_flag("DJANGO_HTTPS", raw)
    if parse_flag("DJANGO_HTTPS", raw, default=True):
        return True
    raise ImproperlyConfigured(
        "DJANGO_HTTPS is turned off, but production must serve over HTTPS. Remove the "
        "variable or set it to True. For local development set DJANGO_DEBUG=True."
    )


def telegram_alert_settings(token_raw, chat_raw, *, debug, testing):
    """(token, chat_id) for the optional Telegram crash alerts; ("", "") means off.

    Both variables set: alerts on. Both unset or blank: alerts off. Only one set: startup
    stops, naming the missing variable and never echoing the one that was supplied. The
    pair is checked in every kind of run, but debug and test runs always get ("", ""), so
    they can never contact Telegram even when the variables are present.
    """
    token, chat_id = (token_raw or "").strip(), (chat_raw or "").strip()
    if bool(token) != bool(chat_id):
        missing, present = (
            ("TELEGRAM_ERROR_CHAT_ID", "TELEGRAM_ERROR_BOT_TOKEN")
            if token
            else ("TELEGRAM_ERROR_BOT_TOKEN", "TELEGRAM_ERROR_CHAT_ID")
        )
        raise ImproperlyConfigured(
            f"{present} is set but {missing} is not. Telegram crash alerts need both "
            "variables; set the missing one, or remove both to turn the alerts off "
            "(see docs/OPERATIONS.md)."
        )
    if debug or testing:
        return "", ""
    return token, chat_id


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
