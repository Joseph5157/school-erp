"""UI-D1-5C: assessment result sheet, Student results, Subject/Section matrix and the shared Term report card.

Presentation only. These tests pin page structure, the Absent / Not graded / no-result distinctions,
that no totals, averages or ranks appear, the matrix's scroll region and sticky Student column, the
existing GET parameters and invalid-selection message, the single shared report-card template in
both the administrator and teacher shells (administrator-only, teacher-only and dual-role users),
permission-gated links and the permission-aware breadcrumbs. Marks, grading and pass/fail are
covered by test_phase4_* and are not retested here.
"""

import re
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core.breadcrumbs import breadcrumb_context
from core.models import ResultStatus, SectionClassTeacher, Subject, TermRemark
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()

TODAY = date(2026, 10, 10)
M, A = ResultStatus.MARKED, ResultStatus.ABSENT


def html(response):
    return response.content.decode()


class ReportFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.asha, self.asha_a = self.make_student("Asha Rao")
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.make_scale()
        self.ut1 = self.finalized("UT1", [(self.asha_a, M, "18"), (self.ravi_a, A, None), (self.meera_a, M, "5")])
        # A later joiner has no result in UT1 (not on that day's roster): the matrix shows a dash for them.
        self.dev, self.dev_a = self.make_student("Dev Rao", start=date(2026, 8, 1))
        self.ut2 = self.finalized(
            "UT2", [(self.asha_a, M, "9"), (self.ravi_a, M, "11"), (self.meera_a, A, None), (self.dev_a, M, "16")],
            on=date(2026, 10, 6), term=self.term2,
        )
        self.draft = self.make_assessment(name="Unfinished", on=date(2026, 7, 29))
        self.sheet_url = reverse("core:report-result-sheet", args=[self.ut1.pk])
        self.student_url = reverse("core:report-student-results", args=[self.asha.pk])
        self.card_url = reverse("core:report-term-report-card", args=[self.asha.pk, self.term1.pk])
        self.matrix_url = reverse("core:report-subject-section-results", args=[self.year.pk])
        self.my_card = reverse("core:my-report-card", args=[self.term1.pk, self.asha.pk])
        self.client.login(username="admin", password="pass-12345")

    def finalized(self, name, rows, on=date(2026, 7, 15), term=None):
        assessment = self.make_assessment(name=name, on=on, term=term or self.term1, maximum="20", pass_mark="8")
        for enrollment, status, score in rows:
            assessment.save_draft_result(enrollment=enrollment, status=status, score=score, actor=self.rao)
        with mock.patch("core.models.business_today", new=lambda: TODAY):
            assessment.finalize(actor=self.admin)
        return assessment

    def class_teacher(self, teacher):
        return SectionClassTeacher.assign(
            teacher=teacher, academic_year=self.year, section=self.six_a, start_date=date(2026, 6, 1)
        )

    def client_with(self, *codenames, groups=()):
        self._users = getattr(self, "_users", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._users}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        user.groups.add(*groups)
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def login(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client


class NoTotalsMixin:
    def assertNoTotals(self, page):
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
        for word in ("Total", "Average", "Rank", "GPA", "Aggregate"):
            self.assertNotRegex(body, rf"<t[hd][^>]*>[^<]*{word}", word)


class ResultSheetTests(ReportFixture, NoTotalsMixin, TestCase):
    def setUp(self):
        self.build()

    def test_header_table_and_semantics(self):
        page = html(self.client.get(self.sheet_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">UT1</h1>', page)
        self.assertRegex(page, r"erp-status--finalized[^>]*><span[^>]*>Status: </span>Finalized")
        self.assertIn('role="region" aria-label="Result sheet for UT1" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', page),
                         ["Student", "Marks", "%", "Grade", "Pass/Fail"])
        rows = dict(re.findall(r'<th scope="row" class="fw-semibold">([^<]+)</th>(.*?)</tr>', page, re.S))
        self.assertIn("18.00 / 20.00", rows["Asha Rao"])
        self.assertNotIn("Not graded", rows["Asha Rao"])
        self.assertIn("Absent", rows["Ravi Rao"])
        self.assertIn("Not graded", rows["Ravi Rao"])        # absent carries no grade
        self.assertNotIn("Fail", rows["Ravi Rao"])            # absent is never a fail
        self.assertNotIn("0.00 / 20.00", rows["Ravi Rao"])    # nor zero
        self.assertIn("Fail", rows["Meera Rao"])
        self.assertIn("audited corrections", page)
        self.assertNoTotals(page)

    def test_draft_assessment_has_no_results_message(self):
        page = html(self.client.get(reverse("core:report-result-sheet", args=[self.draft.pk])))
        self.assertIn("This assessment is not finalized yet, so it has no official results.", page)
        self.assertNotIn("<table", page)

    def test_back_link_is_gated(self):
        back = reverse("core:assessment-detail", args=[self.ut1.pk])
        self.assertIn(f'href="{back}"', html(self.client.get(self.sheet_url)))
        _, viewer = self.client_with("view_studentresult")
        self.assertNotIn(back, html(viewer.get(self.sheet_url)))

    def test_context_is_unchanged(self):
        response = self.client.get(self.sheet_url)
        self.assertEqual(response.context["assessment"], self.ut1)
        self.assertEqual(len(response.context["results"]), 3)


class StudentResultsTests(ReportFixture, NoTotalsMixin, TestCase):
    def setUp(self):
        self.build()

    def test_header_cards_table_and_notes(self):
        page = html(self.client.get(self.student_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Asha Rao</h1>', page)
        self.assertIn(f'href="{self.card_url}"', page)
        self.assertIn('aria-label="Results for Asha Rao"', page)
        self.assertEqual(
            re.findall(r'<th scope="col">([^<]+)</th>', page),
            ["Assessment", "Date", "Term", "Section", "Subject", "Marks", "%", "Grade", "Pass/Fail"],
        )
        self.assertIn("Grade 6 - A", page)
        self.assertIn("UT1", page)
        self.assertIn("UT2", page)
        self.assertNotIn("Unfinished", page)  # drafts never appear
        self.assertIn("Totals, averages and ranks are not shown.", page)
        self.assertNoTotals(page)

    def test_absent_is_not_zero_for_a_student(self):
        page = html(self.client.get(reverse("core:report-student-results", args=[self.ravi.pk])))
        row = re.search(r"UT1.*?</tr>", page, re.S).group(0)
        self.assertIn("Absent", row)
        self.assertNotIn("0.00 / 20.00", row)

    def test_empty_state(self):
        newcomer, _ = self.make_student("Nia Rao")
        page = html(self.client.get(reverse("core:report-student-results", args=[newcomer.pk])))
        self.assertIn("No finalized results yet.", page)

    def test_back_to_student_is_gated_by_view_student(self):
        back = reverse("core:student-detail", args=[self.asha.pk])
        self.assertIn(f'href="{back}"', html(self.client.get(self.student_url)))
        _, viewer = self.client_with("view_studentresult")
        self.assertNotIn(f'href="{back}"', html(viewer.get(self.student_url)))

    def test_context_is_unchanged(self):
        response = self.client.get(self.student_url)
        for key in ("student", "results", "terms"):
            self.assertIn(key, response.context)


class MatrixTests(ReportFixture, NoTotalsMixin, TestCase):
    def setUp(self):
        self.build()
        self.full = {"offering": self.maths.pk, "section": self.six_a.pk}

    def test_first_load_shows_guidance_and_no_table(self):
        page = html(self.client.get(self.matrix_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn("Choose a Subject and a Section", page)
        self.assertNotIn("<table", page)
        self.assertIn('aria-label="Choose a Subject, Section and Term"', page)
        for name in ("offering", "section", "term"):
            self.assertIn(f'<label for="id_{name}">', page)
            self.assertIn(f'name="{name}" id="id_{name}"', page)
        self.assertNotIn("aria-invalid", page)  # these selects have no form: no invented errors

    def test_matrix_structure_scroll_region_and_sticky_column_hooks(self):
        page = html(self.client.get(self.matrix_url, self.full))
        self.assertIn('role="region" aria-label="Results for Mathematics, Grade 6 - A" tabindex="0"', page)
        self.assertIn('<table class="table erp-results-matrix">', page)
        self.assertIn("<caption", page)
        self.assertEqual(len(re.findall(r'<th scope="col">', page)), 3)  # Student + UT1 + UT2
        self.assertIn(reverse("core:report-result-sheet", args=[self.ut1.pk]), page)
        rows = dict(re.findall(r'<th scope="row" class="fw-semibold"><a [^>]*>([^<]+)</a></th>(.*?)</tr>', page, re.S))
        self.assertIn("18.00 (A)", rows["Asha Rao"])
        self.assertIn("Absent", rows["Ravi Rao"])
        self.assertIn("&mdash;", rows["Dev Rao"])           # no UT1 result: a dash, never Absent or zero
        self.assertNotIn("Absent", rows["Dev Rao"])
        self.assertIn("never counted as zero", page)
        self.assertIn("it is not Absent and not zero", page)
        self.assertNoTotals(page)

    def test_get_parameters_are_preserved_in_the_form(self):
        page = html(self.client.get(self.matrix_url, {**self.full, "term": self.term2.pk}))
        self.assertRegex(page, rf'<option value="{self.maths.pk}" selected>')
        self.assertRegex(page, rf'<option value="{self.six_a.pk}" selected>')
        self.assertRegex(page, rf'<option value="{self.term2.pk}" selected>')
        self.assertIn(">UT2<", page)
        self.assertNotIn(">UT1<", page)

    def test_invalid_selection_shows_the_existing_message_and_nothing_else(self):
        response = self.client.get(self.matrix_url, {"offering": "999999", "section": "abc"})
        page = html(response)
        self.assertIn("Choose a Subject, Section and Term from the lists.", page)
        self.assertNotIn("<table", page)
        self.assertIn("Choose a Subject and a Section", page)
        self.assertNotIn("aria-invalid", page)
        self.assertNotIn("form-error-summary", page)
        self.assertIsNone(response.context["offering"])

    def test_many_assessments_make_a_wide_matrix(self):
        for index in range(8):
            self.finalized(f"Weekly {index}", [(self.asha_a, M, "10"), (self.ravi_a, M, "10"),
                                               (self.meera_a, M, "10"), (self.dev_a, M, "10")],
                           on=date(2026, 8, 3 + index), term=self.term1)
        page = html(self.client.get(self.matrix_url, self.full))
        self.assertEqual(len(re.findall(r'<th scope="col">', page)), 1 + 2 + 8)

    def test_empty_matrix_row(self):
        page = html(self.client.get(self.matrix_url, {"offering": self.maths.pk, "section": self.six_b.pk}))
        self.assertIn("No finalized results for this Subject and Section.", page)
        self.assertIn('<td colspan="1">', page)

    def test_assessments_link_is_gated(self):
        link = reverse("core:academic-year-assessments", args=[self.year.pk])
        self.assertIn(f'href="{link}"', html(self.client.get(self.matrix_url)))
        _, viewer = self.client_with("view_studentresult")
        self.assertNotIn(link, html(viewer.get(self.matrix_url)))

    def test_context_is_unchanged(self):
        response = self.client.get(self.matrix_url, self.full)
        for key in ("academic_year", "offerings", "sections", "terms", "offering", "section", "term",
                    "assessments", "rows"):
            self.assertIn(key, response.context)
        self.assertEqual(len(response.context["assessments"]), 2)


class ReportCardTests(ReportFixture, NoTotalsMixin, TestCase):
    def setUp(self):
        self.build()
        TermRemark.objects.create(term=self.term1, student=self.asha, remark="Steady progress.", written_by=self.rao)
        self.results_link = reverse("core:report-student-results", args=[self.asha.pk])
        self.my_students = reverse("core:my-students")

    def test_administrator_rendering(self):
        page = html(self.client.get(self.card_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Asha Rao</h1>', page)
        self.assertIn("Term report card", page)
        self.assertIn("2026-27 Term 1", page)
        self.assertIn("Section: Grade 6 - A.", page)
        self.assertIn("(no weighting, totals or rank)", page)
        self.assertIn("Steady progress.", page)
        self.assertIn(f'href="{self.results_link}"', page)  # All results (admin has view_studentresult)
        self.assertNotIn(self.my_students, page)
        self.assertIn('aria-label="Mathematics results"', page)
        self.assertIn("UT1", page)
        self.assertNotIn("UT2", page)                        # other Term
        self.assertNoTotals(page)
        self.assertIn('aria-label="Breadcrumb"', page)

    def test_teacher_only_rendering(self):
        self.class_teacher(self.rao)
        teacher = self.login("rao")
        page = html(teacher.get(self.my_card))
        self.assertIn("Class report card", page)
        self.assertNotIn("Term report card", page)
        self.assertIn(f'href="{self.my_students}"', page)
        self.assertNotIn(self.results_link, page)            # no view_studentresult: no link
        self.assertIn("UT1", page)
        self.assertNotIn("UT2", page)
        self.assertIn("Steady progress.", page)
        self.assertNotIn('aria-label="Breadcrumb"', page)    # teacher shell has no admin trail
        self.assertEqual(teacher.get(self.card_url).status_code, 403)  # and no administrator access

    def test_dual_role_user_gets_chrome_by_area_and_links_by_permission(self):
        dual_user = self.make_user("dual", self.admins, self.teachers)
        self.class_teacher(dual_user)
        dual = self.login("dual")
        teacher_view = html(dual.get(self.my_card))
        self.assertIn("Class report card", teacher_view)
        self.assertIn(f'href="{self.my_students}"', teacher_view)
        self.assertIn(f'href="{self.results_link}"', teacher_view)  # permission, not area, shows it
        self.assertNotIn('aria-label="Breadcrumb"', teacher_view)
        admin_view = html(dual.get(self.card_url))
        self.assertIn("Term report card", admin_view)
        self.assertNotIn(self.my_students, admin_view)
        self.assertIn(f'href="{self.results_link}"', admin_view)
        self.assertIn('aria-label="Breadcrumb"', admin_view)

    def test_administrator_without_teacher_role_cannot_use_the_teacher_route(self):
        self.assertEqual(self.client.get(self.my_card).status_code, 403)

    def test_all_results_link_needs_view_studentresult(self):
        _, viewer = self.client_with("view_studentresult")
        self.assertIn(f'href="{self.results_link}"', html(viewer.get(self.card_url)))

    def test_no_results_and_no_remark_states(self):
        newcomer, _ = self.make_student("Nia Rao")
        page = html(self.client.get(reverse("core:report-term-report-card", args=[newcomer.pk, self.term1.pk])))
        self.assertIn("No finalized results for this Term yet.", page)
        self.assertIn("No remark.", page)

    def test_historical_subject_label_is_kept(self):
        Subject.objects.filter(pk=self.maths_subject.pk).update(name="Maths (renamed)")
        page = html(self.client.get(self.card_url))
        self.assertIn('aria-label="Mathematics results"', page)
        self.assertNotIn("Maths (renamed)", page)

    def test_same_template_serves_both_routes(self):
        self.class_teacher(self.rao)
        teacher = self.login("rao")
        for response in (self.client.get(self.card_url), teacher.get(self.my_card)):
            self.assertIn("core/report_term_report_card.html", [t.name for t in response.templates])


class SharedCellsTests(ReportFixture, TestCase):
    def setUp(self):
        self.build()

    def test_teacher_student_detail_still_renders_the_shared_cells(self):
        self.class_teacher(self.rao)
        teacher = self.login("rao")
        response = teacher.get(reverse("core:my-student-detail", args=[self.ravi.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("core/_result_cells.html", [t.name for t in response.templates])
        self.assertContains(response, "Absent")


class AccessTests(ReportFixture, TestCase):
    def setUp(self):
        self.build()

    def test_routes_keep_their_permission_outcomes(self):
        urls = [self.sheet_url, self.student_url, self.card_url, self.matrix_url]
        anonymous = self.client_class()
        teacher = self.login("rao")
        _, no_perm = self.client_with("view_assessment")
        _, viewer = self.client_with("view_studentresult")
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
            self.assertEqual(anonymous.get(url).status_code, 302, url)
            self.assertEqual(teacher.get(url).status_code, 403, url)
            self.assertEqual(no_perm.get(url).status_code, 403, url)
            self.assertEqual(viewer.get(url).status_code, 200, url)


class BreadcrumbTests(ReportFixture, TestCase):
    def setUp(self):
        self.build()

    def trail(self, url, user=None):
        return breadcrumb_context(resolve(url), user)

    def labels(self, context):
        return [c["label"] for c in context["breadcrumbs"]]

    def test_result_sheet_links_to_its_own_assessment(self):
        context = self.trail(self.sheet_url)
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Assessment", "Result sheet"])
        self.assertEqual(context["breadcrumbs"][2]["url"], reverse("core:assessment-detail", args=[self.ut1.pk]))
        self.assertEqual(context["nav_section"], "academic-year-list")

    def test_matrix_links_to_the_year_assessment_list(self):
        context = self.trail(self.matrix_url)
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Assessments", "Subject/Section results"])
        self.assertEqual(context["breadcrumbs"][2]["url"],
                         reverse("core:academic-year-assessments", args=[self.year.pk]))

    def test_student_reports_use_the_student_pk_only_for_student_routes(self):
        context = self.trail(self.card_url)
        self.assertEqual(self.labels(context), ["Overview", "Students", "Student", "Results", "Report card"])
        self.assertEqual(context["breadcrumbs"][2]["url"], reverse("core:student-detail", args=[self.asha.pk]))
        self.assertEqual(context["breadcrumbs"][3]["url"], self.student_url)
        self.assertEqual(context["nav_section"], "student-list")
        results = self.trail(self.student_url)
        self.assertEqual(self.labels(results), ["Overview", "Students", "Student", "Results"])

    def test_parent_crumbs_follow_the_destination_permission(self):
        user, _ = self.client_with("view_school", "view_studentresult")
        self.assertEqual(self.labels(self.trail(self.card_url, user)), ["Overview", "Results", "Report card"])
        user, _ = self.client_with("view_school", "view_studentresult", "view_student")
        self.assertEqual(self.labels(self.trail(self.card_url, user)),
                         ["Overview", "Students", "Student", "Results", "Report card"])
        user, _ = self.client_with("view_school", "view_studentresult", "view_academicyear")
        self.assertEqual(self.labels(self.trail(self.matrix_url, user)),
                         ["Overview", "Academic Years", "Subject/Section results"])
        user, _ = self.client_with("view_school", "view_studentresult", "view_academicyear", "view_assessment")
        self.assertEqual(self.labels(self.trail(self.sheet_url, user)),
                         ["Overview", "Academic Years", "Assessment", "Result sheet"])

    def test_overview_crumb_requires_view_school_and_teacher_route_has_no_trail(self):
        user, _ = self.client_with("view_studentresult")
        self.assertEqual(self.trail(self.student_url, user)["breadcrumbs"], [])
        self.assertEqual(self.trail(self.my_card)["breadcrumbs"], [])
