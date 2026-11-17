"""Modern web audit 12: A11Y-01 (flash messages) and A11Y-04 (large-form counters)."""

import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class Message:
    def __init__(self, level_tag, text):
        self.level_tag, self.text = level_tag, text

    def __str__(self):
        return self.text


class MessageRegionTests(SimpleTestCase):
    def render(self, *messages):
        return render_to_string("partials/_messages.html", {"messages": list(messages)})

    def test_messages_sit_in_a_named_region(self):
        html = self.render(Message("success", "Saved."))
        self.assertIn('<section class="erp-messages" aria-label="Notifications">', html)
        self.assertNotIn('aria-live="polite"', html)

    def test_errors_are_alerts_and_the_rest_are_status(self):
        html = self.render(Message("error", "Not saved."), Message("success", "Saved."),
                           Message("warning", "Check this."), Message("info", "Note."))
        roles = re.findall(r'class="alert alert-(\w+)[^"]*" role="(\w+)"', html)
        self.assertEqual(roles, [("danger", "alert"), ("success", "status"), ("warning", "status"), ("info", "status")])

    def test_only_success_and_info_hide_themselves(self):
        html = self.render(Message("error", "x"), Message("warning", "y"), Message("success", "z"), Message("info", "w"))
        self.assertEqual(html.count("data-erp-autohide"), 2)

    def test_no_messages_renders_nothing(self):
        self.assertEqual(self.render().strip(), "")

    def test_region_is_first_inside_main_in_both_shells(self):
        for shell in (("templates", "base.html"), ("templates", "portal", "base.html")):
            with self.subTest(shell=shell):
                text = read(*shell)
                self.assertRegex(text, r'<main id="main" class="erp-main"[^>]*>\n\s*\{% include "partials/_messages.html" %\}')
                self.assertEqual(text.count("_messages.html"), 1)

    def test_autohide_waits_while_a_message_is_hovered_or_focused(self):
        js = read("static", "js", "erp.js")
        self.assertIn('alert.matches(":hover") || alert.contains(document.activeElement)', js)


class CounterSpeechTests(SimpleTestCase):
    def test_counters_are_not_live_regions(self):
        for name in ("_attendance_capture_table.html", "_attendance_autosave_status.html", "assessment_marks_entry.html"):
            with self.subTest(name=name):
                text = read("core", "templates", "core", name)
                self.assertNotRegex(text, r"data-erp-hint[^>]*aria-live")

    def test_each_large_form_has_one_completion_announcer(self):
        for name in ("_attendance_capture_table.html", "assessment_marks_entry.html"):
            with self.subTest(name=name):
                text = read("core", "templates", "core", name)
                self.assertEqual(text.count('<p class="visually-hidden" role="status" data-erp-done-announce></p>'), 1)

    def test_announcer_speaks_only_on_a_change_and_not_on_load(self):
        js = read("static", "js", "erp.js")
        self.assertIn("if (!node || done === wasDone) return;", js)
        self.assertIn('if (wasDone !== null) node.textContent = done ? message : "";', js)
        self.assertIn('doneAnnouncer(roster, "All students marked.")', js)
        self.assertIn('doneAnnouncer(sheet, "All students have a mark or Absent.")', js)
