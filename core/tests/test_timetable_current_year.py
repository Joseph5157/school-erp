"""Timetables follow the newest Academic Year that has started; archived classes leave the sheet."""

from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    SchoolCalendarDay,
    Section,
    Subject,
    TimetablePeriod,
)
from core.tests.test_phase5_teacher_home import MONDAY
from core.tests.test_ui_teacher_timetable import TimetableDashboardFixture
from core.timetable import teacher_timetable_on, teacher_week, timetable_picker

BEFORE_NEW_YEAR = date(2026, 9, 28)  # a Monday before the newer year starts on 1 Oct


class CurrentYearFixture(TimetableDashboardFixture):
    def setUp(self):
        super().setUp()
        self.new_year = AcademicYear.objects.create(
            name="Next", start_date=date(2026, 10, 1), end_date=date(2027, 9, 30)
        )
        self.new_p1 = TimetablePeriod.objects.create(
            academic_year=self.new_year, sequence=1, label="N1"
        )
        self.drawing = AcademicSubjectOffering.objects.create(
            academic_year=self.new_year, class_grade=self.grade6,
            subject=Subject.objects.create(name="Drawing"),
        )

    def new_year_slot(self, section):
        return self.slot(
            period=self.new_p1, offering=self.drawing, section=section,
            start_date=date(2026, 10, 1),
        )


class TeacherTimetableYearTests(CurrentYearFixture, TestCase):
    def rows(self, on_date, assignments):
        return teacher_timetable_on(
            assignments, on_date, lambda year: year.is_instructional_day(on_date)
        )

    def test_old_year_periods_stop_once_the_new_year_starts(self):
        mine = [self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1))]
        self.slot()                                    # old year, Monday P1
        self.new_year_slot(self.six_b)                 # the new year has a timetable too
        self.assertEqual(
            [r["subject"] for r in self.rows(BEFORE_NEW_YEAR, mine)], ["Mathematics"]
        )
        self.assertEqual(self.rows(MONDAY, mine), [])  # new year open, no row for Rao

    def test_new_year_without_a_timetable_yet_hides_the_old_one(self):
        # User-confirmed (2026-11-17): after rollover, nothing shows until the new grid is built.
        mine = [self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1))]
        self.slot()                                    # old year only; the new year has no slots
        self.assertIsNone(self.rows(MONDAY, mine))
        self.assertEqual(
            [r["subject"] for r in self.rows(BEFORE_NEW_YEAR, mine)], ["Mathematics"]
        )

    def test_new_year_periods_show(self):
        mine = [self.assign_between(self.rao, self.drawing, self.six_b, date(2026, 10, 1))]
        self.slot()
        self.new_year_slot(self.six_b)
        self.assertEqual([r["subject"] for r in self.rows(MONDAY, mine)], ["Drawing"])

    def test_new_year_holiday_closes_the_day_even_if_the_old_year_is_open(self):
        mine = [self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1))]
        self.slot()
        self.new_year_slot(self.six_b)
        SchoolCalendarDay.objects.create(
            academic_year=self.new_year, date=MONDAY, is_instructional=False, label="Diwali"
        )
        self.assertIsNone(self.rows(MONDAY, mine))
        week = teacher_week(self.rao, MONDAY, MONDAY, lambda y, d: y.is_instructional_day(d))
        self.assertFalse(week["days"][0]["is_school_day"])
        self.assertEqual(week["days"][0]["label"], "Holiday")


class PickerYearAndArchiveTests(CurrentYearFixture, TestCase):
    def listed(self, dates):
        picker = timetable_picker(self.rao, dates)
        return [s for group in picker["grades"] for s in group["sections"]], picker["mine"]

    def test_all_classes_lists_only_the_current_years_classes(self):
        self.slot(section=self.six_a)                  # old year only
        self.new_year_slot(self.six_b)                 # new year
        before, _ = self.listed([BEFORE_NEW_YEAR])
        after, _ = self.listed([MONDAY])
        self.assertEqual(before, [self.six_a])
        self.assertEqual(after, [self.six_b])

    def test_archived_classes_are_left_out_of_both_lists(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(section=self.six_a)
        self.new_year_slot(self.six_a)
        Section.objects.filter(pk=self.six_a.pk).update(
            archived_at=timezone.now(), archived_by=self.admin
        )
        listed, mine = self.listed([MONDAY])
        self.assertNotIn(self.six_a.pk, [s.pk for s in listed])
        self.assertNotIn(self.six_a.pk, [s.pk for s in mine])

    def test_an_archived_class_link_still_opens(self):
        self.slot(section=self.six_a)
        Section.objects.filter(pk=self.six_a.pk).update(
            archived_at=timezone.now(), archived_by=self.admin
        )
        page = self.teacher.get(
            reverse("core:my-timetable"), {"section": self.six_a.pk, "date": "2026-09-28"}
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["section"], self.six_a)
