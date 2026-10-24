"""UI-D1-5B: assessment list and filters, create/edit form, detail and roster, finalization
presentation, audited result correction form and history, and permission-aware breadcrumbs.

Presentation only. These tests pin page structure, the Absent / Not entered distinction, the
finalization readiness presentation, permission-gated controls, that every POST keeps its URL and
behaviour, invalid-filter disclosure, form error association and the breadcrumb trails (including
that no breadcrumb reuses one model's pk for another model's route). Marks, grading, readiness and
correction rules are covered by test_phase4_* and are not retested here.
"""

import re
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core.breadcrumbs import breadcrumb_context
from core.models import AcademicYear, Assessment, ResultCorrection, ResultStatus, Section, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()

TODAY = date(2026, 10, 10)


def html(response):
    return response.content.decode()


class AssessmentFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.ravi, self.ravi_a = self.make_student("Ravi Rao")
        self.meera, self.meera_a = self.make_student("Meera Rao")
        self.dev, self.dev_a = self.make_student("Dev Rao")
        self.assign(self.rao, self.maths, self.six_a)
        self.make_scale()
        # A draft with one marked, one absent and one student not entered (not ready to finalize).
        self.draft = self.unique_assessment("Quiz 1", maximum="20", pass_mark="8")
        self.draft.save_draft_result(
            enrollment=self.ravi_a, status=ResultStatus.MARKED, score="17", actor=self.rao
        )
        self.draft.save_draft_result(
            enrollment=self.meera_a, status=ResultStatus.ABSENT, score=None, actor=self.rao
        )
        # A finalized assessment (Term 2, Section B) with one result.
        self.assign(self.rao, self.maths, self.six_b)
        self.zoya, self.zoya_a = self.make_student("Zoya Iyer", section=self.six_b)
        self.final = self.unique_assessment(
            "Midterm", section=self.six_b, term=self.term2, on=date(2026, 10, 5), maximum="50"
        )
        self.final.save_draft_result(
            enrollment=self.zoya_a, status=ResultStatus.MARKED, score="40", actor=self.rao
        )
        with mock.patch("core.models.business_today", new=lambda: TODAY):
            self.final.finalize(actor=self.admin)
        self.zoya_result = StudentResult.objects.get(academic_enrollment=self.zoya_a)
        self.client.login(username="admin", password="pass-12345")
        self.list_url = reverse("core:academic-year-assessments", args=[self.year.pk])
        self.draft_url = reverse("core:assessment-detail", args=[self.draft.pk])
        self.final_url = reverse("core:assessment-detail", args=[self.final.pk])

    def unique_assessment(self, name, **kwargs):
        """An assessment whose pk differs from the year's pk, so a pk mix-up fails a test."""
        assessment = self.make_assessment(name=name, **kwargs)
        if assessment.pk == self.year.pk:
            assessment.delete()
            assessment = self.make_assessment(name=name, **kwargs)
        return assessment

    def client_with(self, *codenames):
        self._users = getattr(self, "_users", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._users}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client


class ListTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()

    def test_header_table_columns_and_badges(self):
        page = html(self.client.get(self.list_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Assessments</h1>', page)
        self.assertIn('role="region" aria-label="Assessments for 2026-27" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertEqual(
            re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', page),
            ["Assessment", "Status", "Subject", "Section", "Date", "Term", "Max", "Pass"],
        )
        self.assertRegex(page, r"erp-status--draft[^>]*><span[^>]*>Status: </span>Draft")
        self.assertRegex(page, r"erp-status--finalized[^>]*><span[^>]*>Status: </span>Finalized")
        self.assertIn(reverse("core:assessment-detail", args=[self.draft.pk]), page)
        row = re.search(r"Quiz 1.*?</tr>", page, re.S).group(0)
        self.assertIn('<td class="erp-num">20.00</td>', row)
        self.assertIn("8.00", row)
        self.assertIn("&mdash;", re.search(r"Midterm.*?</tr>", page, re.S).group(0))  # no pass mark

    def test_first_load_is_unfiltered_and_silent(self):
        page = html(self.client.get(self.list_url))
        self.assertNotIn("were not applied", page)
        self.assertNotIn("Clear filters", page)
        self.assertNotIn("form-error-summary", page)
        self.assertIn("Quiz 1", page)
        self.assertIn("Midterm", page)

    def test_valid_filter_narrows_and_offers_clear(self):
        page = html(self.client.get(self.list_url, {"status": "FINALIZED", "term": "", "section": ""}))
        self.assertIn("Midterm", page)
        self.assertNotIn("Quiz 1", page)
        self.assertIn("Clear filters", page)
        self.assertNotIn("were not applied", page)
        # An empty submitted filter is valid and shows everything, without the "Clear" note.
        everything = html(self.client.get(self.list_url, {"status": "", "term": "", "section": ""}))
        self.assertIn("Quiz 1", everything)
        self.assertNotIn("Clear filters", everything)

    def test_invalid_filter_is_disclosed_and_shows_everything(self):
        page = html(self.client.get(self.list_url, {"term": "999999", "status": "NOPE"}))
        self.assertIn("The filters were not applied; showing all assessments.", page)
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertIn('href="#id_term"', page)
        self.assertIn('href="#id_status"', page)
        self.assertIn('aria-invalid="true"', page)
        self.assertIn('id="id_term_error"', page)
        self.assertIn("Quiz 1", page)
        self.assertIn("Midterm", page)
        self.assertNotIn("Clear filters", page)

    def test_empty_states_differ(self):
        page = html(self.client.get(self.list_url, {"status": "FINALIZED", "term": self.term1.pk}))
        self.assertIn("No assessments match these filters.", page)
        other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        self.assertIn(
            "No assessments have been planned for this Academic Year yet.",
            html(self.client.get(reverse("core:academic-year-assessments", args=[other_year.pk]))),
        )

    def test_header_actions_are_gated(self):
        plan = reverse("core:assessment-create", args=[self.year.pk])
        results = reverse("core:report-subject-section-results", args=[self.year.pk])
        page = html(self.client.get(self.list_url))
        self.assertIn(f'href="{plan}"', page)
        self.assertIn(f'href="{results}"', page)
        _, viewer = self.client_with("view_assessment")
        page = html(viewer.get(self.list_url))
        self.assertNotIn(plan, page)
        self.assertNotIn(results, page)
        self.assertIn("Quiz 1", page)

    def test_context_is_unchanged(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.context["academic_year"], self.year)
        self.assertEqual(len(response.context["assessments"]), 2)
        self.assertFalse(response.context["form"].is_bound)


class DetailTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()

    def test_draft_header_facts_and_semantics(self):
        page = html(self.client.get(self.draft_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Quiz 1</h1>', page)
        self.assertRegex(page, r"erp-status--draft[^>]*><span[^>]*>Status: </span>Draft")
        self.assertNotIn("No teacher assigned", page)
        self.assertIn('aria-label="Results for Quiz 1"', page)
        self.assertIn("A Student without a result is <strong>not</strong> absent", page)
        rows = dict(re.findall(
            r'<th scope="row" class="fw-semibold">([^<]+)</th>(.*?)</tr>', page, re.S))
        self.assertIn("Not entered", rows["Dev Rao"])
        self.assertNotIn("Absent", rows["Dev Rao"])
        self.assertIn("Absent", rows["Meera Rao"])
        self.assertNotIn("Not entered", rows["Meera Rao"])
        self.assertIn("17.00 / 20.00", rows["Ravi Rao"])

    def test_missing_teacher_has_a_text_label(self):
        other = self.unique_assessment("Orphan", section=self.six_b, term=self.term1)
        Assessment.objects.filter(pk=other.pk).update(offering=self.sanskrit)
        page = html(self.client.get(reverse("core:assessment-detail", args=[other.pk])))
        self.assertRegex(page, r"erp-status--pending[^>]*><span[^>]*>Status: </span>No teacher assigned")

    def test_not_ready_lists_problems_and_offers_no_finalize_button(self):
        response = self.client.get(self.draft_url)
        page = html(response)
        self.assertEqual(response.context["problems"], self.draft.finalization_problems())
        self.assertTrue(response.context["problems"])
        self.assertIn("Not ready yet:", page)
        self.assertRegex(page, r"erp-status--pending[^>]*><span[^>]*>Status: </span>Not ready")
        self.assertNotIn(reverse("core:assessment-finalize", args=[self.draft.pk]), page)

    def test_ready_shows_consequence_text_and_the_same_finalize_post(self):
        self.draft.save_draft_result(
            enrollment=self.dev_a, status=ResultStatus.MARKED, score="9", actor=self.rao
        )
        page = html(self.client.get(self.draft_url))
        finalize = reverse("core:assessment-finalize", args=[self.draft.pk])
        self.assertIn(f'method="post" action="{finalize}"', page)
        self.assertIn("Every Student on the roster has a result. Finalizing makes these the official "
                      "results; after that only audited corrections can change them.", page)
        self.assertIn("Finalizing does not publish anything to guardians.", page)
        self.assertRegex(page, r"erp-status--info[^>]*><span[^>]*>Status: </span>Ready to finalize")
        self.assertNotIn("Not ready yet", page)
        self.client.get(finalize)  # GET never finalizes
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.is_finalized)
        with mock.patch("core.models.business_today", new=lambda: TODAY):
            self.client.post(finalize)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.is_finalized)

    def test_finalize_panel_needs_the_permission(self):
        self.draft.save_draft_result(
            enrollment=self.dev_a, status=ResultStatus.MARKED, score="9", actor=self.rao
        )
        _, viewer = self.client_with("view_assessment")
        page = html(viewer.get(self.draft_url))
        self.assertNotIn("Finalize results", page)
        self.assertNotIn("assessment-finalize", page)
        _, finalizer = self.client_with("view_assessment", "finalize_assessment")
        self.assertIn("Finalize results", html(finalizer.get(self.draft_url)))

    def test_finalized_page(self):
        page = html(self.client.get(self.final_url))
        self.assertRegex(page, r"erp-status--finalized[^>]*><span[^>]*>Status: </span>Finalized")
        self.assertIn("(frozen at finalization)", page)
        self.assertIn(f'href="{reverse("core:report-result-sheet", args=[self.final.pk])}"', page)
        self.assertNotIn("Finalize results", page)
        self.assertNotIn("Delete this planned assessment", page)
        self.assertNotIn(reverse("core:assessment-update", args=[self.final.pk]), page)
        self.assertIn(reverse("core:result-correct", args=[self.zoya_result.pk]), page)
        self.assertIn('aria-label="Correct result for Zoya Iyer">Correct</a>', page)

    def test_correct_and_result_sheet_links_are_gated(self):
        correct = reverse("core:result-correct", args=[self.zoya_result.pk])
        sheet = reverse("core:report-result-sheet", args=[self.final.pk])
        _, viewer = self.client_with("view_assessment")
        page = html(viewer.get(self.final_url))
        self.assertNotIn(correct, page)
        self.assertNotIn(sheet, page)
        for codename, needle in (("correct_studentresult", correct), ("view_studentresult", sheet)):
            _, client = self.client_with("view_assessment", codename)
            self.assertIn(needle, html(client.get(self.final_url)), codename)

    def test_corrected_badge_after_a_correction(self):
        self.zoya_result.correct(
            new_status=ResultStatus.MARKED, new_score="42", actor=self.admin, reason="Re-added."
        )
        page = html(self.client.get(self.final_url))
        self.assertRegex(page, r"erp-status--info[^>]*><span[^>]*>Status: </span>corrected")
        self.assertIn("42.00 / 50.00", page)

    def test_delete_is_gated_keeps_post_and_states_its_consequence(self):
        empty = self.unique_assessment("Planned", section=self.six_b, term=self.term1)
        url = reverse("core:assessment-detail", args=[empty.pk])
        delete = reverse("core:assessment-delete", args=[empty.pk])
        page = html(self.client.get(url))
        self.assertIn(f'method="post" action="{delete}"', page)
        self.assertIn("Delete removes the planned assessment at once and is not confirmed first.", page)
        self.assertNotIn("assessment-delete", self.draft_url)
        self.assertNotIn("Delete this planned assessment", html(self.client.get(self.draft_url)))  # locked
        _, viewer = self.client_with("view_assessment")
        self.assertNotIn(delete, html(viewer.get(url)))
        self.client.get(delete)
        self.assertTrue(Assessment.objects.filter(pk=empty.pk).exists())
        self.client.post(delete)
        self.assertFalse(Assessment.objects.filter(pk=empty.pk).exists())

    def test_locked_draft_explains_why(self):
        self.assertIn("Results entered; the Term, Subject, Section, date and maximum marks are locked.",
                      html(self.client.get(self.draft_url)))

    def test_primary_action_follows_state_and_permission(self):
        edit = reverse("core:assessment-update", args=[self.draft.pk])
        self.assertIn(f'href="{edit}"', html(self.client.get(self.draft_url)))
        _, viewer = self.client_with("view_assessment")
        self.assertNotIn(edit, html(viewer.get(self.draft_url)))

    def test_context_is_unchanged(self):
        response = self.client.get(self.draft_url)
        for key in ("assessment", "problems", "rows", "marked_count", "ineligible_results", "teacher"):
            self.assertIn(key, response.context)
        self.assertEqual(response.context["marked_count"], 2)
        self.assertEqual(len(response.context["rows"]), 3)


    def empty_roster_assessment(self, *, pass_mark, finalized):
        """An assessment in a Section with no enrolled Students, so the roster is empty."""
        self._empty_sections = getattr(self, "_empty_sections", 0) + 1
        section = Section.objects.create(class_grade=self.grade6, name=f"Empty {self._empty_sections}")
        assessment = self.unique_assessment(
            f"Empty roster {self._empty_sections}", section=section, pass_mark=pass_mark
        )
        if finalized:
            self.force_finalize(assessment)
        return assessment

    def test_empty_roster_colspan_matches_the_visible_columns(self):
        _, viewer = self.client_with("view_assessment")
        cases = (  # (pass mark, finalized, client, expected visible columns)
            (None, False, self.client, 6),
            ("8", False, self.client, 7),
            (None, True, self.client, 7),   # Correct column, no Pass/Fail
            ("8", True, self.client, 8),    # Correct column and Pass/Fail
            (None, True, viewer, 6),        # finalized but the viewer cannot correct
            ("8", True, viewer, 7),
        )
        for pass_mark, finalized, client, expected in cases:
            with self.subTest(pass_mark=pass_mark, finalized=finalized, expected=expected):
                assessment = self.empty_roster_assessment(pass_mark=pass_mark, finalized=finalized)
                page = html(client.get(reverse("core:assessment-detail", args=[assessment.pk])))
                table = re.search(r'aria-label="Results for[^>]*>.*?</table>', page, re.S).group(0)
                headers = len(re.findall(r'<th scope="col"', table))
                colspan = int(re.search(r'<td colspan="(\d+)">No Students are enrolled', table).group(1))
                self.assertEqual(headers, expected)
                self.assertEqual(colspan, headers)
                self.assertIn("No Students are enrolled in this Section on the assessment date.", table)

    def test_populated_roster_rows_match_the_header_count(self):
        page = html(self.client.get(self.final_url))
        table = re.search(r'aria-label="Results for[^>]*>.*?</table>', page, re.S).group(0)
        headers = len(re.findall(r'<th scope="col"', table))
        first_row = re.search(r"<tbody>.*?<tr>(.*?)</tr>", table, re.S).group(1)
        self.assertEqual(headers, len(re.findall(r"<t[dh][ >]", first_row)))


class FormTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()
        self.create_url = reverse("core:assessment-create", args=[self.year.pk])

    def test_create_form_structure(self):
        page = html(self.client.get(self.create_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Plan an assessment</h1>', page)
        self.assertIn("erp-required-legend", page)
        for name in ("term", "offering", "section", "name", "assessment_date", "maximum_marks", "pass_mark"):
            self.assertIn(f'name="{name}"', page)
            self.assertIn(f'for="id_{name}"', page)
        self.assertIn("Optional. Leave empty for no pass/fail.", page)
        self.assertIn('id="id_pass_mark_helptext"', page)
        self.assertIn(f'href="{self.list_url}"', page)  # Cancel

    def test_invalid_post_shows_summary_and_associated_errors(self):
        response = self.client.post(self.create_url, {"name": ""})
        page = html(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn('role="alert" id="form-error-summary"', page)
        for name in ("term", "offering", "section", "name", "assessment_date", "maximum_marks"):
            self.assertIn(f'href="#id_{name}"', page, name)
            self.assertIn(f'id="id_{name}_error"', page, name)
        self.assertIn('aria-invalid="true"', page)
        dangling = [t for m in re.findall(r'aria-describedby="([^"]+)"', page) for t in m.split()
                    if f'id="{t}"' not in page]
        self.assertEqual(dangling, [])
        self.assertEqual(Assessment.objects.count(), 2)

    def test_create_and_update_post_still_work(self):
        fields = {
            "term": self.term1.pk, "offering": self.maths.pk, "section": self.six_a.pk,
            "name": "Quiz 2", "assessment_date": "2026-07-20", "maximum_marks": "10", "pass_mark": "",
        }
        response = self.client.post(self.create_url, fields)
        created = Assessment.objects.get(name="Quiz 2")
        self.assertRedirects(response, reverse("core:assessment-detail", args=[created.pk]))
        update = reverse("core:assessment-update", args=[created.pk])
        page = html(self.client.get(update))
        self.assertIn('class="erp-page-title">Edit assessment</h1>', page)
        self.assertIn('value="Quiz 2"', page)
        self.assertNotIn("Locked:", page)
        self.client.post(update, {**fields, "name": "Quiz 2b"})
        created.refresh_from_db()
        self.assertEqual(created.name, "Quiz 2b")

    def test_locked_assessment_explains_and_disables_fields(self):
        page = html(self.client.get(reverse("core:assessment-update", args=[self.draft.pk])))
        self.assertIn("<strong>Locked:</strong> results already exist", page)
        self.assertRegex(page, r'<input[^>]*name="maximum_marks"[^>]*disabled')
        self.assertNotRegex(page, r'<input[^>]*name="name"[^>]*disabled')

    def test_finalized_assessment_cannot_be_edited(self):
        response = self.client.get(reverse("core:assessment-update", args=[self.final.pk]))
        self.assertRedirects(response, self.final_url)


class CorrectionTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()
        self.url = reverse("core:result-correct", args=[self.zoya_result.pk])

    def test_page_structure(self):
        page = html(self.client.get(self.url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Correct result</h1>', page)
        self.assertIn("Zoya Iyer", page)
        self.assertIn("40.00 / 50.00", page)
        self.assertIn("The assessment stays finalized.", page)
        self.assertIn("erp-required-legend", page)
        for name in ("status", "score", "reason"):
            self.assertIn(f'for="id_{name}"', page)
        self.assertIn('aria-label="Correction history"', page)
        self.assertIn("No corrections yet.", page)
        self.assertIn(f'href="{self.final_url}"', page)

    def test_invalid_post_is_summarised_and_associated(self):
        page = html(self.client.post(self.url, {"status": "MARKED", "score": "", "reason": ""}))
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertIn('href="#id_score"', page)
        self.assertIn('href="#id_reason"', page)
        self.assertRegex(page, r'aria-describedby="[^"]*id_score_error[^"]*"')
        self.assertIn('id="id_reason_error"', page)
        self.assertEqual(ResultCorrection.objects.count(), 0)

    def test_post_still_corrects_and_history_lists_the_audit_row(self):
        response = self.client.post(
            self.url, {"status": "ABSENT", "score": "", "reason": "Was not present."}
        )
        self.assertRedirects(response, self.final_url)
        correction = ResultCorrection.objects.get()
        self.assertEqual((correction.previous_status, correction.new_status), ("MARKED", "ABSENT"))
        page = html(self.client.get(self.url))
        self.assertIn("Was not present.", page)
        self.assertIn("40.00", page)
        self.assertIn("Absent", page)
        self.assertNotIn("No corrections yet.", page)
        self.assertIn('<th scope="col">Reason</th>', page)

    def test_draft_results_cannot_be_corrected(self):
        draft_result = StudentResult.objects.get(academic_enrollment=self.ravi_a)
        response = self.client.get(reverse("core:result-correct", args=[draft_result.pk]))
        self.assertRedirects(response, self.draft_url)


    def test_history_table_has_its_own_scoped_class_and_readable_cells(self):
        reason = "Re-marked after a paper recount, with the second marker's agreement noted in the file."
        self.zoya_result.correct(
            new_status=ResultStatus.MARKED, new_score="42", actor=self.admin, reason=reason
        )
        page = html(self.client.get(self.url))
        region = re.search(r'<div class="erp-table-scroll"[^>]*aria-label="Correction history"[^>]*>', page).group(0)
        self.assertIn('role="region"', region)
        self.assertIn('tabindex="0"', region)
        table = re.search(r'aria-label="Correction history".*?</table>', page, re.S).group(0)
        self.assertIn('<table class="table erp-correction-table">', table)
        self.assertNotIn("erp-keep", table)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', table),
                         ["When", "From", "To", "Reason", "By"])
        row = re.search(r"<tbody>.*?<tr>(.*?)</tr>", table, re.S).group(1)
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S)
        self.assertEqual([c[0].strip() for c in cells],
                         ['class="text-nowrap"', 'class="text-nowrap"', 'class="text-nowrap"',
                          'class="text-break erp-correction-reason"', 'class="text-nowrap"'])
        self.assertEqual([cells[1][1], cells[2][1]], ["40.00", "42.00"])
        self.assertIn("agreement noted in the file.", cells[3][1])  # the whole reason is kept
        self.assertEqual(cells[4][1], "admin")

    def test_history_survives_an_invalid_post(self):
        self.zoya_result.correct(
            new_status=ResultStatus.MARKED, new_score="42", actor=self.admin, reason="First fix."
        )
        page = html(self.client.post(self.url, {"status": "MARKED", "score": "", "reason": ""}))
        self.assertIn("First fix.", page)
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertEqual(ResultCorrection.objects.count(), 1)


class AccessTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()

    def test_routes_keep_their_permission_outcomes(self):
        anonymous = self.client_class()
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        urls = [
            self.list_url,
            self.draft_url,
            reverse("core:assessment-create", args=[self.year.pk]),
            reverse("core:assessment-update", args=[self.draft.pk]),
            reverse("core:result-correct", args=[self.zoya_result.pk]),
        ]
        for url in urls:
            self.assertEqual(teacher.get(url).status_code, 403, url)
            self.assertEqual(anonymous.get(url).status_code, 302, url)
            self.assertEqual(self.client.get(url).status_code, 200, url)
        _, viewer = self.client_with("view_assessment")
        self.assertEqual(viewer.get(urls[0]).status_code, 200)
        self.assertEqual(viewer.get(urls[1]).status_code, 200)
        for url in urls[2:]:
            self.assertEqual(viewer.get(url).status_code, 403, url)


class BreadcrumbTests(AssessmentFixture, TestCase):
    def setUp(self):
        self.build()

    def trail(self, url, user=None):
        return breadcrumb_context(resolve(url), user)

    def labels(self, context):
        return [c["label"] for c in context["breadcrumbs"]]

    def test_ids_are_distinct_in_this_fixture(self):
        self.assertNotEqual(self.year.pk, self.draft.pk)
        self.assertNotEqual(self.year.pk, self.final.pk)

    def test_list_and_create_trails_use_the_year_pk(self):
        context = self.trail(self.list_url)
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Assessments"])
        self.assertEqual(context["nav_section"], "academic-year-assessments")
        create = self.trail(reverse("core:assessment-create", args=[self.year.pk]))
        self.assertEqual(self.labels(create),
                         ["Overview", "Academic Years", "Assessments", "Plan an assessment"])
        self.assertEqual(create["breadcrumbs"][2]["url"], self.list_url)

    def test_detail_and_correction_never_reuse_their_pk_as_a_year_pk(self):
        for url, last in (
            (self.draft_url, "Assessment"),
            (reverse("core:result-correct", args=[self.zoya_result.pk]), "Correct result"),
        ):
            context = self.trail(url)
            self.assertEqual(self.labels(context), ["Overview", "Academic Years", last])
            urls = [c["url"] for c in context["breadcrumbs"]]
            pk = resolve(url).kwargs["pk"]
            if pk != self.year.pk:
                self.assertNotIn(reverse("core:academic-year-assessments", args=[pk]), urls)

    def test_edit_links_to_its_own_assessment_only(self):
        context = self.trail(reverse("core:assessment-update", args=[self.draft.pk]))
        self.assertEqual(self.labels(context),
                         ["Overview", "Academic Years", "Assessment", "Edit assessment"])
        self.assertEqual(context["breadcrumbs"][2]["url"], self.draft_url)

    def test_pages_link_back_to_the_year_list_with_the_real_year_id(self):
        page = html(self.client.get(self.draft_url))
        self.assertIn(f'href="{self.list_url}"', page)
        correction = html(self.client.get(reverse("core:result-correct", args=[self.zoya_result.pk])))
        self.assertIn(f'href="{self.final_url}"', correction)
        if self.draft.pk != self.year.pk:
            wrong = reverse("core:academic-year-assessments", args=[self.draft.pk])
            self.assertNotIn(f'href="{wrong}"', page)

    def test_parent_crumbs_follow_the_destination_permission(self):
        create = reverse("core:assessment-create", args=[self.year.pk])
        user, _ = self.client_with("view_school", "add_assessment")
        self.assertEqual(self.labels(self.trail(create, user)), ["Overview", "Plan an assessment"])
        user, _ = self.client_with("view_school", "add_assessment", "view_academicyear")
        self.assertEqual(self.labels(self.trail(create, user)),
                         ["Overview", "Academic Years", "Plan an assessment"])
        user, _ = self.client_with(
            "view_school", "add_assessment", "view_academicyear", "view_assessment")
        self.assertEqual(self.labels(self.trail(create, user)),
                         ["Overview", "Academic Years", "Assessments", "Plan an assessment"])
        edit = reverse("core:assessment-update", args=[self.draft.pk])
        user, _ = self.client_with("view_school", "change_assessment", "view_academicyear")
        self.assertEqual(self.labels(self.trail(edit, user)),
                         ["Overview", "Academic Years", "Edit assessment"])

    def test_overview_crumb_requires_view_school(self):
        user, _ = self.client_with("view_assessment", "view_academicyear")
        self.assertEqual(self.labels(self.trail(self.list_url, user)), ["Academic Years", "Assessments"])
        user, _ = self.client_with("view_assessment")
        self.assertEqual(self.trail(self.list_url, user)["breadcrumbs"], [])
