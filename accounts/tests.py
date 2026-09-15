from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import User


class CustomUserModelTests(TestCase):
    def test_auth_user_model_points_to_accounts_user(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        self.assertIs(get_user_model(), User)

    def test_can_create_user(self):
        user = User.objects.create_user(
            username="jdoe", email="jdoe@example.com", password="s3cret-pass"
        )

        self.assertTrue(user.pk)
        self.assertEqual(user.username, "jdoe")
        self.assertTrue(user.check_password("s3cret-pass"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_can_create_superuser(self):
        admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="s3cret-pass"
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_user_has_no_school_domain_fields(self):
        """The User model is an authentication identity only.

        It must not carry Student/Guardian/Teacher/academic fields --
        those belong to future school-domain apps, not accounts.
        """
        field_names = {field.name for field in User._meta.get_fields()}
        forbidden = {
            "student",
            "guardian",
            "teacher",
            "applicant",
            "school",
            "class_grade",
            "section",
            "academic_year",
        }

        self.assertEqual(field_names & forbidden, set())
