from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import teacher_accounts
from core.models import TEACHERS_GROUP_NAME, AcademicYear, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()


def add_teacher(actor, username, first="Asha", last="Rao"):
    return teacher_accounts.create_teacher(
        username=username, first_name=first, last_name=last, email="", actor=actor
    )


class TeacherListTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:teacher-list")

    def test_permissions(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(self.url), f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.administrator.get(self.url).status_code, 200)

    def test_lists_only_teachers_with_table_semantics(self):
        add_teacher(self.admin_user, "asha.rao")
        response = self.administrator.get(self.url)
        self.assertContains(response, "asha.rao")
        usernames = [t.username for t in response.context["teachers"]]
        self.assertEqual(usernames, ["asha.rao"])
        self.assertContains(response, "<caption")
        self.assertContains(response, 'scope="col"')
        self.assertContains(response, "Add teacher")

    def test_sidebar_has_teachers_link_for_administrators(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, f'href="{self.url}"')

    def test_search_status_filter_sort_and_pagination(self):
        for index in range(30):
            add_teacher(self.admin_user, f"teacher{index:02d}", first=f"T{index:02d}", last="X")
        inactive, _ = add_teacher(self.admin_user, "gone.teacher", first="Zed", last="Gone")
        teacher_accounts.deactivate_teacher(user=inactive, reason="Left", actor=self.admin_user)
        page1 = self.administrator.get(self.url)
        self.assertEqual(len(page1.context["teachers"]), 25)
        self.assertContains(page1, "Showing 1–25 of 31")
        found = self.administrator.get(self.url, {"q": "gone"})
        self.assertEqual([t.username for t in found.context["teachers"]], ["gone.teacher"])
        only_inactive = self.administrator.get(self.url, {"status": "inactive"})
        self.assertEqual(
            [t.username for t in only_inactive.context["teachers"]], ["gone.teacher"]
        )
        self.assertEqual(self.administrator.get(self.url, {"status": "bogus"}).status_code, 200)
        self.assertEqual(
            self.administrator.get(self.url, {"sort": "nope", "page": "x"}).status_code, 200
        )


class TeacherListAssignmentCountTests(Phase4Fixture, AuthorizationClientsMixin, TestCase):
    """The Assignments column counts subject + class-teacher rows from real data."""

    def setUp(self):
        super().setUp()
        self.build_phase4()
        self.url = reverse("core:teacher-list")

    def counts(self):
        response = self.administrator.get(self.url)
        return {t.username: t.assignment_count for t in response.context["teachers"]}

    def class_teacher(self, teacher, section):
        return SectionClassTeacher.assign(
            teacher=teacher, academic_year=self.year, section=section,
            start_date=date(2026, 6, 1),
        )

    def test_assignment_counts_use_real_subject_and_class_teacher_rows(self):
        add_teacher(self.admin_user, "no.work")
        subject_only, _ = add_teacher(self.admin_user, "subject.only")
        class_only, _ = add_teacher(self.admin_user, "class.only")
        both, _ = add_teacher(self.admin_user, "both.kinds")
        self.assign(subject_only, self.maths, self.six_a)
        self.class_teacher(class_only, self.six_a)
        # 2 subject + 1 class must be 3, not a join-multiplied 2.
        self.assign(both, self.maths, self.six_b)
        self.assign(both, self.sanskrit, self.six_b)
        self.class_teacher(both, self.six_b)
        counts = self.counts()
        self.assertEqual(counts["no.work"], 0)
        self.assertEqual(counts["subject.only"], 1)
        self.assertEqual(counts["class.only"], 1)
        self.assertEqual(counts["both.kinds"], 3)

    def test_rendered_row_shows_the_count(self):
        both, _ = add_teacher(self.admin_user, "both.kinds")
        self.assign(both, self.maths, self.six_a)
        self.assign(both, self.sanskrit, self.six_b)
        self.class_teacher(both, self.six_b)
        self.assertContains(self.administrator.get(self.url), "<td>3</td>", html=True)


class TeacherCreateTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:teacher-create")
        self.data = {
            "first_name": "Asha", "last_name": "Rao",
            "username": "asha.rao", "email": "asha@example.com",
        }

    def test_permissions(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
        self.assertEqual(self.non_admin.post(self.url, self.data).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(self.url), f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertFalse(User.objects.filter(username="asha.rao").exists())

    def test_form_renders(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "Add teacher")
        self.assertContains(response, 'name="username"')

    def test_post_creates_teacher_and_shows_slip_once_with_no_store(self):
        response = self.administrator.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="asha.rao")
        self.assertTrue(user.groups.filter(name=TEACHERS_GROUP_NAME).exists())
        self.assertContains(response, "Temporary password")
        self.assertContains(response, "asha.rao")
        self.assertIn("no-store", response["Cache-Control"])
        shown = response.context["password"]
        self.assertNotIn(shown, str(list(response.context["messages"])))
        self.assertNotIn(shown, str(dict(self.administrator.session)))
        event = SecurityEvent.objects.get(
            event_type=SecurityEvent.EventType.TEACHER_ACCOUNT_CREATED, subject_user=user
        )
        self.assertNotIn(shown, str(event.detail))
        self.assertNotContains(self.administrator.get(reverse("core:teacher-list")), shown)

    def test_duplicate_and_invalid_username_show_errors_not_500(self):
        add_teacher(self.admin_user, "asha.rao")
        for username in ("asha.rao", "x", "has space"):
            with self.subTest(username=username):
                response = self.administrator.post(self.url, {**self.data, "username": username})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "erp-field-errors")
        self.assertEqual(User.objects.filter(username__iexact="asha.rao").count(), 1)

    def test_first_and_last_name_are_required(self):
        response = self.administrator.post(self.url, {**self.data, "first_name": ""})
        self.assertContains(response, "erp-field-errors")
        self.assertFalse(User.objects.filter(username="asha.rao").exists())


class TeacherManageTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher, self.password = add_teacher(self.admin_user, "asha.rao")

    def url(self, name):
        return reverse(f"core:{name}", args=[self.teacher.pk])

    def test_detail_shows_profile_workload_link_events_and_actions(self):
        response = self.administrator.get(self.url("teacher-detail"))
        self.assertContains(response, "asha.rao")
        self.assertContains(response, reverse("core:teacher-load", args=[self.teacher.pk]))
        self.assertContains(response, "Teacher account created")
        for name in ("teacher-reset-password", "teacher-username", "teacher-deactivate"):
            self.assertContains(response, self.url(name))

    def test_list_names_link_to_detail(self):
        response = self.administrator.get(reverse("core:teacher-list"))
        self.assertContains(response, f'href="{self.url("teacher-detail")}"')

    def test_every_page_refuses_non_admin_and_anonymous(self):
        for name in ("teacher-detail", "teacher-reset-password", "teacher-username",
                     "teacher-deactivate", "teacher-reactivate"):
            with self.subTest(name=name):
                self.assertEqual(self.non_admin.get(self.url(name)).status_code, 403)
                self.assertEqual(self.non_admin.post(self.url(name)).status_code, 403)
                self.assertEqual(self.anonymous.get(self.url(name)).status_code, 302)

    def test_non_teacher_and_superuser_targets_are_404_everywhere(self):
        root = User.objects.create_superuser(username="root2", password="pass-12345")
        root.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        for target in (self.admin_user, root):
            for name in ("teacher-detail", "teacher-reset-password", "teacher-username",
                         "teacher-deactivate", "teacher-reactivate"):
                with self.subTest(target=target.username, name=name):
                    url = reverse(f"core:{name}", args=[target.pk])
                    self.assertEqual(self.administrator.get(url).status_code, 404)
                    self.assertEqual(
                        self.administrator.post(url, {"reason": "x", "username": "zz.zz"})
                        .status_code, 404)
        self.assertTrue(User.objects.get(pk=self.admin_user.pk).is_active)

    def test_reset_get_confirms_and_post_shows_slip(self):
        confirm = self.administrator.get(self.url("teacher-reset-password"))
        self.assertContains(confirm, "Reset password")
        self.assertEqual(User.objects.get(pk=self.teacher.pk).session_version, 0)
        response = self.administrator.post(self.url("teacher-reset-password"))
        self.assertContains(response, "Temporary password")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotEqual(response.context["password"], self.password)
        self.assertEqual(User.objects.get(pk=self.teacher.pk).session_version, 1)

    def test_username_change(self):
        self.assertContains(self.administrator.get(self.url("teacher-username")), "New username")
        bad = self.administrator.post(self.url("teacher-username"), {"username": "x"})
        self.assertContains(bad, "erp-field-errors")
        done = self.administrator.post(self.url("teacher-username"), {"username": "asha.r"})
        self.assertRedirects(done, self.url("teacher-detail"))
        self.assertEqual(User.objects.get(pk=self.teacher.pk).username, "asha.r")

    def test_deactivate_needs_reason_then_reactivate(self):
        page = self.administrator.get(self.url("teacher-deactivate"))
        self.assertContains(page, "assignment")  # states how many assignments remain on record
        missing = self.administrator.post(self.url("teacher-deactivate"), {"reason": ""})
        self.assertContains(missing, "erp-field-errors")
        self.assertTrue(User.objects.get(pk=self.teacher.pk).is_active)
        done = self.administrator.post(self.url("teacher-deactivate"), {"reason": "Left"})
        self.assertRedirects(done, self.url("teacher-detail"))
        self.assertFalse(User.objects.get(pk=self.teacher.pk).is_active)
        self.assertContains(self.administrator.get(self.url("teacher-detail")), "Inactive")
        back = self.administrator.post(self.url("teacher-reactivate"))
        self.assertRedirects(back, self.url("teacher-detail"))
        self.assertTrue(User.objects.get(pk=self.teacher.pk).is_active)

    def test_administrator_who_is_also_a_teacher_cannot_deactivate_self(self):
        self.admin_user.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        url = reverse("core:teacher-deactivate", args=[self.admin_user.pk])
        response = self.administrator.post(url, {"reason": "Oops"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot deactivate your own login")
        self.assertContains(response, "erp-form-errors")
        self.assertTrue(User.objects.get(pk=self.admin_user.pk).is_active)

    def test_breadcrumbs_link_back_to_the_teacher_and_the_list(self):
        response = self.administrator.get(self.url("teacher-deactivate"))
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, f'href="{reverse("core:teacher-list")}"')
        self.assertContains(response, f'href="{self.url("teacher-detail")}"')

    def test_assignments_page_links_to_teachers_page(self):
        year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        response = self.administrator.get(
            reverse("core:academic-year-teacher-assignments", args=[year.pk])
        )
        self.assertContains(response, reverse("core:teacher-list"))
        self.assertNotContains(response, "site administration")
