"""Timetable page: rows for any date (ADR 0021 D10)."""

import re
from datetime import date, timedelta

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import SchoolCalendarDay
from core.navigation import teacher_tabs
from core.tests.test_phase5_teacher_home import MONDAY, SUNDAY
from core.tests.test_ui_teacher_timetable import TUESDAY, TimetableDashboardFixture
from core.timetable import (
    date_strip,
    parse_timetable_date,
    teacher_timetable_on,
    teacher_week,
    todays_teacher_timetable,
)


class TimetableRowsOnTests(TimetableDashboardFixture, TestCase):
    def rows(self, on_date, assignments):
        return teacher_timetable_on(
            assignments, on_date, lambda year: year.is_instructional_day(on_date)
        )

    def test_rows_for_a_given_date_match_that_dates_weekday(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()                                    # Monday
        self.slot(weekday=1, period=self.p2)           # Tuesday
        rows = self.rows(TUESDAY, mine)
        self.assertEqual([r["period"] for r in rows], ["P2"])
        self.assertEqual([r["subject"] for r in rows], ["Mathematics"])

    def test_rows_carry_the_period_sequence(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        self.assertEqual(self.rows(MONDAY, mine)[0]["sequence"], 1)

    def test_none_when_the_date_is_not_an_instructional_day(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        self.assertIsNone(self.rows(SUNDAY, mine))

    def test_todays_wrapper_still_returns_the_same_rows(self):
        mine = [self.assign(self.rao, self.maths, self.six_a)]
        self.slot()
        def check(year):
            return year.is_instructional_day(MONDAY)

        self.assertEqual(
            todays_teacher_timetable(mine, MONDAY, check),
            teacher_timetable_on(mine, MONDAY, check),
        )


class ParseTimetableDateTests(SimpleTestCase):
    TODAY = date(2026, 11, 17)

    def test_parse_accepts_a_valid_date_inside_the_window(self):
        self.assertEqual(
            parse_timetable_date("2026-11-20", self.TODAY), date(2026, 11, 20)
        )

    def test_parse_falls_back_to_today_for_garbage_empty_none_and_out_of_window(self):
        today = self.TODAY
        for raw in ("abc", "", None, "2026-13-40", "9999-12-31", "0001-01-01"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_timetable_date(raw, today), today)
        low = today - timedelta(days=366)
        high = today + timedelta(days=366)
        self.assertEqual(parse_timetable_date(low.isoformat(), today), low)
        self.assertEqual(parse_timetable_date(high.isoformat(), today), high)
        past = (low - timedelta(days=1)).isoformat()
        future = (high + timedelta(days=1)).isoformat()
        self.assertEqual(parse_timetable_date(past, today), today)
        self.assertEqual(parse_timetable_date(future, today), today)


class DateStripTests(SimpleTestCase):
    TODAY = date(2026, 11, 17)  # Tuesday

    def test_strip_has_30_chips_monday_to_saturday_no_sundays(self):
        chips = date_strip(self.TODAY, self.TODAY)
        self.assertEqual(len(chips), 30)
        self.assertEqual(chips[0]["date"], date(2026, 11, 2))   # Monday, 2 weeks back
        self.assertEqual(chips[-1]["date"], date(2026, 12, 5))  # Saturday, 2 weeks on
        self.assertEqual(
            [c["weekday"] for c in chips[:6]],
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        )
        self.assertNotIn(6, [c["date"].weekday() for c in chips])
        self.assertEqual(chips[12]["day"], 16)

    def test_strip_marks_exactly_one_selected_and_one_today_and_none_when_today_is_outside(self):
        selected = date(2026, 11, 19)
        chips = date_strip(selected, self.TODAY)
        self.assertEqual(
            [c["date"] for c in chips if c["is_selected"]], [selected]
        )
        self.assertEqual(
            [c["date"] for c in chips if c["is_today"]], [self.TODAY]
        )
        far = date_strip(date(2026, 11, 19), date(2027, 6, 1))
        self.assertEqual(sum(c["is_today"] for c in far), 0)
        self.assertEqual(sum(c["is_selected"] for c in far), 1)

    def test_strip_marks_month_start_on_first_chip_of_a_new_month(self):
        chips = date_strip(self.TODAY, self.TODAY)
        self.assertEqual(
            [c["date"] for c in chips if c["month_start"]], [date(2026, 12, 1)]
        )

    def test_strip_for_a_sunday_selection_still_builds(self):
        sunday = date(2026, 11, 22)
        chips = date_strip(sunday, self.TODAY)
        self.assertEqual(len(chips), 30)
        self.assertFalse(any(c["is_selected"] for c in chips))


class TimetablePageTests(TimetableDashboardFixture, TestCase):
    """The /my/timetable/ page (fixture business date is Monday 12 Oct 2026)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-timetable")

    def get(self, date_value=None, client=None):
        client = client or self.teacher
        return client.get(self.url, {"date": date_value} if date_value is not None else {})

    def test_teacher_sees_own_periods_for_the_chosen_date(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=1, period=self.p2)           # Tuesday P2
        tue = self.get("2026-10-13")
        self.assertEqual(tue.status_code, 200)
        self.assertEqual(
            [r["period"] for r in tue.context["rows"]], ["P2"]
        )
        self.assertContains(tue, "Grade 6 - A")
        self.assertContains(tue, "Mathematics")
        self.assertContains(tue, "Tuesday, 13 October 2026")
        self.assertEqual(self.get("2026-10-12").context["rows"], [])
        self.assertContains(
            self.get("2026-10-12"), "No periods scheduled for you on this day."
        )

    def test_default_date_is_today_with_no_query(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.get()
        self.assertEqual(page.context["selected"], MONDAY)
        self.assertEqual(page.context["today"], MONDAY)
        self.assertTrue(page.context["is_today"])
        self.assertEqual([r["period"] for r in page.context["rows"]], ["P1"])
        self.assertContains(page, "Monday, 12 October 2026")
        self.assertContains(page, "‹ My day")
        self.assertEqual(page.content.decode().count("<h1"), 1)

    def test_bad_date_values_load_today_not_500(self):
        for raw in ("abc", "", "2026-13-40", "9999-12-31", "0001-01-01"):
            with self.subTest(raw=raw):
                page = self.get(raw)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context["selected"], MONDAY)

    def test_sunday_shows_non_school_sentence_and_strip(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.get(SUNDAY.isoformat())
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.context["rows"])
        self.assertContains(page, "No school timetable on this day.")
        self.assertContains(page, 'aria-label="Pick a day"')
        self.assertEqual(len(page.context["strip"]), 30)

    def test_no_assignments_shows_empty_sentence(self):
        self.slot()
        page = self.get()
        self.assertEqual(page.context["rows"], [])
        self.assertContains(page, "No periods scheduled for you on this day.")

    def test_no_assignments_on_a_sunday_shows_non_school_sentence(self):
        self.slot()
        page = self.get(SUNDAY.isoformat())
        self.assertIsNone(page.context["rows"])
        self.assertContains(page, "No school timetable on this day.")

    def test_chips_carry_full_date_labels(self):
        html = self.get("2026-10-13").content.decode()
        selected = re.search(r'<a[^>]*aria-current="date"[^>]*>', html).group(0)
        self.assertIn('aria-label="Tuesday 13 October 2026"', selected)
        self.assertIn('aria-label="Monday 28 September 2026"', html)

    def test_holiday_shows_non_school_sentence(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=MONDAY, is_instructional=False, label="Holiday"
        )
        page = self.get()
        self.assertIsNone(page.context["rows"])
        self.assertContains(page, "No school timetable on this day.")
        self.assertNotContains(page, "No periods scheduled for you on this day.")

    def test_past_date_uses_assignments_effective_then(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 4))
        self.assign_between(self.iyer, self.maths, self.six_a, date(2026, 10, 5))
        self.slot()
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        past = "2026-10-05"                            # a Monday, Iyer's first day
        self.assertEqual(self.get(past).context["rows"], [])
        self.assertEqual(
            [r["subject"] for r in self.get(past, iyer).context["rows"]], ["Mathematics"]
        )
        before = "2026-09-28"                          # Rao's last Monday
        self.assertEqual(
            [r["subject"] for r in self.get(before).context["rows"]], ["Mathematics"]
        )
        self.assertEqual(self.get(before, iyer).context["rows"], [])

    def test_other_teachers_slots_never_appear(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.slot(section=self.six_a)
        self.slot(section=self.six_b, period=self.p2)
        page = self.get()
        self.assertEqual(
            [(r["period"], str(r["section"])) for r in page.context["rows"]],
            [("P1", "Grade 6 - A")],
        )
        self.assertContains(page, "Grade 6 - A")
        self.assertNotContains(page, "Grade 6 - B")

    def test_non_teacher_gets_403(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.make_user("parent")
        guardian = self.client_class()
        guardian.login(username="parent", password="pass-12345")
        self.assertEqual(guardian.get(self.url).status_code, 403)
        self.assertEqual(self.client_class().get(self.url).status_code, 302)

    def test_selected_chip_has_aria_current_and_today_link_goes_to_bare_route(self):
        page = self.get("2026-10-14")
        html = page.content.decode()
        self.assertEqual(html.count('aria-current="date"'), 1)
        selected = re.search(r'<a[^>]*aria-current="date"[^>]*>', html).group(0)
        self.assertIn("date=2026-10-14", selected)
        self.assertIn("erp-tt-chip", selected)
        self.assertRegex(html, r'<a[^>]*href="' + re.escape(self.url) + r'"[^>]*>\s*Today\s*</a>')
        self.assertContains(page, "October 2026")

    def test_today_tab_stays_active(self):
        active = [
            t["mobile_label"] for t in teacher_tabs("my-timetable") if t["active"]
        ]
        self.assertEqual(active, ["Today"])


class TeacherWeekTests(TimetableDashboardFixture, TestCase):
    """teacher_week(): the teacher's own week, Monday to Saturday (fixture week 12-17 Oct 2026)."""

    def week(self, any_date=MONDAY, user=None):
        return teacher_week(
            user or self.rao, any_date, MONDAY,
            lambda year, day: year.is_instructional_day(day),
        )

    def cell(self, week, sequence, day):
        for period in week["grid"]:
            if period["sequence"] == sequence:
                for cell in period["cells"]:
                    if cell["day"]["date"] == day:
                        return cell["rows"]
        raise AssertionError(f"no cell for period {sequence} on {day}")

    def test_week_runs_monday_to_friday_when_saturday_is_not_a_school_day(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        week = self.week(date(2026, 10, 15))           # a Thursday picks its own week
        self.assertEqual(week["monday"], MONDAY)
        self.assertEqual(
            [d["weekday"] for d in week["days"]], ["Mon", "Tue", "Wed", "Thu", "Fri"]
        )
        self.assertTrue(week["days"][0]["is_today"])
        self.assertTrue(all(d["is_school_day"] for d in week["days"]))
        self.assertEqual(week["heading"], "12 – 16 Oct 2026")
        self.assertTrue(week["contains_today"])

    def test_cells_hold_that_days_rows_and_periods_list_only_used_sequences(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()                                    # Monday P1
        self.slot(weekday=2, period=self.p2)           # Wednesday P2
        week = self.week()
        self.assertEqual([p["sequence"] for p in week["grid"]], [1, 2])
        self.assertEqual(
            [r["subject"] for r in self.cell(week, 1, MONDAY)], ["Mathematics"]
        )
        self.assertEqual(self.cell(week, 1, date(2026, 10, 14)), [])
        self.assertEqual(self.cell(week, 2, date(2026, 10, 14))[0]["short"], "6-A")
        self.assertFalse(week["is_empty"])

    def test_mid_week_hand_over_shows_each_days_own_rows(self):
        self.assign_between(self.rao, self.maths, self.six_a, date(2026, 6, 1), date(2026, 10, 13))
        self.assign_between(self.iyer, self.maths, self.six_a, date(2026, 10, 14))
        for weekday in range(5):
            self.slot(weekday=weekday)
        rao = self.week()
        iyer = self.week(user=self.iyer)
        filled = [d for d in (MONDAY + timedelta(days=i) for i in range(5))
                  if self.cell(rao, 1, d)]
        self.assertEqual(filled, [MONDAY, date(2026, 10, 13)])
        filled = [d for d in (MONDAY + timedelta(days=i) for i in range(5))
                  if self.cell(iyer, 1, d)]
        self.assertEqual(filled, [date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16)])

    def test_holiday_column_is_not_a_school_day_and_carries_a_label(self):
        self.assign(self.rao, self.maths, self.six_a)
        for weekday in range(5):
            self.slot(weekday=weekday)
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 10, 14), is_instructional=False,
            label="Holiday",
        )
        week = self.week()
        wed = week["days"][2]
        self.assertFalse(wed["is_school_day"])
        self.assertEqual(wed["label"], "Holiday")
        self.assertEqual(self.cell(week, 1, date(2026, 10, 14)), [])
        self.assertEqual(week["days"][1]["label"], "")

    def test_instructional_saturday_is_shown(self):
        self.year.set_saturdays_instructional(True)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=5)
        week = self.week()
        self.assertEqual(week["days"][-1]["weekday"], "Sat")
        self.assertEqual(week["heading"], "12 – 17 Oct 2026")
        self.assertEqual(len(self.cell(week, 1, date(2026, 10, 17))), 1)

    def test_empty_week_and_no_timetable_week(self):
        self.slot()
        week = self.week()
        self.assertTrue(week["is_empty"])
        self.assertEqual(week["grid"], [])
        self.assertEqual(week["key"], [])
        far = self.week(date(2027, 10, 11))            # outside the Academic Year
        self.assertTrue(far["is_empty"])
        self.assertEqual({d["label"] for d in far["days"]}, {"No school"})

    def test_other_teachers_slots_never_appear(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.slot(section=self.six_a)
        self.slot(section=self.six_b, period=self.p2)
        week = self.week()
        self.assertEqual([p["sequence"] for p in week["grid"]], [1])
        self.assertEqual([k["full"] for k in week["key"]], ["Grade 6 - A"])

    def test_key_lists_each_section_once_in_grid_order(self):
        self.assign(self.rao, self.maths, self.six_b)
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(section=self.six_b)
        self.slot(section=self.six_a, period=self.p2)
        self.slot(section=self.six_a, period=self.p2, weekday=1)
        week = self.week()
        self.assertEqual(
            week["key"],
            [{"short": "6-A", "full": "Grade 6 - A"}, {"short": "6-B", "full": "Grade 6 - B"}],
        )

    def test_headings_across_months_and_years(self):
        self.assertEqual(self.week(date(2026, 10, 1))["heading"], "28 Sep – 2 Oct 2026")
        self.assertFalse(self.week(date(2026, 10, 1))["contains_today"])

    def test_query_count_does_not_grow_with_rows(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        with CaptureQueriesContext(connection) as small:
            self.week()
        for weekday in range(1, 5):
            self.slot(weekday=weekday)
            self.slot(weekday=weekday, period=self.p2)
        with CaptureQueriesContext(connection) as large:
            self.week()
        self.assertEqual(len(large), len(small))


class TimetableWeekPageTests(TimetableDashboardFixture, TestCase):
    """/my/timetable/?view=week (fixture business date is Monday 12 Oct 2026)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-timetable")

    def get(self, params=None, client=None):
        return (client or self.teacher).get(self.url, params or {})

    def week_page(self, date_value=None, client=None):
        params = {"view": "week"}
        if date_value is not None:
            params["date"] = date_value
        return self.get(params, client)

    def test_toggle_links_keep_the_date(self):
        day = self.get({"date": "2026-10-14"})
        self.assertEqual(day.context["view"], "day")
        self.assertContains(day, f'href="{self.url}?view=week&amp;date=2026-10-14"')
        week = self.week_page("2026-10-14")
        self.assertEqual(week.context["view"], "week")
        self.assertContains(week, f'href="{self.url}?date=2026-10-14"')
        html = week.content.decode()
        current = re.search(r'<a[^>]*aria-current="page"[^>]*>\s*Week\s*</a>', html)
        self.assertIsNotNone(current)

    def test_unknown_view_means_day(self):
        page = self.get({"view": "month"})
        self.assertEqual(page.context["view"], "day")
        self.assertContains(page, 'aria-label="Pick a day"')

    def test_week_has_no_date_line_and_no_strip(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        page = self.week_page()
        self.assertNotContains(page, "Monday, 12 October 2026")
        self.assertNotContains(page, 'aria-label="Pick a day"')
        self.assertContains(page, "12 – 16 Oct 2026")
        self.assertContains(page, "This week")
        self.assertEqual(page.content.decode().count("<h1"), 1)

    def test_other_week_has_no_this_week_line(self):
        page = self.week_page("2026-10-21")
        self.assertContains(page, "19 – 23 Oct 2026")
        self.assertNotContains(page, "This week")

    def test_arrows_move_seven_days(self):
        page = self.week_page("2026-10-14")
        self.assertContains(
            page, f'href="{self.url}?view=week&amp;date=2026-10-07" aria-label="Previous week"'
        )
        self.assertContains(
            page, f'href="{self.url}?view=week&amp;date=2026-10-21" aria-label="Next week"'
        )

    def test_arrows_stop_at_the_window_edges_and_far_dates_load(self):
        edge = (MONDAY + timedelta(days=366)).isoformat()
        page = self.week_page(edge)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'aria-label="Next week"')
        self.assertContains(page, 'aria-label="Previous week"')
        edge = (MONDAY - timedelta(days=366)).isoformat()
        page = self.week_page(edge)
        self.assertNotContains(page, 'aria-label="Previous week"')
        for raw in ("abc", "", "9999-12-31", "0001-01-01"):
            with self.subTest(raw=raw):
                page = self.week_page(raw)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context["week"]["monday"], MONDAY)

    def test_filled_cells_link_to_that_day_with_full_label_and_blank_cells_are_empty(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot(weekday=1, period=self.p2)           # Tuesday P2
        self.slot(period=self.p1)                      # Monday P1
        html = self.week_page().content.decode()
        self.assertIn(
            f'<a href="{self.url}?date=2026-10-13" '
            'aria-label="Grade 6 - A, period 2, Tuesday 13 October">6-A</a>',
            html,
        )
        table = html.split('<table class="erp-keep erp-tt-week"')[1].split("</table>")[0]
        body = table.split("<tbody>")[1]
        cells = re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)
        self.assertEqual(len(cells), 2 * 5)
        self.assertEqual(sum(1 for c in cells if c.strip()), 2)
        self.assertTrue(all(c == "" for c in cells if not c.strip()))
        for word in ("Free", "free", "Break", "Lunch"):
            self.assertNotIn(word, table)

    def test_key_lists_short_and_full_names(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        self.slot()
        self.slot(section=self.six_b, period=self.p2)
        page = self.week_page()
        self.assertContains(page, "Tap a class to open that day.")
        html = page.content.decode()
        key = html.split('class="erp-tt-key"')[1].split("</ul>")[0]
        self.assertLess(key.index("Grade 6 - A"), key.index("Grade 6 - B"))
        self.assertIn("6-A", key)

    def test_holiday_header_label(self):
        self.assign(self.rao, self.maths, self.six_a)
        for weekday in range(5):
            self.slot(weekday=weekday)
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 10, 14), is_instructional=False,
            label="Holiday",
        )
        html = self.week_page().content.decode()
        head = html.split("<thead>")[1].split("</thead>")[0]
        self.assertRegex(head, r'<th scope="col" class="[^"]*is-closed[^"]*"[^>]*>.*?Holiday')

    def test_empty_week_sentence(self):
        self.slot()
        page = self.week_page()
        self.assertContains(page, "No periods for you this week.")
        self.assertNotContains(page, "erp-tt-week\"")

    def test_other_teachers_slots_never_appear(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.slot(section=self.six_a)
        self.slot(section=self.six_b, period=self.p2)
        page = self.week_page()
        self.assertContains(page, "Grade 6 - A")
        self.assertNotContains(page, "Grade 6 - B")

    def test_non_teacher_gets_403(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url, {"view": "week"}).status_code, 403)

    def test_today_column_is_marked(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.slot()
        html = self.week_page().content.decode()
        head = html.split("<thead>")[1].split("</thead>")[0]
        today = re.search(r'<th[^>]*aria-current="date"[^>]*>', head).group(0)
        self.assertIn("is-today", today)
