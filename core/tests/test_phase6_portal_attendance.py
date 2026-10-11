"""Phase 6 Gate 5: submitted attendance history and summary (ADR 0014, P8)."""

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import reports
from core.models import AttendanceRegister, AttendanceStatus
from core.tests.test_phase6_access_boundary import BoundaryFixture

MON, TUE, WED, THU = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)


class PortalAttendanceTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.bina_e = self.bina.enrollments.get()
        self.register(MON, asha=AttendanceStatus.PRESENT)
        self.tue = self.register(TUE, asha=AttendanceStatus.ABSENT, note="Fever, called in")
        self.register(WED, asha=AttendanceStatus.ABSENT)
        self.register(THU, asha=AttendanceStatus.PRESENT, submit=False)  # DRAFT
        self.portal = self.guardian_client()
        self.url = reverse("portal:attendance", args=[self.asha_grant.public_id])

    def register(self, on_date, *, asha, note="", submit=True):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=asha, absence_note=note)
        register.save_draft_entry(enrollment=self.bina_e, status=AttendanceStatus.PRESENT)
        if submit:
            register.submit(actor=self.admin)
        return register

    def test_only_submitted_days_with_current_status(self):
        page = self.portal.get(self.url)
        days = [(d["date"], d["status"]) for d in page.context["days"]]
        self.assertEqual(days, [(WED, "ABSENT"), (TUE, "ABSENT"), (MON, "PRESENT")])
        self.assertNotIn(THU, [d for d, _ in days])

    def test_summary_matches_phase_2_report(self):
        summary = self.portal.get(self.url).context["summary"]
        expected = reports.student_summary(self.asha, start=self.year.start_date,
                                           end=self.year.end_date)
        self.assertEqual(summary, expected)
        self.assertEqual((summary["present"], summary["absent"]), (1, 2))

    def test_correction_shows_only_the_corrected_value(self):
        entry = self.tue.entries.get(academic_enrollment=self.asha_e)
        entry.record_status_change(AttendanceStatus.PRESENT, actor=self.admin,
                                   reason="Arrived late, register was wrong")
        page = self.portal.get(self.url)
        self.assertIn((TUE, "PRESENT"), [(d["date"], d["status"]) for d in page.context["days"]])
        text = page.content.decode()
        for hidden in ("Arrived late", "register was wrong", "admin", "orrect", "Fever"):
            with self.subTest(hidden=hidden):
                self.assertNotIn(hidden, text)

    def test_absence_notes_never_render(self):
        self.assertNotContains(self.portal.get(self.url), "Fever, called in")

    def test_other_years_and_bad_year_parameter(self):
        page = self.portal.get(self.url, {"year": "1999-06-01"})
        self.assertEqual(page.context["year"], self.year)
        self.assertEqual(page.context["years"], [self.year])

    def test_scope(self):
        other = reverse("portal:attendance", args=[self.bina_grant.public_id])
        self.assertEqual(self.portal.get(other).status_code, 404)
        self.today = date(2027, 4, 5)
        self.assertEqual(self.portal.get(self.url).status_code, 404)  # pending review

    def test_profile_links_to_attendance(self):
        page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, self.url)

    def test_query_count_constant(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.portal.get(self.url).status_code, 200)
            return len(ctx.captured_queries)

        small = count()
        for day in (date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)):
            self.register(day, asha=AttendanceStatus.PRESENT)
        self.assertEqual(count(), small)

    def test_no_attendance_yet(self):
        AttendanceRegister.objects.all().update(status="DRAFT", submitted_by=None,
                                                submitted_at=None)
        page = self.portal.get(self.url)
        self.assertEqual(page.context["days"], [])
        self.assertNotContains(page, "Absent")
