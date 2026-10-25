"""Phase 4 Gate 8: Term remarks and result-UI polish (ADR 0009)."""

from datetime import date
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.authorization import can_write_term_remarks
from core.models import Assessment, SectionClassTeacher, TermRemark
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class TermPlacementTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")

    def test_placement_is_the_section_on_the_last_day(self):
        self.ravi.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_b,
            start_date=date(2026, 8, 1),
        )
        self.assertEqual(self.term1.enrollment_for(self.ravi).section, self.six_b)
        self.assertEqual(self.term1.section_roster(self.six_a), [self.meera])
        self.assertEqual(self.term1.section_roster(self.six_b), [self.ravi])

    def test_student_who_joined_after_the_term_is_not_placed(self):
        late, _ = self.make_student("Dev Nair", start=date(2026, 10, 5))
        self.assertIsNone(self.term1.enrollment_for(late))
        self.assertNotIn(late, self.term1.section_roster(self.six_a))
        self.assertIn(late, self.term2.section_roster(self.six_a))


@mock.patch("core.models.business_today", new=lambda: TODAY)
class TermRemarkTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.ravi, _ = self.make_student("Ravi Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.iyer, self.maths, self.six_b)
        # Phase 5 (ADR 0012 D10): remarks belong to the class teacher.
        for teacher, section in ((self.rao, self.six_a), (self.iyer, self.six_b)):
            SectionClassTeacher.assign(teacher=teacher, academic_year=self.year,
                                       section=section, start_date=date(2026, 6, 1))
        self.url = reverse("core:term-remarks", args=[self.term1.pk])
        self.client.login(username="admin", password="pass-12345")
        self.rao_client = self.client_class()
        self.rao_client.login(username="rao", password="pass-12345")
        self.iyer_client = self.client_class()
        self.iyer_client.login(username="iyer", password="pass-12345")

    def test_who_may_write(self):
        self.assertTrue(can_write_term_remarks(self.admin, self.term1, self.six_a))
        self.assertTrue(can_write_term_remarks(self.rao, self.term1, self.six_a))
        self.assertFalse(can_write_term_remarks(self.iyer, self.term1, self.six_a))
        self.assertFalse(can_write_term_remarks(self.make_user("clerk"), self.term1, self.six_a))

    def test_assigned_teacher_writes_edits_and_clears(self):
        data = {"section": self.six_a.pk, f"remark_{self.ravi.pk}": "Strong progress."}
        response = self.rao_client.post(self.url, data)
        self.assertRedirects(response, f"{self.url}?section={self.six_a.pk}")
        remark = TermRemark.objects.get()
        self.assertEqual((remark.remark, remark.written_by), ("Strong progress.", self.rao))
        self.client.post(self.url, {**data, f"remark_{self.ravi.pk}": "Excellent term."})
        remark.refresh_from_db()
        self.assertEqual((remark.remark, remark.written_by), ("Excellent term.", self.admin))
        self.rao_client.post(self.url, {**data, f"remark_{self.ravi.pk}": "  "})
        self.assertFalse(TermRemark.objects.exists())

    def test_other_section_teacher_is_refused(self):
        response = self.iyer_client.post(
            self.url, {"section": self.six_a.pk, f"remark_{self.ravi.pk}": "x"}
        )
        self.assertEqual(response.status_code, 404)  # not one of Iyer's Sections
        self.assertFalse(TermRemark.objects.exists())

    def test_plain_user_is_refused(self):
        self.make_user("clerk")
        clerk = self.client_class()
        clerk.login(username="clerk", password="pass-12345")
        self.assertEqual(clerk.get(self.url).status_code, 403)

    def test_teacher_only_sees_own_sections(self):
        page = self.rao_client.get(self.url)
        self.assertEqual(list(page.context["sections"]), [self.six_a])
        admin_page = self.client.get(self.url)
        self.assertEqual(set(admin_page.context["sections"]), {self.six_a, self.six_b})

    def test_page_lists_term_roster(self):
        page = self.rao_client.get(self.url, {"section": self.six_a.pk})
        self.assertContains(page, "Ravi Rao")
        self.assertContains(page, "never affect marks")

    def test_roster_table_is_a_labelled_panel_region_inside_the_form(self):
        html = self.rao_client.get(self.url, {"section": self.six_a.pk}).content.decode()
        self.assertRegex(
            html,
            r'(?s)<form method="post">.*?<div class="erp-panel mb-4">\s*<div class="erp-table-scroll" '
            r'role="region" aria-label="Term remarks" tabindex="0">\s*'
            r'<table class="table align-middle">.*?</table>\s*</div>\s*</div>.*?</form>',
        )
        # erp-keep must be absent so the table scrolls on phones instead of squeezing.
        self.assertNotIn("erp-keep", html)

    def test_one_non_blank_remark_per_student_per_term(self):
        TermRemark.objects.create(
            term=self.term1, student=self.ravi, remark="a", written_by=self.admin
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            TermRemark.objects.create(
                term=self.term1, student=self.ravi, remark="b", written_by=self.admin
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            TermRemark.objects.create(
                term=self.term2, student=self.ravi, remark="", written_by=self.admin
            )

    def test_my_assessments_links_to_remarks(self):
        page = self.rao_client.get(reverse("core:my-assessments"))
        self.assertContains(page, f"{self.url}?section={self.six_a.pk}")


@mock.patch("core.models.business_today", new=lambda: TODAY)
class AssessmentListStatusFilterTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")

    def test_status_filter(self):
        draft = self.make_assessment()
        finalized = self.make_assessment(name="Done")
        self.force_finalize(finalized)
        url = reverse("core:academic-year-assessments", args=[self.year.pk])
        self.assertEqual(
            list(self.client.get(url, {"status": Assessment.Status.DRAFT}).context["assessments"]),
            [draft],
        )
        self.assertEqual(
            list(
                self.client.get(url, {"status": Assessment.Status.FINALIZED}).context[
                    "assessments"
                ]
            ),
            [finalized],
        )


class NavigationTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_teacher_menu_shows_only_teacher_pages(self):
        self.client.login(username="rao", password="pass-12345")
        page = self.client.get(reverse("core:my-assessments"))
        self.assertContains(page, reverse("core:my-assessments"))
        for name in ("core:student-list", "core:attendance-register-list", "core:subject-list"):
            self.assertNotContains(page, f'href="{reverse(name)}"')

    def test_administrator_menu_shows_admin_pages(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:subject-list"))
        for name in ("core:student-list", "core:attendance-register-list", "core:subject-list"):
            self.assertContains(page, f'href="{reverse(name)}"')
        self.assertNotContains(page, reverse("core:my-assessments"))
