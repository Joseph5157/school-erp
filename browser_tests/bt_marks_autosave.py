"""Marks autosave in a real browser (ENG-JS-01 JS2, spec section 8.1, cases M1-M9).

The unchanged erp.js and HTMX run against browser_tests/fixtures/marks.html (rows 101-103; row 103
has the documented 600 ms timeout). Every autosave request is held until the test answers it, with
reply fixtures the Django contract test keeps in step with the real view. The server half of each
case is covered by core/tests/test_marks_autosave.py.
"""

from browser_tests.support.autosave import COUNT_SIGNED_OUT, FRAGMENT, HTML, JSON, form
from browser_tests.support.page import FixturePage, reply

SAVE = "/marks/autosave/"
NEEDS_SCORE = "Enter a score or choose Absent."


class MarksPage(FixturePage):
    init_scripts = (COUNT_SIGNED_OUT,)

    def setUp(self):
        super().setUp()
        self.open("marks.html")

    # --- what the teacher sees --------------------------------------------------------------

    def row_status(self, pk):
        return " ".join(self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-row-status]').inner_text().split())

    def has_retry(self, pk):
        return self.page.locator(f'[data-erp-enrollment="{pk}"] [data-erp-retry]').count() == 1

    def page_line(self):
        return self.page.locator("[data-erp-autosave-state]").inner_text().strip()

    def announced(self):
        return self.page.locator("[data-erp-autosave-announce]").text_content().strip()

    def signed_out_events(self):
        return self.page.evaluate("window.signedOutEvents || 0")

    def wait_for_status(self, pk, start):
        self.wait_until(lambda: self.row_status(pk).startswith(start), message=f"row {pk} to say {start!r}")

    # --- what the teacher does --------------------------------------------------------------

    def enter_score(self, pk, value):
        """Type a score and leave the box, so the browser fires `change`."""
        self.page.fill(f"#id_score_{pk}", value)
        self.page.press(f"#id_score_{pk}", "Tab")

    def saves(self):
        return self.pending(SAVE)

    def sent(self):
        return len([h for h in self.held if h.path.startswith(SAVE)])

    def new_save(self, already):
        """The next autosave request beyond the `already` ones seen."""
        self.wait_until(lambda: self.sent() > already, message="a new autosave request")
        return [h for h in self.held if h.path.startswith(SAVE)][already]

    def fail_101(self):
        """Row 101 fails with no connection (a network error made on arrival)."""
        self.fail_on_arrival(SAVE)
        self.enter_score(101, "12")
        self.wait_for_status(101, "Not saved: no connection.")
        self.fail_paths.clear()


class OlderReplyTests(MarksPage):
    def change_twice_and_answer_the_first(self):
        self.enter_score(101, "12")
        first = self.next_request(SAVE)
        self.assertEqual(form(first)["score_101"], "12")
        self.enter_score(101, "13")
        self.pump(0.2)
        self.assertEqual(len(self.saves()), 1, "the newer change waits for the first reply (queue last)")
        first.respond(200, reply("marks_saved.html"), FRAGMENT)
        second = self.new_save(1)
        self.assertEqual(form(second)["score_101"], "13")
        return second

    def test_m1_an_older_reply_cannot_overwrite_a_newer_edit(self):
        second = self.change_twice_and_answer_the_first()
        self.assertEqual(self.row_status(101), "Saving…")
        self.assertNotEqual(self.announced(), "Saved Student A.")
        second.respond(200, reply("marks_saved.html"), FRAGMENT)
        self.wait_for_status(101, "✓ Saved")
        self.assertEqual(self.announced(), "Saved Student A.")

    def test_m2_the_page_line_says_saving_while_a_newer_request_is_active(self):
        self.assertEqual(self.page_line(), "Changes save automatically")
        second = self.change_twice_and_answer_the_first()
        self.assertEqual(self.page_line(), "Saving…")
        second.respond(200, reply("marks_saved.html"), FRAGMENT)
        self.wait_until(lambda: self.page_line() == "All changes saved", message="All changes saved")


class LostReplyTests(MarksPage):
    def test_m3_a_lost_reply_offers_retry_which_resends_the_original_base(self):
        self.enter_score(103, "9")  # row 103 times out after 600 ms
        lost = self.next_request(SAVE)
        self.assertEqual((form(lost)["base_status_103"], form(lost)["base_score_103"]), ("", ""))
        self.wait_for_status(103, "Not saved: no connection.")
        self.assertTrue(self.has_retry(103))
        self.page.click('[data-erp-enrollment="103"] [data-erp-retry]')
        retry = self.new_save(1)
        body = form(retry)
        # The base is still the value the page last saw confirmed, so the server can tell a
        # repeat of the lost save from a real conflict.
        self.assertEqual((body["status_103"], body["score_103"]), ("MARKED", "9"))
        self.assertEqual((body["base_status_103"], body["base_score_103"]), ("", ""))
        retry.respond(204)


class FailureStateTests(MarksPage):
    def answer_101(self, status, body="", headers=None):
        already = self.sent()  # requests held from an earlier page load are not this one
        self.open("marks.html")
        self.enter_score(101, "12")
        self.new_save(already).respond(status, body, headers or HTML)

    def assert_failed(self, pk, text, retry):
        self.wait_for_status(pk, text)
        self.assertEqual(self.has_retry(pk), retry, f"Retry offered: {text}")
        self.assertIn("is-unsaved", self.page.locator(f'[data-erp-enrollment="{pk}"]').get_attribute("class"))
        self.assertEqual(self.page_line(), "Changes not saved (1)")

    def test_m4_each_failure_has_its_own_words_and_only_some_offer_retry(self):
        with self.subTest("network"):
            self.fail_101()
            self.assert_failed(101, "Not saved: no connection.", retry=True)
        with self.subTest("timeout"):
            self.open("marks.html")
            self.enter_score(103, "9")
            self.assert_failed(103, "Not saved: no connection.", retry=True)
        with self.subTest("500"):
            self.answer_101(500, "Server error")
            self.assert_failed(101, "Not saved.", retry=True)
            # The visually hidden parts name the row for screen readers (no CSS in fixtures).
            self.assertEqual(self.row_status(101), "Not saved. Student A Retry saving Student A")
        with self.subTest("422 fragment"):
            self.answer_101(422, reply("marks_refused.html"), FRAGMENT)
            self.assert_failed(101, "Not saved: Ensure this value is less than or equal to 20.", retry=False)
        with self.subTest("409 conflict fragment"):
            self.answer_101(409, reply("marks_conflict.html"), FRAGMENT)
            self.assert_failed(101, "Changed on another device to 12.", retry=False)
            self.assertEqual(self.page.locator("[data-erp-use-mine], [data-erp-keep-theirs]").count(), 2)
        with self.subTest("403 fragment"):
            self.answer_101(403, reply("marks_forbidden.html"), FRAGMENT)
            self.assert_failed(101, "Not saved: You can no longer enter marks for this assessment.", retry=False)
        with self.subTest("403 without the fragment header (CSRF)"):
            self.answer_101(403, "Forbidden")
            self.assert_failed(101, "Not saved: the page has expired. Reload the page.", retry=False)
            self.assertEqual(self.signed_out_events(), 0)
        with self.subTest("401"):
            self.answer_101(401, reply("signed_out.json"), JSON)
            self.assert_failed(101, "Not saved: you have been signed out.", retry=False)
            self.assertEqual(self.signed_out_events(), 1, "only a 401 reports a sign-out")

    def test_m4_the_connection_coming_back_changes_only_the_words(self):
        self.fail_101()
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.wait_for_status(101, "Connection is back. Tap Retry.")
        self.assertTrue(self.has_retry(101))
        self.no_request(SAVE)


class RetryTests(MarksPage):
    def test_m5_retry_resends_only_the_affected_row_with_its_base(self):
        self.fail_on_arrival(SAVE)
        self.enter_score(101, "12")
        self.enter_score(102, "14")
        self.wait_for_status(101, "Not saved: no connection.")
        self.wait_for_status(102, "Not saved: no connection.")
        self.assertEqual(self.page_line(), "Changes not saved (2)")
        self.fail_paths.clear()
        self.page.click('[data-erp-enrollment="102"] [data-erp-retry]')
        retry = self.next_request(SAVE)
        self.assertEqual(form(retry), {"enrollment": "102", "status_102": "MARKED", "score_102": "14",
                                       "base_status_102": "", "base_score_102": ""})
        retry.respond(204)
        self.no_request(SAVE)
        self.assertTrue(self.has_retry(101), "the other row still waits for its own Retry")


class FallbackTests(MarksPage):
    def test_m6_the_fallback_never_submits_the_whole_form(self):
        self.assertTrue(self.page.locator("[data-erp-save-fallback]").is_hidden())
        self.page.evaluate("window.stillHere = true; document.querySelector('form').requestSubmit()")
        self.pump(0.3)
        self.assertTrue(self.page.evaluate("window.stillHere === true"), "the form must not be posted")
        self.assertEqual(self.held, [])
        # One row lost its connection, two have conflicts: Save draft resends only the first.
        self.fail_101()
        for pk, score in ((102, "14"), (103, "15")):  # answered at once: row 103 times out after 600 ms
            self.enter_score(pk, score)
            self.next_request(SAVE).respond(409, reply("marks_conflict.html"), FRAGMENT)
            self.wait_for_status(pk, "Changed on another device")
        already = self.sent()
        self.page.click("[data-erp-save-fallback]")
        resent = self.new_save(already)
        self.assertEqual(form(resent)["enrollment"], "101")
        resent.respond(200, reply("marks_saved.html"), FRAGMENT)
        self.wait_until(lambda: self.page_line() == "2 rows need your attention", message="the attention line")
        self.assertEqual(self.sent(), already + 1, "conflict rows wait for Use or Keep")
        self.assertTrue(self.page.evaluate("window.stillHere === true"))

    def test_m6_with_a_row_in_flight_the_fallback_waits_then_resends(self):
        self.fail_101()
        self.enter_score(102, "14")
        in_flight = self.next_request(SAVE)
        self.page.click("[data-erp-save-fallback]")
        self.pump(0.3)
        self.assertEqual([form(h)["enrollment"] for h in self.saves()], ["102"], "nothing resent yet")
        self.assertEqual(self.page_line(), "Saving…")
        in_flight.respond(204)
        resent = self.next_request(SAVE)
        self.assertEqual(form(resent)["enrollment"], "101")
        resent.respond(204)


class ConflictTests(MarksPage):
    def conflict_on_101(self):
        self.enter_score(101, "13")
        self.next_request(SAVE).respond(409, reply("marks_conflict.html"), FRAGMENT)  # server has 12
        self.wait_for_status(101, "Changed on another device to 12.")

    def base_101(self):
        return (self.page.input_value('input[name="base_status_101"]'),
                self.page.input_value('input[name="base_score_101"]'))

    def test_m7_keep_theirs_shows_the_saved_value_and_sends_nothing(self):
        self.conflict_on_101()
        self.page.click("[data-erp-keep-theirs]")
        self.assertEqual(self.base_101(), ("MARKED", "12"))
        self.assertTrue(self.page.is_checked("#id_status_101_1"))  # Marked
        self.assertEqual(self.page.input_value("#id_score_101"), "12")
        self.assertTrue(self.row_status(101).startswith("✓ Saved"))
        self.no_request(SAVE)

    def test_m7_use_mine_sends_the_teachers_value_against_the_servers(self):
        self.conflict_on_101()
        self.page.click("[data-erp-use-mine]")
        self.assertEqual(self.base_101(), ("MARKED", "12"))
        mine = self.next_request(SAVE)
        body = form(mine)
        self.assertEqual((body["score_101"], body["base_status_101"], body["base_score_101"]), ("13", "MARKED", "12"))
        mine.respond(204)


class EnterTests(MarksPage):
    def test_m8_enter_on_a_middle_row_moves_on_and_the_row_left_is_saved(self):
        self.page.focus("#id_score_101")
        self.page.keyboard.type("12")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_score_102")
        saved = self.next_request(SAVE)
        self.assertEqual((form(saved)["enrollment"], form(saved)["score_101"]), ("101", "12"))
        saved.respond(204)
        self.no_request(SAVE)

    def test_m8_enter_on_the_last_row_keeps_focus_and_saves_once_only_if_changed(self):
        self.page.focus("#id_score_103")
        self.page.keyboard.type("7")
        self.page.keyboard.press("Enter")
        saved = self.next_request(SAVE)
        saved.respond(204)  # quickly: row 103 times out after 600 ms
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_score_103")
        self.assertEqual(form(saved)["score_103"], "7")
        self.no_request(SAVE)
        self.page.keyboard.press("Enter")  # unchanged since it was sent
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_score_103")
        self.no_request(SAVE)
        self.assertEqual(self.sent(), 1)


class MarkedWithoutScoreTests(MarksPage):
    def test_m9_marked_without_a_score_sends_nothing(self):
        self.page.check("#id_status_101_1")  # Marked, score empty
        self.wait_for_status(101, NEEDS_SCORE)
        self.assertEqual(self.announced(), "Could not save Student A. Enter a score or choose Absent.")
        self.no_request(SAVE)

    def test_m9_an_older_reply_does_not_hide_the_message(self):
        self.enter_score(101, "12")
        older = self.next_request(SAVE)
        self.enter_score(101, "")  # still Marked, now with no score
        self.pump(0.2)
        older.respond(200, reply("marks_saved.html"), FRAGMENT)
        self.wait_for_status(101, NEEDS_SCORE)
        self.no_request(SAVE)
        self.assertEqual(self.sent(), 1, "the empty score was never sent")
        self.assertIn("is-unsaved", self.page.locator('[data-erp-enrollment="101"]').get_attribute("class"))
