"""Administrator Reassign, End, History and Delete for subject teachers (ADR 0018)."""

from datetime import date
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core import assignments
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    ResultStatus,
    StudentResult,
)
from core.models import AssessmentTeacherAssignment as Assignment
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)
YEAR_START = date(2026, 6, 1)


class AdminFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for target in ("core.models.business_today", "core.views.business_today"):
            patch = mock.patch(target, new=lambda: TODAY)
            patch.start()
            self.addCleanup(patch.stop)
        self.client.login(username="admin", password="pass-12345")
        self.list_url = reverse("core:academic-year-teacher-assignments", args=[self.year.pk])
        self.create_url = reverse("core:teacher-assignment-create", args=[self.year.pk])

    def assign_on(self, teacher, start, offering=None, section=None):
        return Assignment.assign(
            teacher=teacher, offering=offering or self.maths,
            section=section or self.six_a, start_date=start,
        )

    def post_assign(self, teacher, start, offering=None, section=None):
        return self.client.post(self.create_url, {
            "teacher": teacher.pk, "offering": (offering or self.maths).pk,
            "section": (section or self.six_a).pk, "start_date": start.isoformat(),
        })

    def end_url(self, row):
        return reverse("core:teacher-assignment-end", args=[row.pk])

    def delete_url(self, row):
        return reverse("core:teacher-assignment-delete", args=[row.pk])

    def snapshot(self):
        return list(Assignment.objects.order_by("pk").values_list(
            "pk", "teacher_id", "start_date", "end_date"
        ))

    def overview_row(self):
        data = assignments.overview(self.year, TODAY)
        return next(r for r in data["subject_rows"]
                    if r["offering"] == self.maths and r["section"] == self.six_a)

    def enter_result(self, teacher, on, term=None):
        _, enrollment = self.make_student("Asha")
        assessment = self.make_assessment(on=on, term=term)
        return StudentResult.objects.create(
            assessment=assessment, academic_enrollment=enrollment,
            status=ResultStatus.ABSENT, entered_by=teacher,
        )


class ReassignTests(AdminFixture, TestCase):
    def test_reassign_ends_the_old_row_and_keeps_both(self):
        old = self.assign_on(self.rao, YEAR_START)
        response = self.post_assign(self.iyer, date(2026, 10, 1))
        self.assertRedirects(response, self.list_url)
        old.refresh_from_db()
        self.assertEqual(old.end_date, date(2026, 9, 30))
        new = Assignment.objects.get(teacher=self.iyer)
        self.assertEqual(new.start_date, date(2026, 10, 1))
        self.assertIsNone(new.end_date)

    def test_form_defaults_the_start_to_today_inside_the_year(self):
        form = self.client.get(self.create_url).context["form"]
        self.assertEqual(form.initial["start_date"], TODAY)

    def test_form_is_prefilled_from_the_slot_link(self):
        page = self.client.get(
            self.create_url, {"offering": self.maths.pk, "section": self.six_a.pk}
        )
        self.assertEqual(str(page.context["form"].initial["offering"]), str(self.maths.pk))

    def test_same_day_replacement_is_rejected(self):
        first = self.assign_on(self.rao, YEAR_START)
        before = self.snapshot()
        response = self.post_assign(self.iyer, YEAR_START)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(), before)
        first.refresh_from_db()
        self.assertIsNone(first.end_date)

    def test_overlapping_future_schedule_rolls_everything_back(self):
        """current A + planned B + an overlapping future C: reject, change nothing."""
        a = self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 11, 1))
        a.refresh_from_db()
        self.assertEqual(a.end_date, date(2026, 10, 31))
        third = self.make_user("kapoor", self.teachers)
        before = self.snapshot()
        response = self.post_assign(third, date(2026, 10, 20))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlap")
        self.assertEqual(self.snapshot(), before)

    def test_start_must_be_inside_the_year(self):
        response = self.post_assign(self.rao, date(2025, 1, 1))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Assignment.objects.exists())

    def test_wrong_section_is_still_rejected(self):
        response = self.post_assign(self.rao, YEAR_START, offering=self.sanskrit)
        self.assertContains(response, "does not take this Subject offering")

    def test_only_active_teachers_can_be_chosen(self):
        gone = self.make_user("gone", self.teachers, is_active=False)
        response = self.post_assign(gone, YEAR_START)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Assignment.objects.exists())


class EndTests(AdminFixture, TestCase):
    def test_end_shortens_a_current_row(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.assertEqual(self.client.get(self.end_url(row)).status_code, 200)
        response = self.client.post(self.end_url(row), {"end_date": "2026-11-30"})
        self.assertRedirects(response, self.list_url)
        row.refresh_from_db()
        self.assertEqual(row.end_date, date(2026, 11, 30))

    def test_end_reports_results_after_the_proposed_date(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.enter_result(self.rao, date(2026, 9, 15))
        response = self.client.post(self.end_url(row), {"end_date": "2026-09-01"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "entered results")
        row.refresh_from_db()
        self.assertIsNone(row.end_date)

    def test_an_ended_row_cannot_be_extended(self):
        row = self.assign_on(self.rao, YEAR_START)
        row.end(date(2026, 8, 31))
        response = self.client.post(self.end_url(row), {"end_date": "2026-09-30"})
        self.assertContains(response, "only be ended earlier")

    def test_end_needs_the_change_permission(self):
        row = self.assign_on(self.rao, YEAR_START)
        teacher_client = self.client_class()
        teacher_client.login(username="rao", password="pass-12345")
        response = teacher_client.post(self.end_url(row), {"end_date": "2026-11-30"})
        self.assertEqual(response.status_code, 403)
        viewer = self.make_user("viewer")
        viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="view_assessmentteacherassignment"
            )
        )
        viewer_client = self.client_class()
        viewer_client.login(username="viewer", password="pass-12345")
        self.assertEqual(viewer_client.get(self.end_url(row)).status_code, 403)

    def test_administrators_group_holds_the_change_permission(self):
        self.assertTrue(
            self.admins.permissions.filter(codename="change_assessmentteacherassignment").exists()
        )


class DeleteStateTests(AdminFixture, TestCase):
    def test_buttons_follow_the_row_state(self):
        past = self.assign_on(self.rao, YEAR_START)
        current = self.assign_on(self.iyer, date(2026, 10, 1))
        page = self.client.get(self.list_url)
        self.assertContains(page, self.end_url(current))
        self.assertNotContains(page, self.delete_url(current))
        self.assertNotContains(page, self.delete_url(past))
        self.assertNotContains(page, self.end_url(past))

    def test_future_untouched_row_may_be_deleted(self):
        self.assign_on(self.rao, YEAR_START)
        future = self.assign_on(self.iyer, date(2026, 11, 1))
        page = self.client.get(self.list_url)
        self.assertContains(page, self.delete_url(future))
        self.assertRedirects(self.client.post(self.delete_url(future)), self.list_url)
        self.assertFalse(Assignment.objects.filter(pk=future.pk).exists())

    def test_started_rows_survive_a_forged_delete_post(self):
        past = self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))
        response = self.client.post(self.delete_url(past), follow=True)
        self.assertTrue(Assignment.objects.filter(pk=past.pk).exists())
        self.assertContains(response, "end it instead")

    def test_future_row_with_results_is_not_offered_for_deletion(self):
        self.assign_on(self.rao, YEAR_START)
        future = self.assign_on(self.iyer, date(2026, 11, 1))
        self.enter_result(self.iyer, date(2026, 11, 5), term=self.term2)
        self.assertNotContains(self.client.get(self.list_url), self.delete_url(future))


class HistoryPageTests(AdminFixture, TestCase):
    def test_history_lists_every_row_in_order_with_status(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))
        self.assign_on(self.rao, date(2026, 12, 1))
        slots = self.client.get(self.list_url).context["slots"]
        self.assertEqual(len(slots), 1)
        history = slots[0]["history"]
        self.assertEqual([(h["row"].teacher.username, h["status"]) for h in history],
                         [("rao", "Past"), ("iyer", "Current"), ("rao", "Starting soon")])
        self.assertEqual(slots[0]["current"].teacher, self.iyer)

    def test_open_ended_rows_are_labelled(self):
        self.assign_on(self.rao, YEAR_START)
        self.assertContains(self.client.get(self.list_url), "open-ended")

    def test_inactive_current_teacher_is_flagged_without_touching_history(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.rao.is_active = False
        self.rao.save()
        slots = self.client.get(self.list_url).context["slots"]
        self.assertTrue(slots[0]["inactive"])
        row.refresh_from_db()
        self.assertIsNone(row.end_date)

    def test_past_year_rows_are_all_past(self):
        past_year = AcademicYear.objects.create(
            name="2024-25", start_date=date(2024, 6, 1), end_date=date(2025, 3, 31)
        )
        offering = AcademicSubjectOffering.objects.create(
            academic_year=past_year, class_grade=self.grade6, subject=self.maths_subject
        )
        Assignment.objects.create(teacher=self.rao, offering=offering, section=self.six_a,
                                  start_date=past_year.start_date)
        url = reverse("core:academic-year-teacher-assignments", args=[past_year.pk])
        slots = self.client.get(url).context["slots"]
        self.assertEqual(slots[0]["history"][0]["status"], "Past")
        self.assertIsNone(slots[0]["current"])


class CoverageAndCopyTests(AdminFixture, TestCase):
    def test_gap_report_uses_the_row_effective_today(self):
        old = self.assign_on(self.rao, YEAR_START)
        old.end(date(2026, 9, 30))  # nobody owns the slot any more
        self.assertTrue(self.overview_row()["gap"])
        self.assign_on(self.iyer, date(2026, 10, 1))
        row = self.overview_row()
        self.assertFalse(row["gap"])
        self.assertEqual(row["assignment"].teacher, self.iyer)

    def test_inactive_flag_applies_to_the_effective_row_only(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))
        self.rao.is_active = False  # a departed former teacher
        self.rao.save()
        self.assertFalse(self.overview_row()["inactive"])
        self.iyer.is_active = False
        self.iyer.save()
        self.assertTrue(self.overview_row()["inactive"])

    def test_copy_takes_the_teacher_effective_on_the_last_day(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))  # rao ended 30 Sep
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        AcademicSubjectOffering.objects.create(
            academic_year=next_year, class_grade=self.grade6, subject=self.maths_subject
        )
        plan = assignments.plan_copy(self.year, next_year)
        teachers = {item.teacher_id for item in plan["copies"] if item.kind == "subject"}
        self.assertEqual(teachers, {self.iyer.pk})
        self.assertEqual(assignments.apply_copy(self.year, next_year, plan["token"]), 1)
        copied = Assignment.objects.get(offering__academic_year=next_year)
        self.assertEqual(copied.start_date, next_year.start_date)
        self.assertEqual(copied.teacher, self.iyer)

    def test_assessment_detail_names_the_teacher_for_the_assessment_date(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))
        sept = self.make_assessment(name="Sept UT", on=date(2026, 9, 15))
        october = self.make_assessment(name="Oct UT", on=date(2026, 10, 5), term=self.term2)
        for assessment, expected in ((sept, self.rao), (october, self.iyer)):
            page = self.client.get(reverse("core:assessment-detail", args=[assessment.pk]))
            self.assertEqual(page.context["teacher"], expected)

    def test_teacher_load_lists_dated_rows(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 10, 1))
        page = self.client.get(reverse("core:teacher-load", args=[self.rao.pk]))
        (_, rows), = page.context["years"]
        (row,) = rows["subject"]
        self.assertEqual((row.start_date, row.end_date), (YEAR_START, date(2026, 9, 30)))
