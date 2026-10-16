"""Phase 6 Gate 2: authorization boundary, access reviews and sweep (ADR 0013, OD-8)."""

import uuid
from datetime import date
from unittest import mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import URLPattern, reverse

from accounts.models import SecurityEvent
from core import guardian_access
from core import guardian_accounts as ga
from core.authorization import (
    guardian_account,
    guardian_can_view,
    guardian_grants,
    guardian_visible_grant,
    is_guardian,
)
from core.models import (
    AcademicYear,
    Guardian,
    GuardianAccessReview,
    GuardianAccount,
    GuardianStudentAccess,
    Student,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture

TODAY = date(2026, 10, 12)
METHOD = GuardianAccount.VerificationMethod.EXISTING_RECORDS
Trigger = GuardianAccessReview.Trigger
RETAIN, REVOKE = GuardianAccessReview.Decision.RETAINED, GuardianAccessReview.Decision.REVOKED


class BoundaryFixture(Phase4Fixture):
    def setUp(self):
        self.today = TODAY
        for target in ("core.views.business_today", "core.models.business_today"):
            patch = mock.patch(target, new=lambda: self.today)
            patch.start()
            self.addCleanup(patch.stop)
        self.build_phase4()
        self.meena = Guardian.objects.create(full_name="Meena Rao")
        self.other = Guardian.objects.create(full_name="Other Parent")
        self.asha, self.asha_e = self.make_student("Asha Rao")
        self.ravi, _ = self.make_student("Ravi Rao", section=self.six_b)
        self.bina, _ = self.make_student("Bina Other")
        self.asha_link = self.relate(self.asha, self.meena)
        self.ravi_link = self.relate(self.ravi, self.meena)
        self.bina_link = self.relate(self.bina, self.other)
        self.account, self.password = ga.create_guardian_account(
            guardian=self.meena, username="meena", method=METHOD, note="known", actor=self.admin)
        self.asha_grant = ga.grant_student_access(student_guardian=self.asha_link,
                                                  actor=self.admin)
        other_account, _ = ga.create_guardian_account(
            guardian=self.other, username="other.parent", method=METHOD, note="known",
            actor=self.admin)
        self.bina_grant = ga.grant_student_access(student_guardian=self.bina_link,
                                                  actor=self.admin)
        self.user = self.account.user
        self.client.login(username="admin", password="pass-12345")

    @staticmethod
    def relate(student, guardian):
        return StudentGuardian.objects.create(student=student, guardian=guardian,
                                              relationship_type="MOTHER")

    def guardian_client(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        client = self.client_class()
        client.login(username="meena", password=self.password)
        return client


class HelperTests(BoundaryFixture, TestCase):
    def test_active_guardian_sees_only_granted_students(self):
        self.assertTrue(is_guardian(self.user))
        self.assertEqual(guardian_account(self.user), self.account)
        self.assertEqual(list(guardian_grants(self.user)), [self.asha_grant])
        self.assertTrue(guardian_can_view(self.user, self.asha))
        self.assertFalse(guardian_can_view(self.user, self.ravi))   # related, not granted
        self.assertFalse(guardian_can_view(self.user, self.bina))   # another family

    def test_visible_grant_by_public_id(self):
        self.assertEqual(guardian_visible_grant(self.user, self.asha_grant.public_id),
                         self.asha_grant)
        for public_id in (self.bina_grant.public_id, uuid.uuid4(), "not-a-uuid"):
            with self.subTest(public_id=public_id):
                self.assertIsNone(guardian_visible_grant(self.user, public_id))

    def test_revoked_grant_revoked_link_and_inactive_login(self):
        ga.revoke_student_access(grant=self.asha_grant, actor=self.admin, reason="x")
        self.assertFalse(guardian_can_view(self.user, self.asha))
        grant = ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        self.assertTrue(guardian_can_view(self.user, self.asha))
        self.user.is_active = False
        self.user.save()
        self.assertFalse(is_guardian(self.user))
        self.user.is_active = True
        self.user.save()
        ga.revoke_account_link(account=self.account, actor=self.admin, reason="x")
        self.assertFalse(is_guardian(self.user))
        self.assertFalse(guardian_can_view(self.user, self.asha))
        self.assertIsNone(guardian_visible_grant(self.user, grant.public_id))

    def test_administrator_is_not_a_guardian(self):
        self.assertFalse(is_guardian(self.admin))
        self.assertFalse(guardian_can_view(self.admin, self.asha))


class InactiveReviewTests(BoundaryFixture, TestCase):
    def test_no_grants_needs_no_review(self):
        self.ravi.record_status_change(Student.Status.INACTIVE, reason="Test reason")
        self.ravi.refresh_from_db()
        self.assertEqual(self.ravi.status, Student.Status.INACTIVE)

    def test_missing_or_partial_decisions_change_nothing(self):
        second = ga.grant_student_access(
            student_guardian=self.relate(self.asha, self.other), actor=self.admin)
        for decisions in (None, {self.asha_grant.pk: RETAIN},
                          {self.asha_grant.pk: RETAIN, second.pk: "MAYBE"}):
            with self.subTest(decisions=decisions), self.assertRaises(ValidationError):
                self.asha.record_status_change(Student.Status.INACTIVE, actor=self.admin,
                                               access_decisions=decisions,
                                               reason="Test reason")
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.ACTIVE)
        self.assertFalse(GuardianAccessReview.objects.exists())

    def test_retain_and_revoke_are_recorded(self):
        second = ga.grant_student_access(
            student_guardian=self.relate(self.asha, self.other), actor=self.admin)
        self.asha.record_status_change(
            Student.Status.INACTIVE, actor=self.admin,
            access_decisions={self.asha_grant.pk: RETAIN, second.pk: REVOKE},
            access_note="Left school", reason="Test reason")
        self.asha_grant.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(self.asha_grant.is_active)
        self.assertFalse(second.is_active)
        self.assertIn("Left school", second.revocation_reason)
        reviews = GuardianAccessReview.objects.all()
        self.assertEqual({(r.grant_id, r.trigger, r.decision, r.enrollment) for r in reviews},
                         {(self.asha_grant.pk, Trigger.STUDENT_INACTIVE, RETAIN, self.asha_e),
                          (second.pk, Trigger.STUDENT_INACTIVE, REVOKE, self.asha_e)})
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.ACCESS_RETAINED).exists())

    def test_view_shows_review_step_then_saves(self):
        url = reverse("core:student-status-change", args=[self.asha.pk])
        page = self.client.post(
            url, {"status": "INACTIVE", "reason": "Test reason"}
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Meena Rao")
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.ACTIVE)
        self.client.post(url, {"status": "INACTIVE", "reason": "Test reason",
                               "access_review": "1",
                               f"decision_{self.asha_grant.pk}": REVOKE})
        self.asha.refresh_from_db()
        self.asha_grant.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.INACTIVE)
        self.assertFalse(self.asha_grant.is_active)

    def test_view_refuses_incomplete_review(self):
        url = reverse("core:student-status-change", args=[self.asha.pk])
        self.client.post(
            url,
            {"status": "INACTIVE", "reason": "Test reason", "access_review": "1"},
            follow=True,
        )
        self.asha.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.ACTIVE)


class PlacementEndedReviewTests(BoundaryFixture, TestCase):
    def enroll_six_b(self, **kwargs):
        return self.asha.enroll(academic_year=self.year, class_grade=self.grade6,
                                section=self.six_b, start_date=TODAY, **kwargs)

    def test_section_move_requires_decisions(self):
        with self.assertRaises(ValidationError):
            self.enroll_six_b()
        self.assertEqual(self.asha.enrollments.count(), 1)
        self.enroll_six_b(actor=self.admin, access_decisions={self.asha_grant.pk: RETAIN})
        review = GuardianAccessReview.objects.get()
        self.assertEqual((review.trigger, review.enrollment), (Trigger.PLACEMENT_ENDED,
                                                               self.asha_e))
        self.assertTrue(guardian_can_view(self.user, self.asha))

    def test_first_placement_needs_no_review(self):
        student = Student.objects.create(applicant=self.asha.applicant.__class__.objects.create(
            admission_status="ACCEPTED", full_name="New"), full_name="New")
        grant = ga.grant_student_access(student_guardian=self.relate(student, self.meena),
                                        actor=self.admin)
        student.enroll(academic_year=self.year, class_grade=self.grade6, section=self.six_a,
                       start_date=TODAY)
        self.assertFalse(GuardianAccessReview.objects.filter(grant=grant).exists())

    def test_view_flow(self):
        url = reverse("core:student-enroll", args=[self.asha.pk])
        data = {"academic_year": self.year.pk, "class_grade": self.grade6.pk,
                "section": self.six_b.pk, "start_date": TODAY.isoformat()}
        page = self.client.post(url, data)
        self.assertContains(page, "Placement ended")
        self.assertEqual(self.asha.enrollments.count(), 1)
        self.client.post(url, {**data, "access_review": "1",
                               f"decision_{self.asha_grant.pk}": RETAIN})
        self.assertEqual(self.asha.enrollments.count(), 2)


class DateReviewTests(BoundaryFixture, TestCase):
    """OD-8: no current enrollment -> fail closed until an explicit decision."""

    def after_year_end(self):
        self.today = date(2027, 4, 5)

    def test_year_end_fails_closed(self):
        self.assertTrue(guardian_can_view(self.user, self.asha))
        self.after_year_end()
        self.assertTrue(guardian_access.is_review_pending(self.asha_grant))
        self.assertFalse(guardian_can_view(self.user, self.asha))
        self.assertIsNone(guardian_visible_grant(self.user, self.asha_grant.public_id))
        self.asha_grant.refresh_from_db()
        self.assertTrue(self.asha_grant.is_active)  # nothing revoked or inferred

    def test_queue_and_retain_restores_access_once(self):
        self.after_year_end()
        page = self.client.get(reverse("core:guardian-access-reviews"))
        self.assertEqual([row["grant"] for row in page.context["rows"]],
                         [self.asha_grant, self.bina_grant])
        decide = reverse("core:guardian-access-review-decide", args=[self.asha_grant.pk])
        self.client.post(decide, {"decision": RETAIN})
        self.assertTrue(guardian_can_view(self.user, self.asha))
        self.client.post(decide, {"decision": REVOKE}, follow=True)  # no longer pending
        self.asha_grant.refresh_from_db()
        self.assertTrue(self.asha_grant.is_active)
        self.assertEqual(GuardianAccessReview.objects.filter(grant=self.asha_grant).count(), 1)

    def test_revoke_from_queue(self):
        self.after_year_end()
        guardian_access.decide_date_review(grant=self.asha_grant, decision=REVOKE,
                                           actor=self.admin)
        self.asha_grant.refresh_from_db()
        self.assertFalse(self.asha_grant.is_active)

    def test_later_placement_asks_again(self):
        self.after_year_end()
        guardian_access.decide_date_review(grant=self.asha_grant, decision=RETAIN,
                                           actor=self.admin)
        next_year = AcademicYear.objects.create(name="2027-28", start_date=date(2027, 6, 1),
                                                end_date=date(2028, 3, 31))
        self.today = date(2027, 6, 1)
        self.asha.enroll(academic_year=next_year, class_grade=self.grade6, section=self.six_a,
                         start_date=self.today, actor=self.admin,
                         access_decisions={self.asha_grant.pk: RETAIN})
        self.assertTrue(guardian_can_view(self.user, self.asha))
        self.today = date(2028, 4, 2)
        self.assertFalse(guardian_can_view(self.user, self.asha))

    def test_student_never_enrolled_is_pending(self):
        student = Student.objects.create(applicant=self.asha.applicant.__class__.objects.create(
            admission_status="ACCEPTED", full_name="Unplaced"), full_name="Unplaced")
        grant = ga.grant_student_access(student_guardian=self.relate(student, self.meena),
                                        actor=self.admin)
        self.assertTrue(guardian_access.is_review_pending(grant))
        guardian_access.decide_date_review(grant=grant, decision=RETAIN, actor=self.admin)
        self.assertFalse(guardian_access.is_review_pending(grant))

    def test_pending_event_recorded_once(self):
        self.after_year_end()
        for _ in range(2):
            self.client.get(reverse("core:guardian-access-reviews"))
        self.assertEqual(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.ACCESS_REVIEW_PENDING).count(), 2)

    def test_guardian_page_marks_review(self):
        self.after_year_end()
        page = self.client.get(reverse("core:guardian-detail", args=[self.meena.pk]))
        self.assertContains(page, "under review")


class ReviewHistoryProtectionTests(BoundaryFixture, TestCase):
    def test_reviews_cannot_be_changed_or_deleted(self):
        self.today = date(2027, 4, 5)
        review = guardian_access.decide_date_review(grant=self.asha_grant, decision=RETAIN,
                                                    actor=self.admin)
        for sql in ("UPDATE core_guardianaccessreview SET decision = 'REVOKED' WHERE id = %s",
                    "DELETE FROM core_guardianaccessreview WHERE id = %s"):
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, [review.pk])


class GuardianSweepTests(BoundaryFixture, TestCase):
    """A guardian-only login is refused on every administrative and teacher URL."""

    def test_guardian_only_login_is_forbidden_everywhere(self):
        from core import urls as core_urls

        client = self.guardian_client()
        names = []
        for pattern in core_urls.urlpatterns:
            assert isinstance(pattern, URLPattern)
            kwargs = {name: 1 for name in pattern.pattern.regex.groupindex}
            url = reverse(f"core:{pattern.name}", kwargs=kwargs)
            names.append(pattern.name)
            for method in ("get", "post"):
                with self.subTest(url=pattern.name, method=method):
                    self.assertEqual(getattr(client, method)(url).status_code, 403)
        self.assertIn("guardian-access-reviews", names)

    def test_guardian_who_is_also_teacher_is_not_an_administrator(self):
        self.user.groups.add(Group.objects.get(name="Teachers"))
        client = self.guardian_client()
        self.assertEqual(client.get(reverse("core:guardian-list")).status_code, 403)
        self.assertEqual(client.get(reverse("core:my-home")).status_code, 200)

    def test_other_family_grants_never_visible(self):
        self.assertNotIn(self.bina_grant, list(guardian_grants(self.user)))
        self.assertEqual(GuardianStudentAccess.objects.count(), 2)
