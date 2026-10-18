"""U3.1 Teacher Mobile Polish: shell and bottom navigation (Gate T1)."""

import re
from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister, School, SectionClassTeacher
from core.navigation import TEACHER_TAB_PARENTS, teacher_tabs
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_ui_teacher_marks import MarksFixture

TABBAR = re.compile(r'<nav class="erp-tabbar.*?</nav>', re.DOTALL)
BODY_TAG = re.compile(r"<body class=\"([^\"]*)\"")


def tabbar_html(page):
    return TABBAR.search(page.content.decode()).group(0)


def body_classes(page):
    return BODY_TAG.search(page.content.decode()).group(1).split()


class TeacherBottomNavTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")
        self.client.login(username="rao", password="pass-12345")

    def test_data_keeps_desktop_labels_and_adds_mobile_labels(self):
        tabs = teacher_tabs("my-home")
        self.assertEqual([t["label"] for t in tabs],
                         ["My day", "My students", "My assessments", "Results"])
        self.assertEqual([t["mobile_label"] for t in tabs],
                         ["Today", "Students", "Assessments", "Results"])
        self.assertEqual([t["url"] for t in tabs], [
            reverse("core:my-home"), reverse("core:my-students"),
            reverse("core:my-assessments"), reverse("core:my-results"),
        ])

    def test_bottom_bar_labels_and_order(self):
        bar = tabbar_html(self.client.get(reverse("core:my-home")))
        labels = re.findall(r'<span class="erp-tab-label">([^<]+)</span>', bar)
        self.assertEqual(labels, ["Today", "Students", "Assessments", "Results"])
        hrefs = re.findall(r'<a href="([^"]+)"', bar)
        self.assertEqual(hrefs, [
            reverse("core:my-home"), reverse("core:my-students"),
            reverse("core:my-assessments"), reverse("core:my-results"),
        ])

    def test_every_item_has_a_decorative_icon_and_a_text_label(self):
        bar = tabbar_html(self.client.get(reverse("core:my-home")))
        items = re.findall(r"<li>(.*?)</li>", bar, re.DOTALL)
        self.assertEqual(len(items), 4)
        for item in items:
            self.assertIn('class="erp-tab-icon"', item)
            self.assertIn('aria-hidden="true"', item)
            label = re.search(r'<span class="erp-tab-label">([^<]*)</span>', item)
            self.assertTrue(label and label.group(1).strip())

    def test_active_item_is_marked_on_each_destination(self):
        cases = (
            ("core:my-home", "Today"),
            ("core:my-students", "Students"),
            ("core:my-assessments", "Assessments"),
            ("core:my-results", "Results"),
        )
        for url_name, label in cases:
            with self.subTest(url_name):
                bar = tabbar_html(self.client.get(reverse(url_name)))
                self.assertEqual(bar.count('aria-current="page"'), 1)
                active = re.search(
                    r'<a href="[^"]+" class="active" aria-current="page">.*?'
                    r'<span class="erp-tab-label">([^<]+)</span>', bar, re.DOTALL)
                self.assertEqual(active.group(1), label)

    def test_desktop_top_bar_and_page_headings_keep_long_labels(self):
        page = self.client.get(reverse("core:my-students"))
        html = page.content.decode()
        top = re.search(r'<nav class="erp-topbar-links.*?</nav>', html, re.DOTALL).group(0)
        for label in ("My day", "My students", "My assessments", "Results"):
            self.assertIn(f">{label}</a>", top)
        self.assertContains(page, "My students")

    def test_bar_is_still_phone_only(self):
        self.assertIn("d-lg-none", tabbar_html(self.client.get(reverse("core:my-home"))))


class TeacherAreaHookTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def test_teacher_pages_carry_the_hook(self):
        self.client.login(username="rao", password="pass-12345")
        for url_name in ("core:my-home", "core:my-students",
                         "core:my-assessments", "core:my-results"):
            with self.subTest(url_name):
                classes = body_classes(self.client.get(reverse(url_name)))
                self.assertIn("erp-teacher", classes)
                self.assertIn("has-tabbar", classes)

    def test_office_pages_do_not_carry_the_hook(self):
        self.client.login(username="admin", password="pass-12345")
        classes = body_classes(self.client.get(reverse("core:student-list")))
        self.assertNotIn("erp-teacher", classes)

    def test_admin_who_teaches_has_hook_only_in_teaching_area(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        self.assertNotIn("erp-teacher",
                         body_classes(self.client.get(reverse("core:school-detail"))))
        self.assertIn("erp-teacher",
                      body_classes(self.client.get(reverse("core:my-home"))))

    def test_login_page_does_not_carry_the_hook(self):
        self.assertNotIn("erp-teacher", body_classes(self.client.get(reverse("login"))))


PARENT_LABELS = {
    "my-home": "Today", "my-students": "Students",
    "my-assessments": "Assessments", "my-results": "Results",
}


class NestedPageActiveTabTests(TestCase):
    """Nested Teacher pages keep their parent destination active (central map)."""

    def test_every_nested_name_activates_its_parent(self):
        for url_name, parent in TEACHER_TAB_PARENTS.items():
            with self.subTest(url_name):
                active = [t["mobile_label"] for t in teacher_tabs(url_name) if t["active"]]
                self.assertEqual(active, [PARENT_LABELS[parent]])

    def test_destinations_activate_themselves_and_unknown_names_none(self):
        for url_name, label in PARENT_LABELS.items():
            active = [t["mobile_label"] for t in teacher_tabs(url_name) if t["active"]]
            self.assertEqual(active, [label])
        self.assertEqual([t for t in teacher_tabs("student-list") if t["active"]], [])

    def test_map_covers_the_agreed_nested_pages(self):
        self.assertEqual(
            {name: PARENT_LABELS[parent] for name, parent in TEACHER_TAB_PARENTS.items()},
            {
                "my-attendance": "Today", "my-attendance-history": "Today",
                "my-attendance-assignment": "Today", "my-attendance-register": "Today",
                "my-student-detail": "Students",
                "my-gradebook": "Assessments", "assessment-marks-entry": "Assessments",
                "my-subject-results": "Results", "my-report-card": "Results",
            },
        )


class NestedPageRenderTests(MarksFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.class_duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )

    def register(self, submit):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 10, 12),
        )
        register.save_draft_entry(enrollment=self.asha, status="PRESENT")
        register.save_draft_entry(enrollment=self.bina, status="ABSENT")
        register.save_draft_entry(enrollment=self.ravi, status="PRESENT")
        if submit:
            register.submit(actor=self.rao)
        return register

    def assert_one_current(self, page, label):
        bar = tabbar_html(page)
        self.assertEqual(bar.count('aria-current="page"'), 1)
        active = re.search(
            r'class="active" aria-current="page">.*?'
            r'<span class="erp-tab-label">([^<]+)</span>', bar, re.DOTALL)
        self.assertEqual(active.group(1), label)

    def test_nested_pages_keep_the_parent_tab_active(self):
        submitted = self.register(submit=True)
        cases = (
            (reverse("core:my-student-detail", args=[self.asha.student.pk]), "Students"),
            (reverse("core:my-attendance-history"), "Today"),
            (reverse("core:my-attendance-assignment", args=[self.class_duty.pk]), "Today"),
            (reverse("core:my-attendance-register", args=[submitted.pk]), "Today"),
            (reverse("core:my-attendance", args=[self.six_a.pk]), "Today"),
            (reverse("core:my-gradebook", args=[self.duty.pk]), "Assessments"),
            (reverse("core:my-subject-results", args=[self.duty.pk]), "Results"),
        )
        for url, label in cases:
            with self.subTest(url):
                page = self.teacher.get(url)
                self.assertEqual(page.status_code, 200)
                self.assert_one_current(page, label)
                self.assertIn("erp-teacher", body_classes(page))

    def test_finalized_marks_entry_keeps_assessments_active(self):
        self.force_finalize(self.test1)
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertEqual(page.status_code, 200)
        self.assert_one_current(page, "Assessments")

    def test_drafting_pages_may_still_hide_the_bar(self):
        self.register(submit=False)
        attendance = self.teacher.get(reverse("core:my-attendance", args=[self.six_a.pk]))
        self.assertNotContains(attendance, 'class="erp-tabbar')
        self.assertNotIn("has-tabbar", body_classes(attendance))
        entry = self.teacher.get(self.entry_url(self.test1))
        self.assertTrue(entry.context["form"].enrollments)
        self.assertNotContains(entry, 'class="erp-tabbar')
        self.assertNotIn("has-tabbar", body_classes(entry))
        for page in (attendance, entry):
            self.assertIn("erp-teacher", body_classes(page))

    def test_exactly_one_current_whenever_the_bar_renders(self):
        self.register(submit=True)
        urls = (
            reverse("core:my-home"), reverse("core:my-students"),
            reverse("core:my-assessments"), reverse("core:my-results"),
            reverse("core:my-attendance-history"),
            reverse("core:my-gradebook", args=[self.duty.pk]),
            self.entry_url(self.test1),
            reverse("core:my-attendance", args=[self.six_a.pk]),
        )
        for url in urls:
            with self.subTest(url):
                page = self.teacher.get(url)
                if 'class="erp-tabbar' in page.content.decode():
                    self.assertEqual(tabbar_html(page).count('aria-current="page"'), 1)


class MyDayPolishTests(MarksFixture, TestCase):
    """U3.1 Gate T2: My day."""

    def setUp(self):
        super().setUp()
        self.class_duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.url = reverse("core:my-home")
        self.attendance_url = reverse("core:my-attendance", args=[self.six_a.pk])

    def home(self):
        return self.teacher.get(self.url)

    def draft_register(self, submit=False):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 10, 12),
        )
        register.save_draft_entry(enrollment=self.asha, status="PRESENT")
        if submit:
            register.save_draft_entry(enrollment=self.bina, status="PRESENT")
            register.save_draft_entry(enrollment=self.ravi, status="PRESENT")
            register.submit(actor=self.rao)
        return register

    def attendance_links(self, page):
        return page.content.decode().count(f'href="{self.attendance_url}"')

    def test_heading_and_real_date_are_kept(self):
        page = self.home()
        self.assertContains(page, '<h1 class="h3 mb-1">My day</h1>')
        self.assertContains(page, "Monday, 12 October 2026")
        self.assertContains(page, "Attendance</h2>")
        self.assertContains(page, "Marks to enter</h2>")

    def test_section_is_the_dominant_element_of_an_attendance_card(self):
        page = self.home()
        self.assertContains(page, f'<p class="erp-day-title">{self.six_a}</p>')

    def test_not_taken_has_exactly_one_primary_action(self):
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-pending">Not taken</span>')
        self.assertContains(page, ">Take attendance<")
        self.assertContains(page, "btn btn-primary")
        self.assertEqual(self.attendance_links(page), 1)
        self.assertContains(page, f'aria-label="Take attendance for {self.six_a}"')

    def test_draft_has_exactly_one_continue_action(self):
        self.draft_register()
        page = self.home()
        self.assertContains(
            page, '<span class="erp-pill is-draft">Draft &mdash; not yet submitted</span>')
        self.assertContains(page, ">Continue<")
        self.assertNotContains(page, ">Take attendance<")
        self.assertEqual(self.attendance_links(page), 1)

    def test_submitted_has_exactly_one_view_action(self):
        self.draft_register(submit=True)
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-submitted">Submitted</span>')
        self.assertContains(page, ">View<")
        self.assertNotContains(page, ">Take attendance<")
        self.assertNotContains(page, ">Continue<")
        self.assertEqual(self.attendance_links(page), 1)

    def test_not_a_school_day_has_no_action(self):
        with mock.patch("core.models.AcademicYear.is_instructional_day", return_value=False):
            page = self.home()
        self.assertContains(page, '<span class="erp-pill">Not a school day</span>')
        self.assertEqual(self.attendance_links(page), 0)

    def test_teacher_without_a_class_keeps_the_empty_wording(self):
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        page = iyer.get(self.url)
        self.assertContains(page, "You are not a class teacher today.")
        self.assertContains(page, "ask the office to check your assignment")

    def test_attendance_history_is_a_clear_secondary_action(self):
        page = self.home()
        history = reverse("core:my-attendance-history")
        self.assertContains(
            page, f'<a class="btn btn-outline-secondary erp-day-secondary" href="{history}">')
        self.assertContains(page, "Attendance history for my Sections")
        self.assertNotContains(page, f'<p><a href="{history}">')

    def test_waiting_marks_keep_real_data_and_links(self):
        page = self.home()
        waiting = page.context["assessments"]
        self.assertTrue(waiting)
        self.assertNotContains(page, "No marks waiting")
        for assessment in waiting:
            self.assertContains(page, f'href="{self.entry_url(assessment)}"')
            self.assertContains(page, assessment.name)
            self.assertContains(page, f"{assessment.unmarked_count} unmarked")

    def test_empty_marks_state_is_neutral_and_links_to_assessments(self):
        self.force_finalize(self.test1)
        self.force_finalize(self.test2)
        page = self.home()
        self.assertEqual(page.context["assessments"], [])
        self.assertContains(page, "No marks waiting")
        self.assertContains(page, "No open assessments are waiting for your marks.")
        self.assertNotContains(page, "Nothing waiting")
        self.assertContains(page, f'href="{reverse("core:my-assessments")}"')
        self.assertContains(page, ">My assessments<")

    def test_term_remarks_are_whole_card_links_with_real_progress(self):
        page = self.home()
        rows = page.context["remarks"]
        self.assertTrue(rows)
        html = page.content.decode()
        section = html.split('id="day-remarks"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(section.count("<a "), len(rows))
        for row in rows:
            href = (f'{reverse("core:term-remarks", args=[row["term"].pk])}'
                    f'?section={row["section"].pk}')
            self.assertContains(page, f'href="{href}"')
            self.assertContains(page, f'{row["written"]} of {row["expected"]} written')
            self.assertContains(
                page, f'max="{row["expected"] or 1}" value="{row["written"]}"')
        self.assertContains(page, 'class="erp-progress"')

    def test_no_tables_and_no_totals_or_ranks(self):
        html = self.home().content.decode()
        self.assertNotIn("<table", html)
        for word in ("Total", "Average", "Rank"):
            self.assertNotIn(word, html)
