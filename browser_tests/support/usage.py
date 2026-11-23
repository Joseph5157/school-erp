"""Shared pieces for the usage-measurement browser tests (ENG-JS-01 JS4, ADR 0027).

Standard library only: core/tests/test_js_fixture_contract.py imports the allowed values below and
checks they equal the server's allow-list in core/usage.py, so the browser tests can never accept a
value the server would refuse (or miss one it allows).
"""

import json

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
# What the beacon view accepts (core/usage_views.py), pinned by the contract test.
MAX_EVENTS = 20
MAX_BODY_BYTES = 2048
PAYLOAD_KEYS = {"d", "x", "p", "r", "a", "e"}
EVENT_KEYS = {"w", "s", "b", "z"}  # workflow, step, duration bucket, size bucket

BEACON = "/u/"

# Test-only switch for Global Privacy Control (Chromium has no setting for it): the page reads
# navigator.globalPrivacyControl, which follows window.btGpc.
GPC_SWITCH = (
    "Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {"
    " configurable: true, get() { return window.btGpc === true; } });"
)
# Test-only observer: records how the page called fetch (URL, keepalive, body) without changing
# the call, because Playwright does not report a request's keepalive flag.
FETCH_SPY = """
(() => {
  const real = window.fetch;
  window.btFetches = [];
  window.fetch = function (url, init) {
    window.btFetches.push({
      url: String(url),
      keepalive: !!(init && init.keepalive),
      body: init && typeof init.body === "string" ? init.body : null,
    });
    return real.apply(this, arguments);
  };
})();
"""


def payload(held):
    return json.loads(held.body)


def events(held):
    """The events in one beacon as (workflow, step, duration bucket or None, size bucket or None)."""
    return [(e["w"], e["s"], e.get("b"), e.get("z")) for e in payload(held)["e"]]
