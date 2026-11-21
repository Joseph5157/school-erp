"""Option A2: consecutive-absence runs (ADR 0026).

Spec: docs/competitive-research/OPTION_A_IMPLEMENTATION_SPEC.md, section 5. A run counts ABSENT
school days backwards from the anchor day (the latest eligible day, with a today-only grace when
today's register is not submitted). Weekends and holidays are skipped. PRESENT, an untaken day
(UNKNOWN), an enrollment gap, the year start and the teacher's scope start stop it. The count
is capped at 30 days; "30+" only when the run could continue past that boundary.

All data here is synthetic and local.
"""

from datetime import date, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core import attendance_insights
from core.models import (
    AcademicEnrollment,
    Applicant,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
    SchoolCalendarDay,
    Student,
)
from core.tests.phase4_fixtures import Phase4Fixture

A = AttendanceStatus.ABSENT
P = AttendanceStatus.PRESENT
Stop = attendance_insights.StopReason

MON = date(2026, 10, 12)  # a Monday inside the 2026-27 year (Jun 2026 - Mar 2027)


def school_days_back(start, n):
    """`n` weekdays ending at `start` (inclusive), newest first. No holidays in the fixture."""
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return days


def patch_today(test):
    for target in ("core.views.business_today", "core.models.business_today",
                   "core.reports.business_today"):
        patcher = mock.patch(target, new=lambda: test.today)
        patcher.start()
        test.addCleanup(patcher.stop)


class RunFixture(Phase4Fixture):
    today = MON

    def setUp(self):
        self.build_phase4()
        patch_today(self)
        self.asha, self.asha_e = self.make_student("Asha")

    def new_student(self, name):
        return Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name=name),
            full_name=name,
        )

    def mark(self, on, statuses, *, submit=True, section=None, year=None):
        """One register for `on` with the given {enrollment: status}; submitted directly."""
        register, _ = AttendanceRegister.objects.get_or_create(
            academic_year=year or self.year, class_grade=self.grade6,
            section=section or self.six_a, date=on,
        )
        for enrollment, status in statuses.items():
            AttendanceEntry.objects.create(
                register=register, academic_enrollment=enrollment, status=status
            )
        if submit:
            AttendanceRegister.objects.filter(pk=register.pk).update(
                status=AttendanceRegister.Status.SUBMITTED, submitted_by=self.admin,
                submitted_at=timezone.now(),
            )
        return register

    def mark_days(self, days, status, enrollment=None, section=None):
        for on in days:
            self.mark(on, {enrollment or self.asha_e: status}, section=section)

    def runs(self, *, threshold=1, lookback=30, scope_start=None, enrollments=None):
        if enrollments is None:
            enrollments = AcademicEnrollment.objects.effective_on(self.today)
        return attendance_insights.absence_runs(
            enrollments, self.today, threshold=threshold, lookback=lookback,
            scope_start=scope_start,
        )

    def run_for(self, student, **kwargs):
        matches = [r for r in self.runs(**kwargs) if r["student_id"] == student.pk]
        self.assertLessEqual(len(matches), 1)
        return matches[0] if matches else None


class EdgeCaseTests(RunFixture, TestCase):
    """Every row of spec 5.6. Day lists are written oldest first, like the spec."""

    def test_a_run_ended_by_a_present_day_is_over(self):
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        self.mark(MON, {self.asha_e: P})
        self.assertIsNone(self.run_for(self.asha))

    def test_present_then_three_absent_days(self):
        self.mark(date(2026, 10, 7), {self.asha_e: P})
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual(run["days"], 3)
        self.assertEqual(run["stopped_by"], Stop.PRESENT)
        self.assertFalse(run["at_least"])
        self.assertEqual(run["first_date"], date(2026, 10, 8))
        self.assertEqual(run["last_date"], MON)
        self.assertEqual(run["as_of"], MON)
        self.assertIsNone(run["unknown_date"])
        self.assertEqual(run["name"], "Asha")
        self.assertEqual(run["class_name"], "Grade 6")
        self.assertEqual(run["section_name"], "A")

    def test_a_weekend_is_skipped(self):
        # Fri 9 Oct and Mon 12 Oct are consecutive school days across Sat and Sun.
        self.mark(date(2026, 10, 7), {self.asha_e: P})
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["first_date"]), (3, date(2026, 10, 8)))

    def test_a_holiday_is_skipped(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 10, 8), is_instructional=False,
            label="Holiday",
        )
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (3, Stop.PRESENT))

    def test_a_not_taken_day_stops_the_count_as_at_least(self):
        self.mark(date(2026, 10, 7), {self.asha_e: A})
        # 8 Oct: no register at all.
        self.mark_days([date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (2, Stop.UNKNOWN))
        self.assertTrue(run["at_least"])
        self.assertEqual(run["unknown_date"], date(2026, 10, 8))

    def test_a_draft_day_is_the_same_as_not_taken(self):
        self.mark(date(2026, 10, 7), {self.asha_e: A})
        self.mark(date(2026, 10, 8), {self.asha_e: A}, submit=False)
        self.mark_days([date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (2, Stop.UNKNOWN))
        self.assertEqual(run["unknown_date"], date(2026, 10, 8))

    def test_a_submitted_register_without_the_students_entry_is_unknown(self):
        _, bala_e = self.make_student("Bala")
        self.mark(date(2026, 10, 7), {self.asha_e: A, bala_e: P})
        self.mark(date(2026, 10, 8), {bala_e: P})  # submitted, no entry for Asha
        self.mark_days([date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (2, Stop.UNKNOWN))
        self.assertEqual(run["unknown_date"], date(2026, 10, 8))

    def test_todays_register_not_taken_counts_from_the_previous_school_day(self):
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (3, Stop.PRESENT))
        self.assertEqual(run["as_of"], date(2026, 10, 9))
        self.assertFalse(run["at_least"])

    def test_todays_draft_register_gets_the_same_grace(self):
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        self.mark(MON, {self.asha_e: A}, submit=False)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["as_of"]), (3, date(2026, 10, 9)))

    def test_todays_register_submitted_present_is_zero(self):
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        self.mark(MON, {self.asha_e: P})
        self.assertIsNone(self.run_for(self.asha))

    def test_an_enrollment_gap_stops_the_run(self):
        """Absences in an earlier enrollment, then a school day with no enrollment."""
        student = self.new_student("Chitra")
        first = student.enroll(academic_year=self.year, class_grade=self.grade6,
                               section=self.six_b, start_date=date(2026, 6, 1))
        AcademicEnrollment.objects.filter(pk=first.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=date(2026, 10, 6))
        second = AcademicEnrollment.objects.create(
            student=student, academic_year=self.year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2026, 10, 8))
        self.mark_days([date(2026, 10, 5), date(2026, 10, 6)], A, enrollment=first,
                       section=self.six_b)
        # 7 Oct: a school day with no enrollment.
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A, enrollment=second)
        run = self.run_for(student)
        self.assertEqual((run["days"], run["stopped_by"]), (3, Stop.ENROLLMENT_GAP))
        self.assertFalse(run["at_least"])

    def test_back_to_back_enrollments_continue_the_run(self):
        student = self.new_student("Devi")
        first = student.enroll(academic_year=self.year, class_grade=self.grade6,
                               section=self.six_b, start_date=date(2026, 6, 1))
        AcademicEnrollment.objects.filter(pk=first.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=date(2026, 10, 7))
        second = AcademicEnrollment.objects.create(
            student=student, academic_year=self.year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2026, 10, 8))
        self.mark(date(2026, 10, 5), {first: P}, section=self.six_b)
        self.mark_days([date(2026, 10, 6), date(2026, 10, 7)], A, enrollment=first,
                       section=self.six_b)
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A, enrollment=second)
        run = self.run_for(student)
        self.assertEqual((run["days"], run["stopped_by"]), (5, Stop.PRESENT))
        self.assertEqual(run["section_name"], "A")  # today's placement

    def test_a_withdrawn_student_is_not_listed(self):
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        AcademicEnrollment.objects.filter(pk=self.asha_e.pk).update(
            status=AcademicEnrollment.Status.COMPLETED, end_date=date(2026, 10, 9))
        self.assertIsNone(self.run_for(self.asha))

    def test_saturday_follows_the_enrollments_own_year(self):
        self.year.saturdays_instructional = True
        self.year.save(update_fields=["saturdays_instructional"])
        # Saturday 10 Oct is a school day this year and was never taken.
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (1, Stop.UNKNOWN))
        self.assertEqual(run["unknown_date"], date(2026, 10, 10))

    def test_a_new_academic_year_stops_at_the_year_start(self):
        """Absences at the end of last year never join this year's run."""
        from core.models import AcademicYear

        old = AcademicYear.objects.create(
            name="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 5, 29))
        student = self.new_student("Esha")
        last_year = AcademicEnrollment.objects.create(
            student=student, academic_year=old, class_grade=self.grade6, section=self.six_a,
            start_date=date(2025, 6, 2), end_date=date(2026, 5, 29),
            status=AcademicEnrollment.Status.COMPLETED)
        this_year = AcademicEnrollment.objects.create(
            student=student, academic_year=self.year, class_grade=self.grade6,
            section=self.six_a, start_date=date(2026, 6, 1))
        self.mark(date(2026, 5, 28), {last_year: A}, year=old)
        self.mark(date(2026, 5, 29), {last_year: A}, year=old)
        self.today = date(2026, 6, 2)
        self.mark_days([date(2026, 6, 1), date(2026, 6, 2)], A, enrollment=this_year)
        run = self.run_for(student)
        self.assertEqual((run["days"], run["stopped_by"]), (2, Stop.YEAR_START))

    def test_future_entries_are_never_counted(self):
        self.mark(date(2026, 10, 8), {self.asha_e: P})
        self.mark_days([date(2026, 10, 9), MON], A)
        self.mark(date(2026, 10, 13), {self.asha_e: A})  # tomorrow
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["last_date"]), (2, MON))


class AnchorTests(RunFixture, TestCase):
    def test_sunday_anchors_on_friday(self):
        self.today = date(2026, 10, 11)
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["as_of"]), (3, date(2026, 10, 9)))

    def test_holiday_today_anchors_on_the_previous_school_day(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=MON, is_instructional=False, label="Holiday")
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["as_of"]), (3, date(2026, 10, 9)))

    def test_sunday_with_fridays_register_never_taken_is_zero(self):
        self.today = date(2026, 10, 11)
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8)], A)
        self.assertIsNone(self.run_for(self.asha))

    def test_grace_is_for_today_only(self):
        """Today not taken and Friday not taken: zero, stopped by UNKNOWN."""
        self.mark_days([date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)], A)
        self.assertIsNone(self.run_for(self.asha))

    def test_today_eligible_and_absent_is_the_anchor(self):
        self.mark(date(2026, 10, 8), {self.asha_e: P})
        self.mark_days([date(2026, 10, 9), MON], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["as_of"], run["last_date"]), (2, MON, MON))


class RecalculationTests(RunFixture, TestCase):
    def test_correcting_an_absence_to_present_shortens_the_run(self):
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), MON], A)
        self.assertEqual(self.run_for(self.asha)["days"], 4)
        entry = AttendanceEntry.objects.get(
            academic_enrollment=self.asha_e, register__date=date(2026, 10, 8))
        entry.record_status_change(P, actor=self.admin, reason="Late arrival recorded")
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (2, Stop.PRESENT))

    def test_correcting_present_to_absent_lengthens_the_run(self):
        self.mark(date(2026, 10, 5), {self.asha_e: P})
        self.mark(date(2026, 10, 6), {self.asha_e: P})
        self.mark_days([date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), MON], A)
        entry = AttendanceEntry.objects.get(
            academic_enrollment=self.asha_e, register__date=date(2026, 10, 6))
        entry.record_status_change(A, actor=self.admin, reason="Marked wrongly")
        self.assertEqual(self.run_for(self.asha)["days"], 5)

    def test_a_day_turned_into_a_holiday_is_skipped_next_time(self):
        self.mark(date(2026, 10, 5), {self.asha_e: P})
        self.mark(date(2026, 10, 6), {self.asha_e: A})
        self.mark(date(2026, 10, 7), {self.asha_e: P})
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A)
        self.assertEqual(self.run_for(self.asha)["days"], 3)
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 10, 7), is_instructional=False,
            label="Declared holiday")
        self.assertEqual(self.run_for(self.asha)["days"], 4)


class ThresholdAndScopeTests(RunFixture, TestCase):
    def test_threshold_filters_shorter_runs(self):
        self.mark(date(2026, 10, 7), {self.asha_e: P})
        self.mark_days([date(2026, 10, 8), date(2026, 10, 9), MON], A)
        self.assertEqual(len(self.runs(threshold=3)), 1)
        self.assertEqual(self.runs(threshold=4), [])

    def test_results_sort_by_days_then_name(self):
        _, bala_e = self.make_student("Bala")
        _, zoya_e = self.make_student("Zoya")
        self.mark(date(2026, 10, 6), {self.asha_e: P, bala_e: P, zoya_e: P})
        self.mark(date(2026, 10, 7), {self.asha_e: P, bala_e: A, zoya_e: P})
        self.mark(date(2026, 10, 8), {self.asha_e: P, bala_e: A, zoya_e: A})
        self.mark(date(2026, 10, 9), {self.asha_e: A, bala_e: A, zoya_e: A})
        self.mark(MON, {self.asha_e: A, bala_e: A, zoya_e: A})
        names = [(r["name"], r["days"]) for r in self.runs(threshold=2)]
        self.assertEqual(names, [("Bala", 4), ("Zoya", 3), ("Asha", 2)])

    def test_scope_start_clips_and_is_always_at_least(self):
        self.mark(date(2026, 10, 5), {self.asha_e: P})
        self.mark_days([date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8),
                        date(2026, 10, 9)], A)
        run = self.run_for(self.asha, scope_start={self.asha_e.pk: date(2026, 10, 7)})
        self.assertEqual((run["days"], run["stopped_by"]), (3, Stop.SCOPE_START))
        self.assertTrue(run["at_least"])
        self.assertEqual(run["first_date"], date(2026, 10, 7))

    def test_scope_start_reached_by_the_run_is_at_least_even_when_short(self):
        """Four ABSENT days back to the scope start: "at least 4", never an exact 4."""
        self.mark_days([date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8),
                        date(2026, 10, 9)], A)
        run = self.run_for(self.asha, scope_start={self.asha_e.pk: date(2026, 10, 6)})
        self.assertEqual((run["days"], run["stopped_by"]), (4, Stop.SCOPE_START))
        self.assertTrue(run["at_least"])

    def test_the_admin_sees_the_whole_run_without_a_scope(self):
        self.mark(date(2026, 10, 5), {self.asha_e: P})
        self.mark_days([date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8),
                        date(2026, 10, 9)], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (4, Stop.PRESENT))
        self.assertFalse(run["at_least"])


class LookbackTests(RunFixture, TestCase):
    """The year starts Mon 1 Jun 2026; 30 school days are 1 Jun .. 10 Jul."""

    def test_thirty_plus_only_when_an_earlier_eligible_day_exists(self):
        self.today = date(2026, 7, 17)
        self.mark_days(school_days_back(self.today, 30), A)  # 8 Jun .. 17 Jul
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (30, Stop.LOOKBACK_LIMIT))
        self.assertTrue(run["at_least"])

    def test_exact_thirty_at_the_year_start(self):
        self.today = date(2026, 7, 10)
        days = school_days_back(self.today, 30)
        self.assertEqual(days[-1], date(2026, 6, 1))
        self.mark_days(days, A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (30, Stop.YEAR_START))
        self.assertFalse(run["at_least"])

    def test_exact_thirty_at_the_enrollment_start(self):
        self.today = date(2026, 7, 17)
        AcademicEnrollment.objects.filter(pk=self.asha_e.pk).update(start_date=date(2026, 6, 8))
        self.mark_days(school_days_back(self.today, 30), A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (30, Stop.ENROLLMENT_GAP))
        self.assertFalse(run["at_least"])

    def test_at_least_thirty_at_the_scope_start(self):
        self.today = date(2026, 7, 17)
        self.mark_days(school_days_back(self.today, 30), A)
        run = self.run_for(self.asha, scope_start={self.asha_e.pk: date(2026, 6, 8)})
        self.assertEqual((run["days"], run["stopped_by"]), (30, Stop.SCOPE_START))
        self.assertTrue(run["at_least"])

    def test_a_shorter_run_at_the_year_start_is_exact(self):
        self.today = date(2026, 6, 3)
        self.mark_days([date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)], A)
        run = self.run_for(self.asha)
        self.assertEqual((run["days"], run["stopped_by"]), (3, Stop.YEAR_START))
        self.assertFalse(run["at_least"])


class QueryCountTests(RunFixture, TestCase):
    """A fixed number of queries whatever the number of candidates (spec 5.3).

    The year bounds, the two calendar queries, the candidates' enrollments (the candidate
    count runs inside it as a subquery) and their entries.
    """

    EXPECTED_QUERIES = 5

    def build(self, count):
        enrollments = [self.make_student(f"Student {i:02d}")[1] for i in range(count)]
        for on in (date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)):
            self.mark(on, {e: A for e in enrollments})

    def test_five_candidates(self):
        self.build(5)
        with self.assertNumQueries(self.EXPECTED_QUERIES):
            rows = self.runs(threshold=3)
        self.assertEqual(len(rows), 5)

    def test_fifty_candidates(self):
        self.build(50)
        with self.assertNumQueries(self.EXPECTED_QUERIES):
            rows = self.runs(threshold=3)
        self.assertEqual(len(rows), 50)
