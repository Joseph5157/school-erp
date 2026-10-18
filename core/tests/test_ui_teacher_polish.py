"""U3.1 Teacher Mobile Polish: shell and bottom navigation (Gate T1)."""

import re
from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import formats

from core.models import AssessmentTeacherAssignment as Assignment
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


ROW = re.compile(r'<li class="erp-student-row[^"]*">(.*?)</li>', re.DOTALL)


class MyStudentsPolishTests(MarksFixture, TestCase):
    """U3.1 Gate T3: My students."""

    def setUp(self):
        super().setUp()
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.url = reverse("core:my-students")

    def page(self):
        return self.teacher.get(self.url)

    def rows(self, page):
        return ROW.findall(page.content.decode())

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

    def test_heading_and_context_wording_are_kept(self):
        page = self.page()
        self.assertContains(page, '<h1 class="h3 mb-1">My students</h1>')
        self.assertContains(page, "Students enrolled today (")
        self.assertContains(page, "in Sections you are class teacher of or teach a Subject in.")
        self.assertContains(page, f"{self.six_a} ")

    def test_each_row_has_exactly_one_link_to_the_student(self):
        page = self.page()
        rows = self.rows(page)
        self.assertEqual(len(rows), 3)
        expected = {
            e.student.full_name: reverse("core:my-student-detail", args=[e.student.pk])
            for e in (self.asha, self.bina, self.ravi)
        }
        for row in rows:
            self.assertEqual(row.count("<a "), 1)
            link = re.search(
                r'<a class="erp-student-name stretched-link" href="([^"]+)">([^<]+)</a>', row)
            self.assertEqual(expected[link.group(2)], link.group(1))
            self.assertNotIn("<button", row)

    def test_initials_are_decorative_and_the_name_is_the_link_text(self):
        for row in self.rows(self.page()):
            initial = re.search(
                r'<span class="erp-initials" aria-hidden="true">(.)</span>', row)
            name = re.search(r'class="erp-student-name[^"]*"[^>]*>([^<]+)</a>', row).group(1)
            self.assertEqual(initial.group(1), name[0].upper())
            self.assertIn('aria-hidden="true">&rsaquo;', row)

    def test_class_teacher_badge_only_on_class_teacher_sections(self):
        self.make_student("Kiran", section=self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        html = self.page().content.decode()
        six_a = html[html.index(str(self.six_a)):html.index(str(self.six_b))]
        six_b = html[html.index(str(self.six_b)):]
        self.assertIn('<span class="erp-pill is-accepted">Class teacher</span>', six_a)
        self.assertNotIn("Class teacher</span>", six_b)

    def test_submitted_attendance_shows_semantic_non_interactive_chips(self):
        self.register(submit=True)
        page = self.page()
        self.assertContains(page, '<span class="erp-pill is-present">Present</span>', count=2)
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>', count=1)
        self.assertNotContains(page, "not submitted yet")
        for row in self.rows(page):
            self.assertEqual(row.count("<a "), 1)
            self.assertNotRegex(row, r"<(a|button)[^>]*>\s*(Present|Absent)")

    def test_draft_attendance_keeps_the_not_submitted_wording_and_no_chips(self):
        self.register(submit=False)
        page = self.page()
        self.assertContains(page, "Today's attendance not submitted yet.")
        self.assertNotContains(page, "erp-pill is-present")
        self.assertNotContains(page, "erp-pill is-absent")

    def test_missing_attendance_keeps_the_not_submitted_wording_and_no_chips(self):
        page = self.page()
        self.assertContains(page, "Today's attendance not submitted yet.")
        self.assertNotContains(page, "erp-pill is-present")

    def test_subject_only_section_has_no_chips_or_attendance_note(self):
        self.make_student("Kiran", section=self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.register(submit=True)
        html = self.page().content.decode()
        part = html[html.index(str(self.six_b)):]
        self.assertNotIn("erp-pill is-present", part)
        self.assertNotIn("erp-pill is-absent", part)
        self.assertNotIn("not submitted yet", part)
        self.assertIn("Kiran", part)

    def test_empty_state_for_a_teacher_with_no_sections(self):
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        page = iyer.get(self.url)
        self.assertContains(page, "No Students in your Sections today.")
        self.assertContains(page, "Ask the school office if this looks wrong.")
        self.assertEqual(self.rows(page), [])

    def test_order_and_urls_follow_the_view(self):
        self.make_student("Kiran", section=self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        page = self.page()
        html = page.content.decode()
        names = re.findall(r'class="erp-student-name[^"]*" href="[^"]+">([^<]+)</a>', html)
        hrefs = re.findall(r'class="erp-student-name[^"]*" href="([^"]+)">', html)
        groups = page.context["groups"]
        self.assertEqual(
            names, [e.student.full_name for g in groups for e in g["enrollments"]])
        self.assertEqual(
            hrefs,
            [reverse("core:my-student-detail", args=[e.student.pk])
             for g in groups for e in g["enrollments"]])
        for group in groups:
            in_group = [e.student.full_name for e in group["enrollments"]]
            self.assertEqual(in_group, sorted(in_group))

    def test_no_table_search_or_sort_controls(self):
        html = self.page().content.decode()
        self.assertNotIn("<table", html)
        self.assertNotIn('type="search"', html)
        self.assertNotIn("<select", html)


class MyAssessmentsPolishTests(MarksFixture, TestCase):
    """U3.1 Gate T4: My assessments."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-assessments")

    def page(self):
        return self.teacher.get(self.url)

    def class_teacher(self):
        return SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )

    def duty_blocks(self, page):
        html = page.content.decode()
        return [part.split("</section>", 1)[0]
                for part in html.split('<section class="erp-assess-duty"')[1:]]

    def test_heading_is_kept(self):
        page = self.page()
        self.assertContains(page, '<h1 class="h3 mb-3">My assessments</h1>')
        self.assertContains(page, "Term remarks</h2>")
        self.assertNotContains(page, "You enter marks for nothing yet")

    def test_each_duty_is_one_group_with_subject_section_dominant(self):
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.make_assessment(offering=self.sanskrit, section=self.six_b, name="Sanskrit Quiz",
                             on=date(2026, 7, 20))
        page = self.page()
        duties = page.context["duties"]
        self.assertEqual(len(duties), 2)
        blocks = self.duty_blocks(page)
        self.assertEqual(len(blocks), 2)
        for duty in duties:
            title = (f'<h2 class="erp-assess-title" id="duty-{duty.pk}">'
                     f'{duty.offering.subject.name} &middot; {duty.section}</h2>')
            block = next(b for b in blocks if title in b)
            self.assertIn(
                f'<p class="erp-card-meta">{duty.offering.academic_year.name}</p>', block)
            self.assertEqual(block.count("Gradebook</a>"), 1)
            self.assertIn(f'href="{reverse("core:my-gradebook", args=[duty.pk])}"', block)
        by_title = {("Mathematics" in b): b for b in blocks}
        self.assertIn("Unit Test 1", by_title[True])
        self.assertNotIn("Sanskrit Quiz", by_title[True])
        self.assertIn("Sanskrit Quiz", by_title[False])
        self.assertNotIn("Unit Test 1", by_title[False])

    def test_assessment_rows_have_name_date_status_and_one_entry_link(self):
        block = self.duty_blocks(self.page())[0]
        rows = re.findall(r'<li class="erp-assess-row[^"]*">(.*?)</li>', block, re.DOTALL)
        self.assertEqual(len(rows), 2)
        for assessment in (self.test1, self.test2):
            row = next(r for r in rows if assessment.name in r)
            self.assertEqual(row.count("<a "), 1)
            self.assertIn(
                f'<a class="erp-assess-name stretched-link" '
                f'href="{self.entry_url(assessment)}">{assessment.name}</a>', row)
            day = assessment.assessment_date
            self.assertIn(f"{day.day} {day.strftime('%b')}", row)
            self.assertIn('aria-hidden="true">&rsaquo;', row)

    def test_rows_keep_the_views_order(self):
        html = self.page().content.decode()
        self.assertLess(html.index("Unit Test 2"), html.index("Unit Test 1"))

    def test_draft_and_finalized_pills_are_non_interactive_status(self):
        page = self.page()
        self.assertContains(page, '<span class="erp-pill is-draft">Draft</span>', count=2)
        self.force_finalize(self.test1)
        page = self.page()
        self.assertContains(page, '<span class="erp-pill is-submitted">Finalized</span>', count=1)
        self.assertContains(page, '<span class="erp-pill is-draft">Draft</span>', count=1)
        for block in self.duty_blocks(page):
            for pill in re.findall(r'<span class="erp-pill[^"]*">[^<]+</span>', block):
                before = block[:block.index(pill)]
                self.assertTrue(before.rfind("</a>") > before.rfind("<a "))

    def test_no_duty_shows_the_purposeful_empty_state(self):
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        page = iyer.get(self.url)
        self.assertContains(page, "No assessments assigned")
        self.assertContains(page, "set by the school office")
        self.assertNotContains(page, "You enter marks for nothing yet")
        self.assertEqual(self.duty_blocks(page), [])

    def test_term_remarks_are_whole_row_links_with_the_section_query(self):
        self.class_teacher()
        page = self.page()
        links = page.context["remark_links"]
        self.assertTrue(links)
        html = page.content.decode()
        remarks = html.split('id="assess-remarks"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(remarks.count("<a "), len(links))
        self.assertEqual(remarks.count("erp-day-linkcard"), len(links))
        for term, section in links:
            href = f'{reverse("core:term-remarks", args=[term.pk])}?section={section.pk}'
            self.assertContains(page, f'href="{href}"')
            self.assertIn(f"{term.academic_year.name} {term.name} &middot; {section}", remarks)
        self.assertNotIn("<li>", remarks)
        self.assertNotContains(page, "No Sections assigned.")

    def test_no_remark_sections_shows_a_quiet_empty_state(self):
        page = self.page()
        self.assertEqual(page.context["remark_links"], [])
        self.assertContains(page, "No Sections are available for term remarks.")
        self.assertNotContains(page, "erp-day-linkcard")
        self.assertNotContains(page, "<li>No Sections assigned.</li>")

    def test_no_totals_averages_ranks_or_invented_progress(self):
        self.class_teacher()
        html = self.page().content.decode()
        for word in ("Total", "Average", "Rank", "<progress", "unmarked", "%"):
            self.assertNotIn(word, html)
        self.assertNotIn("<table", html)


RESULT_ROW = re.compile(r'<li class="erp-results-row([^"]*)">(.*?)</li>', re.DOTALL)


class MyResultsPolishTests(MarksFixture, TestCase):
    """U3.1 Gate T5: Results."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:my-results")
        # rao: Maths 6A handed over to iyer on 1 Oct (past), Sanskrit 6B (current),
        # Maths 6B from 1 Nov (starting soon). Today is 12 Oct.
        Assignment.assign(teacher=self.iyer, offering=self.maths, section=self.six_a,
                          start_date=date(2026, 10, 1))
        self.past = Assignment.objects.get(pk=self.duty.pk)
        self.current = self.assign(self.rao, self.sanskrit, self.six_b)
        self.upcoming = Assignment.assign(teacher=self.rao, offering=self.maths,
                                          section=self.six_b, start_date=date(2026, 11, 1))

    def page(self):
        return self.teacher.get(self.url)

    def section(self, page, ident):
        html = page.content.decode()
        return html.split(f'id="{ident}"', 1)[1].split("</section>", 1)[0]

    def rows(self, block):
        return RESULT_ROW.findall(block)

    def test_context_sorts_the_three_kinds_of_duty(self):
        page = self.page()
        self.assertEqual(list(page.context["duties"]), [self.current])
        self.assertEqual(list(page.context["upcoming_duties"]), [self.upcoming])
        self.assertEqual(list(page.context["past_duties"]), [self.past])

    def test_heading_and_finalized_only_explanation_are_kept(self):
        page = self.page()
        self.assertContains(page, '<h1 class="h3 mb-3">Results for my Subjects</h1>')
        self.assertContains(
            page, "Finalized results only, for the Subjects and Sections you teach.")

    def test_current_duty_is_one_whole_row_link(self):
        page = self.page()
        rows = self.rows(self.section(page, "results-current"))
        self.assertEqual(len(rows), 1)
        classes, row = rows[0]
        self.assertIn("is-link", classes)
        self.assertEqual(row.count("<a "), 1)
        self.assertIn(
            f'<a class="erp-results-name stretched-link" '
            f'href="{reverse("core:my-subject-results", args=[self.current.pk])}">'
            f'{self.current.offering.subject.name} &middot; {self.current.section}</a>', row)
        self.assertIn(
            f'<span class="erp-card-meta">{self.current.offering.academic_year.name}</span>', row)
        self.assertIn('aria-hidden="true">&rsaquo;', row)

    def test_no_current_duty_is_truthful_and_keeps_the_other_sections(self):
        self.current.end(date(2026, 10, 5))
        page = self.page()
        self.assertEqual(list(page.context["duties"]), [])
        self.assertContains(page, "No current Subject duties")
        self.assertContains(page, "The school office assigns Subjects")
        self.assertNotContains(page, "No subject results yet")
        self.assertNotContains(page, "no finalized results")
        self.assertContains(page, "Starting soon")
        self.assertContains(page, "Past duties")

    def test_teacher_with_no_duties_at_all_sees_the_same_neutral_state(self):
        self.make_user("newt", self.teachers)
        client = self.client_class()
        client.login(username="newt", password="pass-12345")
        page = client.get(self.url)
        self.assertContains(page, "No current Subject duties")
        self.assertContains(page, "The school office assigns Subjects")
        self.assertNotContains(page, "No subject results yet")
        self.assertNotContains(page, "Starting soon")
        self.assertNotContains(page, "Past duties")

    def test_starting_soon_rows_are_informational_with_the_real_start_date(self):
        page = self.page()
        block = self.section(page, "results-soon")
        rows = self.rows(block)
        self.assertEqual(len(rows), 1)
        classes, row = rows[0]
        self.assertNotIn("is-link", classes)
        self.assertNotIn("<a ", row)
        self.assertNotIn("&rsaquo;", row)
        self.assertIn(
            f"{self.upcoming.offering.subject.name} &middot; {self.upcoming.section}", row)
        self.assertIn(f"from {formats.localize(self.upcoming.start_date)}", row)
        self.assertIn("erp-results-list--info", block)

    def test_past_duties_are_read_only_links_with_the_real_dates(self):
        page = self.page()
        block = self.section(page, "results-past")
        self.assertIn(
            "Read-only. Only results from the dates you taught each Subject are shown.", block)
        rows = self.rows(block)
        self.assertEqual(len(rows), 1)
        classes, row = rows[0]
        self.assertIn("is-link", classes)
        self.assertEqual(row.count("<a "), 1)
        self.assertIn(
            f'href="{reverse("core:my-subject-results", args=[self.past.pk])}"', row)
        self.assertIn(
            f"{formats.localize(self.past.start_date)} to "
            f"{formats.localize(self.past.last_effective_date)}", row)
        self.assertIn('<span class="erp-pill">Read-only</span>', row)

    def test_sections_and_rows_keep_the_views_order(self):
        page = self.page()
        html = page.content.decode()
        self.assertLess(html.index('id="results-current"'), html.index('id="results-soon"'))
        self.assertLess(html.index('id="results-soon"'), html.index('id="results-past"'))
        hrefs = re.findall(r'class="erp-results-name stretched-link" href="([^"]+)"', html)
        expected = [reverse("core:my-subject-results", args=[d.pk])
                    for d in list(page.context["duties"]) + list(page.context["past_duties"])]
        self.assertEqual(hrefs, expected)

    def test_status_labels_are_not_links_or_buttons(self):
        page = self.page()
        main = page.content.decode().split("<main", 1)[1].split("</main>", 1)[0]
        self.assertNotIn("<button", main)
        for ident in ("results-current", "results-soon", "results-past"):
            for _, row in self.rows(self.section(page, ident)):
                for pill in re.findall(r'<span class="erp-pill[^"]*">[^<]+</span>', row):
                    before = row[:row.index(pill)]
                    self.assertGreater(before.rfind("</a>"), before.rfind("<a "))

    def test_only_navigable_rows_have_a_link(self):
        page = self.page()
        for ident, links in (("results-current", 1), ("results-soon", 0), ("results-past", 1)):
            for _, row in self.rows(self.section(page, ident)):
                self.assertEqual(row.count("<a "), links)

    def test_no_totals_averages_ranks_or_invented_counts(self):
        html = self.page().content.decode()
        for word in ("Total", "Average", "Rank", "<progress", "%", "published"):
            self.assertNotIn(word, html)
        self.assertNotIn("<table", html)
