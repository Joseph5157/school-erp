"""Class timetable builders: any Section's periods with subject and teacher."""

import re
from datetime import date, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    ClassGrade,
    SchoolCalendarDay,
    Section,
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
    timetable_picker,
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


class PickerTests(TimetableDashboardFixture, TestCase):
    def grade7_section(self):
        grade7 = ClassGrade.objects.create(name="Grade 7", display_order=self.grade6.display_order + 1)
        offering = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=grade7, subject=self.maths.subject
        )
        return grade7, offering, Section.objects.create(class_grade=grade7, name="A")

    def test_mine_lists_class_teacher_section_first_then_subject_sections_once(self):
        self.class_teacher(self.rao, self.six_b)
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.assertEqual(timetable_picker(self.rao, [MONDAY])["mine"], [self.six_b, self.six_a])

    def test_all_classes_grouped_by_grade_in_display_order(self):
        grade7, offering7, seven_a = self.grade7_section()
        self.slot(section=seven_a, offering=offering7)
        self.slot(section=self.six_b, offering=self.sanskrit)
        self.slot()
        grades = timetable_picker(self.rao, [MONDAY])["grades"]
        self.assertEqual(
            [(g["grade"], g["sections"]) for g in grades],
            [(self.grade6, [self.six_a, self.six_b]), (grade7, [seven_a])],
        )

    def test_week_dates_include_sections_active_any_day(self):
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 10, 14))
        def flat(dates):
            return [s for g in timetable_picker(self.rao, dates)["grades"] for s in g["sections"]]

        self.assertEqual(flat([MONDAY]), [self.six_a])
        week = [MONDAY + timedelta(days=i) for i in range(6)]
        self.assertEqual(flat(week), [self.six_a, self.six_b])

    def test_sections_without_slots_are_not_listed(self):
        self.slot()
        grades = timetable_picker(self.rao, [MONDAY])["grades"]
        self.assertEqual([s for g in grades for s in g["sections"]], [self.six_a])


class ClassPageTests(TimetableDashboardFixture, TestCase):
    """/my/timetable/?section=<pk> (fixture business date is Monday 12 Oct 2026)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-timetable")

    def get(self, params=None, client=None):
        return (client or self.teacher).get(self.url, params or {})

    def chip(self, page):
        match = re.search(r'<a class="erp-tt-pick"[^>]*>(.*?)</a>', page.content.decode(), re.S)
        self.assertIsNotNone(match)
        return re.sub(r"<[^>]+>|\s+", " ", match.group(1)).strip()

    def six_a_day(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        self.slot(period=self.p2, offering=self.science)

    def test_chip_says_my_timetable_and_class_name(self):
        self.assertEqual(self.chip(self.get()), "My timetable")
        self.assertEqual(self.chip(self.get({"section": self.six_a.pk})), "Grade 6 - A")

    def test_class_day_cards_show_subject_and_teacher(self):
        self.six_a_day()
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        for client in (self.teacher, iyer):
            page = self.get({"section": self.six_a.pk}, client)
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context["section"], self.six_a)
            self.assertContains(page, "Mathematics")
            self.assertContains(page, _teacher_name(self.rao))
            self.assertContains(page, "Science")
            self.assertContains(page, "No teacher assigned")

    def test_class_week_boxes_and_key(self):
        self.six_a_day()
        page = self.get({"view": "week", "section": self.six_a.pk})
        pk = self.six_a.pk
        self.assertContains(
            page,
            f'<a href="{self.url}?date=2026-10-12&amp;section={pk}" '
            f'aria-label="Mathematics, {_teacher_name(self.rao)}, period 1, Monday 12 October">Mat</a>',
            html=False,
        )
        self.assertContains(page, '<span class="erp-tt-key-short">Mat</span> Mathematics')
        self.assertContains(page, '<span class="erp-tt-key-short">Sci</span> Science')

    def test_class_links_keep_section(self):
        self.six_a_day()
        pk = self.six_a.pk
        needle = f"section={pk}"
        day = self.get({"date": "2026-10-14", "section": pk}).content.decode()
        chips = re.findall(r'<a class="erp-tt-chip[^"]*" href="([^"]+)"', day)
        self.assertTrue(chips)
        for href in chips:
            self.assertIn(needle, href)
        self.assertIn(f"{self.url}?view=week&amp;date=2026-10-14&amp;{needle}", day)
        self.assertIn(f'class="erp-tt-today" href="{self.url}?{needle}"', day)
        week = self.get({"view": "week", "date": "2026-10-14", "section": pk}).content.decode()
        for label in ("Previous week", "Next week"):
            self.assertRegex(week, rf'href="[^"]*{needle}[^"]*" aria-label="{label}"')
        self.assertIn(f'href="{self.url}?date=2026-10-14&amp;{needle}"', week)
        sheet = re.search(r"<dialog.*?</dialog>", week, re.S).group(0)
        mine_link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>\s*My timetable', sheet)
        self.assertIsNotNone(mine_link)
        self.assertNotIn("section=", mine_link.group(1))

    def test_bad_section_values_fall_back_to_mine(self):
        for value in ("abc", "-1", "99999999", "1.5", ""):
            page = self.get({"section": value})
            self.assertEqual(page.status_code, 200, value)
            self.assertIsNone(page.context["section"], value)
            self.assertEqual(self.chip(page), "My timetable", value)

    def sheet_setup(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit)

    def test_sheet_lists_three_groups(self):
        self.sheet_setup()
        html = self.get({"view": "week", "date": "2026-10-14"}).content.decode()
        sheet = re.search(r"<dialog.*?</dialog>", html, re.S).group(0)
        for text in ("Choose a timetable", "My timetable", "My classes", "All classes"):
            self.assertIn(text, sheet)
        self.assertRegex(sheet, r'<label[^>]*for="(\w[\w-]*)"[^>]*>\s*Search classes')
        self.assertIn('type="search"', sheet)
        for section in (self.six_a, self.six_b):
            self.assertIn(
                f'href="{self.url}?view=week&amp;date=2026-10-14&amp;section={section.pk}"', sheet
            )

    def test_no_js_pick_list(self):
        self.sheet_setup()
        page = self.get({"pick": "1"})
        html = page.content.decode()
        self.assertTrue(page.context["pick"])
        outside = re.sub(r"<dialog.*?</dialog>", "", html, flags=re.S)
        for text in ("My classes", "All classes"):
            self.assertIn(text, outside)
        self.assertIn(f"section={self.six_a.pk}", outside)
        self.assertRegex(html, r'<a class="erp-tt-pick"[^>]*href="[^"]*\?pick=1&amp;')
        self.assertNotIn("All classes", re.sub(r"<dialog.*?</dialog>", "", self.get().content.decode(), flags=re.S))

    def test_class_view_writes_nothing(self):
        self.six_a_day()
        with CaptureQueriesContext(connection) as queries:
            self.get({"section": self.six_a.pk})
            self.get({"view": "week", "section": self.six_a.pk})
        writes = [
            q["sql"] for q in queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            and "django_session" not in q["sql"]  # the session middleware, not the view
        ]
        self.assertEqual(writes, [])

    def test_non_teacher_gets_403_with_section(self):
        params = {"section": self.six_a.pk}
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.get(params, self.client).status_code, 403)
        self.make_user("plain")
        plain = self.client_class()
        plain.login(username="plain", password="pass-12345")
        self.assertEqual(self.get(params, plain).status_code, 403)
        self.assertEqual(self.get(params, self.client_class()).status_code, 302)

    def test_existing_section_with_nothing_scheduled_stays_on_that_class(self):
        page = self.get({"section": self.six_b.pk})
        self.assertEqual(self.chip(page), "Grade 6 - B")
        self.assertContains(page, "No school timetable on this day.")
