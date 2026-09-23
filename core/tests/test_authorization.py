from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.forms import AttendanceCaptureForm
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    ApplicantGuardian,
    AttendanceCorrection,
    AttendanceEntry,
    AttendanceRegister,
    AttendanceStatus,
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
                "add_academicenrollment",
                "change_academicenrollment",
                "view_academicenrollment",
                "add_attendanceregister",
                "change_attendanceregister",
                "view_attendanceregister",
                "add_attendanceentry",
                "change_attendanceentry",
                "view_attendanceentry",
                "add_attendancecorrection",
                "change_attendancecorrection",
                "view_attendancecorrection",
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

    def test_section_date_range_includes_status_summary(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        response = self.administrator.get(
            self.url,
            {"section": self.section.pk, "start": "2026-07-01", "end": "2026-07-01"},
        )

        self.assertEqual(response.context["section_total"], 1)
        self.assertEqual(
            response.context["section_summary"],
            [
                {"label": "Present", "count": 1},
                {"label": "Absent", "count": 0},
                {"label": "Late", "count": 0},
                {"label": "Excused", "count": 0},
            ],
        )
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


class StudentEnrollAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        self.url = reverse("core:student-enroll", args=[self.student.pk])
        self.valid_payload = {
            "academic_year": self.year.pk,
            "class_grade": self.class_grade.pk,
            "section": self.section.pk,
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_administrator_can_enroll(self):
        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:student-detail", args=[self.student.pk])
        )
        enrollment = AcademicEnrollment.objects.get()
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)
        self.assertEqual(enrollment.student, self.student)

    def test_superuser_can_enroll(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:student-detail", args=[self.student.pk])
        )
        self.assertEqual(AcademicEnrollment.objects.count(), 1)

    def test_incompatible_section_leaves_no_enrollment(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        other_section = Section.objects.create(class_grade=other_class_grade, name="A")

        response = self.administrator.post(
            self.url,
            {**self.valid_payload, "section": other_section.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_missing_student_is_not_found(self):
        response = self.administrator.post(
            reverse("core:student-enroll", args=[self.student.pk + 999]), self.valid_payload
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_administrator_can_open_form(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)


class StudentListAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.ravi = self._student("Ravi Rao", "ravi@example.com", "111-222")
        self.meera = self._student("Meera Iyer", "meera@example.com", "333-444")
        self.url = reverse("core:student-list")

    def _student(self, full_name, email, phone):
        applicant = Applicant.objects.create(full_name=full_name, email=email, phone=phone)
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        return applicant.progress_to_student()

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.get(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_administrator_sees_all_students(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "Meera Iyer")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_search_by_name(self):
        response = self.administrator.get(self.url, {"q": "Meera"})

        self.assertEqual(list(response.context["students"]), [self.meera])

    def test_search_by_email(self):
        response = self.administrator.get(self.url, {"q": "ravi@example.com"})

        self.assertEqual(list(response.context["students"]), [self.ravi])

    def test_search_by_phone(self):
        response = self.administrator.get(self.url, {"q": "333-444"})

        self.assertEqual(list(response.context["students"]), [self.meera])

    def test_search_with_no_match_returns_nothing(self):
        response = self.administrator.get(self.url, {"q": "Nobody"})

        self.assertEqual(list(response.context["students"]), [])


class StudentStatusChangeAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.url = reverse("core:student-status-change", args=[self.student.pk])

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, {"status": Student.Status.INACTIVE})

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, {"status": Student.Status.INACTIVE})

        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_administrator_can_deactivate(self):
        response = self.administrator.post(self.url, {"status": Student.Status.INACTIVE})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)
        self.assertIsNotNone(self.student.status_changed_at)

    def test_administrator_can_reactivate(self):
        self.student.record_status_change(Student.Status.INACTIVE)

        response = self.administrator.post(self.url, {"status": Student.Status.ACTIVE})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_superuser_can_change_status(self):
        response = self.superuser_client.post(self.url, {"status": Student.Status.INACTIVE})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)

    def test_invalid_status_is_rejected(self):
        response = self.administrator.post(self.url, {"status": "GRADUATED"})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_repeat_status_is_rejected(self):
        response = self.administrator.post(self.url, {"status": Student.Status.ACTIVE})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_get_does_not_change_status(self):
        response = self.administrator.get(self.url)

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_missing_student_is_not_found(self):
        response = self.administrator.post(
            reverse("core:student-status-change", args=[self.student.pk + 999]),
            {"status": Student.Status.INACTIVE},
        )

        self.assertEqual(response.status_code, 404)


class AttendanceFixtureMixin:
    """Builds an enrolled Student and an empty register for attendance tests."""

    def build_attendance_fixture(self, *, date="2026-07-01"):
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        applicant = Applicant.objects.create(full_name="Ravi Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()
        self.enrollment = self.student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=self.section
        )
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date=date,
        )
        return self.register


class AttendanceRegisterCreateAuthorizationTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-06-01", end_date="2027-04-30"
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section = Section.objects.create(class_grade=self.class_grade, name="A")
        self.url = reverse("core:attendance-register-create")
        self.valid_payload = {
            "academic_year": self.year.pk,
            "class_grade": self.class_grade.pk,
            "section": self.section.pk,
            "date": "2026-07-01",
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_administrator_can_create(self):
        response = self.administrator.post(self.url, self.valid_payload)

        register = AttendanceRegister.objects.get()
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceRegister.objects.count(), 1)

    def test_incompatible_section_leaves_no_register(self):
        other_class_grade = ClassGrade.objects.create(name="Grade 2")
        other_section = Section.objects.create(class_grade=other_class_grade, name="A")

        response = self.administrator.post(
            self.url, {**self.valid_payload, "section": other_section.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_date_outside_academic_year_leaves_no_register(self):
        response = self.administrator.post(
            self.url, {**self.valid_payload, "date": "2027-05-01"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AttendanceRegister.objects.exists())

    def test_duplicate_register_leaves_one_record(self):
        AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-07-01",
        )

        response = self.administrator.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRegister.objects.count(), 1)


class AttendanceRegisterListAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.url = reverse("core:attendance-register-list")

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
        self.assertContains(response, "Grade 1 - A")

    def test_superuser_can_list(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)


class AttendanceRegisterDetailAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.url = reverse("core:attendance-register-detail", args=[self.register.pk])

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

    def test_missing_register_is_not_found(self):
        response = self.administrator.get(
            reverse("core:attendance-register-detail", args=[self.register.pk + 999])
        )

        self.assertEqual(response.status_code, 404)


class AttendanceCaptureAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.url = reverse("core:attendance-capture", args=[self.register.pk])
        self.valid_payload = {
            AttendanceCaptureForm.field_name(self.enrollment): AttendanceStatus.PRESENT,
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_administrator_can_capture(self):
        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        entry = AttendanceEntry.objects.get()
        self.assertEqual(entry.academic_enrollment, self.enrollment)
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)

    def test_superuser_can_capture(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_missing_status_leaves_no_entry(self):
        response = self.administrator.post(self.url, {})

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_repeated_capture_does_not_duplicate(self):
        self.administrator.post(self.url, self.valid_payload)

        self.administrator.post(self.url, self.valid_payload)

        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_get_does_not_capture(self):
        response = self.administrator.get(self.url)

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        self.assertFalse(AttendanceEntry.objects.exists())


class AttendanceCorrectionAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.entry = self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        self.url = reverse("core:attendance-entry-correct", args=[self.entry.pk])
        self.valid_payload = {
            "status": AttendanceStatus.ABSENT,
            "reason": "Guardian reported illness.",
        }

    def test_anonymous_is_redirected_to_login(self):
        response = self.anonymous.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_authenticated_non_admin_is_forbidden(self):
        response = self.non_admin.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 403)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)

    def test_administrator_can_correct(self):
        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.ABSENT)
        correction = AttendanceCorrection.objects.get()
        self.assertEqual(correction.previous_status, AttendanceStatus.PRESENT)
        self.assertEqual(correction.new_status, AttendanceStatus.ABSENT)
        self.assertEqual(correction.reason, "Guardian reported illness.")
        self.assertEqual(correction.corrected_by, self.admin_user)

    def test_superuser_can_correct(self):
        response = self.superuser_client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceCorrection.objects.count(), 1)

    def test_invalid_status_is_rejected(self):
        response = self.administrator.post(
            self.url, {"status": "HOLIDAY", "reason": "Typo."}
        )

        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_repeat_status_is_rejected(self):
        response = self.administrator.post(
            self.url, {"status": AttendanceStatus.PRESENT, "reason": "No change."}
        )

        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_missing_reason_is_rejected(self):
        response = self.administrator.post(self.url, {"status": AttendanceStatus.ABSENT})

        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_get_does_not_change_status(self):
        response = self.administrator.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_missing_entry_is_not_found(self):
        response = self.administrator.get(
            reverse("core:attendance-entry-correct", args=[self.entry.pk + 999])
        )

        self.assertEqual(response.status_code, 404)


class StudentAttendanceAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)
        self.url = reverse("core:student-attendance", args=[self.student.pk])

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
        self.assertContains(response, "Present")

    def test_superuser_can_view(self):
        response = self.superuser_client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_date_range_filter_excludes_entries(self):
        response = self.administrator.get(self.url, {"start": "2026-08-01"})

        self.assertEqual(response.context["total"], 0)
        self.assertEqual(list(response.context["entries"]), [])

    def test_missing_student_is_not_found(self):
        response = self.administrator.get(
            reverse("core:student-attendance", args=[self.student.pk + 999])
        )

        self.assertEqual(response.status_code, 404)
