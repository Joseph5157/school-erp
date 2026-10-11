"""Phase 5 Gate 6: teacher result views and class-teacher Term remarks (ADR 0012)."""

from datetime import date
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.authorization import can_write_term_remarks, term_remark_date
from core.models import ResultStatus, SectionClassTeacher, StudentResult, TermRemark
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)


class Gate6Fixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.set_today(TODAY)
        self.asha, self.asha_e = self.make_student("Asha")
        self.rao_client = self.login("rao")
        self.iyer_client = self.login("iyer")

    def set_today(self, day):
        for patch in (mock.patch("core.views.business_today", new=lambda: day),
                      mock.patch("core.models.business_today", new=lambda: day)):
            patch.start()
            self.addCleanup(patch.stop)

    def login(self, username):
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def class_teacher(self, teacher, section, start):
        return SectionClassTeacher.assign(teacher=teacher, academic_year=self.year,
                                          section=section, start_date=start)


class RemarkOwnershipTests(Gate6Fixture, TestCase):
    def test_remark_date(self):
        self.assertEqual(term_remark_date(self.term1), self.term1.end_date)
        self.assertEqual(term_remark_date(self.term2), TODAY)

    def test_remark_date_before_term_starts(self):
        self.set_today(date(2026, 9, 15))
        self.assertEqual(term_remark_date(self.term2), self.term2.start_date)

    def test_subject_teacher_may_no_longer_write(self):
        self.assign(self.iyer, self.maths, self.six_a)
        self.assertFalse(can_write_term_remarks(self.iyer, self.term1, self.six_a))
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.assertEqual(self.iyer_client.get(url, {"section": self.six_a.pk}).status_code, 404)
        self.iyer_client.post(url, {"section": self.six_a.pk,
                                    f"remark_{self.asha.pk}": "Nope"})
        self.assertFalse(TermRemark.objects.exists())

    def test_class_teacher_on_term_end_owns_finished_term(self):
        self.class_teacher(self.rao, self.six_a, date(2026, 6, 1))
        self.class_teacher(self.iyer, self.six_a, date(2026, 10, 1))
        self.assertTrue(can_write_term_remarks(self.rao, self.term1, self.six_a))
        self.assertFalse(can_write_term_remarks(self.iyer, self.term1, self.six_a))
        self.assertTrue(can_write_term_remarks(self.iyer, self.term2, self.six_a))
        self.assertFalse(can_write_term_remarks(self.rao, self.term2, self.six_a))
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.rao_client.post(url, {"section": self.six_a.pk,
                                   f"remark_{self.asha.pk}": "Steady."})
        self.assertEqual(TermRemark.objects.get().written_by, self.rao)

    def test_existing_remarks_are_unchanged(self):
        TermRemark.objects.create(term=self.term1, student=self.asha, remark="Old",
                                  written_by=self.iyer)
        self.assertEqual(TermRemark.objects.get().written_by, self.iyer)

    def test_administrator_keeps_power(self):
        self.assertTrue(can_write_term_remarks(self.admin, self.term1, self.six_a))

    def test_my_assessments_links_remarks_by_class_teacher(self):
        self.assign(self.iyer, self.maths, self.six_a)
        self.class_teacher(self.rao, self.six_a, date(2026, 6, 1))
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.assertContains(self.rao_client.get(reverse("core:my-assessments")), url)
        self.assertNotContains(self.iyer_client.get(reverse("core:my-assessments")), url)


class TeacherResultViewTests(Gate6Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.duty = self.assign(self.iyer, self.maths, self.six_a)
        self.final = self.make_assessment(name="UT1")
        self.draft = self.make_assessment(name="UT2", on=date(2026, 8, 1))
        for assessment in (self.final, self.draft):
            StudentResult.objects.create(assessment=assessment, academic_enrollment=self.asha_e,
                                         status=ResultStatus.MARKED, score=15,
                                         entered_by=self.iyer)
        self.force_finalize(self.final)

    def test_subject_results_show_finalized_only(self):
        self.assertContains(self.iyer_client.get(reverse("core:my-results")), "Mathematics")
        page = self.iyer_client.get(reverse("core:my-subject-results", args=[self.duty.pk]))
        self.assertEqual([a.name for a in page.context["assessments"]], ["UT1"])
        self.assertContains(page, "15")

    def test_term_filter(self):
        url = reverse("core:my-subject-results", args=[self.duty.pk])
        page = self.iyer_client.get(url, {"term": self.term2.pk})
        self.assertEqual(page.context["assessments"], [])
        self.assertEqual(self.iyer_client.get(url, {"term": "x"}).status_code, 200)

    def test_other_teachers_assignment_is_404(self):
        url = reverse("core:my-subject-results", args=[self.duty.pk])
        self.assertEqual(self.rao_client.get(url).status_code, 404)

    def test_class_teacher_report_card(self):
        self.class_teacher(self.rao, self.six_a, date(2026, 6, 1))
        url = reverse("core:my-report-card", args=[self.term1.pk, self.asha.pk])
        page = self.rao_client.get(url)
        self.assertContains(page, "UT1")
        self.assertNotContains(page, "UT2")
        self.assertNotContains(page, reverse("core:report-student-results", args=[self.asha.pk]))
        self.assertEqual(self.iyer_client.get(url).status_code, 403)

    def test_report_card_follows_term_placement(self):
        self.class_teacher(self.rao, self.six_a, date(2026, 6, 1))
        self.asha.enroll(academic_year=self.year, class_grade=self.grade6, section=self.six_b,
                         start_date=date(2026, 9, 1))
        url = reverse("core:my-report-card", args=[self.term1.pk, self.asha.pk])
        self.assertEqual(self.rao_client.get(url).status_code, 403)

    def test_remarks_page_links_report_cards(self):
        self.class_teacher(self.rao, self.six_a, date(2026, 6, 1))
        page = self.rao_client.get(reverse("core:term-remarks", args=[self.term1.pk]),
                                   {"section": self.six_a.pk})
        self.assertContains(page, reverse("core:my-report-card",
                                          args=[self.term1.pk, self.asha.pk]))
