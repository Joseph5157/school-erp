from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core import models as core_models
from core.authorization import user_areas
from core.breadcrumbs import breadcrumb_context
from core.dashboard import overview_cards, split_cards
from core.models import (
    TEACHERS_GROUP_NAME,
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    School,
    SchoolCalendarDay,
    SectionClassTeacher,
    Subject,
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

    def pin_today_before_year(self):
        """The fixture's year runs 2026-06-01 to 2027-04-30; tests that expect an empty Overview
        pin "today" before it so they do not depend on the real date (a school day with no
        register adds an attention card)."""
        patcher = mock.patch.object(core_models, "business_today", return_value=date(2026, 5, 1))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_applicants_card_counts_only_pending(self):
        Applicant.objects.create(full_name="Pending One")
        accepted = Applicant.objects.create(full_name="Done")
        accepted.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        data = card(overview_cards(self.admin_user), "applicants")

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["url"], reverse("core:applicant-list") + "?status=PENDING")

    def test_split_puts_waiting_cards_first_and_keeps_order_in_each_group(self):
        self.pin_today_before_year()
        Applicant.objects.create(full_name="Pending One")
        cards = overview_cards(self.admin_user)
        attention, clear = split_cards(cards)
        self.assertEqual([c["key"] for c in attention], ["applicants"])
        self.assertTrue(all(c["count"] == 0 for c in clear))
        self.assertEqual(
            [c["key"] for c in clear], [c["key"] for c in cards if c["key"] != "applicants"],
        )

    def test_page_shows_waiting_card_in_full_and_zero_cards_as_links(self):
        self.pin_today_before_year()
        Applicant.objects.create(full_name="Pending One")
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "Needs attention")
        self.assertContains(response, "erp-stat-card--attention", count=1)
        self.assertContains(response, 'class="erp-clear-row"')
        content = response.content.decode()
        clear_html = content[content.index('class="erp-clear-row"'):]
        self.assertIn(f'href="{reverse("core:report-missing-attendance")}', clear_html)
        self.assertNotIn("Applicants awaiting decision", clear_html)
        self.assertEqual(content.count("btn btn-primary btn-sm mt-auto"), 1)

    def test_page_says_all_clear_when_every_card_is_zero(self):
        self.pin_today_before_year()
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "Nothing needs attention today.")
        self.assertNotContains(response, "erp-stat-card--attention")
        self.assertContains(response, 'class="erp-clear-row"')

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
        today = core_models.business_today()
        self.assertEqual(
            data["url"],
            reverse("core:report-missing-attendance")
            + f"?start={today:%Y-%m-%d}&end={today:%Y-%m-%d}",
        )

    def test_attendance_card_link_lists_the_counted_section(self):
        self._open_today()
        url = self._attendance()["url"]
        response = self.administrator.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.section))

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

        # A fully set-up school, so the "Set up your school" checklist is
        # hidden and the empty-state copy is the only thing left to render.
        School.objects.create(name="Greenwood High")
        Subject.objects.create(name="Mathematics")
        teacher = User.objects.create_user(username="rao", password="pass-12345")
        teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        SectionClassTeacher.assign(
            teacher=teacher, academic_year=self.year, section=self.section,
            start_date=date(2026, 6, 1),
        )

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

    def test_brand_new_school_shows_setup_before_cards(self):
        content = self.administrator.get(reverse("core:admin-overview")).content.decode()
        self.assertLess(content.index("Set up your school"), content.index("Applicants awaiting decision"))

    def test_cards_precede_checklist_once_the_foundation_exists(self):
        # foundation_incomplete has its own unit tests; here only the page order is under test.
        with mock.patch("core.views.setup_checklist.foundation_incomplete", return_value=False):
            content = self.administrator.get(reverse("core:admin-overview")).content.decode()
        self.assertLess(content.index("Applicants awaiting decision"), content.index("Set up your school"))

    def test_checklist_lists_only_open_steps_and_folds_the_done_ones(self):
        School.objects.create(name="Greenwood High")
        response = self.administrator.get(reverse("core:admin-overview"))
        content = response.content.decode()
        self.assertContains(response, 'class="erp-setup-done"')
        self.assertContains(response, " completed steps</summary>")
        done_html = content[content.index('class="erp-setup-done"'):]
        open_html = content[content.index('class="erp-setup-list"'):content.index('class="erp-setup-done"')]
        self.assertIn("School profile", done_html)
        self.assertNotIn("School profile", open_html)
        self.assertEqual(open_html.count("btn-primary"), 1)  # only the next step is filled


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
