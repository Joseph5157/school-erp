"""Effective-dated subject teacher assignments: model rules (ADR 0018 D1-D5, D9)."""

from datetime import date, timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import AssessmentTeacherAssignment as Assignment
from core.models import ResultStatus, StudentResult
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)
YEAR_START = date(2026, 6, 1)
YEAR_END = date(2027, 3, 31)


class DatingFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        patch = mock.patch("core.models.business_today", new=lambda: TODAY)
        patch.start()
        self.addCleanup(patch.stop)

    def assign_on(self, teacher, start, offering=None, section=None):
        return Assignment.assign(
            teacher=teacher, offering=offering or self.maths,
            section=section or self.six_a, start_date=start,
        )

    def enter_result(self, teacher, on, term=None):
        _, enrollment = self.make_student("Asha")
        assessment = self.make_assessment(on=on, term=term)
        return StudentResult.objects.create(
            assessment=assessment, academic_enrollment=enrollment,
            status=ResultStatus.ABSENT, entered_by=teacher,
        )


class DateRulesTests(DatingFixture, TestCase):
    def test_open_ended_row_runs_to_year_end(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.assertIsNone(row.end_date)
        self.assertEqual(row.last_effective_date, YEAR_END)
        self.assertTrue(row.is_effective_on(YEAR_START))
        self.assertTrue(row.is_effective_on(YEAR_END))
        self.assertFalse(row.is_effective_on(YEAR_START - timedelta(days=1)))
        self.assertFalse(row.is_effective_on(YEAR_END + timedelta(days=1)))

    def test_dates_are_inclusive(self):
        row = self.assign_on(self.rao, date(2026, 7, 1))
        row.end(date(2026, 8, 31))
        for day, expected in ((date(2026, 6, 30), False), (date(2026, 7, 1), True),
                              (date(2026, 8, 31), True), (date(2026, 9, 1), False)):
            with self.subTest(day=day):
                self.assertEqual(
                    Assignment.objects.effective_on(day).filter(pk=row.pk).exists(), expected
                )

    def test_open_ended_queryset_stops_at_year_end(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.assertTrue(Assignment.objects.effective_on(YEAR_END).filter(pk=row.pk).exists())
        self.assertFalse(
            Assignment.objects.effective_on(YEAR_END + timedelta(days=1)).filter(pk=row.pk).exists()
        )

    def test_dates_must_sit_inside_the_year(self):
        for start in (YEAR_START - timedelta(days=1), YEAR_END + timedelta(days=1)):
            with self.subTest(start=start), self.assertRaises(ValidationError) as ctx:
                self.assign_on(self.rao, start)
            self.assertIn("start_date", ctx.exception.message_dict)
        row = Assignment(teacher=self.rao, offering=self.maths, section=self.six_a,
                         start_date=YEAR_START, end_date=YEAR_END + timedelta(days=1))
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_end_before_start_is_rejected(self):
        row = Assignment(teacher=self.rao, offering=self.maths, section=self.six_a,
                         start_date=date(2026, 8, 1), end_date=date(2026, 7, 31))
        with self.assertRaises(ValidationError):
            row.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assignment.objects.bulk_create([row])

    def test_future_dated_assignment_is_allowed_and_not_yet_effective(self):
        row = self.assign_on(self.rao, date(2026, 11, 1))
        self.assertFalse(row.is_effective_on(TODAY))
        self.assertFalse(Assignment.objects.effective_on(TODAY).filter(pk=row.pk).exists())
        self.assertTrue(
            Assignment.objects.effective_on(date(2026, 11, 1)).filter(pk=row.pk).exists()
        )


class OverlapAndHandoverTests(DatingFixture, TestCase):
    def test_handover_ends_the_old_row_and_keeps_history(self):
        old = self.assign_on(self.rao, YEAR_START)
        new = self.assign_on(self.iyer, date(2026, 9, 1))
        old.refresh_from_db()
        self.assertEqual(old.end_date, date(2026, 8, 31))
        self.assertEqual(
            Assignment.objects.filter(offering=self.maths, section=self.six_a).count(), 2
        )
        self.assertEqual(
            Assignment.objects.effective_on(date(2026, 8, 31)).get().teacher, self.rao
        )
        self.assertEqual(Assignment.objects.effective_on(date(2026, 9, 1)).get(), new)

    def test_other_section_or_offering_is_independent(self):
        self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, YEAR_START, section=self.six_b)
        self.assign_on(self.iyer, YEAR_START, offering=self.sanskrit, section=self.six_b)

    def test_overlapping_rows_are_rejected(self):
        first = self.assign_on(self.rao, date(2026, 7, 1))
        first.end(date(2026, 8, 31))
        second = self.assign_on(self.iyer, date(2026, 9, 1))
        overlapping = Assignment(teacher=self.rao, offering=self.maths, section=self.six_a,
                                 start_date=date(2026, 8, 15), end_date=date(2026, 9, 15))
        with self.assertRaises(ValidationError):
            overlapping.full_clean()
        self.assertEqual(Assignment.objects.count(), 2)
        second.refresh_from_db()
        self.assertIsNone(second.end_date)

    def test_same_start_date_is_rejected_by_the_database_too(self):
        self.assign_on(self.rao, YEAR_START)
        with self.assertRaises(ValidationError):
            self.assign_on(self.iyer, YEAR_START)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assignment.objects.create(teacher=self.iyer, offering=self.maths,
                                      section=self.six_a, start_date=YEAR_START)

    def test_future_handover_ends_the_current_row_the_day_before(self):
        current = self.assign_on(self.rao, YEAR_START)
        self.assign_on(self.iyer, date(2026, 11, 1))
        current.refresh_from_db()
        self.assertEqual(current.end_date, date(2026, 10, 31))

    def test_cannot_extend_an_ended_row(self):
        row = self.assign_on(self.rao, YEAR_START)
        row.end(date(2026, 8, 31))
        with self.assertRaises(ValidationError):
            row.end(date(2026, 9, 30))

    def test_cannot_end_before_results_the_teacher_entered(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.enter_result(self.rao, date(2026, 9, 15))
        with self.assertRaises(ValidationError):
            row.end(date(2026, 9, 1))
        row.end(date(2026, 9, 15))

    def test_section_must_take_the_offering(self):
        with self.assertRaises(ValidationError) as ctx:
            self.assign_on(self.rao, YEAR_START, offering=self.sanskrit, section=self.six_a)
        self.assertIn("section", ctx.exception.message_dict)


class TeacherStatusTests(DatingFixture, TestCase):
    def test_new_rows_need_an_active_teacher(self):
        outsider = self.make_user("outsider")
        with self.assertRaises(ValidationError) as ctx:
            self.assign_on(outsider, YEAR_START)
        self.assertIn("teacher", ctx.exception.message_dict)
        self.rao.is_active = False
        self.rao.save()
        with self.assertRaises(ValidationError):
            self.assign_on(self.rao, YEAR_START)

    def test_a_departed_teachers_row_can_still_be_ended(self):
        row = self.assign_on(self.rao, YEAR_START)
        self.rao.groups.remove(self.teachers)
        self.rao.is_active = False
        self.rao.save()
        row.end(date(2026, 9, 30))
        row.refresh_from_db()
        self.assertEqual(row.end_date, date(2026, 9, 30))
        self.assign_on(self.iyer, date(2026, 10, 1))  # and a hand-over from them works


class DeletionRulesTests(DatingFixture, TestCase):
    def test_future_row_without_dependents_can_be_deleted(self):
        row = self.assign_on(self.rao, date(2026, 11, 1))
        self.assertFalse(row.is_historically_relevant)
        row.delete()
        self.assertFalse(Assignment.objects.exists())

    def test_started_row_is_historical_even_with_no_results(self):
        for start in (YEAR_START, TODAY):
            with self.subTest(start=start):
                row = Assignment.objects.create(
                    teacher=self.rao, offering=self.sanskrit, section=self.six_b,
                    start_date=start,
                )
                self.assertTrue(row.is_historically_relevant)
                with self.assertRaises(ValidationError):
                    row.delete()
                self.assertTrue(Assignment.objects.filter(pk=row.pk).exists())
                Assignment.objects.filter(pk=row.pk).update(start_date=date(2027, 1, 1))
                row.refresh_from_db()
                row.delete()  # the same row, not yet started, may go

    def test_future_row_with_results_cannot_be_deleted(self):
        row = self.assign_on(self.rao, date(2026, 11, 1))
        self.enter_result(self.rao, date(2026, 11, 5), term=self.term2)
        self.assertTrue(row.has_dependents())
        with self.assertRaises(ValidationError):
            row.delete()

    def test_queryset_delete_obeys_the_same_rule(self):
        started = self.assign_on(self.rao, YEAR_START)
        with self.assertRaises(ValidationError):
            Assignment.objects.filter(pk=started.pk).delete()
        started.end(date(2026, 7, 31))
        future = self.assign_on(self.iyer, date(2026, 11, 1))
        Assignment.objects.filter(pk=future.pk).delete()
        self.assertEqual(Assignment.objects.count(), 1)

    def test_offering_cannot_drop_a_section_with_a_historical_row(self):
        row = self.assign_on(self.rao, YEAR_START, offering=self.sanskrit, section=self.six_b)
        row.end(date(2026, 7, 31))
        with self.assertRaises(ValidationError):
            self.sanskrit.set_sections([self.six_a])
