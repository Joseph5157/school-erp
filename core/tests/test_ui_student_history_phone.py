"""Student history on phones: stacked records, tap links, and the Change placement summary step.

Which layout shows is a Bootstrap breakpoint class, checked in a real browser; these tests pin
what each layout says and that the summary step saves nothing until it is confirmed.
"""

import re
from datetime import date
from decimal import Decimal
from html import unescape
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import views
from core.models import (
    AcademicEnrollment,
    AttendanceRegister,
    ClassGrade,
    ResultStatus,
    Section,
    StudentResult,
    StudentStatusChange,
)
from core.tests.phase4_fixtures import Phase4Fixture


def text_of(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def cards_of(html):
    """The text of each phone record card, tags removed."""
    region = re.search(r'<ul class="erp-record-cards"[^>]*role="list">(.*?)</ul>', html, re.S)
    if region is None:
        return []
    return [text_of(body) for body in re.findall(r"<li[^>]*>(.*?)</li>", region.group(1), re.S)]


def all_cards(html):
    return [
        text_of(body)
        for region in re.findall(r'<ul class="erp-record-cards"[^>]*role="list">(.*?)</ul>', html, re.S)
        for body in re.findall(r"<li[^>]*>(.*?)</li>", region, re.S)
    ]


class HistoryFixture(Phase4Fixture):
    def build_history(self):
        self.build_phase4()
        self.student, self.enrollment = self.make_student("Ravi Rao")
        self.client.force_login(self.admin)


class StackedRecordTests(HistoryFixture, TestCase):
    def setUp(self):
        self.build_history()

    def test_results_enrollment_attendance_status_have_stacked_phone_records(self):
        StudentStatusChange.objects.create(
            student=self.student, previous_status="ACTIVE", new_status="INACTIVE",
            reason="Moved away", changed_by=self.admin,
        )
        assessment = self.make_assessment(name="Unit Test 1")
        StudentResult.objects.create(
            assessment=assessment, academic_enrollment=self.enrollment,
            status=ResultStatus.MARKED, score=Decimal("17"), entered_by=self.rao,
        )
        self.force_finalize(assessment)
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a,
            date=date(2026, 7, 6),
        )
        register.capture(enrollment=self.enrollment, status="ABSENT")
        register.submit(actor=self.admin)

        detail = self.client.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()
        status_card, enrollment_card = all_cards(detail)
        self.assertIn("Active", status_card)
        self.assertIn("Inactive", status_card)
        self.assertIn("Moved away", status_card)
        self.assertIn("2026-27", enrollment_card)
        self.assertIn("Grade 6 - A", enrollment_card)
        self.assertIn("Roll number", enrollment_card)

        results = self.client.get(reverse("core:report-student-results", args=[self.student.pk])).content.decode()
        (result_card,) = cards_of(results)
        self.assertIn("Unit Test 1", result_card)
        self.assertIn("17", result_card)
        self.assertIn("Mathematics", result_card)

        attendance = self.client.get(reverse("core:student-attendance", args=[self.student.pk])).content.decode()
        (attendance_card,) = cards_of(attendance)
        self.assertIn("6 Jul 2026", attendance_card)
        self.assertIn("Absent", attendance_card)
        self.assertIn("Grade 6 - A", attendance_card)

    def test_result_cards_match_the_table_for_absent_and_ungraded(self):
        for name, status, score in (("Marked", ResultStatus.MARKED, Decimal("5")),
                                    ("Away", ResultStatus.ABSENT, None)):
            assessment = self.make_assessment(name=name)
            StudentResult.objects.create(
                assessment=assessment, academic_enrollment=self.enrollment,
                status=status, score=score, entered_by=self.rao,
            )
            self.force_finalize(assessment)
        html = self.client.get(reverse("core:report-student-results", args=[self.student.pk])).content.decode()
        cards = {c.split()[0]: c for c in cards_of(html)}
        self.assertIn("5.00 / 20.00", cards["Marked"])
        self.assertIn("Not graded", cards["Marked"])
        self.assertIn("Absent", cards["Away"])
        self.assertNotIn("%", cards["Away"])
        self.assertNotIn("Pass/Fail", cards["Away"])
        self.assertNotIn("Fail", cards["Away"])

    def test_tables_stay_for_wide_screens_and_cards_hide_on_print(self):
        html = self.client.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()
        self.assertIn('<div class="d-none d-md-block d-print-block">', html)
        self.assertIn('class="d-md-none d-print-none', html)
        self.assertIn('aria-label="Enrollment history"', html)

    def test_empty_histories_say_so_in_the_phone_layout(self):
        student, _ = self.make_student("Meera Rao")
        AcademicEnrollment.objects.filter(student=student).delete()
        html = self.client.get(reverse("core:student-detail", args=[student.pk])).content.decode()
        self.assertEqual(html.count("No enrollments yet."), 2)
        self.assertEqual(html.count("No status changes recorded."), 2)

    def test_contact_details_are_tap_links(self):
        self.student.email = "ravi@example.com"
        self.student.phone = "+91 98765 43210"
        self.student.save()
        html = self.client.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()
        self.assertIn('<a href="mailto:ravi@example.com">ravi@example.com</a>', html)
        self.assertIn('<a href="tel:+91 98765 43210">+91 98765 43210</a>', html)

    def test_missing_contact_details_show_a_dash_not_a_link(self):
        html = self.client.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()
        self.assertNotIn("mailto:", html)
        self.assertNotIn("tel:", html)


class ActionLabelTests(HistoryFixture, TestCase):
    def setUp(self):
        self.build_history()

    def detail(self):
        return self.client.get(reverse("core:student-detail", args=[self.student.pk])).content.decode()

    def test_action_says_change_placement_when_active_enrollment_exists(self):
        html = self.detail()
        self.assertIn(">Change placement</a>", html)
        self.assertNotIn(">Record enrollment</a>", html)
        form = self.client.get(reverse("core:student-enroll", args=[self.student.pk])).content.decode()
        self.assertIn("Change placement", text_of(form))

    def test_action_says_record_enrollment_otherwise(self):
        AcademicEnrollment.objects.filter(student=self.student).delete()
        html = self.detail()
        self.assertIn(">Record enrollment</a>", html)
        self.assertNotIn(">Change placement</a>", html)


class ChangePlacementSummaryTests(HistoryFixture, TestCase):
    def setUp(self):
        self.build_history()
        self.url = reverse("core:student-enroll", args=[self.student.pk])
        self.payload = {
            "academic_year": self.year.pk,
            "class_grade": self.grade6.pk,
            "section": self.six_b.pk,
            "start_date": "2026-08-01",
        }

    def test_change_placement_shows_summary_before_saving(self):
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 200)
        text = text_of(response.content.decode())
        self.assertIn("Grade 6 - A", text)
        self.assertIn("Grade 6 - B", text)
        self.assertIn("Current placement will end on 31 Jul 2026", text)
        self.assertIn("from 1 Aug 2026", text)

    def test_summary_step_saves_nothing_until_confirmed(self):
        self.client.post(self.url, self.payload)
        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 1)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertIsNone(self.enrollment.end_date)

        response = self.client.post(self.url, {**self.payload, "confirm": "1"})
        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(self.enrollment.end_date, date(2026, 7, 31))
        self.assertEqual(self.student.current_enrollment.section, self.six_b)

    def assert_form_with_error_and_no_write(self, response, text):
        self.assertTemplateUsed(response, "core/enrollment_form.html")
        self.assertTemplateNotUsed(response, "core/enrollment_confirm.html")
        self.assertIn(text, text_of(response.content.decode()))
        self.assertNotContains(response, "will end on")
        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 1)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, AcademicEnrollment.Status.ACTIVE)

    def test_same_placement_shows_the_form_with_the_error_not_a_summary(self):
        same = {**self.payload, "section": self.six_a.pk}
        response = self.client.post(self.url, same)
        self.assert_form_with_error_and_no_write(response, "already has an active enrollment")

    def test_start_date_not_after_current_start_shows_the_form_with_the_error(self):
        response = self.client.post(self.url, {**self.payload, "start_date": "2026-06-01"})
        self.assert_form_with_error_and_no_write(response, "must start after")

    def test_future_start_date_shows_the_form_with_the_error(self):
        with mock.patch("core.models.business_today", new=lambda: date(2026, 7, 1)):
            response = self.client.post(self.url, {**self.payload, "start_date": "2026-07-02"})
        self.assert_form_with_error_and_no_write(response, "cannot be in the future")

    def test_second_post_changes_nothing(self):
        self.client.post(self.url, {**self.payload, "confirm": "1"})
        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 2)
        response = self.client.post(self.url, {**self.payload, "confirm": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(list(response.context["messages"]))
        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 2)
        self.assertEqual(self.student.current_enrollment.section, self.six_b)

    def test_confirm_revalidates_the_carried_values(self):
        other = Section.objects.create(class_grade=ClassGrade.objects.create(name="Grade 7"), name="A")
        response = self.client.post(self.url, {**self.payload, "section": other.pk, "confirm": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/enrollment_form.html")
        self.assertEqual(AcademicEnrollment.objects.filter(student=self.student).count(), 1)

    def test_invalid_form_shows_the_form_not_the_summary(self):
        response = self.client.post(self.url, {**self.payload, "start_date": "not a date"})
        self.assertTemplateUsed(response, "core/enrollment_form.html")
        self.assertTemplateNotUsed(response, "core/enrollment_confirm.html")

    def test_back_to_edit_refills_the_form_without_errors(self):
        response = self.client.post(self.url, {**self.payload, "edit": "1"})
        self.assertTemplateUsed(response, "core/enrollment_form.html")
        self.assertContains(response, 'value="2026-08-01"')
        self.assertNotContains(response, "erp-form-errors")

    def test_first_enrollment_has_no_summary_step(self):
        student, _ = self.make_student("Meera Rao")
        AcademicEnrollment.objects.filter(student=student).delete()
        response = self.client.post(reverse("core:student-enroll", args=[student.pk]), self.payload)
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        self.assertEqual(AcademicEnrollment.objects.filter(student=student).count(), 1)

    def test_summary_dict_matches_what_enroll_does(self):
        new = {
            "academic_year": self.year, "class_grade": self.grade6,
            "section": self.six_b, "start_date": date(2026, 8, 1),
        }
        summary = views.placement_change_summary(self.student, new)
        self.assertEqual(summary["current"], self.enrollment)
        self.assertEqual(summary["new"], new)
        self.assertEqual(summary["ends_on"], date(2026, 7, 31))

        self.student.enroll(**new)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.end_date, summary["ends_on"])

    def test_summary_without_a_current_placement_has_no_end_date(self):
        AcademicEnrollment.objects.filter(student=self.student).delete()
        summary = views.placement_change_summary(
            self.student,
            {"academic_year": self.year, "class_grade": self.grade6,
             "section": self.six_b, "start_date": date(2026, 8, 1)},
        )
        self.assertIsNone(summary["current"])
        self.assertIsNone(summary["ends_on"])

