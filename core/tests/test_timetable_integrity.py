"""TDB-4B: timetable integrity rules R1-R8, lifecycle and clash helper (ADR 0021)."""

import threading
from datetime import date
from unittest import mock, skipUnless

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase

from core import authorization, timetable
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    AssessmentTeacherAssignment,
    Section,
    Subject,
    TimetablePeriod,
    TimetableSlot,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 18)  # a Sunday; only used as the pinned business date


def pin_today(on=TODAY):
    return mock.patch("core.models.business_today", new=lambda: on)


class TimetableFixture(Phase4Fixture):
    def build_timetable(self):
        self.build_phase4()
        self.p1 = TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="P1")
        self.p2 = TimetablePeriod.objects.create(academic_year=self.year, sequence=2, label="P2")

    def slot(self, **overrides):
        values = {
            "period": self.p1, "weekday": 0, "section": self.six_a, "offering": self.maths,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return TimetableSlot.create(**values)

    def assign_from(self, teacher, offering, section, start, end=None):
        return AssessmentTeacherAssignment.objects.create(
            teacher=teacher, offering=offering, section=section, start_date=start, end_date=end,
        )

    def clear_assignments(self, **filters):
        # The model refuses to delete started assignments; fixtures reset them raw.
        AssessmentTeacherAssignment.objects.filter(**filters)._raw_delete("default")

    def other_year(self):
        return AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )


class EffectiveOnTests(TimetableFixture, TestCase):
    def setUp(self):
        self.build_timetable()

    def test_null_end_runs_to_the_academic_year_end_and_no_further(self):
        slot = self.slot(start_date=date(2026, 6, 1))
        effective = TimetableSlot.objects.effective_on
        self.assertIn(slot, effective(date(2027, 3, 31)))
        self.assertNotIn(slot, effective(date(2027, 4, 1)))
        self.assertNotIn(slot, effective(date(2030, 1, 1)))

    def test_explicit_end_still_applies_inside_the_year(self):
        slot = self.slot(start_date=date(2026, 6, 10), end_date=date(2026, 6, 20))
        effective = TimetableSlot.objects.effective_on
        self.assertIn(slot, effective(date(2026, 6, 10)))
        self.assertIn(slot, effective(date(2026, 6, 20)))
        self.assertNotIn(slot, effective(date(2026, 6, 21)))
        self.assertNotIn(slot, effective(date(2026, 6, 9)))


class StructuralRuleTests(TimetableFixture, TestCase):
    def setUp(self):
        self.build_timetable()

    def assertRejected(self, field=None, **overrides):
        before = TimetableSlot.objects.count()
        with self.assertRaises(ValidationError) as ctx:
            self.slot(**overrides)
        self.assertEqual(TimetableSlot.objects.count(), before)
        if field:
            self.assertIn(field, ctx.exception.message_dict)

    # R1
    def test_r1_offering_from_another_academic_year_is_rejected(self):
        other = self.other_year()
        foreign = AcademicSubjectOffering.objects.create(
            academic_year=other, class_grade=self.grade6, subject=Subject.objects.create(name="Art")
        )
        self.assertRejected("offering", offering=foreign)

    # R2
    def test_r2_offering_limited_to_other_sections_is_rejected(self):
        self.assertRejected("offering", offering=self.sanskrit, section=self.six_a)

    def test_r2_offering_for_another_grade_is_rejected(self):
        from core.models import ClassGrade

        seven_a = Section.objects.create(class_grade=ClassGrade.objects.create(name="G7"), name="A")
        self.assertRejected("offering", section=seven_a)

    def test_r2_limited_offering_is_accepted_for_its_listed_section(self):
        self.assertEqual(self.slot(offering=self.sanskrit, section=self.six_b).section, self.six_b)

    # R3
    def test_r3_start_before_the_year_is_rejected(self):
        self.assertRejected("start_date", start_date=date(2026, 5, 31))

    def test_r3_start_after_the_year_is_rejected(self):
        self.assertRejected("start_date", start_date=date(2027, 4, 1))

    def test_r3_end_after_the_year_is_rejected(self):
        self.assertRejected("end_date", end_date=date(2027, 4, 1))

    def test_r3_end_before_start_is_rejected(self):
        self.assertRejected("end_date", start_date=date(2026, 7, 2), end_date=date(2026, 7, 1))

    def test_r3_dates_on_the_year_edges_are_accepted(self):
        self.slot(start_date=date(2026, 6, 1), end_date=date(2027, 3, 31))

    # R4
    def test_r4_adjacent_ranges_do_not_overlap(self):
        self.slot(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        self.slot(start_date=date(2026, 7, 1))

    def test_r4_shared_boundary_day_overlaps(self):
        self.slot(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        self.assertRejected(start_date=date(2026, 6, 30))

    def test_r4_null_ended_slot_blocks_later_starts_to_year_end(self):
        self.slot(start_date=date(2026, 6, 1))
        with self.assertRaises(ValidationError):
            self.slot(start_date=date(2027, 3, 31))

    def test_r4_null_ended_new_slot_collides_with_a_later_existing_one(self):
        self.slot(start_date=date(2026, 9, 1))
        with self.assertRaises(ValidationError):
            self.slot(start_date=date(2026, 6, 1))

    def test_r4_other_period_weekday_or_section_is_independent(self):
        self.slot()
        self.slot(period=self.p2)
        self.slot(weekday=1)
        self.slot(section=self.six_b)

    # R5
    def test_r5_saturday_needs_a_saturday_instructional_year(self):
        self.assertRejected("weekday", weekday=5)

    def test_r5_saturday_is_accepted_when_the_year_runs_saturdays(self):
        self.year.saturdays_instructional = True
        self.year.save()
        self.assertEqual(self.slot(weekday=5).weekday, 5)

    def test_r5_weekdays_are_accepted_without_saturdays(self):
        for weekday in range(5):
            self.slot(weekday=weekday)


class LifecycleTests(TimetableFixture, TestCase):
    def setUp(self):
        self.build_timetable()

    def test_create_saves_a_validated_slot(self):
        slot = self.slot()
        self.assertIsNotNone(slot.pk)
        self.assertIsNone(slot.end_date)

    def test_end_sets_an_inclusive_end_date_and_keeps_the_row(self):
        slot = self.slot()
        slot.end(date(2026, 9, 30))
        slot.refresh_from_db()
        self.assertEqual(slot.end_date, date(2026, 9, 30))
        self.assertIn(slot, TimetableSlot.objects.effective_on(date(2026, 9, 30)))
        self.assertNotIn(slot, TimetableSlot.objects.effective_on(date(2026, 10, 1)))

    def test_end_cannot_extend_an_ended_slot(self):
        slot = self.slot(end_date=date(2026, 9, 30))
        with self.assertRaises(ValidationError):
            slot.end(date(2026, 10, 31))

    def test_end_before_start_is_rejected(self):
        slot = self.slot(start_date=date(2026, 7, 1))
        with self.assertRaises(ValidationError):
            slot.end(date(2026, 6, 30))

    def test_future_slot_can_be_deleted(self):
        with pin_today():
            slot = self.slot(start_date=date(2026, 10, 19))
            slot.delete()
        self.assertFalse(TimetableSlot.objects.exists())

    def test_started_slot_is_never_deleted_including_start_today(self):
        with pin_today():
            for start in (date(2026, 6, 1), TODAY):
                slot = self.slot(start_date=start, weekday=start.weekday() % 5)
                with self.assertRaises(ValidationError):
                    slot.delete()
                slot.end(TODAY)
                self.assertTrue(TimetableSlot.objects.filter(pk=slot.pk).exists())

    def test_queryset_delete_obeys_the_same_rule(self):
        with pin_today():
            self.slot(start_date=date(2026, 6, 1))
            with self.assertRaises(ValidationError):
                TimetableSlot.objects.all().delete()
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_change_of_started_slot_ends_it_the_day_before_and_starts_a_replacement(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 6, 1))
            new = old.change(effective_from=date(2026, 11, 2), offering=self.sanskrit,
                             section=self.six_b)
        old.refresh_from_db()
        self.assertEqual(old.end_date, date(2026, 11, 1))
        self.assertEqual((new.start_date, new.end_date), (date(2026, 11, 2), None))
        self.assertEqual((new.offering, new.section), (self.sanskrit, self.six_b))
        self.assertEqual(TimetableSlot.objects.count(), 2)  # history preserved

    def test_change_keeps_the_original_end_date_by_default(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 6, 1), end_date=date(2026, 12, 31))
            new = old.change(effective_from=date(2026, 11, 2), weekday=1)
        self.assertEqual(new.end_date, date(2026, 12, 31))
        self.assertEqual(new.weekday, 1)

    def test_change_of_started_slot_cannot_rewrite_its_own_start(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 6, 1))
            for effective_from in (date(2026, 6, 1), date(2026, 5, 1)):
                with self.assertRaises(ValidationError):
                    old.change(effective_from=effective_from, weekday=1)
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_change_after_the_slot_ended_is_rejected(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 6, 1), end_date=date(2026, 9, 30))
            with self.assertRaises(ValidationError):
                old.change(effective_from=date(2026, 11, 2), weekday=1)

    def test_failed_change_rolls_back_the_ending_of_the_old_row(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 6, 1))
            with self.assertRaises(ValidationError):
                old.change(effective_from=date(2026, 11, 2), offering=self.sanskrit)  # 6A: R2
        old.refresh_from_db()
        self.assertIsNone(old.end_date)
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_change_of_future_slot_replaces_it_without_leaving_a_row(self):
        with pin_today():
            old = self.slot(start_date=date(2026, 12, 1))
            new = old.change(effective_from=date(2026, 12, 8), weekday=2)
        self.assertEqual(list(TimetableSlot.objects.all()), [new])
        self.assertEqual((new.weekday, new.start_date), (2, date(2026, 12, 8)))


class TeacherClashTests(TimetableFixture, TestCase):
    """R6: one derived teacher cannot be in two Sections in a period + weekday."""

    def setUp(self):
        self.build_timetable()
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2026, 6, 1))

    def test_same_teacher_two_sections_same_period_and_day_is_blocked(self):
        self.slot(section=self.six_a, offering=self.maths)
        with self.assertRaises(ValidationError) as ctx:
            self.slot(section=self.six_b, offering=self.sanskrit)
        self.assertIn("rao", str(ctx.exception))
        self.assertEqual(TimetableSlot.objects.count(), 1)

    def test_different_period_or_weekday_is_allowed(self):
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit, period=self.p2)
        self.slot(section=self.six_b, offering=self.sanskrit, weekday=1)

    def test_different_teachers_in_the_same_period_are_allowed(self):
        self.clear_assignments(offering=self.sanskrit)
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 6, 1))
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit)

    def test_non_overlapping_slot_dates_are_allowed(self):
        self.slot(end_date=date(2026, 8, 31))
        self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 9, 1))

    def test_shared_final_day_is_a_clash(self):
        self.slot(end_date=date(2026, 8, 31))
        with self.assertRaises(ValidationError):
            self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 8, 31))

    def test_teacher_handover_removes_the_clash_after_the_boundary(self):
        # Rao teaches 6B Sanskrit only until 30 Sep; Iyer from 1 Oct.
        self.clear_assignments(offering=self.sanskrit)
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2026, 6, 1), date(2026, 9, 30))
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 10, 1))
        self.slot(end_date=date(2026, 9, 30), section=self.six_a)  # Rao in 6A to 30 Sep
        # From 1 Oct Rao is no longer 6B's teacher, so 6B in the same cell is fine ...
        self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 10, 1))
        # ... but a 6B slot covering the final shared day is a clash.
        with self.assertRaises(ValidationError):
            self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 6, 1),
                      weekday=0, period=self.p1, end_date=date(2026, 9, 30))

    def test_future_assignment_clash_is_blocked_before_it_takes_effect(self):
        self.clear_assignments(offering=self.sanskrit)
        # Iyer teaches 6B now; Rao takes over from 1 Jan 2027 (planned).
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 6, 1), date(2026, 12, 31))
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2027, 1, 1))
        self.slot()
        with self.assertRaises(ValidationError):
            self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 6, 1))
        # The same cell is fine if the slot ends before the planned hand-over.
        self.slot(section=self.six_b, offering=self.sanskrit, start_date=date(2026, 6, 1),
                  end_date=date(2026, 12, 31))

    def test_unassigned_slot_is_allowed(self):
        self.clear_assignments()
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit)
        self.assertEqual(TimetableSlot.objects.count(), 2)

    def _september_clash(self):
        """Rao in 6A and 6B, P1 Monday: a clash blocked at save, so built raw."""
        TimetableSlot.objects.create(
            period=self.p1, weekday=0, section=self.six_a, offering=self.maths,
            start_date=date(2026, 6, 1), end_date=date(2026, 9, 30),
        )
        TimetableSlot.objects.create(
            period=self.p1, weekday=0, section=self.six_b, offering=self.sanskrit,
            start_date=date(2026, 6, 1), end_date=date(2026, 9, 30),
        )

    def assertSeptemberClashRemains(self):
        report = timetable.find_all_clashes(self.year)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0].teacher, self.rao)
        self.assertEqual((report[0].start, report[0].end), (date(2026, 6, 1), date(2026, 9, 30)))

    def test_historical_clash_survives_the_teacher_being_deactivated(self):
        self._september_clash()
        self.assertSeptemberClashRemains()
        self.rao.is_active = False
        self.rao.save()
        self.assertSeptemberClashRemains()

    def test_historical_clash_survives_removal_from_the_teachers_group(self):
        self._september_clash()
        self.rao.groups.remove(self.teachers)
        self.assertSeptemberClashRemains()

    def test_save_time_check_still_sees_a_former_teachers_assignment(self):
        self.rao.is_active = False
        self.rao.save()
        self.slot()
        with self.assertRaises(ValidationError):
            self.slot(section=self.six_b, offering=self.sanskrit)

    def test_former_teacher_still_has_no_access(self):
        self.rao.is_active = False
        self.rao.save()
        with pin_today(date(2026, 10, 19)):
            self.assertFalse(authorization.can_enter_results(self.rao, self.maths, self.six_a))
            self.assertFalse(authorization.current_teacher_assignments(self.rao).exists())
        self.rao.is_active = True
        self.rao.save()
        self.rao.groups.remove(self.teachers)
        with pin_today(date(2026, 10, 19)):
            self.assertFalse(authorization.can_enter_results(self.rao, self.maths, self.six_a))

    def test_assignment_rows_remain_the_source_of_historical_identity(self):
        self.rao.is_active = False
        self.rao.groups.remove(self.teachers)
        self.rao.save()
        self.assertEqual(
            AssessmentTeacherAssignment.objects.filter(teacher=self.rao).count(), 2
        )
        self._september_clash()
        clash = timetable.find_all_clashes(self.year)[0]
        self.assertEqual(clash.teacher.pk, self.rao.pk)

    def test_change_that_creates_a_clash_is_blocked_and_rolled_back(self):
        with pin_today():
            self.slot(section=self.six_a, offering=self.maths, period=self.p1)
            mover = self.slot(section=self.six_b, offering=self.sanskrit, period=self.p2)
            with self.assertRaises(ValidationError):
                mover.change(effective_from=date(2026, 11, 2), period=self.p1)
        mover.refresh_from_db()
        self.assertIsNone(mover.end_date)

    def test_helper_finds_the_exact_clashing_window(self):
        a = self.slot(end_date=date(2026, 9, 30))
        b = TimetableSlot.objects.create(
            period=self.p1, weekday=0, section=self.six_b, offering=self.sanskrit,
            start_date=date(2026, 9, 15),
        )
        clashes = timetable.find_clashes(b)
        self.assertEqual(len(clashes), 1)
        clash = clashes[0]
        self.assertEqual((clash.teacher, clash.other), (self.rao, a))
        self.assertEqual((clash.start, clash.end), (date(2026, 9, 15), date(2026, 9, 30)))

    def test_year_wide_report_lists_drift_once_per_pair(self):
        self.clear_assignments(offering=self.sanskrit)
        self.assign_from(self.iyer, self.sanskrit, self.six_b, date(2026, 6, 1))
        self.slot()
        self.slot(section=self.six_b, offering=self.sanskrit)
        self.assertEqual(timetable.find_all_clashes(self.year), [])
        # Drift: Rao is assigned to 6B too, bypassing the timetable.
        self.clear_assignments(offering=self.sanskrit)
        self.assign_from(self.rao, self.sanskrit, self.six_b, date(2026, 6, 1))
        report = timetable.find_all_clashes(self.year)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0].teacher, self.rao)


class OfferingScopeProtectionTests(TimetableFixture, TestCase):
    """R7: set_sections cannot drop a Section that has any slot."""

    def setUp(self):
        self.build_timetable()
        self.sanskrit.set_sections([self.six_a, self.six_b])

    def test_current_slot_blocks_dropping_the_section(self):
        self.slot(offering=self.sanskrit, section=self.six_a)
        with self.assertRaisesMessage(ValidationError, "timetable"):
            self.sanskrit.set_sections([self.six_b])
        self.assertTrue(self.sanskrit.applies_to(self.six_a))

    def test_ended_historical_slot_still_blocks(self):
        slot = self.slot(offering=self.sanskrit, section=self.six_a)
        slot.end(date(2026, 8, 31))
        with self.assertRaises(ValidationError):
            self.sanskrit.set_sections([self.six_b])

    def test_sections_without_slots_can_still_be_dropped(self):
        self.slot(offering=self.sanskrit, section=self.six_b)
        self.sanskrit.set_sections([self.six_b])
        self.assertFalse(self.sanskrit.applies_to(self.six_a))

    def test_existing_assignment_protection_is_unchanged(self):
        self.assign_from(self.rao, self.sanskrit, self.six_a, date(2026, 6, 1))
        with self.assertRaisesMessage(ValidationError, "assigned teacher"):
            self.sanskrit.set_sections([self.six_b])

    def test_widening_to_all_sections_is_always_allowed(self):
        self.slot(offering=self.sanskrit, section=self.six_a)
        self.sanskrit.set_sections([])
        self.assertTrue(self.sanskrit.applies_to(self.six_a))


class AuthorizationIndependenceTests(TimetableFixture, TestCase):
    """D7: the timetable grants nothing and removes nothing."""

    def setUp(self):
        self.build_timetable()

    def test_slot_without_assignment_grants_no_access(self):
        self.slot()
        with pin_today(date(2026, 10, 19)):
            self.assertFalse(
                authorization.can_enter_results(self.rao, self.maths, self.six_a)
            )
            self.assertFalse(authorization.current_teacher_assignments(self.rao).exists())

    def test_assignment_without_slot_keeps_access(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        self.assertEqual(TimetableSlot.objects.count(), 0)
        with pin_today(date(2026, 10, 19)):
            self.assertTrue(authorization.can_enter_results(self.rao, self.maths, self.six_a))

    def test_creating_and_ending_slots_changes_no_access(self):
        self.assign_from(self.rao, self.maths, self.six_a, date(2026, 6, 1))
        with pin_today(date(2026, 10, 19)):
            def access():
                return (
                    authorization.can_enter_results(self.rao, self.maths, self.six_a),
                    authorization.can_enter_results(self.iyer, self.maths, self.six_a),
                    sorted(authorization.current_teacher_assignments(self.rao).values_list("pk")),
                )

            before = access()
            slot = self.slot()
            self.assertEqual(access(), before)
            slot.end(date(2026, 10, 19))
            self.assertEqual(access(), before)

    def test_authorization_module_does_not_consult_the_timetable(self):
        import inspect

        source = inspect.getsource(authorization)
        self.assertNotIn("Timetable", source)


@skipUnless(connection.vendor == "postgresql", "needs concurrent writers (PostgreSQL)")
class ConcurrentCreateTests(TimetableFixture, TransactionTestCase):
    """Two simultaneous identical creates: exactly one wins, none corrupts."""

    def setUp(self):
        # A TransactionTestCase flushes the database, and another one may have run first in
        # this worker, deleting the groups the migrations created: make sure they exist.
        for name in ("School Administrators", "Teachers"):
            Group.objects.get_or_create(name=name)
        self.build_timetable()

    def test_concurrent_overlapping_creates_leave_one_row(self):
        outcomes = []
        barrier = threading.Barrier(2)

        def work():
            from django.db import connection as conn

            try:
                barrier.wait()
                self.slot()
                outcomes.append("created")
            except ValidationError:
                outcomes.append("refused")
            finally:
                conn.close()

        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes), ["created", "refused"])
        self.assertEqual(TimetableSlot.objects.count(), 1)



class LockRequestTests(TimetableFixture, TestCase):
    def setUp(self):
        self.build_timetable()

    def test_creation_takes_a_row_lock_on_the_section_and_period(self):
        # On SQLite select_for_update is a no-op, so assert the locks are requested.
        with mock.patch.object(
            type(Section.objects.all()), "select_for_update", autospec=True,
            side_effect=lambda qs, *a, **k: qs,
        ) as locked:
            self.slot()
        self.assertTrue(locked.called)
