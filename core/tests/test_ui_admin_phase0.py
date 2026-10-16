from datetime import date
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, AttendanceRegister, AttendanceStatus, Student
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin
from core.tests.test_phase6_access_boundary import REVOKE, BoundaryFixture


class AttendanceListOrderTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_registers_listed_newest_date_first_with_section_tiebreak(self):
        second_section = self.section.__class__.objects.create(
            class_grade=self.class_grade, name="B"
        )
        for day, section in (
            (1, self.section),
            (13, second_section),
            (8, self.section),
            (13, self.section),
        ):
            AttendanceRegister.objects.create(
                academic_year=self.year,
                class_grade=self.class_grade,
                section=section,
                date=date(2026, 9, day),
            )

        response = self.administrator.get(reverse("core:attendance-register-list"))
        actual = [
            (register.date, register.section.name)
            for register in response.context["registers"]
        ]

        self.assertEqual(actual, sorted(actual, key=lambda item: (-item[0].toordinal(), item[1])))


class NotGradedDisplayTests(TestCase):
    @staticmethod
    def render_cells(grade):
        result = SimpleNamespace(
            status="MARKED",
            score=7,
            percentage=70,
            grade=grade,
            pass_fail="PASS",
            assessment=SimpleNamespace(maximum_marks=10),
        )
        return render_to_string("core/_result_cells.html", {"result": result})

    def test_blank_grade_shows_not_graded(self):
        self.assertIn("Not graded", self.render_cells(""))

    def test_real_grade_is_shown_not_placeholder(self):
        html = self.render_cells("A")
        self.assertIn(">A<", html)
        self.assertNotIn("Not graded", html)


class DeactivateStudentTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Asha Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.url = reverse("core:student-status-change", args=[self.student.pk])

    def test_confirm_page_shows_student_and_reason_field(self):
        response = self.administrator.get(
            reverse("core:student-deactivate-confirm", args=[self.student.pk])
        )
        self.assertContains(response, "Asha Rao")
        self.assertContains(response, 'name="reason"')

    def test_post_without_reason_is_rejected_and_student_stays_active(self):
        response = self.administrator.post(
            self.url, {"status": Student.Status.INACTIVE, "reason": "   "}
        )
        self.assertRedirects(
            response,
            reverse("core:student-deactivate-confirm", args=[self.student.pk]),
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        self.assertFalse(self.student.status_changes.exists())

    def test_post_with_reason_deactivates_and_records_audit_row(self):
        self.administrator.post(
            self.url,
            {"status": Student.Status.INACTIVE, "reason": "Left the school"},
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)
        change = self.student.status_changes.get()
        self.assertEqual(
            (change.previous_status, change.new_status, change.reason),
            (Student.Status.ACTIVE, Student.Status.INACTIVE, "Left the school"),
        )
        self.assertEqual(change.changed_by, self.admin_user)

    def test_reactivation_needs_no_reason(self):
        self.administrator.post(
            self.url, {"status": Student.Status.INACTIVE, "reason": "Moved away"}
        )
        self.administrator.post(self.url, {"status": Student.Status.ACTIVE})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)
        self.assertEqual(self.student.status_changes.count(), 2)

    def test_confirm_page_requires_permission(self):
        url = reverse("core:student-deactivate-confirm", args=[self.student.pk])
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        self.assertEqual(self.anonymous.get(url).status_code, 302)

    def test_confirm_page_for_inactive_student_redirects_to_detail(self):
        self.administrator.post(
            self.url, {"status": Student.Status.INACTIVE, "reason": "Moved away"}
        )
        response = self.administrator.get(
            reverse("core:student-deactivate-confirm", args=[self.student.pk])
        )
        self.assertRedirects(
            response, reverse("core:student-detail", args=[self.student.pk])
        )


class DeactivateStudentGuardianReviewTests(BoundaryFixture, TestCase):
    def test_reason_survives_guardian_access_review_round_trip(self):
        url = reverse("core:student-status-change", args=[self.asha.pk])
        reason = "Family moved out of the area"

        page = self.client.post(
            url, {"status": Student.Status.INACTIVE, "reason": reason}
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'name="reason" value="{reason}"')
        self.client.post(
            url,
            {
                "status": Student.Status.INACTIVE,
                "reason": reason,
                "access_review": "1",
                f"decision_{self.asha_grant.pk}": REVOKE,
            },
        )
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.INACTIVE)
        self.assertEqual(self.asha.status_changes.get().reason, reason)


class ApplicantDecisionTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Kumar")
        self.decide_url = reverse(
            "core:applicant-admission-decision", args=[self.applicant.pk]
        )

    def test_confirm_page_for_each_decision(self):
        for decision in (
            Applicant.AdmissionStatus.ACCEPTED,
            Applicant.AdmissionStatus.REJECTED,
        ):
            with self.subTest(decision=decision):
                response = self.administrator.get(
                    reverse(
                        "core:applicant-decision-confirm",
                        args=[self.applicant.pk, decision],
                    )
                )
                self.assertContains(response, "Ravi Kumar")

    def test_confirm_page_unknown_decision_404(self):
        response = self.administrator.get(
            reverse(
                "core:applicant-decision-confirm",
                args=[self.applicant.pk, Applicant.AdmissionStatus.PENDING],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_reject_without_reason_keeps_pending(self):
        self.administrator.post(
            self.decide_url,
            {"decision": Applicant.AdmissionStatus.REJECTED, "reason": ""},
        )
        self.applicant.refresh_from_db()
        self.assertEqual(
            self.applicant.admission_status, Applicant.AdmissionStatus.PENDING
        )

    def test_reject_with_reason_is_stored(self):
        self.administrator.post(
            self.decide_url,
            {"decision": Applicant.AdmissionStatus.REJECTED, "reason": "No seat"},
        )
        self.applicant.refresh_from_db()
        self.assertEqual(
            (
                self.applicant.admission_status,
                self.applicant.admission_decision_reason,
            ),
            (Applicant.AdmissionStatus.REJECTED, "No seat"),
        )

    def test_accept_needs_no_reason(self):
        self.administrator.post(
            self.decide_url, {"decision": Applicant.AdmissionStatus.ACCEPTED}
        )
        self.applicant.refresh_from_db()
        self.assertEqual(
            self.applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED
        )

    def test_second_decision_does_not_change_record_and_does_not_500(self):
        self.administrator.post(
            self.decide_url,
            {"decision": Applicant.AdmissionStatus.REJECTED, "reason": "No seat"},
        )
        response = self.administrator.post(
            self.decide_url,
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
            follow=True,
        )
        self.applicant.refresh_from_db()
        self.assertEqual(
            self.applicant.admission_status, Applicant.AdmissionStatus.REJECTED
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "An admission decision has already been recorded for this Applicant.",
        )

    def test_confirm_page_for_decided_applicant_redirects_to_detail(self):
        self.administrator.post(
            self.decide_url, {"decision": Applicant.AdmissionStatus.ACCEPTED}
        )
        response = self.administrator.get(
            reverse(
                "core:applicant-decision-confirm",
                args=[self.applicant.pk, Applicant.AdmissionStatus.REJECTED],
            )
        )
        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )


class StudentSearchLabelTests(AuthorizationClientsMixin, TestCase):
    def test_search_input_has_label_and_clear_link_when_filtered(self):
        url = reverse("core:student-list")
        plain = self.administrator.get(url)
        self.assertContains(plain, '<label for="student-search"')
        self.assertContains(plain, 'id="student-search"')
        self.assertNotContains(plain, "Clear search")

        filtered = self.administrator.get(url, {"q": "zzz"})
        self.assertContains(filtered, '<label for="student-search"')
        self.assertContains(filtered, "Clear search")


class AttendanceCorrectionCancelTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )

    def test_correction_form_has_cancel_back_to_register(self):
        response = self.administrator.get(
            reverse("core:attendance-entry-correct", args=[self.entry.pk])
        )
        back = reverse(
            "core:attendance-register-detail", args=[self.entry.register_id]
        )
        self.assertContains(response, f'href="{back}"')
        self.assertContains(response, "Cancel")
