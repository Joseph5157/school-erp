"""Phase 5 Gate 8: the end-to-end teacher workflow journey and hardening."""

from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    Assessment,
    AssessmentTeacherAssignment,
    AttendanceCorrection,
    AttendanceRegister,
    ResultStatus,
    SectionClassTeacher,
    TermRemark,
)
from core.tests.phase4_fixtures import Phase4Fixture


class Clock:
    """A school-local business date shared by views and models."""

    def __init__(self, test, day):
        self.day = day
        for target in ("core.views.business_today", "core.models.business_today"):
            patch = mock.patch(target, new=lambda: self.day)
            patch.start()
            test.addCleanup(patch.stop)


class Phase5AcceptanceJourneyTests(Phase4Fixture, TestCase):
    """Admin assigns class and subject teachers -> teacher home -> teacher
    submits today's attendance -> admin corrects it -> teacher enters marks
    -> admin finalizes -> class teacher writes the remark -> class teacher
    replaced mid-year -> old teacher loses access, history intact -> next
    year's assignments copied conservatively."""

    def setUp(self):
        self.build_phase4()
        self.clock = Clock(self, date(2026, 7, 15))  # a Wednesday
        self.kapoor = self.make_user("kapoor", self.teachers, first_name="Dev",
                                     last_name="Kapoor")
        self.ravi, self.ravi_e = self.make_student("Ravi")
        self.asha, self.asha_e = self.make_student("Asha")
        self.client.login(username="admin", password="pass-12345")
        self.rao_c, self.iyer_c, self.kapoor_c = (
            self.login(name) for name in ("rao", "iyer", "kapoor")
        )

    def login(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_reconciled_phase_5_journey(self):
        # Administrator assigns the class teacher and the subject teacher.
        self.client.post(reverse("core:class-teacher-assign", args=[self.year.pk]),
                         {"section": self.six_a.pk, "teacher": self.rao.pk,
                          "start_date": "2026-06-01"})
        self.client.post(reverse("core:teacher-assignment-create", args=[self.year.pk]),
                         {"teacher": self.iyer.pk, "offering": self.maths.pk,
                          "section": self.six_a.pk})
        overview = self.client.get(reverse("core:academic-year-assignments",
                                           args=[self.year.pk]))
        self.assertEqual(overview.context["class_gaps"], 1)  # 6B has none

        # Teacher home shows today's work and lands after login.
        home = self.rao_c.get(reverse("core:my-home"))
        self.assertContains(home, "Take attendance")

        # The class teacher submits today's attendance.
        attendance = reverse("core:my-attendance", args=[self.six_a.pk])
        self.rao_c.post(attendance, {"action": "open"})
        self.rao_c.post(attendance, {"action": "submit",
                                     f"status_{self.ravi_e.pk}": "ABSENT",
                                     f"status_{self.asha_e.pk}": "PRESENT"})
        register = AttendanceRegister.objects.get(section=self.six_a, date=date(2026, 7, 15))
        self.assertEqual((register.status, register.submitted_by), ("SUBMITTED", self.rao))

        # The teacher cannot change it; the administrator corrects it, audited.
        self.rao_c.post(attendance, {"action": "submit",
                                     f"status_{self.ravi_e.pk}": "PRESENT",
                                     f"status_{self.asha_e.pk}": "PRESENT"})
        entry = register.entries.get(academic_enrollment=self.ravi_e)
        self.assertEqual(entry.status, "ABSENT")
        self.client.post(reverse("core:attendance-entry-correct", args=[entry.pk]),
                         {"status": "PRESENT", "reason": "Arrived late, was present."})
        entry.refresh_from_db()
        self.assertEqual(entry.status, "PRESENT")
        self.assertEqual(AttendanceCorrection.objects.get().corrected_by, self.admin)

        # Subject teacher enters marks; administrator finalizes.
        self.client.post(reverse("core:assessment-create", args=[self.year.pk]),
                         {"term": self.term1.pk, "offering": self.maths.pk,
                          "section": self.six_a.pk, "name": "Unit Test 1",
                          "assessment_date": "2026-07-15", "maximum_marks": "20"})
        assessment = Assessment.objects.get()
        self.assertContains(self.iyer_c.get(reverse("core:my-home")), "Unit Test 1")
        self.iyer_c.post(reverse("core:assessment-marks-entry", args=[assessment.pk]),
                         {f"status_{self.ravi_e.pk}": "MARKED", f"score_{self.ravi_e.pk}": "18",
                          f"status_{self.asha_e.pk}": "ABSENT", f"score_{self.asha_e.pk}": ""})
        self.client.post(reverse("core:assessment-finalize", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertTrue(assessment.is_finalized)

        # Both teachers see the result within their scope.
        rao_profile = self.rao_c.get(reverse("core:my-student-detail", args=[self.ravi.pk]))
        self.assertEqual([r.assessment for r in rao_profile.context["results"]], [assessment])
        self.assertTrue(rao_profile.context["show_guardians"])
        iyer_profile = self.iyer_c.get(reverse("core:my-student-detail", args=[self.ravi.pk]))
        self.assertFalse(iyer_profile.context["show_guardians"])

        # Term 1 ends; the class teacher on its last day writes the remark.
        self.clock.day = date(2026, 10, 5)
        remarks = reverse("core:term-remarks", args=[self.term1.pk])
        self.iyer_c.post(remarks, {"section": self.six_a.pk,
                                   f"remark_{self.ravi.pk}": "Subject teacher"})
        self.assertFalse(TermRemark.objects.exists())
        self.rao_c.post(remarks, {"section": self.six_a.pk,
                                  f"remark_{self.ravi.pk}": "Steady progress."})
        self.assertEqual(TermRemark.objects.get().written_by, self.rao)

        # Mid-year hand-over to Kapoor.
        self.client.post(reverse("core:class-teacher-assign", args=[self.year.pk]),
                         {"section": self.six_a.pk, "teacher": self.kapoor.pk,
                          "start_date": "2026-10-05"})
        rao_row = SectionClassTeacher.objects.get(teacher=self.rao)
        self.assertEqual(rao_row.end_date, date(2026, 10, 4))
        self.assertEqual(self.rao_c.get(attendance).status_code, 403)
        self.assertEqual(
            self.rao_c.get(reverse("core:my-student-detail", args=[self.ravi.pk])).status_code,
            403,
        )
        self.assertEqual(self.kapoor_c.get(attendance).status_code, 200)

        # History is intact: Rao still sees July; Kapoor does not.
        july = reverse("core:my-attendance-register", args=[register.pk])
        self.assertEqual(self.rao_c.get(july).status_code, 200)
        self.assertEqual(self.kapoor_c.get(july).status_code, 403)
        register.refresh_from_db()
        self.assertEqual(register.submitted_by, self.rao)
        card = self.rao_c.get(reverse("core:my-report-card", args=[self.term1.pk, self.ravi.pk]))
        self.assertContains(card, "Steady progress.")
        self.assertEqual(
            self.kapoor_c.get(reverse("core:my-report-card",
                                      args=[self.term1.pk, self.ravi.pk])).status_code,
            403,
        )

        # Rao's effective row is protected: delete refused at app and DB level.
        delete = self.client.post(reverse("core:class-teacher-delete", args=[rao_row.pk]),
                                  follow=True)
        self.assertContains(delete, "end it instead of deleting it")
        self.assertTrue(SectionClassTeacher.objects.filter(pk=rao_row.pk).exists())

        # Next Academic Year: conservative copy.
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        next_maths = AcademicSubjectOffering.objects.create(
            academic_year=next_year, class_grade=self.grade6, subject=self.maths_subject
        )
        copy_url = reverse("core:assignment-copy", args=[next_year.pk])
        preview = self.client.get(copy_url)
        plan = preview.context["plan"]
        self.assertEqual(len(plan["copies"]), 2)
        self.assertIn("Not the class teacher at the end of the source year.",
                      {skip.reason for skip in plan["skips"]})
        self.client.post(copy_url, {"source": self.year.pk, "token": plan["token"]})
        copied = SectionClassTeacher.objects.get(academic_year=next_year)
        self.assertEqual((copied.teacher, copied.start_date), (self.kapoor, date(2027, 6, 1)))
        self.assertTrue(AssessmentTeacherAssignment.objects.filter(
            teacher=self.iyer, offering=next_maths, section=self.six_a).exists())
        # The old open row still ends with its own year.
        kapoor_row = SectionClassTeacher.objects.get(teacher=self.kapoor, academic_year=self.year)
        self.assertIsNone(kapoor_row.end_date)


class ClassTeacherHistoryGuardTests(Phase4Fixture, TestCase):
    """ADR 0011 D3 at the application and database level."""

    def setUp(self):
        self.build_phase4()
        self.clock = Clock(self, date(2026, 7, 15))
        self.row = SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                              section=self.six_a, start_date=date(2026, 6, 1))
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 7, 6), status="SUBMITTED", submitted_by=self.rao,
            submitted_at="2026-07-06T10:00:00+05:30",
        )

    def raw(self, sql, params):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)

    def test_bulk_delete_is_refused(self):
        with self.assertRaises(ValidationError):
            SectionClassTeacher.objects.filter(pk=self.row.pk).delete()
        self.assertTrue(SectionClassTeacher.objects.filter(pk=self.row.pk).exists())

    def test_bulk_delete_of_planned_rows_is_allowed(self):
        planned = SectionClassTeacher.assign(teacher=self.iyer, academic_year=self.year,
                                             section=self.six_b, start_date=date(2026, 11, 1))
        SectionClassTeacher.objects.filter(pk=planned.pk).delete()
        self.assertFalse(SectionClassTeacher.objects.filter(pk=planned.pk).exists())

    def test_database_refuses_deleting_a_row_with_dependents(self):
        with self.assertRaises(IntegrityError):
            self.raw("DELETE FROM core_sectionclassteacher WHERE id = %s", [self.row.pk])
        self.assertTrue(SectionClassTeacher.objects.filter(pk=self.row.pk).exists())

    def test_database_refuses_rewriting_a_row(self):
        for column, value in (("teacher_id", self.iyer.pk), ("section_id", self.six_b.pk),
                              ("start_date", "2026-06-02")):
            with self.subTest(column=column), self.assertRaises(IntegrityError):
                self.raw(f"UPDATE core_sectionclassteacher SET {column} = %s WHERE id = %s",
                         [value, self.row.pk])

    def test_database_refuses_cutting_off_dependents(self):
        with self.assertRaises(IntegrityError):
            self.raw("UPDATE core_sectionclassteacher SET end_date = %s WHERE id = %s",
                     ["2026-07-01", self.row.pk])
        self.row.end(date(2026, 7, 6))
        self.row.refresh_from_db()
        self.assertEqual(self.row.end_date, date(2026, 7, 6))

    def test_planned_row_without_dependents_can_still_be_deleted_in_sql(self):
        planned = SectionClassTeacher.assign(teacher=self.iyer, academic_year=self.year,
                                             section=self.six_b, start_date=date(2026, 11, 1))
        self.raw("DELETE FROM core_sectionclassteacher WHERE id = %s", [planned.pk])
        self.assertFalse(SectionClassTeacher.objects.filter(pk=planned.pk).exists())


class TeacherPageQueryCountTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.clock = Clock(self, date(2026, 7, 15))
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 6, 1))
        self.assign(self.rao, self.maths, self.six_a)
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.client.login(username="admin", password="pass-12345")
        self.students = [self.make_student(f"Student {i:02d}") for i in range(3)]

    def count(self, client, url):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(client.get(url).status_code, 200)
        return len(ctx.captured_queries)

    def finalized_assessment(self, name, students):
        assessment = self.make_assessment(name=name)
        for _, enrollment in students:
            assessment.save_draft_result(enrollment=enrollment, status=ResultStatus.ABSENT,
                                         actor=self.rao)
        self.force_finalize(assessment)

    def test_pages_do_not_grow_with_students(self):
        student = self.students[0][0]
        self.finalized_assessment("UT1", self.students)
        pages = [
            (self.teacher, reverse("core:my-students")),
            (self.teacher, reverse("core:my-student-detail", args=[student.pk])),
            (self.teacher, reverse("core:my-attendance", args=[self.six_a.pk])),
            (self.client, reverse("core:academic-year-assignments", args=[self.year.pk])),
            (self.client, reverse("core:academic-year-class-teachers", args=[self.year.pk])),
        ]
        small = [self.count(client, url) for client, url in pages]
        more = [self.make_student(f"Later {i:02d}") for i in range(6)]
        self.finalized_assessment("UT2", self.students + more)
        self.assign(self.iyer, self.maths, self.six_b)
        large = [self.count(client, url) for client, url in pages]
        self.assertEqual(small, large)
