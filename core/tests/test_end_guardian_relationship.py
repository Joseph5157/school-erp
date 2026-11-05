"""Ending a Student-Guardian relationship, which also removes portal access to that child.

An ended relationship stays on the record but must stop counting everywhere. The portal,
notices and alerts all read access grants, so revoking the grant closes those paths; the
pages that list relationships read the link itself, so each is checked here.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core import guardian_accounts as ga
from core.authorization import guardian_grants
from core.models import GuardianStudentAccess, SectionClassTeacher, StudentGuardian
from core.tests.test_phase6_access_boundary import BoundaryFixture


class EndRelationshipFixture(BoundaryFixture):
    def setUp(self):
        super().setUp()
        self.ravi_grant = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        self.url = reverse("core:student-guardian-end", args=[self.asha_link.pk])
        self.detail = reverse("core:student-detail", args=[self.asha.pk])

    def end(self, reason="Linked by mistake"):
        return self.client.post(self.url, {"reason": reason})


class EndingTests(EndRelationshipFixture, TestCase):
    def test_records_who_when_and_why_and_keeps_the_row(self):
        self.assertRedirects(self.end(), self.detail)
        self.asha_link.refresh_from_db()
        self.assertIsNotNone(self.asha_link.ended_at)
        self.assertEqual(self.asha_link.ended_by, self.admin)
        self.assertEqual(self.asha_link.end_reason, "Linked by mistake")

    def test_removes_access_to_that_child_only(self):
        self.end()
        self.asha_grant.refresh_from_db()
        self.ravi_grant.refresh_from_db()
        self.assertFalse(self.asha_grant.is_active)
        self.assertEqual(self.asha_grant.revoked_by, self.admin)
        self.assertIn("Linked by mistake", self.asha_grant.revocation_reason)
        self.assertTrue(self.ravi_grant.is_active)
        self.assertEqual(
            [g.student_guardian.student for g in guardian_grants(self.user)], [self.ravi]
        )

    def test_login_stays_active(self):
        self.end()
        self.account.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(self.account.is_active)
        self.assertTrue(self.user.is_active)

    def test_long_reason_still_fits_the_access_record(self):
        self.assertRedirects(self.end("x" * 200), self.detail)
        self.asha_grant.refresh_from_db()
        self.assertFalse(self.asha_grant.is_active)

    def test_works_with_no_portal_access(self):
        link = self.relate(self.bina, self.meena)
        response = self.client.post(
            reverse("core:student-guardian-end", args=[link.pk]), {"reason": "Wrong person"}
        )
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertIsNotNone(link.ended_at)

    def test_reason_is_required_and_nothing_changes_without_it(self):
        response = self.end("   ")
        self.assertEqual(response.status_code, 200)
        self.asha_link.refresh_from_db()
        self.asha_grant.refresh_from_db()
        self.assertIsNone(self.asha_link.ended_at)
        self.assertTrue(self.asha_grant.is_active)

    def test_opening_the_page_changes_nothing(self):
        self.client.get(self.url)
        self.asha_link.refresh_from_db()
        self.assertIsNone(self.asha_link.ended_at)

    def test_ending_twice_is_refused(self):
        self.end()
        self.asha_link.refresh_from_db()
        first = self.asha_link.ended_at
        self.assertRedirects(self.end("Again"), self.detail)
        self.asha_link.refresh_from_db()
        self.assertEqual(self.asha_link.ended_at, first)
        self.assertEqual(self.asha_link.end_reason, "Linked by mistake")

    def test_blank_reason_is_refused_by_the_workflow_too(self):
        with self.assertRaises(ValidationError):
            ga.end_relationship(link=self.asha_link, actor=self.admin, reason="  ")
        self.asha_grant.refresh_from_db()
        self.assertTrue(self.asha_grant.is_active)


class ConfirmPageTests(EndRelationshipFixture, TestCase):
    def test_states_the_consequences_when_access_exists(self):
        response = self.client.get(self.url)
        for text in ("Meena Rao", "Asha Rao", "portal access to Asha Rao",
                     "Access to their other children", "login stays"):
            self.assertContains(response, text)

    def test_does_not_mention_removing_access_when_there_is_none(self):
        link = self.relate(self.bina, self.meena)
        response = self.client.get(reverse("core:student-guardian-end", args=[link.pk]))
        self.assertNotContains(response, "portal access to Bina Other")
        self.assertContains(response, "no portal access")

    def test_teachers_are_refused(self):
        self.client.logout()
        self.client.force_login(self.rao)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"reason": "x"}).status_code, 403)
        self.asha_link.refresh_from_db()
        self.assertIsNone(self.asha_link.ended_at)


class EndedStopsCountingTests(EndRelationshipFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.end()
        self.asha_link.refresh_from_db()

    def test_student_page_moves_it_to_ended_with_who_and_why(self):
        response = self.client.get(self.detail)
        self.assertEqual(list(response.context["guardian_links"]), [])
        self.assertEqual(list(response.context["ended_links"]), [self.asha_link])
        self.assertContains(response, "Ended relationships")
        self.assertContains(response, "Linked by mistake")
        self.assertNotContains(response, reverse("core:student-guardian-edit", args=[self.asha_link.pk]))
        self.assertNotContains(response, self.url)

    def test_class_teacher_no_longer_sees_the_ended_guardian(self):
        SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        self.relate(self.asha, self.other)
        self.client.logout()
        self.client.force_login(self.rao)
        response = self.client.get(reverse("core:my-student-detail", args=[self.asha.pk]))
        self.assertTrue(response.context["show_guardians"])
        self.assertEqual([link.guardian for link in response.context["guardian_links"]], [self.other])
        self.assertNotContains(response, "Meena Rao")

    def test_student_list_and_search_ignore_it(self):
        response = self.client.get(reverse("core:student-list"), {"q": "Meena"})
        names = [s.full_name for s in response.context["students"]]
        self.assertNotIn("Asha Rao", names)
        self.assertIn("Ravi Rao", names)
        response = self.client.get(reverse("core:student-list"), {"q": "Asha"})
        self.assertEqual(response.context["students"][0].guardian_rows, [])

    def test_guardian_list_and_search_ignore_it(self):
        response = self.client.get(reverse("core:guardian-list"), {"q": "Meena"})
        guardian = response.context["guardians"][0]
        self.assertEqual([link.student for link in guardian.child_links], [self.ravi])
        response = self.client.get(reverse("core:guardian-list"), {"q": "Asha"})
        self.assertNotIn(self.meena, list(response.context["guardians"]))

    def test_guardian_page_shows_it_ended_without_a_grant_button(self):
        response = self.client.get(reverse("core:guardian-detail", args=[self.meena.pk]))
        self.assertContains(response, "Relationship ended")
        self.assertContains(response, "Linked by mistake")
        self.assertNotContains(response, reverse("core:guardian-access-grant", args=[self.asha_link.pk]))

    def test_access_cannot_be_granted_on_it(self):
        with self.assertRaises(ValidationError):
            ga.grant_student_access(student_guardian=self.asha_link, actor=self.admin)
        grant_url = reverse("core:guardian-access-grant", args=[self.asha_link.pk])
        self.assertEqual(self.client.get(grant_url).status_code, 302)
        self.client.post(grant_url)
        self.assertFalse(
            GuardianStudentAccess.objects.filter(
                student_guardian=self.asha_link, revoked_at__isnull=True
            ).exists()
        )

    def test_relationship_type_cannot_be_edited(self):
        url = reverse("core:student-guardian-edit", args=[self.asha_link.pk])
        self.assertRedirects(self.client.get(url), self.detail)
        self.client.post(url, {"relationship_type": "FATHER"})
        self.asha_link.refresh_from_db()
        self.assertEqual(self.asha_link.relationship_type, "MOTHER")

    def test_guardian_can_be_linked_again_with_no_access(self):
        add = reverse("core:student-guardian-add", args=[self.asha.pk])
        response = self.client.get(add, {"q": "Meena"})
        self.assertContains(response, f"guardian={self.meena.pk}")
        response = self.client.post(add, {"guardian": self.meena.pk, "relationship_type": "GUARDIAN"})
        self.assertRedirects(response, self.detail)
        current = self.asha.guardian_links.current().get()
        self.assertNotEqual(current.pk, self.asha_link.pk)
        self.assertFalse(current.access_grants.exists())

    def test_ended_row_cannot_be_changed_or_deleted(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            StudentGuardian.objects.filter(pk=self.asha_link.pk).update(ended_at=None)
        no_grants = self.relate(self.bina, self.meena)
        ga.end_relationship(link=no_grants, actor=self.admin, reason="Wrong person")
        with self.assertRaises(DatabaseError), transaction.atomic():
            no_grants.delete()


class CurrentLinkRulesTests(EndRelationshipFixture, TestCase):
    def test_two_current_links_for_the_same_pair_are_still_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.relate(self.asha, self.meena)

    def test_current_link_still_blocks_a_duplicate_on_the_form(self):
        response = self.client.post(
            reverse("core:student-guardian-add", args=[self.asha.pk]),
            {"guardian": self.meena.pk, "relationship_type": "GUARDIAN"},
        )
        self.assertContains(response, "already associated")

    def test_half_finished_end_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGuardian.objects.filter(pk=self.asha_link.pk).update(end_reason="No date")
