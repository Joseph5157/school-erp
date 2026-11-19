import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core import home_today
from core.forms import SchoolForm
from core.models import (
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceRegister,
    ClassGrade,
    School,
    Section,
    SectionClassTeacher,
)
from core.tests.test_admin_overview_analytics import (
    TODAY,
    A,
    MarksFixture,
    P,
)


class RegisterCutoffTests(TestCase):
    def test_default_is_ten_oclock(self):
        school = School.objects.create(name="X")
        self.assertEqual(school.register_cutoff, datetime.time(10, 0))

    def test_falls_back_to_ten_without_a_school(self):
        self.assertEqual(home_today.register_cutoff(), datetime.time(10, 0))

    def test_returns_the_schools_value(self):
        School.objects.create(name="X", register_cutoff=datetime.time(9, 15))
        self.assertEqual(home_today.register_cutoff(), datetime.time(9, 15))

    def test_school_form_saves_the_cutoff(self):
        form = SchoolForm(data={"name": "X", "notification_channel": "PORTAL_ONLY",
                                "register_cutoff": "09:30"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().register_cutoff, datetime.time(9, 30))

    def test_school_form_blank_cutoff_keeps_the_default(self):
        form = SchoolForm(data={"name": "X", "notification_channel": "PORTAL_ONLY",
                                "register_cutoff": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().register_cutoff, datetime.time(10, 0))


IST = timezone.get_default_timezone()
SATURDAY = datetime.date(2026, 7, 18)


def at(hour, minute, on=TODAY):
    return datetime.datetime.combine(on, datetime.time(hour, minute), tzinfo=IST)


class TodayDataFixture(MarksFixture):
    def setUp(self):
        super().setUp()
        self.teacher = get_user_model().objects.create(
            username="mrs.rao", first_name="Asha", last_name="Rao"
        )
        SectionClassTeacher.objects.create(
            teacher=self.teacher, academic_year=self.year, section=self.section,
            start_date=datetime.date(2026, 6, 1),
        )

    def add_section(self, grade_name="Grade 2", name="A"):
        grade, _ = ClassGrade.objects.get_or_create(name=grade_name)
        section = Section.objects.create(class_grade=grade, name=name)
        enrollment = self.enroll_student(f"Kid {grade_name}{name}", grade, section)
        return grade, section, enrollment

    def submit_at(self, register, when):
        AttendanceRegister.objects.filter(pk=register.pk).update(submitted_at=when)


class AttendanceTodayTests(TodayDataFixture, TestCase):
    def test_not_taken_lists_class_and_teacher_in_class_order(self):
        self.add_section("Grade 2")
        rows = home_today.attendance_today(TODAY, can_open_registers=True)["not_taken"]
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1", "Grade 2"])
        self.assertEqual(rows[0]["teacher_name"], "Asha Rao")
        self.assertEqual(rows[0]["section_name"], "A")
        self.assertEqual(rows[1]["teacher_name"], "")

    def test_submitted_section_is_not_listed(self):
        self.add_section("Grade 2")
        self.day(TODAY, {self.s1: P, self.s2: A})
        result = home_today.attendance_today(TODAY, can_open_registers=True)
        self.assertTrue(result["school_day"])
        self.assertEqual([r["class_name"] for r in result["not_taken"]], ["Grade 2"])

    def test_username_used_when_teacher_has_no_name(self):
        self.teacher.first_name = self.teacher.last_name = ""
        self.teacher.save()
        rows = home_today.attendance_today(TODAY, can_open_registers=False)["not_taken"]
        self.assertEqual(rows[0]["teacher_name"], "mrs.rao")

    def test_not_taken_rows_link_only_with_permission(self):
        register = self.day(TODAY, {self.s1: P}, submit=False)
        self.add_section("Grade 2")
        off = home_today.attendance_today(TODAY, can_open_registers=False)["not_taken"]
        self.assertTrue(off)
        self.assertTrue(all(r["url"] is None for r in off))
        on = {r["class_name"]: r for r in
              home_today.attendance_today(TODAY, can_open_registers=True)["not_taken"]}
        self.assertEqual(on["Grade 1"]["url"], f"/attendance/{register.pk}/")
        self.assertEqual(on["Grade 1"]["state"], AttendanceRegister.AttendanceState.DRAFT)
        self.assertEqual(on["Grade 2"]["url"], "/attendance/create/")

    def test_donut_has_only_present_and_absent(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        result = home_today.attendance_today(TODAY, can_open_registers=False)
        self.assertEqual([s["label"] for s in result["donut"]["segments"]], ["Present", "Absent"])
        self.assertEqual((result["present"], result["absent"]), (1, 1))

    def test_donut_is_none_when_nothing_submitted(self):
        self.assertIsNone(home_today.attendance_today(TODAY, can_open_registers=False)["donut"])

    def test_non_school_day_has_no_rows_and_says_so(self):
        result = home_today.attendance_today(SATURDAY, can_open_registers=True)
        self.assertFalse(result["school_day"])
        self.assertEqual(result["not_taken"], [])
        compliance = home_today.register_compliance(
            SATURDAY, at(11, 0, SATURDAY), datetime.time(10, 0)
        )
        self.assertEqual(compliance["missing"], [])
        self.assertEqual(compliance["late"], [])


class RegisterComplianceTests(TodayDataFixture, TestCase):
    CUTOFF = datetime.time(10, 0)

    def test_register_submitted_after_cutoff_is_late(self):
        register = self.day(TODAY, {self.s1: P, self.s2: A})
        self.submit_at(register, at(10, 20))
        result = home_today.register_compliance(TODAY, at(11, 0), self.CUTOFF)
        self.assertEqual([r["class_name"] for r in result["late"]], ["Grade 1"])
        self.assertEqual(result["late"][0]["submitted_at"].hour, 10)
        self.assertEqual(result["missing"], [])

    def test_register_submitted_before_cutoff_is_neither(self):
        register = self.day(TODAY, {self.s1: P, self.s2: A})
        self.submit_at(register, at(9, 30))
        result = home_today.register_compliance(TODAY, at(11, 0), self.CUTOFF)
        self.assertEqual((result["late"], result["missing"]), ([], []))

    def test_before_cutoff_nothing_is_missing(self):
        result = home_today.register_compliance(TODAY, at(9, 15), self.CUTOFF)
        self.assertEqual(result["missing"], [])
        self.assertTrue(result["before_cutoff"])

    def test_after_cutoff_unsubmitted_is_missing(self):
        result = home_today.register_compliance(TODAY, at(10, 1), self.CUTOFF)
        self.assertFalse(result["before_cutoff"])
        self.assertEqual([r["section_name"] for r in result["missing"]], ["A"])
        self.assertEqual(result["missing"][0]["teacher_name"], "Asha Rao")

    def test_cutoff_is_read_from_the_school(self):
        School.objects.create(name="X", register_cutoff=datetime.time(9, 0))
        register = self.day(TODAY, {self.s1: P, self.s2: A})
        self.submit_at(register, at(9, 30))
        result = home_today.register_compliance(TODAY, at(11, 0), home_today.register_cutoff())
        self.assertEqual(len(result["late"]), 1)

    def test_utc_timestamps_are_compared_in_local_time(self):
        register = self.day(TODAY, {self.s1: P, self.s2: A})
        # 04:00 UTC is 09:30 IST, so on time.
        self.submit_at(register, datetime.datetime(2026, 7, 14, 4, 0, tzinfo=datetime.UTC))
        result = home_today.register_compliance(TODAY, at(11, 0), self.CUTOFF)
        self.assertEqual(result["late"], [])

    def test_query_count_does_not_grow_with_sections(self):
        def run():
            with CaptureQueriesContext(connection) as ctx:
                home_today.register_compliance(TODAY, at(11, 0), self.CUTOFF)
                home_today.attendance_today(TODAY, can_open_registers=True)
            return len(ctx)

        self.add_section("Grade 2")
        first = run()
        self.add_section("Grade 3")
        self.add_section("Grade 4")
        self.assertEqual(run(), first)


class OverdueMarksTests(TodayDataFixture, TestCase):
    def draft(self, days_ago, *, name="Unit Test", finalize=False):
        assessment = self.assessment({}, name=name, finalize=finalize)
        Assessment.objects.filter(pk=assessment.pk).update(
            assessment_date=TODAY - datetime.timedelta(days=days_ago)
        )
        return assessment

    def test_overdue_marks_after_15_days_only(self):
        self.draft(15, name="Edge")
        late = self.draft(16, name="Late")
        self.draft(30, name="Done", finalize=True)
        rows = home_today.overdue_marks(TODAY)
        self.assertEqual([r["name"] for r in rows], ["Late"])
        self.assertEqual(rows[0]["days_late"], 1)
        self.assertEqual(rows[0]["subject"], "Mathematics")
        self.assertEqual((rows[0]["class_name"], rows[0]["section_name"]), ("Grade 1", "A"))
        self.assertEqual(rows[0]["url"], None)
        linked = home_today.overdue_marks(TODAY, can_open=True)
        self.assertEqual(linked[0]["url"], f"/assessments/{late.pk}/")
        self.assertEqual(rows[0]["teacher_name"], "")

    def test_overdue_marks_link_only_with_permission(self):
        late = self.draft(20)
        self.assertIsNone(home_today.overdue_marks(TODAY)[0]["url"])
        self.assertIsNone(home_today.overdue_marks(TODAY, can_open=False)[0]["url"])
        self.assertEqual(
            home_today.overdue_marks(TODAY, can_open=True)[0]["url"], f"/assessments/{late.pk}/"
        )

    def test_oldest_first(self):
        self.draft(20, name="Newer")
        self.draft(40, name="Older")
        self.assertEqual([r["name"] for r in home_today.overdue_marks(TODAY)], ["Older", "Newer"])

    def test_overdue_marks_names_the_assigned_teacher(self):
        assessment = self.draft(20)
        AssessmentTeacherAssignment.objects.create(
            teacher=self.teacher, offering=assessment.offering, section=assessment.section,
            start_date=datetime.date(2026, 6, 1),
        )
        rows = home_today.overdue_marks(TODAY)
        self.assertEqual(rows[0]["teacher_name"], "Asha Rao")

    def test_assignment_not_effective_on_the_date_is_ignored(self):
        assessment = self.draft(20)
        AssessmentTeacherAssignment.objects.create(
            teacher=self.teacher, offering=assessment.offering, section=assessment.section,
            start_date=TODAY - datetime.timedelta(days=5),
        )
        self.assertEqual(home_today.overdue_marks(TODAY)[0]["teacher_name"], "")

    def test_query_count_does_not_grow_with_assessments(self):
        self.draft(20, name="One")

        def run():
            with CaptureQueriesContext(connection) as ctx:
                home_today.overdue_marks(TODAY)
            return len(ctx)

        first = run()
        for i in range(3):
            self.draft(25 + i, name=f"More {i}")
        self.assertEqual(run(), first)
