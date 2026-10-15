"""U1 UI foundation: static files, shell, navigation, auth pages, components."""

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from core.models import School
from core.navigation import current_area, office_nav, teacher_tabs
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_phase6_access_boundary import BoundaryFixture

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


class StaticFilesTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def test_tests_use_plain_static_storage(self):
        self.assertEqual(
            settings.STORAGES["staticfiles"]["BACKEND"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )

    def test_admin_login_renders(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_base_links_stylesheet_and_viewport(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertContains(page, VIEWPORT)
        self.assertContains(page, "/static/css/erp.css")
        self.assertContains(page, "/static/js/erp.js")


class NavigationDataTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")

    def titles(self, groups):
        return [group["title"] for group in groups]

    def labels(self, groups):
        return [link["label"] for group in groups for link in group["links"]]

    def area_for(self, user, path):
        request = RequestFactory().get(path)
        request.user = user
        request.resolver_match = resolve(path)
        return current_area(request)

    def test_admin_sees_all_office_groups(self):
        groups = office_nav(self.admin, "school-detail")
        self.assertEqual(
            self.titles(groups),
            ["School setup", "Admissions", "Daily", "Results", "Access and security"],
        )
        self.assertIn("Academic Years", self.labels(groups))
        self.assertIn("Sign-in lockouts", self.labels(groups))

    def test_teacher_sees_no_office_groups(self):
        self.assertEqual(office_nav(self.rao, "my-home"), [])

    def test_links_need_their_permission(self):
        clerk = self.make_user("clerk")
        clerk.user_permissions.add(
            Permission.objects.get(codename="view_student", content_type__app_label="core")
        )
        groups = office_nav(clerk, None)
        self.assertEqual(self.titles(groups), ["Admissions"])
        self.assertEqual(self.labels(groups), ["Students"])

    def test_active_link_follows_url_name(self):
        groups = office_nav(self.admin, "student-list")
        active = [link["label"] for g in groups for link in g["links"] if link["active"]]
        self.assertEqual(active, ["Students"])

    def test_teacher_tabs(self):
        tabs = teacher_tabs("my-assessments")
        self.assertEqual([t["label"] for t in tabs],
                         ["My day", "My students", "My assessments", "Results"])
        self.assertEqual([t["label"] for t in tabs if t["active"]], ["My assessments"])
        self.assertEqual(tabs[0]["url"], reverse("core:my-home"))

    def test_current_area(self):
        self.assertEqual(self.area_for(self.admin, reverse("core:school-detail")), "admin")
        self.assertEqual(self.area_for(self.rao, reverse("core:my-home")), "teacher")
        self.assertEqual(self.area_for(self.rao, reverse("core:my-students")), "teacher")

    def test_current_area_none_for_anonymous(self):
        self.assertIsNone(self.area_for(AnonymousUser(), reverse("login")))

    def test_context_exposes_navigation(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertEqual(page.context["current_area"], "admin")
        self.assertTrue(page.context["office_nav"])
        self.assertEqual(len(page.context["teacher_tabs"]), 4)


class StaffShellTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()
        School.objects.create(name="Greenwood High")  # school-detail redirects without one

    def test_admin_office_page_has_sidebar_and_no_tabbar(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:student-list"))
        self.assertContains(page, 'id="erp-sidebar"')
        self.assertContains(page, reverse("core:academic-year-list"))
        self.assertContains(page, 'aria-current="page"')
        self.assertNotContains(page, 'class="erp-tabbar')

    def test_teacher_page_has_tabbar_and_no_sidebar(self):
        self.client.login(username="rao", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertContains(page, 'class="erp-tabbar')
        self.assertContains(page, "My assessments")
        self.assertContains(page, reverse("core:my-students"))
        self.assertNotContains(page, 'id="erp-sidebar"')

    def test_admin_teacher_sees_sidebar_only_in_office_area(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        office = self.client.get(reverse("core:school-detail"))
        teaching = self.client.get(reverse("core:my-home"))
        self.assertContains(office, 'id="erp-sidebar"')
        self.assertNotContains(office, 'class="erp-tabbar')
        self.assertNotContains(teaching, 'id="erp-sidebar"')
        self.assertContains(teaching, 'class="erp-tabbar')

    def test_anonymous_login_page_has_no_navigation(self):
        page = self.client.get(reverse("login"))
        self.assertNotContains(page, 'id="erp-sidebar"')
        self.assertNotContains(page, 'class="erp-tabbar')

    def test_skip_link_targets_main(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertContains(page, 'href="#main"')
        self.assertContains(page, 'id="main"')


class AccountMenuTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_account_menu_lists_all_areas_and_marks_current(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertContains(page, 'class="erp-account"')
        self.assertContains(page, reverse("core:school-detail"))
        self.assertContains(page, 'aria-current="true"', count=1)
        self.assertContains(page, reverse("password_change"))

    def test_single_area_user_has_no_switch_heading(self):
        self.client.login(username="rao", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertNotContains(page, "Switch to")

    def test_choose_area_page_lists_areas(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("choose-area"))
        self.assertContains(page, "School administration")
        self.assertContains(page, "My day (teaching)")


class GuardianShellTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def portal_url(self, name):
        return reverse(name, args=[self.asha_grant.public_id])

    def test_portal_home_has_only_home_tab(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, 'class="erp-tabbar')
        self.assertNotContains(page, self.portal_url("portal:attendance"))

    def test_child_page_tabs_link_to_that_child(self):
        page = self.portal.get(self.portal_url("portal:child"))
        for name in ("portal:child", "portal:attendance", "portal:report-cards"):
            self.assertContains(page, self.portal_url(name))
        self.assertContains(page, "Report cards")

    def test_portal_pages_still_have_no_excluded_words(self):
        urls = [reverse("portal:home")] + [
            self.portal_url(name)
            for name in ("portal:child", "portal:attendance", "portal:report-cards")
        ]
        for url in urls:
            html = self.portal.get(url).content.decode().lower()
            for word in ("fee", "announcement", "pdf", "download"):
                self.assertNotIn(word, html, f"{word!r} found on {url}")
            self.assertNotIn(f"/students/{self.asha.pk}/", html)

    def test_portal_has_viewport_and_stylesheet(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, VIEWPORT)
        self.assertContains(page, "/static/css/erp.css")


class AuthPageTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_login_page_fields(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, ">Username</label>")
        self.assertContains(page, 'autocomplete="username"')
        self.assertContains(page, 'autocomplete="current-password"')
        self.assertContains(page, "data-erp-toggle-password")
        self.assertContains(page, "Ask the school office")

    def test_login_keeps_next(self):
        target = reverse("core:student-list")
        page = self.client.get(reverse("login") + f"?next={target}")
        self.assertContains(page, f'name="next" value="{target}"')
        response = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "pass-12345", "next": target},
        )
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_login_error_is_shown_once(self):
        page = self.client.post(reverse("login"), {"username": "admin", "password": "wrong"})
        self.assertContains(page, "The username or password is incorrect", count=1)
        self.assertContains(page, 'role="alert"')

    def test_password_change_page(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, 'autocomplete="current-password"', count=1)
        self.assertContains(page, 'autocomplete="new-password"', count=2)
        self.assertContains(page, "data-erp-toggle-password", count=3)

    def test_forced_change_notice(self):
        self.admin.must_change_password = True
        self.admin.save(update_fields=["must_change_password"])
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, "You must choose a new password before you continue.")
