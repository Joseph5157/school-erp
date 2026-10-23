"""UI-D1-4B: administrator Attendance Register Detail and Correction pages.

Presentation-only: Draft/Submitted behaviour, roster counts, permissions, CSRF, Save draft,
Save and submit, correction validation and the immutable correction history are unchanged.
"""

import re
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AttendanceCorrection, AttendanceEntry, AttendanceRegister, AttendanceStatus, Section,
)
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()
DAY = date(2026, 7, 6)  # a Monday inside the instructional calendar


class DetailFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")

    def register(self, on_date=DAY, section=None, *, submitted=False, marks=()):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            section=section or self.six_a, date=on_date,
        )
        for enrollment, status, note in marks:
            register.save_draft_entry(enrollment=enrollment, status=status, absence_note=note)
        if submitted:
            AttendanceRegister.objects.filter(pk=register.pk).update(
                status="SUBMITTED", submitted_by=self.admin,
                submitted_at=timezone.make_aware(datetime(2026, 7, 6, 15, 30)),
            )
            register.refresh_from_db()
        return register

    def detail_url(self, register):
        return reverse("core:attendance-register-detail", args=[register.pk])

    def viewer(self, *codenames):
        user = User.objects.create_user(username="v-" + "-".join(codenames), password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return client

    def submitted_entry(self, note="", status=AttendanceStatus.ABSENT):
        register = self.register(submitted=True, marks=[
            (self.asha, status, note), (self.ravi, AttendanceStatus.PRESENT, "")])
        return register, register.entries.get(academic_enrollment=self.asha)


class DetailHeaderTests(DetailFixture, TestCase):
    def setUp(self):
        self.build()

    def test_one_h1_context_line_status_badge_and_back_link(self):
        register = self.register(marks=[(self.asha, AttendanceStatus.PRESENT, "")])
        content = self.client.get(self.detail_url(register)).content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn(">Attendance register</h1>", content)
        self.assertIn("Grade 6 - A · Monday, 6 July 2026", content)
        self.assertRegex(content, r'erp-status--draft"><span class="visually-hidden">Status: </span>Draft')
        self.assertIn(f'href="{reverse("core:attendance-register-list")}">Back to attendance', content)

    def test_context_panel_keeps_every_original_value(self):
        content = self.client.get(self.detail_url(self.register())).content.decode()
        panel = content.split('aria-labelledby="register-context-heading"')[1].split("</section>")[0]
        for label in ("Academic year", "Class/Grade", "Section", "Date", "Register status"):
            self.assertIn(f">{label}</dt>", panel)
        self.assertIn("2026-27", panel)
        self.assertIn("(Monday)", panel)
        self.assertIn("Attendance started, not yet official.", panel)
        self.assertNotIn("Submitted</dt>", panel)

    def test_submitted_register_shows_submitter_and_no_draft_helper(self):
        register, _ = self.submitted_entry()
        content = self.client.get(self.detail_url(register)).content.decode()
        self.assertIn(">Submitted</dt>", content)
        self.assertIn("by admin", content)
        self.assertNotIn("Attendance started, not yet official.", content)
        self.assertRegex(content, r'erp-status--submitted"><span class="visually-hidden">Status: </span>Submitted')

    def test_long_unbroken_section_name_is_escaped_and_wrappable(self):
        long = Section.objects.create(class_grade=self.grade6, name="X" * 70 + "<b>")
        register = self.register(section=long)
        content = self.client.get(self.detail_url(register)).content.decode()
        self.assertIn("X" * 70 + "&lt;b&gt;", content)
        self.assertNotIn("<b>", content)
        self.assertIn('class="col-sm-9 text-break">Grade 6 - ' + "X" * 70, content)


class DraftDetailTests(DetailFixture, TestCase):
    def setUp(self):
        self.build()
        self.register_obj = self.register(marks=[(self.asha, AttendanceStatus.ABSENT, "ill")])
        self.url = self.detail_url(self.register_obj)

    def test_roster_counts_and_unmarked_is_not_absent(self):
        content = self.client.get(self.url).content.decode()
        self.assertIn("Students enrolled in this Section on", content)
        self.assertRegex(content, r"Section on [^:]+: 2\.\s+Marked: 1\.")
        self.assertIn("<strong>not</strong> treated as absent", content)
        self.assertIn("1 unmarked", content)

    def test_capture_form_is_unchanged_with_csrf_save_draft_and_submit(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        capture = reverse("core:attendance-capture", args=[self.register_obj.pk])
        self.assertIn(f'<form method="post" action="{capture}" id="attendance-capture">', content)
        form = content.split('id="attendance-capture">')[1].split("</form>")[0]
        self.assertEqual(form.count('name="csrfmiddlewaretoken"'), 1)
        self.assertIn('name="action" value="save"', content)
        self.assertIn('name="action" value="submit"', content)
        # Logout form + the one capture form. (The shared partial's two-line {# #} comment renders
        # literally, adding a stray "<form id=...>" text outside this gate's scope.)
        self.assertEqual(content.count('<form method="post"'), 2)
        self.assertEqual(content.count('action="%s"' % capture), 1)
        self.assertNotContains(response, "Submitted attendance")

    def test_submit_button_needs_change_register_but_save_draft_does_not(self):
        client = self.viewer("view_attendanceregister", "add_attendanceentry")
        content = client.get(self.url).content.decode()
        self.assertIn('name="action" value="save"', content)
        self.assertNotIn('name="action" value="submit"', content)

        both = self.viewer("view_attendanceregister", "add_attendanceentry", "change_attendanceregister")
        self.assertIn('name="action" value="submit"', both.get(self.url).content.decode())

    def test_view_only_user_gets_read_only_context_and_no_capture_form(self):
        response = self.viewer("view_attendanceregister").get(self.url)
        self.assertContains(response, "You do not have permission to capture attendance.")
        self.assertNotContains(response, 'id="attendance-capture"')
        self.assertNotContains(response, 'name="action"')
        self.assertContains(response, "Marked: 1.")

    def test_change_register_alone_cannot_capture(self):
        response = self.viewer("view_attendanceregister", "change_attendanceregister").get(self.url)
        self.assertNotContains(response, 'id="attendance-capture"')

    def test_empty_roster_shows_neutral_message_and_no_form(self):
        empty = self.register(section=self.six_b, on_date=date(2026, 7, 7))
        response = self.client.get(self.detail_url(empty))
        self.assertContains(response, "No Students are enrolled in this Section on this date.")
        self.assertContains(response, "Marked: 0.")
        self.assertNotContains(response, 'id="attendance-capture"')
        self.assertNotContains(response, 'name="action"')

    def test_get_writes_nothing(self):
        before = (AttendanceRegister.objects.count(), AttendanceEntry.objects.count())
        self.client.get(self.url)
        self.assertEqual((AttendanceRegister.objects.count(), AttendanceEntry.objects.count()), before)

    def test_save_draft_keeps_the_register_editable_and_creates_no_correction(self):
        capture = reverse("core:attendance-capture", args=[self.register_obj.pk])
        response = self.client.post(capture, {
            f"status_{self.asha.pk}": "ABSENT", f"note_{self.asha.pk}": "ill",
            f"status_{self.ravi.pk}": "PRESENT", "action": "save"})
        self.assertRedirects(response, self.url)
        self.register_obj.refresh_from_db()
        self.assertFalse(self.register_obj.is_submitted)
        self.assertEqual(self.register_obj.entries.count(), 2)
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_submit_is_rejected_until_every_student_is_marked(self):
        capture = reverse("core:attendance-capture", args=[self.register_obj.pk])
        self.client.post(capture, {f"status_{self.asha.pk}": "PRESENT", "action": "submit"})
        self.register_obj.refresh_from_db()
        self.assertFalse(self.register_obj.is_submitted)
        self.assertFalse(self.register_obj.entries.filter(academic_enrollment=self.ravi).exists())


class SubmittedDetailTests(DetailFixture, TestCase):
    def setUp(self):
        self.build()
        self.register_obj, self.entry = self.submitted_entry(note="ill")
        self.url = self.detail_url(self.register_obj)

    def table(self, response):
        return response.content.decode().split('aria-label="Submitted attendance"')[1].split("</table>")[0]

    def test_panel_region_caption_and_scoped_headers_with_actions_for_correctors(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn('<div class="erp-panel">\n<div class="erp-table-scroll" role="region" '
                      'aria-label="Submitted attendance" tabindex="0">', content)
        table = self.table(response)
        self.assertIn('<caption class="visually-hidden">', table)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', table),
                         ["Student", "Status", "Absence note", "Actions"])
        self.assertContains(response, "Correct</a>", count=2)
        self.assertContains(response, reverse("core:attendance-entry-correct", args=[self.entry.pk]))
        self.assertNotContains(response, 'id="attendance-capture"')
        self.assertNotContains(response, "Roster")

    def test_view_only_sees_three_columns_and_no_correct_links(self):
        response = self.viewer("view_attendanceregister").get(self.url)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', self.table(response)),
                         ["Student", "Status", "Absence note"])
        self.assertNotContains(response, "Correct</a>")
        self.assertNotContains(response, "attendance-entry-correct")

    def test_rows_keep_model_order_status_text_note_and_student_links(self):
        response = self.client.get(self.url)
        rows = re.findall(r'<td class="text-break"><a href="([^"]+)">([^<]+)</a></td>\s*<td>([^<]+)</td>\s*'
                          r'<td class="text-break">([^<]*)</td>', self.table(response))
        expected = [(reverse("core:student-detail", args=[e.academic_enrollment.student.pk]),
                     e.academic_enrollment.student.full_name, e.get_status_display(), e.absence_note)
                    for e in response.context["entries"]]
        self.assertEqual(rows, expected)
        self.assertIn(("Asha", "Absent", "ill"), [(r[1], r[2], r[3]) for r in rows])

    def test_empty_submitted_register_colspan_matches_the_rendered_columns(self):
        empty = self.register(on_date=date(2026, 7, 7), section=self.six_b, submitted=True)
        self.assertContains(self.client.get(self.detail_url(empty)), 'colspan="4">No attendance entries.')
        viewer = self.viewer("view_attendanceregister").get(self.detail_url(empty))
        self.assertContains(viewer, 'colspan="3">No attendance entries.')


class CorrectionFormTests(DetailFixture, TestCase):
    def setUp(self):
        self.build()
        self.register_obj, self.entry = self.submitted_entry(note="ill")
        self.url = reverse("core:attendance-entry-correct", args=[self.entry.pk])

    def post(self, **data):
        return self.client.post(self.url, data)

    def assert_untouched(self):
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.status, self.entry.absence_note), ("ABSENT", "ill"))
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_get_shows_context_panel_fields_in_order_and_unchanged_form_controls(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        panel = content.split('aria-labelledby="correction-context-heading"')[1].split("</section>")[0]
        for text in ("Asha", "Grade 6 - A", "Absent", "ill",
                     "Correcting this entry to Present clears its absence note."):
            self.assertIn(text, panel)
        self.assertEqual(list(response.context["form"].fields), ["status", "absence_note", "reason"])
        form = content.split('<form method="post" class="erp-form">')[1].split("</form>")[0]
        self.assertEqual(form.count("csrfmiddlewaretoken"), 1)
        self.assertEqual(re.findall(r'name="(status|absence_note|reason)"', form),
                         ["status", "absence_note", "reason"])
        self.assertIn(">Save correction</button>", form)
        self.assertIn(f'href="{self.detail_url(self.register_obj)}">Cancel', form)
        self.assertEqual(AttendanceCorrection.objects.count(), 0)

    def test_no_note_line_when_the_entry_has_no_absence_note(self):
        entry = AttendanceEntry.objects.get(academic_enrollment=self.ravi)
        response = self.client.get(reverse("core:attendance-entry-correct", args=[entry.pk]))
        self.assertNotContains(response, "clears its absence note")

    def test_non_correctors_are_forbidden(self):
        self.assertEqual(self.viewer("view_attendanceregister").get(self.url).status_code, 403)
        self.assertEqual(self.client_class().get(self.url).status_code, 302)

    def test_valid_correction_to_present_records_history_clears_note_and_redirects(self):
        response = self.post(status="PRESENT", absence_note="", reason="Parent called school")
        self.assertRedirects(response, self.detail_url(self.register_obj))
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.status, self.entry.absence_note), ("PRESENT", ""))
        correction = AttendanceCorrection.objects.get()
        self.assertEqual((correction.previous_status, correction.new_status), ("ABSENT", "PRESENT"))
        self.assertEqual((correction.previous_absence_note, correction.new_absence_note), ("ill", ""))
        self.assertEqual((correction.reason, correction.corrected_by), ("Parent called school", self.admin))

    def test_invalid_posts_are_rejected_without_writes_and_keep_their_errors(self):
        cases = {
            "missing reason": ({"status": "PRESENT", "absence_note": "", "reason": ""}, "This field is required."),
            "present with note": ({"status": "PRESENT", "absence_note": "x", "reason": "r"},
                                  "Only an absent Student can have a note."),
            "invalid status": ({"status": "LATE", "absence_note": "", "reason": "r"}, "Select a valid choice."),
            "no-op": ({"status": "ABSENT", "absence_note": "ill", "reason": "r"}, None),
        }
        for name, (data, message) in cases.items():
            with self.subTest(case=name):
                response = self.post(**data)
                self.assertEqual(response.status_code, 200)
                if message:
                    self.assertContains(response, message)
                self.assert_untouched()

    def test_invalid_post_keeps_submitted_values(self):
        response = self.post(status="PRESENT", absence_note="keep me", reason="")
        content = response.content.decode()
        self.assertIn("keep me", content)
        self.assertIn('class="erp-field-errors"', content)

    def test_draft_entry_redirects_to_the_register_without_a_form(self):
        draft = self.register(on_date=date(2026, 7, 7), marks=[(self.asha, AttendanceStatus.ABSENT, "")])
        entry = draft.entries.get()
        url = reverse("core:attendance-entry-correct", args=[entry.pk])
        self.assertRedirects(self.client.get(url), self.detail_url(draft))
        self.assertEqual(self.client.post(url, {"status": "PRESENT", "reason": "r"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "ABSENT")


class CorrectionHistoryTests(DetailFixture, TestCase):
    def setUp(self):
        self.build()
        self.register_obj, self.entry = self.submitted_entry(note="ill")
        self.url = reverse("core:attendance-entry-correct", args=[self.entry.pk])

    def history(self, response):
        content = response.content.decode()
        return content.split('aria-labelledby="correction-history-heading"')[1].split("</section>")[0]

    def test_empty_history_is_truthful_and_still_a_labelled_scroll_region(self):
        history = self.history(self.client.get(self.url))
        self.assertIn('<div class="erp-panel">', history)
        self.assertIn('role="region" aria-label="Correction history" tabindex="0"', history)
        self.assertIn('colspan="6">No corrections recorded.', history)

    def test_six_scoped_headers_caption_and_newest_first_rows(self):
        self.entry.record_status_change("PRESENT", actor=self.admin, reason="First fix")
        self.entry.refresh_from_db()
        self.entry.record_status_change("ABSENT", actor=self.admin, reason="Second fix", absence_note="back ill")
        history = self.history(self.client.get(self.url))
        self.assertIn('<caption class="visually-hidden">', history)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', history),
                         ["When", "From", "To", "Note change", "Reason", "By"])
        self.assertLess(history.index("Second fix"), history.index("First fix"))
        self.assertEqual(history.count("<tr>"), 3)  # header + two rows

    def test_note_change_shown_only_when_notes_differ_and_none_is_spelled_out(self):
        self.entry.record_status_change("PRESENT", actor=self.admin, reason="Cleared")
        self.assertIn("ill → (none)", self.history(self.client.get(self.url)).replace("&rarr;", "→"))
        register = self.register(on_date=date(2026, 7, 8), submitted=True,
                                 marks=[(self.asha, AttendanceStatus.PRESENT, "")])
        other = register.entries.get()
        other.record_status_change("ABSENT", actor=self.admin, reason="Marked absent")
        page = self.client.get(reverse("core:attendance-entry-correct", args=[other.pk]))
        history = self.history(page)
        self.assertIn("Marked absent", history)
        self.assertNotIn("(none)", history)

    def test_long_multiline_reason_is_kept_whole_and_escaped(self):
        reason = "Line one\nLine two <script>alert(1)</script> " + "word " * 80
        self.entry.record_status_change("PRESENT", actor=self.admin, reason=reason)
        history = self.history(self.client.get(self.url))
        self.assertIn("Line one<br>Line two &lt;script&gt;", history)
        self.assertNotIn("<script>", history)
        self.assertEqual(history.count("word"), 80)
        self.assertIn('<td class="text-break">Line one', history)

    def test_history_is_immutable_after_a_later_correction(self):
        self.entry.record_status_change("PRESENT", actor=self.admin, reason="One")
        first = AttendanceCorrection.objects.get()
        snapshot = (first.previous_status, first.new_status, first.reason, first.created_at)
        self.entry.refresh_from_db()
        self.entry.record_status_change("ABSENT", actor=self.admin, reason="Two")
        first.refresh_from_db()
        self.assertEqual((first.previous_status, first.new_status, first.reason, first.created_at), snapshot)
