"""Self-checks for the browser fixture harness (ENG-JS-01 JS1, spec sections 7.2 and 8.1).

These prove the harness itself: isolation, the page clock, request control, error and network
guards, diagnostics, and that every fixture page loads the real scripts cleanly. Marks,
attendance and measurement behaviour tests arrive in later PRs (JS2, JS4).
"""

import hashlib
import pathlib
import tempfile

from browser_tests.support.page import STATIC, FixturePage

FIXTURE_PAGES = ("marks.html", "attendance.html", "usage.html", "sidebar.html", "blank.html")


class IsolationTests(FixturePage):
    def test_1_storage_written_in_one_test(self):
        self.open("blank.html")
        self.page.evaluate("localStorage.setItem('bt-isolation', 'written')")
        self.assertEqual(self.page.evaluate("localStorage.getItem('bt-isolation')"), "written")

    def test_2_is_absent_in_the_next_test(self):
        self.open("blank.html")
        self.assertIsNone(self.page.evaluate("localStorage.getItem('bt-isolation')"))


class ServedFilesTests(FixturePage):
    def test_erp_js_and_htmx_are_served_byte_for_byte(self):
        self.open("blank.html")
        for path in ("js/erp.js", "vendor/htmx/2.0.4/htmx.min.js"):
            served = self.page.evaluate(
                "path => fetch('/static/' + path).then(r => r.arrayBuffer())"
                ".then(b => crypto.subtle.digest('SHA-256', b))"
                ".then(d => Array.from(new Uint8Array(d)).map(x => x.toString(16).padStart(2, '0')).join(''))",
                path,
            )
            self.assertEqual(served, hashlib.sha256((STATIC / path).read_bytes()).hexdigest(), path)

    def test_every_fixture_page_loads_the_real_scripts_without_errors(self):
        for fixture in FIXTURE_PAGES:
            with self.subTest(fixture=fixture):
                self.open(fixture)
                self.pump(0.1)
                self.assertEqual(self.page_errors, [], fixture)
        # erp.js ran on the roster pages: it reveals the filter tabs that start hidden.
        for fixture in ("marks.html", "attendance.html"):
            self.open(fixture)
            self.assertFalse(self.page.locator("[data-erp-tabs]").is_hidden(), fixture)


class ClockTests(FixturePage):
    clock = True

    def test_the_page_clock_controls_page_timers(self):
        self.open("blank.html")
        self.page.evaluate("window.fired = false; setTimeout(() => { window.fired = true; }, 30000)")
        self.page.clock.run_for(29_000)
        self.assertFalse(self.page.evaluate("window.fired"))
        self.page.clock.run_for(1_500)
        self.assertTrue(self.page.evaluate("window.fired"))

    def test_the_clock_is_installed_before_erp_js_starts_its_interval(self):
        self.open("usage.html")
        self.page.clock.run_for(29_000)
        self.no_request("/u/")
        self.page.clock.run_for(1_500)
        self.next_request("/u/").respond(204)


class RequestControlTests(FixturePage):
    def test_held_requests_are_answered_later_and_in_any_order(self):
        self.open("blank.html")
        self.page.evaluate(
            "window.order = [];"
            "['a', 'b'].forEach(n => fetch('/held/' + n).then(r => r.text()).then(t => window.order.push(t)));"
        )
        self.wait_until(lambda: len(self.pending("/held/")) == 2, message="two held requests")
        first, second = self.pending("/held/")
        self.pump(0.2)
        self.assertEqual(self.page.evaluate("window.order"), [])
        second.respond(200, second.path[-1])
        first.respond(200, first.path[-1])
        self.wait_until(lambda: len(self.page.evaluate("window.order")) == 2, message="both replies")
        self.assertEqual(self.page.evaluate("window.order"), ["b", "a"])

    def test_a_failed_request_reaches_the_page_as_a_network_error(self):
        self.open("blank.html")
        self.fail_on_arrival("/offline/")
        outcome = self.page.evaluate("fetch('/offline/x').then(() => 'ok', () => 'network')")
        self.assertEqual(outcome, "network")
        self.assertEqual(self.held, [])


class GuardTests(FixturePage):
    def test_a_page_error_is_collected(self):
        self.open("blank.html")
        self.page.evaluate("setTimeout(() => { throw new Error('bt-self-check'); }, 0)")
        self.wait_until(lambda: self.page_errors, message="the page error")
        self.assertIn("bt-self-check", self.page_errors[0])
        self.page_errors.clear()  # expected here; any other test fails on it in tearDown

    def test_a_real_network_request_is_blocked_and_recorded(self):
        self.open("blank.html")
        outcome = self.page.evaluate("fetch('https://example.com/x').then(() => 'reached', () => 'blocked')")
        self.assertEqual(outcome, "blocked")
        self.assertEqual(self.external, ["https://example.com/x"])
        self.external.clear()  # expected here; any other test fails on it in tearDown


class DiagnosticsTests(FixturePage):
    def test_a_screenshot_and_trace_are_saved(self):
        self.open("marks.html")
        with tempfile.TemporaryDirectory() as folder:
            stem = pathlib.Path(folder) / "diagnostics"
            self.save_diagnostics(stem)
            self.assertGreater((stem.parent / "diagnostics.png").stat().st_size, 0)
            self.assertGreater((stem.parent / "diagnostics-trace.zip").stat().st_size, 0)
        self.context.tracing.start(screenshots=True, snapshots=True)  # tearDown stops it again
