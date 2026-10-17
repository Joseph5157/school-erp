"""Current ownership vs historical visibility for subject teachers (ADR 0018 D6-D9).

Current operational scope (what a teacher owns today) decides result entry,
the working gradebook and My Students. Historical scope (all dated rows)
decides only which finalized results a teacher may still read, by the
assessment's own date.
"""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.authorization import (
    can_enter_results,
    current_teacher_assignments,
    historical_teacher_assignments,
    teacher_student_scope,
)
from core.forms import ResultEntryForm
from core.models import AssessmentTeacherAssignment as Assignment
from core.models import ResultStatus, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)
YEAR_START = date(2026, 6, 1)


class HandoverFixture(Phase4Fixture):
    """rao (A) teaches Maths 6A until 30 Sep; iyer (B) from 1 Oct. Today is 12 Oct."""

    def setUp(self):
        self.build_phase4()
        for target in ("core.models.business_today", "core.views.business_today"):
            patch = mock.patch(target, new=lambda: TODAY)
            patch.start()
            self.addCleanup(patch.stop)
        self.row_a = Assignment.assign(
            teacher=self.rao, offering=self.maths, section=self.six_a, start_date=YEAR_START
        )
        self.row_b = Assignment.assign(
            teacher=self.iyer, offering=self.maths, section=self.six_a,
            start_date=date(2026, 10, 1),
        )
        self.row_a.refresh_from_db()
        self.asha, self.asha_e = self.make_student("Asha")
        self.a_client = self.login("rao")
        self.b_client = self.login("iyer")

    def login(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def finalized(self, name, on, term):
        assessment = self.make_assessment(name=name, on=on, term=term)
        StudentResult.objects.create(
            assessment=assessment, academic_enrollment=self.asha_e,
            status=ResultStatus.MARKED, score=15, entered_by=self.admin,
        )
        self.force_finalize(assessment)
        return assessment

    def names(self, response):
        return [a.name for a in response.context["assessments"]]


class CurrentVersusHistoricalScopeTests(HandoverFixture, TestCase):
    def test_current_scope_is_only_rows_effective_today(self):
        self.assertFalse(current_teacher_assignments(self.rao).exists())
        self.assertEqual(list(current_teacher_assignments(self.iyer)), [self.row_b])
        self.assertFalse(can_enter_results(self.rao, self.maths, self.six_a))
        self.assertTrue(can_enter_results(self.iyer, self.maths, self.six_a))

    def test_historical_scope_keeps_every_row_of_that_teacher(self):
        self.assertEqual(list(historical_teacher_assignments(self.rao)), [self.row_a])
        self.assertEqual(list(historical_teacher_assignments(self.iyer)), [self.row_b])

    def test_current_scope_can_be_asked_for_another_date(self):
        on_boundary = current_teacher_assignments(self.rao, date(2026, 9, 30))
        self.assertEqual(list(on_boundary), [self.row_a])
        self.assertEqual(
            list(current_teacher_assignments(self.iyer, date(2026, 10, 1))), [self.row_b]
        )
        self.assertFalse(current_teacher_assignments(self.iyer, date(2026, 9, 30)).exists())

    def test_future_row_grants_no_current_access(self):
        self.row_b.end(date(2026, 10, 31))
        later = Assignment.assign(
            teacher=self.rao, offering=self.maths, section=self.six_a,
            start_date=date(2026, 11, 1),
        )
        self.assertFalse(current_teacher_assignments(self.rao).exists())
        self.assertFalse(can_enter_results(self.rao, self.maths, self.six_a))
        self.assertEqual(list(historical_teacher_assignments(self.rao)), [self.row_a, later])

    def test_deactivated_or_removed_teacher_has_neither_scope(self):
        self.iyer.groups.remove(self.teachers)
        self.rao.is_active = False
        self.rao.save()
        for user in (self.rao, self.iyer):
            with self.subTest(user=user.username):
                self.assertFalse(current_teacher_assignments(user).exists())
                self.assertFalse(historical_teacher_assignments(user).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.row_a.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.row_b.pk).exists())

    def test_student_scope_follows_current_ownership_only(self):
        self.assertFalse(teacher_student_scope(self.rao, TODAY).exists())
        self.assertEqual(set(teacher_student_scope(self.iyer, TODAY)), {self.asha_e})
        profile = reverse("core:my-student-detail", args=[self.asha.pk])
        self.assertEqual(self.a_client.get(profile).status_code, 403)
        self.assertEqual(self.b_client.get(profile).status_code, 200)


class DraftOwnershipVersusHistoricalVisibilityTests(HandoverFixture, TestCase):
    """The deliberate R10 rule: B finishes A's DRAFT, but A keeps the history."""

    def setUp(self):
        super().setUp()
        self.sept = self.make_assessment(name="Sept UT", on=date(2026, 9, 15), term=self.term1)
        self.entry = reverse("core:assessment-marks-entry", args=[self.sept.pk])
        field = ResultEntryForm.status_name(self.asha_e)
        self.post = {field: "MARKED", ResultEntryForm.score_name(self.asha_e): "17"}

    def test_new_owner_finishes_the_draft_and_the_old_owner_cannot(self):
        self.assertEqual(self.a_client.get(self.entry).status_code, 403)
        self.assertEqual(self.a_client.post(self.entry, self.post).status_code, 403)
        self.assertEqual(self.b_client.post(self.entry, self.post).status_code, 302)
        result = StudentResult.objects.get(assessment=self.sept)
        self.assertEqual(result.entered_by, self.iyer)

    def test_finalized_visibility_follows_the_assessment_date_not_entered_by(self):
        self.b_client.post(self.entry, self.post)
        self.force_finalize(self.sept)
        a_page = self.a_client.get(reverse("core:my-subject-results", args=[self.row_a.pk]))
        self.assertEqual(a_page.status_code, 200)
        self.assertEqual(self.names(a_page), ["Sept UT"])
        b_page = self.b_client.get(reverse("core:my-subject-results", args=[self.row_b.pk]))
        self.assertEqual(self.names(b_page), [])
        # B entered the marks but never gains historical ownership of September.
        profile = reverse("core:my-student-detail", args=[self.asha.pk])
        self.assertEqual(list(self.b_client.get(profile).context["results"]), [])

    def test_new_owner_cannot_open_the_old_owners_finalized_assessment(self):
        self.b_client.post(self.entry, self.post)
        self.force_finalize(self.sept)
        self.assertEqual(self.b_client.get(self.entry).status_code, 403)

    def test_working_gradebook_hides_finalized_results_outside_the_owners_dates(self):
        self.finalized("Aug UT", date(2026, 8, 20), self.term1)
        self.finalized("Oct UT", date(2026, 10, 5), self.term2)
        gradebook = reverse("core:my-gradebook", args=[self.row_b.pk])
        shown = self.names(self.b_client.get(gradebook))
        self.assertIn("Sept UT", shown)  # still DRAFT: B owns it now
        self.assertIn("Oct UT", shown)
        self.assertNotIn("Aug UT", shown)  # finalized while A owned the slot

    def test_former_owner_has_no_working_gradebook(self):
        gradebook = reverse("core:my-gradebook", args=[self.row_a.pk])
        self.assertEqual(self.a_client.get(gradebook).status_code, 404)


class HandoverBoundaryTests(HandoverFixture, TestCase):
    def test_the_last_day_belongs_to_the_old_teacher_and_the_next_to_the_new_one(self):
        self.finalized("Last day", date(2026, 9, 30), self.term1)
        self.finalized("First day", date(2026, 10, 1), self.term2)
        a_page = self.a_client.get(reverse("core:my-subject-results", args=[self.row_a.pk]))
        b_page = self.b_client.get(reverse("core:my-subject-results", args=[self.row_b.pk]))
        self.assertEqual(self.names(a_page), ["Last day"])
        self.assertEqual(self.names(b_page), ["First day"])

    def test_student_profile_shows_only_the_current_owners_dates(self):
        self.finalized("Last day", date(2026, 9, 30), self.term1)
        self.finalized("First day", date(2026, 10, 1), self.term2)
        profile = reverse("core:my-student-detail", args=[self.asha.pk])
        shown = {r.assessment.name for r in self.b_client.get(profile).context["results"]}
        self.assertEqual(shown, {"First day"})


class PastDutiesTests(HandoverFixture, TestCase):
    def test_results_page_separates_current_and_past_duties(self):
        a_page = self.a_client.get(reverse("core:my-results"))
        self.assertEqual(list(a_page.context["duties"]), [])
        self.assertEqual(list(a_page.context["past_duties"]), [self.row_a])
        self.assertContains(a_page, "Past duties")
        b_page = self.b_client.get(reverse("core:my-results"))
        self.assertEqual(list(b_page.context["duties"]), [self.row_b])
        self.assertEqual(list(b_page.context["past_duties"]), [])
        self.assertNotContains(b_page, "Past duties")

    def test_past_duty_is_limited_to_its_dates(self):
        self.finalized("Aug UT", date(2026, 8, 20), self.term1)
        self.finalized("Oct UT", date(2026, 10, 5), self.term2)
        page = self.a_client.get(reverse("core:my-subject-results", args=[self.row_a.pk]))
        self.assertEqual(self.names(page), ["Aug UT"])

    def test_deactivated_former_teacher_loses_the_past_duty_too(self):
        self.rao.is_active = False
        self.rao.save()
        url = reverse("core:my-subject-results", args=[self.row_a.pk])
        self.assertIn(self.a_client.get(url).status_code, (302, 403))

    def test_teacher_removed_from_the_group_loses_the_past_duty_too(self):
        self.rao.groups.remove(self.teachers)
        url = reverse("core:my-subject-results", args=[self.row_a.pk])
        self.assertEqual(self.a_client.get(url).status_code, 403)
        self.assertEqual(self.a_client.get(reverse("core:my-results")).status_code, 403)

    def test_a_future_row_is_not_a_past_duty(self):
        self.row_b.end(date(2026, 10, 31))
        future = Assignment.assign(
            teacher=self.rao, offering=self.maths, section=self.six_a,
            start_date=date(2026, 11, 1),
        )
        page = self.a_client.get(reverse("core:my-results"))
        self.assertEqual(list(page.context["past_duties"]), [self.row_a])
        self.assertEqual(list(page.context["duties"]), [])
        self.assertEqual(list(page.context["upcoming_duties"]), [future])
