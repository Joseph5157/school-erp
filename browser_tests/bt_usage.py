"""Privacy-safe usage measurement in a real browser (ENG-JS-01 JS4, spec section 8.3, ADR 0027).

The unchanged erp.js runs against fixture pages that carry the measurement attributes the server
renders only when measurement is switched on (pinned to the real pages by the Django contract
test). Measurement stays off by default in the product; these tests only prove what the browser
does when a page says it is on, when it is off, and under Global Privacy Control. Every beacon is
held by the harness and checked against the ADR 0027 allow-list (browser_tests/support/usage.py,
pinned to core/usage.py). Page hide is simulated by the visibilitychange event erp.js listens for.
"""

import re

from browser_tests.support.autosave import FRAGMENT, HTML, JSON
from browser_tests.support.page import FIXTURES, FixturePage, reply
from browser_tests.support.usage import (
    AREAS,
    BEACON,
    CLIENT_EVENTS,
    DEVICES,
    DISPLAYS,
    DURATION_BUCKETS,
    EVENT_KEYS,
    FETCH_SPY,
    GPC_SWITCH,
    MAX_BODY_BYTES,
    MAX_EVENTS,
    PAYLOAD_KEYS,
    PLATFORMS,
    SIZE_BUCKETS,
    events,
    payload,
)

MARKS_SAVE = "/marks/autosave/"
ATTENDANCE_SAVE = "/attendance/autosave/"
ATTENDANCE_BULK = "/attendance/present/"
CLIENT_HEADER = re.compile(r"^device=(phone|tablet|desktop);display=(browser|installed);platform=(android|ios|other)$")
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
# Synthetic people, record ids, typed values and the CSRF token that appear on the fixture pages;
# none may ever reach a beacon. "/" rules out any URL or path.
NEVER_SENT = ("Student", "101", "102", "103", "201", "202", "203", "test-token", "erp.test", "/", "12")


class UsagePage(FixturePage):
    clock = True
    init_scripts = (GPC_SWITCH, FETCH_SPY)

    # --- beacons ----------------------------------------------------------------------------

    def beacons(self):
        return [h for h in self.held if h.path.startswith(BEACON)]

    def next_beacon(self, already):
        self.wait_until(lambda: len(self.beacons()) > already, message="a usage beacon")
        return self.beacons()[already]

    def spied(self):
        """Every fetch the page made to the beacon URL, including ones that never arrived."""
        return [f for f in self.page.evaluate("window.btFetches") if f["url"].endswith(BEACON)]

    def hide(self):
        """The page is hidden (switching app or tab): erp.js flushes on visibilitychange."""
        self.page.evaluate(
            "window.btVisibility = 'hidden';"
            "if (!window.btVisibilityPatched) { window.btVisibilityPatched = true;"
            " Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => window.btVisibility}); }"
            "document.dispatchEvent(new Event('visibilitychange'));"
            "window.btVisibility = 'visible';")

    def drain(self):
        """Answer every open beacon with 204, as the server accepts a valid batch."""
        while self.pending(BEACON):
            for held in self.pending(BEACON):
                held.respond(204)
            self.pump(0.1)

    def flush_all(self, since=0):
        """Hide the page and answer beacons until nothing is left; all events sent since `since`."""
        self.drain()
        self.hide()
        self.pump(0.2)
        self.drain()
        sent = []
        for held in self.beacons()[since:]:
            sent.extend(events(held))
        return sent

    def assert_allowed(self, held):
        """One beacon carries only ADR 0027 values: no person, record, value, URL or free text."""
        body = payload(held)
        self.assertEqual(set(body), PAYLOAD_KEYS)
        self.assertIn(body["d"], DEVICES)
        self.assertIn(body["x"], DISPLAYS)
        self.assertIn(body["p"], PLATFORMS)
        self.assertIn(body["a"], AREAS)
        # Route and area come only from the attributes the server put on <body>.
        page_body = self.page.locator("body")
        self.assertEqual(body["r"], page_body.get_attribute("data-erp-route"))
        self.assertEqual(body["a"], page_body.get_attribute("data-erp-area"))
        self.assertTrue(body["e"])
        for event in body["e"]:
            self.assertLessEqual(set(event), EVENT_KEYS)
            self.assertIn((event["w"], event["s"]), CLIENT_EVENTS)
            if "b" in event:
                self.assertIn(event["b"], DURATION_BUCKETS)
            if "z" in event:
                self.assertIn(event["z"], SIZE_BUCKETS)
        for text in NEVER_SENT:
            self.assertNotIn(text, held.body, f"{text!r} must never be sent")
        self.assertEqual(held.headers.get("content-type"), "application/json")
        self.assertEqual(held.headers.get("x-requested-with"), "XMLHttpRequest")
        self.assertEqual(held.headers.get("x-csrftoken"), "test-token")
        self.assertEqual(held.method, "POST")

    # --- page helpers -----------------------------------------------------------------------

    def enter_score(self, pk, value):
        self.page.fill(f"#id_score_{pk}", value)
        self.page.press(f"#id_score_{pk}", "Tab")

    def row_status(self, pk):
        return " ".join(self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-row-status]').inner_text().split())

    def wait_for_status(self, pk, start):
        self.wait_until(lambda: self.row_status(pk).startswith(start), message=f"row {pk} to say {start!r}")

    def requests_to(self, path):
        return [h for h in self.held if h.path.startswith(path)]

    def next_new(self, path, already):
        self.wait_until(lambda: len(self.requests_to(path)) > already, message=f"a request to {path}")
        return self.requests_to(path)[already]


class OffAndPrivacyControlTests(UsagePage):
    def test_u2_with_measurement_off_nothing_is_ever_sent(self):
        self.open("marks.html")  # no data-erp-usage on <body>
        self.enter_score(101, "12")
        save = self.next_request(MARKS_SAVE)
        self.assertNotIn("x-erp-client", save.headers, "the device header is sent only when measurement is on")
        save.respond(200, reply("marks_saved.html"), FRAGMENT)  # a successful save would flush
        self.hide()
        self.page.clock.run_for(31_000)
        self.no_request(BEACON)
        self.assertEqual(self.spied(), [])

    def test_u1_with_gpc_on_nothing_is_queued_or_sent(self):
        self.context.add_init_script("window.btGpc = true;")
        self.open("usage_marks.html")
        self.enter_score(101, "12")
        save = self.next_request(MARKS_SAVE)
        self.assertNotIn("x-erp-client", save.headers)
        save.respond(200, reply("marks_saved.html"), FRAGMENT)
        self.hide()
        self.page.clock.run_for(31_000)
        self.no_request(BEACON)
        self.assertEqual(self.spied(), [])

    def test_u1_gpc_turned_on_after_queueing_empties_the_queue_without_sending(self):
        self.open("usage.html")  # "page viewed" is queued
        self.page.evaluate("window.btGpc = true")
        self.hide()
        self.no_request(BEACON)
        self.page.evaluate("window.btGpc = false")
        self.hide()
        self.no_request(BEACON)
        self.assertEqual(self.spied(), [], "the queued event was dropped, not kept for later")


class FlushTests(UsagePage):
    def test_u10_the_queue_is_sent_every_30_seconds(self):
        self.page.clock.pause_at(1_800_000_000_000)
        self.open("usage.html")
        self.page.clock.run_for(29_900)
        self.no_request(BEACON, seconds=0.3)
        self.page.clock.run_for(100)
        beacon = self.next_beacon(0)
        self.assertEqual(events(beacon), [("page", "viewed", None, None)])
        self.assert_allowed(beacon)

    def test_page_hide_sends_with_keepalive(self):
        self.open("usage.html")
        self.hide()
        beacon = self.next_beacon(0)
        self.assert_allowed(beacon)
        self.assertEqual([f["keepalive"] for f in self.spied()], [True], "the send must survive the page closing")

    def test_u3_the_queue_keeps_only_the_newest_20_events(self):
        self.open("usage_marks.html")
        expected = [("page", "viewed", None, None), ("marks_entry", "started", None, "1-20")]
        self.fail_on_arrival(MARKS_SAVE)
        self.enter_score(101, "12")
        self.wait_for_status(101, "Not saved: no connection.")
        expected += [("marks_entry", "attempt", None, None), ("marks_entry", "network", None, None)]
        for _ in range(9):
            self.page.click('[data-erp-enrollment="101"] [data-erp-retry]')
            self.wait_for_status(101, "Not saved: no connection.")
            expected += [("marks_entry", s, None, None) for s in ("retry_tapped", "attempt", "network")]
        self.assertEqual(len(expected), 31)
        self.hide()
        beacon = self.next_beacon(0)
        self.assertEqual(events(beacon), expected[-MAX_EVENTS:], "the oldest events are dropped first")
        self.assertLessEqual(len(beacon.body.encode()), MAX_BODY_BYTES, "a full batch fits the server's limit")
        self.assert_allowed(beacon)

    def test_u4_a_lost_send_is_kept_and_sent_at_the_next_moment(self):
        self.open("usage.html")
        self.fail_on_arrival(BEACON)
        self.hide()
        self.wait_until(lambda: len(self.spied()) == 1, message="the first send")
        self.pump(0.2)
        self.assertEqual(self.beacons(), [])
        self.fail_paths.clear()
        self.hide()
        beacon = self.next_beacon(0)
        self.assertEqual(beacon.body, self.spied()[0]["body"], "the same events, sent again")
        self.assert_allowed(beacon)

    def test_u4_a_server_error_keeps_the_events_for_the_next_moment(self):
        self.open("usage.html")
        self.hide()
        first = self.next_beacon(0)
        first.respond(500)
        self.pump(0.2)
        self.hide()
        again = self.next_beacon(1)
        self.assertEqual(events(again), events(first))

    def test_u5_a_refused_batch_is_dropped_and_never_resent(self):
        for status in (400, 401, 403):
            with self.subTest(status=status):
                already = len(self.beacons())
                self.open("usage.html")
                self.hide()
                self.next_beacon(already).respond(status)
                self.pump(0.2)
                self.hide()
                self.page.clock.run_for(31_000)
                self.no_request(BEACON)
                self.assertEqual(len(self.beacons()), already + 1)


class DeviceTests(UsagePage):
    def test_u6_u7_each_event_keeps_its_device_and_each_send_has_one_set(self):
        self.open("usage_marks.html")  # page viewed and marks started at 390 px: phone
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.enter_score(101, "12")  # desktop
        self.assertEqual(self.next_request(MARKS_SAVE).headers.get("x-erp-client"),
                         "device=desktop;display=browser;platform=other")
        self.page.set_viewport_size({"width": 800, "height": 800})
        self.enter_score(102, "14")  # tablet
        self.wait_until(lambda: len(self.requests_to(MARKS_SAVE)) == 2, message="the second save")
        self.assertEqual(self.requests_to(MARKS_SAVE)[1].headers.get("x-erp-client"),
                         "device=tablet;display=browser;platform=other")
        self.hide()
        sends = []
        for index in range(3):
            beacon = self.next_beacon(index)
            self.assert_allowed(beacon)
            sends.append((payload(beacon)["d"], [s for _, s, _, _ in events(beacon)]))
            beacon.respond(204)  # the next device state goes out in its own send
        self.assertEqual(sends, [("phone", ["viewed", "started"]), ("desktop", ["attempt"]), ("tablet", ["attempt"])])

    def test_platform_and_display_android_installed(self):
        self.context.add_init_script(
            f"Object.defineProperty(Navigator.prototype, 'userAgent', {{get: () => {ANDROID!r}}});"
            "Object.defineProperty(Navigator.prototype, 'standalone', {get: () => true});")
        self.open("usage.html")
        self.hide()
        beacon = self.next_beacon(0)
        self.assertEqual((payload(beacon)["p"], payload(beacon)["x"]), ("android", "installed"))
        self.assert_allowed(beacon)
        self.assertNotIn("Pixel", beacon.body, "the user agent itself is never sent")

    def test_platform_iphone_in_the_browser(self):
        self.context.add_init_script(f"Object.defineProperty(Navigator.prototype, 'userAgent', {{get: () => {IPHONE!r}}});")
        self.open("usage.html")
        self.hide()
        beacon = self.next_beacon(0)
        self.assertEqual((payload(beacon)["p"], payload(beacon)["x"]), ("ios", "browser"))
        self.assert_allowed(beacon)


class PersonalDataTests(UsagePage):
    def test_u8_a_beacon_holds_only_allowed_values_and_no_personal_data(self):
        self.open("usage_marks.html")
        self.enter_score(101, "12")
        save = self.next_request(MARKS_SAVE)
        self.assertRegex(save.headers.get("x-erp-client", ""), CLIENT_HEADER)
        self.assertEqual(save.headers.get("x-erp-client"), "device=phone;display=browser;platform=other")
        self.hide()
        beacon = self.next_beacon(0)
        self.assert_allowed(beacon)
        self.assertEqual((payload(beacon)["r"], payload(beacon)["a"]), ("core:assessment-marks-entry", "teacher"))

    def test_u8_a_page_with_a_canary_name_sends_only_its_view(self):
        self.open("usage.html")
        self.assertIn("Student A", self.page.locator("main").inner_text())  # the canary is on the page
        self.hide()
        beacon = self.next_beacon(0)
        self.assert_allowed(beacon)
        self.assertEqual(payload(beacon)["r"], "core:student-list")
        self.assertEqual(events(beacon), [("page", "viewed", None, None)])


class DurationBucketTests(UsagePage):
    BOUNDARIES = ((4_900, "<5s"), (5_000, "5-15s"), (15_000, "15-60s"), (60_000, "1-3m"),
                  (180_000, "3-10m"), (600_000, "10-30m"), (1_800_000, ">30m"))

    def test_u9_teacher_home_completed_carries_the_bucket_of_the_load_time(self):
        self.page.clock.pause_at(1_800_000_000_000)  # only the test moves time
        for millis, bucket in self.BOUNDARIES:
            with self.subTest(seconds=millis / 1000):
                since = len(self.beacons())
                images = len(self.requests_to("/held/"))
                self.page.goto("https://erp.test/fixtures/usage_teacher_home.html", wait_until="domcontentloaded")
                image = self.next_new("/held/", images)  # holds the page's load event
                started_at = self.page.evaluate("performance.now()")
                self.page.clock.run_for(millis - started_at)
                self.drain()  # the 30-second flush may have run meanwhile
                image.respond(200, "", {"Content-Type": "image/png"})
                self.wait_until(lambda: self.page.evaluate("document.readyState") == "complete", message="load")
                sent = self.flush_all(since)
                self.assertEqual([e for e in sent if e[0] == "teacher_home"],
                                 [("teacher_home", "started", None, None), ("teacher_home", "completed", bucket, None)])

    def test_u9_marks_completed_carries_the_bucket_and_size(self):
        self.page.clock.pause_at(1_800_000_000_000)
        for millis, bucket in ((4_900, "<5s"), (5_000, "5-15s"), (1_800_000, ">30m")):
            with self.subTest(seconds=millis / 1000):
                since = len(self.beacons())
                saves = len(self.requests_to(MARKS_SAVE))
                self.open("usage_marks.html")  # the sheet starts timing when it loads
                self.page.clock.run_for(millis)
                self.drain()
                self.enter_score(101, "12")
                self.next_new(MARKS_SAVE, saves).respond(200, reply("marks_saved_last.html"), FRAGMENT)  # 0 left
                sent = self.flush_all(since)
                self.assertEqual([e for e in sent if e[:2] == ("marks_entry", "completed")],
                                 [("marks_entry", "completed", bucket, "1-20")])


class WorkflowTests(UsagePage):
    def completed_bucket(self, sent, workflow):
        buckets = [e[2] for e in sent if e[:2] == (workflow, "completed")]
        self.assertEqual(len(buckets), 1, f"{workflow} completed exactly once")
        self.assertIn(buckets[0], DURATION_BUCKETS)
        return buckets[0]

    def test_missing_attendance_act_completes_once_on_an_action_link(self):
        self.open("usage_missing_attendance.html")
        self.page.click("#other-link")
        self.page.click('a[href="#review"]')
        self.page.click('a[href="#take"]')
        sent = self.flush_all()
        bucket = self.completed_bucket(sent, "missing_attendance_act")
        self.assertEqual(sent, [("page", "viewed", None, None), ("missing_attendance_act", "started", None, None),
                                ("missing_attendance_act", "completed", bucket, None)])
        for beacon in self.beacons():
            self.assert_allowed(beacon)

    def test_marks_entry_starts_with_work_left_and_completes_once(self):
        self.open("usage_marks.html")
        self.enter_score(101, "12")
        self.next_request(MARKS_SAVE).respond(200, reply("marks_saved_last.html"), FRAGMENT)
        self.enter_score(102, "14")
        self.next_new(MARKS_SAVE, 1).respond(200, reply("marks_saved_last.html"), FRAGMENT)
        sent = self.flush_all()
        bucket = self.completed_bucket(sent, "marks_entry")
        self.assertEqual([e for e in sent if e[1] in ("started", "completed")],
                         [("marks_entry", "started", None, "1-20"), ("marks_entry", "completed", bucket, "1-20")])

    def test_a_sheet_with_no_work_left_neither_starts_nor_completes(self):
        # The server leaves out data-erp-usage-size when nothing is left to enter.
        html = (FIXTURES / "usage_marks.html").read_text(encoding="utf-8").replace(' data-erp-usage-size="1-20"', "")
        self.page.route("**/fixtures/usage_marks.html", lambda route: route.fulfill(
            status=200, body=html, headers={"Content-Type": "text/html; charset=utf-8"}))
        self.open("usage_marks.html")
        self.enter_score(101, "12")
        self.next_request(MARKS_SAVE).respond(200, reply("marks_saved_last.html"), FRAGMENT)
        sent = self.flush_all()
        self.assertEqual([e for e in sent if e[1] in ("started", "completed")], [])
        self.assertIn(("marks_entry", "attempt", None, None), sent)

    def test_marks_save_outcomes_are_counted_and_a_success_sends_at_once(self):
        self.open("usage_marks.html")
        self.fail_on_arrival(MARKS_SAVE)
        self.enter_score(101, "12")
        self.wait_for_status(101, "Not saved: no connection.")
        self.fail_paths.clear()
        self.page.click('[data-erp-enrollment="101"] [data-erp-retry]')
        self.next_request(MARKS_SAVE).respond(200, reply("marks_saved.html"), FRAGMENT)
        # A successful save sends the queue straight away, so failures seen offline go out now.
        first = self.next_beacon(0)
        self.assertIn(("marks_entry", "network", None, None), events(first))
        first.respond(204)
        saves = len(self.requests_to(MARKS_SAVE))
        self.enter_score(102, "14")
        self.next_new(MARKS_SAVE, saves).respond(500, "Server error", HTML)
        self.wait_for_status(102, "Not saved.")
        self.enter_score(103, "15")
        self.next_new(MARKS_SAVE, saves + 1).respond(403, "Forbidden", HTML)
        self.wait_for_status(103, "Not saved: the page has expired.")
        self.page.click("[data-erp-save-fallback]")
        sent = self.flush_all()
        steps = {s for w, s, _, _ in sent if w == "marks_entry"}
        self.assertLessEqual({"attempt", "network", "retry_tapped", "retry_succeeded", "server", "csrf",
                              "fallback_save_used"}, steps)
        for beacon in self.beacons():
            self.assert_allowed(beacon)

    def test_attendance_save_outcomes_are_counted_and_a_success_sends_at_once(self):
        self.open("usage_attendance.html")
        self.fail_on_arrival(ATTENDANCE_SAVE)
        self.page.check("#id_status_201_0")
        self.wait_for_status(201, "Not saved.")
        self.fail_paths.clear()
        self.page.click('[data-erp-enrollment="201"] [data-erp-retry]')
        self.next_request(ATTENDANCE_SAVE).respond(200, reply("attendance_saved.html"), HTML)
        first = self.next_beacon(0)
        self.assertIn(("attendance_capture", "network", None, None), events(first))
        first.respond(204)
        saves = len(self.requests_to(ATTENDANCE_SAVE))
        self.page.check("#id_status_202_0")
        self.next_new(ATTENDANCE_SAVE, saves).respond(500, "Server error", HTML)
        self.wait_for_status(202, "Not saved.")
        self.page.click("[data-erp-mark-present]")  # row 203: one bulk request
        self.next_request(ATTENDANCE_BULK).respond(200, reply("attendance_bulk_saved.json"), JSON)
        sent = self.flush_all()
        steps = [s for w, s, _, _ in sent if w == "attendance_capture"]
        self.assertLessEqual({"attempt", "network", "retry_tapped", "retry_succeeded", "server"}, set(steps))
        self.assertEqual(steps.count("attempt"), 4, "row 201 twice, row 202, and one for the bulk request")
        for beacon in self.beacons():
            self.assert_allowed(beacon)


class InstallTests(UsagePage):
    def offer_install(self, outcome="accepted"):
        """The browser offers an install (Chrome's beforeinstallprompt), with the given user choice."""
        self.page.evaluate(
            "outcome => { window.btPrompted = 0; const e = new Event('beforeinstallprompt', {cancelable: true});"
            " e.prompt = () => { window.btPrompted += 1; };"
            " e.userChoice = Promise.resolve({outcome: outcome}); window.dispatchEvent(e); }", outcome)

    def install_events(self, sent):
        return [s for w, s, _, _ in sent if w == "install"]

    def test_the_bar_is_counted_as_shown_once_per_page_view(self):
        self.open("usage_install.html")
        self.offer_install()
        bar = self.page.locator("[data-erp-install-bar]")
        self.assertTrue(bar.is_visible())
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.wait_until(lambda: bar.is_hidden(), message="the bar to hide on a wide screen")
        self.page.set_viewport_size({"width": 390, "height": 800})
        self.wait_until(lambda: bar.is_visible(), message="the bar to come back on a phone")
        self.assertEqual(self.install_events(self.flush_all()), ["shown"])

    def test_not_now_is_a_dismissal_and_never_an_installation(self):
        self.open("usage_install.html")
        self.offer_install()
        self.page.click("[data-erp-install-bar-dismiss]")
        self.assertTrue(self.page.locator("[data-erp-install-bar]").is_hidden())
        self.assertEqual(self.install_events(self.flush_all()), ["shown", "dismissed"])

    def test_cancelling_the_browser_prompt_is_not_counted(self):
        self.open("usage_install.html")
        self.offer_install("dismissed")
        self.page.click("[data-erp-install-bar-install]")
        self.assertEqual(self.page.evaluate("window.btPrompted"), 1)
        self.assertEqual(self.install_events(self.flush_all()), ["shown"])

    def test_installed_comes_only_from_appinstalled_and_is_sent_at_once(self):
        self.open("usage_install.html")
        self.offer_install("accepted")
        self.page.click("[data-erp-install-bar-install]")  # accepting the prompt is not yet an installation
        self.assertEqual(self.install_events(self.flush_all()), ["shown"])
        already = len(self.beacons())
        self.page.evaluate("window.dispatchEvent(new Event('appinstalled'))")
        beacon = self.next_beacon(already)  # sent without waiting for a flush moment
        self.assertEqual(self.install_events(events(beacon)), ["installed"])
        self.assert_allowed(beacon)
