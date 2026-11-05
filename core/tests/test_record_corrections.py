"""Correcting an Applicant's or Student's details, with a permanent record of each change."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, RecordCorrection, Student
from core.tests.test_authorization import AuthorizationClientsMixin


def payload(**changes):
    return {
        "full_name": "Asha Rao", "date_of_birth": "2015-03-09", "email": "asha@example.test",
        "phone": "9811111111", "reason": "Spelling on the application form", **changes,
    }


class CorrectionFlowMixin:
    """Subclasses set `edit_name`, `detail_name`, `link_field` and make `self.record`."""

    def setUp(self):
        super().setUp()
        self.record = self.make_record()
        self.url = reverse(self.edit_name, args=[self.record.pk])
        self.detail = reverse(self.detail_name, args=[self.record.pk])

    def corrections(self):
        return RecordCorrection.objects.filter(**{self.link_field: self.record})

    def test_form_opens_with_current_values(self):
        response = self.administrator.get(self.url)
        for value in ("Asha Rao", "2015-03-09", "asha@example.test", "9811111111"):
            self.assertContains(response, f'value="{value}"')

    def test_correction_updates_only_changed_fields_and_records_old_and_new(self):
        response = self.administrator.post(self.url, payload(full_name="Aasha Rao", phone=""))
        self.assertRedirects(response, self.detail)
        self.record.refresh_from_db()
        self.assertEqual(self.record.full_name, "Aasha Rao")
        self.assertEqual(self.record.phone, "")
        correction = self.corrections().get()
        self.assertEqual(correction.changes, [
            {"field": "full_name", "old": "Asha Rao", "new": "Aasha Rao"},
            {"field": "phone", "old": "9811111111", "new": ""},
        ])
        self.assertEqual(correction.reason, "Spelling on the application form")
        self.assertEqual(correction.changed_by, self.admin_user)

    def test_date_of_birth_change_is_recorded_as_a_date(self):
        self.administrator.post(self.url, payload(date_of_birth=""))
        self.assertEqual(
            self.corrections().get().changes,
            [{"field": "date_of_birth", "old": "2015-03-09", "new": ""}],
        )

    def test_reason_is_required(self):
        response = self.administrator.post(self.url, payload(full_name="Aasha Rao", reason="  "))
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.full_name, "Asha Rao")
        self.assertFalse(self.corrections().exists())

    def test_no_change_writes_nothing_and_says_so(self):
        response = self.administrator.post(self.url, payload())
        self.assertContains(response, "Nothing has changed")
        self.assertFalse(self.corrections().exists())

    def test_invalid_values_are_refused(self):
        tomorrow = (date.today() + timedelta(days=2)).isoformat()
        for bad in ({"full_name": ""}, {"email": "not-an-email"}, {"date_of_birth": tomorrow}):
            with self.subTest(bad=bad):
                response = self.administrator.post(self.url, payload(**bad))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(self.corrections().exists())

    def test_form_cannot_change_status_or_other_fields(self):
        before = self.record.__class__.objects.filter(pk=self.record.pk).values().get()
        self.administrator.post(
            self.url,
            payload(full_name="Aasha Rao", admission_status="REJECTED", status="INACTIVE",
                    admission_number="HACK-1"),
        )
        after = self.record.__class__.objects.filter(pk=self.record.pk).values().get()
        for field in ("admission_status", "status", "admission_number"):
            self.assertEqual(before.get(field), after.get(field))

    def test_history_shows_on_the_record_with_who_why_and_values(self):
        self.administrator.post(self.url, payload(full_name="Aasha Rao"))
        response = self.administrator.get(self.detail)
        for text in ("Corrections", "Full name", "Asha Rao", "Aasha Rao",
                     "Spelling on the application form", self.admin_user.username):
            self.assertContains(response, text)

    def test_history_values_are_escaped(self):
        self.administrator.post(self.url, payload(reason="<script>x</script>", phone="1"))
        self.assertNotContains(self.administrator.get(self.detail), "<script>x</script>")

    def test_needs_change_permission(self):
        self.assertEqual(self.non_admin.post(self.url, payload(full_name="X Y")).status_code, 403)
        user = get_user_model().objects.create_user("viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename=f"view_{self.link_field}"))
        client = self.client_class()
        client.force_login(user)
        self.assertNotContains(client.get(self.detail), self.url)
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_details_page_offers_the_correction(self):
        self.assertContains(self.administrator.get(self.detail), self.url)

    def test_history_rows_cannot_be_changed_or_deleted(self):
        self.administrator.post(self.url, payload(full_name="Aasha Rao"))
        correction = self.corrections().get()
        correction.reason = "Rewritten"
        with self.assertRaises(DatabaseError), transaction.atomic():
            correction.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            RecordCorrection.objects.filter(pk=correction.pk).delete()


class ApplicantCorrectionTests(CorrectionFlowMixin, AuthorizationClientsMixin, TestCase):
    edit_name = "core:applicant-edit"
    detail_name = "core:applicant-detail"
    link_field = "applicant"

    def make_record(self):
        return Applicant.objects.create(**self.identity())

    @staticmethod
    def identity():
        return {
            "full_name": "Asha Rao", "date_of_birth": date(2015, 3, 9),
            "email": "asha@example.test", "phone": "9811111111",
        }

    def test_locked_once_a_student_exists_on_every_method(self):
        self.record.admission_status = "ACCEPTED"
        self.record.save()
        Student.objects.create(applicant=self.record, full_name="Asha Rao")
        for response in (
            self.administrator.get(self.url),
            self.administrator.post(self.url, payload(full_name="Aasha Rao")),
        ):
            self.assertRedirects(response, self.detail)
        self.record.refresh_from_db()
        self.assertEqual(self.record.full_name, "Asha Rao")
        self.assertFalse(self.corrections().exists())
        self.assertNotContains(self.administrator.get(self.detail), self.url)

    def test_rejected_applicant_can_still_be_corrected(self):
        self.record.admission_status = "REJECTED"
        self.record.save()
        self.assertRedirects(self.administrator.post(self.url, payload(full_name="Aasha Rao")), self.detail)
        self.record.refresh_from_db()
        self.assertEqual(self.record.admission_status, "REJECTED")
        self.assertEqual(self.record.full_name, "Aasha Rao")

    def test_corrected_values_carry_into_the_student(self):
        self.administrator.post(self.url, payload(full_name="Aasha Rao"))
        self.record.refresh_from_db()
        self.record.admission_status = "ACCEPTED"
        self.record.save()
        self.assertEqual(self.record.progress_to_student().full_name, "Aasha Rao")


class StudentCorrectionTests(CorrectionFlowMixin, AuthorizationClientsMixin, TestCase):
    edit_name = "core:student-edit"
    detail_name = "core:student-detail"
    link_field = "student"

    def make_record(self):
        identity = ApplicantCorrectionTests.identity()
        self.source = Applicant.objects.create(admission_status="ACCEPTED", **identity)
        return Student.objects.create(applicant=self.source, **identity)

    def test_source_applicant_keeps_what_was_recorded_at_application(self):
        self.administrator.post(self.url, payload(full_name="Aasha Rao"))
        self.source.refresh_from_db()
        self.assertEqual(self.source.full_name, "Asha Rao")

    def test_inactive_student_can_still_be_corrected(self):
        Student.objects.filter(pk=self.record.pk).update(status="INACTIVE")
        self.assertRedirects(self.administrator.post(self.url, payload(full_name="Aasha Rao")), self.detail)
