from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core import guardian_accounts as ga
from core import models as core_models
from core.dashboard import glance_cards, parents_glance
from core.models import (
    TEACHERS_GROUP_NAME,
    AcademicTerm,
    Applicant,
    ClassGrade,
    Guardian,
)
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin

User = get_user_model()


def by_key(cards):
    return {c["key"]: c for c in cards}


class GlanceEmptySchoolTests(AuthorizationClientsMixin, TestCase):
    def test_empty_school_shows_zeros_and_dash_for_the_term(self):
        cards = by_key(glance_cards(self.superuser))
        self.assertEqual(
            [c["key"] for c in glance_cards(self.superuser)],
            ["students", "teachers", "classes", "term"],
        )
        for key in ("students", "teachers", "classes"):
            self.assertEqual(cards[key]["count"], 0)
        self.assertEqual(cards["term"]["count"], "-")
        self.assertEqual(cards["term"]["summary"], "No term is running today.")
        self.assertEqual(parents_glance(self.superuser)["count"], 0)

    def test_overview_renders_glance_section_on_empty_school(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "School at a glance")
        self.assertContains(response, "erp-stat-card--glance", count=4)


class GlanceCountTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_counts_on_seeded_fixture(self):
        # An inactive student, an inactive teacher, a second class and a revoked guardian
        # login must not be counted as active.
        applicant = Applicant.objects.create(full_name="Gone Away")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        gone = applicant.progress_to_student()
        gone.status = core_models.Student.Status.INACTIVE
        gone.save()
        teachers = Group.objects.get_or_create(name=TEACHERS_GROUP_NAME)[0]
        active = User.objects.create_user(username="t.active", password="x")
        active.groups.add(teachers)
        inactive = User.objects.create_user(username="t.inactive", password="x", is_active=False)
        inactive.groups.add(teachers)
        ClassGrade.objects.create(name="Grade 2")
        guardian = Guardian.objects.create(full_name="Meena Rao")
        ga.create_guardian_account(
            guardian=guardian, username="meena.rao",
            method="IN_PERSON_DOCUMENTS", note="Aadhaar card seen", actor=self.admin_user,
        )
        other = Guardian.objects.create(full_name="Old Parent")
        old, _ = ga.create_guardian_account(
            guardian=other, username="old.parent",
            method="IN_PERSON_DOCUMENTS", note="Aadhaar card seen", actor=self.admin_user,
        )
        ga.revoke_account_link(account=old, actor=self.admin_user, reason="Left school")

        cards = by_key(glance_cards(self.superuser))

        self.assertEqual(cards["students"]["count"], 1)
        self.assertEqual(cards["teachers"]["count"], 1)
        self.assertEqual(cards["classes"]["count"], 2)
        self.assertEqual(parents_glance(self.superuser)["count"], 1)

    def test_term_card_names_the_term_running_today(self):
        AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 6, 1),
            end_date=date(2026, 9, 30), display_order=1,
        )
        card = by_key(glance_cards(self.superuser, today=date(2026, 7, 14)))["term"]
        self.assertEqual((card["count"], card["summary"]), ("Term 1", "Running today."))
        between = by_key(glance_cards(self.superuser, today=date(2026, 10, 5)))["term"]
        self.assertEqual((between["count"], between["summary"]), ("-", "No term is running today."))

    def test_page_shows_counts(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "School at a glance")
        self.assertContains(response, "erp-stat-card--glance", count=4)


class GlanceLinkPermissionTests(AuthorizationClientsMixin, TestCase):
    def test_links_present_for_administrator(self):
        cards = by_key(glance_cards(self.admin_user))
        self.assertEqual(cards["students"]["url"], reverse("core:student-list"))
        self.assertEqual(cards["teachers"]["url"], reverse("core:teacher-list"))
        self.assertEqual(cards["classes"]["url"], reverse("core:class-grade-list"))
        self.assertEqual(cards["term"]["url"], reverse("core:academic-year-list"))
        self.assertEqual(parents_glance(self.admin_user)["url"], reverse("core:guardian-list"))

    def test_only_permitted_links_are_given(self):
        user = User.objects.create_user(username="limited", password="x")
        user.user_permissions.add(Permission.objects.get(codename="view_student"))
        cards = by_key(glance_cards(user))
        self.assertEqual(cards["students"]["url"], reverse("core:student-list"))
        for key in ("teachers", "classes", "term"):
            self.assertEqual(cards[key]["url"], "")
        self.assertEqual(parents_glance(user)["url"], "")
