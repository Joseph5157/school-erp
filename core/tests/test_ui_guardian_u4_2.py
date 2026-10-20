"""U4-2: Guardian attendance calendar (truthful Present / Absent / Not recorded)."""

from datetime import date
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicEnrollment,
    AcademicYear,
    AttendanceRegister,
    AttendanceStatus,
    SchoolCalendarDay,
)
from core.tests.test_phase6_access_boundary import BoundaryFixture

# Oct 2026: Fri 2 is a holiday, Sat 3 / Sun 4 are weekend, Mon 5 present,
# Tue 6 absent, Wed 7 instructional but never recorded, Thu 8 is in a DRAFT register.
HOLIDAY, SAT, SUN = date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)
MON, TUE, WED, THU = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)


class CalendarFixture(BoundaryFixture):
    def setUp(self):
        super().setUp()
        patch = mock.patch("core.reports.business_today", new=lambda: self.today)
        patch.start()
        self.addCleanup(patch.stop)
        self.portal = self.guardian_client()
        self.url = reverse("portal:attendance", args=[self.asha_grant.public_id])

    def register(self, on_date, status, submit=True):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=status)
        register.save_draft_entry(
            enrollment=self.bina.enrollments.get(), status=AttendanceStatus.PRESENT)
        if submit:
            register.submit(actor=self.admin)
        return register

    def page(self, **params):
        params.setdefault("month", "2026-10")
        return self.portal.get(self.url, params)

    @staticmethod
    def cell(page, on_date):
        for week in page.context["month"]["weeks"]:
            for cell in week:
                if cell and cell["date"] == on_date:
                    return cell
        raise AssertionError(f"{on_date} not in month grid")


class MonthCellTests(CalendarFixture, TestCase):
    def setUp(self):
        super().setUp()
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=HOLIDAY, is_instructional=False, label="Holiday")
        self.register(MON, AttendanceStatus.PRESENT)
        self.register(TUE, AttendanceStatus.ABSENT)
        self.register(THU, AttendanceStatus.PRESENT, submit=False)

    def test_recorded_present_and_absent(self):
        page = self.page()
        self.assertEqual(self.cell(page, MON)["state"], "present")
        self.assertEqual(self.cell(page, TUE)["state"], "absent")
        self.assertContains(page, "erp-cal-day is-present")
        self.assertContains(page, "erp-cal-day is-absent")

    def test_instructional_day_without_submitted_record_is_not_recorded(self):
        page = self.page()
        self.assertEqual(self.cell(page, WED)["state"], "not_recorded")
        self.assertEqual(self.cell(page, WED)["label"], "Not recorded")
        # A DRAFT register is not officially recorded either, and never shown as a status.
        self.assertEqual(self.cell(page, THU)["state"], "not_recorded")

    def test_holiday_and_weekend_are_neither_absent_nor_not_recorded(self):
        page = self.page()
        for on_date in (HOLIDAY, SAT, SUN):
            with self.subTest(on_date=on_date):
                self.assertEqual(self.cell(page, on_date)["state"], "no_school")
                self.assertEqual(self.cell(page, on_date)["label"], "No school")

    def test_future_school_day_is_not_marked_not_recorded(self):
        self.assertEqual(self.cell(self.page(), date(2026, 10, 13))["state"], "upcoming")

    def test_cells_carry_text_not_just_colour(self):
        text = self.page().content.decode()
        for label in ("Present", "Absent", "Not recorded", "No school"):
            self.assertIn(f'erp-cal-text visually-hidden">{label}<', text)

    def test_date_before_enrolment_is_not_not_recorded(self):
        AcademicEnrollment.objects.filter(pk=self.asha_e.pk).update(start_date=WED)
        page = self.page()
        self.assertEqual(self.cell(page, date(2026, 10, 1))["state"], "not_enrolled")
        self.assertEqual(self.cell(page, MON)["state"], "not_enrolled")
        self.assertEqual(self.cell(page, WED)["state"], "not_recorded")

    def test_gap_between_placements_is_not_not_recorded(self):
        AcademicEnrollment.objects.filter(pk=self.asha_e.pk).update(
            end_date=THU, status=AcademicEnrollment.Status.COMPLETED)
        AcademicEnrollment.objects.create(
            student=self.asha, academic_year=self.year, class_grade=self.grade6,
            section=self.six_b, start_date=date(2026, 10, 12),
            status=AcademicEnrollment.Status.ACTIVE)
        page = self.page()
        self.assertEqual(self.cell(page, date(2026, 10, 9))["state"], "not_enrolled")
        self.assertEqual(self.cell(page, WED)["state"], "not_recorded")
        self.assertEqual(self.cell(page, date(2026, 10, 12))["state"], "not_recorded")

    def test_dates_outside_the_academic_year_are_not_not_recorded(self):
        AcademicYear.objects.filter(pk=self.year.pk).update(start_date=date(2026, 6, 15))
        page = self.page(month="2026-06")
        self.assertEqual(page.context["month"]["label"], "June 2026")
        self.assertEqual(self.cell(page, date(2026, 6, 10))["state"], "outside_year")


class CalendarPhoneLayoutTests(CalendarFixture, TestCase):
    """Below 576px erp.css turns every `.erp-content table:not(.erp-keep)` into a scroll box
    (`display: block`), which shrink-wraps the calendar columns to ~22px instead of filling
    the card. The calendar must keep opting out with `erp-keep`."""

    def test_calendar_table_opts_out_of_the_phone_block_rule(self):
        self.register(MON, AttendanceStatus.PRESENT)
        self.assertContains(self.page(), '<table class="erp-cal erp-keep">')

    def test_the_generic_phone_rule_still_exists_under_that_opt_out_name(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-content table:not(.erp-keep)", css)


class SummaryAndEmptyStateTests(CalendarFixture, TestCase):
    def test_no_attendance_data_shows_no_fake_percentage_or_calendar(self):
        page = self.page()
        self.assertContains(page, "No attendance has been recorded yet")
        self.assertNotContains(page, "0%")
        self.assertNotContains(page, "erp-cal-day")
        self.assertNotContains(page, "Absent")

    def test_summary_counts_and_official_note(self):
        self.register(MON, AttendanceStatus.PRESENT)
        self.register(TUE, AttendanceStatus.ABSENT)
        page = self.page()
        self.assertEqual(page.context["summary"]["total"], 2)
        self.assertContains(page, "50.0%")
        self.assertContains(page, "Only attendance the school has officially recorded is shown.")
        for label in ("Present", "Absent", "Not recorded"):
            self.assertContains(page, f"</span> {label}</li>")

    def test_existing_context_contract_is_preserved(self):
        self.register(MON, AttendanceStatus.PRESENT)
        page = self.page()
        for key in ("days", "summary", "year", "years"):
            self.assertIn(key, page.context)


class YearAndMonthNavigationTests(CalendarFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.old_year = AcademicYear.objects.create(
            name="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 3, 31))
        AcademicEnrollment.objects.create(
            student=self.asha, academic_year=self.old_year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2025, 6, 1), end_date=date(2026, 3, 31),
            status=AcademicEnrollment.Status.COMPLETED)

    def test_year_selection_and_default_month(self):
        page = self.portal.get(self.url, {"year": "2025-06-01"})
        self.assertEqual(page.context["year"], self.old_year)
        # The year has ended, so the default month is its last one.
        self.assertEqual(page.context["month"]["label"], "March 2026")
        self.assertContains(page, '<option value="2025-06-01" selected>')

    def test_current_year_defaults_to_this_month(self):
        page = self.portal.get(self.url)
        self.assertEqual(page.context["year"], self.year)
        self.assertEqual(page.context["month"]["label"], "October 2026")

    def test_month_links_stay_inside_the_selected_year(self):
        first = self.portal.get(self.url, {"year": "2026-06-01", "month": "2026-06"})
        self.assertIsNone(first.context["month"]["prev"])
        self.assertEqual(first.context["month"]["next"], "2026-07")
        last = self.portal.get(self.url, {"year": "2026-06-01", "month": "2027-03"})
        self.assertIsNone(last.context["month"]["next"])
        self.assertEqual(last.context["month"]["prev"], "2027-02")

    def test_navigation_links_keep_year_and_work_without_js(self):
        self.register(MON, AttendanceStatus.PRESENT)
        page = self.page(year="2026-06-01")
        self.assertContains(page, 'href="?year=2026-06-01&amp;month=2026-09"')
        self.assertContains(page, 'href="?year=2026-06-01&amp;month=2026-11"')
        self.assertNotContains(page, "onchange")

    def test_out_of_year_or_malformed_month_falls_back(self):
        for raw in ("2031-01", "1999-12", "garbage", "2026-13", ""):
            with self.subTest(raw=raw):
                page = self.portal.get(self.url, {"year": "2026-06-01", "month": raw})
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context["month"]["label"], "October 2026")


class AccessTests(CalendarFixture, TestCase):
    def test_cannot_view_another_students_attendance(self):
        other = reverse("portal:attendance", args=[self.bina_grant.public_id])
        self.assertEqual(self.portal.get(other, {"month": "2026-10"}).status_code, 404)

    def test_calendar_is_read_only(self):
        self.assertEqual(self.portal.post(self.url).status_code, 405)
