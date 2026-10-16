"""Phase 6 Gate 4: admission and roll numbers; read-only guardian profile (ADR 0014)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core import guardian_access
from core.models import AcademicEnrollment, AcademicYear, Guardian, GuardianAccessReview, Student
from core.tests.test_phase6_access_boundary import BoundaryFixture


class AdmissionNumberTests(BoundaryFixture, TestCase):
    def test_never_generated(self):
        self.assertIsNone(self.asha.admission_number)

    def test_set_trim_and_clear(self):
        self.asha.set_admission_number("  ADM/2026/014 ")
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.admission_number, "ADM/2026/014")
        self.asha.set_admission_number("   ")
        self.asha.refresh_from_db()
        self.assertIsNone(self.asha.admission_number)

    def test_unique_case_insensitively(self):
        self.asha.set_admission_number("adm-1")
        with self.assertRaises(ValidationError):
            self.ravi.set_admission_number("ADM-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.filter(pk=self.ravi.pk).update(admission_number="ADM-1")

    def test_invalid_form_refused(self):
        for value in ("bad number", "#1", "x" * 31, "ādm"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.asha.set_admission_number(value)

    def test_database_refuses_blank(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.objects.filter(pk=self.asha.pk).update(admission_number="")

    def test_admin_view(self):
        url = reverse("core:student-admission-number", args=[self.asha.pk])
        self.assertRedirects(self.client.post(url, {"admission_number": "A-7"}),
                             reverse("core:student-detail", args=[self.asha.pk]))
        self.ravi.set_admission_number("B-1")
        page = self.client.post(reverse("core:student-admission-number", args=[self.ravi.pk]),
                                {"admission_number": "a-7"})
        self.assertContains(page, "already has this admission number")
        self.assertContains(self.client.get(reverse("core:student-detail",
                                                    args=[self.asha.pk])), "A-7")


class RollNumberTests(BoundaryFixture, TestCase):
    def test_unique_within_year_and_section(self):
        self.asha_e.set_roll_number(5)
        other_e = self.make_student("Kiran")[1]
        with self.assertRaises(ValidationError):
            other_e.set_roll_number(5)
        ravi_e = self.ravi.enrollments.get()
        ravi_e.set_roll_number(5)  # 6B: allowed
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicEnrollment.objects.filter(pk=other_e.pk).update(roll_number=5)

    def test_positive_and_clearable(self):
        with self.assertRaises(ValidationError):
            self.asha_e.set_roll_number(0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicEnrollment.objects.filter(pk=self.asha_e.pk).update(roll_number=0)
        self.asha_e.set_roll_number(3)
        self.asha_e.set_roll_number("")
        self.asha_e.refresh_from_db()
        self.assertIsNone(self.asha_e.roll_number)

    def test_belongs_to_the_placement_not_the_student(self):
        self.asha_e.set_roll_number(9)
        self.asha.enroll(academic_year=self.year, class_grade=self.grade6, section=self.six_b,
                         start_date=self.today, actor=self.admin,
                         access_decisions={self.asha_grant.pk: "RETAINED"})
        new = self.asha.enrollments.get(status="ACTIVE")
        self.assertIsNone(new.roll_number)
        self.asha_e.refresh_from_db()
        self.assertEqual(self.asha_e.roll_number, 9)

    def test_admin_view(self):
        url = reverse("core:enrollment-roll-number", args=[self.asha_e.pk])
        self.client.post(url, {"roll_number": "12"})
        self.asha_e.refresh_from_db()
        self.assertEqual(self.asha_e.roll_number, 12)


class GuardianProfileTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.asha.date_of_birth = date(2014, 5, 17)
        self.asha.phone = "98450-00001"
        self.asha.email = "asha@example.com"
        self.asha.save()
        self.asha.set_admission_number("ADM-77")
        self.asha_e.set_roll_number(14)
        other_parent = Guardian.objects.create(full_name="Second Guardian", phone="98450-55555")
        self.relate(self.asha, other_parent)
        self.portal = self.guardian_client()
        self.url = reverse("portal:child", args=[self.asha_grant.public_id])

    def test_shows_exactly_the_approved_fields(self):
        page = self.portal.get(self.url)
        for text in ("Asha Rao", "ADM-77", "2026-27", "Grade 6", "Section", "14", "Active"):
            self.assertContains(page, text)
        self.assertEqual(set(page.context["profile"]),
                         {"name", "admission_number", "placement", "status"})

    def test_never_shows_private_data(self):
        page = self.portal.get(self.url).content.decode()
        for text in ("2014", "17 May", "98450-00001", "asha@example.com", "Second Guardian",
                     "98450-55555", "Meena Rao", f"/students/{self.asha.pk}/",
                     "Date of birth", "Phone", "Email"):
            with self.subTest(text=text):
                self.assertNotIn(text, page)

    def test_missing_values_are_omitted_not_invented(self):
        self.asha.set_admission_number("")
        self.asha_e.set_roll_number(None)
        page = self.portal.get(self.url)
        self.assertNotContains(page, "Admission number")
        self.assertNotContains(page, "Roll number")

    def test_no_current_placement_after_retained_review(self):
        self.today = date(2027, 4, 5)
        guardian_access.decide_date_review(grant=self.asha_grant,
                                           decision=GuardianAccessReview.Decision.RETAINED,
                                           actor=self.admin)
        page = self.portal.get(self.url)
        self.assertIsNone(page.context["profile"]["placement"])
        self.assertContains(page, "None at present")

    def test_shows_current_placement_after_transfer(self):
        self.asha.enroll(academic_year=self.year, class_grade=self.grade6, section=self.six_b,
                         start_date=self.today, actor=self.admin,
                         access_decisions={self.asha_grant.pk: "RETAINED"})
        self.assertEqual(self.portal.get(self.url).context["profile"]["placement"]["section"],
                         "B")

    def test_inactive_status_shown_when_access_retained(self):
        self.asha.record_status_change(Student.Status.INACTIVE, actor=self.admin,
                                       access_decisions={self.asha_grant.pk: "RETAINED"},
                                       reason="Test reason")
        self.assertContains(self.portal.get(self.url), "Inactive")

    def test_read_only(self):
        self.assertEqual(self.portal.post(self.url, {"admission_number": "X"}).status_code, 405)

    def test_next_year_placement(self):
        next_year = AcademicYear.objects.create(name="2027-28", start_date=date(2027, 6, 1),
                                                end_date=date(2028, 3, 31))
        self.today = date(2027, 6, 1)
        self.asha.enroll(academic_year=next_year, class_grade=self.grade6, section=self.six_a,
                         start_date=self.today, actor=self.admin,
                         access_decisions={self.asha_grant.pk: "RETAINED"})
        profile = self.portal.get(self.url).context["profile"]
        self.assertEqual(profile["placement"]["academic_year"], "2027-28")
        self.assertIsNone(profile["placement"]["roll_number"])
