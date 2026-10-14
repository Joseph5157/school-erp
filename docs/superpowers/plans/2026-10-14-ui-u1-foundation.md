# U1 UI Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every page a phone-ready shell — design tokens, viewport, office sidebar/drawer, teacher and guardian bottom tabs, account menu with role switcher, redesigned sign-in and change-password pages, and shared empty-state and message components — without changing any behaviour.

**Architecture:** Server-rendered Django templates on Bootstrap 5.3.3 (CDN, already used). A new `core/navigation.py` builds permission-filtered navigation data; `core.context_processors.roles` exposes it to every template. Layout pieces live in `templates/partials/`. Our own styles live in `static/css/erp.css` (CSS custom properties over Bootstrap); `static/js/erp.js` adds small progressive enhancements (password show/hide, message auto-hide). Bootstrap's JS bundle is added for the off-canvas phone drawer.

**Tech Stack:** Python 3.13, Django 5.2.17, Bootstrap 5.3.3 (jsDelivr), WhiteNoise 6.12, Django `TestCase`, ruff.

**Spec:** `docs/UI_REFERENCES.md` (picks 1.1 Square sidebar, 1.2 Shopify phone menu, 1.3 ShopBack sign-in, 4.1 Cash App choose-sheet style for role switching, 5.11 Sprig empty state, 5.12 Fresha change password, 5.13 Luma toast) and `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md`.

## Global Constraints

- Start from `origin/main`; branch name `ui/u1-foundation`.
- No model, migration, URL or permission changes. All 944 existing tests must still pass.
- Keep every existing text that tests depend on: "My assessments", "You are not a class teacher today.", "access under review by the school".
- Guardian portal HTML must never contain the substrings `fee`, `announcement`, `pdf`, `download` (case-insensitive) and never `/students/<pk>/` (asserted by `test_no_database_ids_and_no_excluded_features`). This includes class names, aria labels and file names — never use "feedback", and never use Bootstrap's `invalid-feedback`/`valid-feedback` classes in a template rendered under `portal/`.
- Navigation links are shown only when the user has the permission; views still enforce access (no access logic moves into templates).
- Bootstrap stays at exactly `5.3.3` from `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/`.
- Sign-in field is labelled **Username** (guardians receive usernames on credential slips, not emails).
- Every page usable at 360 px wide with no horizontal page scroll.
- Python: line length 100, ruff rules E, F, I, UP, B. All imports in `core/tests/test_ui_foundation.py` stay in the single import block at the top of the file, sorted (run `ruff check --fix` after adding imports).
- Commands assume Windows PowerShell from the repo root with the DB variables loaded (Task 1 Step 1).

## Review Focus

1. **Portal forbidden words** — any new partial included on portal pages that contains "fee" (e.g. "feedback", Bootstrap `invalid-feedback`), "download", "pdf" or "announcement" breaks the existing guardian test. Pinned in Task 5 (`test_portal_pages_still_have_no_excluded_words`).
2. **Static files in tests and local dev** — `{% static %}` with `CompressedManifestStaticFilesStorage` raises "Missing staticfiles manifest entry" until `collectstatic` runs; this already broke `/admin/login/` locally. Pinned in Task 1 (`test_admin_login_renders`, `test_base_links_stylesheet_and_viewport`).
3. **Multi-role users** — an admin who is also a teacher must see the sidebar only in the office area, the tab bar only in the teacher area, and links to every area in the account menu. Pinned in Task 4 (`test_admin_teacher_sees_sidebar_only_in_office_area`) and Task 5 (`test_account_menu_lists_all_areas_and_marks_current`).
4. **Login `next` handling** — rewriting the login form by hand can drop `next` or the CSRF token, sending users to the wrong page or failing every sign-in. Pinned in Task 6 (`test_login_keeps_next`).
5. **Error messages styled as success** — Django's `error` level tag has no Bootstrap `alert-error` class; errors must render as `alert-danger` and must not auto-hide. Pinned in Task 7 (`test_error_message_uses_danger_and_stays`).

---

## File structure

| File | Responsibility |
|---|---|
| `config/settings.py` (modify) | `STATICFILES_DIRS`; plain static storage in DEBUG and tests |
| `static/css/erp.css` (create) | Design tokens and layout: top bar, sidebar, tab bar, auth card, empty state, messages, status pills |
| `static/js/erp.js` (create) | Password show/hide, auto-hide for success/info messages |
| `core/navigation.py` (create) | `NavLink`, `OFFICE_NAV`, `TEACHER_TABS`, `office_nav()`, `teacher_tabs()`, `current_area()` |
| `core/context_processors.py` (modify) | Add `office_nav`, `teacher_tabs`, `current_area` to template context |
| `templates/base.html` (rewrite) | Staff shell: head, top bar, sidebar, main, tab bar, scripts |
| `templates/portal/base.html` (rewrite) | Guardian shell: head, top bar, child chips, main, tab bar |
| `templates/partials/_sidebar.html` (create) | Office sidebar / phone drawer |
| `templates/partials/_tabbar.html` (create) | Bottom tab bar (teacher) |
| `templates/partials/_account_menu.html` (create) | Account menu: user, area switcher, change password, log out |
| `templates/partials/_messages.html` (create) | Django messages as dismissible live-region alerts |
| `templates/partials/_empty.html` (create) | Empty-state block |
| `templates/registration/login.html` (rewrite) | Sign-in card |
| `templates/registration/password_change_form.html` (rewrite) | Change-password card |
| `core/templates/core/choose_area.html` (rewrite) | Area chooser card |
| `core/templates/core/my_home.html` (modify) | Empty-state partial for "not a class teacher" |
| `templates/portal/home.html` (modify) | Empty-state partial for "no students linked" |
| `core/tests/test_ui_foundation.py` (create) | All U1 tests |

---

### Task 1: Branch, static files and asset hooks

**Files:**
- Modify: `config/settings.py` (imports at top; static block near line 186)
- Create: `static/css/erp.css`, `static/js/erp.js`
- Modify: `templates/base.html` (head and end of body only in this task)
- Create: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Produces: `settings.STATICFILES_DIRS == [BASE_DIR / "static"]`; `settings.TESTING: bool`; `/static/css/erp.css` and `/static/js/erp.js` resolvable in tests and DEBUG.

- [ ] **Step 1: Create the branch from an up-to-date main and load the DB environment**

```powershell
git fetch origin
git switch -c ui/u1-foundation origin/main
foreach ($k in 'DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT') { Set-Item "env:$k" ([Environment]::GetEnvironmentVariable($k,'User')) }
.\.venv\Scripts\python.exe manage.py migrate
```

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_ui_foundation.py`:

```python
"""U1 UI foundation: static files, shell, navigation, auth pages, components."""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.tests.phase4_fixtures import Phase4Fixture

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


class StaticFilesTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_tests_use_plain_static_storage(self):
        self.assertEqual(
            settings.STORAGES["staticfiles"]["BACKEND"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )

    def test_admin_login_renders(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_base_links_stylesheet_and_viewport(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertContains(page, VIEWPORT)
        self.assertContains(page, "/static/css/erp.css")
        self.assertContains(page, "/static/js/erp.js")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation -v 2`
Expected: FAIL — `test_tests_use_plain_static_storage` (backend is `CompressedManifestStaticFilesStorage`) and `test_base_links_stylesheet_and_viewport` (no viewport, no stylesheet).

- [ ] **Step 4: Update settings**

In `config/settings.py`, add `import sys` next to the existing `import os` at the top. Then replace the static block (from `STATIC_URL` through the closing `}` of `STORAGES`) with:

```python
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# The manifest storage needs `collectstatic` first; tests and local DEBUG use plain storage
# so `{% static %}` works without it. Production (DEBUG off, not testing) is unchanged.
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if DEBUG or TESTING:
    STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
```

- [ ] **Step 5: Create the static files**

`static/css/erp.css`:

```css
/* School ERP design layer over Bootstrap 5.3.3. Tokens first, then layout, then components. */
```

`static/js/erp.js`:

```javascript
// School ERP progressive enhancements. Every page works without this file.
```

- [ ] **Step 6: Add viewport, stylesheet and scripts to `templates/base.html`**

Replace everything from the first line through `</head>` with:

```html
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}School ERP{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="{% static 'css/erp.css' %}" rel="stylesheet">
</head>
```

and insert immediately before `</body>`:

```html
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
    <script src="{% static 'js/erp.js' %}" defer></script>
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation -v 2`
Expected: 3 tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add config/settings.py static/css/erp.css static/js/erp.js templates/base.html core/tests/test_ui_foundation.py
git commit -m "feat(ui): static files dir, plain storage in dev/tests, viewport and erp assets"
```

---

### Task 2: Design tokens and layout CSS

**Files:**
- Modify: `static/css/erp.css`

**Interfaces:**
- Produces CSS classes used by later tasks: `.erp-topbar`, `.erp-brand`, `.erp-topbar-links`, `.erp-spacer`, `.erp-sidebar`, `.erp-nav-heading`, `.erp-main`, `.erp-content`, `.erp-tabbar`, `.erp-account`, `.erp-avatar`, `.erp-account-panel`, `.erp-menu-item`, `.erp-check`, `.erp-auth`, `.erp-password`, `.erp-empty`, `.erp-empty-icon`, `.erp-empty-title`, `.erp-messages`, `.erp-chips`, `.erp-pill` (+ `.is-draft`, `.is-submitted`, `.is-present`, `.is-absent`, `.is-pending`, `.is-accepted`, `.is-rejected`); body modifiers `.erp`, `.has-sidebar`, `.has-tabbar`.

Pure CSS; verified by Task 1's stylesheet test and visually in Task 8.

- [ ] **Step 1: Write the stylesheet**

Replace `static/css/erp.css` with:

```css
/* School ERP design layer over Bootstrap 5.3.3. Tokens first, then layout, then components. */

:root {
  --erp-ink: #18212b;
  --erp-ink-soft: #4a5562;
  --erp-paper: #f5f6f3;
  --erp-surface: #ffffff;
  --erp-rule: #dde1dc;
  --erp-accent: #1f6b52;
  --erp-accent-strong: #185842;
  --erp-accent-wash: #e3efe9;
  --erp-warn: #9a5b00;
  --erp-warn-wash: #fbf0dc;
  --erp-crit: #a3322a;
  --erp-crit-wash: #f8e4e1;
  --erp-radius: 10px;
  --erp-topbar-h: 3.5rem;
  --erp-sidebar-w: 15.5rem;
  --erp-tabbar-h: 3.75rem;

  --bs-body-bg: var(--erp-paper);
  --bs-body-color: var(--erp-ink);
  --bs-secondary-color: var(--erp-ink-soft);
  --bs-border-color: var(--erp-rule);
  --bs-link-color: var(--erp-accent);
  --bs-link-color-rgb: 31, 107, 82;
  --bs-link-hover-color: var(--erp-accent-strong);
  --bs-primary: var(--erp-accent);
  --bs-primary-rgb: 31, 107, 82;
}

.btn-primary {
  --bs-btn-bg: var(--erp-accent);
  --bs-btn-border-color: var(--erp-accent);
  --bs-btn-hover-bg: var(--erp-accent-strong);
  --bs-btn-hover-border-color: var(--erp-accent-strong);
  --bs-btn-active-bg: var(--erp-accent-strong);
  --bs-btn-active-border-color: var(--erp-accent-strong);
  --bs-btn-disabled-bg: var(--erp-accent);
  --bs-btn-disabled-border-color: var(--erp-accent);
}
.btn-outline-primary {
  --bs-btn-color: var(--erp-accent);
  --bs-btn-border-color: var(--erp-accent);
  --bs-btn-hover-bg: var(--erp-accent);
  --bs-btn-hover-border-color: var(--erp-accent);
  --bs-btn-active-bg: var(--erp-accent-strong);
}
.form-control:focus, .form-select:focus, .btn:focus-visible {
  border-color: var(--erp-accent);
  box-shadow: 0 0 0 .2rem rgba(31, 107, 82, .25);
}

/* ---------- Layout ---------- */

body.erp { min-height: 100vh; }

.erp-topbar {
  position: sticky; top: 0; z-index: 1030;
  height: var(--erp-topbar-h);
  display: flex; align-items: center; gap: .75rem;
  padding-inline: 1rem;
  background: var(--erp-surface);
  border-bottom: 1px solid var(--erp-rule);
}
.erp-brand { font-weight: 700; color: var(--erp-ink); text-decoration: none; white-space: nowrap; }
.erp-topbar-links { gap: .25rem; min-width: 0; overflow-x: auto; }
.erp-topbar-links a {
  padding: .4rem .6rem; border-radius: 6px; color: var(--erp-ink);
  text-decoration: none; white-space: nowrap;
}
.erp-topbar-links a.active { background: var(--erp-accent-wash); color: var(--erp-accent); font-weight: 600; }
.erp-spacer { flex: 1; }

.erp-main { min-width: 0; }
.erp-content { max-width: 75rem; padding-block: 1.5rem 2.5rem; padding-inline: 1rem; }

.erp-sidebar { background: var(--erp-surface); }
.erp-nav-heading {
  margin: 1rem 0 .25rem; padding-inline: .75rem;
  font-size: .72rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  color: var(--erp-ink-soft);
}
.erp-sidebar .nav-link { color: var(--erp-ink); border-radius: 6px; padding: .4rem .75rem; }
.erp-sidebar .nav-link:hover { background: var(--erp-paper); }
.erp-sidebar .nav-link.active { background: var(--erp-accent-wash); color: var(--erp-accent); font-weight: 600; }

@media (min-width: 992px) {
  body.has-sidebar .erp-sidebar {
    position: fixed; top: var(--erp-topbar-h); bottom: 0; left: 0;
    width: var(--erp-sidebar-w); overflow-y: auto;
    border-right: 1px solid var(--erp-rule); padding: .5rem;
  }
  body.has-sidebar .erp-main { margin-left: var(--erp-sidebar-w); }
  .erp-content { padding-inline: 2rem; }
}

.erp-tabbar {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 1030;
  background: var(--erp-surface); border-top: 1px solid var(--erp-rule);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.erp-tabbar ul { display: flex; margin: 0; padding: 0; list-style: none; }
.erp-tabbar li { flex: 1; }
.erp-tabbar a {
  display: flex; align-items: center; justify-content: center; text-align: center;
  min-height: var(--erp-tabbar-h); padding: .25rem; font-size: .8rem; line-height: 1.2;
  color: var(--erp-ink-soft); text-decoration: none;
}
.erp-tabbar a.active { color: var(--erp-accent); font-weight: 700; box-shadow: inset 0 3px 0 var(--erp-accent); }
@media (max-width: 991.98px) {
  body.has-tabbar .erp-content {
    padding-bottom: calc(var(--erp-tabbar-h) + 2rem + env(safe-area-inset-bottom, 0px));
  }
}

/* ---------- Account menu (details/summary, works without JS) ---------- */

.erp-account { position: relative; }
.erp-account > summary {
  list-style: none; cursor: pointer; display: flex; align-items: center; gap: .5rem;
  padding: .3rem .5rem; border-radius: 999px; border: 1px solid var(--erp-rule);
}
.erp-account > summary::-webkit-details-marker { display: none; }
.erp-avatar {
  width: 1.9rem; height: 1.9rem; border-radius: 50%;
  display: inline-grid; place-items: center;
  background: var(--erp-accent-wash); color: var(--erp-accent); font-weight: 700; font-size: .85rem;
}
.erp-account-panel {
  position: absolute; right: 0; top: calc(100% + .4rem); z-index: 1040;
  width: min(18rem, calc(100vw - 2rem));
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
  box-shadow: 0 8px 24px rgba(24, 33, 43, .12); padding: .5rem;
}
.erp-account-panel .erp-nav-heading { margin-top: .5rem; }
.erp-account-panel a, .erp-account-panel .erp-menu-item {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
  padding: .55rem .75rem; border-radius: 6px; border: 0; background: none;
  color: var(--erp-ink); text-decoration: none; text-align: left; font: inherit;
}
.erp-account-panel a:hover, .erp-account-panel .erp-menu-item:hover { background: var(--erp-paper); }
.erp-account-panel [aria-current="true"] { font-weight: 600; color: var(--erp-accent); }
.erp-check { color: var(--erp-accent); font-weight: 700; }

/* ---------- Auth pages ---------- */

.erp-auth {
  max-width: 26rem; margin: 2rem auto; padding: 1.75rem;
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
}
.erp-auth h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: .25rem; }
.erp-password { position: relative; }
.erp-password .form-control { padding-right: 4.5rem; }
.erp-password [data-erp-toggle-password] {
  position: absolute; right: .25rem; top: 50%; transform: translateY(-50%);
  font-size: .85rem; font-weight: 600; text-decoration: none;
}
.erp-auth .form-text ul { padding-left: 1.1rem; margin: .35rem 0 0; }

/* ---------- Components ---------- */

.erp-empty {
  display: grid; justify-items: center; gap: .35rem; text-align: center;
  padding: 2.5rem 1rem; border: 1px dashed var(--erp-rule); border-radius: var(--erp-radius);
  background: var(--erp-surface); color: var(--erp-ink-soft);
}
.erp-empty-icon { font-size: 1.6rem; line-height: 1; }
.erp-empty-title { font-weight: 600; color: var(--erp-ink); margin: 0; }
.erp-empty p { margin: 0; max-width: 34rem; }

.erp-messages {
  position: fixed; z-index: 1050; display: grid; gap: .5rem;
  left: 1rem; right: 1rem; bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
}
body.has-tabbar .erp-messages {
  bottom: calc(var(--erp-tabbar-h) + 1rem + env(safe-area-inset-bottom, 0px));
}
@media (min-width: 992px) {
  .erp-messages, body.has-tabbar .erp-messages {
    left: auto; right: 1.5rem; top: calc(var(--erp-topbar-h) + 1rem); bottom: auto; width: 24rem;
  }
}
.erp-messages .alert { margin: 0; box-shadow: 0 6px 18px rgba(24, 33, 43, .12); }

.erp-chips { display: flex; gap: .4rem; overflow-x: auto; padding-block: .25rem; }
.erp-chips a {
  white-space: nowrap; padding: .3rem .8rem; border-radius: 999px; border: 1px solid var(--erp-rule);
  color: var(--erp-ink); text-decoration: none; background: var(--erp-surface); font-size: .9rem;
}
.erp-chips a.active { background: var(--erp-accent); border-color: var(--erp-accent); color: #fff; }

.erp-pill {
  display: inline-block; padding: .1rem .55rem; border-radius: 999px;
  font-size: .78rem; font-weight: 600; line-height: 1.5;
  background: var(--erp-paper); color: var(--erp-ink-soft); border: 1px solid var(--erp-rule);
}
.erp-pill.is-submitted, .erp-pill.is-present, .erp-pill.is-accepted {
  background: var(--erp-accent-wash); color: var(--erp-accent); border-color: transparent;
}
.erp-pill.is-draft, .erp-pill.is-pending {
  background: var(--erp-warn-wash); color: var(--erp-warn); border-color: transparent;
}
.erp-pill.is-absent, .erp-pill.is-rejected {
  background: var(--erp-crit-wash); color: var(--erp-crit); border-color: transparent;
}

/* Wide tables scroll inside their own box on phones instead of widening the page. */
@media (max-width: 575.98px) {
  .erp-content table:not(.erp-keep) { display: block; overflow-x: auto; }
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
```

- [ ] **Step 2: Run the U1 tests and ruff**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation` → PASS (3).
Run: `.\.venv\Scripts\ruff.exe check .` → no errors.

- [ ] **Step 3: Commit**

```powershell
git add static/css/erp.css
git commit -m "feat(ui): design tokens, layout and component styles"
```

---

### Task 3: Navigation data (`core/navigation.py`) and context

**Files:**
- Create: `core/navigation.py`
- Modify: `core/context_processors.py`
- Test: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Consumes: `core.authorization.user_areas(user) -> list[tuple[str, str, str]]` (existing; keys `"admin"`, `"teacher"`, `"guardian"`).
- Produces:
  - `NavLink(label: str, url_name: str, perm: str | None = None)` — frozen dataclass; `url_name` is namespaced (`"core:student-list"`).
  - `office_nav(user, url_name: str | None) -> list[dict]` — `[{"title": str, "links": [{"label": str, "url": str, "active": bool}]}]`; groups with no visible links are dropped; `url_name` is the un-namespaced current name (`"student-list"`).
  - `teacher_tabs(url_name: str | None) -> list[dict]` — `[{"label", "url", "active"}]`, always 4 items.
  - `current_area(request) -> str | None` — `"guardian"`, `"teacher"`, `"admin"` or `None`.
  - Template context from `roles()`: existing `user_is_teacher`, `user_is_guardian`, `user_areas`, `user_has_several_areas`, plus new `current_area`, `office_nav` (non-empty only when `current_area == "admin"`), `teacher_tabs`.

- [ ] **Step 1: Add imports at the top of the test file**

Add to the import block of `core/tests/test_ui_foundation.py` (then run `.\.venv\Scripts\ruff.exe check --fix core/tests/test_ui_foundation.py` to sort):

```python
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import RequestFactory
from django.urls import resolve

from core.navigation import current_area, office_nav, teacher_tabs
```

- [ ] **Step 2: Append the failing tests**

```python
class NavigationDataTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def titles(self, groups):
        return [group["title"] for group in groups]

    def labels(self, groups):
        return [link["label"] for group in groups for link in group["links"]]

    def area_for(self, user, path):
        request = RequestFactory().get(path)
        request.user = user
        request.resolver_match = resolve(path)
        return current_area(request)

    def test_admin_sees_all_office_groups(self):
        groups = office_nav(self.admin, "school-detail")
        self.assertEqual(
            self.titles(groups),
            ["School setup", "Admissions", "Daily", "Results", "Access and security"],
        )
        self.assertIn("Academic Years", self.labels(groups))
        self.assertIn("Sign-in lockouts", self.labels(groups))

    def test_teacher_sees_no_office_groups(self):
        self.assertEqual(office_nav(self.rao, "my-home"), [])

    def test_links_need_their_permission(self):
        clerk = self.make_user("clerk")
        clerk.user_permissions.add(
            Permission.objects.get(codename="view_student", content_type__app_label="core")
        )
        groups = office_nav(clerk, None)
        self.assertEqual(self.titles(groups), ["Admissions"])
        self.assertEqual(self.labels(groups), ["Students"])

    def test_active_link_follows_url_name(self):
        groups = office_nav(self.admin, "student-list")
        active = [link["label"] for g in groups for link in g["links"] if link["active"]]
        self.assertEqual(active, ["Students"])

    def test_teacher_tabs(self):
        tabs = teacher_tabs("my-assessments")
        self.assertEqual([t["label"] for t in tabs],
                         ["My day", "My students", "My assessments", "Results"])
        self.assertEqual([t["label"] for t in tabs if t["active"]], ["My assessments"])
        self.assertEqual(tabs[0]["url"], reverse("core:my-home"))

    def test_current_area(self):
        self.assertEqual(self.area_for(self.admin, reverse("core:school-detail")), "admin")
        self.assertEqual(self.area_for(self.rao, reverse("core:my-home")), "teacher")
        self.assertEqual(self.area_for(self.rao, reverse("core:my-students")), "teacher")

    def test_current_area_none_for_anonymous(self):
        self.assertIsNone(self.area_for(AnonymousUser(), reverse("login")))

    def test_context_exposes_navigation(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertEqual(page.context["current_area"], "admin")
        self.assertTrue(page.context["office_nav"])
        self.assertEqual(len(page.context["teacher_tabs"]), 4)
```

If `test_admin_sees_all_office_groups` fails because the "School Administrators" group lacks one of the permissions, do not change the test to match: check the group's permissions in the migrations first (`core/migrations/*group*`), because the decorators on those views (`administrator_required(...)`) expect administrators to have them.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation -v 2`
Expected: ERROR — `ModuleNotFoundError: No module named 'core.navigation'`.

- [ ] **Step 4: Implement `core/navigation.py`**

```python
"""Navigation data for the page shell (U1). Display only: views still enforce access."""

from dataclasses import dataclass

from django.urls import reverse

from core.authorization import user_areas


@dataclass(frozen=True)
class NavLink:
    label: str
    url_name: str  # namespaced, e.g. "core:student-list"
    perm: str | None = None


OFFICE_NAV = (
    ("School setup", (
        NavLink("School", "core:school-detail", "core.view_school"),
        NavLink("Academic Years", "core:academic-year-list", "core.view_academicyear"),
        NavLink("Classes/Grades", "core:class-grade-list", "core.view_classgrade"),
        NavLink("Subjects", "core:subject-list", "core.view_subject"),
    )),
    ("Admissions", (
        NavLink("Applicants", "core:applicant-list", "core.view_applicant"),
        NavLink("Students", "core:student-list", "core.view_student"),
        NavLink("Guardians", "core:guardian-list", "core.view_guardian"),
    )),
    ("Daily", (
        NavLink("Attendance", "core:attendance-register-list", "core.view_attendanceregister"),
        NavLink("Attendance reports", "core:attendance-reports", "core.view_attendanceentry"),
    )),
    ("Results", (
        NavLink("Stale publications", "core:publications-stale", "core.view_termpublication"),
    )),
    ("Access and security", (
        NavLink("Access reviews", "core:guardian-access-reviews",
                "core.view_guardianaccessreview"),
        NavLink("Sign-in lockouts", "core:login-lockouts", "accounts.clear_login_lockout"),
    )),
)

TEACHER_TABS = (
    NavLink("My day", "core:my-home"),
    NavLink("My students", "core:my-students"),
    NavLink("My assessments", "core:my-assessments"),
    NavLink("Results", "core:my-results"),
)

# Teacher pages whose URL name does not start with "my-".
_TEACHER_URL_NAMES = {"assessment-marks-entry"}


def _short(url_name):
    return url_name.split(":", 1)[-1]


def _link(link, url_name):
    return {
        "label": link.label,
        "url": reverse(link.url_name),
        "active": url_name == _short(link.url_name),
    }


def office_nav(user, url_name):
    """Office sidebar groups the user may see; empty groups are dropped."""
    if not (user and user.is_authenticated):
        return []
    groups = []
    for title, links in OFFICE_NAV:
        visible = [
            _link(link, url_name)
            for link in links
            if link.perm is None or user.has_perm(link.perm)
        ]
        if visible:
            groups.append({"title": title, "links": visible})
    return groups


def teacher_tabs(url_name):
    return [_link(tab, url_name) for tab in TEACHER_TABS]


def current_area(request):
    """Which area the current page belongs to: "guardian", "teacher", "admin" or None."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return None
    match = getattr(request, "resolver_match", None)
    if match is not None and match.namespace == "portal":
        return "guardian"
    url_name = match.url_name if match is not None else None
    if url_name and (url_name.startswith("my-") or url_name in _TEACHER_URL_NAMES):
        return "teacher"
    keys = [key for key, _, _ in user_areas(user)]
    if "admin" in keys:
        return "admin"
    return keys[0] if keys else None
```

- [ ] **Step 5: Extend the context processor**

Replace `core/context_processors.py` with:

```python
from core.authorization import is_guardian, is_teacher, user_areas
from core.navigation import current_area, office_nav, teacher_tabs


def roles(request):
    """Expose role flags and navigation to templates (display only; views enforce access)."""
    user = getattr(request, "user", None)
    areas = user_areas(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match is not None else None
    area = current_area(request)
    return {
        "user_is_teacher": is_teacher(user),
        "user_is_guardian": is_guardian(user),
        "user_areas": areas,
        "user_has_several_areas": len(areas) > 1,
        "current_area": area,
        "office_nav": office_nav(user, url_name) if area == "admin" else [],
        "teacher_tabs": teacher_tabs(url_name),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation -v 2`
Expected: all PASS.
Run: `.\.venv\Scripts\ruff.exe check .` → no errors.

- [ ] **Step 7: Commit**

```powershell
git add core/navigation.py core/context_processors.py core/tests/test_ui_foundation.py
git commit -m "feat(ui): permission-filtered navigation data and current area"
```

---

### Task 4: Staff shell — top bar, sidebar/drawer, teacher tab bar

**Files:**
- Rewrite: `templates/base.html`
- Create: `templates/partials/_sidebar.html`, `templates/partials/_tabbar.html`, `templates/partials/_messages.html` (interim version; finished in Task 7), `templates/partials/_account_menu.html` (empty; filled in Task 5)
- Test: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Consumes: context `office_nav`, `teacher_tabs`, `current_area` (Task 3).
- Produces: element ids `erp-sidebar` and `main`; `_tabbar.html` expects `tabs` (list of `{"label","url","active"}`) and `tabbar_label` (str).

- [ ] **Step 1: Append the failing tests**

```python
class StaffShellTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_admin_office_page_has_sidebar_and_no_tabbar(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:student-list"))
        self.assertContains(page, 'id="erp-sidebar"')
        self.assertContains(page, reverse("core:academic-year-list"))
        self.assertContains(page, 'aria-current="page"')
        self.assertNotContains(page, 'class="erp-tabbar')

    def test_teacher_page_has_tabbar_and_no_sidebar(self):
        self.client.login(username="rao", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertContains(page, 'class="erp-tabbar')
        self.assertContains(page, "My assessments")
        self.assertContains(page, reverse("core:my-students"))
        self.assertNotContains(page, 'id="erp-sidebar"')

    def test_admin_teacher_sees_sidebar_only_in_office_area(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        office = self.client.get(reverse("core:school-detail"))
        teaching = self.client.get(reverse("core:my-home"))
        self.assertContains(office, 'id="erp-sidebar"')
        self.assertNotContains(office, 'class="erp-tabbar')
        self.assertNotContains(teaching, 'id="erp-sidebar"')
        self.assertContains(teaching, 'class="erp-tabbar')

    def test_anonymous_login_page_has_no_navigation(self):
        page = self.client.get(reverse("login"))
        self.assertNotContains(page, 'id="erp-sidebar"')
        self.assertNotContains(page, 'class="erp-tabbar')

    def test_skip_link_targets_main(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:school-detail"))
        self.assertContains(page, 'href="#main"')
        self.assertContains(page, 'id="main"')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation.StaffShellTests -v 2`
Expected: FAIL — no `erp-sidebar`, no `erp-tabbar`, no `#main`.

- [ ] **Step 3: Create the partials**

`templates/partials/_sidebar.html`:

```html
{# Office navigation: fixed sidebar from 992px, off-canvas drawer below. Display only. #}
<nav class="erp-sidebar offcanvas-lg offcanvas-start" tabindex="-1" id="erp-sidebar" aria-label="School administration">
    <div class="offcanvas-header">
        <span class="h6 mb-0">Menu</span>
        <button type="button" class="btn-close" data-bs-dismiss="offcanvas" data-bs-target="#erp-sidebar" aria-label="Close menu"></button>
    </div>
    <div class="offcanvas-body d-block">
        {% for group in office_nav %}
        <p class="erp-nav-heading">{{ group.title }}</p>
        <ul class="nav flex-column">
            {% for link in group.links %}
            <li class="nav-item"><a class="nav-link{% if link.active %} active{% endif %}" href="{{ link.url }}"{% if link.active %} aria-current="page"{% endif %}>{{ link.label }}</a></li>
            {% endfor %}
        </ul>
        {% endfor %}
    </div>
</nav>
```

`templates/partials/_tabbar.html`:

```html
{# Bottom tab bar for phones. Expects `tabs` and `tabbar_label`. #}
<nav class="erp-tabbar d-lg-none" aria-label="{{ tabbar_label }}">
    <ul>
        {% for tab in tabs %}
        <li><a href="{{ tab.url }}"{% if tab.active %} class="active" aria-current="page"{% endif %}>{{ tab.label }}</a></li>
        {% endfor %}
    </ul>
</nav>
```

`templates/partials/_messages.html` (interim; replaced in Task 7):

```html
{% for message in messages %}<div class="alert alert-info">{{ message }}</div>{% endfor %}
```

`templates/partials/_account_menu.html`: create as an empty file.

- [ ] **Step 4: Rewrite `templates/base.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}School ERP{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="{% static 'css/erp.css' %}" rel="stylesheet">
</head>
<body class="erp{% if office_nav %} has-sidebar{% endif %}{% if current_area == 'teacher' %} has-tabbar{% endif %}">
    <a class="visually-hidden-focusable" href="#main">Skip to content</a>
    <header class="erp-topbar">
        {% if office_nav %}
        <button class="btn btn-outline-secondary btn-sm d-lg-none" type="button" data-bs-toggle="offcanvas" data-bs-target="#erp-sidebar" aria-controls="erp-sidebar">Menu</button>
        {% endif %}
        <a class="erp-brand" href="{% url 'home' %}">School ERP</a>
        {% if current_area == 'teacher' %}
        <nav class="erp-topbar-links d-none d-lg-flex" aria-label="Teaching">
            {% for tab in teacher_tabs %}<a href="{{ tab.url }}"{% if tab.active %} class="active" aria-current="page"{% endif %}>{{ tab.label }}</a>{% endfor %}
        </nav>
        {% endif %}
        <span class="erp-spacer"></span>
        {% if user.is_authenticated %}
            {% include "partials/_account_menu.html" %}
        {% else %}
            <a class="btn btn-outline-primary btn-sm" href="{% url 'login' %}">Log in</a>
        {% endif %}
    </header>
    {% if office_nav %}{% include "partials/_sidebar.html" %}{% endif %}
    <main id="main" class="erp-main">
        <div class="erp-content">
            {% block content %}{% endblock %}
        </div>
    </main>
    {% include "partials/_messages.html" %}
    {% if current_area == 'teacher' %}{% include "partials/_tabbar.html" with tabs=teacher_tabs tabbar_label="Teaching" %}{% endif %}
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
    <script src="{% static 'js/erp.js' %}" defer></script>
</body>
</html>
```

Note: the old `base.html` showed the guardian portal link and the teacher links in the top bar. Area links move to the account menu in Task 5; `test_role_aware_navigation_both_ways` (existing) depends on them, so run it after Task 5, not now.

- [ ] **Step 5: Run tests**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation -v 2`
Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add templates/base.html templates/partials core/tests/test_ui_foundation.py
git commit -m "feat(ui): staff shell with office sidebar/drawer and teacher tab bar"
```

---

### Task 5: Account menu with area switcher; guardian shell

**Files:**
- Fill: `templates/partials/_account_menu.html`
- Rewrite: `templates/portal/base.html`
- Rewrite: `core/templates/core/choose_area.html`
- Test: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Consumes: `user_areas` (list of `(key, label, url_name)`), `user_has_several_areas`, `current_area`, `request.resolver_match.url_name`; portal context `children` (list of dicts with `visible`, `student`, `grant`) and optional `grant`, `student`.
- Produces: `<details class="erp-account">` on every authenticated page (staff and portal); guardian tab bar labels "Home", "Overview", "Attendance", "Report cards".

- [ ] **Step 1: Add the import at the top of the test file**

```python
from core.tests.test_phase6_access_boundary import BoundaryFixture
```

(then `.\.venv\Scripts\ruff.exe check --fix core/tests/test_ui_foundation.py`)

- [ ] **Step 2: Append the failing tests**

```python
class AccountMenuTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_account_menu_lists_all_areas_and_marks_current(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertContains(page, 'class="erp-account"')
        self.assertContains(page, reverse("core:school-detail"))
        self.assertContains(page, 'aria-current="true"', count=1)
        self.assertContains(page, reverse("password_change"))

    def test_single_area_user_has_no_switch_heading(self):
        self.client.login(username="rao", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertNotContains(page, "Switch to")

    def test_choose_area_page_lists_areas(self):
        self.admin.groups.add(self.teachers)
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("choose-area"))
        self.assertContains(page, "School administration")
        self.assertContains(page, "My day (teaching)")


class GuardianShellTests(BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def portal_url(self, name):
        return reverse(name, args=[self.asha_grant.public_id])

    def test_portal_home_has_only_home_tab(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, 'class="erp-tabbar')
        self.assertNotContains(page, self.portal_url("portal:attendance"))

    def test_child_page_tabs_link_to_that_child(self):
        page = self.portal.get(self.portal_url("portal:child"))
        for name in ("portal:child", "portal:attendance", "portal:report-cards"):
            self.assertContains(page, self.portal_url(name))
        self.assertContains(page, "Report cards")

    def test_portal_pages_still_have_no_excluded_words(self):
        urls = [reverse("portal:home")] + [
            self.portal_url(name)
            for name in ("portal:child", "portal:attendance", "portal:report-cards")
        ]
        for url in urls:
            html = self.portal.get(url).content.decode().lower()
            for word in ("fee", "announcement", "pdf", "download"):
                self.assertNotIn(word, html, f"{word!r} found on {url}")
            self.assertNotIn(f"/students/{self.asha.pk}/", html)

    def test_portal_has_viewport_and_stylesheet(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, VIEWPORT)
        self.assertContains(page, "/static/css/erp.css")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation.AccountMenuTests core.tests.test_ui_foundation.GuardianShellTests -v 2`
Expected: FAIL — no `erp-account`, no portal tab bar, no stylesheet on portal pages.

- [ ] **Step 4: Fill `templates/partials/_account_menu.html`**

```html
{# Account menu: who is signed in, switch area, change password, log out. Works without JS. #}
<details class="erp-account">
    <summary aria-label="Account menu for {{ user.get_username }}">
        <span class="erp-avatar" aria-hidden="true">{{ user.get_username|slice:":1"|upper }}</span>
        <span class="d-none d-sm-inline">{{ user.get_username }}</span>
    </summary>
    <div class="erp-account-panel">
        {% if user_has_several_areas %}
        <p class="erp-nav-heading">Switch to</p>
        {% for key, label, url_name in user_areas %}
        <a href="{% url url_name %}"{% if key == current_area %} aria-current="true"{% endif %}>
            <span>{{ label }}</span>{% if key == current_area %}<span class="erp-check" aria-hidden="true">✓</span>{% endif %}
        </a>
        {% endfor %}
        <hr class="my-2">
        {% endif %}
        <a href="{% url 'password_change' %}">Change password</a>
        <form method="post" action="{% url 'logout' %}">
            {% csrf_token %}
            <button type="submit" class="erp-menu-item">Log out</button>
        </form>
    </div>
</details>
```

- [ ] **Step 5: Rewrite `templates/portal/base.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Guardian Portal{% endblock %} &middot; School ERP</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="{% static 'css/erp.css' %}" rel="stylesheet">
</head>
{% with here=request.resolver_match.url_name %}
<body class="erp has-tabbar">
    <a class="visually-hidden-focusable" href="#main">Skip to content</a>
    <header class="erp-topbar">
        <a class="erp-brand" href="{% url 'portal:home' %}">Guardian Portal</a>
        <span class="erp-spacer"></span>
        {% include "partials/_account_menu.html" %}
    </header>
    <main id="main" class="erp-main">
        <div class="erp-content">
            {% if children|length > 1 %}
            <nav class="erp-chips mb-3" aria-label="Your students">
                {% for item in children %}{% if item.visible %}
                <a href="{% url 'portal:child' item.grant.public_id %}"{% if student and item.student.pk == student.pk %} class="active" aria-current="page"{% endif %}>{{ item.student.full_name }}</a>
                {% endif %}{% endfor %}
            </nav>
            {% endif %}
            {% block content %}{% endblock %}
        </div>
    </main>
    {% include "partials/_messages.html" %}
    <nav class="erp-tabbar d-lg-none" aria-label="Guardian Portal">
        <ul>
            <li><a href="{% url 'portal:home' %}"{% if here == 'home' %} class="active" aria-current="page"{% endif %}>Home</a></li>
            {% if grant %}
            <li><a href="{% url 'portal:child' grant.public_id %}"{% if here == 'child' %} class="active" aria-current="page"{% endif %}>Overview</a></li>
            <li><a href="{% url 'portal:attendance' grant.public_id %}"{% if here == 'attendance' %} class="active" aria-current="page"{% endif %}>Attendance</a></li>
            <li><a href="{% url 'portal:report-cards' grant.public_id %}"{% if here == 'report-cards' or here == 'report-card' %} class="active" aria-current="page"{% endif %}>Report cards</a></li>
            {% endif %}
        </ul>
    </nav>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
    <script src="{% static 'js/erp.js' %}" defer></script>
</body>
{% endwith %}
</html>
```

The existing `test_switcher_shows_every_visible_child` grants a second child before checking links, so the chips (shown only with 2+ children) still satisfy it. The previous portal top bar showed only visible children too.

- [ ] **Step 6: Rewrite `core/templates/core/choose_area.html`**

```html
{% extends "base.html" %}
{% block title %}Choose where to go{% endblock %}
{% block content %}
<div class="erp-auth">
    <h1>Where would you like to go?</h1>
    <p class="text-secondary">Your login has more than one role. You can switch at any time from the account menu.</p>
    <div class="list-group">
        {% for key, label, url_name in areas %}
        <a class="list-group-item list-group-item-action py-3 d-flex justify-content-between align-items-center" href="{% url url_name %}">
            <span>{{ label }}</span><span aria-hidden="true">›</span>
        </a>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Run the new tests and the existing portal and teacher-home tests**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation core.tests.test_phase6_portal_shell core.tests.test_phase5_teacher_home -v 2`
Expected: all PASS (including the existing `test_role_aware_navigation_both_ways` and `test_no_database_ids_and_no_excluded_features`).

- [ ] **Step 8: Commit**

```powershell
git add templates/partials/_account_menu.html templates/portal/base.html core/templates/core/choose_area.html core/tests/test_ui_foundation.py
git commit -m "feat(ui): account menu with area switcher and guardian shell with tab bar"
```

---

### Task 6: Sign-in and change-password pages

**Files:**
- Rewrite: `templates/registration/login.html`, `templates/registration/password_change_form.html`
- Modify: `static/js/erp.js`
- Test: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Consumes: `LoginView` context `form` (`accounts.forms.ThrottledAuthenticationForm`, fields `username`, `password`; generic error text "The username or password is incorrect, or sign-in is temporarily unavailable.") and `next`; `accounts.views.PasswordChangeView` context `form` (Django `PasswordChangeForm`: `old_password`, `new_password1`, `new_password2`); `user.must_change_password`.
- Produces: `data-erp-toggle-password` buttons (start `hidden`, revealed by `erp.js`), each with `aria-controls` = the input id.

- [ ] **Step 1: Append the failing tests**

```python
class AuthPageTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def test_login_page_fields(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, ">Username</label>")
        self.assertContains(page, 'autocomplete="username"')
        self.assertContains(page, 'autocomplete="current-password"')
        self.assertContains(page, "data-erp-toggle-password")
        self.assertContains(page, "Ask the school office")

    def test_login_keeps_next(self):
        target = reverse("core:student-list")
        page = self.client.get(reverse("login") + f"?next={target}")
        self.assertContains(page, f'name="next" value="{target}"')
        response = self.client.post(
            reverse("login"),
            {"username": "admin", "password": "pass-12345", "next": target},
        )
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_login_error_is_shown_once(self):
        page = self.client.post(reverse("login"), {"username": "admin", "password": "wrong"})
        self.assertContains(page, "The username or password is incorrect", count=1)
        self.assertContains(page, 'role="alert"')

    def test_password_change_page(self):
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, 'autocomplete="current-password"', count=1)
        self.assertContains(page, 'autocomplete="new-password"', count=2)
        self.assertContains(page, "data-erp-toggle-password", count=3)

    def test_forced_change_notice(self):
        self.admin.must_change_password = True
        self.admin.save(update_fields=["must_change_password"])
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("password_change"))
        self.assertContains(page, "You must choose a new password before you continue.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation.AuthPageTests -v 2`
Expected: FAIL — label, autocomplete attributes and toggles missing.

- [ ] **Step 3: Rewrite `templates/registration/login.html`**

```html
{% extends "base.html" %}
{% block title %}Log in{% endblock %}
{% block content %}
<div class="erp-auth">
    <h1>Log in</h1>
    <p class="text-secondary">Use the username the school gave you.</p>
    {% if form.non_field_errors %}
    <div class="alert alert-danger" role="alert">{% for error in form.non_field_errors %}{{ error }}{% endfor %}</div>
    {% endif %}
    <form method="post" novalidate>
        {% csrf_token %}
        <div class="mb-3">
            <label class="form-label" for="{{ form.username.id_for_label }}">Username</label>
            <input type="text" class="form-control form-control-lg{% if form.username.errors %} is-invalid{% endif %}"
                   name="{{ form.username.html_name }}" id="{{ form.username.id_for_label }}"
                   value="{{ form.username.value|default_if_none:'' }}"
                   autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus>
            {% for error in form.username.errors %}<div class="text-danger small mt-1">{{ error }}</div>{% endfor %}
        </div>
        <div class="mb-4">
            <label class="form-label" for="{{ form.password.id_for_label }}">Password</label>
            <div class="erp-password">
                <input type="password" class="form-control form-control-lg{% if form.password.errors %} is-invalid{% endif %}"
                       name="{{ form.password.html_name }}" id="{{ form.password.id_for_label }}"
                       autocomplete="current-password" required>
                <button type="button" class="btn btn-link" data-erp-toggle-password aria-controls="{{ form.password.id_for_label }}" hidden>Show</button>
            </div>
            {% for error in form.password.errors %}<div class="text-danger small mt-1">{{ error }}</div>{% endfor %}
        </div>
        {% if next %}<input type="hidden" name="next" value="{{ next }}">{% endif %}
        <button type="submit" class="btn btn-primary btn-lg w-100">Log in</button>
    </form>
    <p class="small text-secondary mt-3 mb-0">Forgot your password? Ask the school office to reset it.</p>
</div>
{% endblock %}
```

- [ ] **Step 4: Rewrite `templates/registration/password_change_form.html`**

```html
{% extends "base.html" %}
{% block title %}Change password{% endblock %}
{% block content %}
<div class="erp-auth">
    <h1>Change your password</h1>
    {% if user.must_change_password %}
    <div class="alert alert-warning" role="alert">You must choose a new password before you continue.</div>
    {% else %}
    <p class="text-secondary">Choose a password you don't use anywhere else.</p>
    {% endif %}
    {% if form.non_field_errors %}
    <div class="alert alert-danger" role="alert">{% for error in form.non_field_errors %}{{ error }}{% endfor %}</div>
    {% endif %}
    <form method="post" novalidate>
        {% csrf_token %}
        {% for field in form %}
        <div class="mb-3">
            <label class="form-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
            <div class="erp-password">
                <input type="password" class="form-control{% if field.errors %} is-invalid{% endif %}"
                       name="{{ field.html_name }}" id="{{ field.id_for_label }}"
                       autocomplete="{% if field.name == 'old_password' %}current-password{% else %}new-password{% endif %}" required>
                <button type="button" class="btn btn-link" data-erp-toggle-password aria-controls="{{ field.id_for_label }}" hidden>Show</button>
            </div>
            {% for error in field.errors %}<div class="text-danger small mt-1">{{ error }}</div>{% endfor %}
            {% if field.help_text %}<div class="form-text">{{ field.help_text|safe }}</div>{% endif %}
        </div>
        {% endfor %}
        <button type="submit" class="btn btn-primary btn-lg w-100">Change password</button>
    </form>
    <form method="post" action="{% url 'logout' %}" class="mt-3">
        {% csrf_token %}
        <button type="submit" class="btn btn-link p-0">Log out instead</button>
    </form>
</div>
{% endblock %}
```

(`help_text` on `new_password1` is Django's own validator help HTML — no user input — hence `|safe`.)

- [ ] **Step 5: Add the password toggle to `static/js/erp.js`**

Replace the file with:

```javascript
// School ERP progressive enhancements. Every page works without this file.
(function () {
  "use strict";

  // Show/hide password: buttons start hidden so no-JS users never see a dead control.
  document.querySelectorAll("[data-erp-toggle-password]").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;
    button.hidden = false;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      button.textContent = showing ? "Show" : "Hide";
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      input.focus();
    });
  });
})();
```

- [ ] **Step 6: Run the auth tests and the existing sign-in/security tests**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation core.tests.test_phase6_security core.tests.test_phase6_guardian_accounts core.tests.test_authorization`
Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add templates/registration static/js/erp.js core/tests/test_ui_foundation.py
git commit -m "feat(ui): redesigned sign-in and change-password pages with show/hide"
```

---

### Task 7: Messages and empty-state components

**Files:**
- Rewrite: `templates/partials/_messages.html`
- Create: `templates/partials/_empty.html`
- Modify: `static/js/erp.js`
- Modify: `core/templates/core/my_home.html`, `templates/portal/home.html`
- Test: `core/tests/test_ui_foundation.py`

**Interfaces:**
- Consumes: Django `messages` (`message.level_tag` ∈ `debug|info|success|warning|error`).
- Produces: `{% include "partials/_empty.html" with title="…" text="…" %}` renders `.erp-empty` (`title` optional, `text` required). Messages render inside `<div class="erp-messages" role="status" aria-live="polite">`; only `success` and `info` carry `data-erp-autohide`.

- [ ] **Step 1: Add imports at the top of the test file**

```python
from django.contrib import messages as django_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
```

(then `.\.venv\Scripts\ruff.exe check --fix core/tests/test_ui_foundation.py`)

- [ ] **Step 2: Append the failing tests**

```python
class ComponentTests(Phase4Fixture, TestCase):
    def setUp(self):
        self.build_phase4()

    def render_messages(self, level, text):
        request = RequestFactory().get("/")
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        django_messages.add_message(request, level, text)
        context = {"messages": django_messages.get_messages(request)}
        return render_to_string("partials/_messages.html", context)

    def test_messages_live_region(self):
        html = self.render_messages(django_messages.SUCCESS, "Saved.")
        self.assertIn('role="status"', html)
        self.assertIn("alert-success", html)
        self.assertIn("data-erp-autohide", html)

    def test_error_message_uses_danger_and_stays(self):
        html = self.render_messages(django_messages.ERROR, "Could not save.")
        self.assertIn("alert-danger", html)
        self.assertNotIn("alert-error", html)
        self.assertNotIn("data-erp-autohide", html)

    def test_empty_partial(self):
        context = {"title": "Nothing yet", "text": "Add one."}
        html = render_to_string("partials/_empty.html", context)
        self.assertIn('class="erp-empty"', html)
        self.assertIn("Nothing yet", html)
        self.assertIn("Add one.", html)

    def test_teacher_without_duty_sees_empty_state(self):
        self.make_user("newteacher", self.teachers)
        self.client.login(username="newteacher", password="pass-12345")
        page = self.client.get(reverse("core:my-home"))
        self.assertContains(page, "You are not a class teacher today.")
        self.assertContains(page, 'class="erp-empty"')
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation.ComponentTests -v 2`
Expected: FAIL — no `role="status"`, `alert-info` used for everything, `_empty.html` missing.

- [ ] **Step 4: Write `templates/partials/_messages.html`**

```html
{% if messages %}
<div class="erp-messages" role="status" aria-live="polite">
    {% for message in messages %}
    <div class="alert alert-{% if message.level_tag == 'error' %}danger{% elif message.level_tag == 'debug' %}secondary{% else %}{{ message.level_tag }}{% endif %} alert-dismissible fade show"{% if message.level_tag == 'success' or message.level_tag == 'info' %} data-erp-autohide{% endif %}>
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Dismiss"></button>
    </div>
    {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 5: Write `templates/partials/_empty.html`**

```html
{# Empty state. Use: {% include "partials/_empty.html" with title="…" text="…" %} #}
<div class="erp-empty">
    <span class="erp-empty-icon" aria-hidden="true">○</span>
    {% if title %}<p class="erp-empty-title">{{ title }}</p>{% endif %}
    <p>{{ text }}</p>
</div>
```

- [ ] **Step 6: Use the empty state on My day and the portal home**

In `core/templates/core/my_home.html`, replace:

```html
{% else %}
<p>You are not a class teacher today.</p>
{% endif %}
```

with:

```html
{% else %}
{% include "partials/_empty.html" with text="You are not a class teacher today." %}
{% endif %}
```

In `templates/portal/home.html`, replace:

```html
{% else %}
<p>No students are linked to your account yet. Please contact the school office.</p>
{% endif %}
```

with:

```html
{% else %}
{% include "partials/_empty.html" with title="No students yet" text="No students are linked to your account yet. Please contact the school office." %}
{% endif %}
```

- [ ] **Step 7: Add message auto-hide to `static/js/erp.js`**

Inside the IIFE, after the password block and before the closing `})();`, add:

```javascript
  // Success and info messages close after 6 seconds; warnings and errors stay until dismissed.
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll("[data-erp-autohide]").forEach(function (alert) {
    window.setTimeout(function () {
      if (window.bootstrap && window.bootstrap.Alert && !reduceMotion) {
        window.bootstrap.Alert.getOrCreateInstance(alert).close();
      } else {
        alert.remove();
      }
    }, 6000);
  });
```

- [ ] **Step 8: Run tests**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation core.tests.test_phase5_teacher_home core.tests.test_phase6_portal_shell`
Expected: all PASS.

- [ ] **Step 9: Commit**

```powershell
git add templates/partials static/js/erp.js core/templates/core/my_home.html templates/portal/home.html core/tests/test_ui_foundation.py
git commit -m "feat(ui): live-region messages and empty-state component"
```

---

### Task 8: Full verification, manual check and docs

**Files:**
- Modify: `docs/UI_REFERENCES.md` (status line)

- [ ] **Step 1: Run the whole suite and ruff**

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\ruff.exe check .
```

Expected: every test passes (944 existing + the U1 tests); ruff reports no errors. If an existing test fails because it asserted old markup, change the template so the asserted text or link is present again. Edit an old test only if it asserted markup that this plan intentionally removed, and list each such change in the PR description.

- [ ] **Step 2: Check the production static build**

```powershell
$env:DJANGO_DEBUG = "False"
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
Remove-Item Env:DJANGO_DEBUG
```

Expected: "… static files copied … post-processed", including `css/erp.css` and `js/erp.js`.

- [ ] **Step 3: Manual check in the browser**

Start the server with demo data: set `$env:DJANGO_DEBUG = "True"`, run `manage.py seed_demo` if the database is empty, then `manage.py runserver`. Check at 360 px and 1280 px wide (browser device toolbar):

| User | Page | Expect |
|---|---|---|
| Not signed in | `/accounts/login/` | Centered card, "Username" label, Show/Hide works, no sidebar or tabs |
| Office admin | `/students/` | Sidebar at 1280 px; "Menu" button opens the drawer at 360 px; no page-wide horizontal scroll |
| Office admin | account menu | Username, Change password, Log out; "Switch to" only for multi-role users |
| Teacher | `/my/` | Tabs in the top bar at 1280 px, bottom tab bar at 360 px; empty state when not a class teacher |
| Guardian | `/guardian/` and a child page | Bottom tabs Home / Overview / Attendance / Report cards; child chips with 2+ children |
| Any | after changing password | Green message appears and closes after ~6 s; an error message stays |

- [ ] **Step 4: Update the docs status**

In `docs/UI_REFERENCES.md`, replace the first status line with:

```markdown
Status: 34 team picks recorded 2026-10-14. U1 Foundation implemented on branch `ui/u1-foundation`; U2–U7 pending (see roadmap).
```

- [ ] **Step 5: Commit, push and open the PR**

```powershell
git add docs/UI_REFERENCES.md
git commit -m "docs(ui): mark U1 foundation implemented"
git push -u origin ui/u1-foundation
gh pr create --base main --title "UI U1: foundation shell, navigation and auth pages" --body "Implements docs/superpowers/plans/2026-10-14-ui-u1-foundation.md. No behaviour, model or permission changes."
```
