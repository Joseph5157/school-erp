"""Phase 4 Gate 10: the end-to-end assessments journey and hardening checks."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import assessment_reports
from core.models import (
    AcademicEnrollment,
    AcademicSubjectOffering,
    AcademicTerm,
    AcademicYear,
    Applicant,
    Assessment,
    AssessmentTeacherAssignment,
    ClassGrade,
    GradingScale,
    ResultCorrection,
    ResultStatus,
    Section,
    Student,
    StudentResult,
    Subject,
    TermRemark,
)
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()
TODAY = date(2026, 10, 10)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class Phase4AcceptanceJourneyTests(TestCase):
    """Configure Term + Subjects -> assign Subject and teacher -> create
    assessment -> historical roster -> teacher DRAFT MARKED/ABSENT ->
    administrator finalizes -> audited correction -> trustworthy reports,
    without rewriting history after a transfer."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.teacher_user = User.objects.create_user(
            username="rao", password="pass-12345", first_name="Anita", last_name="Rao"
        )
        self.teacher_user.groups.add(Group.objects.get(name="Teachers"))
        self.client.login(username="admin", password="pass-12345")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def student(self, name):
        self.client.post(reverse("core:applicant-create"), {"full_name": name})
        applicant = Applicant.objects.get(full_name=name)
        self.client.post(
            reverse("core:applicant-admission-decision", args=[applicant.pk]),
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
        )
        self.client.post(reverse("core:applicant-progress", args=[applicant.pk]))
        return Student.objects.get(applicant=applicant)

    def enroll(self, student, section, start):
        self.client.post(
            reverse("core:student-enroll", args=[student.pk]),
            {"academic_year": self.year.pk, "class_grade": self.grade.pk,
             "section": section.pk, "start_date": start},
        )
        return AcademicEnrollment.objects.get(student=student, section=section)

    def test_reconciled_phase_4_journey(self):
        # Academic Year, Terms, Subject, offering.
        self.client.post(reverse("core:academic-year-create"),
                         {"name": "2026-27", "start_date": "2026-06-01",
                          "end_date": "2027-03-31"})
        self.year = AcademicYear.objects.get()
        for name, start, end, order in (("Term 1", "2026-06-01", "2026-09-30", 1),
                                        ("Term 2", "2026-10-01", "2026-12-31", 2)):
            self.client.post(reverse("core:term-create", args=[self.year.pk]),
                             {"name": name, "start_date": start, "end_date": end,
                              "display_order": order})
        term1 = AcademicTerm.objects.get(name="Term 1")
        self.client.post(reverse("core:class-grade-create"), {"name": "Grade 6"})
        self.grade = ClassGrade.objects.get()
        for name in ("A", "B"):
            self.client.post(reverse("core:section-create", args=[self.grade.pk]),
                             {"name": name})
        six_a, six_b = Section.objects.get(name="A"), Section.objects.get(name="B")
        self.client.post(reverse("core:subject-create"),
                         {"name": "Mathematics", "code": "math", "is_active": "on"})
        maths_subject = Subject.objects.get()
        self.client.post(reverse("core:offering-create", args=[self.year.pk]),
                         {"class_grade": self.grade.pk, "subject": maths_subject.pk})
        maths = AcademicSubjectOffering.objects.get()
        self.assertEqual(
            list(AcademicSubjectOffering.objects.for_term_section(term1, six_a)), [maths]
        )

        # Grading scale.
        self.client.post(reverse("core:grading-scale-create", args=[self.year.pk]),
                         {"name": "Standard", "class_grades": [self.grade.pk]})
        scale = GradingScale.objects.get()
        for minimum, label in (("90", "A"), ("75", "B"), ("50", "C"), ("0", "D")):
            self.client.post(reverse("core:grade-boundary-create", args=[scale.pk]),
                             {"min_percentage": minimum, "label": label})
        self.assertTrue(scale.is_complete)

        # Teacher assignment for Mathematics 6A and 6B.
        for section in (six_a, six_b):
            self.client.post(reverse("core:teacher-assignment-create", args=[self.year.pk]),
                             {"teacher": self.teacher_user.pk, "offering": maths.pk,
                              "section": section.pk})
        self.assertEqual(AssessmentTeacherAssignment.objects.count(), 2)
        # Phase 5 (ADR 0012 D10): the class teacher writes Term remarks.
        self.client.post(reverse("core:class-teacher-assign", args=[self.year.pk]),
                         {"section": six_a.pk, "teacher": self.teacher_user.pk,
                          "start_date": "2026-06-01"})

        # Students and the assessment.
        ravi, meera, asha = self.student("Ravi Rao"), self.student("Meera Iyer"), \
            self.student("Asha Nair")
        ravi_a = self.enroll(ravi, six_a, "2026-06-01")
        meera_a = self.enroll(meera, six_a, "2026-06-01")
        self.enroll(asha, six_a, "2026-07-20")  # joins after the assessment date
        self.client.post(reverse("core:assessment-create", args=[self.year.pk]),
                         {"term": term1.pk, "offering": maths.pk, "section": six_a.pk,
                          "name": "Unit Test 1", "assessment_date": "2026-07-15",
                          "maximum_marks": "20", "pass_mark": "8"})
        assessment = Assessment.objects.get()

        # Historical roster: Asha joined later, so she is not on it.
        entry_url = reverse("core:assessment-marks-entry", args=[assessment.pk])
        page = self.teacher.get(entry_url)
        self.assertEqual(page.context["form"].enrollments, [meera_a, ravi_a])

        # Teacher enters DRAFT marks for one Student only.
        self.teacher.post(entry_url, {f"status_{ravi_a.pk}": "", f"score_{ravi_a.pk}": "17"})
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, Assessment.Status.DRAFT)

        # Incomplete finalization is rejected.
        detail_url = reverse("core:assessment-detail", args=[assessment.pk])
        self.assertContains(self.client.get(detail_url), "1 Student(s) still have no result.")
        self.client.post(reverse("core:assessment-finalize", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertFalse(assessment.is_finalized)

        # Complete the roster with one ABSENT, then the administrator finalizes.
        self.teacher.post(entry_url, {f"status_{ravi_a.pk}": "MARKED",
                                      f"score_{ravi_a.pk}": "17",
                                      f"status_{meera_a.pk}": "ABSENT",
                                      f"score_{meera_a.pk}": ""})
        self.client.post(reverse("core:assessment-finalize", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertTrue(assessment.is_finalized)
        self.assertEqual(assessment.finalized_by, self.admin)
        self.assertEqual(assessment.grading_snapshot["scale"], "Standard")

        # Teachers can no longer change it.
        self.teacher.post(entry_url, {f"status_{ravi_a.pk}": "MARKED",
                                      f"score_{ravi_a.pk}": "20"})
        ravi_result = StudentResult.objects.get(academic_enrollment=ravi_a)
        self.assertEqual(ravi_result.score, Decimal("17"))
        self.assertEqual(ravi_result.grade, "B")

        # Audited correction updates grading and reports.
        self.client.post(reverse("core:result-correct", args=[ravi_result.pk]),
                         {"status": "MARKED", "score": "19", "reason": "Re-totalled."})
        ravi_result.refresh_from_db()
        self.assertEqual((ravi_result.score, ravi_result.grade), (Decimal("19"), "A"))
        self.assertEqual(ResultCorrection.objects.get().previous_score, Decimal("17"))
        sheet = self.client.get(reverse("core:report-result-sheet", args=[assessment.pk]))
        self.assertContains(sheet, "95.00%")
        self.assertContains(sheet, "Absent")

        # Later scale edit does not touch finalized grades.
        scale.boundaries.filter(label="A").update(min_percentage=96)
        ravi_result.refresh_from_db()
        self.assertEqual(ravi_result.grade, "A")

        # Remark, then Ravi transfers to 6B.
        self.teacher.post(reverse("core:term-remarks", args=[term1.pk]),
                          {"section": six_a.pk, f"remark_{ravi.pk}": "Steady progress."})
        self.enroll(ravi, six_b, "2026-10-01")
        ravi_result.refresh_from_db()
        self.assertEqual(ravi_result.academic_enrollment, ravi_a)
        self.assertEqual(ravi_result.academic_enrollment.section, six_a)

        # Term 1 report card still shows the 6A result and the remark.
        card = self.client.get(reverse("core:report-term-report-card",
                                       args=[ravi.pk, term1.pk]))
        self.assertContains(card, "Mathematics")
        self.assertContains(card, "Unit Test 1")
        self.assertContains(card, "Steady progress.")
        self.assertEqual(card.context["placement"].section, six_a)
        history = assessment_reports.student_history(ravi)
        self.assertEqual([r.academic_enrollment.section for r in history], [six_a])
        self.assertEqual(TermRemark.objects.get().written_by, self.teacher_user)


@mock.patch("core.models.business_today", new=lambda: TODAY)
class Phase4HardeningTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        self.assign(self.rao, self.maths, self.six_a)
        self.students = [self.make_student(f"Student {i:02d}")[1] for i in range(3)]
        self.assessment = self.make_assessment()

    def queries(self, client, url, data=None):
        with CaptureQueriesContext(connection) as ctx:
            response = client.post(url, data) if data is not None else client.get(url)
        self.assertLess(response.status_code, 400)
        return len(ctx.captured_queries)

    def test_bulk_marks_entry_is_all_or_nothing(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        url = reverse("core:assessment-marks-entry", args=[self.assessment.pk])
        data = {f"score_{e.pk}": "10" for e in self.students}
        original = Assessment.save_draft_result
        calls = {"n": 0}

        def flaky(assessment, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                from django.core.exceptions import ValidationError
                raise ValidationError("Simulated failure on the second row.")
            return original(assessment, **kwargs)

        with mock.patch.object(Assessment, "save_draft_result", flaky):
            response = teacher.post(url, data, follow=True)
        self.assertContains(response, "Simulated failure")
        self.assertFalse(StudentResult.objects.exists())

    def test_result_pages_do_not_grow_queries_with_roster(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.client.login(username="admin", password="pass-12345")
        entry = reverse("core:assessment-marks-entry", args=[self.assessment.pk])
        detail = reverse("core:assessment-detail", args=[self.assessment.pk])
        mine = reverse("core:my-assessments")
        for e in self.students:
            self.assessment.save_draft_result(enrollment=e, status=ResultStatus.MARKED,
                                              score="10", actor=self.rao)
        small = [self.queries(teacher, entry), self.queries(self.client, detail),
                 self.queries(teacher, mine)]
        more = [self.make_student(f"Later {i:02d}")[1] for i in range(5)]
        for e in more:
            self.assessment.save_draft_result(enrollment=e, status=ResultStatus.ABSENT,
                                              actor=self.rao)
        self.make_assessment(name="Unit Test 2", on=date(2026, 8, 1))
        large = [self.queries(teacher, entry), self.queries(self.client, detail),
                 self.queries(teacher, mine)]
        self.assertEqual(small, large)
