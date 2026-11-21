"""Privacy-safe usage measurement (ADR 0027, Option B2).

Daily aggregate counters only: every accepted event becomes `count + 1` on one `UsageCounter` row
whose dimensions all come from the fixed enums below. No person, record, value, path, free text,
IP address, user agent or time of day is ever stored or logged. The database mirrors every enum and
column-use rule with check constraints (core.models.UsageCounter), so a code path that forgets a
rule is still refused.

Nothing is recorded unless `USAGE_MEASUREMENT_ENABLED` is on (it is off by default and switched on
only after written school approval), and never for a request carrying `Sec-GPC: 1`.

This module must not import core.models at import time: core.models imports the enums from here.
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F

logger = logging.getLogger(__name__)

# --- enums (mirrored by database check constraints; changing one needs a migration) --------------

AREAS = ("admin", "teacher", "guardian", "multi", "public")
SURFACES = ("admin", "teacher", "guardian")

WORKFLOWS = (
    "attendance_capture", "marks_entry", "teacher_home", "find_student", "missing_attendance_act",
    "page", "guardian_first_view", "guardian_report_pdf", "notice_view", "install",
    "sign_in", "session",
)

FAILURE_STEPS = ("network", "server", "signed_out", "forbidden", "conflict", "closed", "invalid",
                 "csrf")
STEPS = (
    "started", "completed", "attempt", "saved", "viewed", "shown", "installed", "dismissed",
    "failed", "throttled", "expired_idle", "expired_limit", "expired_unsaved",
    "relogin_after_expiry", "password_changed_first", "retry_tapped", "retry_succeeded",
    "fallback_save_used",
) + FAILURE_STEPS

# Stored forms use ASCII hyphens so the same text works in JSON, SQL and a terminal.
DURATION_BUCKETS = ("<5s", "5-15s", "15-60s", "1-3m", "3-10m", "10-30m", ">30m")
SIZE_BUCKETS = ("1-20", "21-40", "41+")
AGE_BUCKETS = ("same_day", "1-2d", "3-7d", "later")
DEVICES = ("phone", "tablet", "desktop")
DISPLAYS = ("browser", "installed")
PLATFORMS = ("android", "ios", "other")

# Curated page routes (spec 5.2). Adding one is a reviewed change with its own migration.
PAGE_ROUTE_AREAS = {
    **{name: "admin" for name in (
        "core:admin-overview", "core:student-list", "core:student-detail",
        "core:student-attendance", "core:attendance-register-list",
        "core:attendance-register-detail", "core:attendance-reports",
        "core:report-missing-attendance", "core:report-daily-absentees",
        "core:announcement-list", "core:announcement-detail", "core:guardian-list",
        "core:guardian-detail", "core:teacher-list", "core:teacher-detail",
        "core:applicant-list", "core:applicant-detail", "core:timetable-index",
        "core:notifications-to-send", "core:publications-stale", "core:import-list",
    )},
    **{name: "teacher" for name in (
        "core:my-home", "core:my-attendance", "core:my-attendance-history",
        "core:my-assessments", "core:assessment-marks-entry", "core:my-students",
        "core:my-student-detail", "core:my-timetable", "core:my-gradebook", "core:my-results",
    )},
    **{name: "guardian" for name in (
        "portal:home", "portal:child", "portal:attendance", "portal:notices", "portal:notice",
        "portal:report-cards", "portal:report-card",
    )},
    "root:login": "public",
}
OTHER_ROUTE = "other"
PAGE_ROUTES = tuple(PAGE_ROUTE_AREAS) + (OTHER_ROUTE,)

# --- code-level rules on top of the database constraints ------------------------------------------

SAVE_STEPS = ("attempt", "saved", "retry_tapped", "retry_succeeded") + FAILURE_STEPS
WORKFLOW_STEPS = {
    "attendance_capture": ("started", "completed") + SAVE_STEPS,
    "marks_entry": ("started", "completed", "fallback_save_used") + SAVE_STEPS,
    "teacher_home": ("started", "completed"),
    "find_student": ("started", "completed"),
    "missing_attendance_act": ("started", "completed"),
    "page": ("viewed",),
    "guardian_first_view": ("started", "completed"),
    "guardian_report_pdf": ("started", "completed"),
    "notice_view": ("viewed",),
    "install": ("shown", "installed", "dismissed"),
    "sign_in": ("completed", "failed", "throttled", "password_changed_first"),
    "session": ("expired_idle", "expired_limit", "expired_unsaved", "relogin_after_expiry"),
}
WORKFLOW_AREAS = {
    "attendance_capture": ("teacher",),
    "marks_entry": ("teacher",),
    "teacher_home": ("teacher",),
    "find_student": ("admin",),
    "missing_attendance_act": ("admin",),
    "page": SURFACES + ("public",),
    "guardian_first_view": ("guardian",),
    "guardian_report_pdf": ("guardian",),
    "notice_view": ("guardian",),
    "install": SURFACES,
    "sign_in": AREAS,
    "session": SURFACES + ("multi",),
}
# Workflows whose `completed` step may carry a duration bucket (spec section 6).
TIMED_WORKFLOWS = ("attendance_capture", "marks_entry", "teacher_home", "find_student",
                   "missing_attendance_act", "guardian_first_view")
SIZED_WORKFLOWS = ("attendance_capture", "marks_entry")
MULTI_ALLOWED = {("sign_in", "completed"), ("sign_in", "password_changed_first"),
                 ("session", "relogin_after_expiry")}

# Events the browser may report through the beacon (spec 5.2 and 6). Everything else is recorded
# by the server where it happens, so a beacon claiming it is refused.
CLIENT_EVENTS = frozenset(
    {("page", "viewed"), ("teacher_home", "started"), ("teacher_home", "completed"),
     ("marks_entry", "started"), ("marks_entry", "completed"),
     ("missing_attendance_act", "started"), ("missing_attendance_act", "completed"),
     ("install", "shown"), ("install", "installed"), ("install", "dismissed")}
    | {(w, s) for w in SIZED_WORKFLOWS
       for s in ("attempt", "network", "server", "csrf", "retry_tapped", "retry_succeeded")}
    | {("marks_entry", "fallback_save_used")}
)

DEVICE_FIELDS = ("device", "display", "platform")
OPTIONAL_FIELDS = ("page_route", "duration_bucket", "size_bucket", "age_bucket") + DEVICE_FIELDS
_ENUMS = {
    "area": AREAS, "workflow": WORKFLOWS, "step": STEPS, "page_route": PAGE_ROUTES,
    "duration_bucket": DURATION_BUCKETS, "size_bucket": SIZE_BUCKETS, "age_bucket": AGE_BUCKETS,
    "device": DEVICES, "display": DISPLAYS, "platform": PLATFORMS,
}

RETENTION_DAYS = 180
EXPIRED_MARKER = "_u_expired_at"  # epoch seconds only, in the anonymous session after an expiry
RELOGIN_WINDOW_SECONDS = 10 * 60
RATE_KEY = "_u_beacon_rate"  # [window start epoch seconds, events accepted]
RATE_LIMIT = 200
RATE_WINDOW_SECONDS = 3600
CLIENT_HEADER = "X-ERP-Client"


class InvalidEvent(ValueError):
    """An event outside the enums or column-use rules. The message never quotes the value."""


def business_today():
    from core.models import business_today as today

    return today()


def enabled():
    return bool(getattr(settings, "USAGE_MEASUREMENT_ENABLED", False))


def gpc(request):
    """Global Privacy Control: the browser asked not to be measured (OD-B10)."""
    headers = getattr(request, "headers", None)
    return bool(headers) and headers.get("Sec-GPC", "").strip() == "1"


def active(request):
    return enabled() and not gpc(request)


def page_route_for(url_name):
    """An allow-listed route name, or "other". Never a path."""
    return url_name if url_name in PAGE_ROUTE_AREAS else OTHER_ROUTE


def validate(*, area, workflow, step, page_route="", duration_bucket="", size_bucket="",
             age_bucket="", device="", display="", platform=""):
    """Return the full dimension dict, or raise InvalidEvent. Touches no database."""
    dims = {"area": area, "workflow": workflow, "step": step, "page_route": page_route,
            "duration_bucket": duration_bucket, "size_bucket": size_bucket,
            "age_bucket": age_bucket, "device": device, "display": display, "platform": platform}
    for name, value in dims.items():
        if not isinstance(value, str):
            raise InvalidEvent(f"{name}: not text")
        if value == "" and name in OPTIONAL_FIELDS:
            continue
        if value not in _ENUMS[name]:
            raise InvalidEvent(f"{name}: not an allowed value")
    if step not in WORKFLOW_STEPS[workflow]:
        raise InvalidEvent("step: not allowed for this workflow")
    if area not in WORKFLOW_AREAS[workflow]:
        raise InvalidEvent("area: not allowed for this workflow")
    if (workflow == "page") != bool(page_route):
        raise InvalidEvent("page_route: only and always for page")
    if page_route and page_route != OTHER_ROUTE and PAGE_ROUTE_AREAS[page_route] != area:
        raise InvalidEvent("page_route: belongs to another area")
    if area == "public" and not (workflow == "sign_in" or page_route == "root:login"):
        raise InvalidEvent("area: public only for sign-in")
    if area == "multi" and (workflow, step) not in MULTI_ALLOWED:
        raise InvalidEvent("area: multi only for sign-in events")
    if duration_bucket and not (step == "completed" and workflow in TIMED_WORKFLOWS):
        raise InvalidEvent("duration_bucket: only on a timed completion")
    if size_bucket and workflow not in SIZED_WORKFLOWS:
        raise InvalidEvent("size_bucket: not for this workflow")
    if (workflow == "notice_view") != bool(age_bucket):
        raise InvalidEvent("age_bucket: only and always for notice_view")
    return dims


def parse_client_header(value):
    """`device=phone;display=installed;platform=android`, strictly against the enums.

    Unknown keys and values are dropped field by field; an oversized header is dropped whole. The
    header is never logged.
    """
    result = dict.fromkeys(DEVICE_FIELDS, "")
    if not isinstance(value, str) or len(value) > 80:
        return result
    for part in value.split(";"):
        key, _, item = part.strip().partition("=")
        if key in result and item in _ENUMS[key]:
            result[key] = item
    return result


def _increment(dims):
    from core.models import UsageCounter

    return UsageCounter.objects.filter(**dims).update(count=F("count") + 1)


def _insert(dims):
    from core.models import UsageCounter

    UsageCounter.objects.create(**dims, count=1)


def _route_pattern(request):
    match = getattr(request, "resolver_match", None)
    return getattr(match, "route", None) or "-"


def record(request, *, area, workflow, step, page_route="", duration_bucket="", size_bucket="",
           age_bucket="", **device):
    """Add one to today's counter for these dimensions. Returns True if a row was written.

    Never raises for a bad value or a database problem: measurement must not break a workflow
    (spec 5.4). Unknown keyword names are a programming error and raise TypeError at the call.
    Device fields default to the `X-ERP-Client` header of `request`.
    """
    if set(device) - set(DEVICE_FIELDS):
        raise TypeError("record() got an unexpected dimension")
    if not active(request):
        return False
    if not device and request is not None:
        device = parse_client_header(getattr(request, "headers", {}).get(CLIENT_HEADER))
    try:
        dims = validate(area=area, workflow=workflow, step=step, page_route=page_route,
                        duration_bucket=duration_bucket, size_bucket=size_bucket,
                        age_bucket=age_bucket, **device)
    except InvalidEvent:
        logger.warning("Usage event dropped: invalid dimensions (route %s)",
                       _route_pattern(request))
        return False
    dims["day"] = business_today()
    try:
        with transaction.atomic():  # savepoint S1: isolates any database error from the caller
            if _increment(dims) == 0:
                try:
                    with transaction.atomic():  # savepoint S2: the creation race
                        _insert(dims)
                except IntegrityError:
                    _increment(dims)  # another request created the row first
    except DatabaseError:
        logger.warning("Usage counter write dropped (route %s)", _route_pattern(request))
        return False
    return True


def cutoff(today=None):
    """Rows on or before this day are past retention: the kept window is today-179 to today."""
    return (today or business_today()) - timedelta(days=RETENTION_DAYS)


def purge(today=None):
    """Delete rows past retention, whether or not measurement is on. Returns the number deleted."""
    from core.models import UsageCounter

    deleted, _ = UsageCounter.objects.filter(day__lte=cutoff(today)).delete()
    return deleted


def stale_rows_exist(today=None):
    from core.models import UsageCounter

    return UsageCounter.objects.filter(day__lte=cutoff(today)).exists()


# --- helpers for the server-side sign-in and session signals ---------------------------------------


def area_of_user(user):
    """`admin`, `teacher` or `guardian` for a one-area login, `multi` for several, else None."""
    from core.authorization import user_areas

    if not enabled():
        return None
    try:
        keys = [key for key, _, _ in user_areas(user)]
    except Exception:  # measurement must never break sign-in
        logger.warning("Usage area lookup failed; sign-in not counted")
        return None
    if not keys:
        return None
    return keys[0] if len(keys) == 1 else "multi"


def area_of_route(user, path):
    """The surface a requested path belongs to for this user (core.navigation.current_area).

    The middleware runs before URL resolution, so the path is resolved here. Never trusts the
    client.
    """
    from types import SimpleNamespace

    from django.urls import Resolver404, resolve

    from core.navigation import current_area

    if not enabled():
        return None
    try:
        try:
            match = resolve(path)
        except Resolver404:
            match = None
        return current_area(SimpleNamespace(user=user, resolver_match=match))
    except Exception:  # measurement must never break sign-out on expiry
        logger.warning("Usage area lookup failed; expiry not counted")
        return None


def mark_expired(request, now=None):
    """After an expiry sign-out: remember when, as a bare integer, for the relogin signal."""
    if active(request):
        request.session[EXPIRED_MARKER] = int(time.time() if now is None else now)


def take_relogin(request, now=None):
    """Pop the expiry marker; True if it was a real expiry at most 10 minutes ago."""
    marker = request.session.pop(EXPIRED_MARKER, None)
    if type(marker) is not int:
        return False
    now = time.time() if now is None else now
    return 0 <= now - marker <= RELOGIN_WINDOW_SECONDS
