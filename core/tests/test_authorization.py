from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
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
    SchoolCalendarDay,
    Section,
    Student,
)

User = get_user_model()


# School form field required since Phase 7 Gate 1 (notification channel).
CHANNEL = {"notification_channel": "PORTAL_ONLY"}


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
                "add_schoolcalendarday",
                "change_schoolcalendarday",
                "delete_schoolcalendarday",
                "view_schoolcalendarday",
                "add_subject",
                "change_subject",
                "view_subject",
                "add_academicterm",
                "change_academicterm",
                "view_academicterm",
                "add_academicsubjectoffering",
                "change_academicsubjectoffering",
                "view_academicsubjectoffering",
                "add_academicsubjectofferingsection",
                "change_academicsubjectofferingsection",
                "view_academicsubjectofferingsection",
                "add_assessmentteacherassignment",
                "change_assessmentteacherassignment",
                "delete_assessmentteacherassignment",
                "view_assessmentteacherassignment",
                "add_gradingscale",
                "change_gradingscale",
                "view_gradingscale",
                "add_gradeboundary",
                "delete_gradeboundary",
                "view_gradeboundary",
                "add_gradingscaleclassgrade",
                "delete_gradingscaleclassgrade",
                "view_gradingscaleclassgrade",
                "add_assessment",
                "change_assessment",
                "delete_assessment",
                "view_assessment",
                "view_studentresult",
                "finalize_assessment",
                "correct_studentresult",
                "view_resultcorrection",
                "add_termremark",
                "change_termremark",
                "delete_termremark",
                "view_termremark",
                "add_sectionclassteacher",
                "change_sectionclassteacher",
                "delete_sectionclassteacher",
                "view_sectionclassteacher",
                "add_guardianaccount",
                "change_guardianaccount",
                "view_guardianaccount",
                "reset_guardian_password",
                "change_guardian_username",
                "add_guardianstudentaccess",
                "change_guardianstudentaccess",
                "view_guardianstudentaccess",
                "view_securityevent",
                "add_guardianaccessreview",
                "view_guardianaccessreview",
                "publish_termpublication",
                "view_termpublication",
                "clear_login_lockout",
                "run_import",
                "view_importbatch",
                "send_notification",
                "view_notification",
                "add_guardiancontactconsent",
                "view_guardiancontactconsent",
                "add_announcement",
                "view_announcement",
                "withdraw_announcement",
                "issue_document",
                "view_issueddocument",
                "manage_teacher_accounts",
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
        response = self.administrator.post(self.url, {"name": "Greenwood High", **CHANNEL})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.url, {"name": "Greenwood High", **CHANNEL})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)

    def test_administrator_cannot_create_a_second_school(self):
        School.objects.create(name="Greenwood High")

        response = self.administrator.post(self.url, {"name": "Riverside Academy", **CHANNEL})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(School.objects.get().name, "Greenwood High")

    def test_concurrent_create_race_is_handled_without_a_server_error(self):
        # Simulate a second request creating the School between this
        # request's exists() guard and its actual save().
        with mock.patch("core.views.School.objects.exists", return_value=False):
            School.objects.create(name="Greenwood High")
            response = self.administrator.post(self.url, {"name": "Riverside Academy", **CHANNEL})

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
        response = self.administrator.post(self.url, {"name": "Greenwood International", **CHANNEL})

        self.assertRedirects(response, reverse("core:school-detail"))
        self.school.refresh_from_db()
        self.assertEqual(self.school.name, "Greenwood International")

    def test_superuser_can_update(self):
        response = self.superuser_client.post(
            self.url, {"name": "Greenwood International", **CHANNEL}
        )

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
        data = {"decision": decision}
        if decision == Applicant.AdmissionStatus.REJECTED:
            data["reason"] = "Test reason"
        return client.post(self.url, data)

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
            "start_date": "2026-06-01",
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
        self.assertContains(response, "Effective start date")

    def test_missing_start_date_leaves_no_enrollment(self):
        payload = {**self.valid_payload}
        del payload["start_date"]

        response = self.administrator.post(self.url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_start_date_outside_academic_year_leaves_no_enrollment(self):
        response = self.administrator.post(
            self.url, {**self.valid_payload, "start_date": "2026-05-01"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_administrator_transfer_records_effective_dates(self):
        self.administrator.post(self.url, self.valid_payload)
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")

        response = self.administrator.post(
            self.url,
            {**self.valid_payload, "section": other_section.pk, "start_date": "2026-09-15"},
        )

        self.assertRedirects(
            response, reverse("core:student-detail", args=[self.student.pk])
        )
        previous = AcademicEnrollment.objects.get(section=self.section)
        current = AcademicEnrollment.objects.get(section=other_section)
        self.assertEqual(previous.status, AcademicEnrollment.Status.COMPLETED)
        self.assertEqual(previous.end_date, date(2026, 9, 14))
        self.assertEqual(current.start_date, date(2026, 9, 15))
        self.assertIsNone(current.end_date)

    def test_transfer_not_after_current_start_is_rejected(self):
        self.administrator.post(self.url, self.valid_payload)
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")

        response = self.administrator.post(
            self.url,
            {**self.valid_payload, "section": other_section.pk, "start_date": "2026-06-01"},
        )

        self.assertEqual(response.status_code, 200)
        enrollment = AcademicEnrollment.objects.get()
        self.assertEqual(enrollment.section, self.section)
        self.assertEqual(enrollment.status, AcademicEnrollment.Status.ACTIVE)

    def test_future_start_date_is_rejected_by_view(self):
        with mock.patch("core.models.business_today", new=lambda: date(2026, 7, 1)):
            response = self.administrator.post(
                self.url, {**self.valid_payload, "start_date": "2026-07-02"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be in the future")
        self.assertFalse(AcademicEnrollment.objects.exists())

    def test_non_admin_cannot_transfer(self):
        self.administrator.post(self.url, self.valid_payload)
        other_section = Section.objects.create(class_grade=self.class_grade, name="B")

        response = self.non_admin.post(
            self.url,
            {**self.valid_payload, "section": other_section.pk, "start_date": "2026-09-15"},
        )

        self.assertEqual(response.status_code, 403)
        enrollment = AcademicEnrollment.objects.get()
        self.assertEqual(enrollment.section, self.section)
        self.assertIsNone(enrollment.end_date)


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
        response = self.administrator.post(
            self.url, {"status": Student.Status.INACTIVE, "reason": "Test reason"}
        )

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.INACTIVE)
        self.assertIsNotNone(self.student.status_changed_at)

    def test_administrator_can_reactivate(self):
        self.student.record_status_change(Student.Status.INACTIVE, reason="Test reason")

        response = self.administrator.post(self.url, {"status": Student.Status.ACTIVE})

        self.assertRedirects(response, reverse("core:student-detail", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.ACTIVE)

    def test_superuser_can_change_status(self):
        response = self.superuser_client.post(
            self.url, {"status": Student.Status.INACTIVE, "reason": "Test reason"}
        )

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
            academic_year=self.year, class_grade=self.class_grade, section=self.section,
            start_date="2026-06-01",  # `date` is shadowed by this method's parameter
        )
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date=date,
        )
        return self.register

    def capture_and_submit(self, *, enrollment, status, absence_note=""):
        """Capture the fixture roster's single entry and submit the register.

        Gate 6: corrections apply only to SUBMITTED attendance.
        """
        entry = self.register.capture(
            enrollment=enrollment, status=status, absence_note=absence_note
        )
        submitter, _ = User.objects.get_or_create(username="register-submitter")
        self.register.submit(actor=submitter)
        return entry


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
        # Gate 5: opening a Section/date that already has a register opens
        # that register instead of creating a second one.
        existing = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section,
            date="2026-07-01",
        )

        response = self.administrator.post(self.url, self.valid_payload)

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[existing.pk])
        )
        self.assertEqual(AttendanceRegister.objects.count(), 1)


class AttendanceRegisterListAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.url = reverse("core:attendance-register-list")

    def test_section_date_range_includes_status_summary(self):
        # Moved from AcademicYearListAuthorizationTests (it had no register
        # fixture there) and reconciled to the ADR 0007 PRESENT/ABSENT set.
        # Gate 7: the summary counts submitted attendance only.
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)
        draft_response = self.administrator.get(
            self.url,
            {"section": self.section.pk, "start": "2026-07-01", "end": "2026-07-01"},
        )
        self.assertEqual(draft_response.context["section_total"], 0)
        self.register.submit(actor=self.admin_user)

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
            ],
        )
        self.assertContains(response, "2026-2027")
        self.assertContains(response, "Submitted")

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
        self.entry = self.capture_and_submit(
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


class SchoolCalendarAuthorizationTests(AuthorizationClientsMixin, TestCase):
    """Gate 2 calendar workflow (docs/adr/0008-phase-2-school-calendar-rules.md)."""

    MONDAY = "2026-08-17"
    SATURDAY = "2026-08-22"

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.calendar_url = reverse("core:academic-year-calendar", args=[self.year.pk])
        self.create_url = reverse("core:calendar-day-create", args=[self.year.pk])
        self.saturday_url = reverse("core:academic-year-saturday-rule", args=[self.year.pk])
        self.holiday_payload = {
            "date": self.MONDAY,
            "is_instructional": "False",
            "label": "Closure",
        }

    def _holiday(self):
        return SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 8, 17), is_instructional=False, label="Closure"
        )

    def _register(self, on_date):
        class_grade = ClassGrade.objects.create(name="Grade 1")
        section = Section.objects.create(class_grade=class_grade, name="A")
        return AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=class_grade, section=section, date=on_date
        )

    # --- calendar page ----------------------------------------------------

    def test_anonymous_calendar_redirects_to_login(self):
        response = self.anonymous.get(self.calendar_url)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.calendar_url}",
            fetch_redirect_response=False,
        )

    def test_non_admin_cannot_view_calendar(self):
        self.assertEqual(self.non_admin.get(self.calendar_url).status_code, 403)

    def test_administrator_views_calendar_with_exceptions(self):
        self._holiday()

        response = self.administrator.get(self.calendar_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Closure")
        self.assertContains(response, "Holiday / closure")

    def test_calendar_date_check_reports_expectation(self):
        self._holiday()
        expectations = {
            self.MONDAY: False,
            "2026-08-18": True,
            self.SATURDAY: False,
        }
        for on_date, expected in expectations.items():
            with self.subTest(on_date=on_date):
                response = self.administrator.get(self.calendar_url, {"date": on_date})
                self.assertTrue(response.context["check_result"]["in_year"])
                self.assertEqual(response.context["check_result"]["instructional"], expected)

        response = self.administrator.get(self.calendar_url, {"date": "2027-05-03"})
        self.assertFalse(response.context["check_result"]["in_year"])
        self.assertContains(response, "outside this Academic Year")

    def test_missing_academic_year_is_not_found(self):
        url = reverse("core:academic-year-calendar", args=[self.year.pk + 999])
        self.assertEqual(self.administrator.get(url).status_code, 404)

    def test_academic_year_list_links_to_calendar(self):
        response = self.administrator.get(reverse("core:academic-year-list"))

        self.assertContains(response, self.calendar_url)

    # --- create -------------------------------------------------------------

    def test_anonymous_create_redirects_without_creating(self):
        response = self.anonymous.post(self.create_url, self.holiday_payload)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_non_admin_cannot_create(self):
        response = self.non_admin.post(self.create_url, self.holiday_payload)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_administrator_creates_holiday(self):
        response = self.administrator.post(self.create_url, self.holiday_payload)

        self.assertRedirects(response, self.calendar_url)
        day = SchoolCalendarDay.objects.get()
        self.assertEqual(day.academic_year, self.year)
        self.assertFalse(day.is_instructional)
        self.assertFalse(self.year.is_instructional_day(self.MONDAY))

    def test_administrator_creates_working_saturday(self):
        response = self.administrator.post(
            self.create_url,
            {"date": self.SATURDAY, "is_instructional": "True", "label": "Working Saturday"},
        )

        self.assertRedirects(response, self.calendar_url)
        self.assertTrue(self.year.is_instructional_day(self.SATURDAY))

    def test_superuser_can_create(self):
        response = self.superuser_client.post(self.create_url, self.holiday_payload)

        self.assertRedirects(response, self.calendar_url)
        self.assertEqual(SchoolCalendarDay.objects.count(), 1)

    def test_duplicate_date_is_rejected(self):
        self._holiday()

        response = self.administrator.post(self.create_url, self.holiday_payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a calendar exception")
        self.assertEqual(SchoolCalendarDay.objects.count(), 1)

    def test_exception_matching_pattern_is_rejected(self):
        response = self.administrator.post(
            self.create_url, {"date": self.SATURDAY, "is_instructional": "False"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_date_outside_year_is_rejected(self):
        response = self.administrator.post(
            self.create_url, {**self.holiday_payload, "date": "2027-05-03"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_holiday_on_date_with_attendance_is_rejected(self):
        self._register(self.MONDAY)

        response = self.administrator.post(self.create_url, self.holiday_payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance already exists on this date")
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_academic_year_cannot_be_injected(self):
        other = AcademicYear.objects.create(
            name="2027-2028", start_date=date(2027, 6, 1), end_date=date(2028, 4, 30)
        )

        self.administrator.post(
            self.create_url, {**self.holiday_payload, "academic_year": other.pk}
        )

        self.assertEqual(SchoolCalendarDay.objects.get().academic_year, self.year)

    # --- update label -------------------------------------------------------

    def test_non_admin_cannot_update(self):
        day = self._holiday()
        url = reverse("core:calendar-day-update", args=[day.pk])

        response = self.non_admin.post(url, {"label": "Changed"})

        self.assertEqual(response.status_code, 403)
        day.refresh_from_db()
        self.assertEqual(day.label, "Closure")

    def test_administrator_updates_label_only(self):
        day = self._holiday()
        url = reverse("core:calendar-day-update", args=[day.pk])

        response = self.administrator.post(
            url, {"label": "Heavy rain", "date": "2026-08-18", "is_instructional": "True"}
        )

        self.assertRedirects(response, self.calendar_url)
        day.refresh_from_db()
        self.assertEqual(day.label, "Heavy rain")
        self.assertEqual(day.date, date(2026, 8, 17))
        self.assertFalse(day.is_instructional)

    # --- delete -------------------------------------------------------------

    def test_get_does_not_delete(self):
        day = self._holiday()

        self.administrator.get(reverse("core:calendar-day-delete", args=[day.pk]))

        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    def test_non_admin_cannot_delete(self):
        day = self._holiday()

        response = self.non_admin.post(reverse("core:calendar-day-delete", args=[day.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    def test_administrator_deletes_exception(self):
        day = self._holiday()

        response = self.administrator.post(reverse("core:calendar-day-delete", args=[day.pk]))

        self.assertRedirects(response, self.calendar_url)
        self.assertFalse(SchoolCalendarDay.objects.exists())

    def test_delete_blocked_when_attendance_exists(self):
        day = SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 8, 22), is_instructional=True
        )
        self._register(self.SATURDAY)

        response = self.administrator.post(
            reverse("core:calendar-day-delete", args=[day.pk]), follow=True
        )

        self.assertContains(response, "cannot be removed")
        self.assertTrue(SchoolCalendarDay.objects.filter(pk=day.pk).exists())

    # --- Saturday rule ------------------------------------------------------

    def test_non_admin_cannot_change_saturday_rule(self):
        response = self.non_admin.post(self.saturday_url, {"saturdays_instructional": "true"})

        self.assertEqual(response.status_code, 403)
        self.year.refresh_from_db()
        self.assertFalse(self.year.saturdays_instructional)

    def test_administrator_changes_saturday_rule(self):
        response = self.administrator.post(
            self.saturday_url, {"saturdays_instructional": "true"}
        )

        self.assertRedirects(response, self.calendar_url)
        self.year.refresh_from_db()
        self.assertTrue(self.year.saturdays_instructional)

    def test_get_does_not_change_saturday_rule(self):
        self.administrator.get(self.saturday_url, {"saturdays_instructional": "true"})

        self.year.refresh_from_db()
        self.assertFalse(self.year.saturdays_instructional)

    def test_saturday_rule_locked_after_attendance(self):
        self._register("2026-07-01")

        response = self.administrator.post(
            self.saturday_url, {"saturdays_instructional": "true"}, follow=True
        )

        self.assertContains(response, "cannot change once attendance")
        self.year.refresh_from_db()
        self.assertFalse(self.year.saturdays_instructional)

    def test_academic_year_create_records_saturday_rule(self):
        self.administrator.post(
            reverse("core:academic-year-create"),
            {
                "name": "2027-2028",
                "start_date": "2027-06-01",
                "end_date": "2028-04-30",
                "saturdays_instructional": "on",
            },
        )

        self.assertTrue(AcademicYear.objects.get(name="2027-2028").saturdays_instructional)


class AttendanceGate3ViewTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    """Gate 3 behaviour through the existing attendance views."""

    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_register_create_ignores_submitted_status_in_request(self):
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")

        response = self.administrator.post(
            reverse("core:attendance-register-create"),
            {
                "academic_year": self.year.pk,
                "class_grade": self.class_grade.pk,
                "section": section_b.pk,
                "date": "2026-07-01",
                "status": "SUBMITTED",
                "submitted_by": self.admin_user.pk,
                "submitted_at": "2026-07-01T10:00",
            },
        )

        register = AttendanceRegister.objects.get(section=section_b)
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)
        self.assertIsNone(register.submitted_by)
        self.assertIsNone(register.submitted_at)

    def test_register_detail_shows_draft_status(self):
        response = self.administrator.get(
            reverse("core:attendance-register-detail", args=[self.register.pk])
        )

        self.assertContains(response, "Register status")
        self.assertContains(response, "Draft")

    def test_capture_form_offers_only_present_and_absent(self):
        form = AttendanceCaptureForm(register=self.register)
        field = form.fields[AttendanceCaptureForm.field_name(self.enrollment)]

        self.assertEqual([value for value, _ in field.choices], ["PRESENT", "ABSENT"])

    def test_capture_rejects_legacy_status_via_view(self):
        response = self.administrator.post(
            reverse("core:attendance-capture", args=[self.register.pk]),
            {AttendanceCaptureForm.field_name(self.enrollment): "LATE"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_correction_rejects_legacy_status_via_view(self):
        entry = self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        response = self.administrator.post(
            reverse("core:attendance-entry-correct", args=[entry.pk]),
            {"status": "EXCUSED", "reason": "Legacy."},
        )

        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_correction_to_present_via_view_clears_absence_note(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.ABSENT, absence_note="Fever."
        )
        url = reverse("core:attendance-entry-correct", args=[entry.pk])
        self.assertContains(self.administrator.get(url), "clears its absence note")

        response = self.administrator.post(
            url, {"status": AttendanceStatus.PRESENT, "reason": "Arrived late."}
        )

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertEqual(entry.absence_note, "")
        self.assertEqual(AttendanceCorrection.objects.count(), 1)

    def test_student_history_shows_absence_note(self):
        self.register.capture(
            enrollment=self.enrollment, status=AttendanceStatus.ABSENT, absence_note="Fever."
        )

        response = self.administrator.get(
            reverse("core:student-attendance", args=[self.student.pk])
        )

        self.assertContains(response, "Fever.")
        self.assertEqual(
            [row["label"] for row in response.context["summary"]], ["Present", "Absent"]
        )


class AttendanceSubmitAuthorizationTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    """Gate 4: submitting a register through the view."""

    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        self.url = reverse("core:attendance-register-submit", args=[self.register.pk])
        self.detail_url = reverse("core:attendance-register-detail", args=[self.register.pk])

    def _complete(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

    def test_anonymous_is_redirected_to_login(self):
        self._complete()
        response = self.anonymous.post(self.url)

        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)

    def test_non_admin_cannot_submit(self):
        self._complete()
        response = self.non_admin.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)

    def test_get_does_not_submit(self):
        self._complete()
        self.administrator.get(self.url)

        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)

    def test_administrator_submits_complete_register(self):
        self._complete()
        response = self.administrator.post(self.url)

        self.assertRedirects(response, self.detail_url)
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.register.submitted_by, self.admin_user)

    def test_incomplete_register_submission_shows_error(self):
        response = self.administrator.post(self.url, follow=True)

        self.assertContains(response, "Attendance is incomplete")
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)

    def test_submitted_detail_shows_submitter_and_hides_submit(self):
        self._complete()
        self.administrator.post(self.url)

        response = self.administrator.get(self.detail_url)

        self.assertContains(response, "Submitted")
        self.assertContains(response, "administrator")
        self.assertNotContains(response, "Submit register")

    def test_register_create_rejects_future_and_non_instructional_dates(self):
        section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        create_url = reverse("core:attendance-register-create")
        payload = {
            "academic_year": self.year.pk,
            "class_grade": self.class_grade.pk,
            "section": section_b.pk,
        }
        with mock.patch("core.models.business_today", new=lambda: date(2026, 10, 10)):
            for on_date, message in (
                ("2026-10-12", "future date"),
                ("2026-07-04", "not an instructional day"),  # Saturday
            ):
                with self.subTest(on_date=on_date):
                    response = self.administrator.post(create_url, {**payload, "date": on_date})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, message)
        self.assertFalse(AttendanceRegister.objects.filter(section=section_b).exists())


class AttendanceCaptureUiTests(AuthorizationClientsMixin, TestCase):
    """Gate 5: the everyday administrator capture workflow."""

    def setUp(self):
        super().setUp()
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 4, 30)
        )
        self.class_grade = ClassGrade.objects.create(name="Grade 1")
        self.section_a = Section.objects.create(class_grade=self.class_grade, name="A")
        self.section_b = Section.objects.create(class_grade=self.class_grade, name="B")
        self.ravi = self._student("Ravi Rao")
        self.meera = self._student("Meera Rao")
        self.ravi_a = self._enroll(self.ravi, self.section_a, date(2026, 6, 1))
        self.meera_a = self._enroll(self.meera, self.section_a, date(2026, 6, 1))
        self.register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section_a,
            date=date(2026, 7, 1),
        )
        self.detail_url = reverse("core:attendance-register-detail", args=[self.register.pk])
        self.capture_url = reverse("core:attendance-capture", args=[self.register.pk])

    def _student(self, name):
        applicant = Applicant.objects.create(full_name=name)
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        return applicant.progress_to_student()

    def _enroll(self, student, section, start):
        return student.enroll(
            academic_year=self.year, class_grade=self.class_grade, section=section, start_date=start
        )

    def _payload(self, statuses, notes=None, action=None):
        data = {}
        for enrollment, status in statuses.items():
            data[AttendanceCaptureForm.field_name(enrollment)] = status
        for enrollment, note in (notes or {}).items():
            data[AttendanceCaptureForm.note_name(enrollment)] = note
        if action:
            data["action"] = action
        return data

    def test_open_register_then_capture_flow(self):
        section_c = Section.objects.create(class_grade=self.class_grade, name="C")
        self._enroll(self._student("Asha Iyer"), section_c, date(2026, 6, 1))

        response = self.administrator.post(
            reverse("core:attendance-register-create"),
            {
                "academic_year": self.year.pk,
                "class_grade": self.class_grade.pk,
                "section": section_c.pk,
                "date": "2026-07-01",
            },
        )

        register = AttendanceRegister.objects.get(section=section_c)
        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[register.pk])
        )
        self.assertEqual(register.status, AttendanceRegister.Status.DRAFT)

    def test_detail_renders_date_effective_roster(self):
        ravi_b = self._enroll(self.ravi, self.section_b, date(2026, 9, 1))  # later transfer
        late = self._enroll(self._student("Asha Iyer"), self.section_a, date(2026, 7, 2))

        response = self.administrator.get(self.detail_url)

        roster = response.context["capture_form"].enrollments
        self.ravi_a.refresh_from_db()
        self.assertEqual(roster, [self.meera_a, self.ravi_a])
        self.assertNotIn(ravi_b, roster)
        self.assertNotIn(late, roster)
        self.assertContains(response, "Ravi Rao")
        self.assertNotContains(response, "Asha Iyer")
        self.assertContains(response, "not</strong> treated as absent")

    def test_detail_offers_present_absent_only_and_mark_all_present(self):
        response = self.administrator.get(self.detail_url)

        self.assertContains(response, 'value="PRESENT"')
        self.assertContains(response, 'value="ABSENT"')
        self.assertNotContains(response, "Late")
        self.assertNotContains(response, "Excused")
        self.assertContains(response, "Mark unanswered as present")
        self.assertContains(response, "Save draft")
        self.assertContains(response, "Save and submit")

    def test_save_partial_draft(self):
        response = self.administrator.post(
            self.capture_url, self._payload({self.ravi_a: "ABSENT"}, {self.ravi_a: "Fever"})
        )

        self.assertRedirects(response, self.detail_url)
        entry = AttendanceEntry.objects.get()
        self.assertEqual((entry.status, entry.absence_note), ("ABSENT", "Fever"))
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)
        follow = self.administrator.get(self.detail_url)
        self.assertContains(follow, "Marked: 1")

    def test_draft_edit_updates_entry_without_correction(self):
        self.administrator.post(self.capture_url, self._payload({self.ravi_a: "ABSENT"}))

        self.administrator.post(self.capture_url, self._payload({self.ravi_a: "PRESENT"}))

        entry = AttendanceEntry.objects.get()
        self.assertEqual(entry.status, "PRESENT")
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_existing_entries_prefill_the_form(self):
        self.register.capture(
            enrollment=self.ravi_a, status=AttendanceStatus.ABSENT, absence_note="Fever"
        )

        response = self.administrator.get(self.detail_url)

        form = response.context["capture_form"]
        self.assertEqual(form[AttendanceCaptureForm.field_name(self.ravi_a)].initial, "ABSENT")
        self.assertEqual(form[AttendanceCaptureForm.note_name(self.ravi_a)].initial, "Fever")

    def test_save_and_submit_complete_register(self):
        response = self.administrator.post(
            self.capture_url,
            self._payload({self.ravi_a: "PRESENT", self.meera_a: "ABSENT"}, action="submit"),
        )

        self.assertRedirects(response, self.detail_url)
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.register.submitted_by, self.admin_user)
        self.assertEqual(AttendanceEntry.objects.count(), 2)

    def test_submit_incomplete_keeps_draft_and_explains(self):
        response = self.administrator.post(
            self.capture_url, self._payload({self.ravi_a: "PRESENT"}, action="submit"), follow=True
        )

        self.assertContains(response, "Draft saved but not submitted")
        self.assertContains(response, "1 Student(s)")
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)
        self.assertEqual(AttendanceEntry.objects.count(), 1)

    def test_note_on_present_is_rejected_with_message(self):
        response = self.administrator.post(
            self.capture_url,
            self._payload({self.ravi_a: "PRESENT"}, {self.ravi_a: "Should not be here"}),
            follow=True,
        )

        self.assertContains(response, "Only an absent Student can have a note.")
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_submitted_register_is_read_only_with_correction_links(self):
        self.register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)
        self.register.capture(enrollment=self.meera_a, status=AttendanceStatus.ABSENT)
        self.register.submit(actor=self.admin_user)

        response = self.administrator.get(self.detail_url)

        self.assertContains(response, "Submitted attendance")
        self.assertNotContains(response, "Save draft")
        self.assertContains(response, "Correct")

    def test_capture_post_to_submitted_register_changes_nothing(self):
        self.register.capture(enrollment=self.ravi_a, status=AttendanceStatus.PRESENT)
        self.register.capture(enrollment=self.meera_a, status=AttendanceStatus.PRESENT)
        self.register.submit(actor=self.admin_user)

        response = self.administrator.post(
            self.capture_url, self._payload({self.ravi_a: "ABSENT"}), follow=True
        )

        self.assertContains(response, "through a correction")
        self.assertEqual(
            AttendanceEntry.objects.get(academic_enrollment=self.ravi_a).status, "PRESENT"
        )
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_empty_roster_message(self):
        register = AttendanceRegister.objects.create(
            academic_year=self.year,
            class_grade=self.class_grade,
            section=self.section_b,
            date=date(2026, 7, 1),
        )

        response = self.administrator.get(
            reverse("core:attendance-register-detail", args=[register.pk])
        )

        self.assertContains(response, "No Students are enrolled in this Section on this date.")

    def test_non_admin_cannot_view_or_capture(self):
        self.assertEqual(self.non_admin.get(self.detail_url).status_code, 403)
        response = self.non_admin.post(self.capture_url, self._payload({self.ravi_a: "PRESENT"}))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AttendanceEntry.objects.exists())

    def test_capture_without_submit_permission_saves_draft_only(self):
        limited = User.objects.create_user(username="clerk", password="pass-12345")
        limited.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["add_attendanceentry", "view_attendanceregister"]
            )
        )
        client = self.client_class()
        client.login(username="clerk", password="pass-12345")

        response = client.post(
            self.capture_url,
            self._payload({self.ravi_a: "PRESENT", self.meera_a: "PRESENT"}, action="submit"),
            follow=True,
        )

        self.assertContains(response, "You do not have permission to submit")
        self.register.refresh_from_db()
        self.assertEqual(self.register.status, AttendanceRegister.Status.DRAFT)
        self.assertEqual(AttendanceEntry.objects.count(), 2)


class AttendanceGate6CorrectionViewTests(
    AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_correction_page_redirects_for_draft_register(self):
        entry = self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)
        url = reverse("core:attendance-entry-correct", args=[entry.pk])

        response = self.administrator.post(url, {"status": "ABSENT", "reason": "x"})

        self.assertRedirects(
            response, reverse("core:attendance-register-detail", args=[self.register.pk])
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, AttendanceStatus.PRESENT)
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_correction_with_note_and_history_display(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        url = reverse("core:attendance-entry-correct", args=[entry.pk])

        self.administrator.post(
            url, {"status": "ABSENT", "absence_note": "Went home sick", "reason": "Nurse note."}
        )
        response = self.administrator.get(url)

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.absence_note), ("ABSENT", "Went home sick"))
        self.assertContains(response, "Nurse note.")
        self.assertContains(response, "Went home sick")

    def test_note_on_present_correction_rejected_by_form(self):
        entry = self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)
        url = reverse("core:attendance-entry-correct", args=[entry.pk])

        response = self.administrator.post(
            url, {"status": "PRESENT", "absence_note": "nope", "reason": "x"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only an absent Student can have a note.")
        self.assertFalse(AttendanceCorrection.objects.exists())

    def test_reports_use_current_corrected_value(self):
        entry = self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.PRESENT
        )
        entry.record_status_change(AttendanceStatus.ABSENT, actor=self.admin_user, reason="x")

        response = self.administrator.get(
            reverse("core:student-attendance", args=[self.student.pk])
        )

        summary = {row["label"]: row["count"] for row in response.context["summary"]}
        self.assertEqual(summary, {"Present": 0, "Absent": 1})
        self.assertEqual(AttendanceCorrection.objects.count(), 1)


class AttendanceReportViewTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    """Gate 7: report pages, authorization and semantics."""

    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()  # register on Wednesday 2026-07-01
        self.urls = {
            "index": reverse("core:attendance-reports"),
            "absent": reverse("core:report-daily-absentees"),
            "missing": reverse("core:report-missing-attendance"),
            "monthly": reverse("core:report-monthly-section"),
        }

    def test_reports_require_admin(self):
        for name, url in self.urls.items():
            with self.subTest(report=name):
                anonymous = self.anonymous.get(url)
                self.assertEqual(anonymous.status_code, 302)
                self.assertIn(reverse("login"), anonymous["Location"])
                self.assertEqual(self.non_admin.get(url).status_code, 403)
                self.assertEqual(self.administrator.get(url).status_code, 200)
                self.assertEqual(self.superuser_client.get(url).status_code, 200)

    def test_daily_absent_list_shows_submitted_absence_with_note(self):
        self.capture_and_submit(
            enrollment=self.enrollment, status=AttendanceStatus.ABSENT, absence_note="Fever"
        )

        response = self.administrator.get(self.urls["absent"], {"date": "2026-07-01"})

        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "Fever")

    def test_daily_absent_list_ignores_draft(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        response = self.administrator.get(self.urls["absent"], {"date": "2026-07-01"})

        self.assertContains(response, "No submitted absences on this date.")

    def test_missing_report_shows_draft_and_not_taken(self):
        with mock.patch("core.models.business_today", new=lambda: date(2026, 10, 10)):
            response = self.administrator.get(
                self.urls["missing"],
                {"start": "2026-07-01", "end": "2026-07-03", "section": self.section.pk},
            )

        rows = response.context["rows"]
        self.assertEqual(
            [(row["date"], row["state"].label) for row in rows],
            [
                (date(2026, 7, 1), "Draft"),
                (date(2026, 7, 2), "Not taken"),
                (date(2026, 7, 3), "Not taken"),
            ],
        )
        self.assertContains(response, "Draft")

    def test_missing_report_rejects_oversized_range(self):
        response = self.administrator.get(
            self.urls["missing"], {"start": "2026-06-01", "end": "2027-12-31"}
        )

        self.assertIsNone(response.context["rows"])
        self.assertContains(response, "at most")

    def test_monthly_summary_page(self):
        self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.PRESENT)

        response = self.administrator.get(
            self.urls["monthly"], {"section": self.section.pk, "month": "2026-07"}
        )

        self.assertContains(response, "Ravi Rao")
        self.assertContains(response, "100.0%")
        self.assertEqual(response.context["summary"]["totals"]["submitted_days"], 1)

    def test_monthly_summary_rejects_bad_month(self):
        response = self.administrator.get(
            self.urls["monthly"], {"section": self.section.pk, "month": "2026-13"}
        )

        self.assertIsNone(response.context["summary"])
        self.assertContains(response, "Enter a month as YYYY-MM.")

    def test_student_page_shows_percentage_and_register_status(self):
        self.capture_and_submit(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        response = self.administrator.get(
            reverse("core:student-attendance", args=[self.student.pk])
        )

        self.assertEqual(response.context["percentage"], 0.0)
        self.assertContains(response, "0.0%")
        self.assertContains(response, "Submitted")

    def test_student_page_draft_not_counted(self):
        self.register.capture(enrollment=self.enrollment, status=AttendanceStatus.ABSENT)

        response = self.administrator.get(
            reverse("core:student-attendance", args=[self.student.pk])
        )

        self.assertEqual(response.context["total"], 0)
        self.assertIsNone(response.context["percentage"])
        self.assertEqual(len(response.context["entries"]), 1)  # history still shows it
        self.assertContains(response, "Draft")


class AppWideAuthorizationSweepTests(AuthorizationClientsMixin, TestCase):
    """Gate 8: every core URL requires login and the administrator permission."""

    # The one URL that any signed-in user may open: the school logo image shown in
    # the header (ADR 0020, D9). Its login requirement is still swept below.
    SIGNED_IN_ONLY = {"school-logo"}

    def _urls(self):
        from django.urls import URLPattern

        from core import urls as core_urls

        for pattern in core_urls.urlpatterns:
            assert isinstance(pattern, URLPattern)
            kwargs = {name: 1 for name in pattern.pattern.regex.groupindex}
            yield pattern.name, reverse(f"core:{pattern.name}", kwargs=kwargs)

    def test_every_url_is_covered(self):
        names = [name for name, _ in self._urls()]
        self.assertGreaterEqual(len(names), 30)
        self.assertEqual(len(names), len(set(names)))

    def test_anonymous_is_sent_to_login_everywhere(self):
        for name, url in self._urls():
            for method in ("get", "post"):
                with self.subTest(url=name, method=method):
                    response = getattr(self.anonymous, method)(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_non_administrator_is_forbidden_everywhere(self):
        for name, url in self._urls():
            if name in self.SIGNED_IN_ONLY:
                continue
            for method in ("get", "post"):
                with self.subTest(url=name, method=method):
                    response = getattr(self.non_admin, method)(url)
                    self.assertEqual(response.status_code, 403)
