"""Progress section on the admin student page: bullet chart, radar, attendance by month."""

import datetime
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.db.models import Q
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import analytics, charts, marks_analytics
from core.models import AcademicTerm, AcademicYear, ClassGrade, Section, Subject
from core.tests.test_admin_overview_analytics import TODAY, A, MarksFixture, P


class ProgressFixture(MarksFixture):
    def setUp(self):
        super().setUp()
        for target in ("core.views.business_today", "core.marks_analytics.business_today"):
            patcher = mock.patch(target, return_value=TODAY)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.url = reverse("core:student-detail", args=[self.s1.student_id])

    def subjects(self, count, term=None, score=10, start=1, **kwargs):
        """One finalized test per subject for s1 (and s2), named Subject 1..count."""
        names = []
        for i in range(start, start + count):
            subject = Subject.objects.create(name=f"Subject {i}")
            self.assessment(
                {self.s1: score, self.s2: score}, subject=subject, name=f"T{i}", term=term, **kwargs
            )
            names.append(subject.name)
        return names

    def get(self, query="", client=None):
        response = (client or self.administrator).get(self.url + query)
        self.assertEqual(response.status_code, 200)
        return response

    def limited_client(self, *codenames):
        user = get_user_model().objects.create_user(username="limited", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username="limited", password="pass-12345")
        return client


class ProgressPageTests(ProgressFixture, TestCase):
    def test_progress_section_appears_in_the_section_nav(self):
        response = self.get()
        self.assertIn({"id": "progress", "label": "Progress"}, response.context["profile_sections"])
        self.assertContains(response, 'href="#progress"')
        self.assertContains(response, 'id="progress"')

    def test_marks_charts_need_results_permission(self):
        self.subjects(3)
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P})
        response = self.get(client=self.limited_client("view_student"))
        self.assertContains(response, "erp-col")  # months shown
        self.assertNotContains(response, "erp-bullet")
        self.assertNotContains(response, "erp-radar")
        self.assertNotContains(response, "Subject 1")

    def test_defaults_to_newest_term_and_honours_a_valid_term_choice(self):
        self.assessment({self.s1: 10}, term=self.term_a, name="Old")
        self.assessment({self.s1: 20}, term=self.term_b, name="New")
        response = self.get()
        self.assertEqual(response.context["progress"]["term"], self.term_b)
        self.assertEqual(response.context["progress"]["bullets"][0]["score"].score, 100.0)
        response = self.get(f"?term={self.term_a.pk}")
        self.assertEqual(response.context["progress"]["term"], self.term_a)
        self.assertEqual(response.context["progress"]["bullets"][0]["score"].score, 50.0)

    def test_unknown_term_param_falls_back_safely(self):
        self.assessment({self.s1: 20}, term=self.term_b)
        # A term where only another student has results.
        self.assessment({self.s2: 4}, term=self.term_a, name="Other")
        for param in ("abc", "99999", "", f"{self.term_a.pk}", "-1", "1e3"):
            with self.subTest(param=param):
                response = self.get(f"?term={param}")
                progress = response.context["progress"]
                self.assertEqual(progress["term"], self.term_b)
                self.assertEqual([b["score"].score for b in progress["bullets"]], [100.0])

    def test_radar_note_under_3_subjects_and_over_8(self):
        self.subjects(2)
        progress = self.get().context["progress"]
        self.assertIsNone(progress["radar"])
        self.assertIn("at least 3", progress["radar_note"])
        self.assertContains(self.get(), "at least 3 subjects")

    def test_radar_note_over_8_subjects(self):
        self.subjects(9)
        progress = self.get().context["progress"]
        self.assertIsNone(progress["radar"])
        self.assertIn("more than 8", progress["radar_note"])
        self.assertEqual(len(progress["bullets"]), 9)

    def test_radar_drawn_for_3_to_8_subjects(self):
        self.subjects(4)
        response = self.get()
        self.assertIsNotNone(response.context["progress"]["radar"])
        self.assertIsNone(response.context["progress"]["radar_note"])
        self.assertContains(response, "erp-radar")

    def test_bullet_rows_keep_subject_order_not_score_order(self):
        for name, score in (("Art", 20), ("Biology", 2), ("Chemistry", 12)):
            self.assessment({self.s1: score}, subject=Subject.objects.create(name=name), name=name)
        bullets = self.get().context["progress"]["bullets"]
        self.assertEqual([b["score"].subject_name for b in bullets], ["Art", "Biology", "Chemistry"])
        content = self.get().content.decode()
        self.assertLess(content.index("Art"), content.index("Biology"))

    def test_marker_and_label_absent_when_section_is_small(self):
        self.subjects(3)  # two students only
        response = self.get()
        self.assertNotContains(response, "erp-bullet-marker")
        self.assertNotContains(response, "Section average")

    def test_marker_and_legend_shown_with_five_students(self):
        self.subjects(3)
        for i in range(3):
            student = self.enroll_student(f"Extra {i}", self.class_grade, self.section)
            for assessment in self.term_b.assessments.all():
                assessment.results.create(
                    academic_enrollment=student, entered_by=self.admin_user, score=5, status="MARKED"
                )
        response = self.get()
        self.assertContains(response, "erp-bullet-marker")
        self.assertContains(response, "Section average")

    def test_no_pass_mark_draws_no_band(self):
        self.subjects(3)
        self.assertNotContains(self.get(), "erp-bullet-pass")

    def test_pass_mark_draws_a_band(self):
        self.subjects(3, pass_mark=8)
        self.assertContains(self.get(), "erp-bullet-pass")

    def test_zero_score_draws_an_empty_bar_labelled_zero(self):
        self.assessment({self.s1: 0}, subject=Subject.objects.create(name="Zero"))
        response = self.get()
        bullet = response.context["progress"]["bullets"][0]
        self.assertEqual(bullet["bullet"]["score"], 0.0)
        self.assertEqual(bullet["display"], "0")
        self.assertContains(response, "Zero: 0%")
        self.assertNotContains(response, "erp-bullet-bar")

    def test_month_with_no_register_is_left_out(self):
        self.day(datetime.date(2026, 6, 8), {self.s1: P, self.s2: P})
        months = analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)
        self.assertEqual([m["label"] for m in months], ["Jun"])
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: A})
        months = analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)
        self.assertEqual([m["label"] for m in months], ["Jun", "Jul"])
        self.assertNotContains(self.get(), "May")

    def test_attendance_by_month_values_and_low_flag(self):
        self.day(datetime.date(2026, 6, 8), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 6, 9), {self.s1: A, self.s2: P})
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P})
        months = analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)
        self.assertEqual(
            [(m["label"], m["present"], m["absent"], m["percentage"]) for m in months],
            [("Jun", 1, 1, 50.0), ("Jul", 1, 0, 100.0)],
        )
        self.assertEqual(months[0]["month"], datetime.date(2026, 6, 1))
        response = self.get()
        self.assertContains(response, "erp-col--low")
        self.assertContains(response, "Under 80%")

    def test_student_with_no_results_sees_a_message(self):
        response = self.get()
        self.assertContains(response, "No finalized results yet.")
        self.assertNotContains(response, "erp-bullet")

    def test_draft_and_absent_results_never_count(self):
        self.assessment({self.s1: 20}, finalize=False)
        self.assessment({self.s1: None}, name="Absent")
        self.assertContains(self.get(), "No finalized results yet.")

    def test_term_selector_links_appear_with_two_terms(self):
        self.assessment({self.s1: 10}, term=self.term_a, name="Old")
        self.assessment({self.s1: 20}, term=self.term_b, name="New")
        response = self.get()
        self.assertContains(response, f"?term={self.term_a.pk}#progress")
        self.assertContains(response, 'aria-current="true"')

    def test_query_count_constant_with_more_subjects(self):
        self.subjects(2)
        with CaptureQueriesContext(connection) as few:
            self.get()
        self.subjects(6, start=3)
        with CaptureQueriesContext(connection) as many:
            self.get()
        self.assertEqual(len(few), len(many))


class QueryCeilingTests(ProgressFixture, TestCase):
    def test_student_page_stays_under_the_query_ceiling(self):
        # Measured: 32 queries for an administrator with results (8 subjects, 2 terms, 7
        # students in the section, attendance in 2 months). The ceiling is that plus 3, so a
        # per-subject loop fails it at once; months are pinned by the one-query test in
        # AttendanceByMonthTests.
        self.subjects(8)
        self.subjects(1, term=self.term_a, start=20)
        everyone = [self.s1, self.s2] + [
            self.enroll_student(f"Pupil {i}", self.class_grade, self.section) for i in range(5)
        ]
        self.day(datetime.date(2026, 6, 8), {e: P for e in everyone})
        self.day(datetime.date(2026, 7, 6), {e: A if e is self.s2 else P for e in everyone})
        with CaptureQueriesContext(connection) as ctx:
            response = self.administrator.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(ctx), 35, [q["sql"][:80] for q in ctx])


class RadarEdgeTests(ProgressFixture, TestCase):
    def test_mixed_section_averages_draw_only_the_student_outline(self):
        # Maths has 5 students (average shown); Art has only 2 (no average). Must not raise.
        self.subjects(1)
        for i in range(3):
            student = self.enroll_student(f"Extra {i}", self.class_grade, self.section)
            for assessment in self.term_b.assessments.all():
                assessment.results.create(
                    academic_enrollment=student, entered_by=self.admin_user, score=5, status="MARKED"
                )
        for name in ("Art", "Biology"):
            self.assessment({self.s1: 12}, subject=Subject.objects.create(name=name), name=name)
        response = self.get()
        radar = response.context["progress"]["radar"]
        self.assertEqual([o["key"] for o in radar["outlines"]], ["student"])
        self.assertContains(response, "erp-bullet-marker")  # still on the bullet where it exists

    def test_all_axes_with_averages_draw_the_section_outline_too(self):
        self.subjects(3)
        for i in range(3):
            student = self.enroll_student(f"Extra {i}", self.class_grade, self.section)
            for assessment in self.term_b.assessments.all():
                assessment.results.create(
                    academic_enrollment=student, entered_by=self.admin_user, score=5, status="MARKED"
                )
        radar = self.get().context["progress"]["radar"]
        self.assertEqual([o["key"] for o in radar["outlines"]], ["student", "section"])

    def test_long_names_wrap_at_a_word_and_stay_distinct(self):
        names = ["Computer Science", "Computer Applications", "Environmental Science", "Mathematics"]
        for name in names:
            subject = self.maths if name == "Mathematics" else Subject.objects.create(name=name)
            self.assessment({self.s1: 12}, subject=subject, name=name)
        response = self.get()
        labels = response.context["progress"]["radar"]["labels"]
        by_name = {label["title"].split(":")[0]: label["lines"] for label in labels}
        self.assertEqual(by_name["Mathematics"], ["Mathematics"])
        self.assertNotEqual(by_name["Computer Science"], by_name["Computer Applications"])
        self.assertEqual(len({tuple(label["lines"]) for label in labels}), 4)
        self.assertContains(response, "Environmental Science")  # bullet chart and hidden list

    def test_label_title_gives_the_exact_value(self):
        self.subjects(3, score=12)  # 60%
        titles = [label["title"] for label in self.get().context["progress"]["radar"]["labels"]]
        self.assertEqual(titles[0], "Subject 1: 60%")
        html = self.get().content.decode()
        radar_svg = html[html.index('<svg class="erp-radar"'): html.index("</svg>", html.index('<svg class="erp-radar"'))]
        self.assertIn("<title>Subject 1: 60%</title>", radar_svg)

    def test_radar_and_partials_follow_the_rendering_rules(self):
        self.subjects(4)
        response = self.get()
        html = response.content.decode()
        self.assertRegex(html, r'<svg class="erp-radar"[^>]* role="img"')
        self.assertIn('<ul class="visually-hidden">', html)
        self.assertIn("Subject 1: 50%", html.split('<ul class="visually-hidden">')[1])
        progress = html[html.index('id="progress"'): html.index('id="enrollment-history"')]
        self.assertNotIn("style=", progress)

    def test_radar_hidden_list_and_bullet_agree_near_the_pass_mark(self):
        self.assessment(
            {self.s1: 49.96}, subject=Subject.objects.create(name="Close"), maximum="100",
            pass_mark=50,
        )
        for name in ("Other 1", "Other 2"):
            self.assessment({self.s1: 15}, subject=Subject.objects.create(name=name), name=name)
        progress = self.get().context["progress"]
        self.assertEqual(progress["bullets"][0]["display"], "49.9")
        self.assertEqual(progress["radar_values"][0]["student"], "49.9")


    def test_wrapped_labels_render_as_tspans_in_the_radar_svg(self):
        for name in ("Computer Science", "Computer Applications", "Environmental Science", "Mathematics"):
            subject = self.maths if name == "Mathematics" else Subject.objects.create(name=name)
            self.assessment({self.s1: 12}, subject=subject, name=name)
        html = self.get().content.decode()
        radar_svg = html[html.index('<svg class="erp-radar"'): html.index("</svg>", html.index('<svg class="erp-radar"'))]
        self.assertIn("<tspan", radar_svg)
        self.assertRegex(radar_svg, r">Science</tspan>")  # the second line of a wrapped label

    def test_radar_card_names_the_term(self):
        self.subjects(3)
        self.assertContains(self.get(), "Subjects at a glance, Term 2")

    def test_radar_block_works_for_any_subset_of_scores(self):
        self.subjects(5)
        scores = marks_analytics.student_subject_scores(self.s1.student, self.term_b)
        block = marks_analytics.radar_block(scores[:3], "Ravi Rao")
        self.assertEqual(len(block["radar"]["labels"]), 3)
        self.assertEqual([v["name"] for v in block["values"]], [s.subject_name for s in scores[:3]])
        self.assertEqual([label["title"].split(":")[0] for label in block["radar"]["labels"]],
                         [s.subject_name for s in scores[:3]])
        self.assertIsNone(marks_analytics.radar_block(scores[:2], "Ravi Rao"))

    def test_radar_default_size_fits_a_phone_card(self):
        radar = charts.radar(list("abc"), [{"key": "s", "label": "S", "values": [1, 2, 3]}])
        self.assertEqual((radar["width"], radar["height"]), (292, 180))


class ProgressCssAndPartialTests(ProgressFixture, TestCase):
    CSS = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")

    def test_month_columns_wrap_instead_of_scrolling(self):
        self.assertIn(
            ".erp-progress-card--months .erp-cols { flex-wrap: wrap;", self.CSS
        )

    def test_five_four_three_split_only_from_1330px(self):
        wide = self.CSS[self.CSS.index("@media (min-width: 1330px) { /* progress */"):]
        wide = wide[: wide.index("\n}")]
        self.assertIn(".erp-progress-card--bullet { grid-column: span 5; }", wide)
        self.assertIn(".erp-progress-card--radar { grid-column: span 4; }", wide)
        self.assertIn(".erp-progress-card--months { grid-column: span 3; }", wide)
        mid = self.CSS[self.CSS.index("@media (min-width: 992px) { /* progress */"):]
        mid = mid[: mid.index("\n}")]
        self.assertIn(".erp-progress-card--bullet { grid-column: span 12; }", mid)
        self.assertIn(".erp-progress-card--radar { grid-column: span 6; }", mid)
        self.assertIn(".erp-progress-card--months { grid-column: span 6; }", mid)

    def test_months_card_is_left_out_when_the_caller_passes_none(self):
        self.subjects(3)
        progress = marks_analytics.student_progress_context(self.s1.student, None)
        html = render_to_string("partials/_student_progress.html", {"progress": progress})
        self.assertNotIn("Attendance by month", html)
        self.assertNotIn("No attendance recorded", html)
        self.assertIn("erp-progress-grid--no-months", html)
        with_empty = render_to_string(
            "partials/_student_progress.html", {"progress": progress, "attendance_months": []}
        )
        self.assertIn("No attendance recorded yet this year.", with_empty)


class AttendanceByMonthTests(ProgressFixture, TestCase):
    def test_another_academic_year_is_excluded(self):
        self.day(datetime.date(2026, 6, 8), {self.s1: P, self.s2: P})
        other = AcademicYear.objects.create(
            name="2027-2028", start_date="2027-06-01", end_date="2028-04-30"
        )
        self.assertEqual(analytics.student_attendance_by_month(self.s1.student, other, TODAY), [])

    def test_two_enrollments_in_one_year_sum_into_the_month(self):
        grade2 = ClassGrade.objects.create(name="Grade 2")
        section2 = Section.objects.create(class_grade=grade2, name="A")
        self.day(datetime.date(2026, 6, 8), {self.s1: P, self.s2: P})
        second = self.s1.student.enroll(
            academic_year=self.year, class_grade=grade2, section=section2, start_date="2026-06-20"
        )
        self.day(datetime.date(2026, 6, 22), {second: A}, class_grade=grade2, section=section2)
        months = analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)
        self.assertEqual([(m["label"], m["present"], m["absent"]) for m in months], [("Jun", 1, 1)])

    def test_one_query_whatever_the_number_of_months(self):
        self.day(datetime.date(2026, 6, 8), {self.s1: P, self.s2: P})
        with self.assertNumQueries(1):
            analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)
        self.day(datetime.date(2026, 7, 6), {self.s1: P, self.s2: P})
        self.day(datetime.date(2026, 7, 7), {self.s1: A, self.s2: P})
        with self.assertNumQueries(1):
            analytics.student_attendance_by_month(self.s1.student, self.year, TODAY)


class RadarLabelUnitTests(TestCase):
    def lines(self, axes, outline_values=None):
        outlines = [{"key": "student", "label": "S", "values": outline_values or [50] * len(axes)}]
        radar = charts.radar(axes, outlines, size=(292, 180))
        return [label["lines"] for label in radar["labels"]], radar

    def test_every_word_survives_when_there_is_room(self):
        lines, _ = self.lines(["Computer Science", "Computer Applications", "Mathematics"])
        for name, got in zip(["Computer Science", "Computer Applications", "Mathematics"], lines, strict=True):
            self.assertEqual(" ".join(got), name)
        self.assertEqual(lines[2], ["Mathematics"])

    def test_top_label_is_not_capped_by_the_side_limit(self):
        lines, _ = self.lines(["Computer Applications", "A", "B"])
        self.assertEqual(lines[0], ["Computer Applications"])

    def test_a_single_word_that_cannot_fit_gets_an_ellipsis(self):
        lines, _ = self.lines(["Top", "Supercalifragilisticexpialidocious", "B"])
        self.assertEqual(len(lines[1]), 1)
        self.assertTrue(lines[1][0].endswith("…"))

    def test_at_most_two_lines(self):
        lines, _ = self.lines(["Top", "One Two Three Four Five Six Seven", "B"])
        self.assertLessEqual(len(lines[1]), 2)


class SubjectOrderTests(ProgressFixture, TestCase):
    def test_subject_order_ignores_case(self):
        for name in ("art", "Biology", "chemistry", "Dance"):
            self.assessment({self.s1: 10}, subject=Subject.objects.create(name=name), name=name)
        names = [s.subject_name for s in marks_analytics.student_subject_scores(self.s1.student, self.term_b)]
        self.assertEqual(names, ["art", "Biology", "chemistry", "Dance"])


class TermsWithResultsTests(ProgressFixture, TestCase):
    def test_a_term_that_has_not_started_is_excluded(self):
        future = AcademicTerm.objects.create(
            academic_year=self.year, name="Term 3", start_date=datetime.date(2026, 10, 1),
            end_date=datetime.date(2026, 12, 1), display_order=3,
        )
        self.assessment({self.s1: 10}, term=future)
        self.assessment({self.s1: 10}, term=self.term_a)
        self.assertEqual(marks_analytics.terms_with_results(self.s1.student), [self.term_a])

    def test_scope_narrows_the_results_that_make_a_term_count(self):
        self.assessment({self.s1: 10}, term=self.term_a)
        other_grade, other_section, other = self.second_class()
        self.assessment({self.s1: 10}, term=self.term_b)
        scope = Q(assessment__term=self.term_b)
        self.assertEqual(
            marks_analytics.terms_with_results(self.s1.student, scope=scope), [self.term_b]
        )
        self.assertEqual(
            marks_analytics.terms_with_results(self.s1.student), [self.term_b, self.term_a]
        )


class BulletClampTests(TestCase):
    def test_score_is_clamped_to_0_100_and_a_real_zero_is_kept(self):
        self.assertEqual(charts.bullet(120, None, None)["score"], 100)
        self.assertEqual(charts.bullet(-5, None, None)["score"], 0)
        self.assertEqual(charts.bullet(0, None, None)["score"], 0)
        self.assertEqual(charts.bullet(64.5, 50, 70)["score"], 64.5)
