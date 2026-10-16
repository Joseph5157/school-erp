from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import SecurityEvent
from core import teacher_accounts
from core.models import TEACHERS_GROUP_NAME

User = get_user_model()

NEW_EVENTS = (
    "TEACHER_ACCOUNT_CREATED",
    "TEACHER_PASSWORD_RESET",
    "TEACHER_USERNAME_CHANGED",
    "TEACHER_DEACTIVATED",
    "TEACHER_REACTIVATED",
)


class TeacherPermissionAndEventTests(TestCase):
    def test_school_administrators_hold_the_permission(self):
        group = Group.objects.get(name="School Administrators")
        self.assertTrue(
            group.permissions.filter(
                content_type__app_label="accounts", codename="manage_teacher_accounts"
            ).exists()
        )

    def test_teachers_group_does_not_hold_it(self):
        group = Group.objects.get(name="Teachers")
        self.assertFalse(group.permissions.filter(codename="manage_teacher_accounts").exists())

    def test_new_event_types_exist_and_are_kept_as_history(self):
        for name in NEW_EVENTS:
            with self.subTest(event=name):
                event_type = getattr(SecurityEvent.EventType, name)
                self.assertEqual(
                    SecurityEvent.class_for(event_type), SecurityEvent.EventClass.HISTORY
                )
                self.assertNotIn(event_type, SecurityEvent.ROUTINE_TYPES)

    def test_event_can_be_recorded(self):
        event = SecurityEvent.record(SecurityEvent.EventType.TEACHER_ACCOUNT_CREATED)
        self.assertEqual(event.event_class, SecurityEvent.EventClass.HISTORY)


def make_actor(username="office"):
    return User.objects.create_user(username=username, password="pass-12345")


class TeacherServiceTests(TestCase):
    def setUp(self):
        self.actor = make_actor()

    def create(self, username="asha.rao", **extra):
        defaults = dict(first_name="Asha", last_name="Rao", email="asha@example.com")
        defaults.update(extra)
        return teacher_accounts.create_teacher(username=username, actor=self.actor, **defaults)

    def test_create_makes_a_teachers_group_login_that_must_change_its_password(self):
        user, password = self.create()
        self.assertTrue(user.groups.filter(name=TEACHERS_GROUP_NAME).exists())
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.is_active)
        self.assertEqual((user.first_name, user.last_name), ("Asha", "Rao"))
        self.assertIsNotNone(authenticate(username="asha.rao", password=password))

    def test_create_records_an_event_without_the_password(self):
        user, password = self.create()
        event = SecurityEvent.objects.get(
            event_type=SecurityEvent.EventType.TEACHER_ACCOUNT_CREATED, subject_user=user
        )
        self.assertEqual(event.actor, self.actor)
        self.assertNotIn(password, str(event.detail))

    def test_create_rejects_duplicate_and_invalid_usernames(self):
        self.create()
        for bad in ("asha.rao", "ASHA.RAO", "x", "has space"):
            with self.subTest(username=bad):
                with self.assertRaises(ValidationError):
                    self.create(username=bad)
        self.assertEqual(User.objects.filter(username__iexact="asha.rao").count(), 1)

    def test_queryset_lists_only_teachers_with_assignment_counts(self):
        teacher, _ = self.create()
        User.objects.create_user(username="plain", password="pass-12345")
        rows = list(teacher_accounts.teacher_queryset())
        self.assertEqual([row.pk for row in rows], [teacher.pk])
        self.assertEqual(rows[0].assignment_count, 0)

    def test_queryset_excludes_superusers_even_in_the_group(self):
        root = User.objects.create_superuser(username="root", password="pass-12345")
        root.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        self.assertNotIn(root.pk, [row.pk for row in teacher_accounts.teacher_queryset()])

    def test_reset_changes_password_forces_change_and_ends_sessions(self):
        user, old = self.create()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        version = User.objects.get(pk=user.pk).session_version
        new = teacher_accounts.reset_teacher_password(user=user, actor=self.actor)
        fresh = User.objects.get(pk=user.pk)
        self.assertTrue(fresh.must_change_password)
        self.assertEqual(fresh.session_version, version + 1)
        self.assertIsNone(authenticate(username="asha.rao", password=old))
        self.assertIsNotNone(authenticate(username="asha.rao", password=new))
        self.assertTrue(
            SecurityEvent.objects.filter(
                event_type=SecurityEvent.EventType.TEACHER_PASSWORD_RESET, subject_user=user
            ).exists()
        )

    def test_change_username(self):
        user, password = self.create()
        teacher_accounts.change_teacher_username(
            user=user, new_username="asha.r", actor=self.actor
        )
        self.assertEqual(User.objects.get(pk=user.pk).username, "asha.r")
        self.assertIsNotNone(authenticate(username="asha.r", password=password))
        self.assertTrue(
            SecurityEvent.objects.filter(
                event_type=SecurityEvent.EventType.TEACHER_USERNAME_CHANGED, subject_user=user
            ).exists()
        )

    def test_change_username_rejects_taken_or_invalid(self):
        user, _ = self.create()
        self.create(username="other.teacher", first_name="O", last_name="T")
        for bad in ("other.teacher", "OTHER.TEACHER", "!"):
            with self.subTest(username=bad):
                with self.assertRaises(ValidationError):
                    teacher_accounts.change_teacher_username(
                        user=user, new_username=bad, actor=self.actor
                    )

    def test_deactivate_requires_a_reason_blocks_sign_in_and_ends_sessions(self):
        user, password = self.create()
        version = User.objects.get(pk=user.pk).session_version
        with self.assertRaises(ValidationError):
            teacher_accounts.deactivate_teacher(user=user, reason="  ", actor=self.actor)
        teacher_accounts.deactivate_teacher(user=user, reason="Left the school", actor=self.actor)
        fresh = User.objects.get(pk=user.pk)
        self.assertFalse(fresh.is_active)
        self.assertEqual(fresh.session_version, version + 1)
        self.assertIsNone(authenticate(username="asha.rao", password=password))
        event = SecurityEvent.objects.get(
            event_type=SecurityEvent.EventType.TEACHER_DEACTIVATED, subject_user=user
        )
        self.assertEqual(event.detail["reason"], "Left the school")

    def test_deactivate_twice_and_reactivate_rules(self):
        user, password = self.create()
        with self.assertRaises(ValidationError):  # already active
            teacher_accounts.reactivate_teacher(user=user, actor=self.actor)
        teacher_accounts.deactivate_teacher(user=user, reason="Leave", actor=self.actor)
        with self.assertRaises(ValidationError):  # already inactive
            teacher_accounts.deactivate_teacher(user=user, reason="Again", actor=self.actor)
        teacher_accounts.reactivate_teacher(user=user, actor=self.actor)
        self.assertTrue(User.objects.get(pk=user.pk).is_active)
        self.assertIsNotNone(authenticate(username="asha.rao", password=password))

    def test_cannot_deactivate_own_login(self):
        user, _ = self.create()
        with self.assertRaises(ValidationError):
            teacher_accounts.deactivate_teacher(user=user, reason="Oops", actor=user)
        self.assertTrue(User.objects.get(pk=user.pk).is_active)

    def test_every_action_refuses_non_teachers_and_superusers(self):
        plain = User.objects.create_user(username="plain", password="pass-12345")
        root = User.objects.create_superuser(username="root", password="pass-12345")
        root.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        for target in (plain, root):
            with self.subTest(target=target.username):
                for action in (
                    lambda: teacher_accounts.reset_teacher_password(user=target, actor=self.actor),
                    lambda: teacher_accounts.change_teacher_username(
                        user=target, new_username="new.name", actor=self.actor),
                    lambda: teacher_accounts.deactivate_teacher(
                        user=target, reason="x", actor=self.actor),
                    lambda: teacher_accounts.reactivate_teacher(user=target, actor=self.actor),
                ):
                    with self.assertRaises(ValidationError):
                        action()
                fresh = User.objects.get(pk=target.pk)
                self.assertTrue(fresh.is_active)
                self.assertEqual(fresh.username, target.username)
