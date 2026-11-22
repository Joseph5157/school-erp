"""Browser fixture harness (ENG-JS-01, ADR 0028, spec section 7.2).

One Chromium process per test run, a fresh browser context and page per test. Every request is
intercepted at the context level: fixture pages and /static/ files are served from disk, other
requests to https://erp.test are held for the test to answer, and anything else is aborted and
recorded so the test fails. If serving a request raises (for example a missing fixture), the request
is aborted at once and the test fails. Service workers are blocked. No Django server, database or
real network is used.

These are plain unittest tests, run with
`python -m unittest discover -s browser_tests -p "bt_*.py" -t .`. Django's SimpleTestCase does
not work here: once Playwright's event loop is running, Django's per-context database wrappers
cannot be restored at teardown. The tests need no Django anyway.
"""

import atexit
import json
import os
import pathlib
import tempfile
import time
import unittest

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
FIXTURES = ROOT / "browser_tests" / "fixtures"
ORIGIN = "https://erp.test"
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css"}
# Failure screenshots and traces show only synthetic fixture pages (spec section 7.6).
ARTIFACTS = pathlib.Path(os.environ.get("BT_ARTIFACT_DIR") or (pathlib.Path(tempfile.gettempdir()) / "bt-artifacts"))

_playwright = None
_browser = None


def _close():
    global _playwright, _browser
    if _browser is not None and _browser.is_connected():
        _browser.close()
    if _playwright is not None:
        _playwright.stop()
    _browser = _playwright = None


def browser():
    """The one browser for this run, started on first use and closed at exit."""
    global _playwright, _browser
    if _browser is not None and not _browser.is_connected():
        _browser = None  # a crashed browser is replaced, so one crash cannot fail every later test
    if _playwright is None:
        _playwright = sync_playwright().start()
        atexit.register(_close)
    if _browser is None:
        _browser = _playwright.chromium.launch()
    return _browser


# Opt-in (FixturePage.xhr_timeouts_on_page_clock): a native XHR timeout is not a JavaScript timer,
# so page.clock cannot move it (checked in JS2). This test-only init script keeps the page's own
# timeout value but runs it on setTimeout, which the page clock controls; when it expires the
# request is ended and only `timeout` then `loadend` reach the page's handlers, as for a real
# timeout (the abort events of ending it are kept silent).
# Time still flows naturally, so a test that never moves the clock sees the real timeout.
XHR_TIMEOUT_ON_PAGE_CLOCK = """
(() => {
  const proto = XMLHttpRequest.prototype;
  const send = proto.send;
  const add = proto.addEventListener;
  // While the request is ended for its timeout, its abort and loadend listeners stay silent; the
  // events a browser fires for a timeout (timeout, then loadend) are dispatched afterwards.
  proto.addEventListener = function (type, listener, options) {
    if ((type === "abort" || type === "loadend") && typeof listener === "function") {
      const inner = listener;
      listener = function (event) { if (!this.btSilent) return inner.call(this, event); };
    }
    return add.call(this, type, listener, options);
  };
  Object.defineProperty(proto, "timeout", {
    configurable: true,
    get() { return this.btTimeout || 0; },
    set(ms) { this.btTimeout = Number(ms) || 0; },
  });
  proto.send = function (...args) {
    const xhr = this;
    if (xhr.btTimeout > 0) {
      const timer = setTimeout(() => {
        if (xhr.readyState === XMLHttpRequest.DONE) return;
        xhr.btTimedOut = true;
        xhr.btSilent = true;
        const onabort = xhr.onabort, onloadend = xhr.onloadend;
        xhr.onabort = null;
        xhr.onloadend = null;
        xhr.abort();
        xhr.onabort = onabort;
        xhr.onloadend = onloadend;
        xhr.btSilent = false;
        xhr.dispatchEvent(new ProgressEvent("timeout"));
        xhr.dispatchEvent(new ProgressEvent("loadend"));
      }, xhr.btTimeout);
      xhr.addEventListener("loadend", () => { if (!xhr.btTimedOut) clearTimeout(timer); });
    }
    return send.apply(this, args);
  };
})();
"""


def reply(name):
    """A hand-written server reply from fixtures/replies/ (kept honest by the Django contract test)."""
    return (FIXTURES / "replies" / name).read_text(encoding="utf-8")


class Held:
    """A request the page made to https://erp.test, waiting for the test to answer it."""

    def __init__(self, route, request, owner):
        self.route = route
        self.request = request
        self.owner = owner
        self.closed = None  # the failure text once the page has given up on this request
        self.url = request.url
        self.path = request.url[len(ORIGIN):]
        self.method = request.method
        self.headers = request.headers
        self.body = request.post_data or ""
        self.answered = False

    def respond(self, status=200, body="", headers=None):
        # A reply with a body but no headers crashed the Chromium 156 renderer (found in JS1), so
        # every reply carries a Content-Type.
        headers = dict(headers or {})
        if not any(key.lower() == "content-type" for key in headers):
            headers["Content-Type"] = "text/plain; charset=utf-8"
        self.owner.page.evaluate("0")  # take in any requestfailed event first
        if self.closed:
            # Playwright accepts a reply to a closed request silently; that would hide a test
            # that answered too late (for example after a timeout).
            raise AssertionError(f"the page had already closed {self.method} {self.path} ({self.closed}) "
                                 "before the test answered it")
        self.answered = True
        self.route.fulfill(status=status, body=body, headers=headers)

    # There is deliberately no later "fail": aborting a request after its route handler has
    # returned crashed the Chromium 156 renderer with every abort code (found in JS1). Network
    # failures are made on arrival instead (FixturePage.fail_on_arrival).


class FixturePage(unittest.TestCase):
    viewport = {"width": 390, "height": 800}
    init_scripts = ()
    clock = False  # install the page clock before the page loads
    xhr_timeouts_on_page_clock = False  # needs clock = True; see XHR_TIMEOUT_ON_PAGE_CLOCK
    artifacts = ARTIFACTS  # where a failing test's diagnostics go
    # A stuck Playwright call fails the test (and saves its diagnostics) well before the CI step
    # timeout kills the run.
    action_timeout_ms = 10_000

    def setUp(self):
        self.context = browser().new_context(viewport=self.viewport, service_workers="block")
        self.context.set_default_timeout(self.action_timeout_ms)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.held = []
        self.fail_paths = []
        self.external = []
        self.page_errors = []
        self.route_errors = []
        self.context.route("**/*", self._route)
        self.context.on("requestfailed", self._request_failed)
        if self.xhr_timeouts_on_page_clock:
            assert self.clock, "xhr_timeouts_on_page_clock needs clock = True"
            self.context.add_init_script(XHR_TIMEOUT_ON_PAGE_CLOCK)
        for script in self.init_scripts:
            self.context.add_init_script(script)
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        if self.clock:
            self.page.clock.install()

    def tearDown(self):
        failed = self._failed()
        # One last round-trip first, so a request the page made just before the test ended has
        # reached the route handler (and is held, blocked or recorded) before the guards are read.
        try:
            self.page.evaluate("0")
        except Exception:  # a crashed or closed page; the test's own failure says why
            pass
        self._release_held()
        guard_failed = bool(self.route_errors or self.page_errors or self.external)
        try:
            if failed or guard_failed:
                self.save_diagnostics(self.artifacts / self.id().replace(".", "-"))
            else:
                self.context.tracing.stop()
        finally:
            self.context.close()
        if not failed:
            self.assertEqual(self.route_errors, [], "the harness could not serve a request")
            self.assertEqual(self.page_errors, [], "errors were thrown in the page")
            self.assertEqual(self.external, [], "the page tried to reach the real network")

    def _release_held(self):
        """Teardown only: settle every held route the test did not answer, closed ones included.

        A route left open when the context closes makes Playwright print a CancelledError. This
        bypasses Held.respond (and its closed-request assertion), ignores every error and records
        nothing, so it cannot change the test's result.
        """
        for held in self.held:
            if held.answered:
                continue
            try:
                held.route.fulfill(status=204, headers={"Content-Type": "text/plain; charset=utf-8"})
            except Exception:  # the page or Playwright may already have finished with it
                pass

    def save_diagnostics(self, stem):
        """Screenshot, Playwright trace and the guard records for a failing test.

        Stops this context's tracing. The records file lists page errors, blocked real-network
        requests, requests the harness could not serve, and held requests (path and method only).
        """
        stem = pathlib.Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        records = {
            "page_errors": self.page_errors,
            "external_requests": self.external,
            "route_errors": self.route_errors,
            "held_requests": [{"method": h.method, "path": h.path, "answered": h.answered, "closed": h.closed}
                              for h in self.held],
        }
        pathlib.Path(f"{stem}-records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        try:
            self.page.screenshot(path=f"{stem}.png", full_page=True)
        finally:
            self.context.tracing.stop(path=f"{stem}-trace.zip")

    def _failed(self):
        # A failure inside self.subTest() is recorded against a _SubTest whose test_case is self.
        result = self._outcome.result
        return any(getattr(test, "test_case", test) is self
                   for test, _ in list(result.errors) + list(result.failures))

    def _request_failed(self, request):
        for held in self.held:
            if held.request is request:
                held.closed = request.failure or "failed"

    def _route(self, route, request):
        try:
            self._serve(route, request)
        except Exception as error:
            # Never leave a request hanging: abort it now (inside the handler, which is safe) and
            # fail the test, at its next pump() or in tearDown at the latest.
            self.route_errors.append(f"{request.method} {request.url}: {type(error).__name__}: {error}")
            try:
                route.abort("failed")
            except Exception:  # already answered before the error
                pass

    def _serve(self, route, request):
        url = request.url
        if url.startswith(ORIGIN + "/static/"):
            path = STATIC / url[len(ORIGIN + "/static/"):].split("?")[0]
            route.fulfill(status=200, body=path.read_bytes(),
                          headers={"Content-Type": TYPES.get(path.suffix, "application/octet-stream")})
        elif url.startswith(ORIGIN + "/fixtures/"):
            path = FIXTURES / url[len(ORIGIN + "/fixtures/"):].split("?")[0]
            route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": TYPES[".html"]})
        elif url.startswith(ORIGIN + "/"):
            path = url[len(ORIGIN):]
            if any(path.startswith(prefix) for prefix in self.fail_paths):
                route.abort("internetdisconnected")  # a network failure, made while handling
            else:
                self.held.append(Held(route, request, self))
        else:
            self.external.append(url)
            route.abort("blockedbyclient")

    # --- helpers ----------------------------------------------------------------------------

    def fail_on_arrival(self, path):
        """Requests to this path fail as network errors when they arrive (see Held)."""
        self.fail_paths.append(path)

    def open(self, fixture):
        self.page.goto(f"{ORIGIN}/fixtures/{fixture}")

    def pump(self, seconds=0.02):
        """Let the browser and Playwright exchange events for a moment of real time."""
        self.page.evaluate("0")
        time.sleep(seconds)
        if self.route_errors:
            self.fail(f"the harness could not serve a request: {self.route_errors}")

    def wait_until(self, condition, timeout=5.0, message="condition"):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return
            self.pump()
        self.fail(f"timed out waiting for {message}")

    def pending(self, path=None):
        """Held requests still open: not answered, and not closed by the page."""
        return [h for h in self.held
                if not h.answered and not h.closed and (path is None or h.path.startswith(path))]

    def next_request(self, path=None, timeout=5.0):
        self.wait_until(lambda: self.pending(path), timeout, f"a request to {path or 'erp.test'}")
        return self.pending(path)[0]

    def no_request(self, path=None, seconds=0.5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.pump()
        self.assertEqual([h.path for h in self.pending(path)], [], "unexpected request")
