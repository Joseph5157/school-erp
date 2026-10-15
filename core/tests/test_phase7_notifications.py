"""Phase 7 Gate 1: consent, notification outbox and ASSIST sending (ADR 0015)."""

from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse

from core import notifications
from core.models import (
    Guardian,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    RelationshipType,
    School,
    StudentGuardian,
)
from core.navigation import office_nav
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

    def test_template_rejects_positional_nested_and_formatted_fields(self):
        bodies = ("Hi {}", "Hi {0}", "{first_name:{date}}", "{first_name!r}", "{first_name:>10}")
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                NotificationTemplate(key="x", version=1, body=body).full_clean()

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


class ServiceTests(NotificationFixture, TestCase):
    def enqueue(self, subject="2026-10-12", **overrides):
        values = dict(guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
                      template_key="absence_alert", parameters=self.params(), subject=subject)
        values.update(overrides)
        return notifications.enqueue(**values)

    def test_consent_latest_row_wins(self):
        self.assertFalse(notifications.is_opted_in(self.guardian))
        self.opt_in()
        self.assertTrue(notifications.is_opted_in(self.guardian))
        self.opt_out()
        self.assertFalse(notifications.is_opted_in(self.guardian))

    def test_to_send_does_not_skip_message_created_mid_call(self):
        self.opt_in()
        self.enqueue()
        other = Guardian.objects.create(full_name="Sita Rao", phone="98765 00000")
        StudentGuardian.objects.create(
            student=self.asha, guardian=other, relationship_type=RelationshipType.MOTHER
        )
        self.opt_in(other)
        real = notifications._opted_in_ids
        created = []

        def racing(guardian_ids):
            result = real(guardian_ids)
            if not created:
                created.append(self.enqueue(guardian=other))
            return result

        with mock.patch("core.notifications._opted_in_ids", racing):
            listed = list(notifications.to_send())
        late = created[0]
        late.refresh_from_db()
        self.assertEqual(late.status, Notification.Status.PREPARED)
        self.assertIn(late, listed)
        self.assertIn(late, list(notifications.to_send()))

    def test_portal_only_creates_nothing(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.opt_in()
        self.assertIsNone(self.enqueue())
        self.assertFalse(Notification.objects.exists())

    def test_assist_with_consent_prepares(self):
        self.opt_in()
        notification = self.enqueue()
        self.assertEqual(notification.status, Notification.Status.PREPARED)
        self.assertEqual(notification.channel_mode, School.NotificationMode.ASSIST)
        self.assertEqual(
            notification.idempotency_key, f"ABSENCE:{self.guardian.pk}:{self.asha.pk}:2026-10-12"
        )

    def test_without_consent_is_skipped(self):
        self.assertEqual(self.enqueue().status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_same_subject_twice_creates_one(self):
        self.opt_in()
        first = self.enqueue()
        self.assertEqual(self.enqueue(), first)
        self.assertEqual(Notification.objects.count(), 1)

    def test_disallowed_parameter_is_refused(self):
        with self.assertRaises(notifications.NotificationError):
            self.enqueue(parameters={**self.params(), "score": "12"})

    def test_missing_template_is_refused(self):
        with self.assertRaises(notifications.NotificationError):
            self.enqueue(template_key="nope")

    def test_uses_highest_approved_version(self):
        NotificationTemplate.objects.create(
            key="absence_alert", version=3, body=BODY + ".", approved=True
        )
        NotificationTemplate.objects.create(key="absence_alert", version=4, body=BODY + "!")
        self.opt_in()
        self.assertEqual(self.enqueue().template.version, 3)

    def test_render(self):
        self.opt_in()
        self.assertEqual(
            notifications.render(self.enqueue()),
            "Dear parent, Asha was absent on 12 Oct 2026. Details: https://erp.example/p/",
        )

    def test_whatsapp_link_normalises_local_numbers(self):
        self.opt_in()
        notification = self.enqueue()
        for phone in ("98765 43210", "098765-43210", "+91 98765 43210"):
            Guardian.objects.filter(pk=self.guardian.pk).update(phone=phone)
            notification.guardian.refresh_from_db()
            link = notifications.whatsapp_link(notification)
            self.assertTrue(link.startswith("https://wa.me/919876543210?text="), link)

    def test_whatsapp_link_encodes_text(self):
        self.opt_in()
        notification = self.enqueue(parameters={**self.params(), "first_name": "A&B #1?"})
        link = notifications.whatsapp_link(notification)
        self.assertIn("A%26B%20%231%3F", link)
        self.assertNotIn(" ", link)

    def test_whatsapp_link_none_for_unusable_phone(self):
        self.opt_in()
        notification = self.enqueue()
        for phone in ("", "N/A", "12345"):
            Guardian.objects.filter(pk=self.guardian.pk).update(phone=phone)
            notification.guardian.refresh_from_db()
            self.assertIsNone(notifications.whatsapp_link(notification))

    def test_to_send_skips_withdrawn_consent(self):
        self.opt_in()
        notification = self.enqueue()
        self.assertEqual(list(notifications.to_send()), [notification])
        self.opt_out()
        self.assertEqual(list(notifications.to_send()), [])
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_mark_sent(self):
        self.opt_in()
        sent = notifications.mark_sent(self.enqueue(), user=self.admin)
        self.assertEqual(sent.status, Notification.Status.SENT)
        self.assertEqual(sent.marked_sent_by, self.admin)
        self.assertIsNotNone(sent.marked_sent_at)
        with self.assertRaises(notifications.NotificationError):
            notifications.mark_sent(sent, user=self.admin)

    def test_mark_sent_after_opt_out_skips(self):
        self.opt_in()
        notification = self.enqueue()
        self.opt_out()
        result = notifications.mark_sent(notification, user=self.admin)
        self.assertEqual(result.status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_dismiss_needs_reason_and_happens_once(self):
        self.opt_in()
        notification = self.enqueue()
        with self.assertRaises(notifications.NotificationError):
            notifications.dismiss(notification, user=self.admin, reason="  ")
        dismissed = notifications.dismiss(
            notification, user=self.admin, reason="Parent called the school"
        )
        self.assertEqual(dismissed.status, Notification.Status.DISMISSED)
        self.assertEqual(dismissed.dismissed_by, self.admin)
        with self.assertRaises(notifications.NotificationError):
            notifications.dismiss(notification, user=self.admin, reason="again")


class ConsentPageTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.page = reverse("core:guardian-detail", args=[self.guardian.pk])
        self.record = reverse("core:guardian-consent-record", args=[self.guardian.pk])

    def test_admin_group_has_new_permissions(self):
        for perm in ("core.send_notification", "core.view_notification",
                     "core.add_guardiancontactconsent", "core.view_guardiancontactconsent"):
            self.assertTrue(self.admin.has_perm(perm), perm)
        self.assertFalse(self.rao.has_perm("core.send_notification"))

    def test_card_shows_no_consent_then_current_state(self):
        self.assertContains(self.client.get(self.page), "No consent recorded")
        response = self.client.post(
            self.record, {"status": "OPTED_IN", "source": "PAPER_FORM", "note": "Admission form"},
            follow=True,
        )
        self.assertContains(response, "Opted in")
        self.assertContains(response, "Paper form")
        self.assertTrue(notifications.is_opted_in(self.guardian))

    def test_invalid_consent_post_records_nothing(self):
        self.client.post(self.record, {"status": "MAYBE", "source": "PAPER_FORM"})
        self.assertFalse(GuardianContactConsent.objects.exists())

    def test_teacher_cannot_record_consent(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        response = teacher.post(self.record, {"status": "OPTED_IN", "source": "PAPER_FORM"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GuardianContactConsent.objects.exists())

    def test_school_form_offers_two_modes(self):
        response = self.client.get(reverse("core:school-update"))
        self.assertContains(response, 'value="PORTAL_ONLY"')
        self.assertContains(response, 'value="ASSIST"')
        self.assertNotContains(response, 'value="API"')
        self.assertNotContains(response, 'value="SMS"')

    def test_school_form_rejects_api_mode(self):
        self.client.post(reverse("core:school-update"),
                         {"name": "Greenwood High", "notification_channel": "API"})
        self.school.refresh_from_db()
        self.assertEqual(self.school.notification_channel, School.NotificationMode.ASSIST)


class ToSendPageTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:notifications-to-send")
        self.opt_in()
        self.message = notifications.enqueue(
            guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
            template_key="absence_alert", parameters=self.params(), subject="2026-10-12",
        )

    def mark_sent_url(self):
        return reverse("core:notification-mark-sent", args=[self.message.pk])

    def test_lists_prepared_with_send_link(self):
        page = self.client.get(self.url)
        self.assertContains(page, "1 waiting")
        self.assertContains(page, "Ravi Kumar")
        self.assertContains(page, "https://wa.me/919876543210?text=")
        self.assertContains(page, "Asha was absent on 12 Oct 2026")

    def test_mark_sent_and_sent_today(self):
        response = self.client.post(self.mark_sent_url(), follow=True)
        self.assertContains(response, "Marked as sent.")
        self.assertContains(response, "0 waiting")
        self.assertContains(response, "1 sent today")

    def test_mark_sent_after_opt_out_wording(self):
        self.opt_out()
        response = self.client.post(self.mark_sent_url(), follow=True)
        self.assertContains(
            response, "The guardian has opted out, so this message is recorded as not sent."
        )
        self.assertNotContains(response, "the message was not sent")

    def test_mark_sent_twice_is_refused(self):
        self.client.post(self.mark_sent_url())
        response = self.client.post(self.mark_sent_url(), follow=True)
        self.assertContains(response, "no longer waiting to be sent")
        self.assertEqual(Notification.objects.get().marked_sent_by, self.admin)

    def test_dismiss_needs_reason(self):
        url = reverse("core:notification-dismiss", args=[self.message.pk])
        response = self.client.post(url, {"reason": ""}, follow=True)
        self.assertContains(response, "Give a reason")
        self.client.post(url, {"reason": "Parent already informed"})
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.DISMISSED)

    def test_unusable_phone_shows_fix_link(self):
        Guardian.objects.filter(pk=self.guardian.pk).update(phone="N/A")
        page = self.client.get(self.url)
        self.assertContains(page, "Phone number missing or not usable")
        self.assertContains(page, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertNotContains(page, "https://wa.me/")

    def test_portal_only_notice(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertContains(self.client.get(self.url), "WhatsApp messages are switched off")

    def test_empty_state(self):
        notifications.dismiss(self.message, user=self.admin, reason="test")
        self.assertContains(self.client.get(self.url), "Nothing to send.")

    def test_access(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.assertEqual(teacher.get(self.url).status_code, 403)
        self.assertEqual(teacher.post(self.mark_sent_url()).status_code, 403)
        self.assertEqual(self.client_class().get(self.url).status_code, 302)
        self.assertEqual(self.client.get(self.mark_sent_url()).status_code, 405)

    def test_nav_link_for_admin_only(self):
        self.assertContains(self.client.get(self.url), f'href="{self.url}"')
        labels = [link["label"] for group in office_nav(self.rao, "") for link in group["links"]]
        self.assertNotIn("To send", labels)
