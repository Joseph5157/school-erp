"""Phase 5 Gate 4: teacher read-only attendance views (ADR 0012 D9)."""

from datetime import date, datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import reports
from core.models import AttendanceRegister, AttendanceStatus, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)


class TeacherAttendanceViewTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: TODAY),
                      mock.patch("core.models.business_today", new=lambda: TODAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.rao_row = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.iyer_row = SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 8, 1),
        )
        self.rao_row.refresh_from_db()
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        self.july = self.submitted(date(2026, 7, 6), absent=[self.ravi])
        self.august = self.submitted(date(2026, 8, 3))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def submitted(self, on_date, absent=()):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date
        )
        for enrollment in (self.asha, self.ravi):
            status = AttendanceStatus.ABSENT if enrollment in absent else AttendanceStatus.PRESENT
            register.save_draft_entry(enrollment=enrollment, status=status)
        AttendanceRegister.objects.filter(pk=register.pk).update(
            status="SUBMITTED", submitted_by=self.admin,
            submitted_at=timezone.make_aware(datetime(2026, 1, 1)),
        )
        register.refresh_from_db()
        return register

    def url(self, row, month=None):
        url = reverse("core:my-attendance-assignment", args=[row.pk])
        return f"{url}?month={month}" if month else url

    def test_history_lists_own_rows_including_ended_ones(self):
        page = self.teacher.get(reverse("core:my-attendance-history"))
        self.assertEqual(list(page.context["rows"]), [self.rao_row])
        self.assertEqual(self.rao_row.end_date, date(2026, 7, 31))

    def test_months_are_limited_to_assignment_dates(self):
        page = self.teacher.get(self.url(self.rao_row))
        self.assertEqual(page.context["months"], ["2026-06", "2026-07"])
        self.assertEqual(page.context["chosen"], "2026-07")
        self.assertEqual(page.context["end"], date(2026, 7, 31))

    def test_month_outside_range_falls_back(self):
        page = self.teacher.get(self.url(self.rao_row, "2026-08"))
        self.assertEqual(page.context["chosen"], "2026-07")
        page = self.teacher.get(self.url(self.rao_row, "nonsense"))
        self.assertEqual(page.context["chosen"], "2026-07")

    def test_summary_and_registers_only_cover_own_dates(self):
        page = self.teacher.get(self.url(self.rao_row, "2026-07"))
        self.assertEqual([r.date for r in page.context["registers"]], [date(2026, 7, 6)])
        register = page.context["registers"][0]
        self.assertEqual((register.present, register.absent), (1, 1))
        totals = page.context["summary"]["totals"]
        self.assertEqual((totals["present"], totals["absent"]), (1, 1))
        self.assertIn(date(2026, 7, 7), [item["date"] for item in page.context["missing"]])

    def test_section_summary_matches_monthly_report(self):
        start, end = reports.month_bounds(2026, 7)
        self.assertEqual(reports.section_summary(self.six_a, start, end),
                         reports.monthly_section_summary(self.six_a, 2026, 7))

    def test_new_class_teacher_sees_only_from_hand_over(self):
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        page = iyer.get(self.url(self.iyer_row))
        self.assertEqual(page.context["months"][0], "2026-08")
        self.assertEqual(page.context["months"][-1], "2026-10")
        self.assertEqual(page.context["end"], TODAY)
        self.assertEqual(iyer.get(self.url(self.rao_row)).status_code, 404)

    def test_register_detail_respects_dates(self):
        own = reverse("core:my-attendance-register", args=[self.july.pk])
        other = reverse("core:my-attendance-register", args=[self.august.pk])
        self.assertContains(self.teacher.get(own), "Absent")
        self.assertEqual(self.teacher.get(other).status_code, 403)
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        self.assertEqual(iyer.get(own).status_code, 403)
        self.assertEqual(iyer.get(other).status_code, 200)

    def test_register_views_are_read_only(self):
        url = reverse("core:my-attendance-register", args=[self.july.pk])
        response = self.teacher.post(url, {f"status_{self.ravi.pk}": "PRESENT"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.july.entries.get(academic_enrollment=self.ravi).status, "ABSENT")

    def test_lost_teacher_status_removes_history_access(self):
        self.rao.groups.remove(self.teachers)
        self.assertEqual(self.teacher.get(self.url(self.rao_row)).status_code, 403)
        register_url = reverse("core:my-attendance-register", args=[self.july.pk])
        self.assertEqual(self.teacher.get(register_url).status_code, 403)

    def test_planned_future_row_is_not_listed(self):
        future = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 11, 1),
        )
        self.assertEqual(self.teacher.get(self.url(future)).status_code, 404)

    def test_administrator_is_forbidden(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(reverse("core:my-attendance-history")).status_code, 403)
