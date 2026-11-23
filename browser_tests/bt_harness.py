"""Self-checks for the browser fixture harness (ENG-JS-01 JS1, spec sections 7.2 and 8.1).

These prove the harness itself: the page clock, request control, error and network guards,
diagnostics, and that every fixture page loads the real scripts cleanly. EnforcementTests runs the
probes in browser_tests/support/probes.py in a nested suite, to prove that tearDown really fails a
test on a page error, a real-network request or an unservable request, that a failing test saves
its diagnostics, and that tests are isolated. Marks, attendance and measurement behaviour tests
arrive in later PRs (JS2, JS4).
"""

import hashlib
import json
import pathlib
import tempfile
import unittest

from browser_tests.support import probes
from browser_tests.support.page import STATIC, FixturePage

FIXTURE_PAGES = ("marks.html", "attendance.html", "usage.html", "sidebar.html", "blank.html")


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
        # erp.js ran: it reveals the roster filter tabs and the sidebar button, which start hidden.
        for fixture, hidden_until_erp_js in (("marks.html", "[data-erp-tabs]"),
                                             ("attendance.html", "[data-erp-tabs]"),
                                             ("sidebar.html", "[data-erp-sidebar-toggle]")):
            self.open(fixture)
            self.wait_until(lambda selector=hidden_until_erp_js: self.page.locator(selector).is_visible(),
                            message=f"erp.js to run on {fixture}")


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


class XhrTimeoutClockTests(FixturePage):
    clock = True
    xhr_timeouts_on_page_clock = True

    def test_an_xhr_timeout_runs_on_the_page_clock(self):
        self.open("blank.html")
        # Paused, so real time spent waiting for the request cannot move the page clock.
        self.page.clock.pause_at(self.page.evaluate("Date.now()") + 1000)
        self.page.evaluate(
            "window.seen = []; const x = new XMLHttpRequest(); x.open('POST', '/held/t'); x.timeout = 15000;"
            "['timeout', 'abort', 'load', 'error', 'loadend'].forEach(n => x.addEventListener(n, () => window.seen.push(n)));"
            "x.onabort = () => window.seen.push('onabort'); x.ontimeout = () => window.seen.push('ontimeout');"
            "x.send('a');")
        held = self.next_request("/held/")
        self.page.clock.run_for(14_999)
        self.pump(0.1)
        self.assertEqual(self.page.evaluate("window.seen"), [])
        self.page.clock.run_for(2)
        self.wait_until(lambda: "loadend" in self.page.evaluate("window.seen"), message="the timeout")
        # As a browser reports a timeout: timeout (listener, then handler), then loadend; no abort.
        self.assertEqual(self.page.evaluate("window.seen"), ["timeout", "ontimeout", "loadend"])
        self.wait_until(lambda: held.closed, message="the request to be closed")
        self.assertEqual(self.pending("/held/"), [])


class RequestControlTests(FixturePage):
    def test_answering_a_request_the_page_already_closed_fails_clearly(self):
        self.open("blank.html")
        self.page.evaluate("window.x = new XMLHttpRequest(); x.open('POST', '/held/c'); x.send('a');")
        held = self.next_request("/held/")
        self.page.evaluate("x.abort()")
        with self.assertRaisesRegex(AssertionError, "had already closed POST /held/c"):
            held.respond(200, "too late")
        self.assertFalse(held.answered)


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
            records = json.loads((stem.parent / "diagnostics-records.json").read_text(encoding="utf-8"))
            self.assertEqual(set(records), {"page_errors", "external_requests", "route_errors", "guard_violations",
                                            "held_requests"})
        self.context.tracing.start(screenshots=True, snapshots=True)  # tearDown stops it again


class EnforcementTests(unittest.TestCase):
    """Runs probe tests in a nested suite and checks the outcome the harness gave them."""

    def run_probes(self, case):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.artifacts = pathlib.Path(folder.name)
        case.artifacts = self.artifacts
        self.addCleanup(delattr, case, "artifacts")  # back to FixturePage.artifacts
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(case).run(result)
        return result

    def only_failure(self, result):
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.failures), 1, result.failures)
        return result.failures[0][1]

    def records(self, case_name):
        found = list(self.artifacts.glob(f"*{case_name}-test_*-records.json"))
        self.assertEqual(len(found), 1, sorted(p.name for p in self.artifacts.iterdir()))
        return json.loads(found[0].read_text(encoding="utf-8"))

    def assert_diagnostics_saved(self, case_name):
        for suffix in (".png", "-trace.zip"):
            found = list(self.artifacts.glob(f"*{case_name}-test_*{suffix}"))
            self.assertEqual(len(found), 1, f"{case_name}{suffix}")
            self.assertGreater(found[0].stat().st_size, 0)

    def test_a_page_error_fails_the_test_and_is_in_the_diagnostics(self):
        traceback = self.only_failure(self.run_probes(probes.PageErrorProbe))
        self.assertIn("errors were thrown in the page", traceback)
        self.assertIn("bt-probe-error", " ".join(self.records("PageErrorProbe")["page_errors"]))
        self.assert_diagnostics_saved("PageErrorProbe")

    def test_a_real_network_request_fails_the_test_and_is_in_the_diagnostics(self):
        traceback = self.only_failure(self.run_probes(probes.ExternalRequestProbe))
        self.assertIn("the page tried to reach the real network", traceback)
        self.assertEqual(self.records("ExternalRequestProbe")["external_requests"], ["https://example.com/bt-probe"])

    def test_a_request_the_harness_cannot_serve_is_aborted_and_fails_the_test(self):
        # The probe's own assertion shows the request was aborted at once; tearDown then fails it.
        traceback = self.only_failure(self.run_probes(probes.RouteErrorProbe))
        self.assertIn("the harness could not serve a request", traceback)
        self.assertIn("bt-missing.js", " ".join(self.records("RouteErrorProbe")["route_errors"]))
        # pump() fails the test as soon as it runs, before the test can carry on.
        traceback = self.only_failure(self.run_probes(probes.RouteErrorPumpProbe))
        self.assertIn("the harness could not serve a request", traceback)
        self.assertNotIn("pump() did not fail the test", traceback)

    def test_a_teardown_guard_violation_fails_the_test_and_is_in_the_diagnostics(self):
        traceback = self.only_failure(self.run_probes(probes.GuardViolationProbe))
        self.assertIn("a tearDown guard check failed", traceback)
        self.assertEqual(self.records("GuardViolationProbe")["guard_violations"], ["bt-probe violation"])
        self.assert_diagnostics_saved("GuardViolationProbe")

    def test_a_failing_test_saves_a_screenshot_trace_and_records(self):
        self.assertIn("bt-probe failure", self.only_failure(self.run_probes(probes.FailingProbe)))
        self.assert_diagnostics_saved("FailingProbe")
        self.records("FailingProbe")

    def test_a_failure_inside_a_subtest_also_saves_diagnostics(self):
        self.assertIn("bt-probe subtest failure", self.only_failure(self.run_probes(probes.SubTestFailingProbe)))
        self.assert_diagnostics_saved("SubTestFailingProbe")

    def test_storage_and_cookies_do_not_leak_between_tests(self):
        result = self.run_probes(probes.IsolationProbe)
        self.assertEqual(result.testsRun, 2)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
