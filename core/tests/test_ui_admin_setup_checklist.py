"""'Set up your school' checklist on the admin Overview page.

Covers the eight steps, their fix/assign links, the reuse of the Assignment
overview gap counts, and the hide-when-complete / reappear-on-break behaviour.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, School, Section, SectionClassTeacher, Student
from core.setup_checklist import foundation_incomplete, setup_complete, setup_steps
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin


def by_key(steps):
    return {step["key"]: step for step in steps}


def client_page_orders_cards_first(client):
    """True when the Overview prints the attention block (cards or the all-clear line) before the checklist."""
    content = client.get(reverse("core:admin-overview")).content.decode()
    top = min(i for i in (content.find('id="attention-title"'), content.find("erp-all-clear")) if i >= 0)
    return top < content.index("erp-setup-title")


class SetupStepsStructureTests(AuthorizationClientsMixin, TestCase):
    def test_eight_steps_in_order(self):
        self.assertEqual(
            [step["key"] for step in setup_steps()],
            [
                "school", "academic-year", "classes", "subjects", "teachers",
                "class-teachers", "subject-teachers", "students-placed",
            ],
        )

    def test_brand_new_school_flags_the_first_five_steps(self):
        steps = by_key(setup_steps())
        for key in ("school", "academic-year", "classes", "subjects", "teachers"):
            with self.subTest(key=key):
                self.assertFalse(steps[key]["done"])
                self.assertEqual(steps[key]["count"], 1)
        # With nothing created there are no gaps and no students to place, so
        # the three tail steps are vacuously complete until their inputs exist.
        for key in ("class-teachers", "subject-teachers", "students-placed"):
            with self.subTest(key=key):
                self.assertTrue(steps[key]["done"])
                self.assertEqual(steps[key]["count"], 0)

    def test_fix_links_point_at_the_right_pages(self):
        steps = by_key(setup_steps())
        self.assertEqual(steps["school"]["url"], reverse("core:school-create"))
        self.assertEqual(steps["academic-year"]["url"], reverse("core:academic-year-list"))
        self.assertEqual(steps["classes"]["url"], reverse("core:class-grade-list"))
        self.assertEqual(steps["subjects"]["url"], reverse("core:subject-list"))
        self.assertEqual(steps["teachers"]["url"], reverse("core:teacher-list"))
        self.assertEqual(steps["students-placed"]["url"], reverse("core:student-list"))
        # Without an Academic Year the two assignment buttons fall back to the
        # year list, where the year is created first.
        self.assertEqual(steps["class-teachers"]["url"], reverse("core:academic-year-list"))
        self.assertEqual(steps["subject-teachers"]["url"], reverse("core:academic-year-list"))

    def test_setup_complete_is_false_until_all_done(self):
        self.assertFalse(setup_complete(setup_steps()))


class SetupStepsGapTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def test_gap_counts_reuse_the_assignment_overview(self):
        # Class teacher for 6A only; 6B stays empty (one class gap).
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        # Subject teacher for every subject/section slot (no subject gaps).
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)

        steps = by_key(setup_steps(today=date(2026, 7, 1)))

        self.assertEqual(steps["class-teachers"]["count"], 1)
        self.assertFalse(steps["class-teachers"]["done"])
        self.assertEqual(
            steps["class-teachers"]["url"],
            reverse("core:academic-year-class-teachers", args=[self.year.pk]),
        )
        self.assertEqual(steps["subject-teachers"]["count"], 0)
        self.assertTrue(steps["subject-teachers"]["done"])

    def test_unplaced_students_are_counted(self):
        self.make_student("Placed Pupil", section=self.six_a)
        # A second student with no enrollment (placement) is the gap.
        Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Lost"),
            full_name="Lost",
        )

        steps = by_key(setup_steps(today=date(2026, 7, 1)))
        self.assertEqual(steps["students-placed"]["count"], 1)
        self.assertFalse(steps["students-placed"]["done"])


class SetupChecklistRenderingTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")
        self.client.login(username="admin", password="pass-12345")

    def complete_setup(self):
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 6, 1),
        )
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)

    def test_foundation_is_complete_with_open_gap_steps_so_cards_lead(self):
        steps = setup_steps()
        self.assertFalse(foundation_incomplete(steps))
        self.assertTrue(client_page_orders_cards_first(self.client))

    def test_foundation_incomplete_when_a_has_at_least_one_step_is_missing(self):
        School.objects.all().delete()
        self.assertTrue(foundation_incomplete(setup_steps()))

    def test_checklist_hides_when_every_step_is_done(self):
        self.complete_setup()
        response = self.client.get(reverse("core:admin-overview"))
        self.assertNotContains(response, "Set up your school")

    def test_checklist_reappears_when_a_gap_opens(self):
        self.complete_setup()
        Section.objects.create(class_grade=self.grade6, name="C")
        response = self.client.get(reverse("core:admin-overview"))
        self.assertContains(response, "Set up your school")
        self.assertContains(response, "A class teacher for every section")

    def test_problem_step_shows_count_and_assign_link(self):
        # No class teacher is assigned, so 6A and 6B are both gaps.
        response = self.client.get(reverse("core:admin-overview"))
        self.assertContains(response, "Set up your school")
        self.assertContains(response, "A class teacher for every section")
        self.assertContains(
            response,
            reverse("core:academic-year-class-teachers", args=[self.year.pk]),
        )
        self.assertContains(response, "Assign")

    def test_checklist_collapses_to_a_single_line_when_done(self):
        self.complete_setup()
        response = self.client.get(reverse("core:admin-overview"))
        self.assertContains(response, "School setup complete")
        self.assertNotContains(response, "Set up your school")
        self.assertNotContains(response, 'class="erp-setup-list"')
        self.assertNotContains(response, 'class="progress erp-setup-bar"')

    def test_progress_bar_and_only_the_next_step_gets_a_filled_button(self):
        response = self.client.get(reverse("core:admin-overview"))
        self.assertContains(response, 'class="progress erp-setup-bar"')
        self.assertContains(response, "of 8 done")
        # The first incomplete step is the class-teacher step; only it is filled.
        class_url = reverse("core:academic-year-class-teachers", args=[self.year.pk])
        self.assertContains(
            response,
            f'class="btn btn-primary btn-sm erp-setup-action" href="{class_url}"',
        )
        # The following incomplete step (subject teachers) stays outline only.
        subject_url = reverse("core:academic-year-teacher-assignments", args=[self.year.pk])
        self.assertContains(
            response,
            f'class="btn btn-outline-secondary btn-sm erp-setup-action" href="{subject_url}"',
        )
        self.assertContains(response, "A subject teacher for every subject")


class SetupChecklistAdminOnlyTests(AuthorizationClientsMixin, TestCase):
    def test_overview_still_refuses_non_administrators(self):
        response = self.non_admin.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 403)
