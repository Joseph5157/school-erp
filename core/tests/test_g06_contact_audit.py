"""G-06 reset spec §3 (PR 1): every change to a guardian's phone or email is audited (ADR 0029 R17)."""
import re
from pathlib import Path

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import imports
from core.models import Guardian
from core.tests.test_phase7_import import ImportFixture, student_row, workbook

Event = SecurityEvent.EventType
User = get_user_model()
CONTACT_EVENTS = (Event.GUARDIAN_PHONE_CHANGED, Event.GUARDIAN_EMAIL_CHANGED)


def contact_events(**filters):
    return SecurityEvent.objects.filter(event_type__in=CONTACT_EVENTS, **filters)


class AdminClientMixin:
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="office", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.login(username="office", password="pass-12345")


class ModelAuditTests(AdminClientMixin, TestCase):
    def test_phone_change_records_one_event_without_the_value(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        guardian.phone = "98450 12345"
        guardian.save(actor=self.admin)
        event = contact_events().get()
        self.assertEqual(event.event_type, Event.GUARDIAN_PHONE_CHANGED)
        self.assertEqual((event.actor, event.guardian_id_ref), (self.admin, guardian.pk))
        self.assertEqual(event.event_class, SecurityEvent.EventClass.ROUTINE)
        self.assertEqual(event.detail, {})

    def test_email_change_and_both_changes(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        guardian.email = "meena@example.com"
        guardian.save()
        self.assertEqual(list(contact_events().values_list("event_type", flat=True)),
                         [Event.GUARDIAN_EMAIL_CHANGED])
        guardian.phone, guardian.email = "98450 12345", "other@example.com"
        guardian.save()
        self.assertEqual(contact_events().count(), 3)

    def test_no_event_when_contact_unchanged(self):
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="98450 12345")
        before = contact_events().count()
        guardian.full_name = "Meena R. Rao"
        guardian.save()
        guardian.save(update_fields=["full_name"])
        self.assertEqual(contact_events().count(), before)

    def test_create_with_contact_counts_and_without_does_not(self):
        Guardian.objects.create(full_name="No Contact")
        self.assertFalse(contact_events().exists())
        Guardian.objects.create(full_name="With Both", phone="98450 12345", email="a@example.com")
        self.assertEqual(contact_events().count(), 2)

    def test_stale_instance_compares_with_the_stored_row(self):
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="1")
        stale = Guardian.objects.get(pk=guardian.pk)
        guardian.phone = "2"
        guardian.save()
        stale.phone = "2"  # same as stored now: no further event
        stale.save()
        self.assertEqual(contact_events(event_type=Event.GUARDIAN_PHONE_CHANGED).count(), 2)

    def test_deferred_instance_saves_without_a_false_event(self):
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="1", email="a@example.com")
        before = contact_events().count()
        partial = Guardian.objects.only("full_name").get(pk=guardian.pk)
        partial.full_name = "Meena R. Rao"
        partial.save()
        self.assertEqual(contact_events().count(), before)

    def test_unsaved_phone_change_outside_update_fields_is_not_audited(self):
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="1")
        before = contact_events().count()
        guardian.phone = "2"
        guardian.full_name = "Renamed"
        guardian.save(update_fields=["full_name"])
        self.assertEqual(contact_events().count(), before)
        guardian.refresh_from_db()
        self.assertEqual(guardian.phone, "1")

    def test_get_or_create_with_a_phone_is_audited(self):
        Guardian.objects.get_or_create(full_name="Via Get Or Create", defaults={"phone": "98450 1"})
        self.assertEqual(contact_events(event_type=Event.GUARDIAN_PHONE_CHANGED).count(), 1)

    def test_event_rolls_back_with_the_save(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        with self.assertRaises(RuntimeError), transaction.atomic():
            guardian.phone = "98450 12345"
            guardian.save()
            raise RuntimeError("caller fails after saving")
        self.assertFalse(contact_events().exists())

    def test_audit_false_records_nothing(self):
        Guardian(full_name="Demo", phone="98450 12345").save(audit=False)
        self.assertFalse(contact_events().exists())

    def test_bulk_paths_refuse_contact_fields(self):
        Guardian.objects.create(full_name="Meena Rao")
        with self.assertRaises(ValueError):
            Guardian.objects.update(phone="1")
        with self.assertRaises(ValueError):
            Guardian.objects.filter(full_name="Meena Rao").update(email="a@example.com")
        with self.assertRaises(ValueError):
            Guardian.objects.bulk_update(list(Guardian.objects.all()), ["phone"])
        with self.assertRaises(ValueError):
            Guardian.objects.bulk_create([Guardian(full_name="X", phone="1")])
        # Other fields still work in bulk.
        Guardian.objects.update(full_name="Renamed")
        Guardian.objects.bulk_create([Guardian(full_name="No contact")])


class WritePathTests(AdminClientMixin, TestCase):
    def test_edit_form_records_actor(self):
        guardian = Guardian.objects.create(full_name="Meena Rao", phone="1")
        response = self.client.post(
            reverse("core:guardian-edit", args=[guardian.pk]),
            {"full_name": "Meena Rao", "phone": "98450 99999", "email": ""},
        )
        self.assertEqual(response.status_code, 302)
        event = contact_events(event_type=Event.GUARDIAN_PHONE_CHANGED).latest("pk")
        self.assertEqual(event.actor, self.admin)

    def test_create_form_records_actor(self):
        self.client.post(
            reverse("core:guardian-create"),
            {"full_name": "Brand New", "phone": "98450 77777", "email": "", "confirm_new": "1"},
        )
        guardian = Guardian.objects.get(full_name="Brand New")
        self.assertEqual(contact_events(guardian_id_ref=guardian.pk).get().actor, self.admin)

    def test_demo_seed_records_no_contact_events(self):
        call_command("seed_demo", allow_non_debug=True, verbosity=0)
        self.assertTrue(Guardian.objects.exists())
        self.assertFalse(contact_events().exists())


class ImportPathTests(ImportFixture):
    def test_import_records_events_with_the_importer(self):
        batch = self.batch_for(workbook([student_row("Asha", roll="1")]))
        imports.commit_batch(batch, user=self.admin)
        father = Guardian.objects.get(full_name="Ravi Kumar")
        event = contact_events(guardian_id_ref=father.pk).get()
        self.assertEqual((event.event_type, event.actor), (Event.GUARDIAN_PHONE_CHANGED, self.admin))


class HistoryTests(AdminClientMixin, TestCase):
    def test_profile_history_lists_contact_changes_and_pages(self):
        guardian = Guardian.objects.create(full_name="Meena Rao")
        SecurityEvent.record(Event.PASSWORD_RESET_BY_ADMIN, actor=self.admin, guardian=guardian)
        for n in range(30):
            guardian.phone = str(n)
            guardian.save(actor=self.admin)
        url = reverse("core:guardian-detail", args=[guardian.pk])
        first = self.client.get(url)
        self.assertContains(first, "Guardian phone changed")
        self.assertEqual(len(first.context["events"]), 25)
        # The reset is older than every phone edit, so it is on the last page, not lost.
        last = self.client.get(url, {"page": 2})
        self.assertContains(last, "Password reset by administrator")
        # Page links keep the reader on the history section.
        self.assertContains(first, "page=2#history")


class GuardsTests(TestCase):
    def test_anchor_event_exists_after_migrate(self):
        self.assertTrue(SecurityEvent.objects.filter(event_type=Event.CONTACT_AUDIT_STARTED).exists())

    def test_guardian_not_registered_in_django_admin(self):
        self.assertNotIn(Guardian, admin.site._registry)

    def test_audit_false_only_in_demo_seeds(self):
        found = set()
        for path in Path("core").rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            if re.search(r"audit\s*=\s*False", path.read_text(encoding="utf-8")):
                found.add(path.name)
        # models.py defines and documents the option; the seeds are its only user.
        self.assertEqual(found, {"models.py", "seed_demo.py"})
