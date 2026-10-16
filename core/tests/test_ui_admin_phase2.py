from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core import models as core_models
from core.authorization import user_areas
from core.breadcrumbs import breadcrumb_context
from core.dashboard import overview_cards
from core.models import (
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    SchoolCalendarDay,
)
from core.navigation import office_nav
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin

User = get_user_model()


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

    def _open_today(self):
        """Make today an instructional day whatever the weekday."""
        today = core_models.business_today()
        if not self.year.default_is_instructional(today):
            SchoolCalendarDay.objects.create(
                academic_year=self.year, date=today, is_instructional=True
            )

    def _register_today(self, *, submit=False):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.class_grade,
            section=self.section, date=core_models.business_today(),
        )
        if submit:
            register.capture(
                enrollment=self.enrollment, status=AttendanceStatus.PRESENT
            )
            submitter, _ = User.objects.get_or_create(username="today-submitter")
            register.submit(actor=submitter)
        return register

    def _attendance(self):
        return card(overview_cards(self.admin_user), "attendance")

    def test_attendance_card_counts_section_with_no_register_today(self):
        self._open_today()
        data = self._attendance()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["url"], reverse("core:attendance-register-list"))

    def test_attendance_card_zero_on_non_instructional_day(self):
        today = core_models.business_today()
        SchoolCalendarDay.objects.filter(academic_year=self.year, date=today).delete()
        if self.year.default_is_instructional(today):
            SchoolCalendarDay.objects.create(
                academic_year=self.year, date=today, is_instructional=False
            )
        data = self._attendance()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["detail"], "No school day today.")

    def test_attendance_card_counts_draft_register_as_missing(self):
        self._open_today()
        self._register_today(submit=False)
        self.assertEqual(self._attendance()["count"], 1)

    def test_attendance_card_does_not_count_submitted_register(self):
        self._open_today()
        self._register_today(submit=True)
        self.assertEqual(self._attendance()["count"], 0)

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


class BreadcrumbMapTests(TestCase):
    def match(self, name, **kwargs):
        return resolve(reverse(name, kwargs=kwargs))

    def test_student_detail_has_students_section_and_trail(self):
        ctx = breadcrumb_context(self.match("core:student-detail", pk=7))
        self.assertEqual(ctx["nav_section"], "student-list")
        self.assertEqual(
            [c["label"] for c in ctx["breadcrumbs"]], ["Overview", "Students", "Student"]
        )
        self.assertIsNone(ctx["breadcrumbs"][-1]["url"])

    def test_deactivate_confirm_parent_reuses_pk(self):
        ctx = breadcrumb_context(self.match("core:student-deactivate-confirm", pk=7))
        self.assertEqual(ctx["breadcrumbs"][-2]["url"], reverse("core:student-detail", args=[7]))

    def test_decision_confirm_parent_reuses_pk(self):
        ctx = breadcrumb_context(
            self.match("core:applicant-decision-confirm", pk=3, decision="accepted")
        )
        self.assertEqual(ctx["breadcrumbs"][-2]["url"], reverse("core:applicant-detail", args=[3]))

    def test_unmapped_page_has_no_breadcrumbs(self):
        ctx = breadcrumb_context(self.match("core:subject-list"))
        self.assertEqual(ctx, {"breadcrumbs": [], "nav_section": None})

    def test_none_match_is_safe(self):
        self.assertEqual(breadcrumb_context(None), {"breadcrumbs": [], "nav_section": None})


class SectionAwareNavTests(AuthorizationClientsMixin, TestCase):
    def active_labels(self, groups):
        return [link["label"] for g in groups for link in g["links"] if link["active"]]

    def test_section_marks_parent_link_active(self):
        groups = office_nav(self.admin_user, "student-detail", section="student-list")
        self.assertEqual(self.active_labels(groups), ["Students"])

    def test_exact_match_still_works_without_section(self):
        groups = office_nav(self.admin_user, "student-list")
        self.assertEqual(self.active_labels(groups), ["Students"])


class BreadcrumbRenderingTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Asha Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()

    def test_student_detail_renders_breadcrumb_nav(self):
        response = self.administrator.get(reverse("core:student-detail", args=[self.student.pk]))
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, '<li aria-current="page">Student</li>', html=False)
        self.assertContains(response, reverse("core:student-list"))

    def test_deactivate_confirm_links_back_to_student(self):
        response = self.administrator.get(
            reverse("core:student-deactivate-confirm", args=[self.student.pk])
        )
        self.assertContains(
            response, f'href="{reverse("core:student-detail", args=[self.student.pk])}"'
        )

    def test_overview_page_itself_has_no_breadcrumb(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertNotContains(response, 'aria-label="Breadcrumb"')
