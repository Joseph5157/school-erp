"""Phase 5 Gate 3: class teacher takes today's attendance (ADR 0012 D4, D5, D7)."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.authorization import can_take_attendance
from core.models import (
    AttendanceCorrection,
    AttendanceRegister,
    AttendanceStatus,
    SchoolCalendarDay,
    SectionClassTeacher,
)
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


def on(day):
    return (
        mock.patch("core.views.business_today", new=lambda: day),
        mock.patch("core.models.business_today", new=lambda: day),
    )


class TeacherAttendanceTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.today(MONDAY)
        self.duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        self.make_student("Bina", section=self.six_b)
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])

    def today(self, day):
        for patch in on(day):
            patch.start()
            self.addCleanup(patch.stop)

    def open_register(self):
        return self.teacher.post(self.url, {"action": "open"})

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def both(self, asha="PRESENT", ravi="ABSENT", action="submit", **extra):
        data = {"action": action, f"status_{self.asha.pk}": asha,
                f"status_{self.ravi.pk}": ravi, **extra}
        return self.teacher.post(self.url, data, follow=True)

    # --- happy path ---

    def test_open_capture_and_submit(self):
        self.assertContains(self.teacher.get(self.url), "Start today's register")
        self.assertRedirects(self.open_register(), self.url)
        register = self.register()
        self.assertEqual((register.status, register.academic_year), ("DRAFT", self.year))
        page = self.teacher.get(self.url)
        self.assertEqual(
            [e.student for e in page.context["capture_form"].enrollments],
            [self.asha.student, self.ravi.student],
        )
        response = self.both(**{f"note_{self.ravi.pk}": "Fever"})
        self.assertContains(response, "Attendance saved and submitted.")
        register.refresh_from_db()
        self.assertTrue(register.is_submitted)
        self.assertEqual(register.submitted_by, self.rao)
        statuses = dict(register.entries.values_list("academic_enrollment_id", "status"))
        self.assertEqual(statuses, {self.asha.pk: "PRESENT", self.ravi.pk: "ABSENT"})

    def test_draft_save_is_editable_until_submitted(self):
        self.open_register()
        self.both(ravi="", action="save")
        self.assertFalse(self.register().is_submitted)
        self.both(asha="ABSENT", ravi="", action="save")
        entries = dict(self.register().entries.values_list("academic_enrollment_id", "status"))
        self.assertEqual(entries, {self.asha.pk: "ABSENT"})
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_incomplete_roster_cannot_be_submitted(self):
        self.open_register()
        response = self.both(ravi="")
        self.assertContains(response, "Draft saved but not submitted.")
        self.assertFalse(self.register().is_submitted)

    def test_home_links_to_attendance(self):
        page = self.teacher.get(reverse("core:my-home"))
        self.assertContains(page, "Not taken")
        self.assertContains(page, self.url)

    # --- D7: submitted is read-only ---

    def test_submitted_register_is_read_only_to_teacher(self):
        self.open_register()
        self.both()
        response = self.both(asha="ABSENT", ravi="ABSENT")
        self.assertContains(response, "ask an administrator to correct it")
        entries = dict(self.register().entries.values_list("academic_enrollment_id", "status"))
        self.assertEqual(entries[self.asha.pk], AttendanceStatus.PRESENT)
        page = self.teacher.get(self.url)
        self.assertNotIn("capture_form", page.context)
        self.assertContains(page, "Submitted")

    def test_administrator_submitted_register_is_read_only_too(self):
        self.open_register()
        self.both(action="save")
        self.register().submit(actor=self.admin)
        self.both(asha="ABSENT")
        self.assertEqual(
            self.register().entries.get(academic_enrollment=self.asha).status, "PRESENT"
        )

    # --- scope ---

    def test_other_section_is_forbidden(self):
        url = reverse("core:my-attendance", args=[self.six_b.pk])
        self.assertEqual(self.teacher.get(url).status_code, 403)
        self.assertEqual(self.teacher.post(url, {"action": "open"}).status_code, 403)
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_subject_teacher_who_is_not_class_teacher_is_forbidden(self):
        self.assign(self.iyer, self.maths, self.six_a)
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        self.assertEqual(iyer.get(self.url).status_code, 403)

    def test_handed_over_teacher_loses_access_on_hand_over_day(self):
        SectionClassTeacher.assign(teacher=self.iyer, academic_year=self.year,
                                   section=self.six_a, start_date=MONDAY)
        self.assertEqual(self.teacher.get(self.url).status_code, 403)
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        self.assertEqual(iyer.get(self.url).status_code, 200)

    def test_ended_or_future_assignment_gives_no_access(self):
        self.duty.end(date(2026, 10, 9))
        self.assertEqual(self.teacher.get(self.url).status_code, 403)

    def test_lost_teacher_status(self):
        self.rao.is_active = False
        self.rao.save()
        self.assertFalse(can_take_attendance(self.rao, self.six_a, MONDAY))

    def test_administrator_and_plain_users_use_admin_workflow(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    # --- D5: today only, instructional only ---

    def test_only_business_date(self):
        self.assertTrue(can_take_attendance(self.rao, self.six_a, MONDAY))
        self.assertFalse(can_take_attendance(self.rao, self.six_a, date(2026, 10, 9)))
        self.assertFalse(can_take_attendance(self.rao, self.six_a, date(2026, 10, 13)))

    def test_yesterdays_draft_is_not_reachable(self):
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 10, 9),
        )
        page = self.teacher.get(self.url)
        self.assertIsNone(page.context["register"])

    def test_non_instructional_day(self):
        SchoolCalendarDay.objects.create(academic_year=self.year, date=MONDAY,
                                         is_instructional=False, label="Holiday")
        self.assertContains(self.teacher.get(self.url), "not a school day")
        self.open_register()
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_count_bar_has_static_text_without_javascript(self):
        self.open_register()
        page = self.teacher.get(self.url)
        self.assertContains(
            page, 'data-erp-static-counts>2 students &middot; 0 present &middot; 0 absent'
        )
        self.assertContains(page, "2 unmarked</span>")
        self.assertContains(page, "erp-count-unmarked is-warn")

    def test_submitted_state_uses_badge_and_empty_card(self):
        self.open_register()
        self.both()
        page = self.teacher.get(self.url)
        self.assertContains(page, "erp-empty--submitted")
        self.assertContains(page, "erp-status--submitted")
        self.assertNotContains(page, "data-erp-static-counts")

    def test_admin_opened_draft_can_be_completed_by_teacher(self):
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY
        )
        self.both()
        self.assertEqual(self.register().submitted_by, self.rao)

    def test_double_open_is_harmless(self):
        self.open_register()
        self.open_register()
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_transferred_student_follows_effective_roster(self):
        self.ravi.student.enroll(academic_year=self.year, class_grade=self.grade6,
                                 section=self.six_b, start_date=MONDAY)
        self.open_register()
        page = self.teacher.get(self.url)
        self.assertEqual([e.student for e in page.context["capture_form"].enrollments],
                         [self.asha.student])


class TeacherAttendanceAutosaveTests(Phase4Fixture, TestCase):
    """HTMX draft autosave: one row at a time, never submits, same rules as the form."""

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
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])
        self.teacher.post(self.url, {"action": "open"})
        self.autosave_url = reverse("core:my-attendance-autosave", args=[self.six_a.pk])

    def autosave(self, enrollment, status="", note=None, url=None, client=None):
        data = {"enrollment": enrollment.pk, f"status_{enrollment.pk}": status}
        if note is not None:
            data[f"note_{enrollment.pk}"] = note
        return (client or self.teacher).post(url or self.autosave_url, data, HTTP_HX_REQUEST="true")

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def both(self, asha="PRESENT", ravi="ABSENT", action="submit"):
        data = {"action": action, f"status_{self.asha.pk}": asha, f"status_{self.ravi.pk}": ravi}
        return self.teacher.post(self.url, data, follow=True)

    def entry(self, enrollment):
        return self.register().entries.filter(academic_enrollment=enrollment).first()

    # --- saving ---

    def test_present_autosave_creates_draft_entry_only(self):
        response = self.autosave(self.asha, "PRESENT")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saved")
        self.assertEqual(self.entry(self.asha).status, AttendanceStatus.PRESENT)
        self.assertIsNone(self.entry(self.ravi))
        self.assertFalse(self.register().is_submitted)

    def test_absent_with_note_autosave(self):
        self.assertEqual(self.autosave(self.ravi, "ABSENT", "Fever").status_code, 200)
        entry = self.entry(self.ravi)
        self.assertEqual((entry.status, entry.absence_note), ("ABSENT", "Fever"))
        self.autosave(self.ravi, "ABSENT", "Fever and cough")
        self.assertEqual(self.entry(self.ravi).absence_note, "Fever and cough")

    def test_existing_draft_row_updates_without_duplicate_or_correction(self):
        self.autosave(self.asha, "PRESENT")
        self.autosave(self.asha, "ABSENT", "Late bus")
        self.assertEqual(self.register().entries.filter(academic_enrollment=self.asha).count(), 1)
        self.assertEqual(self.entry(self.asha).status, AttendanceStatus.ABSENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_note_on_present_is_refused_and_keeps_saved_value(self):
        self.autosave(self.ravi, "ABSENT", "Fever")
        response = self.autosave(self.ravi, "PRESENT", "Fever")
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Only an absent Student can have a note.", status_code=422)
        self.assertEqual(self.entry(self.ravi).status, AttendanceStatus.ABSENT)

    def test_unanswered_row_saves_nothing(self):
        self.assertEqual(self.autosave(self.asha, "").status_code, 200)
        self.assertEqual(self.register().entries.count(), 0)

    # --- counts ---

    def test_response_carries_saved_counts_and_hint(self):
        self.autosave(self.asha, "PRESENT")
        response = self.autosave(self.ravi, "ABSENT")
        for key, value in (("present", 1), ("absent", 1), ("unmarked", 0)):
            self.assertContains(
                response,
                f'id="erp-count-{key}" data-erp-count="{key}" hx-swap-oob="true">{value}<',
            )
        self.assertContains(response, "All students marked")

    def test_hint_reports_unmarked_rows(self):
        response = self.autosave(self.asha, "PRESENT")
        self.assertContains(response, "Mark all students to submit (1 unmarked)")

    # --- guard rails ---

    def test_submitted_register_is_refused(self):
        self.both()
        response = self.autosave(self.asha, "ABSENT")
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "already submitted", status_code=409)
        self.assertEqual(self.entry(self.asha).status, AttendanceStatus.PRESENT)

    def test_autosave_never_submits(self):
        self.autosave(self.asha, "PRESENT")
        self.autosave(self.ravi, "PRESENT")
        self.assertFalse(self.register().is_submitted)

    def test_other_section_is_forbidden(self):
        url = reverse("core:my-attendance-autosave", args=[self.six_b.pk])
        self.assertEqual(self.autosave(self.asha, "PRESENT", url=url).status_code, 403)
        self.assertEqual(self.register().entries.count(), 0)

    def test_enrollment_from_another_section_is_not_found(self):
        _, cara = self.make_student("Cara", section=self.six_b)
        response = self.autosave(cara, "PRESENT")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.register().entries.count(), 0)

    def test_forged_enrollment_id_is_not_found(self):
        data = {"enrollment": 999999, "status_999999": "PRESENT"}
        response = self.teacher.post(self.autosave_url, data, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 404)

    def test_only_the_posted_row_is_saved(self):
        data = {
            "enrollment": self.asha.pk,
            f"status_{self.asha.pk}": "PRESENT",
            f"status_{self.ravi.pk}": "ABSENT",
        }
        self.teacher.post(self.autosave_url, data, HTTP_HX_REQUEST="true")
        self.assertIsNone(self.entry(self.ravi))

    def test_other_teacher_and_anonymous_are_refused(self):
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        self.assertEqual(self.autosave(self.asha, "PRESENT", client=iyer).status_code, 403)
        anonymous = self.client_class()
        self.assertEqual(self.autosave(self.asha, "PRESENT", client=anonymous).status_code, 302)
        self.assertEqual(self.register().entries.count(), 0)

    def test_without_htmx_header_and_on_get_nothing_happens(self):
        data = {"enrollment": self.asha.pk, f"status_{self.asha.pk}": "PRESENT"}
        self.assertEqual(self.teacher.post(self.autosave_url, data).status_code, 400)
        self.assertEqual(self.teacher.get(self.autosave_url).status_code, 405)
        self.assertEqual(self.register().entries.count(), 0)

    # --- the page and the non-HTMX flow ---

    def test_capture_page_wires_rows_to_autosave(self):
        page = self.teacher.get(self.url)
        self.assertContains(page, f'hx-post="{self.autosave_url}"', count=2)
        self.assertContains(page, "data-erp-autosave-announce")
        self.assertContains(page, "htmx.org@2.0.4")
        self.assertContains(page, "Save draft")
        self.assertContains(page, "Save and submit")

    def test_submitted_page_does_not_load_htmx(self):
        self.both()
        self.assertNotContains(self.teacher.get(self.url), "htmx")

    def test_admin_capture_page_is_unchanged(self):
        register = self.register()
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertNotContains(page, "hx-post")
        self.assertNotContains(page, "htmx")

    def test_ordinary_save_and_submit_still_work_after_autosave(self):
        self.autosave(self.asha, "PRESENT")
        self.assertContains(self.both(ravi="", action="save"), "Draft saved.")
        self.assertFalse(self.register().is_submitted)
        response = self.both()
        self.assertContains(response, "Attendance saved and submitted.")
        self.assertTrue(self.register().is_submitted)
