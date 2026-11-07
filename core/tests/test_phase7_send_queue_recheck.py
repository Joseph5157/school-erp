"""Security Gate 3B: the send queue rechecks eligibility when shown and when marked sent.

A message is prepared while its guardian can open the portal for the child and has
opted in. Access, the login, the account link or a date-based review can change
afterwards, so the To send page and "mark sent" each decide again from current data.
Showing a message never promises it can still be marked sent.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import announcements, notification_producers, notifications
from core import guardian_accounts as ga
from core.models import (
    Announcement,
    Applicant,
    AttendanceStatus,
    GuardianContactConsent,
    Notification,
    Student,
)
from core.tests.test_phase7_announcements import AnnouncementFixture

PREPARED = Notification.Status.PREPARED
SENT = Notification.Status.SENT
DISMISSED = Notification.Status.DISMISSED
SKIPPED = Notification.Status.SKIPPED_NO_CONSENT
ABSENCE = Notification.Type.ABSENCE
LOST_ACCESS = "Guardian no longer has portal access"


class RecheckFixture(AnnouncementFixture):
    def prepared_alert(self):
        """Meena's absence alert for Asha, prepared while everything is valid."""
        self.register()
        [alert] = [m for m in self.messages() if m.guardian == self.meena]
        self.assertEqual(alert.status, PREPARED)
        return alert

    def prepared_notice_message(self, notice=None):
        announcements.prepare_messages(notice or self.notice())
        message = Notification.objects.get(type=Notification.Type.ANNOUNCEMENT,
                                           guardian=self.meena)
        self.assertEqual(message.status, PREPARED)
        return message

    def shown(self):
        return list(notifications.to_send())

    def fresh(self, notification):
        return Notification.objects.get(pk=notification.pk)

    def withdraw_consent(self):
        self.consent(self.meena, GuardianContactConsent.Status.OPTED_OUT)

    def revoke_grant(self):
        ga.revoke_student_access(grant=self.asha_grant, actor=self.admin, reason="Court order")

    def revoke_account_link(self):
        ga.revoke_account_link(account=self.account, actor=self.admin, reason="Left the school")

    def deactivate_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

    def end_relationship(self):
        ga.end_relationship(link=self.asha_link, actor=self.admin, reason="Moved away")

    def enqueue_for(self, student, name):
        return notifications.enqueue(
            guardian=self.meena, student=student, type=ABSENCE,
            template_key=notification_producers.ABSENCE_TEMPLATE,
            parameters={"first_name": name, "date": "12 Oct 2026",
                        "portal_url": "https://erp.example/p/"},
            subject="2026-10-12",
        )

    def pending_review_message(self):
        """A message for a child whose grant is in the pending date-based review."""
        unplaced = Student.objects.create(
            applicant=Applicant.objects.create(admission_status="ACCEPTED", full_name="Unplaced"),
            full_name="Unplaced",
        )
        grant = ga.grant_student_access(
            student_guardian=self.relate(unplaced, self.meena), actor=self.admin
        )
        self.assertNotIn(grant, notification_producers.portal_grants(unplaced))
        message = self.enqueue_for(unplaced, "Unplaced")
        self.assertEqual(message.status, PREPARED)
        return message

    def assert_removed_when_shown(self, alert):
        self.assertNotIn(alert.pk, [row.pk for row in self.shown()])
        stored = self.fresh(alert)
        self.assertEqual(stored.status, DISMISSED)
        self.assertEqual(stored.dismiss_reason, LOST_ACCESS)
        self.assertIsNone(stored.dismissed_by)
        self.assertIsNone(stored.marked_sent_at)

    def assert_refused_when_marked(self, alert):
        result = notifications.mark_sent(alert, user=self.admin)
        self.assertEqual(result.status, DISMISSED)
        stored = self.fresh(alert)
        self.assertEqual(stored.status, DISMISSED)
        self.assertEqual(stored.dismiss_reason, LOST_ACCESS)
        self.assertIsNone(stored.marked_sent_at)
        self.assertIsNone(stored.marked_sent_by)


class ShownQueueTests(RecheckFixture, TestCase):
    def test_a_message_prepared_while_valid_is_shown(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.assertEqual(self.fresh(alert).status, PREPARED)

    def test_grant_revoked_before_display(self):
        alert = self.prepared_alert()
        self.revoke_grant()
        self.assert_removed_when_shown(alert)

    def test_relationship_ended_before_display(self):
        alert = self.prepared_alert()
        self.end_relationship()
        self.assert_removed_when_shown(alert)

    def test_account_link_revoked_before_display(self):
        alert = self.prepared_alert()
        self.revoke_account_link()
        self.assert_removed_when_shown(alert)

    def test_login_deactivated_before_display(self):
        alert = self.prepared_alert()
        self.deactivate_login()
        self.assert_removed_when_shown(alert)

    def test_pending_review_before_display(self):
        message = self.pending_review_message()
        self.assert_removed_when_shown(message)

    def test_message_for_a_child_never_granted_is_not_shown(self):
        # Ravi is linked to Meena but was never granted access.
        message = self.enqueue_for(self.ravi, "Ravi")
        self.assertEqual(message.status, PREPARED)
        self.assert_removed_when_shown(message)

    def test_lost_access_is_not_recorded_as_missing_consent(self):
        alert = self.prepared_alert()
        self.revoke_grant()
        self.shown()
        self.assertNotEqual(self.fresh(alert).status, SKIPPED)

    def test_consent_withdrawn_before_display(self):
        alert = self.prepared_alert()
        self.withdraw_consent()
        self.assertEqual(self.shown(), [])
        self.assertEqual(self.fresh(alert).status, SKIPPED)

    def test_only_the_stale_message_goes(self):
        self.register(bina=AttendanceStatus.ABSENT)
        by_guardian = {m.guardian: m for m in self.messages()}
        meena_alert, other_alert = by_guardian[self.meena], by_guardian[self.other]
        self.revoke_grant()
        self.assertEqual(self.shown(), [other_alert])
        self.assertEqual(self.fresh(meena_alert).status, DISMISSED)
        self.assertEqual(self.fresh(other_alert).status, PREPARED)

    def test_announcement_message_is_shown_while_the_audience_is_reachable(self):
        message = self.prepared_notice_message()
        self.assertIn(message, self.shown())
        self.assertEqual(self.fresh(message).status, PREPARED)

    def test_announcement_message_goes_when_the_guardian_loses_access(self):
        message = self.prepared_notice_message()
        self.assertIn(message, self.shown())
        self.revoke_grant()
        self.assert_removed_when_shown(message)
        # The other family's message for the same notice is untouched.
        other = Notification.objects.get(type=Notification.Type.ANNOUNCEMENT, guardian=self.other)
        self.assertEqual(self.fresh(other).status, PREPARED)

    def test_announcement_message_goes_when_its_notice_is_withdrawn(self):
        notice = self.notice()
        message = self.prepared_notice_message(notice)
        # A queryset update skips withdraw(), which would dismiss the waiting message.
        Announcement.objects.filter(pk=notice.pk).update(
            withdrawn_at=timezone.now(), withdrawn_by=self.admin, withdrawal_reason="Wrong date"
        )
        self.assertEqual(self.shown(), [])
        self.assertEqual(self.fresh(message).status, DISMISSED)


class MarkSentTests(RecheckFixture, TestCase):
    def test_a_valid_message_can_be_marked_sent(self):
        alert = self.prepared_alert()
        result = notifications.mark_sent(alert, user=self.admin)
        self.assertEqual(result.status, SENT)
        self.assertEqual(result.marked_sent_by, self.admin)
        self.assertIsNotNone(result.marked_sent_at)

    def test_grant_revoked_after_display(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.revoke_grant()
        self.assert_refused_when_marked(alert)

    def test_relationship_ended_after_display(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.end_relationship()
        self.assert_refused_when_marked(alert)

    def test_account_link_revoked_after_display(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.revoke_account_link()
        self.assert_refused_when_marked(alert)

    def test_login_deactivated_after_display(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.deactivate_login()
        self.assert_refused_when_marked(alert)

    def test_pending_review_blocks_marking_sent(self):
        self.assert_refused_when_marked(self.pending_review_message())

    def test_consent_withdrawn_after_display(self):
        alert = self.prepared_alert()
        self.assertEqual(self.shown(), [alert])
        self.withdraw_consent()
        result = notifications.mark_sent(alert, user=self.admin)
        self.assertEqual(result.status, SKIPPED)
        self.assertIsNone(self.fresh(alert).marked_sent_at)

    def test_marking_sent_decides_again_even_if_the_queue_was_never_loaded(self):
        alert = self.prepared_alert()
        self.revoke_grant()
        self.assert_refused_when_marked(alert)

    def test_the_decision_uses_current_data_not_the_displayed_object(self):
        alert = self.prepared_alert()
        [displayed] = self.shown()
        self.assertEqual(displayed.status, PREPARED)
        self.revoke_grant()
        result = notifications.mark_sent(displayed, user=self.admin)  # stale instance
        self.assertNotEqual(result.status, SENT)
        self.assertEqual(self.fresh(alert).status, DISMISSED)

    def test_announcement_message_after_access_is_lost(self):
        message = self.prepared_notice_message()
        self.assertIn(message, self.shown())
        self.revoke_grant()
        self.assert_refused_when_marked(message)

    def test_a_refused_message_cannot_be_marked_sent_afterwards(self):
        alert = self.prepared_alert()
        self.revoke_grant()
        notifications.mark_sent(alert, user=self.admin)
        with self.assertRaises(notifications.NotificationError):
            notifications.mark_sent(alert, user=self.admin)
        self.assertEqual(self.fresh(alert).status, DISMISSED)


class MarkSentViewTests(RecheckFixture, TestCase):
    def post(self, notification):
        return self.client.post(
            reverse("core:notification-mark-sent", args=[notification.pk]), follow=True
        )

    def test_view_marks_a_still_valid_message_sent(self):
        alert = self.prepared_alert()
        self.assertContains(self.post(alert), "Marked as sent.")
        self.assertEqual(self.fresh(alert).status, SENT)

    def test_view_explains_lost_access_and_records_nothing_as_sent(self):
        alert = self.prepared_alert()
        self.client.get(reverse("core:notifications-to-send"))  # shown while eligible
        self.revoke_grant()
        page = self.post(alert)
        self.assertNotContains(page, "Marked as sent.")
        self.assertContains(page, "no longer has portal access")
        stored = self.fresh(alert)
        self.assertEqual(stored.status, DISMISSED)
        self.assertIsNone(stored.marked_sent_at)
        self.assertEqual(list(page.context["sent_today"]), [])

    def test_to_send_page_does_not_list_a_message_whose_access_was_revoked(self):
        alert = self.prepared_alert()
        self.revoke_grant()
        page = self.client.get(reverse("core:notifications-to-send"))
        self.assertEqual([row["notification"] for row in page.context["rows"]], [])
        self.assertEqual(self.fresh(alert).status, DISMISSED)
