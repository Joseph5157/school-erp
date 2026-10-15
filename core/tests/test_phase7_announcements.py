"""Phase 7 Gate 3: announcements (ADR 0015)."""

from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from core import announcements, notifications
from core import guardian_accounts as ga
from core.models import (
    Announcement,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    School,
)
from core.tests.test_phase7_alerts import BASE, AlertFixture

TEXT = "Dear parent, there is a new notice from the school. Read it here: {portal_url}"
ALL = Announcement.Audience.ALL
CLASS = Announcement.Audience.CLASS
SECTION = Announcement.Audience.SECTION


class AnnouncementFixture(AlertFixture):
    """Gates 2/4 fixture: ASSIST school, PORTAL_BASE_URL, today 2026-10-12;
    Meena -> Asha (6A, granted), Other -> Bina (6A, granted),
    Meena -> Ravi (6B, linked without access); both guardians opted in;
    self.client is logged in as the administrator."""

    def notice(self, audience=ALL, *, class_grade=None, section=None,
               title="Sports Day", body="Sports Day is on 20 October."):
        return announcements.publish(title=title, body=body, audience=audience,
                                     class_grade=class_grade, section=section,
                                     actor=self.admin)


class PublishTests(AnnouncementFixture, TestCase):
    def test_publish_each_audience(self):
        everyone = self.notice()
        grade = self.notice(CLASS, class_grade=self.grade6)
        section = self.notice(SECTION, section=self.six_b)
        self.assertEqual((everyone.class_grade, everyone.section), (None, None))
        self.assertEqual((grade.class_grade, grade.section), (self.grade6, None))
        self.assertEqual((section.class_grade, section.section), (None, self.six_b))
        self.assertEqual(everyone.published_by, self.admin)
        self.assertFalse(everyone.is_withdrawn)
        self.assertEqual([everyone.audience_label(), grade.audience_label(),
                          section.audience_label()],
                         ["Whole school", "Grade 6", "Grade 6 - B"])

    def test_title_and_body_are_stripped_and_required(self):
        notice = self.notice(title="  Holiday  ", body="  Closed on Friday.  ")
        self.assertEqual((notice.title, notice.body), ("Holiday", "Closed on Friday."))
        for title, body in (("   ", "x"), ("x", "   ")):
            with self.subTest(title=title, body=body), self.assertRaises(ValidationError):
                self.notice(title=title, body=body)

    def test_lengths_are_limited(self):
        with self.assertRaises(ValidationError):
            self.notice(title="x" * 121)
        with self.assertRaises(ValidationError):
            self.notice(body="x" * 2001)

    def test_audience_target_must_match(self):
        for audience, kwargs in ((CLASS, {}), (SECTION, {}),
                                 (CLASS, {"section": self.six_a})):
            with self.subTest(audience=audience, kwargs=kwargs), \
                    self.assertRaises(ValidationError):
                self.notice(audience, **kwargs)

    def test_extra_target_is_dropped_for_other_audiences(self):
        notice = self.notice(ALL, class_grade=self.grade6, section=self.six_a)
        self.assertEqual((notice.class_grade, notice.section), (None, None))

    def test_announcement_text_is_seeded_and_valid(self):
        template = NotificationTemplate.objects.get(
            key="announcement", channel="WHATSAPP", language="en", version=1)
        self.assertTrue(template.approved)
        self.assertEqual(template.body, TEXT)
        template.full_clean()

    def test_administrators_have_the_permissions(self):
        for perm in ("core.add_announcement", "core.view_announcement",
                     "core.withdraw_announcement"):
            with self.subTest(perm=perm):
                self.assertTrue(self.admin.has_perm(perm))
                self.assertFalse(self.rao.has_perm(perm))


class WithdrawTests(AnnouncementFixture, TestCase):
    def test_withdraw_records_who_when_and_why(self):
        notice = announcements.withdraw(self.notice(), actor=self.admin, reason=" Wrong date ")
        self.assertTrue(notice.is_withdrawn)
        self.assertEqual((notice.withdrawn_by, notice.withdrawal_reason),
                         (self.admin, "Wrong date"))

    def test_reason_required_and_only_once(self):
        notice = self.notice()
        with self.assertRaisesMessage(ValidationError,
                                      "Give a reason for withdrawing this notice."):
            announcements.withdraw(notice, actor=self.admin, reason="  ")
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        with self.assertRaisesMessage(ValidationError,
                                      "This notice has already been withdrawn."):
            announcements.withdraw(notice, actor=self.admin, reason="Again")


class HistoryGuardTests(AnnouncementFixture, TestCase):
    def refused(self, queryset, **changes):
        with self.assertRaises(DatabaseError), transaction.atomic():
            queryset.update(**changes)

    def test_published_content_is_fixed_and_never_deleted(self):
        rows = Announcement.objects.filter(pk=self.notice().pk)
        self.refused(rows, title="Changed")
        self.refused(rows, body="Changed")
        self.refused(rows, audience=CLASS, class_grade=self.grade6)
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()

    def test_withdrawal_is_set_once_and_never_cleared(self):
        notice = announcements.withdraw(self.notice(), actor=self.admin, reason="Wrong date")
        rows = Announcement.objects.filter(pk=notice.pk)
        self.refused(rows, withdrawn_at=None, withdrawn_by=None, withdrawal_reason="")
        self.refused(rows, withdrawal_reason="Other reason")


class AudienceTests(AnnouncementFixture, TestCase):
    def guardians(self, notice):
        return {g.student_guardian.guardian for g in announcements.recipient_grants(notice)}

    def test_whole_school_reaches_every_portal_guardian(self):
        self.assertEqual(self.guardians(self.notice()), {self.meena, self.other})

    def test_class_and_section_reach_only_matching_guardians(self):
        ravi_grant = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        self.assertEqual(self.guardians(self.notice(CLASS, class_grade=self.grade6)),
                         {self.meena, self.other})
        self.assertEqual(self.guardians(self.notice(SECTION, section=self.six_a)),
                         {self.meena, self.other})
        only_b = announcements.recipient_grants(self.notice(SECTION, section=self.six_b))
        self.assertEqual(only_b, [ravi_grant])

    def test_one_grant_per_guardian_with_two_children(self):
        ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        grants = announcements.recipient_grants(self.notice())
        self.assertEqual(sorted(g.student_guardian.guardian.pk for g in grants),
                         sorted([self.meena.pk, self.other.pk]))

    def test_without_portal_access_or_with_inactive_login_reaches_nobody(self):
        ga.revoke_student_access(grant=self.bina_grant, actor=self.admin, reason="Left")
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.guardians(self.notice()), set())

    def test_audience_is_todays_enrollments(self):
        notice = self.notice(SECTION, section=self.six_a)
        self.assertEqual(set(announcements.audience_students(notice)), {self.asha, self.bina})
        after_year = date(2027, 4, 5)
        self.assertEqual(list(announcements.audience_students(notice, on_date=after_year)), [])

    def test_counts_portal_guardians_and_whatsapp_opt_ins(self):
        self.consent(self.other, GuardianContactConsent.Status.OPTED_OUT)
        self.assertEqual(announcements.audience_counts(self.notice()),
                         {"guardians": 2, "opted_in": 1})


class VisibilityTests(AnnouncementFixture, TestCase):
    def test_guardian_sees_matching_live_notices_newest_first(self):
        everyone = self.notice(title="Everyone")
        mine = self.notice(SECTION, section=self.six_a, title="6A")
        self.notice(SECTION, section=self.six_b, title="6B")  # Ravi is not granted
        withdrawn = self.notice(title="Withdrawn")
        announcements.withdraw(withdrawn, actor=self.admin, reason="Wrong")
        self.assertEqual(announcements.visible_announcements(self.user), [mine, everyone])

    def test_no_current_enrollment_sees_nothing(self):
        self.notice()
        self.today = date(2027, 4, 5)  # after the year: Asha's access is under review
        self.assertEqual(announcements.visible_announcements(self.user), [])

    def test_non_guardian_sees_nothing(self):
        self.notice()
        self.assertEqual(announcements.visible_announcements(self.admin), [])


class PrepareMessagesTests(AnnouncementFixture, TestCase):
    def sent(self):
        return list(Notification.objects.filter(type=Notification.Type.ANNOUNCEMENT)
                    .order_by("pk"))

    def test_one_message_per_guardian_and_repeat_is_harmless(self):
        ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        notice = self.notice()
        self.assertEqual(announcements.prepare_messages(notice),
                         {"prepared": 2, "skipped": 0, "failed": 0})
        self.assertEqual(announcements.prepare_messages(notice),
                         {"prepared": 2, "skipped": 0, "failed": 0})
        messages = self.sent()
        self.assertEqual(sorted(m.guardian.pk for m in messages),
                         sorted([self.meena.pk, self.other.pk]))
        self.assertTrue(all(m.student is None for m in messages))
        self.assertEqual(messages[0].idempotency_key,
                         f"ANNOUNCEMENT:{messages[0].guardian.pk}:-:announcement-{notice.pk}")

    def test_text_is_the_approved_link_only_wording(self):
        notice = self.notice(title="Fee dates", body="Secret body text")
        announcements.prepare_messages(notice)
        link = BASE + reverse("portal:notice", args=[notice.public_id])
        self.assertEqual(self.sent()[0].parameters, {"portal_url": link})
        text = notifications.render(self.sent()[0])
        self.assertEqual(text, "Dear parent, there is a new notice from the school. "
                               "Read it here: " + link)
        self.assertNotIn("Fee dates", text)
        self.assertNotIn("Secret", text)

    def test_guardian_without_consent_is_skipped(self):
        self.consent(self.other, GuardianContactConsent.Status.OPTED_OUT)
        self.assertEqual(announcements.prepare_messages(self.notice()),
                         {"prepared": 1, "skipped": 1, "failed": 0})

    def test_refused_when_withdrawn_portal_only_or_no_address(self):
        withdrawn = self.notice()
        announcements.withdraw(withdrawn, actor=self.admin, reason="Wrong")
        with self.assertRaisesMessage(ValidationError, "This notice has been withdrawn."):
            announcements.prepare_messages(withdrawn)
        live = self.notice()
        with override_settings(PORTAL_BASE_URL=""), self.assertRaisesMessage(
                ValidationError,
                "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."):
            announcements.prepare_messages(live)
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        with self.assertRaisesMessage(ValidationError,
                                      "WhatsApp sending is switched off for this school."):
            announcements.prepare_messages(live)
        self.assertEqual(self.sent(), [])

    def test_stale_instance_of_a_withdrawn_notice_is_refused(self):
        notice = self.notice()
        announcements.withdraw(notice, actor=self.admin, reason="Wrong")
        with self.assertRaisesMessage(ValidationError, "This notice has been withdrawn."):
            announcements.prepare_messages(notice)
        self.assertEqual(self.sent(), [])

    def test_missing_text_is_counted_as_failed_and_logged(self):
        with mock.patch.object(announcements, "TEMPLATE_KEY", "no-such-text"), \
                self.assertLogs("core.announcements", "WARNING"):
            result = announcements.prepare_messages(self.notice())
        self.assertEqual(result, {"prepared": 0, "skipped": 0, "failed": 2})

    def test_withdraw_dismisses_waiting_messages_only(self):
        notice = self.notice()
        announcements.prepare_messages(notice)
        first, second = self.sent()
        notifications.mark_sent(first, user=self.admin)
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, Notification.Status.SENT)
        self.assertEqual((second.status, second.dismiss_reason, second.dismissed_by),
                         (Notification.Status.DISMISSED, "Announcement withdrawn", self.admin))

    def test_withdraw_leaves_other_notices_messages_alone(self):
        keep, drop = self.notice(title="Keep"), self.notice(title="Drop")
        announcements.prepare_messages(keep)
        announcements.prepare_messages(drop)
        announcements.withdraw(drop, actor=self.admin, reason="Wrong")
        statuses = {(m.idempotency_key.rsplit("-", 1)[1], m.status) for m in self.sent()}
        self.assertEqual(statuses, {(str(keep.pk), Notification.Status.PREPARED),
                                    (str(drop.pk), Notification.Status.DISMISSED)})


class OfficePageTests(AnnouncementFixture, TestCase):
    def test_publish_from_the_form(self):
        page = self.client.post(reverse("core:announcement-create"), {
            "title": "Holiday", "body": "Closed on Friday.", "audience": "SECTION",
            "section": self.six_a.pk,
        })
        notice = Announcement.objects.get()
        self.assertRedirects(page, reverse("core:announcement-detail", args=[notice.pk]))
        self.assertEqual((notice.audience, notice.section), (SECTION, self.six_a))

    def test_form_requires_the_matching_class_or_section(self):
        page = self.client.post(reverse("core:announcement-create"), {
            "title": "Holiday", "body": "Closed.", "audience": "CLASS"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Choose the class.")
        self.assertFalse(Announcement.objects.exists())

    def test_detail_shows_body_counts_and_actions(self):
        notice = self.notice(body="Line one\nLine two <b>x</b>")
        page = self.client.get(reverse("core:announcement-detail", args=[notice.pk]))
        self.assertContains(page, "Line one<br>Line two &lt;b&gt;x&lt;/b&gt;", html=False)
        self.assertEqual(page.context["counts"], {"guardians": 2, "opted_in": 2})
        self.assertContains(page, reverse("core:announcement-prepare", args=[notice.pk]))
        self.assertContains(page, reverse("core:announcement-withdraw", args=[notice.pk]))

    def test_prepare_button_hidden_in_portal_only(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        notice = self.notice()
        page = self.client.get(reverse("core:announcement-detail", args=[notice.pk]))
        self.assertNotContains(page, reverse("core:announcement-prepare", args=[notice.pk]))

    def test_prepare_and_withdraw_from_the_page(self):
        notice = self.notice()
        page = self.client.post(reverse("core:announcement-prepare", args=[notice.pk]),
                                follow=True)
        self.assertContains(page, "Messages ready on the To send page: 2.")
        page = self.client.post(reverse("core:announcement-withdraw", args=[notice.pk]),
                                {"reason": ""}, follow=True)
        self.assertContains(page, "Give a reason for withdrawing this notice.")
        self.client.post(reverse("core:announcement-withdraw", args=[notice.pk]),
                         {"reason": "Wrong date"})
        notice.refresh_from_db()
        self.assertTrue(notice.is_withdrawn)
        page = self.client.post(reverse("core:announcement-prepare", args=[notice.pk]),
                                follow=True)
        self.assertContains(page, "This notice has been withdrawn.")

    def test_list_page(self):
        notice = self.notice(title="Sports Day")
        page = self.client.get(reverse("core:announcement-list"))
        self.assertContains(page, "Sports Day")
        self.assertContains(page, reverse("core:announcement-detail", args=[notice.pk]))

    def test_office_nav_has_announcements(self):
        from core.navigation import office_nav

        labels = [link["label"] for group in office_nav(self.admin, "")
                  for link in group["links"]]
        self.assertIn("Announcements", labels)
        teacher_labels = [link["label"] for group in office_nav(self.rao, "")
                          for link in group["links"]]
        self.assertNotIn("Announcements", teacher_labels)

    def test_teachers_and_guardians_are_forbidden(self):
        notice = self.notice()
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        guardian = self.guardian_client()
        for client in (teacher, guardian):
            for url, method in ((reverse("core:announcement-list"), "get"),
                                (reverse("core:announcement-create"), "post"),
                                (reverse("core:announcement-prepare", args=[notice.pk]), "post"),
                                (reverse("core:announcement-withdraw", args=[notice.pk]),
                                 "post")):
                with self.subTest(url=url):
                    self.assertEqual(getattr(client, method)(url).status_code, 403)

    def test_to_send_labels_announcement_rows(self):
        announcements.prepare_messages(self.notice())
        page = self.client.get(reverse("core:notifications-to-send"))
        self.assertContains(page, "School notice")
