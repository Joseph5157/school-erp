"""The usage beacon (ADR 0027, Option B2; spec 5.6).

A signed-in page posts a small JSON batch of allow-listed events here. The whole batch is checked
against the enums, the client-reportable events and the signed-in user's own areas; one bad field
drops all of it. Accepted events become daily counter increments. Nothing from the body or the
headers is logged, and the reply never has a body.

No page sends beacons yet: the client side arrives with the workflow instrumentation (B3).
"""

import json
import time

from django.http import HttpResponse
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core import usage
from core.authorization import user_areas

MAX_BODY_BYTES = 2048
MAX_EVENTS = 20
SHARED_KEYS = {"d", "x", "p", "r", "a", "e"}
EVENT_KEYS = {"w", "s", "b"}


def _empty(status):
    response = HttpResponse(status=status)
    patch_cache_control(response, no_store=True)
    return response


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise usage.InvalidEvent("not text")
    return value


def _parse(request):
    """The batch as a list of validated dimension dicts, or raise InvalidEvent."""
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise usage.InvalidEvent("not JSON") from None
    if not isinstance(body, dict) or not set(body) <= SHARED_KEYS:
        raise usage.InvalidEvent("bad shape")
    events = body.get("e")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise usage.InvalidEvent("bad events")
    area = _text(body.get("a"))
    if area not in [key for key, _, _ in user_areas(request.user)]:
        raise usage.InvalidEvent("area is not one of this login's areas")
    route = _text(body.get("r"))
    if route and route not in usage.PAGE_ROUTES:
        raise usage.InvalidEvent("route not allowed")
    if route and route != usage.OTHER_ROUTE and usage.PAGE_ROUTE_AREAS[route] != area:
        raise usage.InvalidEvent("route belongs to another area")
    device = {"device": _text(body.get("d")), "display": _text(body.get("x")),
              "platform": _text(body.get("p"))}
    batch = []
    for event in events:
        if not isinstance(event, dict) or not set(event) <= EVENT_KEYS:
            raise usage.InvalidEvent("bad event")
        workflow, step = _text(event.get("w")), _text(event.get("s"))
        if (workflow, step) not in usage.CLIENT_EVENTS:
            raise usage.InvalidEvent("not a client-reported event")
        batch.append(usage.validate(
            area=area, workflow=workflow, step=step,
            page_route=route if workflow == "page" else "",
            duration_bucket=_text(event.get("b")), **device,
        ))
    return batch


def _within_rate(request, wanted):
    """How many of `wanted` events this session may still record this hour (spec 5.6)."""
    now = int(time.time())
    window = request.session.get(usage.RATE_KEY)
    if not (isinstance(window, list) and len(window) == 2
            and all(type(v) is int for v in window)
            and 0 <= now - window[0] < usage.RATE_WINDOW_SECONDS):
        window = [now, 0]
    allowed = max(0, min(wanted, usage.RATE_LIMIT - window[1]))
    request.session[usage.RATE_KEY] = [window[0], window[1] + allowed]
    return allowed


@never_cache
@require_POST
def beacon(request):
    """Record a batch of allow-listed usage events. 401 signed out, 400 bad batch, else 204."""
    if not request.user.is_authenticated:
        return _empty(401)  # never a redirect: a background request must not read a sign-in page
    if not usage.active(request):
        return _empty(204)
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return _empty(400)
    if declared > MAX_BODY_BYTES or len(request.body) > MAX_BODY_BYTES:
        return _empty(400)
    try:
        batch = _parse(request)
    except usage.InvalidEvent:
        return _empty(400)
    for dims in batch[:_within_rate(request, len(batch))]:
        usage.record(request, **dims)
    return _empty(204)
