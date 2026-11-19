"""Admin home tab shell: four tabs by job, each its own URL (?tab=)."""

import datetime
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Assessment, ClassGrade, Section, Student, StudentResult
from core.tests.test_admin_overview_analytics import TODAY, A, MarksFixture, P

URL = reverse("core:admin-overview")
TAB_KEYS = ("today", "attendance", "academics", "parents")


def seed_academics(fx, extra_classes=3):
    """Data for every Academics card: finalized marks in both terms, a ready and an in-progress draft, no publications.

    Grade 1: s1 rises 40 points (improver), s2 falls 40 points (at risk). Each extra class has one
    student with steady marks, so four classes have results (best and worst show).
    """
    for term, (m1, m2) in ((fx.term_a, (10, 18)), (fx.term_b, (18, 10))):
        for n in (1, 2):
            fx.assessment({fx.s1: m1, fx.s2: m2}, name=f"Quiz {n}", term=term, pass_mark=10)
    for i in range(extra_classes):
        grade = ClassGrade.objects.create(name=f"Grade {i + 2}")
        section = Section.objects.create(class_grade=grade, name="A")
        student = fx.enroll_student(f"Steady Pupil {i}", grade, section)
        for term in (fx.term_a, fx.term_b):
            for n in (1, 2):
                fx.assessment(
                    {student: 10 + 2 * i}, name=f"Quiz {n}", term=term, class_grade=grade,
                    section=section, pass_mark=10,
                )
    fx.assessment({fx.s1: 15, fx.s2: 15}, name="Draft ready", finalize=False)
    fx.assessment({fx.s1: 12}, name="Draft marking", finalize=False)  # s2 unmarked: in progress


def card_html(html, name):
    """The text of one card, from its class to the next card (or the end of the section)."""
    start = html.index(f"erp-card--{name}")
    ends = [html.find("erp-card erp-card--", start + 10), html.find("</section>", start)]
    return html[start:min(e for e in ends if e != -1)]


def tab_nav(html):
    match = re.search(r'<nav class="erp-home-tabs" aria-label="Overview sections">(.*?)</nav>', html, re.S)
    assert match, "no tab bar"
    return match.group(1)


def tab_links(html):
    """[(label, href, current)] in page order."""
    return [
        (label, href, bool(current))
        for href, current, label in re.findall(
            r'<a class="erp-home-tab" href="([^"]*)"( aria-current="page")?>([^<]*)</a>', tab_nav(html)
        )
    ]


class HomeTabsTests(MarksFixture, TestCase):
    def get(self, client=None, **params):
        response = (client or self.administrator).get(URL, params)
        self.assertEqual(response.status_code, 200)
        return response

    def current_tab(self, response):
        return [label for label, _, current in tab_links(response.content.decode()) if current]

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_default_tab_is_today_and_marked_current(self):
        response = self.get()
        links = tab_links(response.content.decode())
        self.assertEqual([label for label, _, _ in links], ["Today", "Attendance", "Academics", "Parents"])
        self.assertEqual(
            [href for _, href, _ in links],
            [URL, f"{URL}?tab=attendance", f"{URL}?tab=academics", f"{URL}?tab=parents"],
        )
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertEqual(response.context["tab"], "today")

    def test_each_tab_has_its_own_url(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        response = self.get(tab="attendance")
        self.assertEqual(self.current_tab(response), ["Attendance"])
        self.assertContains(response, "Attendance heatmap")
        self.assertNotContains(response, "Birthdays")
        self.assertNotContains(response, "School at a glance")
        for key, label in (("academics", "Academics"), ("parents", "Parents")):
            with self.subTest(tab=key):
                self.assertEqual(self.current_tab(self.get(tab=key)), [label])

    def test_exactly_one_tab_context_is_built(self):
        names = {"today": "today", "attendance": "attendance_tab",
                 "academics": "academics_tab", "parents": "parents_tab"}
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                context = self.get(tab=key).context
                present = [name for name in names.values() if name in context]
                self.assertEqual(present, [names[key]])

    def test_unknown_or_empty_tab_shows_today(self):
        for value in ("nonsense", ""):
            with self.subTest(tab=value):
                response = self.get(tab=value)
                self.assertEqual(self.current_tab(response), ["Today"])
                self.assertIn("today", response.context)

    def test_old_period_links_are_ignored(self):
        response = self.get(period="term")
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertNotContains(response, "Custom range")
        self.assertNotContains(response, "erp-period")
        self.assertNotContains(response, 'role="status"')

    def test_only_the_active_tab_is_queried(self):
        self.get()  # warm per-process caches
        with CaptureQueriesContext(connection) as today:
            self.get()
        with CaptureQueriesContext(connection) as parents:
            self.get(tab="parents")
        self.assertLess(len(parents), len(today))

    def test_removed_parts_are_gone(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(tab=key)
                for gone in ("Still to finish", "Score bands", "Daily attendance",
                             "erp-ring", "erp-gauge", "Checklist"):
                    self.assertNotContains(response, gone)

    def test_viewer_without_student_permission_sees_no_names(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        Student.objects.filter(pk=self.s2.student_id).update(date_of_birth=datetime.date(2015, 7, 14))
        client = self.viewer("no-students", "view_school", "view_attendanceentry")
        birthdays = self.get(client).context["today"]["birthdays"]
        self.assertEqual(birthdays["count"], 1)
        self.assertEqual((birthdays["today"], birthdays["later"]), ([], []))
        response = self.get(client, tab="attendance")
        self.assertIsNone(response.context["attendance_tab"]["absentees"])
        self.assertNotContains(response, "Frequent absentees")
        self.assertNotContains(response, "Meena Das")
        # Holding students too brings the names back.
        both = self.viewer("both", "view_school", "view_attendanceentry", "view_student")
        self.assertEqual(self.get(both).context["today"]["birthdays"]["today"][0]["name"], "Meena Das")

    def test_nothing_repeats_across_tabs(self):
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(self.superuser_client, tab=key)
                if key == "parents":
                    self.assertContains(response, "Pending access reviews")
                else:
                    self.assertNotContains(response, "Pending access reviews")
                if key != "today":
                    self.assertNotContains(response, "Attendance today")
                    self.assertNotContains(response, "School at a glance")
        today = self.get(self.superuser_client).context["today"]
        self.assertNotIn("access_reviews", [c["key"] for c in today["cards"]])
        self.assertNotIn("attendance", [c["key"] for c in today["cards"]])
        self.assertIn("attendance", today)

    def test_today_context_is_pinned_to_the_business_date(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        today = self.get(self.superuser_client).context["today"]
        self.assertEqual((today["attendance"]["present"], today["attendance"]["absent"]), (1, 1))
        for key in ("compliance", "overdue_marks", "assessments", "birthdays", "glance_cards"):
            self.assertIn(key, today)

    def test_compliance_and_overdue_marks_need_their_view_permissions(self):
        today = self.get(self.viewer("plain", "view_school")).context["today"]
        self.assertIsNone(today["compliance"])
        self.assertIsNone(today["overdue_marks"])
        today = self.get(
            self.viewer("ops", "view_school", "view_attendanceregister", "view_assessment")
        ).context["today"]
        self.assertIsNotNone(today["compliance"])
        self.assertEqual(today["overdue_marks"], [])

    def test_not_taken_registers_need_view_attendanceregister(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        attendance = self.get(self.viewer("school-only", "view_school")).context["today"]["attendance"]
        self.assertIsNone(attendance["not_taken"])  # sections and their teachers are not listed
        self.assertTrue(attendance["school_day"])
        rows = self.get(
            self.viewer("registers", "view_school", "view_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1"])
        self.assertIsNotNone(rows[0]["url"])  # the draft opens on the register page
        rows = self.get(
            self.viewer("add-only", "view_school", "add_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertIsNone(rows)

    def test_parents_tab_shows_guardians_and_links_only_what_the_viewer_may_open(self):
        response = self.get(self.superuser_client, tab="parents")
        parents = response.context["parents_tab"]
        self.assertEqual(parents["glance"]["key"], "guardians")
        self.assertEqual(parents["announcements_url"], reverse("core:announcement-list"))
        self.assertContains(response, reverse("core:announcement-list"))
        plain = self.get(self.viewer("plain-parents", "view_school"), tab="parents").context["parents_tab"]
        self.assertIsNone(plain["access_review_card"])
        self.assertIsNone(plain["announcements_url"])
        self.assertEqual(plain["glance"]["url"], "")

    def test_tab_bar_markup_and_phone_css(self):
        from pathlib import Path

        from django.conf import settings

        html = self.get().content.decode()
        self.assertIn('<nav class="erp-home-tabs" aria-label="Overview sections">', html)
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-home-tab \{[^}]*min-height: 2\.75rem")

    def test_today_cards_in_order(self):
        html = self.get().content.decode()
        positions = [
            html.index(f'id="{anchor}"')
            for anchor in (
                "glance-title", "att-today-title", "compliance-title", "assess-title", "bday-title",
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_not_taken_row_shows_teacher_and_open_link(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        response = self.get()
        self.assertContains(response, "Not taken yet")
        row = response.context["today"]["attendance"]["not_taken"][0]
        self.assertContains(response, f"{row['class_name']} {row['section_name']}")
        self.assertContains(response, f'href="{row["url"]}">Open')

    def test_all_registers_in_message(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        self.assertContains(self.get(), "All registers are in.")

    def test_before_cutoff_shows_due_by_line(self):
        from unittest import mock

        from django.utils import timezone

        early = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(9, 0)))
        with mock.patch("django.utils.timezone.now", return_value=early):
            response = self.get()
        self.assertContains(response, "Registers are due by 10:00.")
        self.assertNotContains(response, "Not submitted yet")

    def test_non_school_day_has_no_due_by_line(self):
        from unittest import mock

        from django.utils import timezone

        saturday = datetime.date(2026, 7, 18)
        early = timezone.make_aware(datetime.datetime.combine(saturday, datetime.time(9, 0)))
        with (
            mock.patch("django.utils.timezone.now", return_value=early),
            mock.patch("core.views.business_today", return_value=saturday),
            mock.patch("core.reports.business_today", return_value=saturday),
        ):
            response = self.get()
        self.assertContains(response, "No school day today.")
        self.assertNotContains(response, "Registers are due by")
        self.assertNotContains(response, "Everyone is on time.")
        self.assertContains(response, "Nothing to check today.")

    def test_compliance_hidden_without_register_permission(self):
        response = self.get(self.viewer("no-reg", "view_school"))
        self.assertNotContains(response, "Teacher compliance")
        self.assertNotContains(response, "Not taken yet")

    def test_home_card_css_is_pinned(self):
        from pathlib import Path

        from django.conf import settings

        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-home-tabs {", css)
        self.assertIn('.erp-home-tab[aria-current="page"]', css)
        self.assertIn(".erp-home-grid {", css)
        self.assertRegex(css, r"@media \(min-width: 992px\) \{ \.erp-home-grid \{ grid-template-columns: repeat\(2")

    def _add_sections(self, count):
        from core.models import ClassGrade, Section

        for i in range(count):
            grade = ClassGrade.objects.create(name=f"Grade {20 + i}")
            section = Section.objects.create(class_grade=grade, name="A")
            self.enroll_student(f"Fold Pupil {i}", grade, section)

    def test_not_taken_list_folds_after_five(self):
        self._add_sections(6)  # plus Grade 1 = 7 sections, none submitted
        html = self.get().content.decode()
        card = html.split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 7)
        self.assertEqual(card.count("<details"), 1)
        self.assertIn("Show all 7 classes", card)
        visible = card.split("<details", 1)[0]
        self.assertEqual(visible.count('class="erp-home-row"'), 5)

    def test_not_taken_list_does_not_fold_at_five_or_fewer(self):
        self._add_sections(4)  # 5 sections in all
        card = self.get().content.decode().split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 5)
        self.assertNotIn("<details", card)

    def _week_assessments(self, count):
        from core.models import Assessment

        for i in range(count):
            a = self.assessment({}, name=f"Quiz {i}", finalize=False)
            Assessment.objects.filter(pk=a.pk).update(assessment_date=TODAY)

    def test_assessments_fold_after_five(self):
        self._week_assessments(7)
        html = self.get().content.decode()
        card = html.split('id="assess-title"', 1)[1].split('id="bday-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 7)
        self.assertEqual(card.count("<details"), 1)
        self.assertIn("Show all 7 assessments", card)
        self.assertEqual(card.split("<details", 1)[0].count('class="erp-home-row"'), 5)

    def test_birthdays_fold_after_five(self):
        Student.objects.filter(pk=self.s1.student_id).update(date_of_birth=datetime.date(2015, 7, 14))
        for i in range(6):
            self.enroll_student(f"Born Pupil {i}", self.class_grade, self.section)
        Student.objects.update(date_of_birth=datetime.date(2015, 7, 14))
        html = self.get().content.decode()
        card = html.split('id="bday-title"', 1)[1]
        self.assertGreaterEqual(card.count('class="erp-home-row"'), 6)
        self.assertEqual(card.count("<details"), 1)
        self.assertRegex(card, r"Show all \d+ birthdays")
        self.assertEqual(card.split("<details", 1)[0].count('class="erp-home-row"'), 5)

    def test_overdue_marks_hidden_without_view_assessment(self):
        response = self.get(self.viewer("regs-only", "view_school", "view_attendanceregister"))
        self.assertContains(response, "Teacher compliance")
        self.assertNotContains(response, "Marks overdue")


    def seed_attendance(self):
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})

    def four_classes(self):
        from core.models import ClassGrade, Section

        for i in range(2, 5):
            grade = ClassGrade.objects.create(name=f"Grade {i}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Class Pupil {i}", grade, section)
            self.day(datetime.date(2026, 7, 2), {student: P}, section=section, class_grade=grade)

    def test_attendance_cards_in_order(self):
        self.seed_attendance()
        html = self.get(tab="attendance").content.decode()
        order = [html.index(t) for t in ("Attendance this month", "Attendance heatmap", "Day of the week", "Absentees")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("Best and worst classes", html)  # one class only

    def test_absentee_switch_links_and_current(self):
        self.seed_attendance()
        month = self.get(tab="attendance").content.decode()
        self.assertIn('href="?tab=attendance&amp;absent=term"', month)
        self.assertRegex(month, r'<a class="erp-seg-link" href="\?tab=attendance" aria-current="page">This month</a>')
        term = self.get(tab="attendance", absent="term")
        self.assertEqual(term.context["attendance_tab"]["absent_view"], "term")
        self.assertContains(term, "Meena Das")
        self.assertContains(term, '<span class="erp-home-meta">0.0%</span>')
        self.assertNotContains(term, "days absent")
        self.assertContains(self.get(tab="attendance"), '<span class="erp-home-meta">6 days absent</span>')
        self.assertEqual(self.get(tab="attendance", absent="x").context["attendance_tab"]["absent_view"], "month")

    def test_no_names_in_either_absentee_view_without_view_student(self):
        self.seed_attendance()
        client = self.viewer("att-only", "view_school", "view_attendanceentry")
        for view in ("month", "term"):
            response = self.get(client, tab="attendance", absent=view)
            self.assertNotContains(response, "Meena Das")
            self.assertNotContains(response, "erp-seg")
            self.assertContains(response, "erp-analytics--no-absent")

    def test_class_links_need_view_classgrade(self):
        self.seed_attendance()
        self.four_classes()
        self.assertContains(self.get(tab="attendance"), "erp-class-link")
        client = self.viewer("no-classes", "view_school", "view_attendanceentry", "view_student")
        response = self.get(client, tab="attendance")
        self.assertContains(response, "Best and worst classes")
        self.assertNotContains(response, "erp-class-link")

    def test_attendance_tab_queries_do_not_grow_with_classes(self):
        self.seed_attendance()
        self.four_classes()
        self.get(tab="attendance")
        with CaptureQueriesContext(connection) as before:
            self.get(tab="attendance")
        from core.models import ClassGrade, Section

        for i in range(5, 8):
            grade = ClassGrade.objects.create(name=f"Grade {i}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Class Pupil {i}", grade, section)
            self.day(datetime.date(2026, 7, 2), {student: P}, section=section, class_grade=grade)
        with CaptureQueriesContext(connection) as after:
            self.get(tab="attendance")
        self.assertEqual(len(before), len(after))

    def test_capped_absentee_list_does_not_say_show_all(self):
        extra = [self.enroll_student(f"Many Absent {i}", self.class_grade, self.section) for i in range(11)]
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A, **{s: A for s in extra}})
        html = self.get(tab="attendance").content.decode()
        self.assertNotIn("Show all", html)
        self.assertIn("Show 5 more students", html)
        self.assertIn("Showing 10 of 12.", html)

    def test_absentee_row_omits_class_when_empty(self):
        from django.template.loader import render_to_string

        row = {"student_id": 1, "name": "No Class", "class_name": "", "absent_days": 3}
        html = render_to_string("partials/home/_absentee_row.html", {"r": row, "view": "month"})
        self.assertIn("No Class", html)
        self.assertNotIn("&middot;", html)

    def test_min_days_comes_from_context(self):
        from core import analytics

        self.seed_attendance()
        context = self.get(tab="attendance", absent="term").context["attendance_tab"]
        self.assertEqual(context["low_min_days"], analytics.LOW_ATTENDANCE_MIN_DAYS)
        self.assertContains(self.get(tab="attendance", absent="term"), f"({analytics.LOW_ATTENDANCE_MIN_DAYS} or more days marked)")

    def test_attendance_card_css_is_pinned(self):
        css = Path(settings.BASE_DIR, "static/css/erp.css").read_text(encoding="utf-8")
        for rule in ('.erp-seg-link[aria-current="page"]', ".erp-trend-figure",
                     ".erp-home .erp-analytics > .erp-card--trend { grid-column: span 12; }",
                     ".erp-home .erp-analytics > .erp-card--heat { grid-column: span 7; }",
                     ".erp-home .erp-analytics > .erp-card--weekday { grid-column: span 5; }",
                     ".erp-home .erp-analytics > .erp-card--absent { grid-column: span 6;",
                     ".erp-home .erp-analytics--no-classes > .erp-card--absent { grid-column: span 12; }",
                     ".erp-home .erp-analytics--no-absent > .erp-card--classes { grid-column: span 12; }"):
            self.assertIn(rule, css)


class AcademicsTabTests(MarksFixture, TestCase):
    url = reverse("core:admin-overview") + "?tab=academics"
    CARDS = ("results", "pass", "best", "subjects", "attention", "improvers")

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def page(self, client=None):
        response = (client or self.administrator).get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_academics_cards_in_spec_order(self):
        seed_academics(self)
        html = self.page()
        positions = [html.index(f"erp-card--{name}") for name in self.CARDS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), 6)
        self.assertNotIn("erp-analytics--no-", html)

    def test_ready_draft_is_listed_with_open_link(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("Ready to finalize", card)
        self.assertIn("Draft ready", card)
        pk = Assessment.objects.get(name="Draft ready").pk
        self.assertIn(reverse("core:assessment-detail", args=[pk]), card)

    def test_in_progress_count_link_has_a_screen_reader_name(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("assessments with marking in progress</span></a>", card)

    def test_at_risk_empty_text_with_a_previous_term_and_no_pass_marks(self):
        self.assessment({self.s1: 15}, term=self.term_a)
        self.assessment({self.s1: 15})
        card = card_html(self.page(), "attention")
        self.assertIn(
            "No pass marks are set for Term 2, and nobody's average is down 10+ points.", card
        )

    def test_stage_counts_and_labels(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("Results to finish, Term 2", card)
        for label in ("Marking in progress", "Ready to finalize", "Finalized, not published"):
            self.assertIn(label, card)
        self.assertEqual(card.count('class="erp-stage"'), 3)
        self.assertIn("status=DRAFT", card)

    def test_unpublished_section_has_publish_link(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        link = reverse("core:term-publication", args=[self.term_b.pk]) + f"?section={self.section.pk}"
        self.assertIn(link, card)
        self.assertIn(">Publish<", card.replace("Publish<span", "Publish<"))
        self.assertIn("To publish", card)

    def test_nothing_to_finish_says_so(self):
        self.assessment({self.s1: 15, self.s2: 10}, name="Done")
        self.assertIn("Finalized, not published", card_html(self.page(), "results"))
        StudentResult.objects.all().delete()
        Assessment.objects.all().delete()
        self.assertIn("Nothing to finish for Term 2.", card_html(self.page(), "results"))

    def test_without_publication_permission_no_publish_rows(self):
        seed_academics(self)
        link = reverse("core:term-publication", args=[self.term_b.pk])
        self.assertIn(link, card_html(self.page(), "results"))
        client = self.viewer("no-pub", "view_school", "view_assessment", "view_studentresult")
        card = card_html(self.page(client), "results")
        self.assertIn("Finalized, not published", card)
        self.assertNotIn("To publish", card)
        self.assertNotIn(link, card)

    def test_without_assessment_permission_no_results_card(self):
        seed_academics(self)
        self.assertIn("erp-card--results", self.page())
        client = self.viewer("no-assess", "view_school", "view_studentresult")
        html = self.page(client)
        self.assertNotIn("erp-card--results", html)
        self.assertNotIn("Draft ready", html)
        self.assertIn("erp-card--subjects", html)

    def test_without_student_permission_no_names_and_no_name_cards(self):
        seed_academics(self)
        name = self.s1.student.full_name
        full = self.page()
        self.assertIn("erp-card--attention", full)
        self.assertIn("erp-card--improvers", full)
        self.assertIn(name, full)
        client = self.viewer(
            "no-students", "view_school", "view_assessment", "view_studentresult",
            "view_attendanceentry", "view_classgrade",
        )
        html = self.page(client)
        self.assertNotIn("erp-card--attention", html)
        self.assertNotIn("erp-card--improvers", html)
        self.assertNotIn(name, html)
        self.assertNotIn(self.s2.student.full_name, html)
        self.assertIn("erp-analytics--no-attention", html)
        self.assertIn("erp-analytics--no-improvers", html)

    def test_class_rows_link_only_with_classgrade_permission(self):
        seed_academics(self)
        link = reverse("core:class-grade-detail", args=[self.class_grade.pk])
        full = self.page()
        self.assertIn(link, card_html(full, "pass"))
        client = self.viewer("no-classes", "view_school", "view_studentresult")
        html = self.page(client)
        self.assertIn("Grade 1", card_html(html, "pass"))
        self.assertNotIn(link, html)
        self.assertNotIn("erp-class-link", html)

    def test_class_rows_show_pass_rate_and_grades(self):
        seed_academics(self)
        Assessment.objects.filter(status=Assessment.Status.FINALIZED).update(
            grading_snapshot={"scale": "S", "bands": [["80", "A"], ["50", "B"], ["0", "C"]]}
        )
        card = card_html(self.page(), "pass")
        self.assertIn("Pass rate and grades by class, Term 2", card)
        self.assertIn("Pass rate 100%", card)
        self.assertIn("Pass rate 100% &middot; A 2 · B 2", card)

    def test_no_pass_mark_says_so(self):
        self.assessment({self.s1: 15, self.s2: 10})
        card = card_html(self.page(), "pass")
        self.assertIn("No pass mark set", card)
        self.assertNotIn("Pass rate 0%", card)

    def test_first_term_says_no_comparison_yet(self):
        for n in (1, 2):
            self.assessment({self.s1: 15, self.s2: 10}, name=f"Only {n}", pass_mark=10)
        html = self.page()
        self.assertIn("No comparison yet", card_html(html, "subjects"))
        self.assertIn("No comparison yet", card_html(html, "improvers"))

    def test_improver_row_and_subject_change_words(self):
        seed_academics(self)
        html = self.page()
        improvers = card_html(html, "improvers")
        self.assertIn(self.s1.student.full_name, improvers)
        self.assertIn("Up 40 points (50% \u2192 90%)", improvers)
        self.assertIn(reverse("core:student-detail", args=[self.s1.student_id]), improvers)
        self.assertIn("Change since Term 1", card_html(html, "subjects"))

    def test_marks_cards_name_the_reporting_term(self):
        for n in (1, 2):
            self.assessment({self.s1: 15, self.s2: 10}, name=f"Old {n}", term=self.term_a)
        self.assessment({self.s1: 15}, name="Open draft", term=self.term_b, finalize=False)
        html = self.page()
        self.assertIn("Results to finish, Term 2", card_html(html, "results"))
        self.assertIn("by class, Term 1", card_html(html, "pass"))
        self.assertIn("Subjects, Term 1", card_html(html, "subjects"))

    def test_falling_threshold_is_ten_points(self):
        for term, a, b in ((self.term_a, 80, 80), (self.term_b, 70, 70.1)):
            for n in (1, 2):
                self.assessment({self.s1: a, self.s2: b}, name=f"Cut {n}", term=term, maximum="100")
        context = self.administrator.get(self.url).context["academics_tab"]
        names = [r["name"] for r in context["attention"]["rows"]]
        self.assertIn(self.s1.student.full_name, names)  # exactly -10.0
        self.assertNotIn(self.s2.student.full_name, names)  # -9.9
        self.assertIn("Average down 10 points since Term 1", card_html(self.page(), "attention"))

    def test_academics_query_count_does_not_grow(self):
        seed_academics(self, extra_classes=3)
        self.page()
        with CaptureQueriesContext(connection) as before:
            self.page()
        for i in range(3, 5):
            grade = ClassGrade.objects.create(name=f"Grade {i + 2}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Late Pupil {i}", grade, section)
            for term in (self.term_a, self.term_b):
                for n in (1, 2):
                    self.assessment(
                        {student: 12}, name=f"Quiz {n}", term=term, class_grade=grade,
                        section=section, pass_mark=10,
                    )
        with CaptureQueriesContext(connection) as after:
            self.page()
        self.assertEqual(len(before), len(after))

    def test_academics_css_is_pinned(self):
        css = Path(settings.BASE_DIR, "static/css/erp.css").read_text(encoding="utf-8")
        for rule in (
            ".erp-home .erp-analytics > .erp-card--results { grid-column: span 12; }",
            ".erp-home .erp-analytics > .erp-card--pass { grid-column: span 7; }",
            ".erp-home .erp-analytics > .erp-card--best { grid-column: span 5; }",
            ".erp-home .erp-analytics > .erp-card--subjects { grid-column: span 12; }",
            ".erp-home .erp-analytics > .erp-card--attention { grid-column: span 7; align-self: start; }",
            ".erp-home .erp-analytics > .erp-card--improvers { grid-column: span 5; align-self: start; }",
            ".erp-home .erp-analytics--no-best > .erp-card--pass { grid-column: span 12; }",
            ".erp-home .erp-analytics--no-attention > .erp-card--improvers { grid-column: span 12; }",
            ".erp-home .erp-analytics--no-improvers > .erp-card--attention { grid-column: span 12; }",
            ".erp-stage-list {",
            ".erp-class-note {",
        ):
            self.assertIn(rule, css)


class OverviewNoBootstrapTests(MarksFixture, TestCase):
    BANNED = ('class="btn', " btn-", "visually-hidden", "text-muted", '"progress"', "progress-bar", "mt-auto", "align-self-start")

    OLD_CARD_NAMES = ("erp-home-card", "erp-chart-card", "erp-analytics-card", "erp-home-empty", "erp-analytics-empty")

    def test_overview_cards_use_erp_card(self):
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        for tab, extra in (("today", {}), ("attendance", {}), ("attendance", {"absent": "term"}), ("academics", {})):
            html = self.administrator.get(URL, {"tab": tab, **extra}).content.decode()
            body = html[html.index('class="erp-page-header'):html.index("</main>")]
            with self.subTest(tab=tab, extra=extra):
                self.assertIn("erp-card", body)
                for old in self.OLD_CARD_NAMES:
                    self.assertNotIn(old, body)

    def test_overview_uses_no_bootstrap_classes(self):
        saw_setup = False
        saw_attention = False
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        seed_academics(self)
        pages = [(tab, {}) for tab in TAB_KEYS] + [("attendance", {"absent": "term"})]
        for tab, extra in pages:
            response = self.administrator.get(URL, {"tab": tab, **extra})
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            saw_setup = saw_setup or "Set up your school" in html
            saw_attention = saw_attention or "erp-stat-card--attention" in html
            # Page header to the end of main: the base shell (sidebar, top bar) may still use Bootstrap.
            body = html[html.index('class="erp-page-header'):html.index("</main>")]
            for banned in self.BANNED:
                with self.subTest(tab=tab, extra=extra, banned=banned):
                    self.assertNotIn(banned, body)
        self.assertTrue(saw_setup, "fixture should show the setup card")
