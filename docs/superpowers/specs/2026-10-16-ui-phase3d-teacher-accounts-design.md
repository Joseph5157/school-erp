# UI Phase 3D: Teacher Accounts Page — Design

Date: 2026-10-16
Source: `School_ERP_Admin_UI_UX_Audit.pdf` finding F09 (teacher setup is a dead end: "add logins to that group in the site administration"). Phase 3 sub-project 3D. Builds on Phases 0-3B (merged to `main`).

## Intent

Office staff can create and manage teacher logins inside the product. A teacher created here can sign in, is forced to choose a new password, lands in the existing teacher area (`/my/`), and can take attendance, enter marks and see their classes as soon as they are assigned to them with the existing assignment pages. Staff no longer have to open the Django admin.

Agreed with the user: option "list plus add and manage" (create, reset password, change username, deactivate/reactivate).

## Background (verified in the code)

- A teacher is an active login in the Django group `Teachers` (`core.models.TEACHERS_GROUP_NAME`, created by migration 0026). There is no Teacher profile model; `core.authorization.is_teacher` checks the group and `is_active`.
- Access to classes and subjects is already scoped by the assignment pages (`SectionClassTeacher`, `AssessmentTeacherAssignment`); code already ignores assignments whose login is inactive or not in the Teachers group.
- Guardian logins already have the pattern to copy (`core/guardian_accounts.py`): `generate_temporary_password`, `clean_new_username`, `must_change_password`, `user.end_all_sessions()`, one-time credential slip (`_credential_slip` in `core/views.py`, never cached), every workflow atomic and audited with `SecurityEvent`.

## Non-goals

Email invitations / set-your-own-password links (needs email delivery), adding an existing login to the Teachers group (use the Django admin, e.g. someone who is also a parent), bulk import of teachers, editing name/email after creation, changing a teacher's assignments (existing pages), any change to administrators' or guardians' accounts.

## Design

### 1. Permission, events, migrations

- New permission `accounts.manage_teacher_accounts` ("Can create and manage teacher logins"), declared in `accounts.User.Meta.permissions`, granted to the `School Administrators` group by a data migration (same style as migrations 0005/0007/0010). Superusers pass automatically. All Teachers pages and the sidebar link require it.
- New `SecurityEvent.EventType` values: `TEACHER_ACCOUNT_CREATED`, `TEACHER_PASSWORD_RESET`, `TEACHER_USERNAME_CHANGED`, `TEACHER_DEACTIVATED`, `TEACHER_REACTIVATED`. They are not routine types (kept, not purged). `class_for` must classify them like the guardian account events.
- Two small migrations (permission; event choices + group grant). No data is rewritten.

### 2. Service: `core/teacher_accounts.py`

Atomic functions, each audited, none logging or storing a plain password:
- `create_teacher(*, username, first_name, last_name, email, actor) -> (user, temporary_password)`: validates with `clean_new_username`, creates the login, `must_change_password=True`, adds it to the Teachers group, records `TEACHER_ACCOUNT_CREATED`. Duplicate username → `ValidationError("That username is not available.")`.
- `reset_teacher_password(*, user, actor) -> temporary_password`: new password, forced change, `end_all_sessions()`, records `TEACHER_PASSWORD_RESET`.
- `change_teacher_username(*, user, new_username, actor)`: validated and unique; records `TEACHER_USERNAME_CHANGED`.
- `deactivate_teacher(*, user, reason, actor)`: reason required; `is_active=False`, `end_all_sessions()`; records `TEACHER_DEACTIVATED` with the reason in `detail`. `reactivate_teacher(*, user, actor)`: `is_active=True`, records `TEACHER_REACTIVATED`.
- Every function first checks the target is in the Teachers group and is not a superuser; anything else raises `ValidationError` (views map this to 404/message), so these actions can never be used on administrators or guardians. Row-level lock (`select_for_update`) on the target user.
- A shared helper `teacher_queryset()` returns users in the Teachers group (active and inactive) annotated for the list.

### 3. Pages

- **Sidebar:** "Teachers" link in the School setup group (`core:teacher-list`), permission `accounts.manage_teacher_accounts`.
- **List `/teachers/` (`teacher-list`):** Phase 3A data table: columns Name (sortable), Username, Email, Status (sortable, active/inactive), Assignments (count of subject + class-teacher assignments), Last sign-in. Search `?q=` (name/username/email) and a status filter. **Add teacher** primary action. Name links to the detail page.
- **Add `/teachers/new/` (`teacher-create`):** form (first name, last name, username, optional email) using the shared field partial and required legend. Success renders the one-time credential slip (same no-store headers as guardians) with the temporary password, username and the instruction that the teacher must change it at first sign-in.
- **Detail `/teachers/<pk>/` (`teacher-detail`):** profile, status, assignments (each linking to its existing page; link to `teacher-load`), recent security events for this login, and the actions below.
- **Actions, each with a confirm page and its own POST (as Phase 0):** reset password (`teacher-reset-password`, shows the slip), change username (`teacher-username`), deactivate (`teacher-deactivate`, requires a reason, lists the number of assignments the teacher still holds so staff can reassign first) and reactivate (`teacher-reactivate`).
- **Assignments page:** the sentence "add logins to that group in the site administration" becomes a link to the Teachers page for users with the permission.
- **Breadcrumbs:** map entries for the five new pages (parent Teachers; sidebar section `teacher-list`).

### 4. Security and errors

- Server enforces the permission on every view; the sidebar stays display-only.
- Non-Teachers-group targets and superusers: 404 on every detail/action URL.
- Credential slip: `Cache-Control: no-store` etc.; the password appears only in that response and is never written to messages, logs, the session or the audit `detail`.
- Duplicate/invalid usernames and a missing deactivation reason show form errors, never a 500.
- A user who is both an administrator and a Teachers-group member cannot deactivate their own login here (clear message).

### 5. Testing

- Service: create makes a Teachers-group login with `must_change_password`, a working temporary password, and an audit event; duplicate username rejected; reset ends sessions and changes the password; username change validated; deactivate requires a reason, blocks sign-in and ends sessions; reactivate restores it; non-Teachers target and superuser rejected; own-login deactivation refused; no plain password in `SecurityEvent.detail`.
- Views: permission (anonymous → login, non-admin → 403), list table behaviours (search, status filter, sort, pagination, assignment counts), slip headers and one-time display, confirm-page-then-POST for each action, 404 for administrators/guardians.
- End-to-end: a teacher created via the page signs in with the temporary password, is forced to change it, reaches `/my/`, sees no sections until assigned, and sees the section after an assignment is made.
- Browser: Playwright pass at 320 and 1440px (list, add, slip, detail, deactivate).

## Open items to confirm during planning

- Exact model names/field names for the assignment counts (`SectionClassTeacher`, `AssessmentTeacherAssignment`) and the helper `teacher_assignments(user)`.
- Where the credential slip template should live (a teacher-specific template vs generalizing `guardian_credential_slip.html`).
- How `SecurityEvent.class_for` classifies new types.
