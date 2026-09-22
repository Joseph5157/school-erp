from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import (
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    ClassGrade,
    Guardian,
    RelationshipType,
    School,
    Section,
    Student,
)

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
                "add_applicant",
                "change_applicant",
                "view_applicant",
                "add_guardian",
                "change_guardian",
                "view_guardian",
                "add_applicantguardian",
                "change_applicantguardian",
                "view_applicantguardian",
                "add_student",
                "change_student",
                "view_student",
                "add_studentguardian",
                "change_studentguardian",
                "view_studentguardian",
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


class ApplicantCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:applicant-create")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"full_name": "Ravi Rao"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(Applicant.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"full_name": "Ravi Rao"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Applicant.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, {"full_name": "Ravi Rao"})

        self.assertRedirects(response, reverse("core:applicant-list"))
        self.assertEqual(Applicant.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"full_name": "Ravi Rao"})

        self.assertRedirects(response, reverse("core:applicant-list"))
        self.assertEqual(Applicant.objects.count(), 1)

    def test_administrator_invalid_payload_leaves_no_partial_record(self):
        response = self.administrator.post(self.url, {"full_name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Applicant.objects.exists())


class ApplicantListAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        Applicant.objects.create(full_name="Ravi Rao")
        self.url = reverse("core:applicant-list")

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
        self.assertContains(response, "Ravi Rao")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")


class ApplicantDetailAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.url = reverse("core:applicant-detail", args=[self.applicant.pk])

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
        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "Pending")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")

    def test_missing_applicant_is_not_found(self):
        response = self.administrator.get(
            reverse("core:applicant-detail", args=[self.applicant.pk + 999])
        )

        self.assertEqual(response.status_code, 404)


class ApplicantGuardianCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.guardian = Guardian.objects.create(full_name="Asha Rao")
        self.url = reverse("core:applicant-guardian-create", args=[self.applicant.pk])
        self.valid_payload = {
            "guardian": self.guardian.pk,
            "relationship_type": RelationshipType.MOTHER,
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(ApplicantGuardian.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ApplicantGuardian.objects.exists())

    def test_administrator_can_associate_guardian(self):
        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.assertEqual(ApplicantGuardian.objects.count(), 1)
        self.assertEqual(ApplicantGuardian.objects.get().applicant, self.applicant)

    def test_superuser_can_associate_guardian(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_administrator_duplicate_association_leaves_no_partial_record(self):
        ApplicantGuardian.objects.create(
            applicant=self.applicant,
            guardian=self.guardian,
            relationship_type=RelationshipType.MOTHER,
        )

        response = self.administrator.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ApplicantGuardian.objects.count(), 1)

    def test_administrator_missing_relationship_type_leaves_no_partial_record(self):
        response = self.administrator.post(self.url, {"guardian": self.guardian.pk})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ApplicantGuardian.objects.exists())

    def test_associate_for_missing_applicant_is_not_found(self):
        response = self.administrator.post(
            reverse("core:applicant-guardian-create", args=[self.applicant.pk + 999]),
            self.valid_payload,
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ApplicantGuardian.objects.exists())


class GuardianCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:guardian-create")

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"full_name": "Asha Rao"})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(Guardian.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"full_name": "Asha Rao"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Guardian.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, {"full_name": "Asha Rao"})

        self.assertRedirects(response, reverse("core:guardian-list"))
        self.assertEqual(Guardian.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"full_name": "Asha Rao"})

        self.assertRedirects(response, reverse("core:guardian-list"))
        self.assertEqual(Guardian.objects.count(), 1)

    def test_administrator_invalid_payload_leaves_no_partial_record(self):
        response = self.administrator.post(self.url, {"full_name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Guardian.objects.exists())


class GuardianListAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        Guardian.objects.create(full_name="Asha Rao")
        self.url = reverse("core:guardian-list")

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
        self.assertContains(response, "Asha Rao")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Rao")


class GuardianDetailAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.guardian = Guardian.objects.create(full_name="Asha Rao")
        self.url = reverse("core:guardian-detail", args=[self.guardian.pk])

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
        self.assertContains(response, "Asha Rao")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha Rao")

    def test_missing_guardian_is_not_found(self):
        response = self.administrator.get(
            reverse("core:guardian-detail", args=[self.guardian.pk + 999])
        )

        self.assertEqual(response.status_code, 404)


class ApplicantAdmissionDecisionAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.url = reverse("core:applicant-admission-decision", args=[self.applicant.pk])

    def _decide(self, client, decision):
        return client.post(self.url, {"decision": decision})

    def test_anonymous_is_redirected_to_login(self):
        response = self._decide(self.anonymous, Applicant.AdmissionStatus.ACCEPTED)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.PENDING)

    def test_authenticated_non_admin_is_forbidden(self):
        response = self._decide(self.non_admin, Applicant.AdmissionStatus.ACCEPTED)

        self.assertEqual(response.status_code, 403)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.PENDING)

    def test_administrator_can_accept(self):
        response = self._decide(self.administrator, Applicant.AdmissionStatus.ACCEPTED)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)
        self.assertIsNotNone(self.applicant.admission_decided_at)

    def test_administrator_can_reject(self):
        response = self._decide(self.administrator, Applicant.AdmissionStatus.REJECTED)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.REJECTED)

    def test_superuser_can_decide(self):
        response = self._decide(self.superuser_client, Applicant.AdmissionStatus.ACCEPTED)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)

    def test_get_does_not_change_state(self):
        response = self.administrator.get(self.url)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.PENDING)

    def test_invalid_decision_leaves_no_change(self):
        response = self._decide(self.administrator, "MAYBE")

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.PENDING)
        self.assertIsNone(self.applicant.admission_decided_at)

    def test_repeat_conflicting_decision_is_not_applied(self):
        self._decide(self.administrator, Applicant.AdmissionStatus.ACCEPTED)

        response = self._decide(self.administrator, Applicant.AdmissionStatus.REJECTED)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, Applicant.AdmissionStatus.ACCEPTED)

    def test_missing_applicant_is_not_found(self):
        response = self.administrator.post(
            reverse("core:applicant-admission-decision", args=[self.applicant.pk + 999]),
            {"decision": Applicant.AdmissionStatus.ACCEPTED},
        )

        self.assertEqual(response.status_code, 404)


class ApplicantProgressAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Rao")
        self.applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.url = reverse("core:applicant-progress", args=[self.applicant.pk])

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(Student.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Student.objects.exists())

    def test_administrator_can_progress(self):
        response = self.administrator.post(self.url)

        student = Student.objects.get()
        self.assertRedirects(response, reverse("core:student-detail", args=[student.pk]))
        self.assertEqual(student.applicant, self.applicant)

    def test_superuser_can_progress(self):
        response = self.superuser_client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Student.objects.count(), 1)

    def test_pending_applicant_is_not_progressed(self):
        pending = Applicant.objects.create(full_name="Meera Rao")

        response = self.administrator.post(
            reverse("core:applicant-progress", args=[pending.pk])
        )

        self.assertRedirects(response, reverse("core:applicant-detail", args=[pending.pk]))
        self.assertFalse(Student.objects.exists())

    def test_repeated_progression_does_not_create_another_student(self):
        self.administrator.post(self.url)

        response = self.administrator.post(self.url)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.assertEqual(Student.objects.count(), 1)

    def test_get_does_not_progress(self):
        response = self.administrator.get(self.url)

        self.assertRedirects(
            response, reverse("core:applicant-detail", args=[self.applicant.pk])
        )
        self.assertFalse(Student.objects.exists())

    def test_missing_applicant_is_not_found(self):
        response = self.administrator.post(
            reverse("core:applicant-progress", args=[self.applicant.pk + 999])
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Student.objects.exists())


class StudentDetailAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.url = reverse("core:student-detail", args=[self.student.pk])

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
        self.assertContains(response, "Ravi Rao")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")

    def test_missing_student_is_not_found(self):
        response = self.administrator.get(
            reverse("core:student-detail", args=[self.student.pk + 999])
        )

        self.assertEqual(response.status_code, 404)
