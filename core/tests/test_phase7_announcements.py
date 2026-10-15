"""Phase 7 Gate 3: announcements (ADR 0015)."""

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase

from core import announcements
from core.models import Announcement, NotificationTemplate
from core.tests.test_phase7_alerts import AlertFixture

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
