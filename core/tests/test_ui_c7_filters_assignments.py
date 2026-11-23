"""Package C7: compact phone filters (C0-05) and Teacher assignments grouped by Class/Grade (C0-04).

The two-column filter grid is CSS only, so these tests pin the opt-in class on each form and that every
rule for it sits in the phone media query. The Teacher assignments phone cards are regrouped in the
template (one collapsible group per Class/Grade under a jump list); the tests pin the groups, the jump
anchors, that every slot appears exactly once, and that card actions keep their permission checks.
The layout itself is checked in a browser at 360, 390, 576 and 1366px.
"""

import re
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AssessmentTeacherAssignment,
    ClassGrade,
    Section,
    Subject,
)

# The module, not its classes: an imported TestCase would run again from here.
from core.tests import test_ui_phone_tables as phone_tables
from core.tests.test_phase5_assignment_workflows import AssignmentFixture
from core.tests.test_ui_admin_desktop_d1_4a_attendance_list import AttendanceListFixture
from core.tests.test_ui_admin_desktop_d1_5b_assessments import AssessmentFixture

HOOK = "erp-toolbar--compact"


def filter_form(page, label):
    return page.split(f'<search aria-label="{label}">')[1].split("</form>")[0]


class AssessmentFilterHookTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()
        self.client.login(username="admin", password="pass-12345")

    def test_assessment_filters_opt_into_the_compact_grid(self):
        page = self.client.get(self.list_url).content.decode()
        form = filter_form(page, "Filter assessments")
        self.assertIn(f'class="erp-toolbar erp-toolbar--inline {HOOK} erp-assessment-toolbar"', form)


class AttendanceFilterHookTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()

    def test_attendance_filters_opt_into_the_compact_grid(self):
        page = self.client.get(self.url).content.decode()
        form = filter_form(page, "Filter attendance registers")
        self.assertIn(f'class="erp-toolbar erp-toolbar--inline {HOOK}"', form)


class CompactFilterCssTests(SimpleTestCase):
    setUp = phone_tables.StackedTableCssTests.setUp
    rules = phone_tables.StackedTableCssTests.rules

    def compact_rules(self):
        return [rule for rule in self.rules() if HOOK in rule[1]]

    def test_compact_rules_only_apply_on_phones(self):
        rules = self.compact_rules()
        self.assertTrue(rules)
        for media, selector, _ in rules:
            self.assertEqual(media, phone_tables.PHONE_QUERY, f"{selector!r} must only apply on phones")

    def test_two_columns_with_full_width_errors_and_buttons(self):
        bodies = {selector.strip(): body for _, selector, body in self.compact_rules()}
        grid = bodies[f".erp-toolbar--inline.{HOOK}"]
        self.assertIn("display: grid", grid)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", grid)
        full = next(b for s, b in bodies.items() if ".erp-form-actions" in s)
        self.assertIn(".erp-form-errors", next(s for s in bodies if ".erp-form-actions" in s))
        self.assertIn("grid-column: 1 / -1", full)


def phone_cards(page):
    """The phone layout: from its wrapper to the end of the page (the table layout comes before it)."""
    return page.split('<div class="erp-assign-grades d-md-none d-print-none">')[1]


class TeacherAssignmentGroupTests(AssignmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.assign(self.iyer, self.maths, self.six_a)
        self.assign(self.rao, self.sanskrit, self.six_b)
        # A second Class/Grade listed before Grade 6.
        ClassGrade.objects.filter(pk=self.grade6.pk).update(display_order=2)
        self.grade5 = ClassGrade.objects.create(name="Grade 5", display_order=1)
        five_a = Section.objects.create(class_grade=self.grade5, name="A")
        science = AcademicSubjectOffering.objects.create(
            academic_year=self.year, class_grade=self.grade5, subject=Subject.objects.create(name="Science")
        )
        self.science = AssessmentTeacherAssignment.objects.create(
            teacher=self.rao, offering=science, section=five_a, start_date=self.year.start_date
        )
        self.url = reverse("core:academic-year-teacher-assignments", args=[self.year.pk])

    def page(self, client=None):
        return (client or self.client).get(self.url)

    def test_cards_are_grouped_by_grade_in_display_order(self):
        cards = phone_cards(self.page().content.decode())
        groups = re.findall(r'<details class="erp-assign-grade"( open)?>\s*<summary>(.*?)</summary>', cards, re.S)
        self.assertEqual([phone_tables.text(summary) for _, summary in groups],
                         ["Grade 5 1 subject slot", "Grade 6 2 subject slots"])
        # The first group starts open, the rest collapsed.
        self.assertEqual([bool(is_open) for is_open, _ in groups], [True, False])

    def test_jump_list_links_to_the_card_list_inside_each_group(self):
        # Targeting content inside a collapsed details element makes the browser open it on the jump.
        cards = phone_cards(self.page().content.decode())
        nav = re.search(r'<nav class="erp-section-nav" aria-label="Jump to a Class/Grade">(.*?)</nav>', cards, re.S)
        self.assertIsNotNone(nav)
        links = re.findall(r'<a href="#([^"]+)">([^<]+)</a>', nav.group(1))
        ids = re.findall(r'<details class="erp-assign-grade"(?: open)?>\s*<summary>.*?</summary>\s*'
                         r'<ul class="erp-assign-cards" id="([^"]+)" role="list">', cards, re.S)
        self.assertEqual([target for target, _ in links], ids)
        self.assertEqual([label for _, label in links], ["Grade 5", "Grade 6"])
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(ids, [f"assign-grade-{self.grade5.pk}", f"assign-grade-{self.grade6.pk}"])

    def test_every_slot_appears_once_in_its_grade_group(self):
        response = self.page()
        cards = phone_cards(response.content.decode())
        slots = response.context["slots"]
        self.assertEqual(cards.count('<li class="erp-assign-card'), len(slots))
        groups = re.split(r'<details class="erp-assign-grade"', cards)[1:]
        for slot in slots:
            title = f"{slot['offering'].class_grade} {slot['section'].name} &middot; {slot['offering'].subject}"
            holders = [g for g in groups if title in g]
            self.assertEqual(len(holders), 1, title)
            self.assertIn(f'id="assign-grade-{slot["offering"].class_grade.pk}"', holders[0])
            self.assertEqual(cards.count(title), 1, title)

    def test_admin_cards_keep_their_actions(self):
        cards = phone_cards(self.page().content.decode())
        self.assertEqual(cards.count(">Reassign<"), 3)
        self.assertIn(reverse("core:teacher-assignment-end", args=[self.science.pk]), cards)

    def test_view_only_user_gets_no_card_actions(self):
        client = phone_tables.limited_client(self, "viewer", "view_assessmentteacherassignment")
        response = self.page(client)
        self.assertEqual(response.status_code, 200)
        cards = phone_cards(response.content.decode())
        self.assertEqual(cards.count('<li class="erp-assign-card'), 3)
        self.assertNotIn("Reassign", cards)
        self.assertNotIn("/end/", cards)
        self.assertNotIn("Delete planned", cards)
        self.assertNotIn("erp-assign-card-actions", cards)

    def test_end_needs_change_permission_and_delete_needs_delete_permission(self):
        planned = AssessmentTeacherAssignment.objects.create(
            teacher=self.iyer, offering=self.maths, section=self.six_b, start_date=date(2027, 1, 1)
        )
        delete_url = reverse("core:teacher-assignment-delete", args=[planned.pk])
        client = phone_tables.limited_client(self, "changer", "view_assessmentteacherassignment",
                                "change_assessmentteacherassignment")
        cards = phone_cards(self.page(client).content.decode())
        self.assertIn(reverse("core:teacher-assignment-end", args=[self.science.pk]), cards)
        self.assertNotIn(delete_url, cards)
        self.assertNotIn("Reassign", cards)
        self.assertIn(delete_url, phone_cards(self.page().content.decode()))


class OneGradeAssignmentTests(AssignmentFixture, TestCase):
    def test_one_grade_gets_no_jump_list(self):
        self.assign(self.iyer, self.maths, self.six_a)
        page = self.client.get(reverse("core:academic-year-teacher-assignments", args=[self.year.pk]))
        cards = phone_cards(page.content.decode())
        self.assertNotIn("erp-section-nav", cards)
        self.assertEqual(cards.count('<details class="erp-assign-grade"'), 1)


class AssignmentGroupCssTests(SimpleTestCase):
    setUp = phone_tables.StackedTableCssTests.setUp
    rules = phone_tables.StackedTableCssTests.rules

    def test_jump_keeps_the_group_summary_in_view(self):
        (body,) = [b for _, s, b in self.rules() if s.strip() == ".erp-assign-grade > .erp-assign-cards"]
        self.assertIn("scroll-margin-top: 3rem", body)
