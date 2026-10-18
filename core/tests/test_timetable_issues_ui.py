"""TDB-4E: the office Timetable issues report (ADR 0021 D6 R6 drift report, D6 R8)."""

import re
from datetime import date
from unittest import mock

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import timetable
from core.models import (
    AcademicYear,
    AssessmentTeacherAssignment,
    SchoolCalendarDay,
    TimetableSlot,
)
from core.tests.test_timetable_grid_ui import TODAY, GridFixture, pinned


class IssuesFixture(GridFixture):
    def issues_url(self, on=None, year=None):
        url = reverse("core:timetable-issues", args=[(year or self.year).pk])
        return f"{url}?date={on.isoformat()}" if on else url

    def raw_slot(self, **overrides):
        """Insert a slot directly: the lifecycle (rightly) blocks known teacher clashes."""
        values = {
            "period": self.p1, "weekday": 0, "section": self.six_a, "offering": self.maths,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return TimetableSlot.objects.create(**values)

    def make_clash(self, start=date(2026, 6, 1), end=date(2026, 9, 30), teacher=None):
        """Rao in 6A Maths and 6B Sanskrit, P1 Monday, over [start, end]."""
        teacher = teacher or self.rao
        self.assign_from(teacher, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(teacher, self.sanskrit, self.six_b, date(2026, 6, 1))
        a = self.raw_slot(start_date=start, end_date=end)
        b = self.raw_slot(section=self.six_b, offering=self.sanskrit, start_date=start,
                          end_date=end)
        return a, b

    def clashes(self, response):
        return response.context["clashes"]

    def missing(self, response):
        return response.context["missing"]


@pinned()
class ReportDateTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_defaults_to_today_inside_the_year(self):
        response = self.client.get(self.issues_url())
        self.assertEqual(response.context["report_date"], TODAY)
        self.assertContains(response, 'value="2026-10-19"')

    def test_defaults_to_year_start_when_today_is_outside_the_year(self):
        with pinned(date(2027, 5, 1)):
            self.assertEqual(self.client.get(self.issues_url()).context["report_date"],
                             self.year.start_date)
        with pinned(date(2026, 1, 1)):
            self.assertEqual(self.client.get(self.issues_url()).context["report_date"],
                             self.year.start_date)

    def test_a_chosen_date_inside_the_year_is_used_including_the_edges(self):
        for chosen in (date(2026, 6, 1), date(2026, 8, 3), date(2027, 3, 31)):
            response = self.client.get(self.issues_url(chosen))
            self.assertEqual(response.context["report_date"], chosen)

    def test_dates_just_outside_the_year_are_rejected_with_the_default_shown(self):
        for bad in ("2026-05-31", "2027-04-01", "garbage", ""):
            response = self.client.get(self.issues_url() + f"?date={bad}")
            self.assertEqual(response.status_code, 200, bad)
            self.assertEqual(response.context["report_date"], TODAY, bad)
            self.assertIn('aria-invalid="true"',
                          re.search(r'<input\b[^>]*\bid="id_date"[^>]*>',
                                    response.content.decode()).group(0), bad)

    def test_the_date_field_is_labelled_report_date(self):
        response = self.client.get(self.issues_url())
        self.assertContains(response, 'for="id_date"')
        self.assertContains(response, "Report date")

    def test_unknown_year_is_404(self):
        self.assertEqual(self.client.get(reverse("core:timetable-issues", args=[9999])
                                         ).status_code, 404)


@pinned()
class ClashReportTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_reuses_the_shared_clash_helper_for_the_chosen_year(self):
        with mock.patch("core.timetable.find_all_clashes",
                        wraps=timetable.find_all_clashes) as helper:
            self.client.get(self.issues_url())
        helper.assert_called_once_with(self.year)

    def test_empty_state_when_there_are_no_clashes(self):
        self.raw_slot()
        response = self.client.get(self.issues_url())
        self.assertEqual(self.clashes(response), [])
        self.assertContains(response, "No teacher clashes")

    def test_a_clash_lists_teacher_period_day_sections_subjects_and_dates(self):
        self.make_clash()
        row = self.clashes(self.client.get(self.issues_url(date(2026, 9, 15))))[0]
        self.assertEqual(row["teacher"], "rao")
        self.assertEqual(row["period"], "P1")
        self.assertEqual(row["weekday"], "Monday")
        self.assertEqual((row["start"], row["end"]), (date(2026, 6, 1), date(2026, 9, 30)))
        self.assertEqual({row["section_a"], row["section_b"]},
                         {str(self.six_a), str(self.six_b)})
        self.assertEqual({row["subject_a"], row["subject_b"]}, {"Mathematics", "Sanskrit"})

    def test_status_follows_the_report_date_at_the_boundaries(self):
        self.make_clash(start=date(2026, 7, 1), end=date(2026, 9, 30))

        def status(on):
            return self.clashes(self.client.get(self.issues_url(on)))[0]["status"]

        self.assertEqual(status(date(2026, 6, 30)), "upcoming")
        self.assertEqual(status(date(2026, 7, 1)), "in_force")
        self.assertEqual(status(date(2026, 9, 30)), "in_force")
        self.assertEqual(status(date(2026, 10, 1)), "ended")

    def test_a_historical_clash_stays_in_the_report(self):
        self.make_clash()
        response = self.client.get(self.issues_url(TODAY))
        self.assertEqual(len(self.clashes(response)), 1)
        self.assertEqual(self.clashes(response)[0]["status"], "ended")
        self.assertContains(response, "Ended")

    def test_a_historical_clash_survives_the_teacher_being_deactivated(self):
        self.make_clash()
        self.rao.is_active = False
        self.rao.save()
        row = self.clashes(self.client.get(self.issues_url()))[0]
        self.assertEqual(row["teacher"], "rao")

    def test_a_historical_clash_survives_removal_from_the_teachers_group(self):
        self.make_clash()
        self.rao.groups.remove(self.teachers)
        self.assertEqual(len(self.clashes(self.client.get(self.issues_url()))), 1)

    def test_a_teacher_handover_limits_the_clash_to_the_shared_dates(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2026, 6, 1), date(2026, 8, 31))
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 9, 1))
        self.raw_slot()
        self.raw_slot(section=self.six_b, offering=self.sanskrit)
        rows = self.clashes(self.client.get(self.issues_url()))
        self.assertEqual([(r["start"], r["end"]) for r in rows],
                         [(date(2026, 6, 1), date(2026, 8, 31))])

    def test_different_teachers_do_not_clash(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 6, 1))
        self.raw_slot()
        self.raw_slot(section=self.six_b, offering=self.sanskrit)
        self.assertEqual(self.clashes(self.client.get(self.issues_url())), [])

    def test_in_force_clashes_come_first_then_upcoming_then_ended(self):
        self.make_clash(start=date(2026, 6, 1), end=date(2026, 9, 30))  # ended
        self.raw_slot(period=self.p2, start_date=date(2026, 6, 1))
        self.raw_slot(period=self.p2, section=self.six_b, offering=self.sanskrit,
                      start_date=date(2026, 6, 1))  # in force from June to year end
        statuses = [r["status"] for r in self.clashes(self.client.get(self.issues_url()))]
        self.assertEqual(statuses, ["in_force", "ended"])

    def test_links_open_both_sections_at_the_right_date(self):
        a, b = self.make_clash(start=date(2026, 6, 1), end=date(2026, 12, 31))
        response = self.client.get(self.issues_url(date(2026, 10, 19)))
        for section in (self.six_a, self.six_b):
            self.assertContains(response, self.grid_url(section, on=date(2026, 10, 19)))
        # an ended clash links to the first day it occurred
        response = self.client.get(self.issues_url(date(2027, 2, 1)))
        for section in (self.six_a, self.six_b):
            self.assertContains(response, self.grid_url(section, on=date(2026, 6, 1)))

    def test_the_report_is_for_the_chosen_year_only(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31))
        self.make_clash()
        response = self.client.get(self.issues_url(year=other))
        self.assertEqual(self.clashes(response), [])
        self.assertContains(response, "No teacher clashes")


@pinned()
class MissingTeacherTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def rows(self, on=TODAY):
        return self.missing(self.client.get(self.issues_url(on)))

    def test_slot_with_no_assignment_is_listed_with_its_details_and_link(self):
        slot = self.raw_slot(weekday=2, offering=self.science)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["subject"], row["period"], row["weekday"]),
                         ("Science", "P1", "Wednesday"))
        self.assertEqual(row["section"], str(self.six_a))
        self.assertEqual(row["slot"], slot)
        self.assertContains(self.client.get(self.issues_url()), self.grid_url(on=TODAY))

    def test_assigned_slot_is_not_listed(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.raw_slot()
        self.assertEqual(self.rows(), [])

    def test_assignment_boundaries_decide_who_is_missing_on_the_report_date(self):
        self.raw_slot()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 22))
        self.assign_from(self.iyer, self.maths, self.six_a, date(2026, 10, 26))
        self.assertEqual(self.rows(date(2026, 10, 22)), [])       # Rao's last day (Thursday)
        self.assertEqual(len(self.rows(date(2026, 10, 23))), 1)   # the gap (Friday)
        self.assertEqual(self.rows(date(2026, 10, 26)), [])       # Iyer's first day (Monday)

    def test_a_future_assignment_does_not_cover_today(self):
        self.raw_slot()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 11, 2))
        self.assertEqual(len(self.rows()), 1)

    def test_an_assignment_for_another_section_does_not_count(self):
        self.assign_from(self.rao, self.maths, self.six_b, date(2026, 6, 1))
        self.raw_slot()
        self.assertEqual(len(self.rows()), 1)

    def test_an_assignment_for_another_offering_does_not_count(self):
        self.assign_from(self.rao, self.science, self.six_a, date(2026, 6, 1))
        self.raw_slot()
        self.assertEqual(len(self.rows()), 1)

    def test_only_slots_effective_on_the_report_date_are_listed(self):
        self.raw_slot(start_date=date(2026, 6, 1), end_date=date(2026, 9, 30))
        self.raw_slot(weekday=1, start_date=date(2026, 11, 2))
        self.raw_slot(weekday=2, start_date=date(2026, 6, 1))
        rows = self.rows()
        self.assertEqual([r["weekday"] for r in rows], ["Wednesday"])

    def test_a_former_teachers_assignment_still_counts_as_assigned(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.rao.is_active = False
        self.rao.save()
        self.rao.groups.remove(self.teachers)
        self.raw_slot()
        self.assertEqual(self.rows(), [])

    def test_rows_are_ordered_by_section_then_period_then_weekday(self):
        self.raw_slot(section=self.six_b, offering=self.sanskrit)
        self.raw_slot(period=self.p2, weekday=1)
        self.raw_slot(weekday=3)
        order = [(r["section"], r["period"], r["weekday"]) for r in self.rows()]
        self.assertEqual(order, [(str(self.six_a), "P1", "Thursday"),
                                 (str(self.six_a), "P2", "Tuesday"),
                                 (str(self.six_b), "P1", "Monday")])

    def test_empty_states_are_truthful(self):
        response = self.client.get(self.issues_url())
        self.assertContains(response, "No slots are effective on this date")
        self.assertNotContains(response, "has a teacher")
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.raw_slot()
        response = self.client.get(self.issues_url())
        self.assertContains(response, "Every slot effective on this date has a teacher")

    def test_a_year_with_no_slots_at_all_says_so(self):
        response = self.client.get(self.issues_url())
        self.assertEqual(self.missing(response), [])
        self.assertContains(response, "No teacher clashes")


@pinned()
class NonSchoolDayTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()
        self.raw_slot()  # unassigned, effective all year

    def test_a_sunday_says_not_a_school_day_and_reports_no_missing_teacher_gaps(self):
        response = self.client.get(self.issues_url(date(2026, 10, 18)))
        self.assertContains(response, "Not a school day")
        self.assertIsNone(self.missing(response))
        self.assertNotContains(response, "has no teacher")

    def test_a_saturday_without_instructional_saturdays_is_not_a_school_day(self):
        response = self.client.get(self.issues_url(date(2026, 10, 24)))
        self.assertContains(response, "Not a school day")
        self.assertIsNone(self.missing(response))

    def test_a_saturday_that_is_instructional_reports_gaps(self):
        self.year.saturdays_instructional = True
        self.year.save()
        response = self.client.get(self.issues_url(date(2026, 10, 24)))
        self.assertNotContains(response, "Not a school day")
        self.assertEqual(len(self.missing(response)), 1)

    def test_a_calendar_holiday_is_not_a_school_day(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 10, 20), is_instructional=False,
            label="Diwali")
        response = self.client.get(self.issues_url(date(2026, 10, 20)))
        self.assertContains(response, "Not a school day")
        self.assertIsNone(self.missing(response))

    def test_a_school_day_is_reported_normally(self):
        response = self.client.get(self.issues_url(date(2026, 10, 19)))
        self.assertNotContains(response, "Not a school day")
        self.assertEqual(len(self.missing(response)), 1)

    def test_clashes_are_still_listed_on_a_non_school_day(self):
        TimetableSlot.objects.all()._raw_delete("default")  # started rows are guarded
        self.make_clash(start=date(2026, 6, 1), end=date(2026, 12, 31))
        response = self.client.get(self.issues_url(date(2026, 10, 18)))
        self.assertContains(response, "Not a school day")
        self.assertEqual(len(self.clashes(response)), 1)


@pinned()
class PermissionAndScopeTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()
        self.count = 0

    def user_with(self, *codenames):
        self.count += 1
        user = self.make_user(f"issues{self.count}")
        user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core", codename__in=codenames))
        return user

    def test_needs_slot_and_period_view_permissions(self):
        for held, expected in (
            ([], 403),
            (["view_timetableslot"], 403),
            (["view_timetableperiod"], 403),
            (["add_timetableslot", "change_timetableslot", "delete_timetableslot"], 403),
            (["view_timetableslot", "view_timetableperiod"], 200),
        ):
            client = self.client_class()
            client.force_login(self.user_with(*held))
            self.assertEqual(client.get(self.issues_url()).status_code, expected, held)

    def test_teacher_is_denied(self):
        client = self.client_class()
        client.force_login(self.rao)
        self.assertEqual(client.get(self.issues_url()).status_code, 403)

    def test_anonymous_is_redirected_to_sign_in(self):
        response = self.client_class().get(self.issues_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_the_report_is_read_only(self):
        self.make_clash()
        before = TimetableSlot.objects.count(), AssessmentTeacherAssignment.objects.count()
        response = self.client.post(self.issues_url(), {"date": "2026-10-19"})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            (TimetableSlot.objects.count(), AssessmentTeacherAssignment.objects.count()), before)

    def test_the_page_has_no_repair_or_assignment_controls(self):
        self.make_clash()
        self.raw_slot(period=self.p2, weekday=3, offering=self.science)
        html = self.client.get(self.issues_url(date(2026, 9, 15))).content.decode()
        self.assertNotIn("teacher-assignment", html)
        self.assertNotIn("/teachers/", html.split("<main")[1])
        self.assertNotIn('method="post"', html.split("<main")[1])
        self.assertNotIn("/timetable/slots/", html)

    def test_the_index_links_to_the_report(self):
        response = self.client.get(reverse("core:timetable-index"))
        self.assertContains(response, self.issues_url())

    def test_index_hides_the_report_link_without_slot_view(self):
        client = self.client_class()
        client.force_login(self.user_with("view_timetableperiod"))
        self.assertNotContains(client.get(reverse("core:timetable-index")), "timetable/issues")

    def test_no_teacher_dashboard_timetable_yet(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.raw_slot()
        client = self.client_class()
        client.force_login(self.rao)
        page = client.get(reverse("core:my-home")).content.decode().lower()
        self.assertNotIn("timetable", page)


@pinned()
class IssuesQueryTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(self.issues_url(TODAY)).status_code, 200)
        return len(ctx)

    def test_query_count_is_constant_as_clashes_and_gaps_grow(self):
        self.make_clash()
        self.raw_slot(period=self.p1, weekday=5, offering=self.science)
        small = self.count()
        for weekday in range(1, 5):
            self.make_clash_cell(self.p1, weekday)
            self.make_clash_cell(self.p2, weekday)
        self.raw_slot(period=self.p2, weekday=5, offering=self.science)
        self.raw_slot(period=self.p1, weekday=5, offering=self.science, section=self.six_b)
        self.raw_slot(period=self.p2, weekday=5, offering=self.science, section=self.six_b)
        self.assertEqual(self.count(), small)

    def make_clash_cell(self, period, weekday):
        self.raw_slot(period=period, weekday=weekday, start_date=date(2026, 6, 1))
        self.raw_slot(period=period, weekday=weekday, section=self.six_b,
                      offering=self.sanskrit, start_date=date(2026, 6, 1))


@pinned()
class IssuesAccessibilityTests(IssuesFixture, TestCase):
    def setUp(self):
        self.build_grid()

    def test_tables_scroll_in_labelled_regions(self):
        self.make_clash(end=date(2026, 12, 31))
        self.raw_slot(period=self.p2, weekday=3, offering=self.science)
        html = self.client.get(self.issues_url()).content.decode()
        self.assertIn('class="erp-table-scroll" role="region" aria-label="Teacher clashes"', html)
        self.assertIn('class="erp-table-scroll" role="region" aria-label="Slots with no teacher"',
                      html)

    def test_date_error_uses_the_summary_pattern(self):
        response = self.client.get(self.issues_url() + "?date=2030-01-01")
        html = response.content.decode()
        self.assertIn('class="erp-form-errors" role="alert"', html)
        self.assertIn('href="#id_date"', html)
        self.assertIn("autofocus", re.search(r'<input\b[^>]*\bid="id_date"[^>]*>', html).group(0))
