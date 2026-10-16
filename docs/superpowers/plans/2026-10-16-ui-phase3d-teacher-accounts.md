# UI Phase 3D: Teacher Accounts Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Office staff create and manage teacher logins inside the product (audit F09): a Teachers list, Add teacher with a one-time temporary password, reset password, change username, deactivate/reactivate.

**Architecture:** A new service module `core/teacher_accounts.py` (patterned on `core/guardian_accounts.py`) holds every atomic, audited workflow. A new `core/teacher_views.py` (patterned on `core/announcement_views.py`) holds the views, using the Phase 3A data table for the list. One new permission `accounts.manage_teacher_accounts` gates everything; five new `SecurityEvent` types audit it. A teacher is, as today, a login in the `Teachers` group; access to classes and subjects still comes from the existing assignment pages.

**Tech Stack:** Django, `accounts.User` (custom user), Bootstrap 5.3, Phase 3A `core/tables.py`, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-10-16-ui-phase3d-teacher-accounts-design.md`

## Global Constraints

- Branch `ui/audit-phase3d-teacher-accounts` (from `main`). Do not push or open a PR until asked.
- Run tests with `.venv\Scripts\python.exe manage.py test <labels> --parallel 4`. One date-dependent attendance test already fails on `main`; ignore only that one.
- Migrations: exactly two, both schema/permission only — `accounts/migrations/0007_teacher_accounts_permission_events.py` and `core/migrations/0068_teacher_account_permission_group.py`. No data is rewritten. `makemigrations --check` must be clean afterwards.
- A temporary password is shown exactly once on the credential slip response (`Cache-Control: no-store, no-cache, must-revalidate, private`, `add_never_cache_headers`). It is never put in `messages`, the session, logs, a redirect URL, or `SecurityEvent.detail`.
- Every action works only on logins that are in the `Teachers` group and are not superusers (`TEACHERS_GROUP_NAME` in `core.models`); any other target is a 404 in views and a `ValidationError` in the service.
- Permission string everywhere: `accounts.manage_teacher_accounts`. Views use `@administrator_required("accounts.manage_teacher_accounts")` (see `core/authorization.py`); navigation stays display-only.
- Usernames: `accounts.usernames.clean_new_username` (normalize, validate, unique). Temporary passwords: `core.guardian_accounts.generate_temporary_password`.
- Use real CSS tokens only (`--erp-ink`, `--erp-ink-soft`, `--erp-rule`, `--erp-accent`, `--erp-surface`, `--erp-space-1..7`, `--erp-text-xs/sm/base`); shared partials `partials/_page_header.html`, `_form_field.html`, `_form_required_legend.html`, `_status_badge.html`, `_table_head.html`, `_table_footer.html`.
- GateGuard hooks block the first Bash command, first Edit of a file and first Write of a new file: state the requested facts in text, then retry the same call.

## Review Focus

1. An administrator (non-Teachers) user's pk on every teacher detail/action URL → 404 and nothing changes; a superuser who is also in the Teachers group → 404 too (Tasks 2-4).
2. An administrator who is also a teacher cannot deactivate their own login (Task 2, Task 4).
3. The temporary password never appears in `SecurityEvent.detail`, messages, the session, or any response other than the slip (Tasks 2-4).
4. A deactivated teacher cannot sign in and an already-open session ends; reactivation restores sign-in without changing the password (Tasks 2 and 5).
5. A newly created teacher is forced to change the temporary password before reaching `/my/`, sees no sections until assigned, and sees the section after an assignment (Task 5).

## File Structure

| File | Responsibility |
|---|---|
| `accounts/models.py` | `manage_teacher_accounts` permission; five `SecurityEvent.EventType` values |
| `accounts/migrations/0007_teacher_accounts_permission_events.py` (new) | Auto-generated schema state for the above |
| `core/migrations/0068_teacher_account_permission_group.py` (new) | Grants the permission to `School Administrators` |
| `core/teacher_accounts.py` (new) | `teacher_queryset`, `create_teacher`, `reset_teacher_password`, `change_teacher_username`, `deactivate_teacher`, `reactivate_teacher` |
| `core/forms.py` | `TeacherCreateForm`, `TeacherUsernameForm`, `TeacherDeactivateForm` |
| `core/teacher_views.py` (new) | List, create, detail, reset, username, deactivate, reactivate |
| `core/urls.py` | Seven routes under `teachers/` |
| `core/navigation.py`, `core/breadcrumbs.py` | Sidebar link; breadcrumb rules |
| `core/templates/core/teacher_*.html` (new) | list, form, credential slip, detail, username form, three confirm pages |
| `core/templates/core/teacher_assignments.html`, `academic_year_list.html` | Replace the "site administration" sentence; rename the confusing "Teachers" link |
| `core/tests/test_teacher_accounts.py` (new) | Permission/event and service tests; `core/tests/test_ui_admin_phase3d.py` (new) view and end-to-end tests |

---

### Task 1: Permission, event types, migrations

**Files:**
- Modify: `accounts/models.py` (`User.Meta`, `SecurityEvent.EventType`)
- Create: `accounts/migrations/0007_teacher_accounts_permission_events.py` (generated), `core/migrations/0068_teacher_account_permission_group.py`
- Test: `core/tests/test_teacher_accounts.py` (create)

**Interfaces:**
- Produces: permission `accounts.manage_teacher_accounts`; `SecurityEvent.EventType.TEACHER_ACCOUNT_CREATED`, `TEACHER_PASSWORD_RESET`, `TEACHER_USERNAME_CHANGED`, `TEACHER_DEACTIVATED`, `TEACHER_REACTIVATED` (all classified HISTORY by `class_for`, i.e. not in `ROUTINE_TYPES`).

- [ ] **Step 1: Write the failing tests** (`core/tests/test_teacher_accounts.py`)

```python
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
```

- [ ] **Step 2: Run, expect FAIL** — `.venv\Scripts\python.exe manage.py test core.tests.test_teacher_accounts --parallel 4` (AttributeError on the event types; permission missing).

- [ ] **Step 3: Implement**

`accounts/models.py`:
- In `class Meta(AbstractUser.Meta)` of `User` add
  ```python
  permissions = [
      ("manage_teacher_accounts", "Can create and manage teacher logins"),
  ]
  ```
- In `SecurityEvent.EventType` add (after `DOCUMENT_DOWNLOADED`):
  ```python
  TEACHER_ACCOUNT_CREATED = "TEACHER_ACCOUNT_CREATED", "Teacher account created"
  TEACHER_PASSWORD_RESET = "TEACHER_PASSWORD_RESET", "Teacher password reset"
  TEACHER_USERNAME_CHANGED = "TEACHER_USERNAME_CHANGED", "Teacher username changed"
  TEACHER_DEACTIVATED = "TEACHER_DEACTIVATED", "Teacher login deactivated"
  TEACHER_REACTIVATED = "TEACHER_REACTIVATED", "Teacher login reactivated"
  ```
  Do NOT add them to `ROUTINE_TYPES`.

Generate the accounts migration: `.venv\Scripts\python.exe manage.py makemigrations accounts -n teacher_accounts_permission_events`. Expected content: `AlterModelOptions` for `user` and `AlterField` for `securityevent.event_type`. Open it and confirm it contains nothing else (no table changes); the database triggers from `0003_securityevent_guards` are unaffected by a choices-only change.

`core/migrations/0068_teacher_account_permission_group.py` (same pattern as `core/migrations/0007_add_applicant_guardian_permissions_to_group.py`, but for the `accounts` app):

```python
from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "School Administrators"
CODENAME = "manage_teacher_accounts"


def add_permission_to_group(apps, schema_editor):
    config = apps.get_app_config("accounts")
    config.models_module = True
    create_permissions(config, verbosity=0, using=schema_editor.connection.alias, apps=apps)
    config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.using(schema_editor.connection.alias).get_or_create(name=GROUP_NAME)
    permission = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="accounts", codename=CODENAME
    )
    group.permissions.add(*permission)


def remove_permission_from_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.using(schema_editor.connection.alias).filter(name=GROUP_NAME).first()
    if group is None:
        return
    permission = Permission.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label="accounts", codename=CODENAME
    )
    group.permissions.remove(*permission)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0067_phase0_decision_reasons"),
        ("accounts", "0007_teacher_accounts_permission_events"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_permission_to_group, remove_permission_from_group),
    ]
```

- [ ] **Step 4: Run Task 1 tests, expect PASS.** Then `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → "No changes detected", and run `core.tests.test_authorization core.tests.test_phase6_security` to confirm nothing about the security-event guards or permissions regressed.

- [ ] **Step 5: Commit**

```bash
git add accounts/models.py accounts/migrations/0007_teacher_accounts_permission_events.py core/migrations/0068_teacher_account_permission_group.py core/tests/test_teacher_accounts.py
git commit -m "feat(accounts): add teacher account permission and audit events (F09)"
```

---

### Task 2: Teacher account service

**Files:**
- Create: `core/teacher_accounts.py`
- Test: `core/tests/test_teacher_accounts.py` (append)

**Interfaces:**
- Consumes: Task 1 permission/event types; `clean_new_username`, `generate_temporary_password`, `SecurityEvent.record`, `User.end_all_sessions`.
- Produces (all keyword-only):
  - `teacher_queryset() -> QuerySet[User]` — Teachers-group, non-superuser logins (active and inactive), annotated `assignment_count` (subject assignments + class-teacher assignments).
  - `create_teacher(*, username, first_name, last_name, email, actor) -> (user, temporary_password)`
  - `reset_teacher_password(*, user, actor) -> temporary_password`
  - `change_teacher_username(*, user, new_username, actor) -> str`
  - `deactivate_teacher(*, user, reason, actor)`; `reactivate_teacher(*, user, actor)`
  - All raise `django.core.exceptions.ValidationError` on refusal.

- [ ] **Step 1: Write the failing tests** (append; hoist the imports to the top of the file)

```python
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError

from core import teacher_accounts
from core.models import TEACHERS_GROUP_NAME

User = get_user_model()


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
```

- [ ] **Step 2: Run, expect FAIL** (`ImportError: cannot import name 'teacher_accounts'`).

- [ ] **Step 3: Implement `core/teacher_accounts.py`**

```python
"""Phase 3D: teacher login workflows (audit F09).

A teacher is an active login in the Teachers group; classes and subjects come
from the existing assignment pages. Every workflow is atomic and audited with
a SecurityEvent, and works only on Teachers-group logins that are not
superusers. Temporary passwords are returned once to the caller for display
on a slip and are never stored in plain text, logged or put in an audit
detail.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count

from accounts.models import SecurityEvent
from accounts.usernames import clean_new_username
from core.guardian_accounts import generate_temporary_password
from core.models import TEACHERS_GROUP_NAME

Event = SecurityEvent.EventType
NOT_A_TEACHER = "That login is not a teacher account."


def teacher_queryset():
    """Teachers-group logins (active and inactive), never superusers."""
    return (
        get_user_model()
        .objects.filter(groups__name=TEACHERS_GROUP_NAME, is_superuser=False)
        .annotate(
            assignment_count=Count("assessment_assignments", distinct=True)
            + Count("class_teacher_assignments", distinct=True)
        )
    )


def _lock_teacher(user):
    """The row-locked Teachers-group login, or ValidationError. Use inside atomic()."""
    locked = get_user_model().objects.select_for_update().filter(pk=user.pk).first()
    if (
        locked is None
        or locked.is_superuser
        or not locked.groups.filter(name=TEACHERS_GROUP_NAME).exists()
    ):
        raise ValidationError(NOT_A_TEACHER)
    return locked


def create_teacher(*, username, first_name, last_name, email, actor):
    """Create a Teachers-group login. Returns (user, temporary password)."""
    username = clean_new_username(username)
    password = generate_temporary_password()
    try:
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=username,
                password=password,
                first_name=(first_name or "").strip(),
                last_name=(last_name or "").strip(),
                email=(email or "").strip(),
            )
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])
            group, _ = Group.objects.get_or_create(name=TEACHERS_GROUP_NAME)
            user.groups.add(group)
            SecurityEvent.record(Event.TEACHER_ACCOUNT_CREATED, actor=actor, subject_user=user)
    except IntegrityError as error:
        raise ValidationError("That username is not available.") from error
    return user, password


def reset_teacher_password(*, user, actor):
    """New temporary password, forced change, every session ended. Returns the password."""
    password = generate_temporary_password()
    with transaction.atomic():
        locked = _lock_teacher(user)
        locked.set_password(password)
        locked.must_change_password = True
        locked.save(update_fields=["password", "must_change_password"])
        locked.end_all_sessions()
        SecurityEvent.record(Event.TEACHER_PASSWORD_RESET, actor=actor, subject_user=locked)
    return password


def change_teacher_username(*, user, new_username, actor):
    """Mirror core.guardian_accounts.change_guardian_username for a teacher."""
    with transaction.atomic():
        locked = _lock_teacher(user)
        username = clean_new_username(new_username, exclude_user=locked)
        locked.username = username
        try:
            locked.save(update_fields=["username"])
        except IntegrityError as error:
            raise ValidationError("That username is not available.") from error
        SecurityEvent.record(Event.TEACHER_USERNAME_CHANGED, actor=actor, subject_user=locked)
    return username


def deactivate_teacher(*, user, reason, actor):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    with transaction.atomic():
        locked = _lock_teacher(user)
        if getattr(actor, "pk", None) == locked.pk:
            raise ValidationError("You cannot deactivate your own login.")
        if not locked.is_active:
            raise ValidationError("This teacher is already inactive.")
        locked.is_active = False
        locked.save(update_fields=["is_active"])
        locked.end_all_sessions()
        SecurityEvent.record(
            Event.TEACHER_DEACTIVATED, actor=actor, subject_user=locked,
            detail={"reason": reason[:200]},
        )
    return locked


def reactivate_teacher(*, user, actor):
    with transaction.atomic():
        locked = _lock_teacher(user)
        if locked.is_active:
            raise ValidationError("This teacher is already active.")
        locked.is_active = True
        locked.save(update_fields=["is_active"])
        SecurityEvent.record(Event.TEACHER_REACTIVATED, actor=actor, subject_user=locked)
    return locked
```

Before finalising, read `change_guardian_username` in `core/guardian_accounts.py` (~line 140) and mirror exactly how it validates (`exclude_user`) and whether it ends sessions; follow it. Confirm `clean_new_username` raises `ValidationError` for taken names and that the project's auth backend (`accounts/backends.py`) refuses inactive users so `authenticate` returns `None`.

- [ ] **Step 4: Run Task 2 tests, expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add core/teacher_accounts.py core/tests/test_teacher_accounts.py
git commit -m "feat(accounts): add audited teacher account workflows (F09)"
```

---

### Task 3: Teachers list, Add teacher, credential slip, sidebar

**Files:**
- Create: `core/teacher_views.py`, `core/templates/core/teacher_list.html`, `teacher_form.html`, `teacher_credential_slip.html`
- Modify: `core/forms.py`, `core/urls.py`, `core/navigation.py`, `core/breadcrumbs.py`
- Test: `core/tests/test_ui_admin_phase3d.py` (create)

**Interfaces:**
- Consumes: Task 2 service; Phase 3A `Column`, `build_table`, `parse_choice`; `administrator_required`.
- Produces: URL names `core:teacher-list` (`teachers/`), `core:teacher-create` (`teachers/new/`); `_teacher_slip(request, user, password, *, heading)` helper and `get_teacher_or_404(pk)` in `core/teacher_views.py`; sidebar link "Teachers" (School setup group); `TeacherCreateForm`.

- [ ] **Step 1: Write the failing tests** (`core/tests/test_ui_admin_phase3d.py`)

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.models import SecurityEvent
from core import teacher_accounts
from core.models import TEACHERS_GROUP_NAME
from core.tests.test_authorization import AuthorizationClientsMixin

User = get_user_model()


def add_teacher(actor, username, first="Asha", last="Rao"):
    return teacher_accounts.create_teacher(
        username=username, first_name=first, last_name=last, email="", actor=actor
    )


class TeacherListTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:teacher-list")

    def test_permissions(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(self.url), f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.administrator.get(self.url).status_code, 200)

    def test_lists_only_teachers_with_table_semantics(self):
        add_teacher(self.admin_user, "asha.rao")
        response = self.administrator.get(self.url)
        self.assertContains(response, "asha.rao")
        usernames = [t.username for t in response.context["teachers"]]
        self.assertEqual(usernames, ["asha.rao"])
        self.assertContains(response, "<caption")
        self.assertContains(response, 'scope="col"')
        self.assertContains(response, "Add teacher")

    def test_sidebar_has_teachers_link_for_administrators(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, f'href="{self.url}"')

    def test_search_status_filter_sort_and_pagination(self):
        for index in range(30):
            add_teacher(self.admin_user, f"teacher{index:02d}", first=f"T{index:02d}", last="X")
        inactive, _ = add_teacher(self.admin_user, "gone.teacher", first="Zed", last="Gone")
        teacher_accounts.deactivate_teacher(user=inactive, reason="Left", actor=self.admin_user)
        page1 = self.administrator.get(self.url)
        self.assertEqual(len(page1.context["teachers"]), 25)
        self.assertContains(page1, "Showing 1–25 of 31")
        found = self.administrator.get(self.url, {"q": "gone"})
        self.assertEqual([t.username for t in found.context["teachers"]], ["gone.teacher"])
        only_inactive = self.administrator.get(self.url, {"status": "inactive"})
        self.assertEqual(
            [t.username for t in only_inactive.context["teachers"]], ["gone.teacher"]
        )
        self.assertEqual(self.administrator.get(self.url, {"status": "bogus"}).status_code, 200)
        self.assertEqual(
            self.administrator.get(self.url, {"sort": "nope", "page": "x"}).status_code, 200
        )


class TeacherCreateTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:teacher-create")
        self.data = {
            "first_name": "Asha", "last_name": "Rao",
            "username": "asha.rao", "email": "asha@example.com",
        }

    def test_permissions(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
        self.assertEqual(self.non_admin.post(self.url, self.data).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(self.url), f"{reverse('login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertFalse(User.objects.filter(username="asha.rao").exists())

    def test_form_renders(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "Add teacher")
        self.assertContains(response, 'name="username"')

    def test_post_creates_teacher_and_shows_slip_once_with_no_store(self):
        response = self.administrator.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="asha.rao")
        self.assertTrue(user.groups.filter(name=TEACHERS_GROUP_NAME).exists())
        self.assertContains(response, "Temporary password")
        self.assertContains(response, "asha.rao")
        self.assertIn("no-store", response["Cache-Control"])
        shown = response.context["password"]
        self.assertNotIn(shown, str(list(response.context["messages"])))
        self.assertNotIn(shown, str(dict(self.administrator.session)))
        event = SecurityEvent.objects.get(
            event_type=SecurityEvent.EventType.TEACHER_ACCOUNT_CREATED, subject_user=user
        )
        self.assertNotIn(shown, str(event.detail))
        self.assertNotContains(self.administrator.get(reverse("core:teacher-list")), shown)

    def test_duplicate_and_invalid_username_show_errors_not_500(self):
        add_teacher(self.admin_user, "asha.rao")
        for username in ("asha.rao", "x", "has space"):
            with self.subTest(username=username):
                response = self.administrator.post(self.url, {**self.data, "username": username})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "errorlist")
        self.assertEqual(User.objects.filter(username__iexact="asha.rao").count(), 1)

    def test_first_and_last_name_are_required(self):
        response = self.administrator.post(self.url, {**self.data, "first_name": ""})
        self.assertContains(response, "errorlist")
        self.assertFalse(User.objects.filter(username="asha.rao").exists())
```

- [ ] **Step 2: Run, expect FAIL** (`NoReverseMatch: 'teacher-list'`).

- [ ] **Step 3: Implement**

`core/forms.py` (use the existing imports; `USERNAME_HELP` is already imported there):

```python
class TeacherCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=30, help_text=USERNAME_HELP)
    email = forms.EmailField(required=False)
```

`core/teacher_views.py`:

```python
"""Phase 3D office views: teacher logins (audit F09). Administrators only."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import add_never_cache_headers

from core import teacher_accounts
from core.authorization import administrator_required
from core.forms import TeacherCreateForm
from core.tables import Column, build_table, parse_choice

PERMISSION = "accounts.manage_teacher_accounts"
STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]

TEACHER_COLUMNS = (
    Column("Name", "name", ("first_name", "last_name", "username")),
    Column("Username", "username", ("username",)),
    Column("Email"),
    Column("Status", "status", ("is_active", "username"), ("-is_active", "username")),
    Column("Assignments", "assignments", ("assignment_count", "username")),
    Column("Last sign-in", "last_login", ("last_login", "username")),
)


def _teacher_slip(request, user, password, *, heading):
    """Render the one-time temporary password; never cached, never stored."""
    response = render(
        request,
        "core/teacher_credential_slip.html",
        {"teacher": user, "password": password, "heading": heading},
    )
    add_never_cache_headers(response)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response


def get_teacher_or_404(pk):
    return get_object_or_404(teacher_accounts.teacher_queryset(), pk=pk)


@administrator_required(PERMISSION)
def teacher_list(request):
    query = request.GET.get("q", "").strip()
    status = parse_choice(request, "status", STATUS_CHOICES)
    teachers = teacher_accounts.teacher_queryset()
    if query:
        teachers = teachers.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
        )
    if status:
        teachers = teachers.filter(is_active=(status == "active"))
    table = build_table(request, teachers, TEACHER_COLUMNS, "name")
    return render(
        request,
        "core/teacher_list.html",
        {
            "teachers": table.page,
            "table": table,
            "query": query,
            "status": status,
            "status_choices": STATUS_CHOICES,
        },
    )


@administrator_required(PERMISSION)
def teacher_create(request):
    form = TeacherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user, password = teacher_accounts.create_teacher(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error("username", error)
        else:
            return _teacher_slip(request, user, password, heading="Teacher account created")
    return render(request, "core/teacher_form.html", {"form": form})
```

`core/urls.py`: import `teacher_views` in the `from core import ...` line and add, before the `teachers/<int:pk>/load/` route:

```python
    path("teachers/", teacher_views.teacher_list, name="teacher-list"),
    path("teachers/new/", teacher_views.teacher_create, name="teacher-create"),
```

`core/navigation.py` `OFFICE_NAV`, in "School setup" after Subjects:

```python
        NavLink("Teachers", "core:teacher-list", "accounts.manage_teacher_accounts"),
```

`core/breadcrumbs.py`: add

```python
_TEACHERS = Crumb("Teachers", "core:teacher-list")
```
and rule `"teacher-create": Rule("teacher-list", (_TEACHERS,), "New teacher"),`.

Templates (extend `base.html`; follow the style of `core/templates/core/student_list.html` after Phase 3A and `core/templates/core/guardian_account_form.html`):

`teacher_list.html`: `_page_header.html` (eyebrow "School setup", title "Teachers", purpose "Create and manage teacher logins. Classes and subjects are assigned from Academic Years.", primary action Add teacher → `teacher-create`); a search + status form (`<label for="teacher-search" class="form-label">Search teachers</label>`, `input type="search" name="q"`, status `<select name="status">` with a visually hidden label, Search button, and a Clear filters link when `query or status`); the table in `<div class="erp-table-scroll" role="region" aria-label="Teachers" tabindex="0">` with `_table_head.html caption="Teachers"` and rows `{% for teacher in table.page %}`: name as plain text for now (**Task 4 adds the `teacher-detail` route and turns it into a link, with a test**), username, email or "-", `_status_badge.html` (label Active/Inactive, tone `active`/`inactive`), `teacher.assignment_count`, `teacher.last_login|date:"j M Y, H:i"|default:"Never"`; an `{% empty %}` row "No teachers yet." with `colspan="6"`; `_table_footer.html`.

`teacher_form.html`: header "Add teacher"; `_form_required_legend.html`; `<form method="post">` rendering first_name, last_name, username, email through `partials/_form_field.html`; submit "Create teacher login"; Cancel → `teacher-list`; a sentence "A temporary password is shown once. The teacher must choose a new password at first sign-in."

`teacher_credential_slip.html`: copy of `guardian_credential_slip.html` with "School ERP — Teacher login", `Teacher: {{ teacher.get_full_name|default:teacher.username }}`, username, temporary password, the same print button, Done → `teacher-list` (Task 4 changes Done to `teacher-detail`).

- [ ] **Step 4: Run Task 3 tests** and the shell/navigation suites: `core.tests.test_ui_admin_phase3d core.tests.test_ui_foundation core.tests.test_ui_admin_phase2 core.tests.test_authorization`. Fix only assertions that encode the exact sidebar link list for administrators (the "School setup" group gains Teachers); do not weaken authorization assertions.

- [ ] **Step 5: Commit**

```bash
git add core/forms.py core/teacher_views.py core/urls.py core/navigation.py core/breadcrumbs.py core/templates/core/teacher_list.html core/templates/core/teacher_form.html core/templates/core/teacher_credential_slip.html core/tests
git commit -m "feat(ui): add Teachers list and Add teacher with one-time password slip (F09)"
```

---

### Task 4: Teacher detail and manage actions

**Files:**
- Modify: `core/teacher_views.py`, `core/forms.py`, `core/urls.py`, `core/breadcrumbs.py`, `core/templates/core/teacher_list.html`, `teacher_credential_slip.html`, `teacher_assignments.html`, `academic_year_list.html`
- Create: `core/templates/core/teacher_detail.html`, `teacher_username_form.html`, `teacher_reset_confirm.html`, `teacher_deactivate_confirm.html`, `teacher_reactivate_confirm.html`
- Test: `core/tests/test_ui_admin_phase3d.py` (append)

**Interfaces:**
- Consumes: Task 2 service, Task 3 `_teacher_slip`, `get_teacher_or_404`.
- Produces: URL names `core:teacher-detail` (`teachers/<int:pk>/`), `core:teacher-reset-password`, `core:teacher-username`, `core:teacher-deactivate`, `core:teacher-reactivate` (all under `teachers/<int:pk>/`); forms `TeacherUsernameForm`, `TeacherDeactivateForm`.

- [ ] **Step 1: Write the failing tests** (append)

```python
from datetime import date

from core.models import AcademicYear


class TeacherManageTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher, self.password = add_teacher(self.admin_user, "asha.rao")

    def url(self, name):
        return reverse(f"core:{name}", args=[self.teacher.pk])

    def test_detail_shows_profile_workload_link_events_and_actions(self):
        response = self.administrator.get(self.url("teacher-detail"))
        self.assertContains(response, "asha.rao")
        self.assertContains(response, reverse("core:teacher-load", args=[self.teacher.pk]))
        self.assertContains(response, "Teacher account created")
        for name in ("teacher-reset-password", "teacher-username", "teacher-deactivate"):
            self.assertContains(response, self.url(name))

    def test_list_names_link_to_detail(self):
        response = self.administrator.get(reverse("core:teacher-list"))
        self.assertContains(response, f'href="{self.url("teacher-detail")}"')

    def test_every_page_refuses_non_admin_and_anonymous(self):
        for name in ("teacher-detail", "teacher-reset-password", "teacher-username",
                     "teacher-deactivate", "teacher-reactivate"):
            with self.subTest(name=name):
                self.assertEqual(self.non_admin.get(self.url(name)).status_code, 403)
                self.assertEqual(self.non_admin.post(self.url(name)).status_code, 403)
                self.assertEqual(self.anonymous.get(self.url(name)).status_code, 302)

    def test_non_teacher_and_superuser_targets_are_404_everywhere(self):
        root = User.objects.create_superuser(username="root2", password="pass-12345")
        root.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        for target in (self.admin_user, root):
            for name in ("teacher-detail", "teacher-reset-password", "teacher-username",
                         "teacher-deactivate", "teacher-reactivate"):
                with self.subTest(target=target.username, name=name):
                    url = reverse(f"core:{name}", args=[target.pk])
                    self.assertEqual(self.administrator.get(url).status_code, 404)
                    self.assertEqual(
                        self.administrator.post(url, {"reason": "x", "username": "zz.zz"})
                        .status_code, 404)
        self.assertTrue(User.objects.get(pk=self.admin_user.pk).is_active)

    def test_reset_get_confirms_and_post_shows_slip(self):
        confirm = self.administrator.get(self.url("teacher-reset-password"))
        self.assertContains(confirm, "Reset password")
        self.assertEqual(User.objects.get(pk=self.teacher.pk).session_version, 0)
        response = self.administrator.post(self.url("teacher-reset-password"))
        self.assertContains(response, "Temporary password")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotEqual(response.context["password"], self.password)
        self.assertEqual(User.objects.get(pk=self.teacher.pk).session_version, 1)

    def test_username_change(self):
        self.assertContains(self.administrator.get(self.url("teacher-username")), "New username")
        bad = self.administrator.post(self.url("teacher-username"), {"username": "x"})
        self.assertContains(bad, "errorlist")
        done = self.administrator.post(self.url("teacher-username"), {"username": "asha.r"})
        self.assertRedirects(done, self.url("teacher-detail"))
        self.assertEqual(User.objects.get(pk=self.teacher.pk).username, "asha.r")

    def test_deactivate_needs_reason_then_reactivate(self):
        page = self.administrator.get(self.url("teacher-deactivate"))
        self.assertContains(page, "assignment")  # states how many assignments remain on record
        missing = self.administrator.post(self.url("teacher-deactivate"), {"reason": ""})
        self.assertContains(missing, "errorlist")
        self.assertTrue(User.objects.get(pk=self.teacher.pk).is_active)
        done = self.administrator.post(self.url("teacher-deactivate"), {"reason": "Left"})
        self.assertRedirects(done, self.url("teacher-detail"))
        self.assertFalse(User.objects.get(pk=self.teacher.pk).is_active)
        self.assertContains(self.administrator.get(self.url("teacher-detail")), "Inactive")
        back = self.administrator.post(self.url("teacher-reactivate"))
        self.assertRedirects(back, self.url("teacher-detail"))
        self.assertTrue(User.objects.get(pk=self.teacher.pk).is_active)

    def test_administrator_who_is_also_a_teacher_cannot_deactivate_self(self):
        self.admin_user.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))
        url = reverse("core:teacher-deactivate", args=[self.admin_user.pk])
        response = self.administrator.post(url, {"reason": "Oops"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot deactivate your own login")
        self.assertTrue(User.objects.get(pk=self.admin_user.pk).is_active)

    def test_breadcrumbs_link_back_to_the_teacher_and_the_list(self):
        response = self.administrator.get(self.url("teacher-deactivate"))
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, f'href="{reverse("core:teacher-list")}"')
        self.assertContains(response, f'href="{self.url("teacher-detail")}"')

    def test_assignments_page_links_to_teachers_page(self):
        year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31)
        )
        response = self.administrator.get(
            reverse("core:academic-year-teacher-assignments", args=[year.pk])
        )
        self.assertContains(response, reverse("core:teacher-list"))
        self.assertNotContains(response, "site administration")
```

(Check `AcademicYear`'s required fields against `core/tests/test_phase5_assignment_workflows.py`; use whatever fields that file's fixture uses.)

- [ ] **Step 2: Run, expect FAIL** (`NoReverseMatch: 'teacher-detail'`).

- [ ] **Step 3: Implement**

`core/forms.py`:

```python
class TeacherUsernameForm(forms.Form):
    username = forms.CharField(max_length=30, label="New username", help_text=USERNAME_HELP)


class TeacherDeactivateForm(forms.Form):
    reason = forms.CharField(max_length=200, help_text="Recorded permanently with the deactivation.")
```

`core/teacher_views.py` (add imports `TeacherUsernameForm`, `TeacherDeactivateForm`, `SecurityEvent` from `accounts.models`):

```python
@administrator_required(PERMISSION)
def teacher_detail(request, pk):
    teacher = get_teacher_or_404(pk)
    return render(request, "core/teacher_detail.html", {
        "teacher": teacher,
        "subject_assignments": teacher.assessment_assignments.select_related(
            "offering__academic_year", "offering__class_grade", "offering__subject", "section"
        ),
        "class_assignments": teacher.class_teacher_assignments.select_related(
            "academic_year", "section__class_grade"
        ),
        "events": SecurityEvent.objects.filter(subject_user=teacher)[:10],
    })


@administrator_required(PERMISSION)
def teacher_reset_password(request, pk):
    teacher = get_teacher_or_404(pk)
    if request.method == "POST":
        try:
            password = teacher_accounts.reset_teacher_password(user=teacher, actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("core:teacher-detail", pk=teacher.pk)
        return _teacher_slip(request, teacher, password, heading="Password reset")
    return render(request, "core/teacher_reset_confirm.html", {"teacher": teacher})


@administrator_required(PERMISSION)
def teacher_username(request, pk):
    teacher = get_teacher_or_404(pk)
    form = TeacherUsernameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            teacher_accounts.change_teacher_username(
                user=teacher, new_username=form.cleaned_data["username"], actor=request.user
            )
        except ValidationError as error:
            form.add_error("username", error)
        else:
            messages.success(request, "Username changed.")
            return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_username_form.html", {"teacher": teacher, "form": form})


@administrator_required(PERMISSION)
def teacher_deactivate(request, pk):
    teacher = get_teacher_or_404(pk)
    form = TeacherDeactivateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            teacher_accounts.deactivate_teacher(
                user=teacher, reason=form.cleaned_data["reason"], actor=request.user
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Teacher login deactivated. Open sessions have ended.")
            return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_deactivate_confirm.html", {
        "teacher": teacher, "form": form,
        "assignment_count": teacher.assignment_count,
    })


@administrator_required(PERMISSION)
def teacher_reactivate(request, pk):
    teacher = get_teacher_or_404(pk)
    if request.method == "POST":
        try:
            teacher_accounts.reactivate_teacher(user=teacher, actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Teacher login reactivated. The password is unchanged.")
        return redirect("core:teacher-detail", pk=teacher.pk)
    return render(request, "core/teacher_reactivate_confirm.html", {"teacher": teacher})
```

`core/urls.py` (add after `teacher-create`; `teachers/<int:pk>/load/` stays):

```python
    path("teachers/<int:pk>/", teacher_views.teacher_detail, name="teacher-detail"),
    path("teachers/<int:pk>/reset-password/", teacher_views.teacher_reset_password,
         name="teacher-reset-password"),
    path("teachers/<int:pk>/username/", teacher_views.teacher_username, name="teacher-username"),
    path("teachers/<int:pk>/deactivate/", teacher_views.teacher_deactivate,
         name="teacher-deactivate"),
    path("teachers/<int:pk>/reactivate/", teacher_views.teacher_reactivate,
         name="teacher-reactivate"),
```

`core/breadcrumbs.py` add (the pk-bearing parent uses `Crumb("Teacher", "core:teacher-detail", True)`):

```python
_TEACHER = Crumb("Teacher", "core:teacher-detail", True)
```
and in `RULES`:
```python
    "teacher-detail": Rule("teacher-list", (_TEACHERS,), "Teacher"),
    "teacher-reset-password": Rule("teacher-list", (_TEACHERS, _TEACHER), "Reset password"),
    "teacher-username": Rule("teacher-list", (_TEACHERS, _TEACHER), "Change username"),
    "teacher-deactivate": Rule("teacher-list", (_TEACHERS, _TEACHER), "Deactivate"),
    "teacher-reactivate": Rule("teacher-list", (_TEACHERS, _TEACHER), "Reactivate"),
    "teacher-load": Rule("teacher-list", (_TEACHERS, _TEACHER), "Workload"),
```

Templates (extend `base.html`; mirror `core/templates/core/student_deactivate_confirm.html` from Phase 0 and `guardian_reset_confirm.html`):
- `teacher_detail.html`: header with name and status badge; profile list (username, email or "-", last sign-in, "Must change password: yes/no"); "Assignments" with `subject_assignments` and `class_assignments` (labels like `teacher_load.html`) and a link to `teacher-load` ("View full workload"); "Recent security events" table (`event.get_event_type_display`, `event.occurred_at|date:"j M Y, H:i"`, actor username); an action bar: Reset password, Change username, and Deactivate (when active, destructive style) or Reactivate (when inactive) — each a link to its confirm page.
- `teacher_reset_confirm.html`: copy `guardian_reset_confirm.html` wording for a teacher (sessions end, new temporary password shown once, must choose a new password); POST button "Reset password"; Cancel → `teacher-detail`.
- `teacher_username_form.html`: form with the `username` field via `_form_field.html`, submit "Change username", Cancel.
- `teacher_deactivate_confirm.html`: states the consequences (cannot sign in, open sessions end, **and "{{ assignment_count }} assignment{{ assignment_count|pluralize }} stay on record — reassign them first if classes still need teaching"**), form with the required `reason`, `form.non_field_errors`, submit "Deactivate login", Cancel.
- `teacher_reactivate_confirm.html`: short confirm ("They can sign in again with their existing password"), POST "Reactivate login", Cancel.
- `teacher_list.html`: make the Name cell link to `{% url 'core:teacher-detail' teacher.pk %}`.
- `teacher_credential_slip.html`: change Done to `{% url 'core:teacher-detail' teacher.pk %}`.
- `teacher_assignments.html` lines 6-8: replace "add logins to that group in the site administration." with `{% if perms.accounts.manage_teacher_accounts %}add teachers on the <a href="{% url 'core:teacher-list' %}">Teachers page</a>.{% else %}ask a school administrator to add teachers.{% endif %}`.
- `academic_year_list.html:42`: rename the link text "Teachers" to "Subject teachers" (it opens the assignments page; `academic_year_assignments.html:11` already calls it that). Update any existing test asserting the old link text and list it in the report.

- [ ] **Step 4: Run Task 4 tests** plus neighbours: `core.tests.test_ui_admin_phase3d core.tests.test_teacher_accounts core.tests.test_phase5_assignment_workflows core.tests.test_phase5_class_teachers core.tests.test_ui_admin_phase2 core.tests.test_ui_foundation core.tests.test_authorization`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/teacher_views.py core/forms.py core/urls.py core/breadcrumbs.py core/templates core/tests
git commit -m "feat(ui): teacher detail with reset, rename, deactivate and reactivate (F09)"
```

---

### Task 5: End-to-end, verification, browser check, notes

**Files:**
- Test: `core/tests/test_ui_admin_phase3d.py` (append the end-to-end tests)
- Modify: `docs/UI_REFERENCES.md` (one Status-line mention), this plan (completion notes)

- [ ] **Step 1: Write the end-to-end tests** (append)

```python
class TeacherEndToEndTests(AuthorizationClientsMixin, TestCase):
    """A teacher created from the page can sign in, must change the password,
    reaches the teacher area, and sees a section only once it is assigned."""

    def create_via_page(self, username="asha.rao"):
        created = self.administrator.post(reverse("core:teacher-create"), {
            "first_name": "Asha", "last_name": "Rao", "username": username, "email": "",
        })
        return created.context["password"]

    def test_new_teacher_must_change_password_then_reaches_the_teacher_area(self):
        password = self.create_via_page()
        teacher = self.client_class()
        self.assertTrue(teacher.login(username="asha.rao", password=password))
        forced = teacher.get(reverse("core:my-home"))
        self.assertEqual(forced.status_code, 302)
        self.assertIn(reverse("password_change"), forced["Location"])
        changed = teacher.post(reverse("password_change"), {
            "old_password": password,
            "new_password1": "Brand-new-pass-91",
            "new_password2": "Brand-new-pass-91",
        })
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(teacher.get(reverse("core:my-home")).status_code, 200)

    def test_deactivated_teacher_loses_access_immediately(self):
        user, password = add_teacher(self.admin_user, "gone.soon")
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        teacher = self.client_class()
        teacher.login(username="gone.soon", password=password)
        self.assertEqual(teacher.get(reverse("core:my-home")).status_code, 200)
        self.administrator.post(
            reverse("core:teacher-deactivate", args=[user.pk]), {"reason": "Left"}
        )
        self.assertNotEqual(teacher.get(reverse("core:my-home")).status_code, 200)
        self.assertFalse(self.client_class().login(username="gone.soon", password=password))
```

Confirm the exact `password_change` URL name and the form's field names from `config/urls.py` / `accounts/forms.py`, and that `core:my-home` is the right name (`core/urls.py:120`), before finalising; use the real ones. Add a third test, "sees the section only once assigned": create a section class-teacher assignment for a teacher created via the service, using the fixture style in `core/tests/test_phase5_class_teachers.py` or `core/tests/test_phase5_teacher_home.py`, and assert that `/my/students/` (or the teacher home) does not mention the section before the assignment and does after it.

- [ ] **Step 2: Run the end-to-end tests, then the full suite**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase3d --parallel 4` then `.venv\Scripts\python.exe manage.py test --parallel 4`. Expected: only the known date-dependent attendance test fails.

- [ ] **Step 3: Static checks**

Run: `.venv\Scripts\python.exe -m ruff check accounts core`, `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, `git diff --check`. Expected: ruff clean; "No changes detected".

- [ ] **Step 4: Browser smoke test (Playwright MCP, isolated server)**

Isolated server on a spare port (not 8765) against a throwaway SQLite database (Postgres env vars NOT set; migrate; `seed_demo` as in `core/tests/test_seed_demo.py`; create an administrator login). At 320 and 1440px: sidebar shows Teachers; the list renders as a table (sort, search, status filter); Add teacher shows the slip with the temporary password and a working Print button; sign in as that teacher in a second browser context, confirm the forced password change then the `/my/` area; detail page actions each show their confirm page; deactivate then confirm the teacher is signed out; no horizontal overflow; the slip response carries `Cache-Control: no-store` (check via `browser_evaluate` fetch or a network request listing). Stop the server and delete the temp DB. Screenshots go to the scratchpad, never the repo.

- [ ] **Step 5: Fix anything found, test first where it is a regression.**

- [ ] **Step 6: Record results**

Add a "Completion notes" section at the end of this plan (tests, counts, browser results, deviations) and a short Phase 3D mention in `docs/UI_REFERENCES.md`'s Status line.

- [ ] **Step 7: Commit**

```bash
git add core/tests docs
git commit -m "docs: record Phase 3D verification"
```

Do not push or open a PR until the user asks.

## Completion notes

**Tests.** `core.tests.test_ui_admin_phase3d` + `core.tests.test_teacher_accounts`: 43 pass. Full suite (`--parallel 4`): 1372 run, 1 failure, the known date-dependent `test_missing_report_skips_sections_without_students_and_future_dates`. `makemigrations --check` reports no changes; `ruff check accounts core` is clean (the 7 findings that remained were all in files this phase touched: `core/urls.py` import order and length, `core/forms.py` line length, and B023 loop-variable binding in `test_teacher_accounts.py`; fixed trivially). `git diff --check` clean.

**End-to-end tests added** (`test_ui_admin_phase3d.py`): a teacher created through the page must change the password (`password_change`, fields `old_password`/`new_password1`/`new_password2`) before reaching `core:my-home`; a deactivated teacher loses access on the next request and cannot sign in again; a service-created teacher sees a class-teacher Section on the teacher home only after `SectionClassTeacher.assign` (absent before).

**Browser smoke test** (Playwright, isolated server on port 8791, throwaway SQLite with `seed_demo`, separate browser contexts for admin and teacher; DB and server removed afterwards). At 1440 and 320 px: sidebar Teachers link works; list renders as a table; search, status filter and sort URLs respond; Add teacher shows the slip (username, temporary password, Print slip button) with `Cache-Control: no-store, no-cache, must-revalidate, private`; new teacher is forced to the password-change page, then reaches `/my/`; detail page links to reset, rename, deactivate and workload, and each confirm page renders; deactivating signs the teacher out on the next request and a re-login is refused. No horizontal overflow on any page checked at 320 or 1440. No defects found.

**Deviations / rulings.** (1) Controller ruling: administrators (superusers, `is_staff`, members of School Administrators) are never valid targets on the Teachers pages; an administrator who also teaches is a 404 there, so end-to-end teachers are plain Teachers-group logins. (2) Direct-permission note: a Teachers-group login that holds admin powers only through direct user permissions or another group is still manageable from these pages; tightening that is a possible follow-up. (3) The third end-to-end test patches `business_today` using the helpers from `test_phase5_teacher_home.py`.
