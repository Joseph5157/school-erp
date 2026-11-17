"""TDB-5 Teacher dashboard timetable (ADR 0021 D10, amended 2026-11-17).

Today's rows are still built for the dashboard, but they are shown as one Timetable card that
counts them and links to the Timetable page, not as a list of periods.
"""

import re
from contextlib import ExitStack
from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import authorization
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    ClassGrade,
    SchoolCalendarDay,
    Section,
    Subject,
    TimetablePeriod,
    TimetableSlot,
)
from core.tests.test_phase5_teacher_home import MONDAY, SUNDAY, on
from core.tests.test_ui_teacher_dashboard import DashboardFixture

TUESDAY = date(2026, 10, 13)
NO_PERIODS = "No periods for you today"
NO_SCHOOL = "No school today"
NO_TIMETABLE = "No timetable for today"


class TimetableDashboardFixture(DashboardFixture):
    def setUp(self):
        super().setUp()
        self.p1 = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.p2 = TimetablePeriod.objects.create(academic_year=self.year, sequence=2, label="P2")
        self.science = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Science"),
        )

    def slot(self, **overrides):
        values = {
            "period": self.p1, "weekday": 0, "section": self.six_a, "offering": self.maths,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return TimetableSlot.create(**values)

    def assign_between(self, teacher, offering, section, start, end=None):
        return AssessmentTeacherAssignment.objects.create(
            teacher=teacher, offering=offering, section=section, start_date=start, end_date=end)

    def day(self, when):
        """Pin the business date for this request (nested over the fixture's Monday)."""
        stack = ExitStack()
        for patch in on(when):
            stack.enter_context(patch)
        return stack

    def shown(self, page=None):
        page = page or self.page()
        return page.context["timetable_rows"]

    def labels(self, page=None):
        rows = self.shown(page)
        return None if rows is None else [
            f"{r['period']} · {r['section']} · {r['subject']}" for r in rows]

    def card_html(self, page):
        html = page.content.decode()
        return html.split('class="erp-tt-entry"')[1].split("</a>")[0]


class FilteringTests(TimetableDashboardFixture, TestCase):
    def test_only_the_signed_in_teachers_own_slots_for_today_are_shown(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.sanskrit, self.six_b)
        self.slot()                                                       # Rao's, Monday
        self.slot(section=self.six_b, offering=self.sanskrit)             # Iyer's, Monday
        self.slot(weekday=1, period=self.p2)                              # Rao's, Tuesday
        self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Mathematics"])

    def test_the_weekday_must_match_today(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=1)
        self.assertEqual(self.labels(), [])                    # Monday: a timetable, no row
        with self.day(TUESDAY):
            self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Mathematics"])

    def test_the_card_sits_between_the_overview_and_the_assignments(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.page()
        html = page.content.decode()
        self.assertEqual(html.count("<h1"), 1)
        self.assertIn("1 period today", self.card_html(page))
        self.assertLess(html.index('id="day-overview"'), html.index('class="erp-tt-entry"'))
        self.assertLess(html.index('class="erp-tt-entry"'), html.index('id="day-assignments"'))

    def test_no_period_list_clock_times_free_periods_or_placeholders_on_the_dashboard(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        self.slot(period=self.p2, weekday=3)  # other weekday: must not become a free period
        page = self.page()
        html = page.content.decode()
        card = self.card_html(page)
        self.assertNotIn("P1 &middot;", html)          # the list is gone; only a count remains
        self.assertNotIn('id="day-timetable"', html)
        self.assertNotRegex(card, r"\d{1,2}:\d{2}")
        for word in ("Free", "free", "Break", "Lunch", "Room", "placeholder"):
            self.assertNotIn(word, card)
        self.assertIn("1 period today", card)

    def test_a_teacher_with_no_assignments_sees_no_periods_when_a_timetable_exists(self):
        self.assign(self.iyer, self.maths, self.six_a)
        self.slot()
        page = self.page()
        self.assertEqual(self.labels(page), [])
        self.assertIn(NO_PERIODS, self.card_html(page))


class OrderingTests(TimetableDashboardFixture, TestCase):
    def test_rows_follow_period_sequence_not_label_or_creation_order(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        late = TimetablePeriod.objects.create(academic_year=self.year, sequence=3, label="A-last")
        TimetablePeriod.objects.filter(pk=self.p1.pk).update(label="Z-first")
        self.slot(period=late)
        self.slot(period=self.p2, section=self.six_b, offering=self.sanskrit)
        self.slot(period=self.p1)
        self.assertEqual(
            self.labels(),
            ["Z-first · Grade 6 - A · Mathematics", "P2 · Grade 6 - B · Sanskrit",
             "A-last · Grade 6 - A · Mathematics"],
        )

    def test_the_card_counts_every_period_today(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.slot(period=self.p2)
        self.slot(period=self.p1, section=self.six_b, offering=self.sanskrit)
        self.assertIn("2 periods today", self.card_html(self.page()))


class EffectiveDateTests(TimetableDashboardFixture, TestCase):
    def test_handover_boundary_follows_the_dated_assignment(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 11))
        self.assign_between(self.iyer, self.maths, self.six_a, date(2026, 10, 12))
        self.slot()
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        # Monday 12 Oct: Iyer's first day
        self.assertEqual(self.labels(), [])
        self.assertEqual(self.labels(iyer.get(self.url)), ["P1 · Grade 6 - A · Mathematics"])
        # Monday 5 Oct: Rao's last full Monday
        with self.day(date(2026, 10, 5)):
            self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Mathematics"])
            self.assertEqual(self.labels(iyer.get(self.url)), [])

    def test_the_teacher_is_the_assignment_on_the_day_not_a_stored_slot_teacher(self):
        self.assertNotIn("teacher", {f.name for f in TimetableSlot._meta.fields})
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 11))
        self.slot()
        self.assertEqual(self.labels(), [])

    def test_ended_and_not_yet_started_slots_are_excluded_with_inclusive_edges(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.science, self.six_a)
        self.slot(end_date=date(2026, 10, 11))                                   # ended yesterday
        self.slot(period=self.p2, start_date=date(2026, 10, 13))                 # starts tomorrow
        self.assertIsNone(self.shown())   # neither is effective today: no timetable today
        self.slot(offering=self.science, weekday=0, period=self.p1,
                  start_date=date(2026, 10, 12), end_date=date(2026, 10, 12))   # exactly today
        self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Science"])
        with self.day(date(2026, 10, 19)):   # a week on: today's slot is gone, the later one began
            self.assertEqual(self.labels(), ["P2 · Grade 6 - A · Mathematics"])

    def test_an_open_ended_slot_stops_at_the_end_of_its_academic_year(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        with self.day(date(2027, 3, 29)):                                         # a Monday
            self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Mathematics"])
        with self.day(date(2027, 4, 5)):                                          # after the year
            self.assertIsNone(self.shown())

    def test_an_unassigned_slot_never_appears(self):
        self.slot()
        self.assign(self.iyer, self.maths, self.six_b)
        self.slot(section=self.six_b)
        page = self.page()
        self.assertEqual(self.labels(page), [])
        card = self.card_html(page)
        self.assertIn(NO_PERIODS, card)
        self.assertNotIn("Mathematics", card)

    def test_a_future_assignment_does_not_show_a_row_today(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 10, 13))
        self.slot()
        self.assertEqual(self.labels(), [])


class VisibilityTests(TimetableDashboardFixture, TestCase):
    def test_no_timetable_configured_still_shows_the_card_saying_so(self):
        self.assign(self.rao, self.maths, self.six_a)
        page = self.page()
        self.assertIsNone(self.shown(page))
        card = self.card_html(page)
        self.assertIn(NO_TIMETABLE, card)
        self.assertNotIn(NO_SCHOOL, card)

    def test_a_slot_that_is_not_effective_today_does_not_count_as_a_timetable(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(start_date=date(2026, 10, 13))
        self.slot(period=self.p2, end_date=date(2026, 10, 11))
        self.assertIsNone(self.shown())

    def test_an_instructional_day_with_a_timetable_and_no_rows_shows_no_periods(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=3)   # effective today but on Thursdays only
        page = self.page()
        self.assertEqual(self.labels(page), [])
        self.assertIn(NO_PERIODS, self.card_html(page))

    def test_a_non_instructional_day_keeps_the_card_and_says_no_school(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        with self.day(SUNDAY):
            page = self.page()
            self.assertIsNone(self.shown(page))
            self.assertIn(NO_SCHOOL, self.card_html(page))
            self.assertIn("Not a school day", page.content.decode())

    def test_a_holiday_on_a_normal_weekday_keeps_the_card_and_says_no_school(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        SchoolCalendarDay.objects.create(academic_year=self.year, date=MONDAY,
                                         is_instructional=False, label="Holiday")
        page = self.page()
        self.assertIsNone(self.shown(page))
        card = self.card_html(page)
        self.assertIn(NO_SCHOOL, card)
        self.assertNotIn(NO_PERIODS, card)

    def test_a_working_saturday_shows_that_days_slots(self):
        self.year.saturdays_instructional = True
        self.year.save()
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=5)
        with self.day(date(2026, 10, 17)):
            self.assertEqual(self.labels(), ["P1 · Grade 6 - A · Mathematics"])

    def test_an_exceptional_sunday_never_guesses_a_pattern(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        SchoolCalendarDay.objects.create(academic_year=self.year, date=SUNDAY,
                                         is_instructional=True, label="Make-up day")
        with self.day(SUNDAY):
            self.assertEqual(self.labels(), [])

    def test_existing_dashboard_content_is_unchanged_when_the_section_is_hidden(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        html = self.page().content.decode()
        for marker in ('id="day-overview"', 'id="day-assignments"', 'class="erp-tiles"',
                       "Subjects I teach", "Class teacher"):
            self.assertIn(marker, html)


class MultipleAcademicYearTests(TimetableDashboardFixture, TestCase):
    def second_year(self, holiday=False):
        other = AcademicYear.objects.create(
            name="2026-27 (extension)", start_date=date(2026, 10, 1), end_date=date(2027, 3, 31))
        grade = ClassGrade.objects.create(name="Grade 8")
        section = Section.objects.create(class_grade=grade, name="A")
        offering = AcademicSubjectOffering.objects.create(
            academic_year=other, class_grade=grade, subject=Subject.objects.create(name="History"))
        period = TimetablePeriod.objects.create(academic_year=other, sequence=1, label="Q1")
        self.assign_between(self.rao, offering, section, date(2026, 10, 1))
        TimetableSlot.create(period=period, weekday=0, section=section, offering=offering,
                             start_date=date(2026, 10, 1))
        if holiday:
            SchoolCalendarDay.objects.create(academic_year=other, date=MONDAY,
                                             is_instructional=False, label="Closure")
        return other

    # ADR 0021 D10 amendment 2026-11-17 (current year): once a newer Academic Year has started,
    # only its timetable shows; the older year's periods stop even if its dates overlap.

    def test_the_newest_started_year_decides_the_day(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        self.second_year(holiday=True)
        self.assertIsNone(self.shown())                # newest year closed today: no timetable

    def test_when_both_years_are_open_only_the_newest_years_rows_show(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(period=self.p2)
        self.second_year()
        self.assertEqual(self.labels(), ["Q1 · Grade 8 - A · History"])

    def test_a_year_that_is_closed_today_does_not_make_a_timetable_for_another(self):
        other = self.second_year(holiday=True)
        self.assertIsNotNone(other)
        # Year 1 has no slots; year 2's only timetable is closed today: nothing to show.
        self.assertIsNone(self.shown())

    def test_a_year_with_a_timetable_that_is_not_effective_yet_is_ignored(self):
        later = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31))
        period = TimetablePeriod.objects.create(academic_year=later, sequence=1, label="P1")
        offering = AcademicSubjectOffering.objects.create(
            academic_year=later, class_grade=self.grade6,
            subject=Subject.objects.create(name="Art"),
        )
        TimetableSlot.create(period=period, weekday=0, section=self.six_a, offering=offering,
                             start_date=date(2027, 6, 7))
        self.assign(self.rao, self.maths, self.six_a)
        self.assertIsNone(self.shown())


class AuthorizationIndependenceTests(TimetableDashboardFixture, TestCase):
    def test_a_slot_without_an_assignment_grants_nothing(self):
        self.slot()
        self.assertFalse(authorization.can_enter_results(self.rao, self.maths, self.six_a))
        page = self.page()
        self.assertEqual(self.labels(page), [])
        self.assertEqual(page.context["subject_rows"], [])
        self.assertIn("No subjects are assigned to you today.", page.content.decode())

    def test_an_assignment_without_a_slot_keeps_access_and_shows_no_row(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(section=self.six_b, offering=self.sanskrit)   # a timetable exists elsewhere
        self.assign(self.iyer, self.sanskrit, self.six_b)
        page = self.page()
        self.assertTrue(authorization.can_enter_results(self.rao, self.maths, self.six_a))
        self.assertEqual(self.labels(page), [])
        self.assertEqual([r["subject"] for r in page.context["subject_rows"]], ["Mathematics"])

    def test_adding_or_removing_slots_changes_no_teaching_assignment_rows(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.class_teacher(self.rao, self.six_a)
        before = self.page().context
        rows_before = (before["subject_rows"], before["class_rows"])
        slot = self.slot()
        slot.end(date(2026, 10, 12))
        after = self.page().context
        self.assertEqual((after["subject_rows"], after["class_rows"]), rows_before)

    def test_an_ended_assignment_means_the_slot_is_no_longer_theirs(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 9, 30))
        self.slot()
        self.assertEqual(self.labels(), [])


class QueryCountTests(TimetableDashboardFixture, TestCase):
    def count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.teacher.get(self.url).status_code, 200)
        return len(ctx.captured_queries)

    def test_queries_do_not_grow_with_timetable_rows(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        small = self.count()
        for number, name in enumerate(("C", "D", "E"), start=3):
            section = Section.objects.create(class_grade=self.grade6, name=name)
            period = TimetablePeriod.objects.create(
                academic_year=self.year, sequence=number, label=f"P{number}")
            for offering in (self.maths, self.science):
                self.assign(self.rao, offering, section)
            self.slot(section=section, period=period)                    # Monday: a row
            self.slot(section=section, period=period, weekday=3, offering=self.science)
        self.assertEqual(self.count(), small)
        self.assertEqual(len(self.shown()), 4)


class TeacherPagesAcceptanceTests(TimetableDashboardFixture, TestCase):
    """TDB-6: the finished dashboard shows the timetable once and offers no office controls."""

    OFFICE = ("/timetable", "/slots/", "/academic-years", "/subject-offerings", "/overview",
              "/teachers/", "/classes/")

    def test_no_teacher_page_links_to_office_timetable_or_setup_screens(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        for name in ("my-home", "my-students", "my-assessments", "my-results"):
            page = self.teacher.get(reverse(f"core:{name}"))
            self.assertEqual(page.status_code, 200, name)
            hrefs = re.findall(r'href="([^"]+)"', page.content.decode())
            own = reverse("core:my-timetable")   # the teacher's own page, not an office screen
            leaked = [h for h in hrefs
                      if not h.startswith(own) and any(part in h for part in self.OFFICE)]
            self.assertEqual(leaked, [], name)

    def test_the_dashboard_has_one_h1_and_no_timetable_list_heading(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        html = self.page().content.decode()
        self.assertEqual(html.count("<h1"), 1)
        self.assertEqual(html.count("Today's timetable"), 0)
        self.assertEqual(html.count('class="erp-tt-entry"'), 1)
        headings = re.findall(r"<h2[^>]*>([^<]+)</h2>", html)
        self.assertEqual(headings[:2], ["Today overview", "Teaching assignments"])


class TimetableCardTests(TimetableDashboardFixture, TestCase):
    """The My day Timetable card: one link to the Timetable page, shown every day."""

    def test_the_card_links_to_the_timetable_page(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        card = self.card_html(self.page())
        self.assertIn(f'href="{reverse("core:my-timetable")}"', card)
        self.assertIn("Timetable", card)
        self.assertNotIn("Full timetable", self.page().content.decode())

    def test_one_period_is_singular_and_more_are_plural(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        self.assertIn("1 period today", self.card_html(self.page()))
        self.slot(period=self.p2)
        self.assertIn("2 periods today", self.card_html(self.page()))

    def test_a_class_teacher_with_no_subjects_still_gets_the_card(self):
        self.class_teacher(self.rao, self.six_a)
        page = self.page()
        self.assertIn(f'href="{reverse("core:my-timetable")}"', self.card_html(page))

    def test_the_card_text_is_not_a_heading(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        card = self.card_html(self.page())
        self.assertNotRegex(card, r"<h\d")
