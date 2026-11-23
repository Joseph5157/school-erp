"""Shared pieces for the usage-measurement browser tests (ENG-JS-01 JS4, ADR 0027).

Standard library only: core/tests/test_js_fixture_contract.py imports the allowed values below and
checks they equal the server's allow-list in core/usage.py, so the browser tests can never accept a
value the server would refuse (or miss one it allows).
"""

import json
import re
from urllib.parse import parse_qsl

# ADR 0027 allow-list, as the browser may send it (pinned to core/usage.py by the contract test).
DEVICES = ("phone", "tablet", "desktop")
DISPLAYS = ("browser", "installed")
PLATFORMS = ("android", "ios", "other")
DURATION_BUCKETS = ("<5s", "5-15s", "15-60s", "1-3m", "3-10m", "10-30m", ">30m")
SIZE_BUCKETS = ("1-20", "21-40", "41+")
AREAS = ("admin", "teacher", "guardian", "multi", "public")
CLIENT_EVENTS = frozenset({
    ("page", "viewed"), ("teacher_home", "started"), ("teacher_home", "completed"),
    ("marks_entry", "started"), ("marks_entry", "completed"),
    ("missing_attendance_act", "started"), ("missing_attendance_act", "completed"),
    ("install", "shown"), ("install", "installed"), ("install", "dismissed"),
    ("marks_entry", "fallback_save_used"),
    *((workflow, step) for workflow in ("attendance_capture", "marks_entry")
      for step in ("attempt", "network", "server", "csrf", "retry_tapped", "retry_succeeded")),
})
# Only marks started and completed may carry a size bucket (core/usage.py CLIENT_SIZED_EVENTS).
CLIENT_SIZED_EVENTS = frozenset({("marks_entry", "started"), ("marks_entry", "completed")})
# Routes a page may report and the area each belongs to (core/usage.py PAGE_ROUTE_AREAS); any other
# route is reported as "other".
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
# What the beacon view accepts (core/usage_views.py), pinned by the contract test.
MAX_EVENTS = 20
MAX_BODY_BYTES = 2048
PAYLOAD_KEYS = {"d", "x", "p", "r", "a", "e"}
EVENT_KEYS = {"w", "s", "b", "z"}  # workflow, step, duration bucket, size bucket

BEACON = "/u/"
BEACON_METHOD = "POST"
# The headers the page itself sets on a beacon (Chromium adds its own, which are not compared).
BEACON_HEADERS = {"Content-Type": "application/json", "X-CSRFToken": "test-token",
                  "X-Requested-With": "XMLHttpRequest"}

# Test-only switch for Global Privacy Control (Chromium has no setting for it): the page reads
# navigator.globalPrivacyControl, which follows window.btGpc.
GPC_SWITCH = (
    "Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {"
    " configurable: true, get() { return window.btGpc === true; } });"
)
# Test-only observer: records how the page called fetch (URL, method, the headers the page set,
# keepalive, body) without changing the call, because Playwright does not report keepalive and
# cannot tell the page's own headers from the browser's.
FETCH_SPY = """
(() => {
  const real = window.fetch;
  window.btFetches = [];
  window.fetch = function (url, init) {
    const record = {
      url: String(url),
      href: new URL(String(url), location.href).href, // the exact destination, fragment included
      method: (init && init.method) || "GET",
      headers: Object.assign({}, (init && init.headers) || {}),
      keepalive: !!(init && init.keepalive),
      body: init && typeof init.body === "string" ? init.body : null,
    };
    window.btFetches.push(record);
    // To the test, across page loads. Each report is a promise the test can wait for (a handshake,
    // not a sleep): window.btReported resolves once the test has received every report so far.
    window.btReports = window.btReports || [];
    if (window.btRecordFetch) window.btReports.push(window.btRecordFetch(record));
    return real.apply(this, arguments);
  };
})();
"""


# Test-only: the installed app (display-mode: standalone) as the page's media query sees it.
STANDALONE_DISPLAY = r"""
(() => {
  const real = window.matchMedia.bind(window);
  window.matchMedia = function (query) {
    if (/display-mode:\s*standalone/.test(query)) {
      return { matches: true, media: query, onchange: null, addListener() {}, removeListener() {},
               addEventListener() {}, removeEventListener() {} };
    }
    return real(query);
  };
})();
"""


def payload(held):
    return json.loads(held.body)


def events(held):
    """The events in one beacon as (workflow, step, duration bucket or None, size bucket or None)."""
    return [(e["w"], e["s"], e.get("b"), e.get("z")) for e in payload(held)["e"]]


def form_fields(body):
    """An application/x-www-form-urlencoded body as an ordered list of (name, value)."""
    return parse_qsl(body or "", keep_blank_values=True)


def multipart_parts(body, content_type):
    """A multipart/form-data body as a list of (name, filename or None, value), or None."""
    match = re.search(r"boundary=([^;]+)", content_type or "")
    if not match:
        return None
    parts = []
    for chunk in (body or "").split("--" + match.group(1))[1:]:
        if chunk.startswith("--"):
            break  # the closing boundary
        head, _, value = chunk.strip("\r\n").partition("\r\n\r\n")
        name = re.search(r'name="([^"]*)"', head)
        filename = re.search(r'filename="([^"]*)"', head)
        parts.append((name.group(1) if name else None, filename.group(1) if filename else None, value))
    return parts
