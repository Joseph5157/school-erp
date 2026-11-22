"""Browser fixture harness (ENG-JS-01, ADR 0028, spec section 7.2). SPIKE VERSION.

One Chromium process per test run, a fresh browser context and page per test. Every request is
intercepted at the context level: fixture pages and /static/ files are served from disk, other
requests to https://erp.test are held for the test to answer, and anything else is aborted and
recorded so the test fails. No Django server, database or real network is used.
"""

import atexit
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
ARTIFACTS = pathlib.Path(os.environ.get("BT_ARTIFACT_DIR") or (pathlib.Path(tempfile.gettempdir()) / "bt-artifacts"))

_playwright = None
_browser = None


def _close():
    global _playwright, _browser
    if _browser is not None:
        _browser.close()
        _playwright.stop()
        _browser = _playwright = None


def browser():
    """The one browser for this run, started on first use and closed at exit."""
    global _playwright, _browser
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch()
        atexit.register(_close)
    return _browser


class Held:
    """A request the page made to https://erp.test, waiting for the test to answer it."""

    def __init__(self, route, request):
        self.route = route
        self.url = request.url
        self.path = request.url[len(ORIGIN):]
        self.method = request.method
        self.headers = request.headers
        self.body = request.post_data or ""
        self.answered = False

    def respond(self, status=200, body="", headers=None):
        self.answered = True
        self.route.fulfill(status=status, body=body, headers=headers or {})

    def fail(self):
        self.answered = True
        self.route.abort("failed")


class FixturePage(unittest.TestCase):
    """Plain unittest: Django's SimpleTestCase breaks once Playwright's event loop is running
    (database wrappers are per async context), and these tests need no Django at all."""

    viewport = {"width": 390, "height": 800}
    init_scripts = ()
    clock = False  # install the page clock before the page loads

    def setUp(self):
        self.context = browser().new_context(viewport=self.viewport)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.held = []
        self.external = []
        self.page_errors = []
        self.context.route("**/*", self._route)
        for script in self.init_scripts:
            self.context.add_init_script(script)
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        if self.clock:
            self.page.clock.install()

    def tearDown(self):
        failed = self._failed()
        for held in self.pending():  # never answered on purpose (for example a timeout test)
            try:
                held.fail()
            except Exception:  # the page may already have given up on it
                pass
        try:
            if failed:
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                stem = ARTIFACTS / self.id().replace(".", "-")
                self.page.screenshot(path=f"{stem}.png", full_page=True)
                self.context.tracing.stop(path=f"{stem}-trace.zip")
            else:
                self.context.tracing.stop()
        finally:
            self.context.close()
        if not failed:
            self.assertEqual(self.page_errors, [], "errors were thrown in the page")
            self.assertEqual(self.external, [], "the page tried to reach the real network")

    def _failed(self):
        result = self._outcome.result
        return any(test is self for test, _ in list(result.errors) + list(result.failures))

    def _route(self, route, request):
        url = request.url
        if url.startswith(ORIGIN + "/static/"):
            path = STATIC / url[len(ORIGIN + "/static/"):].split("?")[0]
            route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": TYPES.get(path.suffix, "application/octet-stream")})
        elif url.startswith(ORIGIN + "/fixtures/"):
            path = FIXTURES / url[len(ORIGIN + "/fixtures/"):].split("?")[0]
            route.fulfill(status=200, body=path.read_bytes(), headers={"Content-Type": TYPES[".html"]})
        elif url.startswith(ORIGIN + "/"):
            self.held.append(Held(route, request))
        else:
            self.external.append(url)
            route.abort("blockedbyclient")

    # --- helpers ----------------------------------------------------------------------------

    def open(self, fixture):
        self.page.goto(f"{ORIGIN}/fixtures/{fixture}")

    def pump(self, seconds=0.02):
        """Let the browser and Playwright exchange events for a moment of real time."""
        self.page.evaluate("0")
        time.sleep(seconds)

    def wait_until(self, condition, timeout=5.0, message="condition"):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return
            self.pump()
        self.fail(f"timed out waiting for {message}")

    def pending(self, path=None):
        return [h for h in self.held if not h.answered and (path is None or h.path.startswith(path))]

    def next_request(self, path=None, timeout=5.0):
        self.wait_until(lambda: self.pending(path), timeout, f"a request to {path or 'erp.test'}")
        return self.pending(path)[0]

    def no_request(self, path=None, seconds=0.5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.pump()
        self.assertEqual([h.path for h in self.pending(path)], [], "unexpected request")
