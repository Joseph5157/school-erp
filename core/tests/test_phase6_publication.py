"""Phase 6 Gate 6: explicit Term publication and guardian report cards (ADR 0014)."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import publication
from core.models import ResultStatus, StudentResult, TermPublication, TermRemark
from core.tests.test_phase6_access_boundary import BoundaryFixture

Status = TermPublication.Status


class PublicationFixture(BoundaryFixture):
    def setUp(self):
        super().setUp()
        self.bina_e = self.bina.enrollments.get()
        self.ut1 = self.make_assessment(name="UT1", on=date(2026, 7, 15))
        self.result = self.mark(self.ut1, self.asha_e, "15")
        self.mark(self.ut1, self.bina_e, "11")
        self.force_finalize(self.ut1)
        self.remark = TermRemark.objects.create(term=self.term1, student=self.asha,
                                                remark="Steady progress.", written_by=self.rao)
        self.portal = self.guardian_client()

    def mark(self, assessment, enrollment, score):
        return StudentResult.objects.create(
            assessment=assessment, academic_enrollment=enrollment, status=ResultStatus.MARKED,
            score=Decimal(score), entered_by=self.rao)

    def plan(self, include=()):
        return publication.plan_publication(self.term1, self.six_a, include)

    def publish(self, include=()):
        plan = self.plan(include)
        return publication.confirm_publication(term=self.term1, section=self.six_a,
                                               include=include, token=plan["token"],
                                               actor=self.admin)

    def cards(self):
        url = reverse("portal:report-cards", args=[self.asha_grant.public_id])
        return self.portal.get(url).context["publications"]

    def raw(self, sql, params):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, params)


class PreviewAndConfirmTests(PublicationFixture, TestCase):
    def test_finalized_but_unpublished_is_invisible(self):
        self.assertEqual(self.cards(), [])

    def test_preview_lists_exact_content_and_writes_nothing(self):
        plan = self.plan()
        rows = {row["student"]: row for row in plan["rows"]}
        self.assertEqual(rows[self.asha]["action"], publication.PUBLISH)
        self.assertEqual([e["score"] for e in rows[self.asha]["content"]["entries"]],
                         [Decimal("15")])
        self.assertEqual(rows[self.asha]["content"]["remark"]["text"], "Steady progress.")
        self.assertFalse(TermPublication.objects.exists())

    def test_confirm_publishes_and_guardian_sees_snapshot(self):
        created = self.publish()
        self.assertEqual({p.student for p in created}, {self.asha, self.bina})
        cards = self.cards()
        self.assertEqual([p.term for p in cards], [self.term1])
        page = self.portal.get(reverse("portal:report-card",
                                       args=[self.asha_grant.public_id, cards[0].public_id]))
        self.assertContains(page, "UT1")
        self.assertContains(page, "15.00 / 20.00")
        self.assertContains(page, "Steady progress.")
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.TERM_PUBLISHED, event_class="HISTORY").exists())

    def test_confirming_twice_publishes_nothing_new(self):
        plan = self.plan()
        publication.confirm_publication(term=self.term1, section=self.six_a, include=(),
                                        token=plan["token"], actor=self.admin)
        with self.assertRaises(ValidationError):
            publication.confirm_publication(term=self.term1, section=self.six_a, include=(),
                                            token=plan["token"], actor=self.admin)
        self.assertEqual(TermPublication.objects.count(), 2)
        self.assertEqual({row["action"] for row in self.plan()["rows"]}, {publication.SKIP_ALREADY})

    def test_stale_token_writes_nothing(self):
        token = self.plan()["token"]
        self.result.correct(new_status=ResultStatus.MARKED, new_score="16", actor=self.admin,
                            reason="Recount")
        with self.assertRaises(ValidationError):
            publication.confirm_publication(term=self.term1, section=self.six_a, include=(),
                                            token=token, actor=self.admin)
        self.assertFalse(TermPublication.objects.exists())

    def test_incomplete_students_flagged_and_excluded_unless_selected(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))  # DRAFT, both on roster
        rows = {row["student"]: row for row in self.plan()["rows"]}
        self.assertEqual(rows[self.asha]["action"], publication.INCOMPLETE)
        self.assertFalse(rows[self.asha]["selected"])
        with self.assertRaises(ValidationError):
            self.publish()  # nothing selected
        created = self.publish(include=[self.asha.pk])
        self.assertEqual([p.student for p in created], [self.asha])
        self.assertTrue(created[0].is_partial)
        page = self.portal.get(reverse("portal:report-card",
                                       args=[self.asha_grant.public_id, created[0].public_id]))
        self.assertContains(page, "Some results for this Term are not yet published.")

    def test_allowed_before_term_ends(self):
        ut = self.make_assessment(name="Oct test", on=date(2026, 10, 5), term=self.term2)
        self.mark(ut, self.asha_e, "18")
        self.mark(ut, self.bina_e, "12")
        self.force_finalize(ut)
        plan = publication.plan_publication(self.term2, self.six_a)
        created = publication.confirm_publication(term=self.term2, section=self.six_a,
                                                  include=(), token=plan["token"],
                                                  actor=self.admin)
        self.assertEqual(len(created), 2)

    def test_nothing_to_publish_is_skipped(self):
        rows = {row["student"]: row for row in publication.plan_publication(
            self.term2, self.six_a)["rows"]}
        self.assertEqual(rows[self.asha]["action"], publication.SKIP_NOTHING)

    def test_views_preview_and_confirm(self):
        url = reverse("core:term-publication", args=[self.term1.pk])
        page = self.client.get(url, {"section": self.six_a.pk})
        self.assertContains(page, "Will publish")
        self.assertFalse(TermPublication.objects.exists())
        self.client.post(url, {"section": self.six_a.pk, "token": page.context["plan"]["token"]})
        self.assertEqual(TermPublication.objects.count(), 2)

    def test_teacher_cannot_publish(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        url = reverse("core:term-publication", args=[self.term1.pk])
        self.assertEqual(teacher.post(url, {"section": self.six_a.pk}).status_code, 403)
        with self.assertRaises(ValidationError):
            publication.confirm_publication(term=self.term1, section=self.six_a, include=(),
                                            token=self.plan()["token"], actor=self.rao)


class StalenessTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.v1 = next(p for p in self.publish() if p.student == self.asha)

    def test_correction_makes_it_stale_and_hidden(self):
        self.result.correct(new_status=ResultStatus.MARKED, new_score="17", actor=self.admin,
                            reason="Recount")
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, Status.STALE)
        self.assertEqual(self.cards(), [])
        self.assertIn(self.v1, publication.stale_publications())

    def test_republish_creates_v2_and_v1_stays_reconstructable(self):
        self.result.correct(new_status=ResultStatus.MARKED, new_score="17", actor=self.admin,
                            reason="Recount")
        rows = {row["student"]: row for row in self.plan()["rows"]}
        self.assertEqual(rows[self.asha]["action"], publication.REPUBLISH)
        v2 = self.publish()[0]
        self.v1.refresh_from_db()
        self.assertEqual((self.v1.status, v2.version, v2.status),
                         (Status.SUPERSEDED, 2, Status.PUBLISHED))
        self.assertEqual(self.v1.entries.get().score, Decimal("15"))
        self.assertEqual(v2.entries.get().score, Decimal("17"))
        admin_page = self.client.get(reverse("core:publication-detail", args=[self.v1.pk]))
        self.assertContains(admin_page, "15.00 / 20.00")
        self.assertEqual([p.version for p in self.cards()], [2])
        old = reverse("portal:report-card", args=[self.asha_grant.public_id, self.v1.public_id])
        self.assertEqual(self.portal.get(old).status_code, 404)

    def test_remark_change_and_removal_make_it_stale(self):
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.client.post(url, {"section": self.six_a.pk, f"remark_{self.asha.pk}": "Changed."})
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, Status.STALE)

    def test_remark_removal_makes_it_stale(self):
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.client.post(url, {"section": self.six_a.pk, f"remark_{self.asha.pk}": ""})
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, Status.STALE)

    def test_new_remark_where_none_was_released_does_not_stale(self):
        bina_v1 = TermPublication.objects.get(student=self.bina)
        url = reverse("core:term-remarks", args=[self.term1.pk])
        self.client.post(url, {"section": self.six_a.pk,
                               f"remark_{self.asha.pk}": "Steady progress.",
                               f"remark_{self.bina.pk}": "New remark"})
        bina_v1.refresh_from_db()
        self.assertEqual(bina_v1.status, Status.PUBLISHED)

    def test_fingerprint_backstop_hides_silent_changes(self):
        StudentResult.objects.filter(pk=self.result.pk).update(score=Decimal("19"))
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, Status.PUBLISHED)
        self.assertEqual(self.cards(), [])

    def test_withdraw_hides_and_is_final(self):
        publication.withdraw(self.v1, actor=self.admin, reason="Published by mistake")
        self.assertEqual(self.cards(), [])
        with self.assertRaises(ValidationError):
            publication.withdraw(self.v1, actor=self.admin, reason="again")
        with self.assertRaises(IntegrityError):
            self.raw("UPDATE core_termpublication SET status = 'PUBLISHED' WHERE id = %s",
                     [self.v1.pk])


class PublicationHistoryProtectionTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.v1 = next(p for p in self.publish() if p.student == self.asha)

    def test_versions_and_entries_cannot_be_deleted_or_rewritten(self):
        entry = self.v1.entries.get()
        statements = [
            ("DELETE FROM core_termpublication WHERE id = %s", [self.v1.pk]),
            ("UPDATE core_termpublication SET fingerprint = 'x' WHERE id = %s", [self.v1.pk]),
            ("UPDATE core_termpublication SET remark_text = 'x' WHERE id = %s", [self.v1.pk]),
            ("UPDATE core_termpublicationentry SET score = 20 WHERE id = %s", [entry.pk]),
            ("DELETE FROM core_termpublicationentry WHERE id = %s", [entry.pk]),
        ]
        for sql, params in statements:
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                self.raw(sql, params)

    def test_only_one_current_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TermPublication.objects.create(
                student=self.asha, term=self.term1, placement=self.asha_e, version=2,
                term_label="x", academic_year_label="x", class_grade_label="x",
                section_label="x", fingerprint="x", published_by=self.admin)

    def test_other_family_cannot_open_the_card(self):
        bina_v1 = TermPublication.objects.get(student=self.bina)
        url = reverse("portal:report-card", args=[self.asha_grant.public_id, bina_v1.public_id])
        self.assertEqual(self.portal.get(url).status_code, 404)
        url = reverse("portal:report-cards", args=[self.bina_grant.public_id])
        self.assertEqual(self.portal.get(url).status_code, 404)
