"""Phase 4 Gate 9: result reports and Term report cards (ADR 0009)."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import assessment_reports
from core.models import ResultStatus, TermRemark
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 10)


class ReportFixture(Phase4Fixture):
    """Builds finalized history. All dates are before TODAY, so setUp (which
    class-level patches do not cover) behaves the same on any later date."""
    def build_reports(self):
        self.build_phase4()
        self.scale = self.make_scale()  # A>=90, B>=75, C>=50, D>=0
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.assign(self.rao, self.maths, self.six_b)
        self.ut1 = self.make_assessment(name="Unit Test 1", on=date(2026, 7, 15), pass_mark="8")
        self.enter(self.ut1, {self.ravi_a: "17", self.meera_a: None})
        self.ut1.finalize(actor=self.admin)
        # Ravi moves to 6B on 1 Aug; later assessments place him there.
        self.ravi_b = self.ravi.enroll(
            academic_year=self.year, class_grade=self.grade6, section=self.six_b,
            start_date=date(2026, 8, 1),
        )
        self.ravi_a.refresh_from_db()
        self.ut2_b = self.make_assessment(name="Unit Test 2", section=self.six_b,
                                          on=date(2026, 8, 20))
        self.enter(self.ut2_b, {self.ravi_b: "19"})
        self.ut2_b.finalize(actor=self.admin)
        self.draft = self.make_assessment(name="Unit Test 3", on=date(2026, 9, 10))
        self.enter(self.draft, {self.meera_a: "5"})  # DRAFT: never reported

    def enter(self, assessment, marks):
        for enrollment, score in marks.items():
            assessment.save_draft_result(
                enrollment=enrollment,
                status=ResultStatus.MARKED if score is not None else ResultStatus.ABSENT,
                score=score,
                actor=self.rao,
            )


@mock.patch("core.models.business_today", new=lambda: TODAY)
class ReportSemanticsTests(ReportFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def test_result_sheet_only_for_finalized(self):
        sheet = assessment_reports.result_sheet(self.ut1)
        self.assertEqual([r.student for r in sheet], [self.meera, self.ravi])
        self.assertIsNone(assessment_reports.result_sheet(self.draft))

    def test_student_history_keeps_historical_section(self):
        history = assessment_reports.student_history(self.ravi)
        self.assertEqual(
            [(r.assessment.name, r.academic_enrollment.section) for r in history],
            [("Unit Test 1", self.six_a), ("Unit Test 2", self.six_b)],
        )
        self.assertEqual([r.grade for r in history], ["B", "A"])

    def test_draft_results_never_appear(self):
        self.assertEqual(
            [r.assessment for r in assessment_reports.student_history(self.meera)], [self.ut1]
        )

    def test_absent_is_absent_not_zero_or_fail(self):
        meera = assessment_reports.result_sheet(self.ut1)[0]
        self.assertEqual((meera.status, meera.score, meera.percentage, meera.grade),
                         (ResultStatus.ABSENT, None, None, None))
        self.assertEqual(meera.pass_fail, "ABSENT")

    def test_corrections_flow_into_every_report(self):
        result = self.ut1.results.get(academic_enrollment=self.ravi_a)
        result.correct(new_status=ResultStatus.MARKED, new_score="19", actor=self.admin,
                       reason="Re-totalled.")
        self.assertEqual(assessment_reports.result_sheet(self.ut1)[1].score, Decimal("19"))
        card = assessment_reports.term_report_card(self.ravi, self.term1)
        group = assessment_reports.SubjectGroup(self.maths_subject, "Mathematics")
        self.assertEqual(card["subjects"][group][0].grade, "A")

    def test_grading_scale_edit_does_not_change_finalized_reports(self):
        self.scale.boundaries.filter(label="A").update(min_percentage=99)
        history = assessment_reports.student_history(self.ravi)
        self.assertEqual([r.grade for r in history], ["B", "A"])

    def test_subject_section_results_grid(self):
        assessments, rows = assessment_reports.subject_section_results(self.maths, self.six_a)
        self.assertEqual(assessments, [self.ut1])
        self.assertEqual([student for student, _ in rows], [self.meera, self.ravi])
        _, rows_b = assessment_reports.subject_section_results(self.maths, self.six_b)
        self.assertEqual([(s, [c.score for c in cells]) for s, cells in rows_b],
                         [(self.ravi, [Decimal("19")])])
        none, _ = assessment_reports.subject_section_results(self.maths, self.six_a, self.term2)
        self.assertEqual(none, [])

    def test_term_report_card(self):
        TermRemark.objects.create(term=self.term1, student=self.ravi,
                                  remark="Steady improvement.", written_by=self.rao)
        card = assessment_reports.term_report_card(self.ravi, self.term1)
        self.assertEqual(card["placement"], self.ravi_b)  # Section at term end
        group = assessment_reports.SubjectGroup(self.maths_subject, "Mathematics")
        self.assertEqual(
            [r.assessment.name for r in card["subjects"][group]],
            ["Unit Test 1", "Unit Test 2"],
        )
        self.assertEqual(card["remark"].remark, "Steady improvement.")
        empty = assessment_reports.term_report_card(self.ravi, self.term2)
        self.assertEqual((dict(empty["subjects"]), empty["remark"]), ({}, None))


@mock.patch("core.models.business_today", new=lambda: TODAY)
class ReportViewTests(ReportFixture, TestCase):
    def setUp(self):
        self.build_reports()
        self.client.login(username="admin", password="pass-12345")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.urls = {
            "sheet": reverse("core:report-result-sheet", args=[self.ut1.pk]),
            "history": reverse("core:report-student-results", args=[self.ravi.pk]),
            "card": reverse("core:report-term-report-card", args=[self.ravi.pk, self.term1.pk]),
            "grid": reverse("core:report-subject-section-results", args=[self.year.pk]),
        }

    def test_result_sheet_page(self):
        page = self.client.get(self.urls["sheet"])
        self.assertContains(page, "85.00%")
        self.assertContains(page, "Absent")
        self.assertContains(page, "graded with Standard")
        draft = self.client.get(reverse("core:report-result-sheet", args=[self.draft.pk]))
        self.assertContains(draft, "not finalized yet")

    def test_history_and_report_card_pages(self):
        history = self.client.get(self.urls["history"])
        self.assertContains(history, "Grade 6 - A")
        self.assertContains(history, "Grade 6 - B")
        self.assertContains(history, self.urls["card"])
        TermRemark.objects.create(term=self.term1, student=self.ravi,
                                  remark="Keep it up.", written_by=self.rao)
        card = self.client.get(self.urls["card"])
        self.assertContains(card, "Mathematics")
        self.assertContains(card, "Keep it up.")
        self.assertContains(card, "no weighting, totals or rank")

    def test_subject_section_grid_page(self):
        page = self.client.get(
            self.urls["grid"], {"offering": self.maths.pk, "section": self.six_a.pk}
        )
        self.assertContains(page, "Unit Test 1")
        self.assertNotContains(page, "Unit Test 3")
        bad = self.client.get(self.urls["grid"], {"offering": "999", "section": "x"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.context["rows"], [])

    def test_reports_are_administrator_only(self):
        for name, url in self.urls.items():
            with self.subTest(report=name):
                self.assertEqual(self.teacher.get(url).status_code, 403)

    def test_links_from_assessment_student_and_list_pages(self):
        self.assertContains(
            self.client.get(reverse("core:assessment-detail", args=[self.ut1.pk])),
            self.urls["sheet"],
        )
        self.assertContains(
            self.client.get(reverse("core:student-detail", args=[self.ravi.pk])),
            self.urls["history"],
        )
        self.assertContains(
            self.client.get(reverse("core:academic-year-assessments", args=[self.year.pk])),
            self.urls["grid"],
        )

    def test_reports_do_not_issue_a_query_per_row(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count(url, params=None):
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url, params or {})
            return len(ctx.captured_queries)

        before = [count(self.urls["sheet"]), count(self.urls["history"])]
        for i in range(4):
            _, extra = self.make_student(f"Extra {i}")
        more = self.make_assessment(name="Big test", on=date(2026, 9, 1))
        self.enter(more, {e: "10" for e in more.roster()})
        more.finalize(actor=self.admin)
        after = [count(reverse("core:report-result-sheet", args=[more.pk])),
                 count(self.urls["history"])]
        self.assertEqual(before, after)
