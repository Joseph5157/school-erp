from django.contrib.auth.models import Group
from django.test import TestCase

from accounts.models import SecurityEvent

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
