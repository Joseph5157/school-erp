"""Optional Telegram alert to the operator when production hits an unhandled 500.

The Railway console log stays the authoritative record of every crash, with the full
traceback. This is only an immediate "something broke, read the log" ping to one operator's
private chat. It is not a guardian channel and accepts no commands.

What is sent comes from the same allow-list as the crash email (`config.error_reporting`,
Security Gate 4A): instance name, UTC time, level, status, request method, route pattern,
exception types and sanitised `file:line in function` locations. Never the concrete URL,
query string, client details, headers, cookies, form values, username, exception messages,
source lines, local variables or absolute paths.

Delivery is one synchronous HTTPS POST with a short timeout, on a request that has already
failed. Any delivery failure is swallowed and replaced by one fixed log line that never
includes the bot token, the chat ID, the Telegram URL, the response or the error text.
Nothing is retried.

Identical crashes are alerted at most once per five minutes. The limiter is in memory, per
process: each Gunicorn worker keeps its own, so two workers can each send one first alert.
It deliberately uses neither the database nor the cache, since either may be what failed.
"""

import json
import logging
import threading
import time
from collections import OrderedDict
from urllib.request import Request, urlopen

from django.conf import settings

from config.error_reporting import crash_facts

TIMEOUT_SECONDS = 3
COOLDOWN_SECONDS = 5 * 60
MAX_MESSAGE_LENGTH = 4096  # Telegram's limit for one message
FAILURE_LINE = "Telegram crash alert delivery failed; see the Railway log."
FOOTER = "The full details are in Railway logs."
_FRAMES_SHOWN = 6
_MAX_RESPONSE_BYTES = 64 * 1024
_HOW = {"cause": "Caused by", "raised while handling": "While handling"}

logger = logging.getLogger(__name__)


def alerts_configured():
    """True when both variables are set. Always False in debug and test runs (see settings)."""
    return bool(
        getattr(settings, "TELEGRAM_ERROR_BOT_TOKEN", "")
        and getattr(settings, "TELEGRAM_ERROR_CHAT_ID", "")
    )


def send_message(text):
    """Send `text` to the operator's chat. True when Telegram accepted it; never raises."""
    try:
        delivered = _post(text)
    except Exception:  # network, timeout, HTTP, JSON or anything unexpected
        delivered = False
    if not delivered:
        # Fixed text only: the URL holds the token and error text may quote it.
        logger.warning(FAILURE_LINE)
    return delivered


def _post(text):
    payload = {
        "chat_id": settings.TELEGRAM_ERROR_CHAT_ID,
        "text": text[:MAX_MESSAGE_LENGTH],
        "protect_content": True,
        "link_preview_options": {"is_disabled": True},
    }  # no parse_mode: plain text, so nothing in the message is interpreted as markup
    request = Request(
        f"https://api.telegram.org/bot{settings.TELEGRAM_ERROR_BOT_TOKEN}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
        status = response.status
        body = response.read(_MAX_RESPONSE_BYTES)
    answer = json.loads(body)
    return status == 200 and isinstance(answer, dict) and answer.get("ok") is True


def _fit(body):
    """Cut the body so the whole message, footer included, stays within Telegram's limit."""
    footer = "\n\n" + FOOTER
    room = MAX_MESSAGE_LENGTH - len(footer)
    if len(body) > room:
        body = body[: room - 3].rstrip() + "..."
    return body + footer


def _alert_text(facts):
    lines = [
        "School ERP error",
        "",
        f"Instance: {facts.instance}",
        f"Time (UTC): {facts.time}",
        f"Level: {facts.level}",
        f"Status: {facts.status}",
        f"Request: {facts.method} {facts.route}",
        f"Exception: {facts.kind}",
    ]
    lines.extend(f"{_HOW.get(link.how, link.how)}: {link.kind}" for link in facts.chain[1:])
    if facts.chain and facts.chain[0].frames:
        lines += ["", "Where (innermost last):"]
        lines.extend(f"  {frame}" for frame in facts.chain[0].frames[-_FRAMES_SHOWN:])
    return _fit("\n".join(lines))


def build_alert_text(record):
    """The alert for one log record, from the Gate 4A allow-list."""
    return _alert_text(crash_facts(record))


def _fallback_text():
    return _fit(
        "School ERP error\n\n"
        f"Instance: {settings.ERP_INSTANCE_NAME}\n"
        "A crash was logged, but its alert could not be built."
    )


def _fingerprint(facts):
    """Safe fields only: which installation, which route, which exception, raised where."""
    top = facts.chain[0].frames[-1] if facts.chain and facts.chain[0].frames else ""
    return (facts.instance, facts.route, facts.kind, top)


def test_message_text():
    """The fixed message `manage.py sendtesttelegram` sends; no request or account data."""
    return (
        "School ERP test alert\n\n"
        f"Instance: {settings.ERP_INSTANCE_NAME}\n"
        "This is a test message from the sendtesttelegram command. "
        "Crash alerts for this installation will arrive in this chat.\n\n"
        "No action is needed."
    )


class AlertCooldown:
    """Per-process, thread-safe and bounded: one alert per fingerprint per window."""

    def __init__(self, window=COOLDOWN_SECONDS, max_entries=256):
        self.window, self.max_entries = window, max_entries
        self._sent = OrderedDict()  # fingerprint -> monotonic time of its last alert, oldest first
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self._lock:
            while self._sent and now - next(iter(self._sent.values())) >= self.window:
                self._sent.popitem(last=False)  # expired
            if key in self._sent:
                return False
            self._sent[key] = now
            while len(self._sent) > self.max_entries:
                self._sent.popitem(last=False)  # forget the oldest rather than grow
            return True

    def keys(self):
        with self._lock:
            return list(self._sent)

    def clear(self):
        with self._lock:
            self._sent.clear()

    def __len__(self):
        with self._lock:
            return len(self._sent)


COOLDOWN = AlertCooldown()


def _is_unhandled_500(record):
    return getattr(record, "status_code", None) == 500 and bool(
        record.exc_info and record.exc_info[1] is not None
    )


class TelegramAlertHandler(logging.Handler):
    """Attached to `django.request` beside the crash email. Never raises, never retries."""

    def emit(self, record):
        try:
            if not alerts_configured() or not _is_unhandled_500(record):
                return
            try:
                facts = crash_facts(record)
                key, text = _fingerprint(facts), _alert_text(facts)
            except Exception:
                key, text = ("unbuildable", settings.ERP_INSTANCE_NAME), _fallback_text()
            if COOLDOWN.allow(key):
                send_message(text)
        except Exception:
            logger.warning(FAILURE_LINE)
