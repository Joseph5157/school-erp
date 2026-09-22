from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear, ClassGrade, School, Section

User = get_user_model()


class SchoolAdministratorsGroupMigrationTests(TestCase):
    def test_group_seeded_with_expected_permissions(self):
        group = Group.objects.get(name="School Administrators")
        codenames = set(group.permissions.values_list("codename", flat=True))

        self.assertEqual(
            codenames,
            {
                "add_school",
                "change_school",
                "view_school",
                "add_academicyear",
                "view_academicyear",
                "add_classgrade",
                "change_classgrade",
                "view_classgrade",
                "add_section",
                "change_section",
                "view_section",
            },
        )


class AuthorizationClientsMixin:
    """Provides one client per point in the Phase 1 authorization matrix."""

    def setUp(self):
        super().setUp()

        self.anonymous = self.client_class()

        self.non_admin_user = User.objects.create_user(username="teacher", password="pass-12345")
        self.non_admin = self.client_class()
        self.non_admin.login(username="teacher", password="pass-12345")

        self.admin_user = User.objects.create_user(username="administrator", password="pass-12345")
        self.admin_user.groups.add(Group.objects.get(name="School Administrators"))
        self.administrator = self.client_class()
        self.administrator.login(username="administrator", password="pass-12345")

        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="pass-12345"
        )
        self.superuser_client = self.client_class()
        self.superuser_client.login(username="root", password="pass-12345")


class SchoolCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:school-create")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"name": "Greenwood High"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(School.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"name": "Greenwood High"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(School.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, {"name": "Greenwood High"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"name": "Greenwood High"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)

    def test_administrator_cannot_create_a_second_school(self):
        School.objects.create(name="Greenwood High")

        response = self.administrator.post(self.url, {"name": "Riverside Academy"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(School.objects.get().name, "Greenwood High")

    def test_concurrent_create_race_is_handled_without_a_server_error(self):
        # Simulate a second request creating the School between this
        # request's exists() guard and its actual save().
        with mock.patch("core.views.School.objects.exists", return_value=False):
            School.objects.create(name="Greenwood High")
            response = self.administrator.post(self.url, {"name": "Riverside Academy"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(School.objects.get().name, "Greenwood High")


class SchoolUpdateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.school = School.objects.create(name="Greenwood High")
        self.url = reverse("core:school-update")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"name": "Renamed"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Greenwood High")

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"name": "Renamed"})

        self.assertEqual(response.status_code, 403)
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Greenwood High")

    def test_administrator_can_update(self):
        response = self.administrator.post(self.url, {"name": "Greenwood International"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Greenwood International")

    def test_superuser_can_update(self):
        response = self.superuser_client.post(self.url, {"name": "Greenwood International"})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Greenwood International")


class SchoolDetailAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        School.objects.create(name="Greenwood High")
        self.url = reverse("core:school-detail")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.get(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_view(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Greenwood High")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Greenwood High")


class AcademicYearCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:academic-year-create")
        self.valid_payload = {
            "name": "2026-2027",
            "start_date": "2026-06-01",
            "end_date": "2027-04-30",
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(AcademicYear.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AcademicYear.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(response, reverse("core:academic-year-list"))
        self.assertEqual(AcademicYear.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertRedirects(response, reverse("core:academic-year-list"))
        self.assertEqual(AcademicYear.objects.count(), 1)

    def test_administrator_invalid_dates_leave_no_partial_record(self):
        invalid_payload = {**self.valid_payload, "end_date": "2026-01-01"}

        response = self.administrator.post(self.url, invalid_payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AcademicYear.objects.exists())


class AcademicYearListAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.url = reverse("core:academic-year-list")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.get(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_list(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-2027")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-2027")


class ClassGradeCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:class-grade-create")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"name": "Grade 1"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(ClassGrade.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"name": "Grade 1"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ClassGrade.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, {"name": "Grade 1"})

        self.assertRedirects(response, reverse("core:class-grade-list"))
        self.assertEqual(ClassGrade.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"name": "Grade 1"})

        self.assertRedirects(response, reverse("core:class-grade-list"))
        self.assertEqual(ClassGrade.objects.count(), 1)

    def test_administrator_duplicate_name_leaves_no_partial_record(self):
        ClassGrade.objects.create(name="Grade 1")

        response = self.administrator.post(self.url, {"name": "Grade 1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ClassGrade.objects.count(), 1)


class ClassGradeListAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        ClassGrade.objects.create(name="Grade 1")
        self.url = reverse("core:class-grade-list")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.get(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_list(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 1")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 1")


class ClassGradeDetailAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.url = reverse("core:class-grade-detail", args=[self.class_grade.pk])

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.get(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_view(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 1")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 1")


class SectionCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.url = reverse("core:section-create", args=[self.class_grade.pk])

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"name": "A"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(Section.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"name": "A"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Section.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, {"name": "A"})

        self.assertRedirects(
            response, reverse("core:class-grade-detail", args=[self.class_grade.pk])
        )
        self.assertEqual(Section.objects.count(), 1)
        self.assertEqual(Section.objects.get().class_grade, self.class_grade)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"name": "A"})

        self.assertRedirects(
            response, reverse("core:class-grade-detail", args=[self.class_grade.pk])
        )
        self.assertEqual(Section.objects.count(), 1)

    def test_administrator_duplicate_section_name_leaves_no_partial_record(self):
        Section.objects.create(class_grade=self.class_grade, name="A")

        response = self.administrator.post(self.url, {"name": "A"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Section.objects.count(), 1)

    def test_create_for_missing_class_grade_is_not_found(self):
        response = self.administrator.post(
            reverse("core:section-create", args=[self.class_grade.pk + 999]), {"name": "A"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Section.objects.exists())
