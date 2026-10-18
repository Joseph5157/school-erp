"""TDB-1 Teacher Dashboard: header and Today overview (docs/superpowers/specs/
2026-10-18-ui-tdb-0-teacher-dashboard-design.md)."""

import re
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    ResultStatus,
    Section,
    SectionClassTeacher,
    TermRemark,
)
from core.tests.test_phase5_teacher_home import MONDAY, SUNDAY, TeacherHomeFixture, on

TILE = re.compile(r'<div class="erp-tile( is-link)?">(.*?)</div>', re.DOTALL)


class DashboardFixture(TeacherHomeFixture):
    def page(self):
        return self.teacher.get(self.url)

    def tiles(self, page):
        """{"Attendance": (is_link, html), "Marks": (...)} from the rendered page."""
        found = {}
        for link, body in TILE.findall(page.content.decode()):
            label = re.search(r'erp-tile-label">([^<]+)<', body).group(1)
            found[label] = (bool(link), body)
        return found

    def submit_register(self, section):
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=section, date=MONDAY,
            status="SUBMITTED", submitted_by=self.admin, submitted_at="2026-10-12T09:00:00Z",
        )

    def header(self, page):
        html = page.content.decode()
        return html.split('<header class="erp-day-head">')[1].split("</header>")[0]


class HeaderTests(DashboardFixture, TestCase):
    def test_greeting_is_the_single_h1(self):
        html = self.page().content.decode()
        self.assertEqual(html.count("<h1"), 1)
        self.assertRegex(
            html, r'<h1 class="h3 mb-1 erp-day-greeting">Good (morning|afternoon|evening), rao</h1>'
        )
        self.assertNotIn(">My day</h1>", html)
        self.assertEqual(html.count("<title>My day</title>"), 1)
        self.assertContains(self.page(), "Monday, 12 October 2026")

    def test_greeting_uses_full_name_with_username_fallback(self):
        at = datetime(2026, 10, 12, 9, 0)
        with mock.patch("core.views.timezone.localtime", return_value=at):
            self.assertContains(self.page(), ">Good morning, rao</h1>")
            self.rao.first_name, self.rao.last_name = "Rao", "Kumar"
            self.rao.save()
            self.assertContains(self.page(), ">Good morning, Rao Kumar</h1>")

    def test_greeting_follows_local_time_of_day(self):
        for hour, word in ((8, "morning"), (13, "afternoon"), (19, "evening")):
            with self.subTest(hour=hour), mock.patch(
                "core.views.timezone.localtime", return_value=datetime(2026, 10, 12, hour)
            ):
                self.assertContains(self.page(), f">Good {word}, rao</h1>")

    def test_school_day_shown_for_exactly_one_relevant_year(self):
        self.class_teacher(self.rao, self.six_a)
        page = self.page()
        self.assertIs(page.context["school_day"], True)
        self.assertIn('<span class="erp-pill">School day</span>', self.header(page))

    def test_one_year_from_a_subject_assignment_alone_is_enough(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assertIs(self.page().context["school_day"], True)

    def test_not_a_school_day_on_a_sunday(self):
        self.class_teacher(self.rao, self.six_a)
        for patch in on(SUNDAY):
            patch.start()
            self.addCleanup(patch.stop)
        page = self.page()
        self.assertIs(page.context["school_day"], False)
        self.assertIn('<span class="erp-pill">Not a school day</span>', self.header(page))

    def test_status_hidden_without_assignment_context(self):
        page = self.page()
        self.assertIsNone(page.context["school_day"])
        self.assertNotIn("erp-pill", self.header(page))

    def test_status_hidden_when_relevant_years_disagree(self):
        other = AcademicYear.objects.create(
            name="Overlapping", start_date=date(2026, 10, 1), end_date=date(2027, 2, 28)
        )
        offering = AcademicSubjectOffering.objects.create(
            academic_year=other, class_grade=self.grade6, subject=self.maths_subject
        )
        self.class_teacher(self.rao, self.six_a)
        AssessmentTeacherAssignment.objects.create(
            teacher=self.rao, offering=offering, section=self.six_a, start_date=date(2026, 10, 1)
        )
        page = self.page()
        self.assertIsNone(page.context["school_day"])
        self.assertNotIn("erp-pill", self.header(page))


class AttendanceTileTests(DashboardFixture, TestCase):
    def test_states_not_taken_draft_submitted(self):
        self.make_student("Asha")
        self.class_teacher(self.rao, self.six_a)
        href = reverse("core:my-attendance", args=[self.six_a.pk])
        link, body = self.tiles(self.page())["Attendance"]
        self.assertTrue(link)
        self.assertIn(">Not taken</a>", body)
        self.assertIn(f'href="{href}"', body)
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY
        )
        self.assertIn(">Draft</a>", self.tiles(self.page())["Attendance"][1])
        AttendanceRegister.objects.filter(pk=register.pk).update(
            status="SUBMITTED", submitted_by=self.admin, submitted_at="2026-10-12T09:00:00Z"
        )
        self.assertIn(">Submitted</a>", self.tiles(self.page())["Attendance"][1])

    def test_no_class_teacher_duty_is_flat_not_required(self):
        link, body = self.tiles(self.page())["Attendance"]
        self.assertFalse(link)
        self.assertIn("Not required", body)
        self.assertIn("No class assigned", body)
        self.assertNotIn("<a ", body)

    def test_non_instructional_day_is_flat_not_required(self):
        self.class_teacher(self.rao, self.six_a)
        for patch in on(SUNDAY):
            patch.start()
            self.addCleanup(patch.stop)
        link, body = self.tiles(self.page())["Attendance"]
        self.assertFalse(link)
        self.assertIn("Not required", body)
        self.assertIn("Not a school day", body)
        self.assertNotIn("<a ", body)

    def test_one_section_has_no_detail_rows(self):
        self.class_teacher(self.rao, self.six_a)
        self.assertNotContains(self.page(), 'aria-label="Attendance by Section"')

    def test_several_sections_make_a_flat_summary_with_compact_rows(self):
        self.class_teacher(self.rao, self.six_a)
        self.class_teacher(self.rao, self.six_b)
        self.submit_register(self.six_b)
        page = self.page()
        link, body = self.tiles(page)["Attendance"]
        self.assertFalse(link)
        self.assertNotIn("<a ", body)
        self.assertIn("Not taken", body)  # most urgent state wins
        self.assertIn("1 of 2 submitted", body)
        html = page.content.decode()
        rows = html.split('aria-label="Attendance by Section"')[1].split("</ul>")[0]
        self.assertEqual(rows.count("<li "), 2)
        for section, action in ((self.six_a, "Take attendance"), (self.six_b, "View attendance")):
            self.assertIn(f'href="{reverse("core:my-attendance", args=[section.pk])}"', rows)
            self.assertIn(f'aria-label="{action} for {section}"', rows)


class MarksTileTests(DashboardFixture, TestCase):
    def test_one_assessment_links_straight_to_marks_entry(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.make_student("Asha")
        only = self.make_assessment(name="UT1")
        link, body = self.tiles(self.page())["Marks"]
        self.assertTrue(link)
        self.assertIn("1 mark remaining", body)
        self.assertIn(f'href="{reverse("core:assessment-marks-entry", args=[only.pk])}"', body)

    def test_several_assessments_link_to_my_assessments_and_count_marks_not_students(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.make_student("Asha")  # one student, unmarked in both assessments
        self.make_assessment(name="UT1")
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        link, body = self.tiles(self.page())["Marks"]
        self.assertTrue(link)
        self.assertIn("2 marks remaining", body)
        self.assertIn("across 2 assessments", body)
        self.assertNotIn("student", body.lower())
        self.assertIn(f'href="{reverse("core:my-assessments")}"', body)

    def test_future_and_complete_assessments_are_not_waiting(self):
        self.assign(self.rao, self.maths, self.six_a)
        _, asha = self.make_student("Asha")
        future = self.make_assessment(name="Later", on=date(2026, 11, 1), term=self.term2)
        done = self.make_assessment(name="Done", on=date(2026, 8, 1))
        done.save_draft_result(enrollment=asha, status=ResultStatus.ABSENT, actor=self.rao)
        link, body = self.tiles(self.page())["Marks"]
        self.assertIn("Nothing waiting", body)
        self.assertNotIn(future.name, body)

    def test_nothing_waiting_links_to_my_assessments(self):
        self.assign(self.rao, self.maths, self.six_a)
        link, body = self.tiles(self.page())["Marks"]
        self.assertTrue(link)
        self.assertIn(">Nothing waiting</a>", body)
        self.assertIn(f'href="{reverse("core:my-assessments")}"', body)

    def test_no_subject_assignment_is_flat_not_required(self):
        link, body = self.tiles(self.page())["Marks"]
        self.assertFalse(link)
        self.assertIn("Not required", body)
        self.assertNotIn("<a ", body)


class PageShapeTests(DashboardFixture, TestCase):
    def test_no_timetable_section_or_placeholder(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        html = self.page().content.decode().lower()
        for word in ("timetable", "period", "coming soon"):
            self.assertNotIn(word, html)

    def test_old_large_attendance_and_marks_sections_are_gone(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        self.make_student("Asha")
        self.make_assessment(name="Distinct Unit Name")
        self.make_assessment(name="Second Unit", on=date(2026, 8, 1))
        html = self.page().content.decode()
        for marker in ('id="day-attendance"', 'id="day-marks"', "Marks to enter",
                       "Take attendance", "Distinct Unit Name", "Second Unit"):
            self.assertNotIn(marker, html)

    def test_two_tiles_in_one_grid(self):
        html = self.page().content.decode()
        self.assertEqual(html.count('<div class="erp-tiles">'), 1)
        self.assertEqual(len(TILE.findall(html)), 2)

    def test_link_tiles_have_one_named_target_and_flat_ones_none(self):
        self.class_teacher(self.rao, self.six_a)
        tiles = self.tiles(self.page())
        link, body = tiles["Attendance"]
        self.assertEqual(body.count("<a "), 1)
        self.assertIn('class="stretched-link"', body)
        self.assertRegex(body, r'aria-label="Attendance: Not taken, ')

    def test_css_keeps_two_columns_and_a_focus_ring(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-tiles \{[^}]*repeat\(2, minmax\(0, 1fr\)\)")
        self.assertIn(".erp-teacher .erp-tile .stretched-link:focus-visible::after", css)
        self.assertRegex(css, r"\.erp-tile \{[^}]*min-width: 0")


class DashboardQueryCountTests(DashboardFixture, TestCase):
    def count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.teacher.get(self.url).status_code, 200)
        return len(ctx.captured_queries)

    def test_queries_do_not_grow_with_assignments(self):
        for section in (self.six_a, self.six_b):
            self.class_teacher(self.rao, section)
            self.assign(self.rao, self.maths, section)
        self.make_student("Asha")
        self.make_assessment(name="UT1")
        small = self.count()
        for name in ("C", "D", "E"):
            extra = Section.objects.create(class_grade=self.grade6, name=name)
            self.class_teacher(self.rao, extra)
            self.assign(self.rao, self.maths, extra)
            self.assign(self.rao, self.sanskrit, extra)
            self.make_student(f"Student {name}", section=extra)
            self.make_assessment(name=f"UT {name}", section=extra)
        self.assertEqual(self.count(), small)


class TeachingAssignmentTests(DashboardFixture, TestCase):
    def groups(self):
        html = self.page().content.decode()
        body = html.split('id="day-assignments"')[1].split("</section>")[0]
        class_part, subject_part = body.split('id="assign-subjects"')
        return class_part, subject_part

    def attendance_href(self, section):
        return reverse("core:my-attendance", args=[section.pk])

    def test_class_teacher_rows_are_current_sections_only(self):
        self.class_teacher(self.rao, self.six_a)
        SectionClassTeacher.objects.create(
            teacher=self.rao, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 6, 1), end_date=date(2026, 9, 30),
        )
        extra = Section.objects.create(class_grade=self.grade6, name="C")
        SectionClassTeacher.objects.create(
            teacher=self.rao, academic_year=self.year, section=extra, start_date=date(2026, 11, 1),
        )
        class_part, _ = self.groups()
        self.assertIn(str(self.six_a), class_part)
        self.assertNotIn(str(self.six_b), class_part)
        self.assertNotIn(str(extra), class_part)

    def test_class_row_shows_section_year_and_one_attendance_link(self):
        self.class_teacher(self.rao, self.six_a)
        self.class_teacher(self.rao, self.six_b)
        class_part, _ = self.groups()
        self.assertEqual(class_part.count("<li "), 2)
        self.assertEqual(class_part.count("<a "), 2)
        self.assertIn(self.year.name, class_part)
        for section in (self.six_a, self.six_b):
            self.assertIn(f'href="{self.attendance_href(section)}"', class_part)
        self.assertEqual(class_part.count("stretched-link"), 2)

    def test_subject_rows_are_current_section_and_subject_pairs_only(self):
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        AssessmentTeacherAssignment.objects.create(
            teacher=self.rao, offering=self.sanskrit, section=self.six_a,
            start_date=date(2026, 6, 1), end_date=date(2026, 6, 30),
        )  # ended
        rows = self.page().context["subject_rows"]
        self.assertEqual(
            [(str(r["section"]), r["subject"]) for r in rows],
            [(str(self.six_a), "Mathematics"), (str(self.six_b), "Mathematics"),
             (str(self.six_b), "Sanskrit")],
        )
        _, subject_part = self.groups()
        self.assertIn(f"{self.six_b} &middot; Sanskrit", subject_part)
        self.assertIn(self.year.name, subject_part)

    def test_ended_and_future_subject_assignments_do_not_appear(self):
        AssessmentTeacherAssignment.objects.create(
            teacher=self.rao, offering=self.maths, section=self.six_a,
            start_date=date(2026, 6, 1), end_date=date(2026, 9, 30),
        )
        AssessmentTeacherAssignment.objects.create(
            teacher=self.rao, offering=self.maths, section=self.six_b,
            start_date=date(2026, 11, 1),
        )
        self.assertEqual(self.page().context["subject_rows"], [])
        _, subject_part = self.groups()
        self.assertIn("No subjects are assigned to you today.", subject_part)
        self.assertNotIn("Mathematics", subject_part)

    def test_subject_rows_have_no_links_and_do_not_look_tappable(self):
        self.assign(self.rao, self.maths, self.six_a)
        _, subject_part = self.groups()
        self.assertNotIn("<a ", subject_part)
        self.assertNotIn("is-link", subject_part)
        self.assertNotIn("erp-day-chevron", subject_part)

    def test_same_section_may_be_in_both_groups(self):
        self.class_teacher(self.rao, self.six_a)
        self.assign(self.rao, self.maths, self.six_a)
        class_part, subject_part = self.groups()
        self.assertIn(str(self.six_a), class_part)
        self.assertIn(f"{self.six_a} &middot; Mathematics", subject_part)

    def test_groups_are_separated_by_text_headings_after_the_overview(self):
        html = self.page().content.decode()
        self.assertEqual(html.count("<h1"), 1)
        for label in ("Teaching assignments", "Class teacher", "Subjects I teach"):
            self.assertIn(f">{label}</h", html)
        self.assertLess(html.index("Today overview"), html.index("Teaching assignments"))

    def test_empty_wording_for_each_group(self):
        class_part, subject_part = self.groups()
        self.assertIn("You are not a class teacher today.", class_part)
        self.assertIn("No subjects are assigned to you today.", subject_part)
        self.class_teacher(self.rao, self.six_a)
        class_part, subject_part = self.groups()
        self.assertNotIn("You are not a class teacher today.", class_part)
        self.assertIn("No subjects are assigned to you today.", subject_part)

    def test_handed_over_class_is_not_listed(self):
        self.class_teacher(self.rao, self.six_a)
        self.class_teacher(self.iyer, self.six_a, start=MONDAY)
        class_part, _ = self.groups()
        self.assertNotIn(str(self.six_a), class_part)


class TermRemarksTreatmentTests(DashboardFixture, TestCase):
    def test_hidden_when_there_is_no_remark_data(self):
        html = self.page().content.decode()
        self.assertNotIn("day-remarks", html)
        self.assertNotIn("Term remarks", html)

    def test_semantics_unchanged_started_terms_with_real_counts(self):
        self.class_teacher(self.rao, self.six_a)
        asha, _ = self.make_student("Asha")
        self.make_student("Ravi")
        TermRemark.objects.create(term=self.term1, student=asha, remark="Good",
                                  written_by=self.rao)
        page = self.page()
        self.assertEqual(
            [(r["term"], r["expected"], r["written"]) for r in page.context["remarks"]],
            [(self.term1, 2, 1), (self.term2, 2, 0)],
        )
        self.assertContains(page, "1 of 2 written")
        self.assertContains(page, "0 of 2 written")

    def test_compact_rows_last_on_the_page_linking_to_term_remarks(self):
        self.class_teacher(self.rao, self.six_a)
        self.make_student("Asha")
        html = self.page().content.decode()
        self.assertGreater(html.index("day-remarks"), html.index("day-assignments"))
        self.assertEqual(html.count('id="day-remarks"'), 1)
        self.assertNotIn("erp-progress", html)
        self.assertNotIn("erp-card ", html)
        section = html.split('id="day-remarks"')[1].split("</section>")[0]
        href = reverse("core:term-remarks", args=[self.term1.pk]) + f"?section={self.six_a.pk}"
        self.assertIn(f'href="{href}"', section)
        self.assertEqual(section.count("<li "), 2)
