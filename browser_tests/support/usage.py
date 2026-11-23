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
CHROMIUM_HEADERS = {"accept", "accept-language", "content-type", "origin", "referer", "user-agent",
                    "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "upgrade-insecure-requests"}
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
# Test-only observer of the page's own requests: for every fetch and XMLHttpRequest it records the
# method, the exact URL (fragment included), the headers the page itself set, the body's type and a
# text body, and reports each record to the test (window.btReports holds a promise per report, so
# the test can wait for them: a handshake, not a sleep). It never changes a request. Chromium's own
# headers are not in a record, which is how the audit tells them apart.
FETCH_SPY = """
(() => {
  window.btFetches = [];
  window.btReports = window.btReports || [];
  function report(record) {
    window.btFetches.push(record);
    if (window.btRecordFetch) window.btReports.push(window.btRecordFetch(record));
  }
  function kind(body) {
    return body === undefined || body === null ? "none" : Object.prototype.toString.call(body);
  }
  const realFetch = window.fetch;
  window.fetch = function (url, init) {
    init = init || {};
    report({
      api: "fetch",
      url: String(url),
      href: new URL(String(url), location.href).href,
      method: init.method || "GET",
      headers: Object.assign({}, init.headers || {}),
      keepalive: !!init.keepalive,
      bodyKind: kind(init.body),
      body: typeof init.body === "string" ? init.body : null,
    });
    return realFetch.apply(this, arguments);
  };
  const xhr = XMLHttpRequest.prototype, open = xhr.open, setHeader = xhr.setRequestHeader, send = xhr.send;
  xhr.open = function (method, url) {
    this.btRecord = {api: "xhr", url: String(url), href: new URL(String(url), location.href).href,
                     method: String(method).toUpperCase(), headers: {}, keepalive: false};
    return open.apply(this, arguments);
  };
  xhr.setRequestHeader = function (name, value) {
    if (this.btRecord) this.btRecord.headers[name] = String(value);
    return setHeader.apply(this, arguments);
  };
  xhr.send = function (body) {
    if (this.btRecord) {
      this.btRecord.bodyKind = kind(body);
      this.btRecord.body = typeof body === "string" ? body : null;
      report(this.btRecord);
    }
    return send.apply(this, arguments);
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
    """A multipart/form-data body as a list of (name, value), parsed strictly; ValueError if not.

    The body must start with the first boundary and end with the closing one (no preamble or
    epilogue); each part has exactly one header, Content-Disposition with a name and nothing else;
    values are kept exactly (no trimming).
    """
    match = re.fullmatch(r"multipart/form-data; boundary=([0-9A-Za-z'()+_,./:=?-]{1,70})", content_type or "")
    if not match:
        raise ValueError(f"not a multipart content type with one boundary: {content_type!r}")
    boundary = "--" + match.group(1)
    body = body or ""
    if not body.startswith(boundary + "\r\n"):
        raise ValueError("text before the first part (a preamble)")
    if not body.endswith("\r\n" + boundary + "--\r\n"):
        raise ValueError("text after the closing boundary (an epilogue), or no closing boundary")
    inner = body[len(boundary) + 2:len(body) - len(boundary) - 6]
    parts = []
    for chunk in inner.split("\r\n" + boundary + "\r\n"):
        head, separator, value = chunk.partition("\r\n\r\n")
        if not separator:
            raise ValueError("a part without a header block")
        header = re.fullmatch(r'Content-Disposition: form-data; name="([^"\r\n]*)"', head)
        if not header:
            raise ValueError(f"part headers other than one Content-Disposition with a name: {head!r}")
        parts.append((header.group(1), value))
    return parts
