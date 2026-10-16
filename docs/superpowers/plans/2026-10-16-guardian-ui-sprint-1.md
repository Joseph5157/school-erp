# Guardian UI Sprint 1 — Highest-Value Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five highest-value findings from the guardian re-test
(`docs/GUARDIAN_UI_UX_RETEST.md`, §11) so the guardian portal stops looking
"broken", gains persistent navigation, shows a parent-first home summary, and the
report card stops showing a blank Grade beside "Pass".

**Findings in scope:** **G-01** branded 403, **G-02** desktop guardian navigation
(+ **G-04** always-present Notices entry point), **G-05** blank Grade column,
**G-07** child-centred home dashboard (first slice), **G-10** accessible login
errors.

**Architecture:** Server-rendered Django, unchanged data model. All work is in the
guardian shell templates (`templates/portal/*`), the shared login template, two new
shared partials (`templates/portal/_portal_nav.html`, `templates/403.html`), small
read-only helpers in `core/portal.py`, `core/portal_views.py`, and existing tokens in
`static/css/erp.css`. No new models, no migrations, no write endpoints, no change to
authorization.

**Tech Stack:** Django 5.2, Bootstrap 5.3 (CDN), `static/css/erp.css` design tokens,
`django.test.TestCase`, existing Phase 6 fixtures.

**Spec / evidence:** `docs/GUARDIAN_UI_UX_RETEST.md` (§5 findings G-01, G-02, G-04,
G-05, G-07, G-10; §10 backlog; §11 sprint). Supporting ADRs:
`docs/adr/0014-phase-6-guardian-visible-information-and-result-publication.md`
(guardian-visible fields; report-card values come from the snapshot, never
recomputed).

## Global Constraints

- Branch `ui/guardian-sprint-1`, stacked on `main`. **Do not push or open a PR until
  the user asks.**
- No new models or migrations: `makemigrations --check --dry-run` must stay
  "No changes detected".
- The guardian portal stays **read-only**. Do not add anything that writes data.
- Authorization is untouched: `guardian_required`, `guardian_visible_grant` and the
  `403`/`404`/redirect behaviour stay exactly as they are. G-01 only changes the
  **presentation** of an existing 403, never its status code.
- Reuse existing CSS tokens and partials (`templates/partials/_empty.html` etc.); no
  new CSS framework or JS library. Do not remove the JS-free fallback of the mobile
  tab bar.
- Use `core.models.business_today()` for "today", never `date.today()`.
- Run tests with `.venv\Scripts\python.exe manage.py test <labels> --parallel 4`.
- One commit per task. The GateGuard hook blocks the first Bash/Edit/Write: state the
  requested facts in text, then retry the same call.

## Review Focus

1. **403 keeps its status and its safety.** A non-guardian still gets HTTP **403**
   (not a redirect, not 200); an anonymous visitor still gets the login redirect. Only
   the body changes (Task 2).
2. **Navigation never leaks.** The desktop nav is display-only. It links only to paths
   the guardian already reaches, and the "current child" is always one of the user's
   own visible grants (`nav_grant`), never a crafted id. A guardian with one child,
   zero children, or a child under access review must not crash (Task 3).
3. **Report card stays snapshot-only.** G-05 changes the *fallback text* for a blank
   grade label; it must not compute, infer or fetch a grade (Task 1).
4. **Login errors are announced and associated.** The empty-submit and generic-error
   states are programmatically linked to their field/alert and exposed to assistive
   tech (Task 4).
5. **Home dashboard is read-only and side-effect free.** No query that writes; no
   attendance/publication is created or finalised. Missing data renders an honest
   empty value, never a fake `0%` (Task 5).
6. **No regression to the mobile tab bar or to the `d-lg-none`/`d-none d-lg-flex`
   breakpoints** used by the admin shell (shared `erp.css`).

## File Structure

| File | Responsibility |
|---|---|
| `templates/portal/report_card.html` | G-05: Grade cell fallback text |
| `templates/403.html` (new) | G-01: branded "no guardian access" page |
| `templates/portal/_portal_nav.html` (new) | G-02/G-04: one nav list reused by the desktop header nav and the mobile tab bar |
| `templates/portal/base.html` | G-02/G-04: render desktop nav; use `nav_grant` for stable child tabs |
| `core/portal_views.py` | G-02/G-04: `_context` supplies `nav_grant`; G-07: home passes `summaries` |
| `core/portal.py` | G-07: `child_summary(student)` read-only helper |
| `templates/portal/home.html` | G-07: child-centred dashboard cards |
| `static/css/erp.css` | `erp-portal-nav`, `erp-child-card` styles; desktop nav visibility |
| `templates/registration/login.html` | G-10: `aria-invalid`, `aria-describedby`, alert `role`/ids |
| `core/tests/test_ui_guardian_sprint1.py` (new) | All Sprint 1 tests |

Existing portal templates live in `templates/portal/`; shared partials in
`templates/partials/`. Verify paths with `ls` before creating files.

---

### Task 1: G-05 — "Not graded" instead of a blank Grade cell in the guardian report card

**Files:**
- Modify: `templates/portal/report_card.html:15`
- Test: `core/tests/test_ui_guardian_sprint1.py`

**Interfaces:** Produces the display string `Not graded` (exact) for a blank
`grade_label`, matching the admin F16 fix. Does not change any data.

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import TestCase


class ReportCardGradeFallbackTests(TestCase):
    def render(self, grade_label, pass_fail_label="Pass"):
        entry = SimpleNamespace(
            subject_label="Science", assessment_label="Unit Test 1",
            assessment_date=None, status="MARKED", score=29, maximum_marks=50,
            percentage=58, grade_label=grade_label, pass_fail_label=pass_fail_label,
        )
        pub = SimpleNamespace(
            term_label="Term 1", academic_year_label="2026-27",
            class_grade_label="Grade 6", section_label="A", public_id="p",
            is_partial=False, remark_text="",
        )
        student = SimpleNamespace(full_name="Anusha Rao")
        grant = SimpleNamespace(public_id="g")
        return render_to_string(
            "portal/report_card.html",
            {"entries": [entry], "pub": pub, "student": student, "grant": grant,
             "children": [], "user": SimpleNamespace(get_username=lambda: "g")},
        )

    def test_blank_grade_shows_not_graded(self):
        self.assertIn("Not graded", self.render(""))
        self.assertIn("Pass", self.render(""))

    def test_real_grade_is_shown_not_placeholder(self):
        html = self.render("B1")
        self.assertIn(">B1<", html)
        self.assertNotIn("Not graded", html)
```

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_guardian_sprint1.ReportCardGradeFallbackTests`
Expected: FAIL on `test_blank_grade_shows_not_graded`.

- [ ] **Step 3: Implement**

`templates/portal/report_card.html:15`, change only the Grade cell:

```django
            <td>{{ e.grade_label|default:"Not graded" }}</td>
```

Do **not** touch `pass_fail_label`, the Marks/`%` cells, or the "no totals" note.

- [ ] **Step 4: Run** the two tests plus
  `core.tests.test_phase6_publication core.tests.test_phase7_documents` → PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/portal/report_card.html core/tests/test_ui_guardian_sprint1.py
git commit -m "fix(guardian): show 'Not graded' for a blank grade on the portal report card (G-05)"
```

---

### Task 2: G-01 — Branded, explained 403 page

**Files:**
- Create: `templates/403.html`
- Test: `core/tests/test_ui_guardian_sprint1.py`

**Interfaces:** Consumes Django's default `permission_denied` handler, which renders
`403.html` with a `RequestContext` (context processors run). Produces a page whose
`<h1>` states the visitor has no guardian access and that links back to a safe place.
**Status code stays 403.**

- [ ] **Step 1: Write the failing tests**

```python
from django.test import TestCase
from django.urls import reverse

from core.tests.test_phase6_access_boundary import BoundaryFixture


class ForbiddenPageTests(BoundaryFixture, TestCase):
    # BoundaryFixture.setUp already logs self.client in as the administrator.

    def test_non_guardian_gets_403_with_branded_body(self):
        response = self.client.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'id="forbidden-title"', status_code=403)
        self.assertContains(response, reverse("login"), status_code=403)

    def test_anonymous_still_redirects_not_403(self):
        anonymous = self.client_class()
        response = anonymous.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
```

> Assert on stable hooks from `403.html` (`id="forbidden-title"`), not on incidental
> wording. Run with `DEBUG=False` (the test runner default) so Django uses
> `templates/403.html` rather than its technical 403 page.

- [ ] **Step 2: Run and confirm failure**
  Expected: the assertion for the branded body FAILS (page is the bare Django 403).

- [ ] **Step 3: Implement `templates/403.html`**

```django
{% extends "base.html" %}
{% block title %}Access denied{% endblock %}
{% block content %}
<div class="erp-auth">
    <h1 id="forbidden-title">You don't have guardian access</h1>
    <p class="text-secondary">
        This page belongs to the Guardian Portal. The signed-in account is not linked
        to a student, so no student information can be shown here.
    </p>
    <p>
        If you are a parent or guardian, sign in with the username the school gave you.
        Otherwise return to your own area.
    </p>
    <p class="mb-0">
        <a class="btn btn-primary" href="{% url 'login' %}">Go to the sign-in page</a>
        <a class="btn btn-outline-secondary" href="{% url 'home' %}">Go to my area</a>
    </p>
</div>
{% endblock %}
```

`base.html` shows the office sidebar only when `office_nav` is non-empty; for a
`portal:` URL `current_area` returns `"guardian"`, so the 403 renders as a clean,
uncluttered page. Confirm this holds for the admin-hits-guardian case (Review Focus 1).

- [ ] **Step 4: Run** `core.tests.test_ui_guardian_sprint1.ForbiddenPageTests` and
  `core.tests.test_phase6_access_boundary core.tests.test_phase6_security` → PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/403.html core/tests/test_ui_guardian_sprint1.py
git commit -m "feat(guardian): branded 403 page instead of the bare Forbidden response (G-01)"
```

---

### Task 3: G-02 + G-04 — Persistent guardian navigation (desktop + stable tab bar)

**Files:**
- Create: `templates/portal/_portal_nav.html`
- Modify: `templates/portal/base.html`, `core/portal_views.py` (`_context`), `static/css/erp.css`
- Test: `core/tests/test_ui_guardian_sprint1.py`

**Interfaces:**
- Produces: `nav_grant` in the portal template context — the current child's grant,
  equal to `grant` when set, otherwise the first **visible** child's grant, otherwise
  `None`.
- Produces: `templates/portal/_portal_nav.html`, rendered twice (desktop nav in the
  header, mobile tab bar) so the two can never drift.

- [ ] **Step 1: Write the failing tests**

```python
from django.urls import reverse
from django.test import TestCase

from core.tests.test_phase6_portal_shell import PortalFixture


class PortalNavTests(PortalFixture, TestCase):
    def test_desktop_nav_present_on_home_with_notices_and_child_links(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, 'class="erp-portal-nav"')
        self.assertContains(page, reverse("portal:notices"))
        self.assertContains(page, reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))
        self.assertContains(page, reverse("portal:report-cards", args=[self.asha_grant.public_id]))

    def test_tabbar_is_stable_on_notices_page(self):
        page = self.portal.get(reverse("portal:notices"))
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))

    def test_child_tabs_point_at_the_current_child_on_child_page(self):
        page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(
            page, reverse("portal:attendance", args=[self.asha_grant.public_id])
        )
```

- [ ] **Step 2: Run and confirm failure**
  Expected: `erp-portal-nav` not found; notices page tab bar lacks the Attendance link.

- [ ] **Step 3: Implement**

`core/portal_views.py` — support a stable current child in one place:

```python
def _context(request, **extra):
    children = portal_children(request.user)
    grant = extra.get("grant")
    if grant is None:
        grant = next((item["grant"] for item in children if item["visible"]), None)
    return {"children": children, "nav_grant": grant, **extra}
```

`templates/portal/_portal_nav.html` (single source of truth for both navs):

```django
<nav class="{{ nav_class }}" aria-label="Guardian Portal">
    <ul>
        <li><a href="{% url 'portal:home' %}"{% if here == 'home' %} class="active" aria-current="page"{% endif %}>Home</a></li>
        <li><a href="{% url 'portal:notices' %}"{% if here == 'notices' or here == 'notice' %} class="active" aria-current="page"{% endif %}>Notices</a></li>
        {% if nav_grant %}
        <li><a href="{% url 'portal:child' nav_grant.public_id %}"{% if here == 'child' %} class="active" aria-current="page"{% endif %}>Overview</a></li>
        <li><a href="{% url 'portal:attendance' nav_grant.public_id %}"{% if here == 'attendance' %} class="active" aria-current="page"{% endif %}>Attendance</a></li>
        <li><a href="{% url 'portal:report-cards' nav_grant.public_id %}"{% if here == 'report-cards' or here == 'report-card' %} class="active" aria-current="page"{% endif %}>Report cards</a></li>
        {% endif %}
    </ul>
</nav>
```

`templates/portal/base.html` — replace the inline tab bar with the partial, and add a
desktop nav in the topbar. The `here` variable from `{% with here=request.resolver_match.url_name %}`
is already in scope:

```django
    <header class="erp-topbar">
        <a class="erp-brand" href="{% url 'portal:home' %}">Guardian Portal</a>
        {% include "portal/_portal_nav.html" with nav_class="erp-portal-nav d-none d-lg-flex" %}
        <span class="erp-spacer"></span>
        {% include "partials/_account_menu.html" %}
    </header>
    ...
    {% include "portal/_portal_nav.html" with nav_class="erp-tabbar d-lg-none" %}
```

Do **not** use `only`: `here` (from the surrounding `{% with %}`) and `nav_grant` must
stay visible to the partial. Use `ls templates/partials` to confirm `_account_menu.html`
lives there.

`static/css/erp.css` (append; confirm token names with `grep -n "^  --erp-" static/css/erp.css`):

```css
.erp-portal-nav { min-width: 0; overflow-x: auto; }
.erp-portal-nav ul { display: flex; gap: var(--erp-space-4); margin: 0; padding: 0; list-style: none; }
.erp-portal-nav a { color: var(--erp-ink-soft); text-decoration: none; padding: .5rem .25rem; white-space: nowrap; }
.erp-portal-nav a.active { color: var(--erp-accent); font-weight: 600; box-shadow: inset 0 -2px 0 var(--erp-accent); }
```

Do **not** alter the existing `.erp-tabbar` rules; the mobile tab bar keeps its look.

- [ ] **Step 4: Run** `PortalNavTests` plus
  `core.tests.test_phase6_portal_shell` → PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/portal/_portal_nav.html templates/portal/base.html core/portal_views.py static/css/erp.css core/tests/test_ui_guardian_sprint1.py
git commit -m "feat(guardian): persistent desktop nav and stable tab bar; always-present Notices link (G-02, G-04)"
```

---

### Task 4: G-10 — Accessible login errors

**Files:**
- Modify: `templates/registration/login.html`
- Test: `core/tests/test_ui_guardian_sprint1.py`

**Interfaces:** Produces `aria-invalid` / `aria-describedby` on the username and
password inputs when they have errors, an `id` on each error element, and
`role="alert"` on the non-field-error alert. No view/JS change; the existing
server-rendered errors are enough.

- [ ] **Step 1: Write the failing test**

```python
from django.test import TestCase
from django.urls import reverse


class LoginErrorA11yTests(TestCase):
    def test_empty_submit_associates_errors_with_fields(self):
        response = self.client.post(reverse("login"), {"username": "", "password": ""})
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_username_error"')
        self.assertContains(response, 'id="id_username_error"')

    def test_generic_failure_alert_is_announced(self):
        response = self.client.post(
            reverse("login"), {"username": "nobody", "password": "wrong"}
        )
        self.assertContains(response, 'role="alert"')
```

- [ ] **Step 2: Run and confirm failure** (attributes absent).

- [ ] **Step 3: Implement `templates/registration/login.html`**

- Non-field alert: give it `id="login-error"`.
- Username input: add `{% if form.username.errors %} aria-invalid="true" aria-describedby="id_username_error"{% endif %}` and give the error loop `<div class="text-danger small mt-1" id="id_username_error" role="alert">`.
- Password input: same pattern with `id_password_error`.
- Keep the existing `required`, `autocomplete`, `autocapitalize`, `spellcheck` and the
  `data-erp-toggle-password` button untouched.

- [ ] **Step 4: Run** `LoginErrorA11yTests` plus `core.tests.test_ui_foundation` → PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/registration/login.html core/tests/test_ui_guardian_sprint1.py
git commit -m "fix(a11y): associate and announce login validation errors (G-10)"
```

---

### Task 5: G-07 — Child-centred home dashboard (first slice)

**Files:**
- Modify: `core/portal.py` (add `child_summary`), `core/portal_views.py` (`home`), `templates/portal/home.html`, `static/css/erp.css`
- Test: `core/tests/test_ui_guardian_sprint1.py`

**Interfaces:**
- Produces: `core.portal.child_summary(student)` → dict with
  `name`, `placement` (or `None`), `status`,
  `attendance` (`{"present","total","percentage"}` or `None`),
  `latest_report_card` (`TermPublication | None`).
- Consumes: existing `student_profile`, `attendance_years`, `submitted_attendance`,
  `visible_publications`, `business_today()`.
- The home view builds `summaries = [child_summary(student) for each visible child]`.

- [ ] **Step 1: Write the failing tests**

```python
from django.urls import reverse
from django.test import TestCase

from core.portal import child_summary
from core.tests.test_phase6_portal_shell import PortalFixture


class HomeDashboardTests(PortalFixture, TestCase):
    def summaries(self):
        page = self.portal.get(reverse("portal:home"))
        return page.context["summaries"]

    def test_one_summary_per_visible_child_with_placement(self):
        rows = self.summaries()
        self.assertEqual([r["name"] for r in rows], ["Asha Rao"])
        self.assertEqual(rows[0]["placement"]["class_grade"], self.asha_e.class_grade.name)

    def test_attendance_is_none_when_nothing_recorded(self):
        self.assertIsNone(self.summaries()[0]["attendance"])

    def test_dashboard_card_renders_and_links_to_attendance(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, "erp-child-card")
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))

    def test_hidden_child_is_not_summarised(self):
        # ravi is related but not granted: must not appear.
        self.assertEqual([r["name"] for r in self.summaries()], ["Asha Rao"])
```

For a populated-attendance assertion, extend the existing attendance fixture used by
`core/tests/test_phase6_portal_attendance.py` (reuse its helper to submit a register);
assert the card then shows `X%`.

- [ ] **Step 2: Run and confirm failure** (`summaries` missing / `erp-child-card` absent).

- [ ] **Step 3: Implement `core/portal.py`**

```python
def child_summary(student):
    """Read-only dashboard summary for one visible child (G-07).

    Never computes or fetches a grade; report cards come from the existing
    published snapshot via visible_publications.
    """
    years = attendance_years(student)
    attendance = None
    if years:
        attendance = submitted_attendance(student, years[0])["summary"]
    profile = student_profile(student)
    cards = visible_publications(student)
    return {
        "name": student.full_name,
        "placement": profile["placement"],
        "status": profile["status"],
        "attendance": attendance,
        "latest_report_card": cards[0] if cards else None,
    }
```

`core/portal_views.py` — `home` (the view attaches the grant, so `child_summary` stays
unaware of access control):

```python
@require_safe
@guardian_required
def home(request):
    children = portal_children(request.user)
    summaries = [
        {**child_summary(item["student"]), "grant": item["grant"]}
        for item in children
        if item["visible"]
    ]
    return render(
        request,
        "portal/home.html",
        _context(request, children=children,
                 notices=visible_announcements(request.user)[:3], summaries=summaries),
    )
```

(Keep `portal_children`/`visible_announcements`; import `child_summary` from `core.portal`.)

`templates/portal/home.html` — replace the plain list with cards, keeping the
empty-state for a guardian with no children:

```django
{% if summaries %}
<div class="erp-child-grid">
    {% for s in summaries %}
    <article class="erp-child-card">
        <h2 class="erp-child-name">{{ s.name }}</h2>
        {% if s.placement %}
        <p class="text-muted mb-1">{{ s.placement.academic_year }} · {{ s.placement.class_grade }}-{{ s.placement.section }} · {{ s.status }}</p>
        {% else %}
        <p class="text-muted mb-1">No current placement · {{ s.status }}</p>
        {% endif %}
        {% if s.attendance %}
        <p class="mb-1"><strong>{{ s.attendance.percentage }}%</strong> attendance ({{ s.attendance.present }} of {{ s.attendance.total }} recorded days)</p>
        {% else %}
        <p class="text-muted mb-1">No attendance recorded yet</p>
        {% endif %}
        <p class="mb-2">
            {% if s.latest_report_card %}<a href="{% url 'portal:report-card' s.grant.public_id s.latest_report_card.public_id %}">Latest report card: {{ s.latest_report_card.term_label }}</a>{% else %}<span class="text-muted">No report cards published yet</span>{% endif %}
        </p>
        <a class="btn btn-outline-primary btn-sm" href="{% url 'portal:child' s.grant.public_id %}">Open {{ s.name }}<span class="visually-hidden"> overview</span></a>
    </article>
    {% endfor %}
</div>
{% else %}
{% include "partials/_empty.html" with title="No students yet" text="No students are linked to your account yet. Please contact the school office." %}
{% endif %}
{% if notices %}
<h2 class="h5 mt-4">Latest notices</h2>
<div class="list-group mb-2" style="max-width: 32rem">
    {% for notice in notices %}
    <a class="list-group-item list-group-item-action" href="{% url 'portal:notice' notice.public_id %}">{{ notice.title }} <span class="text-muted small">· {{ notice.published_at|date:"j M" }}</span></a>
    {% endfor %}
</div>
<p class="mb-4"><a href="{% url 'portal:notices' %}">All notices</a></p>
{% endif %}
```

> The report-card link uses the grant `public_id` attached by the view
> (`s.grant.public_id`) and the publication's `public_id`. Verify `TermPublication`
> exposes `public_id` and `term_label` against `core/models.py` before writing the
> link, and confirm the `{% url %}` names (`portal:report-card`, `portal:child`).

`static/css/erp.css`:

```css
.erp-child-grid { display: grid; gap: var(--erp-space-4); grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); margin-bottom: var(--erp-space-4); }
.erp-child-card { background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius); padding: var(--erp-space-4); }
.erp-child-name { font-size: 1.1rem; margin: 0 0 .25rem; }
```

- [ ] **Step 4: Run** `HomeDashboardTests` plus
  `core.tests.test_phase6_portal_shell core.tests.test_phase6_portal_attendance
  core.tests.test_phase6_publication` → PASS.

- [ ] **Step 5: Commit**

```bash
git add core/portal.py core/portal_views.py templates/portal/home.html static/css/erp.css core/tests/test_ui_guardian_sprint1.py
git commit -m "feat(guardian): child-centred home dashboard with attendance and latest report card (G-07)"
```

---

### Task 6: Verification, responsive check, docs

**Files:**
- Modify: `docs/UI_REFERENCES.md`, this plan (completion notes)

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python.exe manage.py test --parallel 4`
Expected: PASS (the pre-existing date-dependent attendance failure, if any, is the
only allowed failure — confirm it also fails on `main`).

- [ ] **Step 2: Static checks**

Run: `.venv\Scripts\python.exe -m ruff check core accounts`,
`.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, `git diff --check`.
Expected: clean / "No changes detected".

- [ ] **Step 3: Browser smoke (Playwright) — local isolated server, throwaway SQLite**

Against a locally seeded guardian (`seed_demo` plus one guardian account), at widths
**320, 375, 768, 1440** check:

- `/guardian/` as the guardian: desktop nav visible ≥992px, tab bar <992px, both with
  an active item; no horizontal document overflow on home/child/attendance/report-card.
- `/guardian/` as a non-guardian login: **branded 403**, status still 403; anonymous →
  login redirect.
- Report card on 375px: a blank-grade row reads "Not graded".
- Login empty submit: error text present with `aria-describedby`.
- Home: one card per visible child showing a % or "No attendance recorded yet", and a
  working report-card / attendance link.
- Re-run the same checks on **staging** (https://school-erp-web-staging.up.railway.app)
  once the branch is deployed, and update the screenshots in `docs/guardian-retest/`.

- [ ] **Step 4: Fix anything found; test-first where it is a regression.**

- [ ] **Step 5: Record results**

Append a "Completion notes" section to this plan (tests run, counts, deviations from
the plan) and a short "Guardian UI Sprint 1" entry in `docs/UI_REFERENCES.md`.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs: record Guardian UI Sprint 1 verification"
```

Do not push or open a PR until the user asks.

---

## Self-Review

- **Spec coverage:** G-01→Task 2, G-02→Task 3, G-04→Task 3, G-05→Task 1,
  G-07→Task 5, G-10→Task 4. The remaining backlog items (G-03 stable tab set is partly
  addressed by Task 3; G-06/G-08/G-09/G-11/G-12/G-13/G-17) are **out of scope** for
  Sprint 1 by design — they are listed in `docs/GUARDIAN_UI_UX_RETEST.md` §10.
- **Placeholder scan:** no TBD/TODO. Open verification points are called out inline
  (`only` and the `here` variable; exact `TermPublication` field names; reuse of the
  attendance fixture) with the command to resolve them.
- **Type/name consistency:** `nav_grant`, `child_summary`, `summaries`,
  `erp-child-card`, `erp-portal-nav`, `id_username_error`/`id_password_error` and the
  URL names (`portal:home|notices|child|attendance|report-cards|report-card`) are used
  identically across tasks.
- **Safety:** no model/migration, no write path, no authorization change; the 403 keeps
  its status; the report card stays snapshot-only.

## Completion notes

Verified 2026-10-16 on branch `ui/guardian-sprint-1` (5 feature/fix commits + 1 test
commit).

**Automated**
- New suite `core.tests.test_ui_guardian_sprint1`: 13 tests, all pass.
- Focused suites alongside each task: `test_phase6_portal_shell`,
  `test_phase6_portal_attendance`, `test_phase6_publication`, `test_phase6_access_boundary`,
  `test_phase6_security`, `test_phase7_documents`, `test_ui_foundation` — all pass.
- Full suite `manage.py test --parallel 4`: **1461 tests, 1 failure** — the
  pre-existing, date-dependent `test_models.AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates`
  (asserts `<= 2026-10-10`; today is 2026-10-16). It is unrelated to the guardian UI
  and fails on `main` too.
- `ruff check core accounts`: clean. `makemigrations --check --dry-run`: "No changes
  detected". `git diff --check`: clean.

**Browser smoke (Playwright, local render of the real templates + `erp.css`, synthetic data — no records or server)**
- 320/375/768/1440: **no horizontal document overflow** on home, report card or 403.
- Desktop nav (`erp-portal-nav d-none d-lg-flex`) **visible only at 1440**; mobile tab
  bar (`erp-tabbar d-lg-none`) **visible at 320/375/768** — both list the same five
  links (Home, Notices, Overview, Attendance, Report cards).
- Home shows one `.erp-child-card` per visible child, with an 80% attendance line on
  one child and "No attendance recorded yet" on the other (honest empty state).
- Report card Grade column reads `Not graded` for a blank grade and `A2` for a real
  one; the 7-column table still scrolls inside its own box on phones.
- 403 renders a branded "You don't have guardian access" card with links to sign-in and
  the account's own area.

**Deviations from the plan**
- `core/portal.py` implements a **batched** `child_summaries(children)` instead of the
  per-child `child_summary` sketched in Task 5. The pre-existing
  `test_phase6_portal_shell.PortalHomeTests.test_query_count_constant` requires the home
  page's query count not to grow with the number of children, so placements, attendance
  counts and latest publications are fetched in bulk. Report cards still come from the
  published snapshot (`publication.guardian_visible`), never recomputed.
- `core/tests/test_ui_foundation.py::GuardianShellTests.test_portal_home_has_only_home_tab`
  encoded the old inconsistent tab bar (G-03) and was renamed/updated to expect the
  stable tab bar.
- The 403's `base.html` shell shows the account's own top bar; the synthetic render
  showed a signed-out top bar because the fake user was anonymous in that render only.

**Still open / not done here**
- The remaining re-test backlog (G-06, G-08, G-09, G-11, G-12, G-13, G-17) is deferred
  and listed in `docs/GUARDIAN_UI_UX_RETEST.md` §10.
- **Re-check on live staging is pending deployment** of this branch; the smoke above is a
  local render, not the deployed app.

## Pre-staging review follow-up (Draft PR #64)

Addressed the review findings without rewriting existing commits.

**H1 — denial-neutral 403.** `templates/403.html` is rendered for administrator,
teacher and guardian `PermissionDenied` responses, so the old guardian-specific copy
("You don't have guardian access" / "not linked to a student") was wrong for a guardian
or teacher refused an administrator page. The heading is now "You don't have access to
this page" with neutral body copy. Status stays 403, branding and both recovery links
stay, and no role/student/permission detail is revealed. Tests: admin→`/guardian/`,
guardian→`core:admin-overview`, neutral heading, no student name, no misleading wording,
anonymous redirect, anonymous actions render.

**M1 — dashboard publication lookup is genuinely constant-query.** Root cause:
`child_summaries` called `publication.guardian_visible(card)` per published card, and
`guardian_visible` recomputed `live_fingerprint` (one query per card). The pre-existing
`test_query_count_constant` never gave children published cards, so it could not catch
this. New `publication.guardian_visible_many(publications)` fetches entries, live results
and remarks in bulk (constant queries) and applies the identical fingerprint comparison;
`child_summaries` and `visible_publications` both use it. Safety rules unchanged:
PUBLISHED-only, released entries only, no grade recomputation, stale/missing/unpublished
still hidden. Measured home-page query count with published cards: **before** 30 (one
child) → 32 (three children); **after** 31 → 31 (constant). Regression test
`DashboardPublicationQueryTests.test_query_count_constant_with_published_cards` fails on
the old code.

**M3 — behaviour-level tests strengthened.** Zero-child portal renders no child-scoped
URLs; multi-child nav defaults to the first visible child; exactly the correct link
carries `aria-current="page"`; pending-review grants are excluded from dashboard and nav;
the attendance card shows the measured numerator, denominator and percentage; the latest
report-card link and label are asserted; empty dashboard states stay honest; login errors
expose `aria-invalid`/`aria-describedby` with existing targets and the live region carries
the error text; the 403 contains no student name; the Grade cell shows "Not graded" when
blank and "A2" when real.

**M2 — temporary decision (not changed here):**

> On global Home and Notices pages, child-scoped navigation currently defaults
> deterministically to the first visible child. The selected child is not yet preserved
> across global pages. A dedicated multi-child context-selector improvement is deferred.

**Deferred findings (unchanged, listed in `docs/GUARDIAN_UI_UX_RETEST.md` §10):**
G-06, G-08, G-09, G-11, G-12, G-13, G-17.

### Deferred Low findings from the final review (recorded, not implemented)

- **Brittle markup-specific assertions** — some Sprint 1 tests match exact HTML
  fragments or `aria-current` counts (e.g. `test_home_marks_only_home_active`, the
  attendance-line assertion), so a shell/markup change can fail them without a
  behaviour regression. Prefer per-link and context-value assertions.
- **Broader batch parity / isolation test coverage** — add a data-driven test
  comparing `guardian_visible_many` with `guardian_visible` across non-PUBLISHED
  mixes, duplicate publication objects and mixed terms, plus an explicit
  cross-publication isolation case. Isolation is currently guaranteed
  structurally and only covered indirectly.
- **Repeated `portal_children` queries** — the home page calls `portal_children`
  three times (view + `_context` + `visible_announcements`). Pre-existing and
  constant with respect to child count; compute once and pass it through.
- **Document the FINALIZED assessment assumption** — the constant-query claim of
  `guardian_visible_many` assumes every released result's assessment stays
  FINALIZED, so `entry_values`/`grade_for` never reaches `applicable_scale()`.
  Add a code comment stating the assumption.
- **Inaccessible / untracked audit evidence references** — the plan and PR cite
  `docs/GUARDIAN_UI_UX_RETEST.md` and `docs/guardian-retest/`, which are not
  tracked. Commit them, or drop the references.

