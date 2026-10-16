from django.test import TestCase
from django.urls import reverse

from core.authorization import user_areas
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin


class OverviewLandingTests(AuthorizationClientsMixin, TestCase):
    def test_admin_home_redirects_to_overview(self):
        response = self.administrator.get(reverse("home"))
        self.assertRedirects(
            response, reverse("core:admin-overview"), fetch_redirect_response=False
        )

    def test_overview_renders_for_admin_with_sidebar_link(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:admin-overview"))
        self.assertContains(response, "Overview")

    def test_overview_refuses_non_admin_and_anonymous(self):
        url = reverse("core:admin-overview")
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(url), f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )

    def test_admin_area_lands_on_overview(self):
        areas = {key: url for key, _, url in user_areas(self.admin_user)}
        self.assertEqual(areas["admin"], "core:admin-overview")


class OverviewMultiRoleTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_admin_who_is_also_teacher_still_chooses_area(self):
        self.rao.groups.add(self.admins)
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        self.assertRedirects(
            client.get(reverse("home")), reverse("choose-area"),
            fetch_redirect_response=False,
        )


from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from core.dashboard import overview_cards
from core import models as core_models
from core.models import Applicant, AttendanceRegister
from core.tests.test_authorization import AttendanceFixtureMixin

User = get_user_model()


def card(cards, key):
    return next((c for c in cards if c["key"] == key), None)


class OverviewCardTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_applicants_card_counts_only_pending(self):
        Applicant.objects.create(full_name="Pending One")
        accepted = Applicant.objects.create(full_name="Done")
        accepted.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        data = card(overview_cards(self.admin_user), "applicants")

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["url"], reverse("core:applicant-list"))

    def test_applicants_card_clear_when_none_pending(self):
        data = card(overview_cards(self.admin_user), "applicants")
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["tone"], "clear")

    def test_attendance_card_counts_sections_without_register_today(self):
        before = card(overview_cards(self.admin_user), "attendance")["count"]
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.class_grade,
            section=self.section, date=core_models.business_today(),
        )
        after = card(overview_cards(self.admin_user), "attendance")
        self.assertEqual(after["count"], before - 1)
        self.assertEqual(after["url"], reverse("core:attendance-register-list"))

    def test_page_shows_cards_and_empty_copy(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "Applicants awaiting decision")
        self.assertContains(response, "Nothing waiting")

    def test_card_hidden_without_source_permission(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        self.assertEqual(overview_cards(User.objects.get(pk=user.pk)), [])
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        response = client.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to show for your role")


class OverviewSetupStateTests(AuthorizationClientsMixin, TestCase):
    def test_brand_new_school_shows_setup_state(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up your school")
        self.assertContains(response, reverse("core:academic-year-list"))
