"""'Mark unanswered as present' saves every bulk-marked row in one request.

Before, the button fired each row's change event, so a class of 40 sent 40 autosave
requests. Now erp.js posts the bulk-marked enrollments once to a batch endpoint with the
same authorization and validation as the single-row autosave. Rows marked by hand still
save one at a time.
"""

from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister, AttendanceStatus, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_phase5_teacher_attendance import MONDAY, on, press_confirm

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class BulkPresentTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        for patch in on(MONDAY):
            patch.start()
            self.addCleanup(patch.stop)
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.mina = self.make_student("Mina")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.teacher.post(self.url, {"action": "open"})
        self.bulk_url = reverse("core:my-attendance-autosave-present", args=[self.six_a.pk])

    def bulk(self, *enrollments, client=None, url=None, headers=AJAX):
        data = {"enrollment": [e.pk for e in enrollments]}
        return (client or self.teacher).post(url or self.bulk_url, data, **headers)

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def statuses(self):
        return dict(self.register().entries.values_list("academic_enrollment_id", "status"))

    # --- saving ---

    def test_one_request_saves_every_listed_row_as_present(self):
        response = self.bulk(self.asha, self.ravi)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"saved": [self.asha.pk, self.ravi.pk]})
        self.assertEqual(
            self.statuses(),
            {self.asha.pk: AttendanceStatus.PRESENT, self.ravi.pk: AttendanceStatus.PRESENT},
        )
        self.assertFalse(self.register().is_submitted)

    def test_unlisted_rows_are_left_alone(self):
        self.bulk(self.asha)
        self.assertNotIn(self.mina.pk, self.statuses())

    def test_an_absent_note_is_cleared_when_the_row_becomes_present(self):
        register = self.register()
        register.save_draft_entry(
            enrollment=self.ravi, status=AttendanceStatus.ABSENT, absence_note="Fever"
        )
        self.assertEqual(self.bulk(self.ravi).status_code, 200)
        entry = register.entries.get(academic_enrollment=self.ravi)
        self.assertEqual((entry.status, entry.absence_note), (AttendanceStatus.PRESENT, ""))

    # --- refusals: nothing is saved ---

    def test_an_enrollment_off_the_roster_refuses_the_whole_batch(self):
        _, cara = self.make_student("Cara", section=self.six_b)
        self.assertEqual(self.bulk(self.asha, cara).status_code, 404)
        self.assertEqual(self.register().entries.count(), 0)

    def test_forged_and_repeated_ids(self):
        response = self.teacher.post(self.bulk_url, {"enrollment": ["999999"]}, **AJAX)
        self.assertEqual(response.status_code, 404)
        response = self.teacher.post(self.bulk_url, {"enrollment": ["abc"]}, **AJAX)
        self.assertEqual(response.status_code, 404)
        response = self.bulk(self.asha, self.asha)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"saved": [self.asha.pk]})

    def test_empty_batch_is_a_bad_request(self):
        self.assertEqual(self.bulk().status_code, 400)

    def test_submitted_register_is_refused(self):
        data = {"action": "submit", f"status_{self.asha.pk}": "PRESENT",
                f"status_{self.ravi.pk}": "PRESENT", f"status_{self.mina.pk}": "PRESENT"}
        press_confirm(self.teacher, self.teacher.post(self.url, data, follow=True))
        self.assertTrue(self.register().is_submitted)
        response = self.bulk(self.asha)
        self.assertEqual(response.status_code, 409)
        self.assertIn("error", response.json())

    def test_other_section_other_teacher_and_anonymous_are_refused(self):
        other = reverse("core:my-attendance-autosave-present", args=[self.six_b.pk])
        self.assertEqual(self.bulk(self.asha, url=other).status_code, 403)
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        self.assertEqual(self.bulk(self.asha, client=iyer).status_code, 403)
        self.assertEqual(self.bulk(self.asha, client=self.client_class()).status_code, 302)
        self.assertEqual(self.register().entries.count(), 0)

    def test_plain_form_post_and_get_do_nothing(self):
        self.assertEqual(self.bulk(self.asha, headers={}).status_code, 400)
        self.assertEqual(self.teacher.get(self.bulk_url).status_code, 405)
        self.assertEqual(self.register().entries.count(), 0)

    # --- the page and the script ---

    def test_teacher_page_wires_the_button_and_rows(self):
        page = self.teacher.get(self.url)
        self.assertContains(page, f'data-erp-bulk-url="{self.bulk_url}"', count=1)
        self.assertContains(page, f'data-erp-enrollment="{self.asha.pk}"', count=1)

    def test_admin_page_has_no_batch_endpoint(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(
            reverse("core:attendance-register-detail", args=[self.register().pk])
        )
        self.assertNotContains(page, "data-erp-bulk-url")

    def test_script_posts_bulk_rows_once_instead_of_firing_each_row(self):
        script = (Path(settings.BASE_DIR) / "static" / "js" / "erp.js").read_text(encoding="utf-8")
        self.assertIn("saveBulk(marked)", script)
        self.assertIn('body.append("enrollment"', script)
