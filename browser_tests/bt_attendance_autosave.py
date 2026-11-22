"""Attendance autosave in a real browser (ENG-JS-01 JS2, spec section 8.1, cases A2-A5).

The unchanged erp.js and HTMX run against browser_tests/fixtures/attendance.html (rows 201-203 and
the session box). Requests are held until the test answers them with reply fixtures the Django
contract test keeps in step with the real views.

A1 (an older reply must never replace a newer pending change) is not here: it is defect F-JS1,
recorded in GitHub issue #289 with no expected-failure test. JS3 adds A1, shows it failing, and
fixes the attendance block.
"""

from browser_tests.support.autosave import COUNT_SIGNED_OUT, HTML, JSON, form, multipart
from browser_tests.support.page import FixturePage, reply

SAVE = "/attendance/autosave/"
BULK = "/attendance/present/"
SIGNED_OUT_ROW = "Not saved: you have been signed out."
SIGNED_OUT_BOX = "You have been signed out. Anything on this page that was not saved is lost."


class AttendancePage(FixturePage):
    init_scripts = (COUNT_SIGNED_OUT,)

    def row_status(self, pk):
        return " ".join(self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-row-status]').inner_text().split())

    def checked(self, pk):
        return self.page.evaluate(
            f"(document.querySelector('input[name=\"status_{pk}\"]:checked') || {{value: null}}).value")

    def announced(self):
        return self.page.locator("[data-erp-autosave-announce]").text_content().strip()

    def signed_out_events(self):
        return self.page.evaluate("window.signedOutEvents || 0")

    def wait_for_status(self, pk, start):
        self.wait_until(lambda: self.row_status(pk).startswith(start), message=f"row {pk} to say {start!r}")

    def requests_to(self, path):
        return [h for h in self.held if h.path.startswith(path)]

    def assert_session_box_signed_out(self):
        box = self.page.locator("[data-erp-session]")
        say = self.page.locator("[data-erp-session-say]")
        self.wait_until(lambda: box.is_visible() and say.text_content() == SIGNED_OUT_BOX,
                        message="the session box's signed-out state")
        self.assertTrue(self.page.locator("[data-erp-session-login]").is_visible())
        self.assertTrue(self.page.locator("[data-erp-session-stay]").is_hidden())


class BulkPresentTests(AttendancePage):
    def test_a2_mark_unanswered_as_present_never_overwrites_a_choice(self):
        self.open("attendance.html")
        self.page.check("#id_status_201_1")  # Absent
        self.next_request(SAVE).respond(200, reply("attendance_saved.html"), HTML)
        self.page.fill("#id_note_201", "Sick")
        self.page.press("#id_note_201", "Tab")
        self.next_request(SAVE).respond(200, reply("attendance_saved.html"), HTML)
        self.wait_for_status(201, "✓ Saved")
        autosaves = len(self.requests_to(SAVE))

        self.page.click("[data-erp-mark-present]")
        bulk = self.next_request(BULK)
        self.assertEqual(multipart(bulk, "enrollment"), ["202", "203"])
        self.assertEqual(bulk.headers.get("x-requested-with"), "XMLHttpRequest")
        self.assertEqual(bulk.headers.get("x-csrftoken"), "test-token")
        self.assertEqual((self.checked(201), self.page.input_value("#id_note_201")), ("ABSENT", "Sick"))
        self.assertEqual((self.checked(202), self.checked(203)), ("PRESENT", "PRESENT"))
        self.assertEqual(self.row_status(202), "Saving…")

        bulk.respond(200, reply("attendance_bulk_saved.json"), JSON)
        self.wait_for_status(202, "✓ Saved")
        self.wait_for_status(203, "✓ Saved")
        self.assertEqual(self.announced(), "Saved 2 students as present.")
        self.assertEqual((self.checked(201), self.page.input_value("#id_note_201")), ("ABSENT", "Sick"))
        self.no_request()
        self.assertEqual(len(self.requests_to(BULK)), 1, "one request for every bulk-marked row")
        self.assertEqual(len(self.requests_to(SAVE)), autosaves, "no per-row requests for the bulk rows")


class SignedOutTests(AttendancePage):
    def test_a3_a_row_save_answered_401_is_never_shown_as_saved(self):
        self.open("attendance.html")
        self.page.check("#id_status_201_0")  # Present
        self.next_request(SAVE).respond(401, reply("signed_out.json"), JSON)
        self.wait_for_status(201, SIGNED_OUT_ROW)
        self.assertNotIn("Saved", self.row_status(201))
        self.assertEqual(self.announced(), "Could not save Student A. Use Retry or Save draft.")
        self.assertEqual(self.signed_out_events(), 1)
        self.assert_session_box_signed_out()

    def test_a3_bulk_present_answered_401_is_never_shown_as_saved(self):
        self.open("attendance.html")
        self.page.click("[data-erp-mark-present]")
        self.next_request(BULK).respond(401, reply("signed_out.json"), JSON)
        for pk in (201, 202, 203):
            self.wait_for_status(pk, SIGNED_OUT_ROW)
            self.assertNotIn("Saved", self.row_status(pk))
        self.assertEqual(self.announced(), "Could not save. Use Retry or Save draft.")
        self.assertEqual(self.signed_out_events(), 1)
        self.assert_session_box_signed_out()

    def test_a4_typed_values_remain_after_sign_out(self):
        self.open("attendance.html")
        self.page.check("#id_status_201_1")  # Absent
        first = self.next_request(SAVE)
        self.page.fill("#id_note_201", "Fever")
        self.page.press("#id_note_201", "Tab")
        first.respond(401, reply("signed_out.json"), JSON)
        self.wait_until(lambda: len(self.requests_to(SAVE)) == 2, message="the queued note save")
        second = self.requests_to(SAVE)[1]
        self.assertEqual(form(second)["note_201"], "Fever")
        second.respond(401, reply("signed_out.json"), JSON)
        self.wait_for_status(201, SIGNED_OUT_ROW)
        self.assert_session_box_signed_out()
        self.assertEqual((self.checked(201), self.page.input_value("#id_note_201")), ("ABSENT", "Fever"))


class NoJavaScriptAutosaveTests(AttendancePage):
    def test_a5_without_htmx_the_roster_warns_and_sends_nothing(self):
        # As if the vendored HTMX failed to load: the roster falls back to the plain form.
        self.page.route("**/static/vendor/htmx/**", lambda route: route.fulfill(
            status=200, body="/* HTMX did not load */", headers={"Content-Type": "application/javascript"}))
        self.open("attendance.html")
        self.assertIsNone(self.page.evaluate("window.htmx || null"))
        self.page.check("#id_status_201_0")  # Present
        hint = self.page.locator("[data-erp-hint]")
        self.wait_until(lambda: hint.text_content().startswith("Unsaved changes. "), message="the unsaved warning")
        self.assertTrue(self.page.locator("[data-erp-autosave-state]").is_hidden())
        self.assertEqual(self.row_status(201), "")
        self.page.click("[data-erp-mark-present]")
        self.assertEqual((self.checked(202), self.checked(203)), ("PRESENT", "PRESENT"))
        self.assertTrue(self.page.evaluate(
            "(() => { const e = new Event('beforeunload', {cancelable: true});"
            " window.dispatchEvent(e); return e.defaultPrevented; })()"), "leaving would warn")
        self.no_request()
        self.assertEqual(self.held, [])
