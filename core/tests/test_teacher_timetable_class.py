"""Class timetable builders: any Section's periods with subject and teacher."""

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    SchoolCalendarDay,
    Subject,
    TimetablePeriod,
)
from core.tests.test_phase5_teacher_home import MONDAY, SUNDAY
from core.tests.test_ui_teacher_timetable import TimetableDashboardFixture
from core.timetable import (
    _teacher_name,
    class_timetable_on,
    class_week,
    short_subject_label,
)


class ClassTimetableTests(TimetableDashboardFixture, TestCase):
    def day_rows(self, section, when=MONDAY):
        return class_timetable_on(section, when, lambda year: year.is_instructional_day(when))

    def week(self, section, any_date=MONDAY, today=MONDAY):
        return class_week(section, any_date, today, lambda year, day: year.is_instructional_day(day))

    def test_short_subject_label(self):
        for name, short in [
            ("Mathematics", "Mat"), ("English", "Eng"), ("Hindi", "Hin"),
            ("  Art ", "Art"), ("PE", "PE"),
        ]:
            self.assertEqual(short_subject_label(name), short)

    def test_class_day_lists_every_period_with_subject_and_teacher(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.science, self.six_a)
        self.slot()
        self.slot(period=self.p2, offering=self.science)
        rows = self.day_rows(self.six_a)
        self.assertEqual(
            [(r["period"], r["subject"], r["teacher"]) for r in rows],
            [("P1", "Mathematics", self.rao), ("P2", "Science", self.iyer)],
        )
        self.assertEqual(
            [r["teacher_name"] for r in rows], [_teacher_name(self.rao), _teacher_name(self.iyer)]
        )
        self.assertEqual(rows[0]["short"], "Mat")
        self.assertEqual(rows[0]["sequence"], 1)
        self.assertEqual(rows[0]["section"], self.six_a)

    def test_class_day_shows_slots_without_a_teacher(self):
        self.slot()
        rows = self.day_rows(self.six_a)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["teacher"])
        self.assertEqual(rows[0]["teacher_name"], "No teacher assigned")

    def test_class_day_none_on_non_school_day(self):
        self.slot()
        self.assertIsNone(self.day_rows(self.six_a, SUNDAY))
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=MONDAY, is_instructional=False, label="Holiday"
        )
        self.assertIsNone(self.day_rows(self.six_a))

    def test_class_day_ignores_other_years_slots(self):
        other = AcademicYear.objects.create(
            name="Overlap", start_date=date(2026, 10, 1), end_date=date(2027, 9, 30)
        )
        period = TimetablePeriod.objects.create(academic_year=other, sequence=1, label="X1")
        offering = AcademicSubjectOffering.objects.create(
            academic_year=other, class_grade=self.grade6,
            subject=Subject.objects.create(name="Drawing"),
        )
        self.slot()
        self.slot(
            period=period, offering=offering, section=self.six_b, start_date=date(2026, 10, 1)
        )
        rows = self.day_rows(self.six_a)
        self.assertEqual([r["subject"] for r in rows], ["Mathematics"])
        self.assertEqual([r["subject"] for r in self.day_rows(self.six_b)], ["Drawing"])
        # 6-A's own year is closed that Monday; only the other year is open: nothing to show.
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=MONDAY, is_instructional=False, label="Holiday"
        )
        self.assertIsNone(self.day_rows(self.six_a))

    def test_class_week_teacher_changes_mid_week(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 13))
        self.assign_between(self.iyer, self.maths, self.six_a, date(2026, 10, 14))
        for weekday in range(5):
            self.slot(weekday=weekday)
        week = self.week(self.six_a)
        names = [day["rows"][0]["teacher"] for day in week["days"][:5]]
        self.assertEqual(names, [self.rao, self.rao, self.iyer, self.iyer, self.iyer])

    def test_class_week_key_and_short_labels(self):
        self.slot()
        self.slot(period=self.p2, offering=self.science, weekday=1)
        week = self.week(self.six_a)
        self.assertEqual(
            week["key"],
            [{"short": "Mat", "full": "Mathematics"}, {"short": "Sci", "full": "Science"}],
        )
        monday_rows = week["days"][0]["rows"]
        self.assertEqual(monday_rows[0]["short"], "Mat")
        self.assertEqual(week["monday"], MONDAY)
        self.assertFalse(week["is_empty"])
        self.assertTrue(week["contains_today"])
        self.assertEqual(week["heading"], "12 – 16 Oct 2026")
        self.assertEqual([len(row["cells"]) for row in week["grid"]], [5, 5])
        self.assertEqual(len(week["days"]), 5)  # Saturday hidden: not a school day

    def test_class_week_shows_saturday_when_a_school_day(self):
        self.year.set_saturdays_instructional(True)
        self.slot(weekday=5)
        week = self.week(self.six_a)
        self.assertEqual(len(week["days"]), 6)

    def test_class_week_query_count_does_not_grow_with_rows(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.science, self.six_a)
        for weekday in range(5):
            self.slot(weekday=weekday)
        with CaptureQueriesContext(connection) as small:
            self.week(self.six_a)
        for weekday in range(5):
            self.slot(weekday=weekday, period=self.p2, offering=self.science)
        with CaptureQueriesContext(connection) as large:
            week = self.week(self.six_a)
        self.assertEqual(sum(len(d["rows"]) for d in week["days"]), 10)
        self.assertEqual(len(large), len(small))
