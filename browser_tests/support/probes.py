"""Probe tests for the harness self-checks (ENG-JS-01 JS1).

bt_harness.py runs these in a nested suite with its own result object, to prove that the harness
turns page errors, real-network requests and unservable requests into real test failures, saves
diagnostics for a failing test (including one that fails inside a subTest), and isolates storage
between tests. Several probes fail on purpose. This module does not match bt_*.py, so discovery
never runs them on their own, and bt_harness.py imports the module rather than its classes so the
loader does not collect them there either.
"""

from browser_tests.support.page import FixturePage


class PageErrorProbe(FixturePage):
    def test_page_error_left_in_place(self):
        self.open("blank.html")
        self.page.evaluate("setTimeout(() => { throw new Error('bt-probe-error'); }, 0)")
        self.wait_until(lambda: self.page_errors, message="the page error")


class ExternalRequestProbe(FixturePage):
    def test_real_network_request(self):
        self.open("blank.html")
        # Fire and forget: the test ends without waiting, so only tearDown's last round-trip can
        # catch the request.
        self.page.evaluate("fetch('https://example.com/bt-probe').catch(() => 0); 0")


class RouteErrorProbe(FixturePage):
    def test_unservable_request_is_answered_at_once(self):
        self.open("blank.html")
        outcome = self.page.evaluate("fetch('/static/js/bt-missing.js').then(() => 'answered', () => 'failed')")
        self.assertEqual(outcome, "failed")  # aborted at once, not left hanging; tearDown must fail the test


class RouteErrorPumpProbe(FixturePage):
    def test_pump_fails_at_once(self):
        self.open("blank.html")
        self.page.evaluate("fetch('/fixtures/bt-missing.html').then(() => 0, () => 0)")
        self.pump()
        raise AssertionError("bt-probe: pump() did not fail the test")


class FailingProbe(FixturePage):
    def test_fails(self):
        self.open("marks.html")
        self.fail("bt-probe failure")


class SubTestFailingProbe(FixturePage):
    def test_fails_in_a_subtest(self):
        self.open("marks.html")
        with self.subTest(case="bt-probe"):
            self.fail("bt-probe subtest failure")


class IsolationProbe(FixturePage):
    # Run in this order (unittest sorts methods by name).
    def test_1_writes_storage_and_a_cookie(self):
        self.open("blank.html")
        self.page.evaluate("localStorage.setItem('bt-isolation', 'written'); document.cookie = 'bt-isolation=1'")
        self.assertEqual(self.page.evaluate("localStorage.getItem('bt-isolation')"), "written")
        self.assertIn("bt-isolation=1", self.page.evaluate("document.cookie"))

    def test_2_sees_neither(self):
        self.open("blank.html")
        self.assertIsNone(self.page.evaluate("localStorage.getItem('bt-isolation')"))
        self.assertEqual(self.page.evaluate("document.cookie"), "")
