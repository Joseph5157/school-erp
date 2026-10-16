"""Phase 3F (F21): task-count badges in the office sidebar and Overview parity."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import LoginFailure
from core import nav_badges
from core.dashboard import overview_cards
from core.models import Notification, ResultStatus, School
from core.nav_badges import queue_counts
from core.tests.test_authorization import AuthorizationClientsMixin
from core.tests.test_phase6_publication import PublicationFixture
from core.tests.test_phase7_notifications import NotificationFixture

User = get_user_model()

NOTIFICATIONS = "core:notifications-to-send"
LOCKOUTS = "core:login-lockouts"
STALE = "core:publications-stale"
ACCESS_REVIEWS = "core:guardian-access-reviews"
PAGE = "core:student-list"


def badge(number):
    return (
        f'<span class="erp-nav-badge">{number}'
        '<span class="visually-hidden"> waiting</span></span>'
    )


def card(cards, key):
    return next(c for c in cards if c["key"] == key)


def lock(username="meena"):
    for _ in range(5):
        LoginFailure.objects.create(username_key=username, source_key="src")


class QueueFixture(AuthorizationClientsMixin, NotificationFixture):
    def prepare(self, count=1):
        start = Notification.objects.count()
        for i in range(count):
            Notification.objects.create(
                guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
                template=self.template, parameters=self.params(),
                channel_mode=School.NotificationMode.ASSIST,
                status=Notification.Status.PREPARED, idempotency_key=f"badge:{start + i}",
            )

    def page(self):
        return self.administrator.get(reverse(PAGE))


class ZeroStateTests(QueueFixture, TestCase):
    def test_no_badge_markup_when_nothing_is_waiting(self):
        response = self.page()
        self.assertContains(response, reverse(NOTIFICATIONS))
        self.assertNotContains(response, "erp-nav-badge")
        self.assertEqual(queue_counts(self.admin_user), {
            NOTIFICATIONS: 0, LOCKOUTS: 0, STALE: 0,
        })


class NotificationBadgeTests(QueueFixture, TestCase):
    def test_badge_shows_prepared_count_with_hidden_text(self):
        self.prepare(2)
        response = self.page()
        self.assertContains(response, badge(2), count=1)

    def test_overview_card_equals_badge(self):
        self.prepare(2)
        self.assertEqual(queue_counts(self.admin_user)[NOTIFICATIONS], 2)
        data = card(overview_cards(self.admin_user), "notifications")
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["url"], reverse(NOTIFICATIONS))
        self.assertEqual(data["title"], "Messages to send")
        self.assertEqual(data["summary"], "Prepared messages waiting to be sent.")

    def test_counting_does_not_change_rows(self):
        self.prepare(3)  # no consent: to_send() would mark these SKIPPED
        self.page()
        self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(
            Notification.objects.filter(status=Notification.Status.PREPARED).count(), 3
        )
        self.assertFalse(Notification.objects.filter(status="SKIPPED").exists())

    def test_query_budget_is_constant_and_small(self):
        url = reverse(PAGE)
        with mock.patch("core.context_processors.queue_counts", return_value={}):
            with CaptureQueriesContext(connection) as baseline:
                self.administrator.get(url)
        self.prepare(1)
        with CaptureQueriesContext(connection) as one:
            self.administrator.get(url)
        self.prepare(9)
        with CaptureQueriesContext(connection) as ten:
            self.administrator.get(url)
        self.assertEqual(len(one), len(ten))
        self.assertLessEqual(len(one) - len(baseline), 3)
        self.assertGreater(len(one), len(baseline))

    def test_teacher_pages_do_not_compute_counts(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        with mock.patch("core.context_processors.queue_counts") as spy:
            response = teacher.get(reverse("core:my-home"))
        self.assertEqual(response.status_code, 200)
        spy.assert_not_called()
        self.assertNotContains(response, "erp-nav-badge")


class LockoutBadgeTests(QueueFixture, TestCase):
    def test_badge_and_overview_card_show_locked_usernames(self):
        lock("meena")
        response = self.page()
        self.assertContains(response, badge(1), count=1)
        self.assertEqual(queue_counts(self.admin_user)[LOCKOUTS], 1)
        data = card(overview_cards(self.admin_user), "lockouts")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["title"], "Locked sign-ins")
        self.assertEqual(data["summary"], "Usernames locked after failed sign-ins.")
        self.assertEqual(data["url"], reverse(LOCKOUTS))

    def test_count_matches_the_lockouts_page(self):
        lock("meena")
        lock("ravi")
        page = self.administrator.get(reverse(LOCKOUTS))
        self.assertEqual(len(page.context["locked"]), queue_counts(self.admin_user)[LOCKOUTS])

    def test_locked_usernames_is_a_single_query(self):
        from accounts import security

        lock("meena")
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(security.locked_usernames(), ["meena"])
        self.assertEqual(len(ctx), 1)


class StaleBadgeTests(AuthorizationClientsMixin, PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.result.correct(new_status=ResultStatus.MARKED, new_score="17", actor=self.admin,
                            reason="Recount")

    def test_badge_and_overview_card_show_stale_count(self):
        response = self.administrator.get(reverse(PAGE))
        self.assertContains(response, badge(1), count=1)
        self.assertEqual(queue_counts(self.admin_user)[STALE], 1)
        self.assertEqual(card(overview_cards(self.admin_user), "publications")["count"], 1)

    def test_guardian_pages_do_not_compute_counts(self):
        url = reverse("portal:report-cards", args=[self.asha_grant.public_id])
        with mock.patch("core.context_processors.queue_counts") as spy:
            response = self.portal.get(url)
        self.assertEqual(response.status_code, 200)
        spy.assert_not_called()


class PermissionTests(QueueFixture, TestCase):
    def viewer(self, *codenames):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        for codename in codenames:
            user.user_permissions.add(Permission.objects.get(codename=codename))
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        return User.objects.get(pk=user.pk), client

    def test_user_without_permissions_gets_no_keys_links_or_badges(self):
        self.prepare(2)
        lock()
        user, client = self.viewer("view_school")
        self.assertEqual(queue_counts(user), {})
        response = client.get(reverse("core:admin-overview"))
        self.assertNotContains(response, reverse(NOTIFICATIONS))
        self.assertNotContains(response, "erp-nav-badge")

    def test_only_permitted_links_are_counted(self):
        self.prepare(2)
        lock()
        user, client = self.viewer("view_school", "send_notification")
        self.assertEqual(queue_counts(user), {NOTIFICATIONS: 2})
        with mock.patch.object(nav_badges, "locked_username_count") as locked:
            client.get(reverse("core:admin-overview"))
        locked.assert_not_called()

    def test_access_reviews_are_never_counted(self):
        self.assertNotIn(ACCESS_REVIEWS, queue_counts(self.admin_user))
        self.assertNotIn(ACCESS_REVIEWS, queue_counts(self.superuser))
        self.assertContains(self.page(), reverse(ACCESS_REVIEWS))
