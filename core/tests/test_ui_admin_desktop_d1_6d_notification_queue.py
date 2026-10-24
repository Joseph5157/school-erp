"""UI-D1-6D: the To send notification queue (presentation only).

The ERP never sends a message: the page shows prepared messages, a click-to-chat link and the Mark as sent
and Dismiss POSTs. These tests prove the message text is displayed exactly and escaped, every control and
state is unchanged, and the page adds no sending behaviour.
"""

import re
from html import escape
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from core import announcements, notifications
from core.breadcrumbs import breadcrumb_context
from core.models import Guardian, GuardianContactConsent, Notification, School, Student
from core.tests.test_phase7_alerts import AlertFixture

User = get_user_model()
ACTIVE_LINK = r'<a class="nav-link active" href="([^"]+)"'
URL = reverse("core:notifications-to-send")
TEMPLATE = "core/notifications_to_send.html"


def html(response):
    return response.content.decode()


def queue_section(page):
    """The 'Waiting to send' panel only (no sidebar or header text)."""
    return page.split('aria-labelledby="queue-heading"', 1)[1].split('aria-labelledby="sent-heading"')[0]


class Base(AlertFixture):
    def setUp(self):
        super().setUp()
        Guardian.objects.update(phone="98765 43210")                       # synthetic, usable number

    def client_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._viewers}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def teacher(self):
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        return client

    def statuses(self):
        return list(Notification.objects.order_by("pk").values_list(
            "pk", "status", "marked_sent_by_id", "dismissed_by_id"))

    def more_types(self):
        """A published report card (RESULT_PUBLISHED) and an announcement (no student), via the real services."""
        self.publish()
        notice = announcements.publish(title="Sports Day", body="Sports Day is on 20 October.",
                                       audience="ALL", class_grade=None, section=None, actor=self.admin)
        announcements.prepare_messages(notice)

    def every_type(self):
        self.register()                                   # ABSENCE
        self.more_types()
        return list(notifications.to_send())

    def query_count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(URL)
        return len(ctx)


class PageTests(Base, TestCase):
    def test_empty_state_header_and_legacy_text(self):
        page = html(self.client.get(URL))
        self.assertRegex(page, r'<h1 class="erp-page-title">To send</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn("0 waiting · 0 sent today", page)
        self.assertIn("Nothing to send.", page)
        self.assertIn("Messages appear here when the school prepares them.", page)
        self.assertNotIn("Sent today</h2>", page)
        self.assertIn("The ERP never sends messages itself.", page)

    def test_every_notification_type_shows_guardian_type_prepared_time_and_status(self):
        queue = self.every_type()
        self.assertEqual({n.type for n in queue},
                         {Notification.Type.ABSENCE, Notification.Type.RESULT_PUBLISHED,
                          Notification.Type.ANNOUNCEMENT})
        response = self.client.get(URL)
        page = html(response)
        self.assertIn(f"{len(queue)} waiting · 0 sent today", page)
        self.assertEqual(len(response.context["rows"]), len(queue))
        body = queue_section(page)
        for n in queue:
            with self.subTest(type=n.type, pk=n.pk):
                self.assertIn(n.guardian.full_name, body)
                self.assertIn(n.get_type_display(), body)
        self.assertIn("School notice", body)                       # the announcement has no student
        self.assertIn("Ready to send", body)
        self.assertEqual(body.count("prepared "), len(queue))
        self.assertEqual(body.count('<li class="erp-queue-row">'), len(queue))

    def test_text_is_exactly_the_service_text_for_every_type_and_leaks_nothing_restricted(self):
        queue = self.every_type()
        page = html(self.client.get(URL))
        for n in queue:
            with self.subTest(type=n.type):
                text = notifications.render(n)
                self.assertIn(
                    f'<blockquote class="erp-queue-text" aria-label="Message text">{escape(text)}</blockquote>', page)
        quoted = "".join(re.findall(r"<blockquote.*?</blockquote>", queue_section(page), re.S))
        for restricted in ("UT1", "15.00", "Steady progress", "Recount", "Mathematics"):
            self.assertNotIn(restricted, quoted)

    def test_hostile_characters_are_escaped_and_not_altered(self):
        name = '<i>"A&B\'s</i>'
        Student.objects.filter(pk=self.asha.pk).update(full_name=f"{name} Rao")
        self.asha.refresh_from_db()
        self.register()
        [message] = [n for n in notifications.to_send() if n.type == Notification.Type.ABSENCE]
        text = notifications.render(message)
        self.assertIn("<i>", text)                                   # the service text is raw
        page = html(self.client.get(URL))
        self.assertIn(escape(text), page)
        self.assertNotIn("<i>", page)
        self.assertNotIn(name, page)
        self.assertIn("&lt;i&gt;", page)
        self.assertIn("&amp;", page)
        self.assertIn("&quot;", page)
        self.assertTrue("&#x27;" in page or "&#39;" in page)

    def test_template_never_disables_escaping_or_truncates(self):
        source = (Path("core/templates") / TEMPLATE).read_text(encoding="utf-8")
        for forbidden in ("|safe", "mark_safe", "autoescape off", "truncate", "|striptags", "|escape"):
            self.assertNotIn(forbidden, source)

    def test_send_link_keeps_href_target_and_rel(self):
        self.register()
        [message] = list(notifications.to_send())
        link = notifications.whatsapp_link(message)
        page = html(self.client.get(URL))
        self.assertIn(
            f'<a class="btn btn-success" href="{escape(link)}" target="_blank" rel="noopener">Send on WhatsApp', page)
        self.assertIn(
            f'Send on WhatsApp<span class="visually-hidden"> to {message.guardian.full_name} (opens in a new tab)</span>',
            page)

    def test_controls_keep_urls_methods_csrf_and_field_names(self):
        self.register()
        [message] = list(notifications.to_send())
        page = html(self.client.get(URL))
        sent = reverse("core:notification-mark-sent", args=[message.pk])
        dismiss = reverse("core:notification-dismiss", args=[message.pk])
        sent_form = re.search(rf'<form method="post" action="{sent}">(.*?)</form>', page, re.S).group(1)
        self.assertIn('name="csrfmiddlewaretoken"', sent_form)
        self.assertIn(f'Mark as sent<span class="visually-hidden"> for {message.guardian.full_name}</span>', sent_form)
        form = re.search(rf'<form method="post" action="{dismiss}"[^>]*>(.*?)</form>', page, re.S).group(1)
        self.assertIn('name="csrfmiddlewaretoken"', form)
        self.assertRegex(form, rf'<label for="reason-{message.pk}">Reason for not sending')
        self.assertIn(f'id="reason-{message.pk}" name="reason" maxlength="200" required', form)
        self.assertIn("Dismissing does not send the message. The reason is recorded.", form)
        self.assertIn(f'Dismiss<span class="visually-hidden"> message to {message.guardian.full_name}</span>', form)
        self.assertNotIn("placeholder", form)

    def test_a_get_changes_no_message(self):
        self.every_type()
        before = self.statuses()
        self.client.get(URL)
        self.client.get(URL)
        self.assertEqual(self.statuses(), before)

    def test_no_per_row_query_growth(self):
        self.register()
        self.more_types()
        before = len(list(notifications.to_send()))
        first = self.query_count()
        notice = announcements.publish(title="Second", body="Second notice.", audience="ALL",
                                       class_grade=None, section=None, actor=self.admin)
        announcements.prepare_messages(notice)
        self.assertGreater(len(list(notifications.to_send())), before)
        self.assertEqual(self.query_count(), first)


class ActionTests(Base, TestCase):
    def setUp(self):
        super().setUp()
        self.register()
        [self.message] = list(notifications.to_send())
        self.mark = reverse("core:notification-mark-sent", args=[self.message.pk])
        self.dismiss = reverse("core:notification-dismiss", args=[self.message.pk])

    def test_mark_sent_records_the_actor_and_shows_in_sent_today(self):
        response = self.client.post(self.mark, follow=True)
        self.assertRedirects(response, URL)
        self.assertContains(response, "Marked as sent.")
        self.message.refresh_from_db()
        self.assertEqual((self.message.status, self.message.marked_sent_by), (Notification.Status.SENT, self.admin))
        page = html(response)
        self.assertIn("0 waiting · 1 sent today", page)
        self.assertIn('role="region" aria-label="Sent today" tabindex="0"', page)
        self.assertEqual(page.count('scope="col"'), 4)
        self.assertIn(f'<td class="text-break">{self.admin.username}</td>', page)
        self.assertIn("<td>Absence alert (Asha)</td>", page)
        self.assertIn(self.message.guardian.full_name, page.split('aria-labelledby="sent-heading"')[1])

    def test_dismiss_requires_a_reason_and_records_actor_and_reason(self):
        response = self.client.post(self.dismiss, {"reason": " "}, follow=True)
        self.assertContains(response, "Give a reason for not sending this message.")
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.PREPARED)
        response = self.client.post(self.dismiss, {"reason": "Parent already informed"}, follow=True)
        self.assertContains(response, "Message dismissed. It will not be sent.")
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.DISMISSED)
        self.assertEqual((self.message.dismissed_by, self.message.dismiss_reason),
                         (self.admin, "Parent already informed"))
        self.assertIsNone(self.message.marked_sent_by)
        self.assertIn("Nothing to send.", html(response))

    def test_both_actions_are_post_only_and_csrf_protected(self):
        for url in (self.mark, self.dismiss):
            self.assertEqual(self.client.get(url).status_code, 405)
        strict = self.client_class(enforce_csrf_checks=True)
        strict.login(username="admin", password="pass-12345")
        self.assertEqual(strict.post(self.mark).status_code, 403)
        self.assertEqual(strict.post(self.dismiss, {"reason": "x"}).status_code, 403)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.PREPARED)

    def opt_out(self):
        GuardianContactConsent.objects.create(
            guardian=self.message.guardian, status=GuardianContactConsent.Status.OPTED_OUT,
            source=GuardianContactConsent.Source.PAPER_FORM, recorded_by=self.admin)

    def test_mark_sent_after_opt_out_is_not_recorded_as_sent(self):
        self.opt_out()
        self.client.post(self.mark, follow=True)
        self.message.refresh_from_db()
        self.assertNotEqual(self.message.status, Notification.Status.SENT)
        self.assertIsNone(self.message.marked_sent_by)

    def test_a_guardian_without_consent_has_no_entry(self):
        self.opt_out()
        page = html(self.client.get(URL))
        self.assertIn("Nothing to send.", page)
        self.assertNotIn("wa.me", page)


class StateTests(Base, TestCase):
    def test_portal_only_banner_and_gated_settings_link(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        page = html(self.client.get(URL))
        self.assertIn("WhatsApp messages are switched off.", page)
        self.assertIn("New messages are not prepared while the school uses portal only.", page)
        self.assertIn(f'<a href="{reverse("core:school-detail")}">School settings</a>', page)
        _, sender = self.client_with("send_notification")
        page = html(sender.get(URL))
        self.assertIn("WhatsApp messages are switched off.", page)
        self.assertNotIn("School settings", page)
        self.assertNotIn("PORTAL_BASE_URL", page)

    @override_settings(PORTAL_BASE_URL="")
    def test_missing_portal_address_banner(self):
        page = html(self.client.get(URL))
        self.assertIn("The portal address (PORTAL_BASE_URL) is not set", page)
        self.assertIn("Ask whoever runs the server to set it.", page)
        self.assertNotIn("WhatsApp messages are switched off.", page)

    def test_no_banner_when_everything_is_configured(self):
        page = html(self.client.get(URL))
        self.assertNotIn("switched off", page)
        self.assertNotIn("PORTAL_BASE_URL", page)

    def test_missing_phone_shows_a_labelled_state_and_a_gated_fix_link(self):
        self.register()
        [message] = list(notifications.to_send())
        Guardian.objects.filter(pk=message.guardian_id).update(phone="N/A")
        page = html(self.client.get(URL))
        self.assertIn("Phone number missing or not usable", page)
        self.assertIn("erp-status--stale", page)
        self.assertNotIn("https://wa.me/", page)
        self.assertIn(
            f'<a href="{reverse("core:guardian-edit", args=[message.guardian_id])}">update the guardian</a>', page)
        self.assertNotIn("Mark as sent", queue_section(page))
        self.assertIn("Reason for not sending", page)                      # Dismiss stays available
        _, sender = self.client_with("send_notification")
        page = html(sender.get(URL))
        self.assertNotIn("/edit/", queue_section(page))
        self.assertIn("ask someone who can update the guardian", page)


class AccessAndNavigationTests(Base, TestCase):
    def test_permission_outcomes_are_unchanged(self):
        self.every_type()
        self.assertEqual(self.client_class().get(URL).status_code, 302)
        self.assertEqual(self.teacher().get(URL).status_code, 403)
        self.assertEqual(self.guardian_client().get(URL).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(URL).status_code, 403)
        _, sender = self.client_with("send_notification")
        self.assertEqual(sender.get(URL).status_code, 200)
        pk = Notification.objects.first().pk
        for url in (reverse("core:notification-mark-sent", args=[pk]),
                    reverse("core:notification-dismiss", args=[pk])):
            self.assertEqual(self.teacher().post(url, {"reason": "x"}).status_code, 403)
            self.assertEqual(nobody.post(url, {"reason": "x"}).status_code, 403)
        self.assertEqual(Notification.objects.filter(status=Notification.Status.PREPARED).count(),
                         Notification.objects.count())

    def test_rule_and_permission_matrix(self):
        context = breadcrumb_context(resolve(URL))
        self.assertEqual([c["label"] for c in context["breadcrumbs"]], ["Overview", "To send"])
        self.assertEqual(context["nav_section"], "notifications-to-send")
        user, _ = self.client_with("send_notification")
        self.assertEqual(breadcrumb_context(resolve(URL), user)["breadcrumbs"], [])
        user, _ = self.client_with("send_notification", "view_school")
        self.assertEqual([c["label"] for c in breadcrumb_context(resolve(URL), user)["breadcrumbs"]],
                         ["Overview", "To send"])

    def test_sidebar_highlights_to_send_empty_and_populated(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                if populated:
                    self.every_type()
                page = html(self.client.get(URL))
                self.assertEqual(re.findall(ACTIVE_LINK, page), [URL])
                self.assertIn('aria-label="Breadcrumb"', page)
        followed = self.client.post(
            reverse("core:notification-dismiss", args=[Notification.objects.first().pk]),
            {"reason": "x"}, follow=True)
        self.assertEqual(re.findall(ACTIVE_LINK, html(followed)), [URL])
