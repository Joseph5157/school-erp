"""ENG-JS-01 JS1 spike: proves the spec section 7.1 pass conditions. SPIKE ONLY, not for merge as is."""

import json
import os
from urllib.parse import parse_qs

from browser_tests.support.page import FixturePage

FRAGMENT = {"Content-Type": "text/html; charset=utf-8", "X-ERP-Row-Fragment": "1"}


def form(held):
    return {k: v[0] for k, v in parse_qs(held.body, keep_blank_values=True).items()}


def marks_saved(pk, score):
    return (
        f'<span class="erp-row-saved">&#10003; Saved<span class="visually-hidden"> Student</span></span>\n'
        f'<span id="erp-base-{pk}" hx-swap-oob="true"><input type="hidden" name="base_status_{pk}" value="MARKED">'
        f'<input type="hidden" name="base_score_{pk}" value="{score}"></span>'
    )


class MarksSpike(FixturePage):
    def status(self, pk):
        return self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-row-status]').inner_text()

    def test_c1_leaving_the_score_fires_change_and_saves_only_that_row(self):
        self.open("marks.html")
        self.page.fill("#id_score_101", "12")
        self.page.keyboard.press("Tab")
        held = self.next_request("/marks/autosave/")
        sent = form(held)
        self.assertEqual(sent["score_101"], "12")
        self.assertEqual(sent["status_101"], "MARKED")
        self.assertEqual(sent["base_status_101"], "")
        self.assertFalse([k for k in sent if k.endswith("_102") or k.endswith("_103")], sent)
        held.respond(200, marks_saved(101, "12"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(101), message="Saved")
        self.assertEqual(self.page.input_value('input[name="base_score_101"]'), "12")

    def test_c1_next_moves_to_the_next_student_and_saves_the_row_left(self):
        self.open("marks.html")
        self.page.fill("#id_score_101", "7")
        self.page.keyboard.press("Enter")
        held = self.next_request("/marks/autosave/")
        self.assertEqual(form(held)["score_101"], "7")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_score_102")
        held.respond(200, marks_saved(101, "7"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(101), message="Saved")

    def test_c2_replies_for_two_rows_answered_in_reverse_order(self):
        self.open("marks.html")
        self.page.fill("#id_score_101", "10")
        self.page.keyboard.press("Tab")
        self.page.fill("#id_score_102", "11")
        self.page.keyboard.press("Tab")
        self.wait_until(lambda: len(self.pending("/marks/autosave/")) == 2, message="two requests")
        first, second = self.pending("/marks/autosave/")
        self.assertIn("score_101", form(first))
        second.respond(200, marks_saved(102, "11"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(102), message="row 102 saved")
        self.assertIn("Saving", self.status(101))
        first.respond(200, marks_saved(101, "10"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(101), message="row 101 saved")

    def test_c2_an_older_reply_never_marks_a_newer_change_saved(self):
        self.open("marks.html")
        self.page.fill("#id_score_101", "5")
        self.page.keyboard.press("Tab")
        older = self.next_request("/marks/autosave/")
        self.page.fill("#id_score_101", "6")
        self.page.keyboard.press("Tab")
        self.pump(0.2)
        self.assertEqual(len(self.pending("/marks/autosave/")), 1)  # the newer change waits (queue last)
        older.respond(200, marks_saved(101, "5"), FRAGMENT)
        newer = self.next_request("/marks/autosave/")
        self.assertIn("Saving", self.status(101))
        sent = form(newer)
        self.assertEqual((sent["score_101"], sent["base_status_101"], sent["base_score_101"]), ("6", "MARKED", "5"))
        newer.respond(200, marks_saved(101, "6"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(101), message="Saved")

    def test_c3_request_timeout_shows_no_connection_and_retry_keeps_the_base(self):
        self.open("marks.html")  # row 103 has the fixture-only 600 ms timeout
        self.page.fill("#id_score_103", "9")
        self.page.keyboard.press("Tab")
        self.next_request("/marks/autosave/")  # never answered
        self.wait_until(lambda: "no connection" in self.status(103), timeout=4, message="timeout")
        self.page.click('[data-erp-enrollment="103"] [data-erp-retry]')
        self.wait_until(lambda: len(self.held) == 2, message="retry request")
        retry = self.held[-1]
        sent = form(retry)
        self.assertEqual((sent["score_103"], sent["base_status_103"], sent["base_score_103"]), ("9", "", ""))
        retry.respond(200, marks_saved(103, "9"), FRAGMENT)
        self.wait_until(lambda: "Saved" in self.status(103), message="Saved")


class AttendanceSpike(FixturePage):
    def status(self, pk):
        return self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-row-status]').inner_text()

    def test_c2_fetch_and_xhr_held_then_answered_out_of_order(self):
        self.open("attendance.html")
        self.page.check("#id_status_201_1")  # Absent: one HTMX XHR
        xhr = self.next_request("/attendance/autosave/")
        self.page.click("[data-erp-mark-present]")  # the other two rows: one fetch
        bulk = self.next_request("/attendance/present/")
        self.assertIn("Saving", self.status(202))
        bulk.respond(200, "{}", {"Content-Type": "application/json"})
        self.wait_until(lambda: "Saved" in self.status(203), message="bulk saved")
        self.assertIn("Saving", self.status(201))
        self.assertTrue(self.page.is_checked("#id_status_201_1"))  # never overrides a choice
        xhr.respond(200, '<span class="erp-row-saved">&#10003; Saved</span>', {"Content-Type": "text/html"})
        self.wait_until(lambda: "Saved" in self.status(201), message="row saved")


HIDE = (
    "Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});"
    "document.dispatchEvent(new Event('visibilitychange'));"
)


class UsageSpike(FixturePage):
    clock = True

    def test_c3_the_30_second_flush_follows_the_page_clock(self):
        self.open("usage.html")
        self.page.clock.run_for(29_000)
        self.no_request("/u/")
        self.page.clock.run_for(1_500)
        beacon = self.next_request("/u/")
        payload = json.loads(beacon.body)
        self.assertEqual(sorted(payload), ["a", "d", "e", "p", "r", "x"])
        self.assertNotIn("Student A", beacon.body)
        self.assertEqual(beacon.headers.get("x-requested-with"), "XMLHttpRequest")
        beacon.respond(204)

    def test_c4_page_hide_sends_the_keepalive_flush(self):
        self.open("usage.html")
        self.page.evaluate(HIDE)
        beacon = self.next_request("/u/")
        self.assertEqual(json.loads(beacon.body)["e"][0], {"w": "page", "s": "viewed"})
        beacon.respond(204)


class GpcSpike(FixturePage):
    clock = True
    init_scripts = ("Object.defineProperty(navigator, 'globalPrivacyControl', {get: () => true});",)

    def test_c4_global_privacy_control_sends_nothing(self):
        self.open("usage.html")
        self.page.clock.run_for(31_000)
        self.page.evaluate(HIDE)
        self.no_request("/u/")


class StorageFailureSpike(FixturePage):
    init_scripts = (
        "Storage.prototype.getItem = function () { throw new Error('blocked'); };"
        "Storage.prototype.setItem = function () { throw new Error('blocked'); };",
    )

    def test_c4_blocked_storage_never_breaks_the_page(self):
        self.open("sidebar.html")
        self.page.click("[data-erp-sidebar-toggle]")
        self.assertTrue(self.page.evaluate("document.documentElement.classList.contains('erp-nav-collapsed')"))
        self.page.click("summary")  # the nav group toggle also writes storage


class StorageIsolationSpike(FixturePage):
    def test_1_storage_written_in_one_test(self):
        self.open("sidebar.html")
        self.page.click("[data-erp-sidebar-toggle]")
        self.assertEqual(self.page.evaluate("localStorage.getItem('erp.nav.collapsed')"), "1")

    def test_2_is_absent_in_the_next(self):
        self.open("sidebar.html")
        self.assertIsNone(self.page.evaluate("localStorage.getItem('erp.nav.collapsed')"))


class NetworkSpike(FixturePage):
    def test_c6_a_real_network_request_is_blocked_and_recorded(self):
        self.open("sidebar.html")
        outcome = self.page.evaluate("fetch('https://example.com/x').then(() => 'reached', () => 'blocked')")
        self.assertEqual(outcome, "blocked")
        self.assertEqual(self.external, ["https://example.com/x"])
        self.external.clear()  # expected here; any other test fails on it in tearDown


class DiagnosticsSpike(FixturePage):
    def test_c8_forced_failure_saves_trace_and_screenshot(self):
        if os.environ.get("BT_SPIKE_FORCE_FAIL") != "1":
            return
        self.open("marks.html")
        self.fail("forced failure to prove diagnostics")
