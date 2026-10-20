"""U4-3A: explicit curriculum order on subject offerings, frozen into future publications."""

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from core import publication
from core.models import (
    AcademicSubjectOffering,
    AcademicYear,
    ClassGrade,
    ResultStatus,
    StudentResult,
    Subject,
)
from core.tests.test_phase6_publication import PublicationFixture


class OrderFixture(PublicationFixture):
    """Grade 6 / 2026-27 with Mathematics (from the base fixture), Telugu and English."""

    def setUp(self):
        super().setUp()
        self.telugu = self.offer("Telugu")
        self.english = self.offer("English")

    def offer(self, name, year=None, grade=None):
        return AcademicSubjectOffering.objects.create(
            academic_year=year or self.year, class_grade=grade or self.grade6,
            subject=Subject.objects.get_or_create(name=name)[0])

    def order(self, mapping):
        """Configure positions by Subject name; unmentioned offerings move out of the way."""
        offerings = {
            o.subject.name: o for o in AcademicSubjectOffering.objects.filter(
                academic_year=self.year, class_grade=self.grade6).select_related("subject")}
        AcademicSubjectOffering.objects.filter(
            pk__in=[o.pk for o in offerings.values()]
        ).update(display_order=F("display_order") + 100)
        for name, position in mapping.items():
            AcademicSubjectOffering.objects.filter(pk=offerings[name].pk).update(
                display_order=position)

    def finalized_result(self, offering, name, on, term=None):
        assessment = self.make_assessment(
            offering=offering, section=self.six_a, term=term, name=name, on=on)
        StudentResult.objects.create(
            assessment=assessment, academic_enrollment=self.asha_e,
            status=ResultStatus.MARKED, score=Decimal("10"), entered_by=self.rao)
        self.force_finalize(assessment)
        return assessment

    def entries(self, publication_obj):
        return list(publication_obj.entries.order_by("display_order").values_list(
            "subject_label", "display_order"))


class BackfillTests(OrderFixture, TestCase):
    """Migration 0082 rule: per (year, grade), 1..n in Subject name order, id as tie-break."""

    def run_backfill(self):
        module = importlib.import_module(
            "core.migrations.0082_backfill_subject_offering_display_order")
        module.assign_order(apps, None)

    def test_numbers_each_grade_and_year_separately_in_subject_name_order(self):
        grade7 = ClassGrade.objects.create(name="Grade 7")
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31))
        self.offer("Zoology", grade=grade7)
        self.offer("Art", grade=grade7)
        self.offer("Telugu", year=next_year)
        # Scramble the stored values (outside 1..n so nothing collides), then recompute.
        AcademicSubjectOffering.objects.update(display_order=F("id") + 500)

        self.run_backfill()

        def positions(**filters):
            return [
                (o.subject.name, o.display_order)
                for o in AcademicSubjectOffering.objects.filter(**filters)
                .select_related("subject").order_by("display_order")]

        self.assertEqual(
            positions(academic_year=self.year, class_grade=self.grade6),
            [("English", 1), ("Mathematics", 2), ("Sanskrit", 3), ("Telugu", 4)])
        self.assertEqual(positions(class_grade=grade7), [("Art", 1), ("Zoology", 2)])
        self.assertEqual(positions(academic_year=next_year), [("Telugu", 1)])

    def test_is_deterministic_and_idempotent(self):
        AcademicSubjectOffering.objects.update(display_order=F("id") + 500)
        self.run_backfill()
        first = list(AcademicSubjectOffering.objects.order_by("pk").values_list(
            "pk", "display_order"))
        self.run_backfill()
        self.assertEqual(
            list(AcademicSubjectOffering.objects.order_by("pk").values_list(
                "pk", "display_order")), first)

    def test_does_not_touch_published_snapshots(self):
        created = self.publish()
        before = [self.entries(p) for p in created]
        AcademicSubjectOffering.objects.update(display_order=F("id") + 500)
        self.run_backfill()
        self.assertEqual([self.entries(p) for p in created], before)


class ValidationTests(OrderFixture, TestCase):
    def test_new_offering_without_order_goes_last_in_its_grade(self):
        self.assertEqual(
            sorted(AcademicSubjectOffering.objects.filter(class_grade=self.grade6)
                   .values_list("display_order", flat=True)), [1, 2, 3, 4])
        grade7 = ClassGrade.objects.create(name="Grade 7")
        self.assertEqual(self.offer("Telugu", grade=grade7).display_order, 1)

    def test_order_must_be_positive(self):
        self.telugu.display_order = 0
        with self.assertRaises(ValidationError) as caught:
            self.telugu.full_clean()
        self.assertIn("display_order", caught.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicSubjectOffering.objects.filter(pk=self.telugu.pk).update(display_order=0)

    def test_duplicate_order_within_grade_and_year_is_rejected(self):
        self.telugu.display_order = self.english.display_order
        with self.assertRaises(ValidationError) as caught:
            self.telugu.full_clean()
        self.assertIn("already used by English", caught.exception.message_dict["display_order"][0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicSubjectOffering.objects.filter(pk=self.telugu.pk).update(
                display_order=self.english.display_order)

    def test_same_number_is_fine_in_another_grade_or_year(self):
        grade7 = ClassGrade.objects.create(name="Grade 7")
        next_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31))
        self.assertEqual(self.offer("Telugu", grade=grade7).display_order, 1)
        self.assertEqual(self.offer("Telugu", year=next_year).display_order, 1)


class AdminConfigurationTests(OrderFixture, TestCase):
    def update(self, offering, **data):
        return self.client.post(
            reverse("core:offering-update", args=[offering.pk]), {"sections": [], **data})

    def test_edit_page_shows_current_order_and_explains_it(self):
        page = self.client.get(reverse("core:offering-update", args=[self.telugu.pk]))
        self.assertContains(page, "Report card position")
        self.assertContains(page, "first language, second language, third language")
        self.assertEqual(page.context["form"].fields["display_order"].initial,
                         self.telugu.display_order)

    def test_admin_can_edit_order(self):
        response = self.update(self.telugu, display_order=9)
        self.assertRedirects(
            response, reverse("core:academic-year-offerings", args=[self.year.pk]))
        self.telugu.refresh_from_db()
        self.assertEqual(self.telugu.display_order, 9)

    def test_taken_position_is_rejected_with_a_clear_message(self):
        original = self.telugu.display_order
        response = self.update(self.telugu, display_order=self.english.display_order)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already used by English")
        self.telugu.refresh_from_db()
        self.assertEqual(self.telugu.display_order, original)

    def test_blank_keeps_current_and_zero_is_rejected(self):
        original = self.telugu.display_order
        self.update(self.telugu, display_order="")
        self.update(self.telugu, display_order=0)
        self.telugu.refresh_from_db()
        self.assertEqual(self.telugu.display_order, original)

    def test_create_accepts_an_explicit_position_or_defaults_to_last(self):
        subject_a = Subject.objects.create(name="Hindi")
        subject_b = Subject.objects.create(name="Art")
        url = reverse("core:offering-create", args=[self.year.pk])
        self.client.post(url, {"class_grade": self.grade6.pk, "subject": subject_a.pk,
                               "display_order": 50})
        self.client.post(url, {"class_grade": self.grade6.pk, "subject": subject_b.pk})
        orders = dict(AcademicSubjectOffering.objects.filter(
            subject__in=[subject_a, subject_b]).values_list("subject__name", "display_order"))
        self.assertEqual(orders, {"Hindi": 50, "Art": 51})

    def test_listing_is_in_report_card_order(self):
        self.order({"Telugu": 1, "English": 2, "Mathematics": 3, "Sanskrit": 4})
        page = self.client.get(reverse("core:academic-year-offerings", args=[self.year.pk]))
        self.assertEqual([o.subject.name for o in page.context["offerings"]],
                         ["Telugu", "English", "Mathematics", "Sanskrit"])
        self.assertContains(page, "Report card position")


class PublicationSnapshotTests(OrderFixture, TestCase):
    def setUp(self):
        super().setUp()
        # Alphabetical would be English, Mathematics, Telugu; the school wants this instead.
        self.order({"Telugu": 1, "English": 2, "Mathematics": 3})
        self.finalized_result(self.telugu, "Telugu UT1", date(2026, 7, 16))
        self.finalized_result(self.english, "English UT1", date(2026, 7, 17))

    def asha_card(self, created):
        return next(p for p in created if p.student == self.asha)

    def test_snapshot_follows_configured_order_not_the_alphabet(self):
        card = self.asha_card(self.publish())
        entries = self.entries(card)
        self.assertEqual([label for label, _ in entries], ["Telugu", "English", "Mathematics"])
        self.assertEqual([position for _, position in entries], sorted(p for _, p in entries))

    def test_released_card_is_unchanged_when_the_order_is_edited_later(self):
        """Acceptance: configure -> publish -> snapshot -> change order -> old card keeps it."""
        card = self.asha_card(self.publish())
        before = self.entries(card)
        self.assertEqual([label for label, _ in before], ["Telugu", "English", "Mathematics"])

        self.order({"Mathematics": 1, "English": 2, "Telugu": 3})  # school reorders later

        card.refresh_from_db()
        self.assertEqual(self.entries(card), before)
        # Still the current, visible card: no stale mark, nothing to republish.
        self.assertEqual([p.pk for p in self.cards()], [card.pk])
        self.assertEqual({row["action"] for row in self.plan()["rows"]}, {publication.SKIP_ALREADY})
        page = self.portal.get(reverse(
            "portal:report-card", args=[self.asha_grant.public_id, card.public_id]))
        labels = [e.subject_label for e in page.context["entries"]]
        self.assertEqual(labels, ["Telugu", "English", "Mathematics"])

    def test_later_publications_use_the_changed_order(self):
        old = self.asha_card(self.publish())
        self.order({"Mathematics": 1, "English": 2, "Telugu": 3})
        for offering, name, day in ((self.telugu, "Telugu T2", 5), (self.english, "English T2", 6)):
            self.finalized_result(offering, name, date(2026, 10, day), term=self.term2)
        self.finalized_result(self.maths, "Maths T2", date(2026, 10, 7), term=self.term2)
        plan = publication.plan_publication(self.term2, self.six_a, ())
        created = publication.confirm_publication(
            term=self.term2, section=self.six_a, include=(), token=plan["token"],
            actor=self.admin)
        new = self.asha_card(created)
        self.assertEqual([label for label, _ in self.entries(new)],
                         ["Mathematics", "English", "Telugu"])
        self.assertEqual([label for label, _ in self.entries(old)],
                         ["Telugu", "English", "Mathematics"])

    def test_marks_percentages_and_grades_are_not_affected(self):
        card = self.asha_card(self.publish())
        telugu = card.entries.get(subject_label="Telugu")
        self.assertEqual((telugu.score, telugu.maximum_marks), (Decimal("10.00"), Decimal("20.00")))
        self.assertEqual(telugu.percentage, Decimal("50.00"))
