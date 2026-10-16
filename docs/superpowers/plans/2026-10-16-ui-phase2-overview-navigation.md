# UI Phase 2: Admin Overview and Section-Aware Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give admins a landing Overview page of work queues (F04) and add breadcrumbs plus section-aware sidebar highlighting on deep pages (F05).

**Architecture:** A new read-only `admin_overview` view renders cards produced by small functions in `core/dashboard.py`, each reusing the data source of the existing list page. Breadcrumbs and the active sidebar section come from one declarative map in `core/breadcrumbs.py`, exposed by the existing `roles` context processor and rendered once in `base.html`, so individual pages need no edits. No models, no migration.

**Tech Stack:** Django, Bootstrap 5.3 (CDN), `static/css/erp.css` tokens from Phase 1, Django `TestCase`.

**Spec:** `docs/superpowers/specs/2026-10-16-ui-phase2-overview-navigation-design.md`

## Global Constraints

- Branch `ui/audit-phase2-overview-navigation` (stacked on Phase 1, PR #55). Do not push or open a PR until asked.
- Run tests with `.venv\Scripts\python.exe manage.py test <labels> --parallel 4`. One date-dependent attendance test already fails on `main`; ignore only that one.
- No new models or migrations: `makemigrations --check` must stay clean.
- Navigation is display-only; views keep enforcing permissions (`administrator_required`).
- Use existing CSS tokens (`--erp-*`) and partials (`_page_header.html`, `_status_badge.html`, `_empty.html`); no new CSS framework or JS.
- Teacher (`my-home`) and guardian (`portal:home`) landings and `choose-area` are unchanged.
- Use `core.models.business_today()` for "today", never `date.today()`.
- GateGuard hooks block the first Bash command, first Edit of a file and first Write of a new file: state the requested facts in text, then retry the same call.

## Review Focus

1. User with `core.view_school` but none of the four source permissions → Overview renders with no cards and a clear "Nothing to show for your role" message (test in Task 2).
2. Brand-new school with no academic year/sections/enrollments → Overview renders the "Set up your school" state, no 500 (Task 2).
3. Admin who is also a teacher → `/` still goes to `choose-area`; the admin area's landing is `core:admin-overview` (Task 1).
4. Deep page not in the breadcrumb map (e.g. a future URL) → no breadcrumb, exact-match highlighting only, no crash (Task 3).
5. Breadcrumb parent that needs the current object (`student-detail` from `student-deactivate-confirm`) resolves with the same `pk`; a mapped page whose kwargs don't fit degrades to no breadcrumb rather than raising `NoReverseMatch` (Task 3).

## File Structure

| File | Responsibility |
|---|---|
| `core/dashboard.py` (new) | One function per queue card + `overview_cards(user)`; no HTTP |
| `core/breadcrumbs.py` (new) | URL-name → section + trail map; `breadcrumb_context(match)` |
| `core/views.py` | `admin_overview` view |
| `core/urls.py` | `overview/` route |
| `core/authorization.py:302` | Admin landing URL → `core:admin-overview` |
| `core/navigation.py` | "Home → Overview" sidebar group; section-aware `_link` |
| `core/context_processors.py` | Expose `breadcrumbs`, pass section to `office_nav` |
| `core/templates/core/admin_overview.html` (new) | Overview page |
| `templates/partials/_queue_card.html` (new) | One card |
| `templates/partials/_breadcrumbs.html` (new) | Breadcrumb `<nav>` |
| `templates/base.html` | Include breadcrumbs above content |
| `static/css/erp.css` | Card grid + breadcrumb styles |
| `core/tests/test_ui_admin_phase2.py` (new) | All Phase 2 tests |

Existing page templates live in `core/templates/core/`; shared partials in `templates/partials/` (verify with `ls` before creating files).

---

### Task 1: Overview route, landing redirect, sidebar link

**Files:**
- Modify: `core/views.py` (add view after `choose_area`), `core/urls.py`, `core/authorization.py:302`, `core/navigation.py` (`OFFICE_NAV`)
- Create: `core/templates/core/admin_overview.html`
- Test: `core/tests/test_ui_admin_phase2.py`
- Fix: existing tests that assert the old landing (Step 5)

**Interfaces:**
- Produces: URL name `core:admin-overview` (path `overview/`); view `admin_overview(request)` rendering `core/admin_overview.html` with context `cards` (empty for now) and `needs_setup` (False for now).

- [ ] **Step 1: Write the failing tests**

```python
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.authorization import user_areas
from core.tests.test_authorization import AuthorizationClientsMixin


class OverviewLandingTests(AuthorizationClientsMixin, TestCase):
    def test_admin_home_redirects_to_overview(self):
        response = self.administrator.get(reverse("home"))
        self.assertRedirects(
            response, reverse("core:admin-overview"), fetch_redirect_response=False
        )

    def test_overview_renders_for_admin_with_sidebar_link(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:admin-overview"))
        self.assertContains(response, "Overview")

    def test_overview_refuses_non_admin_and_anonymous(self):
        url = reverse("core:admin-overview")
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        self.assertRedirects(
            self.anonymous.get(url), f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )

    def test_admin_area_lands_on_overview(self):
        areas = {key: url for key, _, url in user_areas(self.admin_user)}
        self.assertEqual(areas["admin"], "core:admin-overview")
```

For the multi-role guarantee (Review Focus 3), reuse the existing multi-role fixture in `core/tests/test_phase5_teacher_home.py` and add one test asserting `/` still redirects to `choose-area` for an admin who is also a teacher.

- [ ] **Step 2: Run and confirm failure**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase2 --parallel 4`
Expected: FAIL (`NoReverseMatch: 'admin-overview'`).

- [ ] **Step 3: Implement**

`core/views.py` (next to `choose_area`; use the same decorator as neighbouring admin views):

```python
@administrator_required("core.view_school")
def admin_overview(request):
    return render(
        request,
        "core/admin_overview.html",
        {"cards": [], "needs_setup": False},
    )
```

`core/urls.py`, first entry of `urlpatterns`:

```python
    path("overview/", views.admin_overview, name="admin-overview"),
```

`core/authorization.py:302`:

```python
        areas.append(("admin", "School administration", "core:admin-overview"))
```

`core/navigation.py`, first element of `OFFICE_NAV`:

```python
    ("Home", (
        NavLink("Overview", "core:admin-overview", "core.view_school"),
    )),
```

`core/templates/core/admin_overview.html`:

```django
{% extends "base.html" %}
{% block title %}Overview{% endblock %}
{% block content %}
{% include "partials/_page_header.html" with eyebrow="School administration" title="Overview" purpose="What needs attention today." only %}
{% endblock %}
```

- [ ] **Step 4: Run Task 1 tests** — Expected: PASS.

- [ ] **Step 5: Find tests that assumed the old landing**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation core.tests.test_phase5_teacher_home core.tests.test_phase6_guardian_accounts core.tests.test_authorization --parallel 4`
Known candidates: `test_phase5_teacher_home.py:55` (asserts `home` → `school-detail`), `test_ui_foundation.py:59` (sidebar group list), `test_phase6_guardian_accounts.py:295`. Update only assertions that encode "admin lands on School" or the exact group list. Do not weaken authorization assertions.

- [ ] **Step 6: Fix those assertions, rerun the same command, expect PASS.**

- [ ] **Step 7: Commit**

```bash
git add core/views.py core/urls.py core/authorization.py core/navigation.py core/templates/core/admin_overview.html core/tests
git commit -m "feat(ui): add admin Overview landing page (F04 shell)"
```

---

### Task 2: Overview queue cards

**Files:**
- Create: `core/dashboard.py`, `templates/partials/_queue_card.html`
- Modify: `core/views.py` (`admin_overview`), `core/templates/core/admin_overview.html`, `static/css/erp.css`
- Test: `core/tests/test_ui_admin_phase2.py`

**Interfaces:**
- Consumes: `core.publication.stale_publications()`, `core.guardian_access.pending_reviews(on_date)`, `core.models.business_today`, `Applicant.AdmissionStatus.PENDING`, `AttendanceRegister`, `AcademicEnrollment.objects.effective_on(date)` (verify the manager is exposed that way with `grep -n "effective_on\|objects = " core/models.py`).
- Produces: `overview_cards(user) -> list[dict]` and `needs_setup() -> bool` in `core/dashboard.py`. Card keys: `key`, `title`, `count`, `summary`, `url`, `tone` (`"attention"` or `"clear"`), `detail`.

- [ ] **Step 1: Write the failing tests** (append to `test_ui_admin_phase2.py`)

```python
from django.contrib.auth.models import Permission

from core.dashboard import overview_cards
from core.models import Applicant, AttendanceRegister, business_today
from core.tests.test_authorization import AttendanceFixtureMixin


def card(cards, key):
    return next((c for c in cards if c["key"] == key), None)


class OverviewCardTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_applicants_card_counts_only_pending(self):
        Applicant.objects.create(full_name="Pending One")
        accepted = Applicant.objects.create(full_name="Done")
        accepted.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)

        data = card(overview_cards(self.admin_user), "applicants")

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["url"], reverse("core:applicant-list"))

    def test_applicants_card_clear_when_none_pending(self):
        data = card(overview_cards(self.admin_user), "applicants")
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["tone"], "clear")

    def test_attendance_card_counts_sections_without_register_today(self):
        before = card(overview_cards(self.admin_user), "attendance")["count"]
        AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.class_grade,
            section=self.section, date=business_today(),
        )
        after = card(overview_cards(self.admin_user), "attendance")
        self.assertEqual(after["count"], before - 1)
        self.assertEqual(after["url"], reverse("core:attendance-register-list"))

    def test_page_shows_cards_and_empty_copy(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertContains(response, "Applicants awaiting decision")
        self.assertContains(response, "Nothing waiting")

    def test_card_hidden_without_source_permission(self):
        user = User.objects.create_user(username="viewer", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        self.assertEqual(overview_cards(User.objects.get(pk=user.pk)), [])
        client = self.client_class()
        client.login(username="viewer", password="pass-12345")
        response = client.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to show for your role")


class OverviewSetupStateTests(AuthorizationClientsMixin, TestCase):
    def test_brand_new_school_shows_setup_state(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up your school")
        self.assertContains(response, reverse("core:academic-year-list"))
```

Read `AttendanceFixtureMixin` first. If its fixture leaves no enrollment effective today, create an `AcademicEnrollment` for `self.section` covering today in `setUp`, so the attendance test measures a real change.

- [ ] **Step 2: Run, expect FAIL** (`ImportError: core.dashboard`).

- [ ] **Step 3: Implement `core/dashboard.py`**

```python
"""Overview cards for the admin landing page (F04). Read-only; no HTTP here.

Each card reuses the data source of the list page it links to, so the
count and the destination cannot disagree. A card is omitted when the user
lacks the permission the destination page requires.
"""

from django.db.models import Min
from django.urls import reverse

from core import guardian_access, publication
from core.models import (
    AcademicEnrollment,
    AcademicYear,
    Applicant,
    AttendanceRegister,
    Section,
    business_today,
)


def _card(key, title, count, summary, url, detail=""):
    return {
        "key": key,
        "title": title,
        "count": count,
        "summary": summary,
        "url": url,
        "detail": detail,
        "tone": "attention" if count else "clear",
    }


def _attendance(today):
    expected = (
        AcademicEnrollment.objects.effective_on(today)
        .values_list("section_id", flat=True)
        .distinct()
    )
    taken = AttendanceRegister.objects.filter(date=today).values_list("section_id", flat=True)
    missing = Section.objects.filter(pk__in=expected).exclude(pk__in=taken).count()
    return _card(
        "attendance", "Attendance today", missing,
        "Sections with no register opened today.",
        reverse("core:attendance-register-list"),
    )


def _applicants(today):
    pending = Applicant.objects.filter(admission_status=Applicant.AdmissionStatus.PENDING)
    oldest = pending.aggregate(oldest=Min("created_at"))["oldest"]
    detail = f"Oldest waiting since {oldest:%d %b %Y}." if oldest else ""
    return _card(
        "applicants", "Applicants awaiting decision", pending.count(),
        "Accept or reject pending applications.",
        reverse("core:applicant-list"), detail,
    )


def _publications(today):
    return _card(
        "publications", "Results to publish", publication.stale_publications().count(),
        "Published results that are out of date.",
        reverse("core:publications-stale"),
    )


def _access_reviews(today):
    return _card(
        "access_reviews", "Pending access reviews",
        len(guardian_access.pending_reviews(today)),
        "Guardian access that needs an explicit decision.",
        reverse("core:guardian-access-reviews"),
    )


# (builder, permission required by the destination page)
_CARDS = (
    (_attendance, "core.view_attendanceregister"),
    (_applicants, "core.view_applicant"),
    (_publications, "core.view_termpublication"),
    (_access_reviews, "core.view_guardianaccessreview"),
)


def overview_cards(user):
    today = business_today()
    return [build(today) for build, perm in _CARDS if user.has_perm(perm)]


def needs_setup():
    """True until the school has an Academic Year and at least one Section."""
    return not (AcademicYear.objects.exists() and Section.objects.exists())
```

Before finalising: confirm `guardian_access.pending_reviews` is side-effect free (the list page calls `record_pending_events` separately; the Overview must NOT call it), and that the permission strings match `navigation.OFFICE_NAV`.

`core/views.py` (add `from core import dashboard` with the other `from core import ...` imports):

```python
@administrator_required("core.view_school")
def admin_overview(request):
    return render(
        request,
        "core/admin_overview.html",
        {
            "cards": dashboard.overview_cards(request.user),
            "needs_setup": dashboard.needs_setup(),
        },
    )
```

`templates/partials/_queue_card.html`:

```django
<article class="erp-queue-card erp-queue-card--{{ card.tone }}">
    <h2 class="erp-queue-title">{{ card.title }}</h2>
    {% if card.count %}
    <p class="erp-queue-count">{{ card.count }}</p>
    <p class="erp-queue-summary">{{ card.summary }}{% if card.detail %} {{ card.detail }}{% endif %}</p>
    {% else %}
    <p class="erp-queue-summary">Nothing waiting.</p>
    {% endif %}
    <a class="btn btn-outline-primary btn-sm" href="{{ card.url }}">Open<span class="visually-hidden"> {{ card.title }}</span></a>
</article>
```

`core/templates/core/admin_overview.html` (replace the body):

```django
{% extends "base.html" %}
{% block title %}Overview{% endblock %}
{% block content %}
{% include "partials/_page_header.html" with eyebrow="School administration" title="Overview" purpose="What needs attention today." only %}
{% if needs_setup %}
<section class="erp-queue-card erp-queue-card--clear" aria-labelledby="setup-title">
    <h2 class="erp-queue-title" id="setup-title">Set up your school</h2>
    <p class="erp-queue-summary">Add an academic year and its classes and sections before daily work can appear here.</p>
    <a class="btn btn-primary btn-sm" href="{% url 'core:academic-year-list' %}">Academic years</a>
    <a class="btn btn-outline-secondary btn-sm" href="{% url 'core:class-grade-list' %}">Classes/Grades</a>
</section>
{% endif %}
{% if cards %}
<div class="erp-queue-grid">
    {% for card in cards %}{% include "partials/_queue_card.html" with card=card only %}{% endfor %}
</div>
{% elif not needs_setup %}
<p class="text-muted">Nothing to show for your role.</p>
{% endif %}
{% endblock %}
```

In `test_card_hidden_without_source_permission` the school has no year or sections, so `needs_setup` is True and "Nothing to show for your role" will not render. Build the year and section in that test (use the attendance fixture, which `OverviewCardTests` already has) so the assertion is meaningful.

`static/css/erp.css` (append; confirm the real token names with `grep -n "^  --erp-" static/css/erp.css` and use those):

```css
.erp-queue-grid { display: grid; gap: var(--erp-space-4); grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); }
.erp-queue-card { background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: 8px; padding: var(--erp-space-4); display: flex; flex-direction: column; gap: var(--erp-space-2); }
.erp-queue-card--attention { border-left: 4px solid var(--erp-accent); }
.erp-queue-title { font-size: 1rem; margin: 0; }
.erp-queue-count { font-size: 2rem; font-weight: 700; margin: 0; line-height: 1.1; }
.erp-queue-summary { margin: 0; color: var(--erp-muted); }
```

- [ ] **Step 4: Run Task 2 tests, expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add core/dashboard.py core/views.py core/templates/core/admin_overview.html templates/partials/_queue_card.html static/css/erp.css core/tests/test_ui_admin_phase2.py
git commit -m "feat(ui): add Overview action-queue cards (F04)"
```

---

### Task 3: Breadcrumb map, context, section-aware sidebar

**Files:**
- Create: `core/breadcrumbs.py`, `templates/partials/_breadcrumbs.html`
- Modify: `core/context_processors.py`, `core/navigation.py` (`_link`, `office_nav`), `templates/base.html`, `static/css/erp.css`
- Test: `core/tests/test_ui_admin_phase2.py`

**Interfaces:**
- Produces: `breadcrumb_context(match) -> {"breadcrumbs": list[{"label","url"}], "nav_section": str | None}`; `office_nav(user, url_name, section=None)`; template context keys `breadcrumbs` and `nav_section`.

- [ ] **Step 1: Write the failing tests**

```python
from django.urls import resolve

from core.breadcrumbs import breadcrumb_context
from core.navigation import office_nav


class BreadcrumbMapTests(TestCase):
    def match(self, name, **kwargs):
        return resolve(reverse(name, kwargs=kwargs))

    def test_student_detail_has_students_section_and_trail(self):
        ctx = breadcrumb_context(self.match("core:student-detail", pk=7))
        self.assertEqual(ctx["nav_section"], "student-list")
        self.assertEqual(
            [c["label"] for c in ctx["breadcrumbs"]], ["Overview", "Students", "Student"]
        )
        self.assertIsNone(ctx["breadcrumbs"][-1]["url"])

    def test_deactivate_confirm_parent_reuses_pk(self):
        ctx = breadcrumb_context(self.match("core:student-deactivate-confirm", pk=7))
        self.assertEqual(ctx["breadcrumbs"][-2]["url"], reverse("core:student-detail", args=[7]))

    def test_unmapped_page_has_no_breadcrumbs(self):
        ctx = breadcrumb_context(self.match("core:subject-list"))
        self.assertEqual(ctx, {"breadcrumbs": [], "nav_section": None})

    def test_none_match_is_safe(self):
        self.assertEqual(breadcrumb_context(None), {"breadcrumbs": [], "nav_section": None})


class SectionAwareNavTests(AuthorizationClientsMixin, TestCase):
    def active_labels(self, groups):
        return [link["label"] for g in groups for link in g["links"] if link["active"]]

    def test_section_marks_parent_link_active(self):
        groups = office_nav(self.admin_user, "student-detail", section="student-list")
        self.assertEqual(self.active_labels(groups), ["Students"])

    def test_exact_match_still_works_without_section(self):
        groups = office_nav(self.admin_user, "student-list")
        self.assertEqual(self.active_labels(groups), ["Students"])


class BreadcrumbRenderingTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        applicant = Applicant.objects.create(full_name="Asha Rao")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.student = applicant.progress_to_student()

    def test_student_detail_renders_breadcrumb_nav(self):
        response = self.administrator.get(reverse("core:student-detail", args=[self.student.pk]))
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, '<li aria-current="page">Student</li>', html=False)
        self.assertContains(response, reverse("core:student-list"))

    def test_deactivate_confirm_links_back_to_student(self):
        response = self.administrator.get(
            reverse("core:student-deactivate-confirm", args=[self.student.pk])
        )
        self.assertContains(
            response, f'href="{reverse("core:student-detail", args=[self.student.pk])}"'
        )

    def test_overview_page_itself_has_no_breadcrumb(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertNotContains(response, 'aria-label="Breadcrumb"')
```

(`Applicant` is already imported from Task 2.)

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: core.breadcrumbs`).

- [ ] **Step 3: Implement `core/breadcrumbs.py`**

```python
"""Breadcrumb trails and sidebar sections for deep admin pages (F05).

One declarative map, so views never build trails by hand. A page that is
not listed gets no trail and keeps exact-match sidebar highlighting.
"""

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class Crumb:
    label: str
    url_name: str
    uses_pk: bool = False  # reverse with the current page's `pk`


@dataclass(frozen=True)
class Rule:
    section: str  # short URL name of the sidebar link to keep active
    trail: tuple  # ancestor Crumbs, outermost first (after "Overview")
    label: str  # current page


_STUDENTS = Crumb("Students", "core:student-list")
_APPLICANTS = Crumb("Applicants", "core:applicant-list")
_ATTENDANCE = Crumb("Attendance", "core:attendance-register-list")
_ANNOUNCEMENTS = Crumb("Announcements", "core:announcement-list")

RULES = {
    "student-detail": Rule("student-list", (_STUDENTS,), "Student"),
    "student-deactivate-confirm": Rule(
        "student-list", (_STUDENTS, Crumb("Student", "core:student-detail", True)), "Deactivate"
    ),
    "applicant-detail": Rule("applicant-list", (_APPLICANTS,), "Applicant"),
    "applicant-decision-confirm": Rule(
        "applicant-list",
        (_APPLICANTS, Crumb("Applicant", "core:applicant-detail", True)),
        "Decision",
    ),
    "attendance-register-detail": Rule("attendance-register-list", (_ATTENDANCE,), "Register"),
    "attendance-entry-correct": Rule("attendance-register-list", (_ATTENDANCE,), "Correct entry"),
    "announcement-create": Rule("announcement-list", (_ANNOUNCEMENTS,), "New announcement"),
    "announcement-detail": Rule("announcement-list", (_ANNOUNCEMENTS,), "Announcement"),
}

_EMPTY = {"breadcrumbs": [], "nav_section": None}


def breadcrumb_context(match):
    if match is None or match.namespace != "core":
        return dict(_EMPTY)
    rule = RULES.get(match.url_name)
    if rule is None:
        return dict(_EMPTY)
    try:
        crumbs = [{"label": "Overview", "url": reverse("core:admin-overview")}]
        for crumb in rule.trail:
            kwargs = {"pk": match.kwargs["pk"]} if crumb.uses_pk else {}
            crumbs.append({"label": crumb.label, "url": reverse(crumb.url_name, kwargs=kwargs)})
    except (NoReverseMatch, KeyError):
        return dict(_EMPTY)
    crumbs.append({"label": rule.label, "url": None})
    return {"breadcrumbs": crumbs, "nav_section": rule.section}
```

Check every URL name against `core/urls.py` (`student-list`, `applicant-list`, `announcement-create`, `attendance-entry-correct`, `applicant-decision-confirm`, `student-deactivate-confirm`) before relying on them. If the app is mounted under a `core` namespace, `match.namespace` is `"core"`; if not, drop that check.

`core/navigation.py`:

```python
def _link(link, url_name, section=None):
    short = _short(link.url_name)
    return {
        "label": link.label,
        "url": reverse(link.url_name),
        "active": url_name == short or section == short,
    }


def office_nav(user, url_name, section=None):
    ...
            _link(link, url_name, section)   # inside the existing comprehension
```

`teacher_tabs` keeps calling `_link(tab, url_name)` unchanged.

`core/context_processors.py`:

```python
from core.breadcrumbs import breadcrumb_context
...
    trail = breadcrumb_context(match) if area == "admin" else {"breadcrumbs": [], "nav_section": None}
    return {
        ...
        "office_nav": office_nav(user, url_name, trail["nav_section"]) if area == "admin" else [],
        "breadcrumbs": trail["breadcrumbs"],
    }
```

`templates/partials/_breadcrumbs.html`:

```django
{% if breadcrumbs %}
<nav class="erp-breadcrumb" aria-label="Breadcrumb">
    <ol>
        {% for crumb in breadcrumbs %}
        <li{% if forloop.last %} aria-current="page"{% endif %}>{% if crumb.url %}<a href="{{ crumb.url }}">{{ crumb.label }}</a>{% else %}{{ crumb.label }}{% endif %}</li>
        {% endfor %}
    </ol>
</nav>
{% endif %}
```

`templates/base.html`, directly inside `<div class="erp-content">`, before the content block:

```django
            {% include "partials/_breadcrumbs.html" %}
```

`static/css/erp.css` (real token names as in Task 2):

```css
.erp-breadcrumb ol { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); list-style: none; padding: 0; margin: 0 0 var(--erp-space-3); font-size: .875rem; color: var(--erp-muted); }
.erp-breadcrumb li + li::before { content: "/"; margin-right: var(--erp-space-2); }
.erp-breadcrumb a { color: var(--erp-accent); }
.erp-breadcrumb li[aria-current] { color: var(--erp-ink); }
```

- [ ] **Step 4: Run Task 3 tests, expect PASS.**

- [ ] **Step 5: Run neighbouring suites for regressions**

Run: `.venv\Scripts\python.exe manage.py test core.tests.test_ui_foundation core.tests.test_ui_admin_phase0 core.tests.test_ui_admin_phase1 core.tests.test_ui_admin_phase2 --parallel 4`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/breadcrumbs.py core/navigation.py core/context_processors.py templates/base.html templates/partials/_breadcrumbs.html static/css/erp.css core/tests/test_ui_admin_phase2.py
git commit -m "feat(ui): add breadcrumbs and section-aware sidebar (F05)"
```

---

### Task 4: Verification, responsive check, notes

**Files:**
- Modify: `docs/UI_REFERENCES.md` (short Phase 2 note), this plan (completion notes)

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python.exe manage.py test --parallel 4`
Expected: only the known date-dependent attendance failure.

- [ ] **Step 2: Static checks**

Run: `.venv\Scripts\python.exe -m ruff check core`, `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`, and `git diff --check`.
Expected: ruff clean; "No changes detected".

- [ ] **Step 3: Browser smoke test (Playwright MCP, isolated local server)**

Seed demo data (see `core/tests/test_seed_demo.py` for the command), log in as an administrator, then at widths 320, 768 and 1440 check: `/` lands on `/overview/`; no horizontal document overflow (`document.documentElement.scrollWidth <= innerWidth`); cards stack to one column at 320; student detail shows the breadcrumb and highlights "Students"; the deactivate confirm page has a working link back to the student; a teacher-only login still lands on `my-home`.

- [ ] **Step 4: Fix anything found, test first where it is a regression.**

- [ ] **Step 5: Record results**

Add a "Completion notes" section at the end of this plan (tests run, counts, deviations) and a two-line Phase 2 entry in `docs/UI_REFERENCES.md`.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs: record Phase 2 verification"
```

Do not push or open a PR until the user asks. PR #55 (Phase 1) must merge first; then rebase this branch onto `main` before opening the Phase 2 PR.


## Completion notes

Verified 2026-10-16 on branch `ui/audit-phase2-overview-navigation`.

**Automated**
- `manage.py test --parallel 4`: 1266 tests, 1 failure, the known date-dependent
  `test_missing_report_skips_sections_without_students_and_future_dates` (pinned to 2026-10-10; fails on `main` too).
- `ruff check core`: initially 3 findings in Phase 2 code (import order in `core/context_processors.py` and
  `core/tests/test_ui_admin_phase2.py`, one over-long line); fixed in a separate style commit, now clean.
- `makemigrations --check --dry-run`: No changes detected. `git diff --check`: clean.

**Browser smoke (Playwright, isolated server, throwaway SQLite DB, `seed_demo`, `demo_admin`)**
- At 320, 768 and 1440 px: `/` redirects to `/overview/`; no horizontal document overflow
  (`scrollWidth <= innerWidth` everywhere; at 320 the four cards stack in one column, 2x2 at 768, 4 across at 1440).
- Student detail shows breadcrumb "Overview > Students > Student" and "Students" is highlighted
  (`aria-current`) in the sidebar at 1440 (the sidebar is collapsed below that width).
- Deactivate confirm shows "Overview > Students > Student > Deactivate"; its Cancel link returns to the student.
- A Teachers-group-only login (created ad hoc; `seed_demo` provides none) lands on `/my/` (teacher home).
- Server stopped and temp DB deleted afterwards.

**Deviations from the plan**
- The attendance queue card is based on `reports.missing_attendance`, not the originally planned source.
- Real CSS tokens (`--erp-rule`, `--erp-ink-soft`, `--erp-radius`, `--erp-text-sm`) replaced the token names
  used in the plan.
- Minor: the breadcrumb labels the student crumb generically ("Student") rather than with the student's name.

**Deviations from the plan**
- Breadcrumbs render in `templates/base.html`, not `_page_header.html`, so no per-page edits were needed.
- Overview cards do not use `_status_badge.html`; they use the `erp-queue-card` tone classes.
- The attendance card links to the Missing attendance report (`core:report-missing-attendance`, today's range), the same
  `reports.missing_attendance` source it counts, rather than the register list.
