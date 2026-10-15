# Phase 7 Gate 1 — Consent, Notification Outbox and ASSIST "To send" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recorded WhatsApp consent per guardian, a per-school channel setting, an idempotent notification outbox with minimal content, and an office "To send" page for ASSIST mode — with no producers yet and no network calls.

**Architecture:** Three new models in `core` plus `School.notification_channel`; database triggers make consent append-only and notifications/templates history-safe; a service module `core/notifications.py` holds every rule (consent, enqueue, render, link, send/dismiss); thin views in `core/notification_views.py`; consent card on the existing guardian page; permissions granted to School Administrators by data migration.

**Tech Stack:** Python 3.13, Django 5.2.17, PostgreSQL 18 (SQLite for quick runs), Bootstrap 5.3.3, Django `TestCase`, ruff.

**Spec:** `docs/superpowers/specs/2026-10-15-phase7-gate1-notifications-design.md` (approved 2026-10-15). Authority above it: `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`, `docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md`.

## Global Constraints

- Branch `phase-7/gate-1-notifications` (created from `main` at `fa67834`; spec committed as `a9160c1`).
- No network calls anywhere. No producers (absence, announcement, result) in this gate.
- Notification parameters may only use the keys `first_name`, `date`, `portal_url` (D4). Never marks, grades or absence reasons.
- No consent = no message. Consent is checked at enqueue, when the To send page loads, and at Mark as sent.
- School modes selectable in the form: `PORTAL_ONLY` and `ASSIST` only. Default `PORTAL_ONLY`.
- Templates: English (`language="en"`) only in this gate.
- Permissions only to "School Administrators": `core.send_notification`, `core.view_notification`, `core.add_guardiancontactconsent`, `core.view_guardiancontactconsent`.
- History tables use database triggers on both SQLite and PostgreSQL (same style as `core/migrations/0054_import_batch_history_guards.py`).
- New pages use the U1 shell and Bootstrap `card` classes (U2's `.erp-card` is not on `main` yet).
- Guardian portal pages unchanged.
- Python line length 100; ruff rules E, F, I, UP, B (no `%` string formatting — UP031).
- Quick runs: `env -u DB_NAME .venv/Scripts/python.exe manage.py test <labels> --noinput` (Git Bash, SQLite). Full suite: PowerShell with DB variables loaded (`foreach ($k in 'DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT') { Set-Item "env:$k" ([Environment]::GetEnvironmentVariable($k,'User')) }`), `.\.venv\Scripts\python.exe manage.py test --noinput` (add `--parallel 4` once PR #48 is merged). Known pre-existing failure on `main`: `core.tests.test_models.AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates`.

## Review Focus

1. **A guardian opts out after a message was prepared** — the message must never be offered or marked sent. Pinned in Task 3 (`test_to_send_skips_withdrawn_consent`, `test_mark_sent_after_opt_out_skips`).
2. **Double click / two staff on the same message** — the second Mark as sent or Dismiss must be refused with a message, not double-recorded. Pinned in Task 5 (`test_mark_sent_twice_is_refused`).
3. **Guardian phone stored in a local format ("98765 43210", "098765-43210") or junk ("N/A")** — local formats must produce a working `wa.me/91…` link; junk must show the fix-phone warning, not a broken link. Pinned in Task 3 (`test_whatsapp_link_normalises_local_numbers`, `test_whatsapp_link_none_for_unusable_phone`) and Task 5 (`test_unusable_phone_shows_fix_link`).
4. **Message text with characters that break a URL ("&", "#", "?", spaces)** — the link must carry the exact text. Pinned in Task 3 (`test_whatsapp_link_encodes_text`).
5. **Someone posts `notification_channel=API` to the School form** — must be rejected while API is not built. Pinned in Task 4 (`test_school_form_rejects_api_mode`).

---

## File structure

| File | Responsibility |
|---|---|
| `core/models.py` (modify) | `School.NotificationMode`, `School.notification_channel`, `NOTIFICATION_PARAMETERS`, `GuardianContactConsent`, `NotificationTemplate`, `Notification` |
| `core/migrations/0056_phase7_notifications.py` (generated) | Schema |
| `core/migrations/0057_notification_history_guards.py` (create) | Triggers |
| `core/migrations/0058_add_notification_permissions_to_group.py` (create) | Grant permissions |
| `core/notifications.py` (create) | All notification rules |
| `core/notification_views.py` (create) | Record consent, To send, mark sent, dismiss |
| `core/forms.py` (modify) | `SchoolForm` channel field; `ContactConsentForm` |
| `core/views.py` (modify `guardian_detail`) | Consent context |
| `core/urls.py` (modify) | Four routes |
| `core/navigation.py` (modify) | "To send" link |
| `core/templates/core/notifications_to_send.html` (create) | To send page |
| `core/templates/core/_guardian_consent.html` (create) | Consent card |
| `core/templates/core/guardian_detail.html` (modify) | Include the card |
| `core/templates/core/school_detail.html` (modify) | Show the mode |
| `core/tests/test_phase7_notifications.py` (create) | All Gate 1 tests |
| `docs/adr/0015-…md`, `docs/PHASE_7_…PLAN.md` (modify) | DISMISSED amendment, Gate 1 notes |

---

### Task 1: Models and schema migration

**Files:**
- Modify: `core/models.py` (School; add three models at the end of the file)
- Create: `core/migrations/0056_phase7_notifications.py` (via `makemigrations`)
- Create: `core/tests/test_phase7_notifications.py`

**Interfaces:**
- Produces: `School.NotificationMode` (`PORTAL_ONLY`, `ASSIST`, `API`, `SMS`), `School.notification_channel`; `NOTIFICATION_PARAMETERS = ("first_name", "date", "portal_url")`; `GuardianContactConsent` with nested `Channel` (`WHATSAPP`), `Status` (`OPTED_IN`, `OPTED_OUT`), `Source` (`PAPER_FORM`, `IN_PERSON`, `PHONE_CALL`, `OTHER`), related name `guardian.contact_consents`, default ordering `["-recorded_at", "-pk"]`; `NotificationTemplate` (`key`, `channel`, `language`, `version`, `body`, `approved`), `clean()` validates placeholders; `Notification` with nested `Type` (`ABSENCE`, `RESULT_PUBLISHED`, `ANNOUNCEMENT`) and `Status` (`QUEUED`, `PREPARED`, `SENT`, `DELIVERED`, `FAILED`, `SKIPPED_NO_CONSENT`, `DISMISSED`), permission `send_notification`.
- Produces (tests): fixture `NotificationFixture` with `self.school` (ASSIST), `self.guardian` (phone "98765 43210"), `self.asha` (Student) linked as father's child, `self.template` (approved `absence_alert` v1), helpers `self.opt_in(guardian=None)`, `self.opt_out(guardian=None)`, `self.params()`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_phase7_notifications.py`:

```python
"""Phase 7 Gate 1: consent, notification outbox and ASSIST sending (ADR 0015)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Guardian,
    GuardianContactConsent,
    NotificationTemplate,
    RelationshipType,
    School,
    StudentGuardian,
)
from core.tests.phase4_fixtures import Phase4Fixture

BODY = "Dear parent, {first_name} was absent on {date}. Details: {portal_url}"


class NotificationFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        self.school = School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST
        )
        self.guardian = Guardian.objects.create(full_name="Ravi Kumar", phone="98765 43210")
        self.asha, _ = self.make_student("Asha Reddy")
        StudentGuardian.objects.create(
            student=self.asha, guardian=self.guardian, relationship_type=RelationshipType.FATHER
        )
        self.template = NotificationTemplate.objects.create(
            key="absence_alert", version=1, body=BODY, approved=True
        )

    def consent(self, status, guardian=None):
        return GuardianContactConsent.objects.create(
            guardian=guardian or self.guardian, status=status,
            source=GuardianContactConsent.Source.PAPER_FORM, recorded_by=self.admin,
        )

    def opt_in(self, guardian=None):
        return self.consent(GuardianContactConsent.Status.OPTED_IN, guardian)

    def opt_out(self, guardian=None):
        return self.consent(GuardianContactConsent.Status.OPTED_OUT, guardian)

    def params(self):
        return {"first_name": "Asha", "date": "12 Oct 2026", "portal_url": "https://erp.example/p/"}


class ModelTests(NotificationFixture, TestCase):
    def test_school_defaults_to_portal_only(self):
        School.objects.all().delete()
        school = School.objects.create(name="Other")
        self.assertEqual(school.notification_channel, School.NotificationMode.PORTAL_ONLY)

    def test_template_accepts_allowed_placeholders(self):
        NotificationTemplate(key="x", version=1, body=BODY).full_clean()

    def test_template_rejects_unknown_placeholder(self):
        template = NotificationTemplate(key="x", version=1, body="Marks: {score}")
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_template_rejects_broken_braces(self):
        with self.assertRaises(ValidationError):
            NotificationTemplate(key="x", version=1, body="Hello {first_name").full_clean()

    def test_consent_history_newest_first(self):
        first = self.opt_in()
        second = self.opt_out()
        self.assertEqual(list(self.guardian.contact_consents.all()), [second, first])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: ERROR — `ImportError: cannot import name 'GuardianContactConsent' from 'core.models'`

- [ ] **Step 3: Add the models**

In `core/models.py`, inside `class School`, before `name = …`:

```python
    class NotificationMode(models.TextChoices):
        PORTAL_ONLY = "PORTAL_ONLY", "Portal only (no WhatsApp messages)"
        ASSIST = "ASSIST", "WhatsApp, sent by office staff (ASSIST)"
        API = "API", "WhatsApp Business API"
        SMS = "SMS", "SMS"

```

and after `name = models.CharField(max_length=255)`:

```python
    notification_channel = models.CharField(
        "Messages to guardians",
        max_length=12,
        choices=NotificationMode.choices,
        default=NotificationMode.PORTAL_ONLY,
    )
```

First check imports: `grep -n "^import\|^from django.conf import settings\|^from django.utils import timezone\|^from django.core.exceptions" core/models.py`. `settings`, `timezone` and `ValidationError` are already imported (ImportBatch uses them); add `import string` to the standard-library imports.

At the end of `core/models.py`:

```python
# --- Phase 7 Gate 1: consent and notification outbox (ADR 0015) -------------

NOTIFICATION_PARAMETERS = ("first_name", "date", "portal_url")


class GuardianContactConsent(models.Model):
    """One recorded opt-in or opt-out. Append-only; the latest row is current."""

    class Channel(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        OPTED_IN = "OPTED_IN", "Opted in"
        OPTED_OUT = "OPTED_OUT", "Opted out"

    class Source(models.TextChoices):
        PAPER_FORM = "PAPER_FORM", "Paper form"
        IN_PERSON = "IN_PERSON", "In person"
        PHONE_CALL = "PHONE_CALL", "Phone call"
        OTHER = "OTHER", "Other"

    guardian = models.ForeignKey(
        Guardian, on_delete=models.PROTECT, related_name="contact_consents"
    )
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.WHATSAPP)
    status = models.CharField(max_length=10, choices=Status.choices)
    source = models.CharField(max_length=12, choices=Source.choices)
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["OPTED_IN", "OPTED_OUT"]),
                name="guardiancontactconsent_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.guardian} {self.get_channel_display()} {self.get_status_display()}"


class NotificationTemplate(models.Model):
    """A versioned message text. Approved bodies never change; edit = new version."""

    key = models.SlugField(max_length=50)
    channel = models.CharField(
        max_length=12,
        choices=GuardianContactConsent.Channel.choices,
        default=GuardianContactConsent.Channel.WHATSAPP,
    )
    language = models.CharField(max_length=10, default="en")
    version = models.PositiveIntegerField()
    body = models.TextField()
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key", "channel", "language", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "channel", "language", "version"],
                name="notificationtemplate_unique_version",
            ),
        ]

    def clean(self):
        super().clean()
        try:
            names = {name for _, name, _, _ in string.Formatter().parse(self.body) if name}
        except ValueError:
            raise ValidationError({"body": "The text has an unmatched { or }."}) from None
        if names - set(NOTIFICATION_PARAMETERS):
            allowed = ", ".join(f"{{{name}}}" for name in NOTIFICATION_PARAMETERS)
            raise ValidationError({"body": f"Only these placeholders are allowed: {allowed}."})

    def __str__(self):
        return f"{self.key} v{self.version} ({self.language})"


class Notification(models.Model):
    """One message to one guardian, in the outbox (ADR 0015)."""

    class Type(models.TextChoices):
        ABSENCE = "ABSENCE", "Absence alert"
        RESULT_PUBLISHED = "RESULT_PUBLISHED", "Report card published"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        PREPARED = "PREPARED", "Ready to send"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        SKIPPED_NO_CONSENT = "SKIPPED_NO_CONSENT", "Skipped — no consent"
        DISMISSED = "DISMISSED", "Dismissed"

    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="notifications")
    student = models.ForeignKey(
        "Student", on_delete=models.PROTECT, null=True, blank=True, related_name="notifications"
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.PROTECT, related_name="notifications"
    )
    parameters = models.JSONField(default=dict)
    channel_mode = models.CharField(max_length=12, choices=School.NotificationMode.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    idempotency_key = models.CharField(max_length=200, unique=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    marked_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    marked_sent_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismiss_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
        permissions = [("send_notification", "Can send prepared notifications")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    "QUEUED", "PREPARED", "SENT", "DELIVERED", "FAILED",
                    "SKIPPED_NO_CONSENT", "DISMISSED",
                ]),
                name="notification_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.get_type_display()} to {self.guardian} ({self.get_status_display()})"
```

- [ ] **Step 4: Generate the migration**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py makemigrations core --name phase7_notifications`
Expected: `core/migrations/0056_phase7_notifications.py` with AddField `school.notification_channel` and CreateModel for the three models.

- [ ] **Step 5: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: `Ran 5 tests` … `OK`

- [ ] **Step 6: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/models.py core/migrations/0056_phase7_notifications.py core/tests/test_phase7_notifications.py
git commit -m "feat(phase7): consent, template and notification models"
```

---

### Task 2: History guards (database triggers)

**Files:**
- Create: `core/migrations/0057_notification_history_guards.py`
- Test: `core/tests/test_phase7_notifications.py`

**Interfaces:**
- Consumes: Task 1 tables `core_guardiancontactconsent`, `core_notificationtemplate`, `core_notification`.
- Produces: triggers — consent: no UPDATE, no DELETE; template: no DELETE, `key/channel/language/version/body` immutable, `approved` cannot go true → false; notification: no DELETE, `guardian_id/student_id/type/template_id/parameters/channel_mode/idempotency_key/created_at` immutable, status changes only along the allowed transitions, same-status updates only while QUEUED or PREPARED.

- [ ] **Step 1: Write the failing tests**

Add `from django.db import DatabaseError, transaction` and `Notification` (in the `core.models` import list) at the top, then append:

```python
class HistoryGuardTests(NotificationFixture, TestCase):
    def notification(self, status=Notification.Status.PREPARED):
        return Notification.objects.create(
            guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
            template=self.template, parameters=self.params(),
            channel_mode=School.NotificationMode.ASSIST, status=status,
            idempotency_key=f"t:{status}",
        )

    def refused(self, queryset, **changes):
        with self.assertRaises(DatabaseError), transaction.atomic():
            queryset.update(**changes)

    def test_consent_is_append_only(self):
        consent = self.opt_in()
        rows = GuardianContactConsent.objects.filter(pk=consent.pk)
        self.refused(rows, status="OPTED_OUT")
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()

    def test_template_body_and_approval_are_fixed(self):
        rows = NotificationTemplate.objects.filter(pk=self.template.pk)
        self.refused(rows, body="Changed {first_name}")
        self.refused(rows, approved=False)
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()
        draft = NotificationTemplate.objects.create(key="absence_alert", version=2, body=BODY)
        NotificationTemplate.objects.filter(pk=draft.pk).update(approved=True)

    def test_allowed_transitions(self):
        prepared = self.notification()
        Notification.objects.filter(pk=prepared.pk).update(status="SENT")
        Notification.objects.filter(pk=prepared.pk).update(status="DELIVERED")
        queued = self.notification(Notification.Status.QUEUED)
        Notification.objects.filter(pk=queued.pk).update(attempts=1)
        Notification.objects.filter(pk=queued.pk).update(status="PREPARED")
        Notification.objects.filter(pk=queued.pk).update(status="DISMISSED")

    def test_refused_transitions_and_frozen_states(self):
        sent = self.notification()
        rows = Notification.objects.filter(pk=sent.pk)
        rows.update(status="SENT")
        self.refused(rows, status="PREPARED")
        self.refused(rows, dismiss_reason="late")
        skipped = Notification.objects.filter(pk=self.notification("SKIPPED_NO_CONSENT").pk)
        self.refused(skipped, status="PREPARED")

    def test_notification_content_is_immutable_and_never_deleted(self):
        rows = Notification.objects.filter(pk=self.notification().pk)
        self.refused(rows, parameters={"first_name": "Other"})
        self.refused(rows, idempotency_key="other")
        with self.assertRaises(DatabaseError), transaction.atomic():
            rows.delete()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications.HistoryGuardTests --noinput`
Expected: FAIL — `AssertionError: DatabaseError not raised` in the refusal tests (`test_allowed_transitions` passes).

- [ ] **Step 3: Write the trigger migration**

Create `core/migrations/0057_notification_history_guards.py`:

```python
# Phase 7 Gate 1 (ADR 0015): consent, templates and notifications are history.
#
# - GuardianContactConsent: no UPDATE, no DELETE (append-only).
# - NotificationTemplate: no DELETE; key/channel/language/version/body fixed;
#   approved may only go from false to true.
# - Notification: no DELETE; content fixed; status only moves forward along
#   QUEUED -> PREPARED/FAILED/SKIPPED_NO_CONSENT,
#   PREPARED -> SENT/DISMISSED/SKIPPED_NO_CONSENT/FAILED, SENT -> DELIVERED;
#   rows may be touched without a status change only while QUEUED or PREPARED.

from django.db import migrations

CONSENT = "Consent records cannot be changed or deleted."
TEMPLATE = "An approved template cannot be changed; create a new version."
TEMPLATE_DELETE = "Notification templates are never deleted."
NOTIFICATION = "Notifications cannot be deleted or rewritten."
STATUS = "That notification status change is not allowed."

TEMPLATE_FIXED = ["key", "channel", "language", "version", "body"]
NOTIFICATION_FIXED = [
    "guardian_id", "student_id", "type", "template_id", "parameters", "channel_mode",
    "idempotency_key", "created_at",
]
TRANSITION = (
    "(OLD.status = NEW.status AND OLD.status IN ('QUEUED', 'PREPARED'))"
    " OR (OLD.status = 'QUEUED' AND NEW.status IN ('PREPARED', 'FAILED', 'SKIPPED_NO_CONSENT'))"
    " OR (OLD.status = 'PREPARED'"
    " AND NEW.status IN ('SENT', 'DISMISSED', 'SKIPPED_NO_CONSENT', 'FAILED'))"
    " OR (OLD.status = 'SENT' AND NEW.status = 'DELIVERED')"
)
UNAPPROVE = "OLD.approved AND NOT NEW.approved"


def _changed(columns, op):
    return " OR ".join(f"NEW.{c} {op} OLD.{c}" for c in columns)


SQLITE = [
    f"CREATE TRIGGER core_gcc_no_update BEFORE UPDATE ON core_guardiancontactconsent "
    f"BEGIN SELECT RAISE(ABORT, '{CONSENT}'); END;",
    f"CREATE TRIGGER core_gcc_no_delete BEFORE DELETE ON core_guardiancontactconsent "
    f"BEGIN SELECT RAISE(ABORT, '{CONSENT}'); END;",
    f"CREATE TRIGGER core_nt_no_delete BEFORE DELETE ON core_notificationtemplate "
    f"BEGIN SELECT RAISE(ABORT, '{TEMPLATE_DELETE}'); END;",
    f"CREATE TRIGGER core_nt_fixed BEFORE UPDATE ON core_notificationtemplate "
    f"WHEN {_changed(TEMPLATE_FIXED, 'IS NOT')} OR ({UNAPPROVE}) "
    f"BEGIN SELECT RAISE(ABORT, '{TEMPLATE}'); END;",
    f"CREATE TRIGGER core_n_no_delete BEFORE DELETE ON core_notification "
    f"BEGIN SELECT RAISE(ABORT, '{NOTIFICATION}'); END;",
    f"CREATE TRIGGER core_n_fixed BEFORE UPDATE ON core_notification "
    f"WHEN {_changed(NOTIFICATION_FIXED, 'IS NOT')} "
    f"BEGIN SELECT RAISE(ABORT, '{NOTIFICATION}'); END;",
    f"CREATE TRIGGER core_n_status BEFORE UPDATE ON core_notification "
    f"WHEN NOT ({TRANSITION}) BEGIN SELECT RAISE(ABORT, '{STATUS}'); END;",
]
SQLITE_REVERSE = [
    f"DROP TRIGGER IF EXISTS {name};"
    for name in ("core_gcc_no_update", "core_gcc_no_delete", "core_nt_no_delete",
                 "core_nt_fixed", "core_n_no_delete", "core_n_fixed", "core_n_status")
]


def _raise(message):
    return (
        f"RAISE EXCEPTION USING ERRCODE = 'integrity_constraint_violation', "
        f"MESSAGE = '{message}';"
    )


POSTGRES = [
    f"""
    CREATE OR REPLACE FUNCTION core_gcc_guard() RETURNS trigger AS $$
    BEGIN {_raise(CONSENT)} END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_gcc_guard BEFORE UPDATE OR DELETE ON core_guardiancontactconsent "
    "FOR EACH ROW EXECUTE FUNCTION core_gcc_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_nt_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN {_raise(TEMPLATE_DELETE)} END IF;
        IF {_changed(TEMPLATE_FIXED, 'IS DISTINCT FROM')} OR ({UNAPPROVE}) THEN
            {_raise(TEMPLATE)}
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_nt_guard BEFORE UPDATE OR DELETE ON core_notificationtemplate "
    "FOR EACH ROW EXECUTE FUNCTION core_nt_guard();",
    f"""
    CREATE OR REPLACE FUNCTION core_n_guard() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN {_raise(NOTIFICATION)} END IF;
        IF {_changed(NOTIFICATION_FIXED, 'IS DISTINCT FROM')} THEN {_raise(NOTIFICATION)} END IF;
        IF NOT ({TRANSITION}) THEN {_raise(STATUS)} END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "CREATE TRIGGER core_n_guard BEFORE UPDATE OR DELETE ON core_notification "
    "FOR EACH ROW EXECUTE FUNCTION core_n_guard();",
]
POSTGRES_REVERSE = [
    "DROP TRIGGER IF EXISTS core_gcc_guard ON core_guardiancontactconsent;",
    "DROP FUNCTION IF EXISTS core_gcc_guard();",
    "DROP TRIGGER IF EXISTS core_nt_guard ON core_notificationtemplate;",
    "DROP FUNCTION IF EXISTS core_nt_guard();",
    "DROP TRIGGER IF EXISTS core_n_guard ON core_notification;",
    "DROP FUNCTION IF EXISTS core_n_guard();",
]


def forwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for statement in POSTGRES if pg else SQLITE:
        schema_editor.execute(statement)


def backwards(apps, schema_editor):
    pg = schema_editor.connection.vendor == "postgresql"
    for statement in POSTGRES_REVERSE if pg else SQLITE_REVERSE:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [("core", "0056_phase7_notifications")]

    operations = [migrations.RunPython(forwards, backwards)]
```

PostgreSQL note: `parameters` is `jsonb`; `IS DISTINCT FROM` compares values, so re-saving the same dict is allowed. On SQLite the JSON text is compared; Django serialises the same dict identically.

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: `OK`

- [ ] **Step 5: Verify on PostgreSQL** (PowerShell, DB variables loaded)

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add core/migrations/0057_notification_history_guards.py core/tests/test_phase7_notifications.py
git commit -m "feat(phase7): history guards for consent, templates and notifications"
```

---

### Task 3: Service module `core/notifications.py`

**Files:**
- Create: `core/notifications.py`
- Test: `core/tests/test_phase7_notifications.py`

**Interfaces:**
- Consumes: Task 1 models; `core.imports.normalize_phone(value) -> str | None` ("" for blank, None for unusable, "+<digits>" otherwise).
- Produces:
  - `class NotificationError(Exception)`
  - `current_consent(guardian, channel="WHATSAPP") -> GuardianContactConsent | None`
  - `is_opted_in(guardian, channel="WHATSAPP") -> bool`
  - `record_consent(*, guardian, status, source, note="", user) -> GuardianContactConsent`
  - `school_mode() -> str` (a `School.NotificationMode` value; PORTAL_ONLY when there is no School)
  - `enqueue(*, guardian, student, type, template_key, parameters, subject) -> Notification | None`
  - `render(notification) -> str`
  - `whatsapp_link(notification) -> str | None`
  - `to_send() -> QuerySet[Notification]`
  - `mark_sent(notification, *, user) -> Notification` (status SENT, or SKIPPED_NO_CONSENT if consent was withdrawn)
  - `dismiss(notification, *, user, reason) -> Notification`

- [ ] **Step 1: Write the failing tests**

Add `from core import notifications` to the imports, then append:

```python
class ServiceTests(NotificationFixture, TestCase):
    def enqueue(self, subject="2026-10-12", **overrides):
        values = dict(guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
                      template_key="absence_alert", parameters=self.params(), subject=subject)
        values.update(overrides)
        return notifications.enqueue(**values)

    def test_consent_latest_row_wins(self):
        self.assertFalse(notifications.is_opted_in(self.guardian))
        self.opt_in()
        self.assertTrue(notifications.is_opted_in(self.guardian))
        self.opt_out()
        self.assertFalse(notifications.is_opted_in(self.guardian))

    def test_portal_only_creates_nothing(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.opt_in()
        self.assertIsNone(self.enqueue())
        self.assertFalse(Notification.objects.exists())

    def test_assist_with_consent_prepares(self):
        self.opt_in()
        notification = self.enqueue()
        self.assertEqual(notification.status, Notification.Status.PREPARED)
        self.assertEqual(notification.channel_mode, School.NotificationMode.ASSIST)
        self.assertEqual(
            notification.idempotency_key, f"ABSENCE:{self.guardian.pk}:{self.asha.pk}:2026-10-12"
        )

    def test_without_consent_is_skipped(self):
        self.assertEqual(self.enqueue().status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_same_subject_twice_creates_one(self):
        self.opt_in()
        first = self.enqueue()
        self.assertEqual(self.enqueue(), first)
        self.assertEqual(Notification.objects.count(), 1)

    def test_disallowed_parameter_is_refused(self):
        with self.assertRaises(notifications.NotificationError):
            self.enqueue(parameters={**self.params(), "score": "12"})

    def test_missing_template_is_refused(self):
        with self.assertRaises(notifications.NotificationError):
            self.enqueue(template_key="nope")

    def test_uses_highest_approved_version(self):
        NotificationTemplate.objects.create(
            key="absence_alert", version=3, body=BODY + ".", approved=True
        )
        NotificationTemplate.objects.create(key="absence_alert", version=4, body=BODY + "!")
        self.opt_in()
        self.assertEqual(self.enqueue().template.version, 3)

    def test_render(self):
        self.opt_in()
        self.assertEqual(
            notifications.render(self.enqueue()),
            "Dear parent, Asha was absent on 12 Oct 2026. Details: https://erp.example/p/",
        )

    def test_whatsapp_link_normalises_local_numbers(self):
        self.opt_in()
        notification = self.enqueue()
        for phone in ("98765 43210", "098765-43210", "+91 98765 43210"):
            Guardian.objects.filter(pk=self.guardian.pk).update(phone=phone)
            notification.guardian.refresh_from_db()
            link = notifications.whatsapp_link(notification)
            self.assertTrue(link.startswith("https://wa.me/919876543210?text="), link)

    def test_whatsapp_link_encodes_text(self):
        self.opt_in()
        notification = self.enqueue(parameters={**self.params(), "first_name": "A&B #1?"})
        link = notifications.whatsapp_link(notification)
        self.assertIn("A%26B%20%231%3F", link)
        self.assertNotIn(" ", link)

    def test_whatsapp_link_none_for_unusable_phone(self):
        self.opt_in()
        notification = self.enqueue()
        for phone in ("", "N/A", "12345"):
            Guardian.objects.filter(pk=self.guardian.pk).update(phone=phone)
            notification.guardian.refresh_from_db()
            self.assertIsNone(notifications.whatsapp_link(notification))

    def test_to_send_skips_withdrawn_consent(self):
        self.opt_in()
        notification = self.enqueue()
        self.assertEqual(list(notifications.to_send()), [notification])
        self.opt_out()
        self.assertEqual(list(notifications.to_send()), [])
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_mark_sent(self):
        self.opt_in()
        sent = notifications.mark_sent(self.enqueue(), user=self.admin)
        self.assertEqual(sent.status, Notification.Status.SENT)
        self.assertEqual(sent.marked_sent_by, self.admin)
        self.assertIsNotNone(sent.marked_sent_at)
        with self.assertRaises(notifications.NotificationError):
            notifications.mark_sent(sent, user=self.admin)

    def test_mark_sent_after_opt_out_skips(self):
        self.opt_in()
        notification = self.enqueue()
        self.opt_out()
        result = notifications.mark_sent(notification, user=self.admin)
        self.assertEqual(result.status, Notification.Status.SKIPPED_NO_CONSENT)

    def test_dismiss_needs_reason_and_happens_once(self):
        self.opt_in()
        notification = self.enqueue()
        with self.assertRaises(notifications.NotificationError):
            notifications.dismiss(notification, user=self.admin, reason="  ")
        dismissed = notifications.dismiss(
            notification, user=self.admin, reason="Parent called the school"
        )
        self.assertEqual(dismissed.status, Notification.Status.DISMISSED)
        self.assertEqual(dismissed.dismissed_by, self.admin)
        with self.assertRaises(notifications.NotificationError):
            notifications.dismiss(notification, user=self.admin, reason="again")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: ERROR — `ImportError: cannot import name 'notifications' from 'core'`

- [ ] **Step 3: Implement `core/notifications.py`**

```python
"""Phase 7 notifications: consent, outbox and ASSIST sending (ADR 0015).

Every rule lives here: consent is checked when a message is enqueued, when
the To send page loads and when a message is marked sent; parameters are
limited to NOTIFICATION_PARAMETERS; nothing here makes a network call.
"""

from urllib.parse import quote

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.imports import normalize_phone
from core.models import (
    NOTIFICATION_PARAMETERS,
    GuardianContactConsent,
    Notification,
    NotificationTemplate,
    School,
)

WHATSAPP = GuardianContactConsent.Channel.WHATSAPP
OPTED_IN = GuardianContactConsent.Status.OPTED_IN
PREPARED = Notification.Status.PREPARED
SKIPPED = Notification.Status.SKIPPED_NO_CONSENT


class NotificationError(Exception):
    """An action that cannot be done; the message is safe to show to staff."""


def current_consent(guardian, channel=WHATSAPP):
    return (
        guardian.contact_consents.filter(channel=channel).order_by("-recorded_at", "-pk").first()
    )


def is_opted_in(guardian, channel=WHATSAPP):
    consent = current_consent(guardian, channel)
    return consent is not None and consent.status == OPTED_IN


def record_consent(*, guardian, status, source, note="", user):
    return GuardianContactConsent.objects.create(
        guardian=guardian, channel=WHATSAPP, status=status, source=source,
        note=(note or "").strip()[:200], recorded_by=user,
    )


def school_mode():
    school = School.objects.first()
    return school.notification_channel if school else School.NotificationMode.PORTAL_ONLY


def enqueue(*, guardian, student, type, template_key, parameters, subject):
    """Prepare one message, or return the existing one for the same key.

    Returns None when the school sends nothing (PORTAL_ONLY).
    """
    if set(parameters) - set(NOTIFICATION_PARAMETERS):
        raise NotificationError(
            "Messages may only contain: " + ", ".join(NOTIFICATION_PARAMETERS) + "."
        )
    mode = school_mode()
    if mode == School.NotificationMode.PORTAL_ONLY:
        return None
    if mode != School.NotificationMode.ASSIST:
        raise NotificationError("Only WhatsApp sent by office staff (ASSIST) is available.")
    template = (
        NotificationTemplate.objects.filter(
            key=template_key, channel=WHATSAPP, language="en", approved=True
        )
        .order_by("-version")
        .first()
    )
    if template is None:
        raise NotificationError(f'There is no approved "{template_key}" message text.')
    key = f"{type}:{guardian.pk}:{student.pk if student else '-'}:{subject}"
    existing = Notification.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Notification.objects.create(
                guardian=guardian, student=student, type=type, template=template,
                parameters=dict(parameters), channel_mode=mode,
                status=PREPARED if is_opted_in(guardian) else SKIPPED,
                idempotency_key=key,
            )
    except IntegrityError:
        return Notification.objects.get(idempotency_key=key)


def render(notification):
    values = dict.fromkeys(NOTIFICATION_PARAMETERS, "")
    values.update(notification.parameters)
    return notification.template.body.format_map(values)


def whatsapp_link(notification):
    phone = normalize_phone(notification.guardian.phone)
    if not phone:
        return None
    return f"https://wa.me/{phone.lstrip('+')}?text={quote(render(notification), safe='')}"


def _opted_in_ids(guardian_ids):
    latest = {}
    for guardian_id, status in (
        GuardianContactConsent.objects.filter(guardian_id__in=guardian_ids, channel=WHATSAPP)
        .order_by("guardian_id", "recorded_at", "pk")
        .values_list("guardian_id", "status")
    ):
        latest[guardian_id] = status
    return {guardian_id for guardian_id, status in latest.items() if status == OPTED_IN}


def to_send():
    """PREPARED messages, oldest first, after skipping any without current consent."""
    pending = Notification.objects.filter(status=PREPARED)
    allowed = _opted_in_ids(set(pending.values_list("guardian_id", flat=True)))
    pending.exclude(guardian_id__in=allowed).update(status=SKIPPED, updated_at=timezone.now())
    return (
        Notification.objects.filter(status=PREPARED)
        .select_related("guardian", "student", "template")
        .order_by("created_at", "pk")
    )


def _locked_prepared(notification):
    locked = Notification.objects.select_for_update().get(pk=notification.pk)
    if locked.status != PREPARED:
        raise NotificationError("This message is no longer waiting to be sent.")
    return locked


def mark_sent(notification, *, user):
    with transaction.atomic():
        locked = _locked_prepared(notification)
        if not is_opted_in(locked.guardian):
            locked.status = SKIPPED
            locked.save(update_fields=["status", "updated_at"])
            return locked
        locked.status = Notification.Status.SENT
        locked.marked_sent_by = user
        locked.marked_sent_at = timezone.now()
        locked.save(update_fields=["status", "marked_sent_by", "marked_sent_at", "updated_at"])
        return locked


def dismiss(notification, *, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise NotificationError("Give a reason for not sending this message.")
    with transaction.atomic():
        locked = _locked_prepared(notification)
        locked.status = Notification.Status.DISMISSED
        locked.dismissed_by = user
        locked.dismissed_at = timezone.now()
        locked.dismiss_reason = reason[:200]
        locked.save(update_fields=[
            "status", "dismissed_by", "dismissed_at", "dismiss_reason", "updated_at",
        ])
        return locked
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications --noinput`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/notifications.py core/tests/test_phase7_notifications.py
git commit -m "feat(phase7): notification service with consent, enqueue and ASSIST actions"
```

---

### Task 4: Permissions, consent on the guardian page, channel setting

**Files:**
- Create: `core/migrations/0058_add_notification_permissions_to_group.py`
- Create: `core/notification_views.py` (consent view only in this task)
- Create: `core/templates/core/_guardian_consent.html`
- Modify: `core/forms.py` (`SchoolForm`, new `ContactConsentForm`), `core/views.py` (`guardian_detail`), `core/urls.py`, `core/templates/core/guardian_detail.html`, `core/templates/core/school_detail.html`
- Test: `core/tests/test_phase7_notifications.py`

**Interfaces:**
- Consumes: `notifications.record_consent`.
- Produces: URL name `core:guardian-consent-record` (POST, `guardians/<int:pk>/consent/`); `ContactConsentForm` fields `status`, `source`, `note`; group permissions used by Task 5.

- [ ] **Step 1: Write the failing tests**

Add `from django.urls import reverse` to the imports, then append:

```python
class ConsentPageTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.page = reverse("core:guardian-detail", args=[self.guardian.pk])
        self.record = reverse("core:guardian-consent-record", args=[self.guardian.pk])

    def test_admin_group_has_new_permissions(self):
        for perm in ("core.send_notification", "core.view_notification",
                     "core.add_guardiancontactconsent", "core.view_guardiancontactconsent"):
            self.assertTrue(self.admin.has_perm(perm), perm)
        self.assertFalse(self.rao.has_perm("core.send_notification"))

    def test_card_shows_no_consent_then_current_state(self):
        self.assertContains(self.client.get(self.page), "No consent recorded")
        response = self.client.post(
            self.record, {"status": "OPTED_IN", "source": "PAPER_FORM", "note": "Admission form"},
            follow=True,
        )
        self.assertContains(response, "Opted in")
        self.assertContains(response, "Paper form")
        self.assertTrue(notifications.is_opted_in(self.guardian))

    def test_invalid_consent_post_records_nothing(self):
        self.client.post(self.record, {"status": "MAYBE", "source": "PAPER_FORM"})
        self.assertFalse(GuardianContactConsent.objects.exists())

    def test_teacher_cannot_record_consent(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        response = teacher.post(self.record, {"status": "OPTED_IN", "source": "PAPER_FORM"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GuardianContactConsent.objects.exists())

    def test_school_form_offers_two_modes(self):
        response = self.client.get(reverse("core:school-update"))
        self.assertContains(response, 'value="PORTAL_ONLY"')
        self.assertContains(response, 'value="ASSIST"')
        self.assertNotContains(response, 'value="API"')
        self.assertNotContains(response, 'value="SMS"')

    def test_school_form_rejects_api_mode(self):
        self.client.post(reverse("core:school-update"),
                         {"name": "Greenwood High", "notification_channel": "API"})
        self.school.refresh_from_db()
        self.assertEqual(self.school.notification_channel, School.NotificationMode.ASSIST)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications.ConsentPageTests --noinput`
Expected: ERROR — `NoReverseMatch: Reverse for 'guardian-consent-record' not found`, plus permission and form failures.

- [ ] **Step 3: Permissions migration**

Read `core/migrations/0055_add_import_permissions_to_group.py` to the end. Create `core/migrations/0058_add_notification_permissions_to_group.py` as an exact copy with only these three differences:

```python
# Phase 7 Gate 1 (ADR 0015): administrators record consent and send prepared messages.
```

```python
PERMISSIONS = {
    "core": [
        "send_notification", "view_notification",
        "add_guardiancontactconsent", "view_guardiancontactconsent",
    ]
}
```

```python
    dependencies = [("core", "0057_notification_history_guards")]
```

- [ ] **Step 4: Forms**

In `core/forms.py` replace `SchoolForm` with:

```python
class SchoolForm(forms.ModelForm):
    SELECTABLE_MODES = (School.NotificationMode.PORTAL_ONLY, School.NotificationMode.ASSIST)

    class Meta:
        model = School
        fields = ["name", "notification_channel"]
        widgets = {"notification_channel": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notification_channel"].choices = [
            (value, label) for value, label in School.NotificationMode.choices
            if value in self.SELECTABLE_MODES
        ]
```

and append (add `GuardianContactConsent` to the `core.models` import list):

```python
# --- Phase 7 Gate 1: guardian consent (ADR 0015) ---------------------------


class ContactConsentForm(forms.Form):
    status = forms.ChoiceField(
        choices=GuardianContactConsent.Status.choices, widget=forms.RadioSelect, label="Decision"
    )
    source = forms.ChoiceField(
        choices=GuardianContactConsent.Source.choices, label="How",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    note = forms.CharField(
        max_length=200, required=False, label="Note (optional)",
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )
```

- [ ] **Step 5: View, URL and guardian page**

Create `core/notification_views.py`:

```python
"""Phase 7 Gate 1 views: guardian consent and the ASSIST To send page (ADR 0015)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core import notifications
from core.authorization import administrator_required
from core.forms import ContactConsentForm
from core.models import Guardian


@administrator_required("core.add_guardiancontactconsent")
@require_POST
def guardian_consent_record(request, pk):
    guardian = get_object_or_404(Guardian, pk=pk)
    form = ContactConsentForm(request.POST)
    if form.is_valid():
        consent = notifications.record_consent(
            guardian=guardian, user=request.user, **form.cleaned_data
        )
        messages.success(request, f"WhatsApp consent recorded: {consent.get_status_display()}.")
    else:
        messages.error(request, "Consent was not recorded. Choose a decision and how it was given.")
    return redirect("core:guardian-detail", pk=pk)
```

In `core/urls.py` change the import to `from core import import_views, notification_views, views` and add after the `guardian-detail` route:

```python
    path(
        "guardians/<int:pk>/consent/",
        notification_views.guardian_consent_record,
        name="guardian-consent-record",
    ),
```

In `core/views.py` `guardian_detail`, just before `return render(request, "core/guardian_detail.html", context)` (add `ContactConsentForm` to the `core.forms` import list):

```python
    if request.user.has_perm("core.view_guardiancontactconsent"):
        context["consents"] = list(guardian.contact_consents.select_related("recorded_by"))
        if request.user.has_perm("core.add_guardiancontactconsent"):
            context["consent_form"] = ContactConsentForm()
```

Create `core/templates/core/_guardian_consent.html`:

```django
{# WhatsApp consent card. Expects `guardian`, `consents` (newest first), optional `consent_form`. #}
<h2 class="h5 mt-4">WhatsApp messages</h2>
<div class="card mb-3"><div class="card-body">
    {% with current=consents.0 %}
    {% if current %}
    <p class="mb-2"><span class="erp-pill {% if current.status == 'OPTED_IN' %}is-accepted{% else %}is-rejected{% endif %}">{{ current.get_status_display }}</span>
        on {{ current.recorded_at|date:"j M Y" }} &middot; {{ current.get_source_display }} &middot; by {{ current.recorded_by.get_full_name|default:current.recorded_by.username }}</p>
    {% else %}
    <p class="mb-2">No consent recorded &mdash; messages will not be prepared for this guardian.</p>
    {% endif %}
    {% endwith %}
    {% if consent_form %}
    <form method="post" action="{% url 'core:guardian-consent-record' guardian.pk %}" class="mt-3">
        {% csrf_token %}
        <fieldset class="mb-2"><legend class="form-label fs-6">Decision</legend>
            {% for radio in consent_form.status %}<div class="form-check form-check-inline">{{ radio.tag }}<label class="form-check-label" for="{{ radio.id_for_label }}">{{ radio.choice_label }}</label></div>{% endfor %}
        </fieldset>
        <div class="row g-2">
            <div class="col-sm-4"><label class="form-label" for="{{ consent_form.source.id_for_label }}">How</label>{{ consent_form.source }}</div>
            <div class="col-sm-8"><label class="form-label" for="{{ consent_form.note.id_for_label }}">Note (optional)</label>{{ consent_form.note }}</div>
        </div>
        <button type="submit" class="btn btn-outline-primary btn-sm mt-2">Record</button>
    </form>
    {% endif %}
    {% if consents|length > 1 %}
    <details class="mt-3"><summary>History ({{ consents|length }})</summary>
        <ul class="list-unstyled small mt-2 mb-0">{% for consent in consents %}<li>{{ consent.recorded_at|date:"j M Y H:i" }} &middot; {{ consent.get_status_display }} &middot; {{ consent.get_source_display }}{% if consent.note %} &middot; {{ consent.note }}{% endif %} &middot; {{ consent.recorded_by.username }}</li>{% endfor %}</ul>
    </details>
    {% endif %}
</div></div>
```

In `core/templates/core/guardian_detail.html`, immediately before the final `{% endblock %}`, add:

```django
{% if consents is not None %}{% include "core/_guardian_consent.html" %}{% endif %}
```

In `core/templates/core/school_detail.html`, read the file and add the mode next to the school name in the file's existing markup style, with the visible label "Messages to guardians" and value `{{ school.get_notification_channel_display }}`.

- [ ] **Step 6: Check migrations**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications core.tests.test_views --noinput`
Expected: `OK`. If an existing School-form test fails because the form now requires `notification_channel`, add `"notification_channel": "PORTAL_ONLY"` to that test's POST data (find it with `grep -rn "school-update\|school-create" core/tests`) and record a ruling.

- [ ] **Step 8: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/migrations/0058_add_notification_permissions_to_group.py core/notification_views.py core/forms.py core/views.py core/urls.py core/templates/core/_guardian_consent.html core/templates/core/guardian_detail.html core/templates/core/school_detail.html core/tests/
git commit -m "feat(phase7): record WhatsApp consent on the guardian page; school channel setting"
```

---

### Task 5: ASSIST "To send" page

**Files:**
- Modify: `core/notification_views.py`, `core/urls.py`, `core/navigation.py`
- Create: `core/templates/core/notifications_to_send.html`
- Test: `core/tests/test_phase7_notifications.py`

**Interfaces:**
- Consumes: `notifications.to_send`, `render`, `whatsapp_link`, `mark_sent`, `dismiss`, `school_mode`, `NotificationError`.
- Produces: URL names `core:notifications-to-send` (GET), `core:notification-mark-sent` (POST), `core:notification-dismiss` (POST, field `reason`); nav link "To send" (Daily group, perm `core.send_notification`).

- [ ] **Step 1: Write the failing tests**

Add `from core.navigation import office_nav` to the top import block (sorted), then append:

```python
class ToSendPageTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:notifications-to-send")
        self.opt_in()
        self.message = notifications.enqueue(
            guardian=self.guardian, student=self.asha, type=Notification.Type.ABSENCE,
            template_key="absence_alert", parameters=self.params(), subject="2026-10-12",
        )

    def mark_sent_url(self):
        return reverse("core:notification-mark-sent", args=[self.message.pk])

    def test_lists_prepared_with_send_link(self):
        page = self.client.get(self.url)
        self.assertContains(page, "1 waiting")
        self.assertContains(page, "Ravi Kumar")
        self.assertContains(page, "https://wa.me/919876543210?text=")
        self.assertContains(page, "Asha was absent on 12 Oct 2026")

    def test_mark_sent_and_sent_today(self):
        response = self.client.post(self.mark_sent_url(), follow=True)
        self.assertContains(response, "Marked as sent.")
        self.assertContains(response, "0 waiting")
        self.assertContains(response, "1 sent today")

    def test_mark_sent_twice_is_refused(self):
        self.client.post(self.mark_sent_url())
        response = self.client.post(self.mark_sent_url(), follow=True)
        self.assertContains(response, "no longer waiting to be sent")
        self.assertEqual(Notification.objects.get().marked_sent_by, self.admin)

    def test_dismiss_needs_reason(self):
        url = reverse("core:notification-dismiss", args=[self.message.pk])
        response = self.client.post(url, {"reason": ""}, follow=True)
        self.assertContains(response, "Give a reason")
        self.client.post(url, {"reason": "Parent already informed"})
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, Notification.Status.DISMISSED)

    def test_unusable_phone_shows_fix_link(self):
        Guardian.objects.filter(pk=self.guardian.pk).update(phone="N/A")
        page = self.client.get(self.url)
        self.assertContains(page, "Phone number missing or not usable")
        self.assertContains(page, reverse("core:guardian-detail", args=[self.guardian.pk]))
        self.assertNotContains(page, "https://wa.me/")

    def test_portal_only_notice(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertContains(self.client.get(self.url), "WhatsApp messages are switched off")

    def test_empty_state(self):
        notifications.dismiss(self.message, user=self.admin, reason="test")
        self.assertContains(self.client.get(self.url), "Nothing to send.")

    def test_access(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.assertEqual(teacher.get(self.url).status_code, 403)
        self.assertEqual(teacher.post(self.mark_sent_url()).status_code, 403)
        self.assertEqual(self.client_class().get(self.url).status_code, 302)
        self.assertEqual(self.client.get(self.mark_sent_url()).status_code, 405)

    def test_nav_link_for_admin_only(self):
        self.assertContains(self.client.get(self.url), f'href="{self.url}"')
        labels = [link["label"] for group in office_nav(self.rao, "") for link in group["links"]]
        self.assertNotIn("To send", labels)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications.ToSendPageTests --noinput`
Expected: ERROR — `NoReverseMatch: Reverse for 'notifications-to-send' not found`

- [ ] **Step 3: Views and URLs**

In `core/notification_views.py`, change the imports to:

```python
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import notifications
from core.authorization import administrator_required
from core.forms import ContactConsentForm
from core.models import Guardian, Notification, School
```

and append:

```python
@administrator_required("core.send_notification")
def to_send(request):
    rows = [
        {
            "notification": notification,
            "text": notifications.render(notification),
            "link": notifications.whatsapp_link(notification),
        }
        for notification in notifications.to_send()
    ]
    sent_today = (
        Notification.objects.filter(marked_sent_at__date=timezone.localdate())
        .select_related("guardian", "marked_sent_by")
        .order_by("-marked_sent_at")
    )
    return render(request, "core/notifications_to_send.html", {
        "rows": rows,
        "sent_today": sent_today,
        "portal_only": notifications.school_mode() == School.NotificationMode.PORTAL_ONLY,
    })


@administrator_required("core.send_notification")
@require_POST
def notification_mark_sent(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    try:
        result = notifications.mark_sent(notification, user=request.user)
    except notifications.NotificationError as problem:
        messages.error(request, str(problem))
    else:
        if result.status == Notification.Status.SENT:
            messages.success(request, "Marked as sent.")
        else:
            messages.info(request, "The guardian has opted out; the message was not sent.")
    return redirect("core:notifications-to-send")


@administrator_required("core.send_notification")
@require_POST
def notification_dismiss(request, pk):
    notification = get_object_or_404(Notification, pk=pk)
    try:
        notifications.dismiss(notification, user=request.user, reason=request.POST.get("reason"))
    except notifications.NotificationError as problem:
        messages.error(request, str(problem))
    else:
        messages.info(request, "Message dismissed. It will not be sent.")
    return redirect("core:notifications-to-send")
```

In `core/urls.py`, at the end of `urlpatterns`:

```python
    # Phase 7 Gate 1: notifications (ADR 0015)
    path("notifications/to-send/", notification_views.to_send, name="notifications-to-send"),
    path(
        "notifications/<int:pk>/sent/",
        notification_views.notification_mark_sent,
        name="notification-mark-sent",
    ),
    path(
        "notifications/<int:pk>/dismiss/",
        notification_views.notification_dismiss,
        name="notification-dismiss",
    ),
```

In `core/navigation.py`, in the `"Daily"` group after "Attendance reports":

```python
        NavLink("To send", "core:notifications-to-send", "core.send_notification"),
```

- [ ] **Step 4: Template `core/templates/core/notifications_to_send.html`**

```django
{% extends "base.html" %}
{% block title %}To send{% endblock %}
{% block content %}
<h1 class="h3 mb-1">To send</h1>
<p class="text-muted">{{ rows|length }} waiting &middot; {{ sent_today|length }} sent today</p>

{% if portal_only %}
<div class="alert alert-warning">WhatsApp messages are switched off. New messages are not prepared while the school uses portal only. <a href="{% url 'core:school-detail' %}">School settings</a></div>
{% endif %}

{% for row in rows %}
{% with n=row.notification %}
<div class="card mb-2"><div class="card-body">
    <p class="fw-semibold mb-0">{{ n.guardian.full_name }}</p>
    <p class="text-muted small mb-0">{{ n.get_type_display }}{% if n.parameters.first_name %} &middot; {{ n.parameters.first_name }}{% endif %} &middot; prepared {{ n.created_at|date:"j M, H:i" }}</p>
    <p class="border rounded p-2 my-2 small bg-light">{{ row.text }}</p>
    <div class="d-flex flex-wrap gap-2 align-items-start">
        {% if row.link %}
        <a class="btn btn-success" href="{{ row.link }}" target="_blank" rel="noopener">Send on WhatsApp</a>
        <form method="post" action="{% url 'core:notification-mark-sent' n.pk %}">{% csrf_token %}<button type="submit" class="btn btn-outline-primary">Mark as sent</button></form>
        {% else %}
        <p class="text-danger small mb-0">Phone number missing or not usable &mdash; <a href="{% url 'core:guardian-detail' n.guardian.pk %}">update the guardian</a>.</p>
        {% endif %}
        <form method="post" action="{% url 'core:notification-dismiss' n.pk %}" class="d-flex gap-1">
            {% csrf_token %}
            <label class="visually-hidden" for="reason-{{ n.pk }}">Reason for not sending</label>
            <input class="form-control form-control-sm" id="reason-{{ n.pk }}" name="reason" maxlength="200" placeholder="Reason for not sending" required>
            <button type="submit" class="btn btn-outline-secondary btn-sm">Dismiss</button>
        </form>
    </div>
</div></div>
{% endwith %}
{% empty %}
{% include "partials/_empty.html" with title="Nothing to send." text="Messages appear here when the school prepares them." %}
{% endfor %}

{% if sent_today %}
<h2 class="h5 mt-4">Sent today</h2>
<ul class="list-unstyled small">
    {% for n in sent_today %}<li>{{ n.marked_sent_at|date:"H:i" }} &middot; {{ n.guardian.full_name }} &middot; {{ n.get_type_display }}{% if n.parameters.first_name %} ({{ n.parameters.first_name }}){% endif %} &middot; by {{ n.marked_sent_by.username }}</li>{% endfor %}
</ul>
{% endif %}
{% endblock %}
```

The `required` attribute stops an empty dismiss in the browser; the server check still applies (tests post an empty reason directly).

- [ ] **Step 5: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_notifications core.tests.test_ui_foundation --noinput`
Expected: `OK`. If `test_ui_foundation` asserts an exact list of "Daily" links, update that assertion to include "To send" and record a ruling.

- [ ] **Step 6: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/notification_views.py core/urls.py core/navigation.py core/templates/core/notifications_to_send.html core/tests/
git commit -m "feat(phase7): ASSIST To send page with send link, mark sent and dismiss"
```

---

### Task 6: ADR amendment, docs, full verification

**Files:**
- Modify: `docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md`, `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`

- [ ] **Step 1: ADR amendment**

Append to ADR 0015, before `## Related`:

```markdown
## Amendment (Gate 1, 2026-10-15)

- Status `DISMISSED` added: a staff member may decide not to send a PREPARED message, with a required reason, recorded with who and when.
- Consent is re-checked when the To send page loads and when a message is marked sent; a PREPARED message whose guardian has opted out becomes `SKIPPED_NO_CONSENT`.
- Gate 1 offers only PORTAL_ONLY (default) and ASSIST in the school settings; API and SMS wait for Gate 4B.
```

- [ ] **Step 2: Plan notes**

In `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md`, after the "Implementation notes (Gates 8-9, bulk import)" section, add a section `## Implementation notes (Gate 1, notifications foundation)` with these bullets:

```markdown
- Consent is recorded by administrators on the guardian page (source: paper form, in person, phone call, other). Append-only; the latest record is current; no record means no messages.
- School setting "Messages to guardians": Portal only (default) or WhatsApp sent by office staff (ASSIST).
- Outbox idempotency key: `type:guardian:student:subject`. Parameters are limited to first_name, date and portal_url, enforced in code and in template validation.
- To send page: WhatsApp link with the text pre-filled, Mark as sent, Dismiss with a reason; unusable phone numbers show a link to fix the guardian record.
- No producers yet: absence alerts (Gate 2), announcements (Gate 3) and result-published notices (Gate 4) create the messages.
```

- [ ] **Step 3: Full suite on PostgreSQL, lint, migrations**

Run (PowerShell, DB variables loaded): `.\.venv\Scripts\python.exe -m ruff check .`, `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, `.\.venv\Scripts\python.exe manage.py test --noinput` (with `--parallel 4` if PR #48 is merged).
Expected: ruff clean; `No changes detected`; all tests pass except the known pre-existing date-dependent failure.

- [ ] **Step 4: Manual check**

Throwaway database (scratch settings module pointing at a scratch SQLite file, `migrate`, seed with `Phase4Fixture` plus a guardian and an approved `absence_alert` template), dev server, as `admin`: set School to ASSIST, record consent on the guardian, enqueue one message from `manage.py shell` with `notifications.enqueue(...)`, open To send at 360 px and 1280 px, check the WhatsApp link URL, Mark as sent, check Sent today; enqueue another and Dismiss it with a reason; set the guardian's phone to "N/A" and see the fix-phone warning.

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0015-phase-7-notifications-consent-and-delivery-modes.md docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md
git commit -m "docs(phase7): Gate 1 notes and ADR 0015 amendment"
```
