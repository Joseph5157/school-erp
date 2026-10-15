"""Phase 7 Gate 3: announcements (ADR 0015)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase

from core import announcements
from core import guardian_accounts as ga
from core.models import Announcement, GuardianContactConsent, NotificationTemplate
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
