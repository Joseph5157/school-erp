"""Phase 7 Gate 1: consent, notification outbox and ASSIST sending (ADR 0015)."""

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase

from core.models import (
    Guardian,
    GuardianContactConsent,
    Notification,
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


class HistoryGuardTests(NotificationFixture, TestCase):
    def notification(self, status=Notification.Status.PREPARED):
        return Notification.objects.create(
            guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
            template=self.template, parameters=self.params(),
            channel_mode=School.NotificationMode.ASSIST, status=status,
            idempotency_key=f"t:{status}",
        )

    def refused(self, queryset, **changes):
        with self.assertRaises(DatabaseError), transaction.atomic():
            queryset.update(**changes)

    def test_consent_is_append_only(self):
        consent = self.opt_in()
        rows = GuardianContactConsent.objects.filter(pk=consent.pk)
        self.refused(rows, status="OPTED_OUT")
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()

    def test_template_body_and_approval_are_fixed(self):
        rows = NotificationTemplate.objects.filter(pk=self.template.pk)
        self.refused(rows, body="Changed {first_name}")
        self.refused(rows, approved=False)
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()
        draft = NotificationTemplate.objects.create(key="absence_alert", version=2, body=BODY)
        NotificationTemplate.objects.filter(pk=draft.pk).update(approved=True)

    def test_allowed_transitions(self):
        prepared = self.notification()
        Notification.objects.filter(pk=prepared.pk).update(status="SENT")
        Notification.objects.filter(pk=prepared.pk).update(status="DELIVERED")
        queued = self.notification(Notification.Status.QUEUED)
        Notification.objects.filter(pk=queued.pk).update(attempts=1)
        Notification.objects.filter(pk=queued.pk).update(status="PREPARED")
        Notification.objects.filter(pk=queued.pk).update(status="DISMISSED")

    def test_refused_transitions_and_frozen_states(self):
        sent = self.notification()
        rows = Notification.objects.filter(pk=sent.pk)
        rows.update(status="SENT")
        self.refused(rows, status="PREPARED")
        self.refused(rows, dismiss_reason="late")
        skipped = Notification.objects.filter(pk=self.notification("SKIPPED_NO_CONSENT").pk)
        self.refused(skipped, status="PREPARED")

    def test_notification_content_is_immutable_and_never_deleted(self):
        rows = Notification.objects.filter(pk=self.notification().pk)
        self.refused(rows, parameters={"first_name": "Other"})
        self.refused(rows, idempotency_key="other")
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()
