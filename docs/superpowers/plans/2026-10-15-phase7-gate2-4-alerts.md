# Phase 7 Gates 2 and 4 — Absence Alerts and Report-Card Notices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare WhatsApp absence alerts when a register is submitted (or corrected to Absent the same day) and "report card available" notices when Term results are published, in the Gate 1 outbox, for guardians with portal access.

**Architecture:** One new module `core/notification_producers.py` holds every Gate 2/4 rule (recipients, parameters, same-day rule, auto-dismissal) and calls Gate 1's `core.notifications.enqueue()` / `dismiss()`. It is called from three existing places inside their transactions: `AttendanceRegister.submit()`, `AttendanceEntry.record_status_change()` and `publication.confirm_publication()`. A producer never raises into its caller: a message that cannot be prepared is logged and skipped.

**Tech Stack:** Django 5.2, PostgreSQL (SQLite for quick runs), Django TestCase.

**Spec:** `docs/superpowers/specs/2026-10-15-phase7-gate2-4-alerts-design.md`

## Global Constraints

- Recipients: only guardians with an active `GuardianStudentAccess` grant for the student, not review-pending, whose guardian has an active `GuardianAccount` (revoked_at is null) with `user.is_active`. Linked guardians without that get no row at all.
- Consent is Gate 1's: `enqueue()` already makes PREPARED (opted in) or SKIPPED_NO_CONSENT.
- Messages carry only `first_name`, `date`, `portal_url` (Gate 1 enforces). Never marks, grades, remarks or absence notes.
- Absence alerts only when the register date equals `core.models.business_today()` (call it through the module, `core_models.business_today()`, so tests that patch `core.models.business_today` control it).
- Idempotency subject: absence → `register.date.isoformat()`; report card → `f"term-{term.pk}"`.
- Auto-dismiss reason, exactly: `Attendance corrected to Present`.
- Template keys and bodies, exactly:
  - `absence-alert`: `Dear parent, {first_name} was marked absent at school on {date}. Attendance details: {portal_url}`
  - `report-card-published`: `Dear parent, {first_name}'s report card is now available on the school portal: {portal_url}`
- Date parameter format: `f"{d.day} {d:%b %Y}"` → `12 Oct 2026`, `5 Oct 2026`.
- `PORTAL_BASE_URL` setting from env `PORTAL_BASE_URL`, stripped, trailing `/` removed, default `""`.
- School form error, exactly: `Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages.`
- Producers never raise into the caller; `NotificationError` is logged at WARNING on logger `core.notification_producers` with type and ids only (no names, phones or text).
- No model field changes; one data migration (0059) only.
- Quick test runs use SQLite: `env -u DB_NAME .venv/Scripts/python.exe manage.py test <label> --noinput`. Never run two Postgres suites at once.

## Review Focus

1. A DRAFT register being saved (not submitted) must prepare nothing — pinned in Task 2 (`test_draft_register_prepares_nothing`).
2. Student names with extra spaces or a single word must give a clean first name — pinned in Task 2 (`test_first_name_is_first_word`).
3. A guardian with two absent children the same day gets one message per child, each with its own link — pinned in Task 2 (`test_two_children_two_messages`).
4. Publishing a student with no portal guardians must succeed and prepare nothing — pinned in Task 4 (`test_student_without_portal_guardian_publishes_quietly`).
5. A waiting alert must be dismissed even if the school switched to Portal only after it was prepared — pinned in Task 3 (`test_dismissal_works_in_portal_only_mode`).

---

### Task 1: Portal address setting, seeded message texts, school form check, To send warning

**Files:**
- Modify: `config/settings.py` (after `SOURCE_HASH_KEY`, ~line 148)
- Create: `core/migrations/0059_seed_alert_templates.py`
- Modify: `core/forms.py:35-48` (`SchoolForm`)
- Modify: `core/notification_views.py:30-48` (`to_send`)
- Modify: `core/templates/core/notifications_to_send.html:7-9`
- Test: `core/tests/test_phase7_alerts.py` (create)

**Interfaces:**
- Produces: `settings.PORTAL_BASE_URL: str`; approved templates `absence-alert` v1 and `report-card-published` v1 (channel WHATSAPP, language en); `SchoolForm` rejects ASSIST when `PORTAL_BASE_URL` is empty; context flag `portal_address_missing` on the To send page.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_phase7_alerts.py`:

```python
"""Phase 7 Gates 2 and 4: absence alerts and report-card notices (ADR 0015)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from core.forms import SchoolForm
from core.models import NotificationTemplate, School
from core.tests.test_phase7_notifications import NotificationFixture

BASE = "https://erp.example"
ABSENCE_BODY = (
    "Dear parent, {first_name} was marked absent at school on {date}. "
    "Attendance details: {portal_url}"
)
NOTICE_BODY = (
    "Dear parent, {first_name}'s report card is now available on the school portal: "
    "{portal_url}"
)
ADDRESS_ERROR = "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."


class SeededTemplateTests(TestCase):
    def test_both_texts_are_seeded_approved_and_valid(self):
        for key, body in (("absence-alert", ABSENCE_BODY),
                          ("report-card-published", NOTICE_BODY)):
            with self.subTest(key=key):
                template = NotificationTemplate.objects.get(
                    key=key, channel="WHATSAPP", language="en", version=1)
                self.assertTrue(template.approved)
                self.assertEqual(template.body, body)
                template.full_clean()


class SchoolFormAddressTests(TestCase):
    def form(self, mode):
        return SchoolForm(data={"name": "Greenwood High", "notification_channel": mode})

    @override_settings(PORTAL_BASE_URL="")
    def test_assist_refused_without_portal_address(self):
        form = self.form("ASSIST")
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["notification_channel"], [ADDRESS_ERROR])

    @override_settings(PORTAL_BASE_URL="")
    def test_portal_only_allowed_without_portal_address(self):
        self.assertTrue(self.form("PORTAL_ONLY").is_valid())

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_assist_allowed_with_portal_address(self):
        self.assertTrue(self.form("ASSIST").is_valid())


class ToSendWarningTests(NotificationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="admin", password="pass-12345")
        self.url = reverse("core:notifications-to-send")

    @override_settings(PORTAL_BASE_URL="")
    def test_warning_when_assist_without_portal_address(self):
        page = self.client.get(self.url)
        self.assertTrue(page.context["portal_address_missing"])
        self.assertContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL=BASE)
    def test_no_warning_with_portal_address(self):
        page = self.client.get(self.url)
        self.assertFalse(page.context["portal_address_missing"])
        self.assertNotContains(page, "PORTAL_BASE_URL")

    @override_settings(PORTAL_BASE_URL="")
    def test_no_address_warning_in_portal_only(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertFalse(self.client.get(self.url).context["portal_address_missing"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts --noinput`
Expected: FAIL/ERROR — `NotificationTemplate.DoesNotExist`, the form tests fail (ASSIST accepted), `KeyError: 'portal_address_missing'`.

- [ ] **Step 3: Implement**

`config/settings.py`, after the `SOURCE_HASH_KEY` line:

```python

# Phase 7: full web address of this site (e.g. https://erp.school.in), used in
# links inside WhatsApp messages. Required before the school can choose ASSIST.
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "").strip().rstrip("/")
```

`core/migrations/0059_seed_alert_templates.py`:

```python
# Phase 7 Gates 2 and 4 (ADR 0015): the first approved message texts.
# Template rows cannot be deleted (history guards), so reversing is a no-op.

from django.db import migrations

TEXTS = {
    "absence-alert": (
        "Dear parent, {first_name} was marked absent at school on {date}. "
        "Attendance details: {portal_url}"
    ),
    "report-card-published": (
        "Dear parent, {first_name}'s report card is now available on the school portal: "
        "{portal_url}"
    ),
}


def seed(apps, schema_editor):
    NotificationTemplate = apps.get_model("core", "NotificationTemplate")
    alias = schema_editor.connection.alias
    for key, body in TEXTS.items():
        NotificationTemplate.objects.using(alias).get_or_create(
            key=key, channel="WHATSAPP", language="en", version=1,
            defaults={"body": body, "approved": True},
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0058_add_notification_permissions_to_group")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
```

`core/forms.py` — add `from django.conf import settings` to the imports (if not already there) and this method to `SchoolForm`:

```python
    def clean_notification_channel(self):
        mode = self.cleaned_data["notification_channel"]
        if mode == School.NotificationMode.ASSIST and not settings.PORTAL_BASE_URL:
            raise forms.ValidationError(
                "Set the portal address (PORTAL_BASE_URL) before sending WhatsApp messages."
            )
        return mode
```

`core/notification_views.py` — add `from django.conf import settings` and change the render call in `to_send`:

```python
    mode = notifications.school_mode()
    return render(request, "core/notifications_to_send.html", {
        "rows": rows,
        "sent_today": sent_today,
        "portal_only": mode == School.NotificationMode.PORTAL_ONLY,
        "portal_address_missing": (
            mode == School.NotificationMode.ASSIST and not settings.PORTAL_BASE_URL
        ),
    })
```

`core/templates/core/notifications_to_send.html` — after the `{% if portal_only %}…{% endif %}` block:

```html
{% if portal_address_missing %}
<div class="alert alert-warning">The portal address (PORTAL_BASE_URL) is not set, so new WhatsApp messages are not being prepared. Ask whoever runs the server to set it.</div>
{% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts core.tests.test_phase7_notifications --noinput`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add config/settings.py core/migrations/0059_seed_alert_templates.py core/forms.py core/notification_views.py core/templates/core/notifications_to_send.html core/tests/test_phase7_alerts.py
git commit -m "feat(phase7): portal address setting and seeded alert texts"
```

---

### Task 2: Producer module and absence alerts on register submission

**Files:**
- Create: `core/notification_producers.py`
- Modify: `core/models.py` — `AttendanceRegister.submit()` (~line 1120-1165)
- Test: `core/tests/test_phase7_alerts.py` (append)

**Interfaces:**
- Consumes: Task 1 templates and `settings.PORTAL_BASE_URL`; Gate 1 `core.notifications.enqueue(*, guardian, student, type, template_key, parameters, subject)`, `notifications.school_mode()`, `notifications.NotificationError`; `core.guardian_access.pending_map(grants)` → `{grant.pk: (is_pending, placement)}`; `core.models._as_date(value)`.
- Produces (used by Tasks 3 and 4):
  - `portal_grants(student) -> list[GuardianStudentAccess]`
  - `portal_url(url_name: str, grant) -> str` (raises `NotificationError` when `PORTAL_BASE_URL` is empty)
  - `first_name(student) -> str`
  - `absence_alerts_for_register(register) -> None`
  - private `_assist() -> bool`, `_prepare(*, kind, template_key, grant, student, subject, url_name, extra=None) -> None`, `_absence_alert(student, on_date) -> None`
  - constants `ABSENCE_TEMPLATE = "absence-alert"`, `REPORT_CARD_TEMPLATE = "report-card-published"`, `CORRECTED_REASON = "Attendance corrected to Present"`

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_phase7_alerts.py` (merge these imports into the top of the file):

```python
from datetime import date
from unittest import mock

from core import guardian_accounts as ga
from core import notification_producers, notifications
from core.models import (
    Applicant,
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianContactConsent,
    Notification,
    Student,
    StudentGuardian,
)
from core.tests.test_phase6_access_boundary import TODAY
from core.tests.test_phase6_publication import PublicationFixture

ABSENCE = Notification.Type.ABSENCE
NOTICE = Notification.Type.RESULT_PUBLISHED
PREPARED = Notification.Status.PREPARED


class AlertFixture(PublicationFixture):
    """Phase 6 publication fixture (Meena → Asha granted, Other → Bina granted,
    Meena → Ravi linked without access; today pinned to 2026-10-12 through
    `self.today`) plus an ASSIST school, consent for both portal guardians and
    a portal address."""

    def setUp(self):
        super().setUp()
        address = override_settings(PORTAL_BASE_URL=BASE)
        address.enable()
        self.addCleanup(address.disable)
        self.school = School.objects.create(
            name="Greenwood High", notification_channel=School.NotificationMode.ASSIST)
        self.consent(self.meena)
        self.consent(self.other)

    def consent(self, guardian, status=GuardianContactConsent.Status.OPTED_IN):
        GuardianContactConsent.objects.create(
            guardian=guardian, status=status,
            source=GuardianContactConsent.Source.PAPER_FORM, recorded_by=self.admin)

    def register(self, on_date=TODAY, *, asha=AttendanceStatus.ABSENT,
                 bina=AttendanceStatus.PRESENT, note="", submit=True):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=asha, absence_note=note)
        register.save_draft_entry(enrollment=self.bina_e, status=bina)
        if submit:
            register.submit(actor=self.admin)
        return register

    def messages(self, kind=ABSENCE):
        return list(Notification.objects.filter(type=kind).order_by("pk"))

    def attendance_link(self, grant):
        return BASE + reverse("portal:attendance", args=[grant.public_id])


class AbsenceAlertTests(AlertFixture, TestCase):
    def test_absent_student_gets_one_prepared_alert_per_portal_guardian(self):
        self.register()
        [alert] = self.messages()
        self.assertEqual((alert.guardian, alert.student, alert.status),
                         (self.meena, self.asha, PREPARED))
        self.assertEqual(alert.parameters, {
            "first_name": "Asha", "date": "12 Oct 2026",
            "portal_url": self.attendance_link(self.asha_grant),
        })
        self.assertEqual(alert.idempotency_key,
                         f"ABSENCE:{self.meena.pk}:{self.asha.pk}:2026-10-12")

    def test_text_is_exactly_the_approved_wording_without_the_note(self):
        self.register(note="Fever, called in")
        text = notifications.render(self.messages()[0])
        self.assertEqual(text, "Dear parent, Asha was marked absent at school on 12 Oct 2026. "
                               "Attendance details: " + self.attendance_link(self.asha_grant))
        self.assertNotIn("Fever", text)

    def test_present_students_get_nothing(self):
        self.register(asha=AttendanceStatus.PRESENT)
        self.assertEqual(self.messages(), [])

    def test_draft_register_prepares_nothing(self):
        self.register(submit=False)
        self.assertEqual(self.messages(), [])

    def test_guardian_without_consent_is_recorded_as_skipped(self):
        self.consent(self.meena, GuardianContactConsent.Status.OPTED_OUT)
        self.register()
        self.assertEqual([m.status for m in self.messages()],
                         [Notification.Status.SKIPPED_NO_CONSENT])

    def test_linked_guardian_without_portal_access_gets_nothing(self):
        father = Guardian.objects.create(full_name="Father Rao")
        StudentGuardian.objects.create(student=self.asha, guardian=father,
                                       relationship_type="FATHER")
        self.consent(father)
        self.register()
        self.assertEqual([m.guardian for m in self.messages()], [self.meena])

    def test_revoked_access_gets_nothing(self):
        ga.revoke_student_access(grant=self.asha_grant, actor=self.admin, reason="Court order")
        self.register()
        self.assertEqual(self.messages(), [])

    def test_inactive_login_gets_nothing(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.register()
        self.assertEqual(self.messages(), [])

    def test_pending_access_review_is_not_a_recipient(self):
        unplaced = Student.objects.create(
            applicant=Applicant.objects.create(full_name="Unplaced"), full_name="Unplaced")
        grant = ga.grant_student_access(student_guardian=self.relate(unplaced, self.meena),
                                        actor=self.admin)
        self.assertNotIn(grant, notification_producers.portal_grants(unplaced))
        self.assertEqual(notification_producers.portal_grants(self.asha), [self.asha_grant])

    def test_two_children_two_messages(self):
        bina_grant_for_meena = ga.grant_student_access(
            student_guardian=self.relate(self.bina, self.meena), actor=self.admin)
        self.register(bina=AttendanceStatus.ABSENT)
        mine = {m.student: m.parameters["portal_url"]
                for m in self.messages() if m.guardian == self.meena}
        self.assertEqual(mine, {
            self.asha: self.attendance_link(self.asha_grant),
            self.bina: self.attendance_link(bina_grant_for_meena),
        })

    def test_earlier_date_prepares_nothing(self):
        self.register(date(2026, 10, 9))
        self.assertEqual(self.messages(), [])

    def test_portal_only_prepares_nothing(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.register()
        self.assertEqual(self.messages(), [])

    def test_missing_portal_address_is_logged_and_submit_succeeds(self):
        with override_settings(PORTAL_BASE_URL=""), \
                self.assertLogs("core.notification_producers", "WARNING") as logs:
            register = self.register()
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.messages(), [])
        self.assertNotIn("Asha", "\n".join(logs.output))

    def test_missing_template_is_logged_and_submit_succeeds(self):
        with mock.patch.object(notification_producers, "ABSENCE_TEMPLATE", "no-such-text"), \
                self.assertLogs("core.notification_producers", "WARNING"):
            register = self.register()
        register.refresh_from_db()
        self.assertEqual(register.status, AttendanceRegister.Status.SUBMITTED)
        self.assertEqual(self.messages(), [])

    def test_running_the_producer_twice_creates_nothing_new(self):
        register = self.register()
        notification_producers.absence_alerts_for_register(register)
        self.assertEqual(len(self.messages()), 1)

    def test_first_name_is_first_word(self):
        for full_name, expected in (("Asha Rao", "Asha"), ("  Ravi   Kumar ", "Ravi"),
                                    ("Lakshmi", "Lakshmi"), ("", "")):
            with self.subTest(full_name=full_name):
                self.assertEqual(
                    notification_producers.first_name(Student(full_name=full_name)), expected)
```

Note: `self.relate`, `self.user`, `self.asha_e`, `self.bina_e`, `self.asha_grant`, `self.bina_grant`, `self.meena`, `self.other`, `self.admin`, `self.today` and `self.publish()` come from `BoundaryFixture` / `PublicationFixture` (`core/tests/test_phase6_access_boundary.py`, `core/tests/test_phase6_publication.py`). `BoundaryFixture` patches `core.models.business_today` to return `self.today`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts --noinput`
Expected: ERROR — `ImportError: cannot import name 'notification_producers'`.

- [ ] **Step 3: Implement**

Create `core/notification_producers.py`:

```python
"""Phase 7 Gates 2 and 4: absence alerts and report-card notices (ADR 0015).

Spec: docs/superpowers/specs/2026-10-15-phase7-gate2-4-alerts-design.md.
Recipients are guardians who can open the portal for the student right now.
Producers never block the action that triggers them: a message that cannot
be prepared is logged (ids only) and skipped.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.urls import reverse

from core import guardian_access, notifications
from core import models as core_models
from core.models import (
    AttendanceStatus,
    GuardianAccount,
    GuardianStudentAccess,
    Notification,
    School,
)

logger = logging.getLogger(__name__)

ABSENCE_TEMPLATE = "absence-alert"
REPORT_CARD_TEMPLATE = "report-card-published"
CORRECTED_REASON = "Attendance corrected to Present"


def _assist():
    return notifications.school_mode() == School.NotificationMode.ASSIST


def portal_grants(student):
    """Active, non-pending grants whose guardian has an active portal login."""
    active_login = GuardianAccount.objects.filter(
        guardian=OuterRef("student_guardian__guardian"),
        revoked_at__isnull=True, user__is_active=True,
    )
    grants = list(
        GuardianStudentAccess.objects.filter(
            student_guardian__student=student, revoked_at__isnull=True
        )
        .filter(Exists(active_login))
        .select_related("student_guardian__guardian", "student_guardian__student")
        .order_by("pk")
    )
    pending = guardian_access.pending_map(grants)
    return [grant for grant in grants if not pending[grant.pk][0]]


def portal_url(url_name, grant):
    if not settings.PORTAL_BASE_URL:
        raise notifications.NotificationError("The portal address is not set.")
    return settings.PORTAL_BASE_URL + reverse(url_name, args=[grant.public_id])


def first_name(student):
    words = (student.full_name or "").split()
    return words[0] if words else ""


def _display_date(on_date):
    return f"{on_date.day} {on_date:%b %Y}"


def _prepare(*, kind, template_key, grant, student, subject, url_name, extra=None):
    guardian = grant.student_guardian.guardian
    try:
        parameters = {"first_name": first_name(student),
                      "portal_url": portal_url(url_name, grant), **(extra or {})}
        with transaction.atomic():
            notifications.enqueue(
                guardian=guardian, student=student, type=kind, template_key=template_key,
                parameters=parameters, subject=subject,
            )
    except notifications.NotificationError as problem:
        logger.warning("%s message not prepared (student %s, guardian %s): %s",
                       kind, student.pk, guardian.pk, problem)


def _absence_alert(student, on_date):
    for grant in portal_grants(student):
        _prepare(kind=Notification.Type.ABSENCE, template_key=ABSENCE_TEMPLATE, grant=grant,
                 student=student, subject=on_date.isoformat(), url_name="portal:attendance",
                 extra={"date": _display_date(on_date)})


def absence_alerts_for_register(register):
    """Called inside AttendanceRegister.submit(): one alert per absent student."""
    on_date = core_models._as_date(register.date)
    if not _assist() or on_date != core_models.business_today():
        return
    entries = register.entries.filter(status=AttendanceStatus.ABSENT).select_related(
        "academic_enrollment__student"
    )
    for entry in entries:
        _absence_alert(entry.academic_enrollment.student, on_date)
```

`core/models.py`, in `AttendanceRegister.submit()`, directly after the final `self.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])` and still inside the `with transaction.atomic():` block:

```python
            from core import notification_producers

            notification_producers.absence_alerts_for_register(self)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts core.tests.test_phase6_portal_attendance core.tests.test_models --noinput`
Expected: all pass except the known pre-existing date-dependent `core.tests.test_models.AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates`.

- [ ] **Step 5: Commit**

```bash
git add core/notification_producers.py core/models.py core/tests/test_phase7_alerts.py
git commit -m "feat(phase7): absence alerts when a register is submitted"
```

---

### Task 3: Corrections — auto-dismiss on Present, alert on same-day Absent

**Files:**
- Modify: `core/notification_producers.py` (append)
- Modify: `core/models.py` — `AttendanceEntry.record_status_change()` (~line 1325-1348)
- Test: `core/tests/test_phase7_alerts.py` (append)

**Interfaces:**
- Consumes: Task 2 `_assist()`, `_absence_alert(student, on_date)`, `CORRECTED_REASON`; Gate 1 `notifications.dismiss(notification, *, user, reason)` (only from PREPARED; raises `NotificationError` otherwise), `notifications.mark_sent(notification, *, user)`.
- Produces: `absence_corrected(entry, *, actor) -> None`.

- [ ] **Step 1: Write the failing tests**

Append:

```python
class CorrectionTests(AlertFixture, TestCase):
    def entry(self, register):
        return register.entries.get(academic_enrollment=self.asha_e)

    def correct(self, register, status):
        self.entry(register).record_status_change(status, actor=self.admin,
                                                  reason="Register was wrong")

    def test_correction_to_present_dismisses_waiting_alert(self):
        register = self.register()
        self.correct(register, AttendanceStatus.PRESENT)
        [alert] = self.messages()
        self.assertEqual(alert.status, Notification.Status.DISMISSED)
        self.assertEqual(alert.dismissed_by, self.admin)
        self.assertEqual(alert.dismiss_reason, "Attendance corrected to Present")

    def test_sent_alert_is_not_retracted(self):
        register = self.register()
        notifications.mark_sent(self.messages()[0], user=self.admin)
        self.correct(register, AttendanceStatus.PRESENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.SENT])

    def test_dismissal_works_in_portal_only_mode(self):
        register = self.register()
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.correct(register, AttendanceStatus.PRESENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.DISMISSED])

    def test_correction_to_absent_same_day_prepares_alert(self):
        register = self.register(asha=AttendanceStatus.PRESENT)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual([(m.student, m.status) for m in self.messages()],
                         [(self.asha, PREPARED)])

    def test_correction_to_absent_on_a_later_day_prepares_nothing(self):
        register = self.register(asha=AttendanceStatus.PRESENT)
        self.today = date(2026, 10, 13)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual(self.messages(), [])

    def test_back_and_forth_does_not_reprepare_a_dismissed_alert(self):
        register = self.register()
        self.correct(register, AttendanceStatus.PRESENT)
        self.correct(register, AttendanceStatus.ABSENT)
        self.assertEqual([m.status for m in self.messages()], [Notification.Status.DISMISSED])

    def test_correcting_another_student_leaves_this_alert_alone(self):
        register = self.register(bina=AttendanceStatus.ABSENT)
        register.entries.get(academic_enrollment=self.bina_e).record_status_change(
            AttendanceStatus.PRESENT, actor=self.admin, reason="Register was wrong")
        statuses = {m.student: m.status for m in self.messages()}
        self.assertEqual(statuses[self.asha], PREPARED)
        self.assertEqual(statuses[self.bina], Notification.Status.DISMISSED)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts.CorrectionTests --noinput`
Expected: FAIL — alerts stay PREPARED; same-day Absent correction prepares nothing.

- [ ] **Step 3: Implement**

Append to `core/notification_producers.py`:

```python
def absence_corrected(entry, *, actor):
    """Called inside AttendanceEntry.record_status_change() after the new status is saved.

    To Present: waiting absence alerts for that student and date are dismissed
    (sent ones are never retracted). To Absent: an alert, same day only.
    """
    register = entry.register
    student = entry.academic_enrollment.student
    on_date = core_models._as_date(register.date)
    if entry.status == AttendanceStatus.PRESENT:
        waiting = Notification.objects.filter(
            type=Notification.Type.ABSENCE, student=student,
            status=Notification.Status.PREPARED,
            idempotency_key__endswith=f":{student.pk}:{on_date.isoformat()}",
        )
        for notification in waiting:
            try:
                notifications.dismiss(notification, user=actor, reason=CORRECTED_REASON)
            except notifications.NotificationError:
                pass  # sent or dismissed meanwhile; nothing to retract
    elif _assist() and on_date == core_models.business_today():
        _absence_alert(student, on_date)
```

`core/models.py`, in `AttendanceEntry.record_status_change()`, directly after `self.save(update_fields=["status", "absence_note", "updated_at"])`, inside the `with transaction.atomic():` block:

```python
            from core import notification_producers

            notification_producers.absence_corrected(self, actor=actor)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts core.tests.test_phase6_portal_attendance --noinput`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/notification_producers.py core/models.py core/tests/test_phase7_alerts.py
git commit -m "feat(phase7): attendance corrections dismiss or prepare absence alerts"
```

---

### Task 4: Report-card notices on publication

**Files:**
- Modify: `core/notification_producers.py` (append)
- Modify: `core/publication.py` — `confirm_publication()` (~line 194-219) and imports
- Test: `core/tests/test_phase7_alerts.py` (append)

**Interfaces:**
- Consumes: Task 2 `portal_grants`, `_prepare`, `_assist`, `REPORT_CARD_TEMPLATE`; Phase 6 `publication.confirm_publication(...) -> list[TermPublication]`, `publication.withdraw(publication, *, actor, reason)`.
- Produces: `report_card_notices(publications) -> None`.

- [ ] **Step 1: Write the failing tests**

Append (add `from core import publication` to the imports):

```python
class ReportCardNoticeTests(AlertFixture, TestCase):
    def report_cards_link(self, grant):
        return BASE + reverse("portal:report-cards", args=[grant.public_id])

    def test_publish_prepares_one_notice_per_portal_guardian(self):
        self.publish()
        notices = {m.student: m for m in self.messages(NOTICE)}
        self.assertEqual(set(notices), {self.asha, self.bina})
        asha = notices[self.asha]
        self.assertEqual((asha.guardian, asha.status), (self.meena, PREPARED))
        self.assertEqual(asha.parameters, {
            "first_name": "Asha", "portal_url": self.report_cards_link(self.asha_grant)})
        self.assertEqual(asha.idempotency_key,
                         f"RESULT_PUBLISHED:{self.meena.pk}:{self.asha.pk}:term-{self.term1.pk}")

    def test_text_has_no_results_or_remarks(self):
        self.publish()
        asha = next(m for m in self.messages(NOTICE) if m.student == self.asha)
        text = notifications.render(asha)
        self.assertEqual(text, "Dear parent, Asha's report card is now available on the school "
                               "portal: " + self.report_cards_link(self.asha_grant))
        for hidden in ("15", "UT1", "Steady"):
            self.assertNotIn(hidden, text)

    def test_republish_after_withdraw_sends_nothing_new(self):
        created = self.publish()
        asha_publication = next(p for p in created if p.student == self.asha)
        publication.withdraw(asha_publication, actor=self.admin, reason="Wrong remark")
        self.publish()
        self.assertEqual(len(self.messages(NOTICE)), 2)

    def test_student_without_portal_guardian_publishes_quietly(self):
        ga.revoke_student_access(grant=self.bina_grant, actor=self.admin, reason="Left school")
        created = self.publish()
        self.assertEqual({p.student for p in created}, {self.asha, self.bina})
        self.assertEqual([m.student for m in self.messages(NOTICE)], [self.asha])

    def test_portal_only_publishes_without_notices(self):
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertEqual(len(self.publish()), 2)
        self.assertEqual(self.messages(NOTICE), [])

    def test_missing_template_does_not_block_publication(self):
        with mock.patch.object(notification_producers, "REPORT_CARD_TEMPLATE", "no-such-text"), \
                self.assertLogs("core.notification_producers", "WARNING"):
            created = self.publish()
        self.assertEqual(len(created), 2)
        self.assertEqual(self.messages(NOTICE), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts.ReportCardNoticeTests --noinput`
Expected: FAIL — no RESULT_PUBLISHED notifications.

- [ ] **Step 3: Implement**

Append to `core/notification_producers.py`:

```python
def report_card_notices(publications):
    """Called inside confirm_publication(): one notice per student, once per Term."""
    if not _assist():
        return
    for publication in publications:
        student = publication.student
        for grant in portal_grants(student):
            _prepare(kind=Notification.Type.RESULT_PUBLISHED,
                     template_key=REPORT_CARD_TEMPLATE, grant=grant, student=student,
                     subject=f"term-{publication.term_id}", url_name="portal:report-cards")
```

`core/publication.py`: add `from core import notification_producers` to the imports. In `confirm_publication()`, replace

```python
        for row in plan["selected"]:
            created.append(_publish(term, row, actor, now))
        return created
```

with

```python
        for row in plan["selected"]:
            created.append(_publish(term, row, actor, now))
        notification_producers.report_card_notices(created)
        return created
```

If the top-level import causes a circular import at startup, move it inside `confirm_publication()` and note it in the report.

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_alerts core.tests.test_phase6_publication --noinput`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/notification_producers.py core/publication.py core/tests/test_phase7_alerts.py
git commit -m "feat(phase7): report-card notices when Term results are published"
```

---

### Task 5: Documentation and full verification

**Files:**
- Modify: `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (new section after the Gate 1 implementation notes)

**Interfaces:** none.

- [ ] **Step 1: Add the implementation notes**

Insert after the "Implementation notes (Gate 1, notifications foundation)" bullet list:

```markdown
## Implementation notes (Gates 2 and 4, absence alerts and report-card notices)

- Recipients: guardians with portal access to the student (active grant, not under access review, active portal login). Other linked guardians get nothing. Gate 1 consent applies on top.
- Absence alert: prepared when a register is submitted, for ABSENT entries, only if the register date is today. A correction to Present dismisses a waiting alert ("Attendance corrected to Present"); a sent alert is never retracted. A correction to Absent prepares an alert on the same day only.
- Report card notice: prepared when Term results are published; once per student and Term, so republishing never sends again.
- Links point at the guardian's own portal page and need `PORTAL_BASE_URL` (env); the school cannot choose WhatsApp sending without it.
- A message that cannot be prepared is logged and skipped; it never blocks submitting a register or publishing results.
- Message texts (`absence-alert`, `report-card-published`, version 1, English) are seeded by migration 0059.
```

- [ ] **Step 2: Lint and full suite on PostgreSQL**

Run (PowerShell, Postgres env loaded):

```powershell
foreach ($k in 'DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT') { Set-Item "env:$k" ([Environment]::GetEnvironmentVariable($k,'User')) }
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test --parallel 4 --noinput
```

Expected: ruff clean; "No changes detected"; all tests pass except the known date-dependent `test_missing_report_skips_sections_without_students_and_future_dates`.

- [ ] **Step 3: Commit**

```bash
git add docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md
git commit -m "docs(phase7): Gates 2 and 4 implementation notes"
```
