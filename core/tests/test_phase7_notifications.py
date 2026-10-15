"""Phase 7 Gate 1: consent, notification outbox and ASSIST sending (ADR 0015)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Guardian,
    GuardianContactConsent,
    NotificationTemplate,
    RelationshipType,
    School,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture

BODY = "Dear parent, {first_name} was absent on {date}. Details: {portal_url}"


class NotificationFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.school = School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST
        )
        self.guardian = Guardian.objects.create(full_name="Ravi Kumar", phone="98765 43210")
        self.asha, _ = self.make_student("Asha Reddy")
        StudentGuardian.objects.create(
            student=self.asha, guardian=self.guardian, relationship_type=RelationshipType.FATHER
        )
        self.template = NotificationTemplate.objects.create(
            key="absence_alert", version=1, body=BODY, approved=True
        )

    def consent(self, status, guardian=None):
        return GuardianContactConsent.objects.create(
            guardian=guardian or self.guardian, status=status,
            source=GuardianContactConsent.Source.PAPER_FORM, recorded_by=self.admin,
        )

    def opt_in(self, guardian=None):
        return self.consent(GuardianContactConsent.Status.OPTED_IN, guardian)

    def opt_out(self, guardian=None):
        return self.consent(GuardianContactConsent.Status.OPTED_OUT, guardian)

    def params(self):
        return {"first_name": "Asha", "date": "12 Oct 2026", "portal_url": "https://erp.example/p/"}


class ModelTests(NotificationFixture, TestCase):
    def test_school_defaults_to_portal_only(self):
        School.objects.all().delete()
        school = School.objects.create(name="Other")
        self.assertEqual(school.notification_channel, School.NotificationMode.PORTAL_ONLY)

    def test_template_accepts_allowed_placeholders(self):
        NotificationTemplate(key="x", version=1, body=BODY).full_clean()

    def test_template_rejects_unknown_placeholder(self):
        template = NotificationTemplate(key="x", version=1, body="Marks: {score}")
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_template_rejects_broken_braces(self):
        with self.assertRaises(ValidationError):
            NotificationTemplate(key="x", version=1, body="Hello {first_name").full_clean()

    def test_consent_history_newest_first(self):
        first = self.opt_in()
        second = self.opt_out()
        self.assertEqual(list(self.guardian.contact_consents.all()), [second, first])
