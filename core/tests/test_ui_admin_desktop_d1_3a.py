"""UI-D1-3A: Applicants, Guardians and Teachers lists adopt the shared panel/toolbar; data and access unchanged.

All names, phones and emails are synthetic.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.models import Applicant, Guardian
from core.tests.phase4_fixtures import Phase4Fixture

LONG_NAME = "Venkataraghavan Subramaniam Ramachandran-Krishnamurthy Iyengar"


class D13AFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.client.login(username="admin", password="pass-12345")
        self.applicants_url = reverse("core:applicant-list")
        self.guardians_url = reverse("core:guardian-list")
        self.teachers_url = reverse("core:teacher-list")

    def client_with(self, username, *codenames):
        user = self.make_user(username)
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def assert_panel_shell(self, content, label, columns):
        self.assertIn('class="erp-page-header"', content)
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn('class="erp-panel"', content)
        self.assertIn(f'role="region" aria-label="{label}" tabindex="0"', content)
        self.assertEqual(content.count("<th scope=\"col\""), columns)
        self.assertNotIn("<th>", content)


class ApplicantListTests(D13AFixture, TestCase):
    def setUp(self):
        super().setUp()
        Applicant.objects.create(full_name="Asha Testfield", admission_status="PENDING")
        Applicant.objects.create(full_name="Bala Sample", admission_status="ACCEPTED")
        Applicant.objects.create(full_name=LONG_NAME, admission_status="REJECTED")

    def test_shell_and_toolbar(self):
        content = self.client.get(self.applicants_url).content.decode()
        self.assert_panel_shell(content, "Applicants", 2)
        self.assertIn('class="erp-toolbar"', content)
        self.assertIn('<label for="applicant-status" class="form-label">Admission status</label>', content)
        self.assertNotIn("input-group", content)

    def test_filter_returns_same_rows(self):
        content = self.client.get(self.applicants_url, {"status": "ACCEPTED"}).content.decode()
        self.assertIn("Bala Sample", content)
        self.assertNotIn("Asha Testfield", content)
        self.assertIn('<option value="ACCEPTED" selected>', content)
        self.assertIn("Clear filters", content)

    def test_sort_state_kept_in_hidden_input(self):
        content = self.client.get(self.applicants_url, {"status": "ACCEPTED", "sort": "-name"}).content.decode()
        self.assertIn('<input type="hidden" name="sort" value="-name">', content)

    def test_pagination_keeps_filter(self):
        for i in range(30):
            Applicant.objects.create(full_name=f"Pending Person {i:02d}", admission_status="PENDING")
        content = self.client.get(self.applicants_url, {"status": "PENDING"}).content.decode()
        self.assertRegex(content, r'href="[^"]*status=PENDING[^"]*page=2')
        self.assertIn("1–25 of 31", content)

    def test_empty_and_filtered_empty_states(self):
        Applicant.objects.all().delete()
        content = self.client.get(self.applicants_url).content.decode()
        self.assertIn("No Applicants yet.", content)
        self.assertIn(f'href="{reverse("core:applicant-create")}">Register applicant', content)
        # Wording is deliberately unchanged from before D1-3A (pinned by phase 3a); the footer offers Clear filters.
        content = self.client.get(self.applicants_url, {"status": "ACCEPTED"}).content.decode()
        self.assertIn("No Applicants yet.", content)
        self.assertIn("No results", content)
        self.assertIn("Clear filters", content)

    def test_long_name_is_not_truncated(self):
        self.assertIn(LONG_NAME, self.client.get(self.applicants_url).content.decode())

    def test_register_action_only_with_add_permission(self):
        create = reverse("core:applicant-create")
        viewer = self.client_with("viewer", "view_applicant")
        self.assertNotIn(create, viewer.get(self.applicants_url).content.decode())
        Applicant.objects.all().delete()
        self.assertNotIn(create, viewer.get(self.applicants_url).content.decode())
        self.assertIn(create, self.client.get(self.applicants_url).content.decode())

    def test_route_still_requires_view_permission(self):
        self.assertEqual(self.client_with("nobody").get(self.applicants_url).status_code, 403)
        self.assertEqual(self.client_class().get(self.applicants_url).status_code, 302)


class GuardianListTests(D13AFixture, TestCase):
    def setUp(self):
        super().setUp()
        Guardian.objects.create(full_name="Zed Example", phone="555-0100", email="zed@example.test")
        Guardian.objects.create(full_name="Amy Example")
        Guardian.objects.create(full_name=LONG_NAME, email="long@example.test")

    def test_shell_and_rows_in_supplied_order(self):
        response = self.client.get(self.guardians_url)
        content = response.content.decode()
        self.assert_panel_shell(content, "Guardians", 4)
        self.assertEqual(
            [g.pk for g in response.context["guardians"]], [g.pk for g in Guardian.objects.all()]
        )
        self.assertIn(LONG_NAME, content)
        self.assertIn("555-0100", content)
        self.assertIn('id="guardian-search"', content)  # working search by parent or child

    def test_paginates_25_per_page_with_count_footer(self):
        for i in range(30):
            Guardian.objects.create(full_name=f"Carer {i:02d}")
        response = self.client.get(self.guardians_url)
        self.assertEqual(len(response.context["guardians"]), 25)
        self.assertIn("Showing 1–25 of 33", response.content.decode())
        page2 = self.client.get(self.guardians_url, {"page": 2})
        self.assertEqual(len(page2.context["guardians"]), 8)
        self.assertIn("Showing 26–33 of 33", page2.content.decode())

    def test_name_sort_toggles_and_page_resets(self):
        for i in range(30):
            Guardian.objects.create(full_name=f"Carer {i:02d}")
        content = self.client.get(self.guardians_url, {"page": 2}).content.decode()
        self.assertIn('href="?sort=-name"', content)
        self.assertIn('aria-sort="ascending"', content)
        desc = self.client.get(self.guardians_url, {"sort": "-name"})
        names = [g.full_name for g in desc.context["guardians"]]
        self.assertEqual(names, sorted(names, reverse=True))
        self.assertIn('aria-sort="descending"', desc.content.decode())
        self.assertNotIn("page=", desc.content.decode().split("<thead")[1].split("</thead>")[0])

    def test_out_of_range_page_clamps_and_bad_sort_ignored(self):
        for i in range(30):
            Guardian.objects.create(full_name=f"Carer {i:02d}")
        response = self.client.get(self.guardians_url, {"page": 99, "sort": "bogus"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["guardians"].number, 2)
        self.assertEqual(self.client.get(self.guardians_url, {"page": "x"}).status_code, 200)

    def test_create_action_moves_to_header_under_add_permission(self):
        create = reverse("core:guardian-create")
        content = self.client.get(self.guardians_url).content.decode()
        header = content.split('class="erp-page-header"')[1].split("</header>")[0]
        self.assertIn(f'<a class="btn btn-primary" href="{create}">Create Guardian</a>', header)
        self.assertEqual(content.count(">Create Guardian<"), 1)
        viewer = self.client_with("viewer", "view_guardian")
        response = viewer.get(self.guardians_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(create, response.content.decode())

    def test_review_and_lockout_links_keep_exact_predicates(self):
        reviews = reverse("core:guardian-access-reviews")
        lockouts = reverse("core:login-lockouts")
        content = self.client.get(self.guardians_url).content.decode()
        self.assertIn(reviews, content)
        self.assertIn(lockouts, content)
        plain = self.client_with("v1", "view_guardian").get(self.guardians_url).content.decode()
        self.assertNotIn(reviews, plain)
        self.assertNotIn(lockouts, plain)
        reviewer = self.client_with("v2", "view_guardian", "view_guardianaccessreview")
        content = reviewer.get(self.guardians_url).content.decode()
        self.assertIn(reviews, content)
        self.assertNotIn(lockouts, content)
        # the lockout link is nested under the reviews permission
        lock_only = self.client_with("v3", "view_guardian", "clear_login_lockout")
        content = lock_only.get(self.guardians_url).content.decode()
        self.assertNotIn(reviews, content)
        self.assertNotIn(lockouts, content)

    def test_empty_state(self):
        Guardian.objects.all().delete()
        content = self.client.get(self.guardians_url).content.decode()
        self.assertIn("No Guardians yet.", content)
        self.assertIn(">Add guardian<", content)
        viewer = self.client_with("viewer", "view_guardian")
        self.assertNotIn(">Add guardian<", viewer.get(self.guardians_url).content.decode())

    def test_route_still_requires_view_permission(self):
        self.assertEqual(self.client_with("nobody").get(self.guardians_url).status_code, 403)


class TeacherListTests(D13AFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.rao = self.make_user(
            "tsample", self.teachers, first_name="Tsample", last_name="Sample", email="tsample@example.test")
        self.iyer = self.make_user(
            "usample", self.teachers, first_name="Usample", last_name="Sample", is_active=False)
        first, _, last = LONG_NAME.partition(" ")
        self.make_user("longname", self.teachers, first_name=first, last_name=last)

    def test_shell_and_toolbar(self):
        content = self.client.get(self.teachers_url).content.decode()
        self.assert_panel_shell(content, "Teachers", 6)
        self.assertIn('role="search"', content)
        self.assertIn('<label for="teacher-search" class="form-label">Search teachers</label>', content)
        self.assertIn('<label for="teacher-status" class="form-label">Status</label>', content)
        self.assertNotIn("input-group", content)

    def test_search_and_status_semantics_unchanged(self):
        rao = reverse("core:teacher-detail", args=[self.rao.pk])
        iyer = reverse("core:teacher-detail", args=[self.iyer.pk])
        content = self.client.get(self.teachers_url, {"q": "tsample"}).content.decode()
        self.assertIn(rao, content)
        self.assertNotIn(iyer, content)
        self.assertIn('value="tsample"', content)
        content = self.client.get(self.teachers_url, {"status": "inactive"}).content.decode()
        self.assertIn(iyer, content)
        self.assertNotIn(rao, content)
        self.assertIn("Inactive", content)
        self.assertIn("Clear filters", content)

    def test_sort_and_filter_survive_pagination(self):
        for i in range(30):
            self.make_user(f"extra{i:02d}", self.teachers, first_name="Extra", last_name=f"T{i:02d}")
        content = self.client.get(self.teachers_url, {"q": "extra", "sort": "-name"}).content.decode()
        self.assertIn('<input type="hidden" name="sort" value="-name">', content)
        self.assertRegex(content, r'href="[^"]*q=extra[^"]*page=2')

    def test_empty_and_filtered_empty_states(self):
        content = self.client.get(self.teachers_url, {"q": "nobody-matches"}).content.decode()
        self.assertIn("No teachers yet.", content)  # wording unchanged from before D1-3A
        self.assertIn("Clear filters", content)
        get_user_model().objects.filter(groups=self.teachers).delete()
        content = self.client.get(self.teachers_url).content.decode()
        self.assertIn("No teachers yet.", content)
        self.assertIn(f'href="{reverse("core:teacher-create")}">Add teacher', content)

    def test_long_name_visible_and_header_action_unchanged(self):
        content = self.client.get(self.teachers_url).content.decode()
        self.assertIn(LONG_NAME, content)
        header = content.split('class="erp-page-header"')[1].split("</header>")[0]
        self.assertIn(f'href="{reverse("core:teacher-create")}">Add teacher</a>', header)

    def test_route_requires_manage_teacher_accounts(self):
        self.assertEqual(self.client_with("nobody", "view_applicant").get(self.teachers_url).status_code, 403)
        manager = self.client_with("mgr", "manage_teacher_accounts")
        self.assertEqual(manager.get(self.teachers_url).status_code, 200)
