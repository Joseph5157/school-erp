"""TDB-4A: timetable foundation models, constraints and permissions (ADR 0021)."""

from datetime import date

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import AcademicYear, TimetablePeriod, TimetableSlot
from core.tests.phase4_fixtures import Phase4Fixture

MODEL_NAMES = ["timetableperiod", "timetableslot"]
ACTIONS = ["view", "add", "change", "delete"]


class TimetableFoundationTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.period1 = TimetablePeriod.objects.create(
            academic_year=self.year, sequence=1, label="Period 1"
        )

    def make_slot(self, **overrides):
        values = {
            "period": self.period1,
            "weekday": 0,
            "section": self.six_a,
            "offering": self.maths,
            "start_date": date(2026, 6, 1),
        }
        values.update(overrides)
        return TimetableSlot.objects.create(**values)

    def assertDbRejects(self, **overrides):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_slot(**overrides)

    # --- TimetablePeriod --------------------------------------------------

    def test_period_is_created(self):
        self.assertEqual(self.period1.sequence, 1)
        self.assertEqual(self.period1.label, "Period 1")
        self.assertIsNotNone(self.period1.created_at)

    def test_period_sequence_is_unique_per_academic_year(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TimetablePeriod.objects.create(academic_year=self.year, sequence=1, label="Other")

    def test_period_label_is_unique_per_academic_year(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TimetablePeriod.objects.create(academic_year=self.year, sequence=2, label="Period 1")

    def test_same_sequence_and_label_are_allowed_in_another_year(self):
        other = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        TimetablePeriod.objects.create(academic_year=other, sequence=1, label="Period 1")

    def test_periods_are_ordered_by_year_then_sequence(self):
        second = TimetablePeriod.objects.create(academic_year=self.year, sequence=2, label="P2")
        self.assertEqual(list(TimetablePeriod.objects.all()), [self.period1, second])

    def test_period_sequence_must_be_positive(self):
        period = TimetablePeriod(academic_year=self.year, sequence=0, label="Zero")
        with self.assertRaises(ValidationError):
            period.full_clean()

    def test_period_has_no_clock_time_or_teacher_fields(self):
        names = {f.name for f in TimetablePeriod._meta.get_fields()}
        for forbidden in ("start_time", "end_time", "teacher", "room", "kind"):
            self.assertNotIn(forbidden, names)

    # --- TimetableSlot ----------------------------------------------------

    def test_slot_is_created_with_valid_weekday(self):
        for weekday in range(6):
            slot = self.make_slot(weekday=weekday)
            self.assertEqual(slot.weekday, weekday)

    def test_slot_has_no_teacher_field(self):
        names = {f.name for f in TimetableSlot._meta.get_fields()}
        self.assertNotIn("teacher", names)
        self.assertNotIn("teacher_user", names)

    def test_weekday_outside_zero_to_five_is_rejected_by_database(self):
        self.assertDbRejects(weekday=-1)
        self.assertDbRejects(weekday=6)

    def test_weekday_outside_zero_to_five_fails_model_validation(self):
        slot = TimetableSlot(
            period=self.period1, weekday=6, section=self.six_a, offering=self.maths,
            start_date=date(2026, 6, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            slot.full_clean()
        self.assertIn("weekday", ctx.exception.message_dict)

    def test_end_date_before_start_date_is_rejected(self):
        self.assertDbRejects(start_date=date(2026, 6, 10), end_date=date(2026, 6, 9))

    def test_end_date_equal_to_start_date_is_allowed(self):
        self.make_slot(start_date=date(2026, 6, 10), end_date=date(2026, 6, 10))

    def test_slot_is_unique_per_period_weekday_section_and_start_date(self):
        self.make_slot()
        # A different offering does not make it a different slot.
        self.assertDbRejects(offering=self.sanskrit, section=self.six_a)

    def test_same_cell_with_another_start_date_is_not_blocked_by_the_constraint(self):
        self.make_slot()
        self.make_slot(start_date=date(2026, 7, 1))

    def test_period_referenced_by_a_slot_cannot_be_deleted(self):
        self.make_slot()
        with self.assertRaises(ProtectedError):
            self.period1.delete()

    def test_unreferenced_period_can_be_deleted(self):
        self.period1.delete()
        self.assertFalse(TimetablePeriod.objects.exists())

    # --- effective_on -----------------------------------------------------

    def test_effective_on_includes_start_and_end_dates(self):
        slot = self.make_slot(start_date=date(2026, 6, 10), end_date=date(2026, 6, 20))
        effective = TimetableSlot.objects.effective_on
        self.assertNotIn(slot, effective(date(2026, 6, 9)))
        self.assertIn(slot, effective(date(2026, 6, 10)))
        self.assertIn(slot, effective(date(2026, 6, 15)))
        self.assertIn(slot, effective(date(2026, 6, 20)))
        self.assertNotIn(slot, effective(date(2026, 6, 21)))

    def test_effective_on_runs_a_null_end_date_to_the_academic_year_end(self):
        # ADR 0021 D3: null means the end of the Period's Academic Year, never beyond.
        slot = self.make_slot(start_date=date(2026, 6, 10), end_date=None)
        self.assertIn(slot, TimetableSlot.objects.effective_on(date(2026, 6, 10)))
        self.assertIn(slot, TimetableSlot.objects.effective_on(date(2027, 3, 31)))
        self.assertNotIn(slot, TimetableSlot.objects.effective_on(date(2027, 4, 1)))
        self.assertNotIn(slot, TimetableSlot.objects.effective_on(date(2030, 1, 1)))
        self.assertNotIn(slot, TimetableSlot.objects.effective_on(date(2026, 6, 9)))

    def test_effective_on_accepts_a_datetime(self):
        from datetime import datetime

        slot = self.make_slot(start_date=date(2026, 6, 10))
        self.assertIn(slot, TimetableSlot.objects.effective_on(datetime(2026, 6, 10, 9, 0)))


class TimetablePermissionTests(TestCase):
    def codenames(self, group_name):
        group = Group.objects.get(name=group_name)
        return set(
            group.permissions.filter(content_type__app_label="core").values_list(
                "codename", flat=True
            )
        )

    def test_school_administrators_receive_the_eight_standard_permissions(self):
        expected = {f"{action}_{model}" for model in MODEL_NAMES for action in ACTIONS}
        self.assertEqual(len(expected), 8)
        self.assertLessEqual(expected, self.codenames("School Administrators"))

    def test_no_custom_timetable_permissions_exist(self):
        codenames = set(
            Permission.objects.filter(
                content_type__app_label="core", content_type__model__in=MODEL_NAMES
            ).values_list("codename", flat=True)
        )
        self.assertEqual(codenames, {f"{a}_{m}" for m in MODEL_NAMES for a in ACTIONS})

    def test_teachers_receive_no_timetable_permissions(self):
        held = self.codenames("Teachers")
        self.assertFalse([c for c in held if any(c.endswith(m) for m in MODEL_NAMES)])
