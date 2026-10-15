# U2 Teacher Daily Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make taking today's attendance, My day and attendance history fast and readable on a 360 px phone, without changing any attendance behaviour.

**Architecture:** Server-rendered Django templates on the U1 shell. The capture partial keeps the existing `AttendanceCaptureForm` radio and note inputs (same names and values) and restyles them; one new form helper `counts()` feeds the static counts. Progressive enhancement lives in one new block in `static/js/erp.js` keyed off `[data-erp-roster]`. The month page gets three new context values for previous/next links.

**Tech Stack:** Python 3.13, Django 5.2.17, Bootstrap 5.3.3 (jsDelivr), Django `TestCase`, ruff.

**Spec:** `docs/superpowers/specs/2026-10-15-ui-u2-teacher-daily-design.md` (its decisions table is binding). Roadmap: `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md`.

## Global Constraints

- Branch `ui/u2-teacher-daily`, created from `main` (U1 merged as PR #44).
- No model, migration, URL, form-field or permission changes. The only Python changes: one new form method (`AttendanceCaptureForm.counts`) and three new context keys on `my_attendance_assignment`.
- POST bodies unchanged: `action` = `open` / `save` / `submit`; `status_<enrollment pk>` = `PRESENT` / `ABSENT` / empty; `note_<enrollment pk>`.
- Works with JS off: every row visible, counts shown as a static line, notes visible when `:has()` is unsupported, Submit always enabled.
- An unanswered row is "Unmarked" — never counted or shown as present or absent.
- Strings existing tests rely on stay exactly: "Start today's register", "Attendance saved and submitted.", "Draft saved but not submitted.", "You are not a class teacher today.", "not a school day", "Submitted", "Absent", "Take attendance", "Mark unanswered as present", "Save draft", "Save and submit"; on the office page also "Marked: N" and `not</strong> treated as absent`.
- Lists stay ordered by student name; nothing is sorted by percentage.
- Bootstrap stays `5.3.3`. No new JS libraries. No inline `<script>` in templates (the capture partial's inline script moves to `erp.js`).
- Python line length 100; ruff rules E, F, I, UP, B. Imports in `core/tests/test_ui_teacher_daily.py` stay in one sorted block at the top (run `ruff check --fix` after adding imports).
- Commands: Windows PowerShell from the repo root with DB variables loaded —
  `foreach ($k in 'DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT') { Set-Item "env:$k" ([Environment]::GetEnvironmentVariable($k,'User')) }` — and `.\.venv\Scripts\python.exe`. Run the full suite without `--parallel` (a parallel run hides failures behind "cannot pickle 'traceback' object").

## Review Focus

1. **Office page loses its submit permission check** — a user who can capture but lacks `change_attendanceregister` must see Save draft and no Save and submit. Pinned in Task 2 (`test_office_page_hides_submit_without_permission`).
2. **Saved absence note hidden** — a draft reloaded with an ABSENT row and a note must show the note without interaction. Pinned in Task 2 (`test_saved_note_is_marked_filled`).
3. **Tab bar hidden on the wrong page** — it is hidden only while a draft roster is shown; it stays on "Start today's register", submitted, and My day. Pinned in Task 3 (`test_tab_bar_hidden_only_while_draft_open`, `test_tab_bar_back_after_submit`).
4. **Counts drift from what is posted** — a re-rendered bound form counts the posted choices, not the database. Pinned in Task 1 (`test_counts_use_bound_data`).
5. **Month links at the edges** — no link may point outside the assignment's months; a single-month assignment has neither. Pinned in Task 5 (`test_month_links_at_edges`, `test_single_month_has_no_links`).

---

## File structure

| File | Responsibility |
|---|---|
| `core/forms.py` (modify) | `AttendanceCaptureForm.counts()` |
| `core/templates/core/_attendance_capture_table.html` (rewrite) | Count line/tabs, roster rows, action bar |
| `core/templates/core/_attendance_entries.html` (create) | Read-only card list of submitted entries |
| `core/templates/core/my_attendance.html` (rewrite) | Teacher take-attendance page |
| `core/templates/core/attendance_register_detail.html` (modify) | Office draft form uses the new partial |
| `core/templates/core/my_home.html` (rewrite) | My day cards |
| `core/templates/core/my_attendance_history.html` (rewrite) | Assignment cards |
| `core/templates/core/my_attendance_assignment.html` (rewrite) | Month page |
| `core/templates/core/my_attendance_register.html` (modify) | Read-only register via `_attendance_entries.html` |
| `core/views.py` (modify `my_attendance_assignment`) | `previous_month`, `next_month`, `chosen_label` |
| `templates/base.html` (modify) | `tabbar_class` and `tabbar` blocks |
| `static/css/erp.css` (modify) | U2 components |
| `static/js/erp.js` (modify) | Roster enhancement |
| `core/tests/test_ui_teacher_daily.py` (create) | All U2 tests |
| `docs/UI_REFERENCES.md`, roadmap (modify) | Status lines |

---

### Task 1: Branch, spec commit and `AttendanceCaptureForm.counts()`

**Files:**
- Modify: `core/forms.py` (class `AttendanceCaptureForm`, after `statuses()`)
- Create: `core/tests/test_ui_teacher_daily.py`
- Add: the spec and this plan

**Interfaces:**
- Produces: `AttendanceCaptureForm.counts() -> dict` with int values for keys `"all"`, `"present"`, `"absent"`, `"unmarked"`, read from each status BoundField's `value()` (bound form → posted choice; unbound → initial).
- Produces: test fixture `U2Fixture` used by every later task: business day `MONDAY = date(2026, 10, 12)` patched in `core.views` and `core.models`; `self.duty` = `rao` class teacher of `self.six_a` from 2026-06-01; enrollments `self.asha`, `self.ravi`, `self.bina` in 6A; logged-in client `self.teacher` (rao); `self.url` = my-attendance URL for 6A; `self.register()`; `self.draft(notes=None, **statuses)` opens today's register and saves the given statuses, returning the register.

- [ ] **Step 1: Create the branch and commit the spec and plan**

```powershell
git fetch origin
git checkout -b ui/u2-teacher-daily origin/main
git add docs/superpowers/specs/2026-10-15-ui-u2-teacher-daily-design.md docs/superpowers/plans/2026-10-15-ui-u2-teacher-daily.md
git commit -m "docs(ui): U2 teacher daily screens spec and plan"
```

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_ui_teacher_daily.py`:

```python
"""U2 teacher daily screens: take attendance, My day, attendance history."""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.forms import AttendanceCaptureForm
from core.models import AttendanceRegister, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class U2Fixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.duty = SectionClassTeacher.assign(
            teacher=self.rao, academic_year=self.year, section=self.six_a,
            start_date=date(2026, 6, 1),
        )
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.bina = self.make_student("Bina")
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")
        self.url = reverse("core:my-attendance", args=[self.six_a.pk])

    def register(self):
        return AttendanceRegister.objects.get(section=self.six_a, date=MONDAY)

    def draft(self, notes=None, **statuses):
        """Open today's register and save entries, e.g. draft(asha="PRESENT")."""
        self.teacher.post(self.url, {"action": "open"})
        data = {"action": "save"}
        for name, status in statuses.items():
            data[f"status_{getattr(self, name).pk}"] = status
        for name, note in (notes or {}).items():
            data[f"note_{getattr(self, name).pk}"] = note
        self.teacher.post(self.url, data)
        return self.register()


class CaptureCountsTests(U2Fixture, TestCase):
    def test_counts_use_saved_entries(self):
        register = self.draft(asha="PRESENT", ravi="ABSENT")
        form = AttendanceCaptureForm(register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        register = self.draft(asha="PRESENT")
        data = {f"status_{self.asha.pk}": "ABSENT", f"status_{self.ravi.pk}": "ABSENT",
                f"status_{self.bina.pk}": ""}
        form = AttendanceCaptureForm(data, register=register)
        self.assertEqual(form.counts(), {"all": 3, "present": 0, "absent": 2, "unmarked": 1})
```

(`get_user_model`, `Permission` are used from Task 2; if ruff flags them as unused in this commit, add them in Task 2 instead.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily --noinput`
Expected: 2 errors, `AttributeError: 'AttendanceCaptureForm' object has no attribute 'counts'`

- [ ] **Step 4: Implement `counts()`**

In `core/forms.py`, inside `AttendanceCaptureForm`, after `statuses()`:

```python
    def counts(self):
        """Roster counts for display: all, present, absent and unmarked rows.

        Uses each field's current value, so a re-rendered bound form counts
        the posted choices. Unanswered rows are unmarked, never absent.
        """
        values = [self[self.field_name(e)].value() or "" for e in self.enrollments]
        present = sum(1 for v in values if v == AttendanceStatus.PRESENT)
        absent = sum(1 for v in values if v == AttendanceStatus.ABSENT)
        return {
            "all": len(values),
            "present": present,
            "absent": absent,
            "unmarked": len(values) - present - absent,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily --noinput`
Expected: `Ran 2 tests` … `OK`

- [ ] **Step 6: Commit**

```powershell
.\.venv\Scripts\python.exe -m ruff check core
git add core/forms.py core/tests/test_ui_teacher_daily.py
git commit -m "feat(ui): attendance capture form counts for roster display"
```

---

### Task 2: Capture partial — roster rows, count tabs, action bar (teacher and office)

**Files:**
- Rewrite: `core/templates/core/_attendance_capture_table.html`
- Modify: `core/templates/core/my_attendance.html` (draft form only)
- Modify: `core/templates/core/attendance_register_detail.html` (draft form only)
- Modify: `static/css/erp.css` (append), `static/js/erp.js` (append inside the IIFE)
- Test: `core/tests/test_ui_teacher_daily.py`

**Interfaces:**
- Consumes: `AttendanceCaptureForm.counts()`; `capture_form.rows()` yields `(enrollment, status_bound_field, note_bound_field)`.
- Produces: partial contract — include inside `<form id="attendance-capture">` as `{% include "core/_attendance_capture_table.html" with can_submit=<bool> %}`; it renders the action bar with Save draft and, if `can_submit`, Save and submit. Hooks: `[data-erp-roster]`, `[data-erp-row]`, `[data-erp-tabs]`, `[data-erp-filter]`, `[data-erp-count]`, `[data-erp-static-counts]`, `[data-erp-mark-present]`, `[data-erp-hint]`, `.erp-note`, `.erp-note.is-filled`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_ui_teacher_daily.py`:

```python
class CapturePartialTests(U2Fixture, TestCase):
    def test_post_names_and_values_unchanged(self):
        self.draft()
        page = self.teacher.get(self.url)
        for enrollment in (self.asha, self.ravi, self.bina):
            self.assertContains(page, f'name="status_{enrollment.pk}" value="PRESENT"')
            self.assertContains(page, f'name="status_{enrollment.pk}" value="ABSENT"')
            self.assertContains(page, f'name="note_{enrollment.pk}"')
        self.assertContains(page, 'name="action" value="save"')
        self.assertContains(page, 'name="action" value="submit"')

    def test_rows_are_fieldsets_named_by_student(self):
        self.draft()
        page = self.teacher.get(self.url)
        self.assertContains(page, '<legend class="erp-roster-name">Asha</legend>')
        self.assertEqual(page.content.decode().count("<fieldset"), 3)

    def test_static_counts(self):
        self.draft(asha="PRESENT", ravi="ABSENT")
        page = self.teacher.get(self.url)
        self.assertContains(page, 'data-erp-count="unmarked">1<')
        self.assertContains(page, 'data-erp-count="present">1<')
        self.assertContains(page, 'data-erp-count="absent">1<')
        self.assertContains(page, "All 3 · Unmarked 1 · Present 1 · Absent 1")
        self.assertContains(page, "1 unmarked")

    def test_saved_note_is_marked_filled(self):
        self.draft(notes={"ravi": "Fever"}, asha="PRESENT", ravi="ABSENT")
        page = self.teacher.get(self.url).content.decode()
        self.assertIn('value="Fever"', page)
        self.assertEqual(page.count('class="erp-note is-filled"'), 1)

    def test_mark_present_button_and_no_inline_script(self):
        self.draft()
        page = self.teacher.get(self.url)
        self.assertContains(page, "Mark unanswered as present")
        self.assertNotContains(page, "<script>")

    def test_office_page_uses_partial(self):
        register = self.draft(asha="PRESENT")
        self.client.login(username="admin", password="pass-12345")
        page = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertContains(page, "data-erp-roster")
        self.assertContains(page, "Marked: 1")
        self.assertContains(page, "Save and submit")

    def test_office_page_hides_submit_without_permission(self):
        register = self.draft()
        clerk = get_user_model().objects.create_user(username="clerk", password="pass-12345")
        clerk.user_permissions.add(
            Permission.objects.get(codename="view_attendanceregister"),
            Permission.objects.get(codename="add_attendanceentry"),
        )
        self.client.login(username="clerk", password="pass-12345")
        page = self.client.get(reverse("core:attendance-register-detail", args=[register.pk]))
        self.assertContains(page, "Save draft")
        self.assertNotContains(page, "Save and submit")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily.CapturePartialTests --noinput`
Expected: FAIL on `test_rows_are_fieldsets_named_by_student`, `test_static_counts`, `test_saved_note_is_marked_filled`, `test_mark_present_button_and_no_inline_script` (inline `<script>` present) and `test_office_page_uses_partial`. `test_post_names_and_values_unchanged` and `test_office_page_hides_submit_without_permission` may already pass; they guard against regressions. If the clerk gets 403, find the detail view's permission with `grep -n "def attendance_register_detail" -B3 core/views.py` and grant that one too.

- [ ] **Step 3: Rewrite the partial**

`core/templates/core/_attendance_capture_table.html`:

```django
{# Roster for a DRAFT register. Include inside <form id="attendance-capture"> with can_submit=<bool>. #}
{% with counts=capture_form.counts %}
<div class="erp-roster" data-erp-roster>
    <p class="erp-count-line" data-erp-static-counts>All {{ counts.all }} · Unmarked {{ counts.unmarked }} · Present {{ counts.present }} · Absent {{ counts.absent }}</p>
    <div class="erp-count-tabs" data-erp-tabs hidden>
        <button type="button" data-erp-filter="all" aria-pressed="true">All <span data-erp-count="all">{{ counts.all }}</span></button>
        <button type="button" data-erp-filter="unmarked" aria-pressed="false">Unmarked <span data-erp-count="unmarked">{{ counts.unmarked }}</span></button>
        <button type="button" data-erp-filter="present" aria-pressed="false">Present <span data-erp-count="present">{{ counts.present }}</span></button>
        <button type="button" data-erp-filter="absent" aria-pressed="false">Absent <span data-erp-count="absent">{{ counts.absent }}</span></button>
        <button type="button" class="btn btn-outline-secondary btn-sm erp-mark-present" data-erp-mark-present>Mark unanswered as present</button>
    </div>

    {% for enrollment, status_field, note_field in capture_form.rows %}
    <fieldset class="erp-roster-row" data-erp-row>
        <legend class="erp-roster-name">{{ enrollment.student.full_name }}</legend>
        <span class="erp-initials" aria-hidden="true">{{ enrollment.student.full_name|slice:":1"|upper }}</span>
        <div class="erp-toggles">
            {% for radio in status_field %}
                {{ radio.tag }}<label for="{{ radio.id_for_label }}" class="erp-toggle is-{{ radio.data.value|lower }}">{{ radio.choice_label }}</label>
            {% endfor %}
        </div>
        <div class="erp-note{% if note_field.value or note_field.errors %} is-filled{% endif %}">
            <label class="form-label small mb-1" for="{{ note_field.id_for_label }}">Absence note<span class="visually-hidden"> for {{ enrollment.student.full_name }}</span></label>
            {{ note_field }}
            {% for error in note_field.errors %}<div class="small text-danger">{{ error }}</div>{% endfor %}
        </div>
    </fieldset>
    {% endfor %}

    <div class="erp-actionbar">
        <span class="erp-actionbar-status" data-erp-hint aria-live="polite">{{ counts.unmarked }} unmarked</span>
        <button type="submit" name="action" value="save" class="btn btn-outline-primary">Save draft</button>
        {% if can_submit %}<button type="submit" name="action" value="submit" class="btn btn-primary">Save and submit</button>{% endif %}
    </div>
    {% if can_submit %}<p class="form-text">Submitting requires Present or Absent for every Student.</p>{% endif %}
</div>
{% endwith %}
```

The exact string `class="erp-note is-filled"` appears only for filled notes, which `test_saved_note_is_marked_filled` counts.

- [ ] **Step 4: Use the partial on both pages**

In `core/templates/core/my_attendance.html`, replace the draft form with:

```django
    <form method="post" id="attendance-capture">
        {% csrf_token %}
        {% include "core/_attendance_capture_table.html" with can_submit=True %}
    </form>
```

(delete the two old buttons and the `form-text` span after the old include). Task 3 rewrites the rest of this page.

In `core/templates/core/attendance_register_detail.html`, inside the draft `<form … id="attendance-capture">`, replace everything from `{% include "core/_attendance_capture_table.html" %}` through the `{% endif %}` that closes the submit button's permission check with:

```django
        {% include "core/_attendance_capture_table.html" with can_submit=perms.core.change_attendanceregister %}
```

Keep the paragraph with "Marked: {{ marked_count }}" and `<strong>not</strong> treated as absent` unchanged.

- [ ] **Step 5: Append CSS to `static/css/erp.css`** (before the `/* Wide tables scroll …` comment)

```css
/* ---------- U2: attendance roster ---------- */

.erp-count-line { color: var(--erp-ink-soft); margin-bottom: .75rem; }
.erp-count-tabs { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .75rem; align-items: center; }
.erp-count-tabs [data-erp-filter] {
  border: 1px solid var(--erp-rule); background: var(--erp-surface); color: var(--erp-ink);
  border-radius: 999px; padding: .35rem .8rem; font-size: .9rem; min-height: 2.25rem;
}
.erp-count-tabs [data-erp-filter][aria-pressed="true"] {
  background: var(--erp-accent); border-color: var(--erp-accent); color: #fff; font-weight: 600;
}
.erp-mark-present { margin-left: auto; }

.erp-roster-row {
  display: grid; grid-template-columns: 2.25rem 1fr; gap: .5rem .75rem; align-items: center;
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
  padding: .75rem; margin-bottom: .5rem;
}
.erp-roster-row[hidden] { display: none; }
.erp-roster-name {
  grid-column: 2; grid-row: 1; float: none; width: auto; margin: 0; font-size: 1rem; font-weight: 600;
}
.erp-initials {
  grid-column: 1; grid-row: 1; width: 2.25rem; height: 2.25rem; border-radius: 50%;
  display: grid; place-items: center; background: var(--erp-accent-wash); color: var(--erp-accent);
  font-weight: 700;
}
.erp-toggles { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.erp-toggles input[type="radio"] { position: absolute; opacity: 0; width: 1px; height: 1px; }
.erp-toggle {
  display: grid; place-items: center; min-height: 2.75rem; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--erp-rule); background: var(--erp-paper); font-weight: 600; margin: 0;
}
.erp-toggles input:focus-visible + .erp-toggle { outline: 3px solid var(--erp-accent); outline-offset: 2px; }
.erp-toggles input:checked + .erp-toggle.is-present {
  background: var(--erp-accent); border-color: var(--erp-accent); color: #fff;
}
.erp-toggles input:checked + .erp-toggle.is-absent {
  background: var(--erp-crit); border-color: var(--erp-crit); color: #fff;
}
.erp-note { grid-column: 1 / -1; }
/* Without :has() support the note simply stays visible. */
@supports selector(:has(*)) {
  .erp-note:not(.is-filled) { display: none; }
  .erp-roster-row:has(input[value="ABSENT"]:checked) .erp-note { display: block; }
}

.erp-actionbar {
  position: sticky; bottom: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: .5rem; align-items: center;
  background: var(--erp-surface); border-top: 1px solid var(--erp-rule);
  padding: .75rem; margin-inline: -.75rem; padding-bottom: calc(.75rem + env(safe-area-inset-bottom));
}
.erp-actionbar-status { flex: 1 1 100%; font-size: .9rem; color: var(--erp-ink-soft); }
.erp-actionbar .btn { flex: 1; min-height: 2.75rem; }
@media (min-width: 576px) {
  .erp-actionbar-status { flex: 1 1 auto; }
  .erp-actionbar .btn { flex: 0 0 auto; }
}
```

- [ ] **Step 6: Append JS to `static/js/erp.js`** (inside the IIFE, before the closing `})();`)

```js
  // Attendance roster: live counts, filter tabs, mark-unanswered-present, submit hint.
  // Without JS the static count line stays and every row is shown.
  document.querySelectorAll("[data-erp-roster]").forEach(function (roster) {
    var rows = Array.prototype.slice.call(roster.querySelectorAll("[data-erp-row]"));
    var tabs = roster.querySelector("[data-erp-tabs]");
    var staticCounts = roster.querySelector("[data-erp-static-counts]");
    var hint = roster.querySelector("[data-erp-hint]");
    var filter = "all";

    function statusOf(row) {
      var checked = row.querySelector('input[type="radio"]:checked');
      return checked ? checked.value.toLowerCase() : "unmarked";
    }

    function refresh() {
      var counts = { all: rows.length, present: 0, absent: 0, unmarked: 0 };
      rows.forEach(function (row) {
        var status = statusOf(row);
        counts[status] += 1;
        row.hidden = filter !== "all" && filter !== status;
      });
      Object.keys(counts).forEach(function (key) {
        var target = roster.querySelector('[data-erp-count="' + key + '"]');
        if (target) target.textContent = counts[key];
      });
      if (hint) {
        hint.textContent = counts.unmarked
          ? "Mark all students to submit (" + counts.unmarked + " unmarked)"
          : "All students marked";
      }
    }

    if (tabs) {
      tabs.hidden = false;
      if (staticCounts) staticCounts.hidden = true;
      tabs.querySelectorAll("[data-erp-filter]").forEach(function (button) {
        button.addEventListener("click", function () {
          filter = button.getAttribute("data-erp-filter");
          tabs.querySelectorAll("[data-erp-filter]").forEach(function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
          });
          refresh();
        });
      });
    }

    // Fills Present only for rows not yet answered and never overrides a choice.
    // Nothing is saved until the form is submitted, so an unopened register is never present.
    var markPresent = roster.querySelector("[data-erp-mark-present]");
    if (markPresent) {
      markPresent.addEventListener("click", function () {
        rows.forEach(function (row) {
          if (statusOf(row) === "unmarked") {
            var present = row.querySelector('input[type="radio"][value="PRESENT"]');
            if (present) present.checked = true;
          }
        });
        refresh();
      });
    }

    roster.addEventListener("change", function (event) {
      if (event.target.type === "radio") refresh();
    });
    refresh();
  });
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily core.tests.test_authorization core.tests.test_phase5_teacher_attendance --noinput`
Expected: `OK`

- [ ] **Step 8: Commit**

```powershell
git add core/templates/core/_attendance_capture_table.html core/templates/core/my_attendance.html core/templates/core/attendance_register_detail.html static/css/erp.css static/js/erp.js core/tests/test_ui_teacher_daily.py
git commit -m "feat(ui): phone attendance roster with count tabs and sticky action bar"
```

---

### Task 3: Take-attendance page — header, states, submitted cards, tab bar hidden while drafting

**Files:**
- Modify: `templates/base.html` (body class and tab bar include)
- Rewrite: `core/templates/core/my_attendance.html`
- Create: `core/templates/core/_attendance_entries.html`
- Modify: `static/css/erp.css` (append `.erp-card`, `.erp-entry`)
- Test: `core/tests/test_ui_teacher_daily.py`

**Interfaces:**
- Consumes: Task 2 partial contract.
- Produces: `base.html` blocks `tabbar_class` (` has-tabbar` in the teacher area) and `tabbar` (the tab bar include in the teacher area). Partial `core/_attendance_entries.html` expecting `entries` (AttendanceEntry objects with `academic_enrollment__student` selected); Task 5 reuses it. CSS classes `.erp-card`, `.erp-card-row`, `.erp-card-title`, `.erp-card-meta` used by Tasks 4 and 5.

- [ ] **Step 1: Write the failing tests**

```python
class TakeAttendancePageTests(U2Fixture, TestCase):
    def test_tab_bar_hidden_only_while_draft_open(self):
        start = self.teacher.get(self.url)
        self.assertContains(start, "Start today's register")
        self.assertContains(start, 'class="erp-tabbar')
        self.draft()
        drafting = self.teacher.get(self.url)
        self.assertNotContains(drafting, 'class="erp-tabbar')
        self.assertNotContains(drafting, "has-tabbar")
        self.assertContains(drafting, reverse("core:my-home"))
        self.assertContains(self.teacher.get(reverse("core:my-home")), 'class="erp-tabbar')

    def test_tab_bar_back_after_submit(self):
        self.draft(asha="PRESENT", ravi="PRESENT", bina="ABSENT")
        self.register().submit(actor=self.rao)
        self.assertContains(self.teacher.get(self.url), 'class="erp-tabbar')

    def test_draft_and_submitted_pills(self):
        self.draft(asha="PRESENT")
        self.assertContains(self.teacher.get(self.url),
                            '<span class="erp-pill is-draft">Draft</span>')
        self.draft(asha="PRESENT", ravi="PRESENT", bina="ABSENT")
        self.register().submit(actor=self.rao)
        page = self.teacher.get(self.url)
        self.assertContains(page, '<span class="erp-pill is-submitted">Submitted</span>')
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
        self.assertContains(page, "only be changed by an administrator")
```

(`draft()` posts `open` again on an existing register; the view answers with an info message and keeps the register, so calling it twice is safe.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily.TakeAttendancePageTests --noinput`
Expected: FAIL (`erp-tabbar` still present while drafting; pills missing).

- [ ] **Step 3: Add blocks to `templates/base.html`**

Replace the body tag and the tab bar include line with:

```django
<body class="erp{% if office_nav %} has-sidebar{% endif %}{% block tabbar_class %}{% if current_area == 'teacher' %} has-tabbar{% endif %}{% endblock %}">
```

```django
    {% block tabbar %}{% if current_area == 'teacher' %}{% include "partials/_tabbar.html" with tabs=teacher_tabs tabbar_label="Teaching" %}{% endif %}{% endblock %}
```

- [ ] **Step 4: Create `core/templates/core/_attendance_entries.html`**

```django
{# Read-only submitted entries. Expects `entries` with academic_enrollment__student selected. #}
<ul class="erp-entries list-unstyled">
    {% for entry in entries %}
    <li class="erp-entry">
        <span class="erp-entry-name">{{ entry.academic_enrollment.student.full_name }}</span>
        <span class="erp-pill is-{{ entry.status|lower }}">{{ entry.get_status_display }}</span>
        {% if entry.absence_note %}<span class="erp-entry-note">{{ entry.absence_note }}</span>{% endif %}
    </li>
    {% empty %}
    <li>No entries.</li>
    {% endfor %}
</ul>
```

- [ ] **Step 5: Rewrite `core/templates/core/my_attendance.html`**

```django
{% extends "base.html" %}
{% block title %}Attendance {{ section }}{% endblock %}
{% block tabbar_class %}{% if not capture_form.enrollments %}{{ block.super }}{% endif %}{% endblock %}
{% block tabbar %}{% if not capture_form.enrollments %}{{ block.super }}{% endif %}{% endblock %}
{% block content %}
<p class="mb-2"><a href="{% url 'core:my-home' %}">‹ My day</a></p>
<h1 class="h3 mb-1">Attendance: {{ section }}</h1>
<p class="text-muted mb-3">{{ today|date:"l, j F Y" }} &middot; {{ year.name }}
    {% if register.is_submitted %}<span class="erp-pill is-submitted">Submitted</span>{% elif register %}<span class="erp-pill is-draft">Draft</span>{% endif %}</p>

{% if register is None %}
    {% if is_instructional %}
    <div class="erp-empty">
        <p class="erp-empty-title">Attendance has not been taken today.</p>
        <form method="post">
            {% csrf_token %}
            <button type="submit" name="action" value="open" class="btn btn-primary">Start today's register</button>
        </form>
    </div>
    {% else %}
    <div class="erp-empty"><p>Today is not a school day for {{ year.name }}; no attendance is expected.</p></div>
    {% endif %}
{% elif register.is_submitted %}
    <p>Submitted {{ register.submitted_at }} by {{ register.submitted_by.get_full_name|default:register.submitted_by.username }}.
       Submitted attendance can only be changed by an administrator, through a correction.</p>
    {% include "core/_attendance_entries.html" %}
{% else %}
    <p class="text-muted">Unmarked Students are <strong>not</strong> treated as absent.</p>
    {% if capture_form.enrollments %}
    <form method="post" id="attendance-capture">
        {% csrf_token %}
        {% include "core/_attendance_capture_table.html" with can_submit=True %}
    </form>
    {% else %}
    {% include "partials/_empty.html" with text="No Students are enrolled in this Section today." %}
    {% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Append CSS**

```css
.erp-card {
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
  padding: .9rem 1rem; margin-bottom: .6rem;
}
.erp-card-row { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; justify-content: space-between; }
.erp-card-title { font-weight: 600; margin: 0; }
.erp-card-meta { color: var(--erp-ink-soft); font-size: .9rem; margin: 0; }
.erp-entry {
  display: flex; flex-wrap: wrap; gap: .25rem .75rem; align-items: center;
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
  padding: .6rem .8rem; margin-bottom: .4rem;
}
.erp-entry-name { flex: 1; font-weight: 600; }
.erp-entry-note { flex-basis: 100%; color: var(--erp-ink-soft); font-size: .9rem; }
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily core.tests.test_phase5_teacher_attendance core.tests.test_ui_foundation --noinput`
Expected: `OK`

- [ ] **Step 8: Commit**

```powershell
git add templates/base.html core/templates/core/my_attendance.html core/templates/core/_attendance_entries.html static/css/erp.css core/tests/test_ui_teacher_daily.py
git commit -m "feat(ui): take-attendance page states and hide tab bar while drafting"
```

---

### Task 4: My day cards

**Files:**
- Rewrite: `core/templates/core/my_home.html`
- Modify: `static/css/erp.css` (append `.erp-section-title`, `.erp-progress`)
- Test: `core/tests/test_ui_teacher_daily.py`

**Interfaces:**
- Consumes: view context unchanged — `today`; `attendance` (list of `{"duty", "register", "state"}`, state one of `NOT_INSTRUCTIONAL`, `NOT_TAKEN`, `DRAFT`, `SUBMITTED`); `assessments` (each with `unmarked_count`); `remarks` (`{"term", "section", "expected", "written"}`). `.erp-card*` classes from Task 3.

- [ ] **Step 1: Write the failing tests**

```python
class MyDayTests(U2Fixture, TestCase):
    def home(self):
        return self.teacher.get(reverse("core:my-home"))

    def test_not_taken_card(self):
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-pending">Not taken</span>')
        self.assertContains(page, "Take attendance")

    def test_draft_card(self):
        self.draft(asha="PRESENT")
        page = self.home()
        self.assertContains(
            page, '<span class="erp-pill is-draft">Draft &mdash; not yet submitted</span>'
        )
        self.assertContains(page, ">Continue<")

    def test_submitted_card(self):
        self.draft(asha="PRESENT", ravi="PRESENT", bina="PRESENT")
        self.register().submit(actor=self.rao)
        page = self.home()
        self.assertContains(page, '<span class="erp-pill is-submitted">Submitted</span>')
        self.assertContains(page, ">View<")

    def test_not_a_school_day_card_has_no_action(self):
        with mock.patch("core.models.AcademicYear.is_instructional_day", return_value=False):
            page = self.home()
        self.assertContains(page, '<span class="erp-pill">Not a school day</span>')
        self.assertNotContains(page, "Take attendance")

    def test_no_tables_on_my_day(self):
        self.assertNotContains(self.home(), "<table")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily.MyDayTests --noinput`
Expected: FAIL (pills and cards missing; `<table` present).

- [ ] **Step 3: Rewrite `core/templates/core/my_home.html`**

```django
{% extends "base.html" %}
{% block title %}My day{% endblock %}
{% block content %}
<h1 class="h3 mb-1">My day</h1>
<p class="text-muted mb-4">{{ today|date:"l, j F Y" }}</p>

<h2 class="erp-section-title">Attendance</h2>
{% for row in attendance %}
<div class="erp-card">
    <div class="erp-card-row">
        <div>
            <p class="erp-card-title">{{ row.duty.section }}</p>
            {% if row.state == "NOT_INSTRUCTIONAL" %}<span class="erp-pill">Not a school day</span>
            {% elif row.state == "NOT_TAKEN" %}<span class="erp-pill is-pending">Not taken</span>
            {% elif row.state == "DRAFT" %}<span class="erp-pill is-draft">Draft &mdash; not yet submitted</span>
            {% else %}<span class="erp-pill is-submitted">Submitted</span>{% endif %}
        </div>
        {% if row.state == "NOT_TAKEN" %}<a class="btn btn-primary" href="{% url 'core:my-attendance' row.duty.section.pk %}">Take attendance</a>
        {% elif row.state == "DRAFT" %}<a class="btn btn-outline-primary" href="{% url 'core:my-attendance' row.duty.section.pk %}">Continue</a>
        {% elif row.state == "SUBMITTED" %}<a href="{% url 'core:my-attendance' row.duty.section.pk %}">View</a>{% endif %}
    </div>
</div>
{% empty %}
{% include "partials/_empty.html" with text="You are not a class teacher today." %}
{% endfor %}
<p><a href="{% url 'core:my-attendance-history' %}">Attendance history for my Sections</a></p>

<h2 class="erp-section-title">Marks to enter</h2>
{% for assessment in assessments %}
<div class="erp-card">
    <div class="erp-card-row">
        <div>
            <p class="erp-card-title"><a href="{% url 'core:assessment-marks-entry' assessment.pk %}">{{ assessment.name }}</a></p>
            <p class="erp-card-meta">{{ assessment.offering.subject.name }} &middot; {{ assessment.section }} &middot; {{ assessment.assessment_date|date:"j M" }}</p>
        </div>
        <span class="erp-pill is-pending">{{ assessment.unmarked_count }} unmarked</span>
    </div>
</div>
{% empty %}
<p>Nothing waiting. <a href="{% url 'core:my-assessments' %}">All my assessments</a></p>
{% endfor %}

{% if remarks %}
<h2 class="erp-section-title">Term remarks</h2>
{% for row in remarks %}
<a class="erp-card d-block text-decoration-none text-reset" href="{% url 'core:term-remarks' row.term.pk %}?section={{ row.section.pk }}">
    <p class="erp-card-title">{{ row.term.academic_year.name }} {{ row.term.name }} &middot; {{ row.section }}</p>
    <p class="erp-card-meta">{{ row.written }} of {{ row.expected }} written</p>
    <progress class="erp-progress" max="{{ row.expected|default:1 }}" value="{{ row.written }}">{{ row.written }} of {{ row.expected }}</progress>
</a>
{% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Append CSS**

```css
.erp-section-title { font-size: 1.05rem; font-weight: 700; margin: 1.5rem 0 .6rem; }
.erp-progress { width: 100%; height: .4rem; accent-color: var(--erp-accent); margin-top: .4rem; }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily core.tests.test_phase5_teacher_attendance core.tests.test_phase5_acceptance core.tests.test_ui_foundation --noinput`
Expected: `OK`. If an older test fails on My day markup, find it with `grep -rn "my-home" core/tests` and keep its asserted text in the cards.

- [ ] **Step 6: Commit**

```powershell
git add core/templates/core/my_home.html static/css/erp.css core/tests/test_ui_teacher_daily.py
git commit -m "feat(ui): My day as cards with one action each"
```

---

### Task 5: Attendance history — assignment cards, month page, read-only register

**Files:**
- Modify: `core/views.py` (`my_attendance_assignment`: three context keys)
- Rewrite: `core/templates/core/my_attendance_history.html`, `core/templates/core/my_attendance_assignment.html`
- Modify: `core/templates/core/my_attendance_register.html`
- Modify: `static/css/erp.css` (append `.erp-month-nav`, `.erp-stat-line`, `.erp-student-rows`)
- Test: `core/tests/test_ui_teacher_daily.py`

**Interfaces:**
- Consumes: `_attendance_entries.html` and `.erp-card*` from Task 3.
- Produces: context keys on `my_attendance_assignment`: `previous_month: str | None`, `next_month: str | None` (each `"YYYY-MM"` and a member of `months`), `chosen_label: str` (e.g. `"July 2026"`). Existing keys `row`, `summary`, `registers`, `missing`, `months`, `chosen`, `start`, `end` unchanged.

- [ ] **Step 1: Write the failing tests**

```python
class HistoryTests(U2Fixture, TestCase):
    def month(self, month=None):
        url = reverse("core:my-attendance-assignment", args=[self.duty.pk])
        return self.teacher.get(f"{url}?month={month}" if month else url)

    def test_month_links_in_the_middle(self):
        page = self.month("2026-08")
        self.assertEqual(page.context["previous_month"], "2026-07")
        self.assertEqual(page.context["next_month"], "2026-09")
        self.assertEqual(page.context["chosen_label"], "August 2026")
        self.assertContains(page, "?month=2026-07")
        self.assertContains(page, "?month=2026-09")

    def test_month_links_at_edges(self):
        first = self.month("2026-06")
        self.assertIsNone(first.context["previous_month"])
        self.assertEqual(first.context["next_month"], "2026-07")
        last = self.month()
        self.assertEqual(last.context["chosen"], "2026-10")
        self.assertIsNone(last.context["next_month"])
        self.assertNotContains(last, "Next ›")

    def test_single_month_has_no_links(self):
        row = SectionClassTeacher.assign(
            teacher=self.iyer, academic_year=self.year, section=self.six_b,
            start_date=date(2026, 10, 1),
        )
        iyer = self.client_class()
        iyer.login(username="iyer", password="pass-12345")
        page = iyer.get(reverse("core:my-attendance-assignment", args=[row.pk]))
        self.assertIsNone(page.context["previous_month"])
        self.assertIsNone(page.context["next_month"])

    def test_student_rows_ordered_by_name(self):
        page = self.month().content.decode()
        self.assertLess(page.index("Asha"), page.index("Bina"))
        self.assertLess(page.index("Bina"), page.index("Ravi"))

    def test_history_list_is_cards(self):
        page = self.teacher.get(reverse("core:my-attendance-history"))
        self.assertContains(page, 'class="erp-card')
        self.assertNotContains(page, "<table")

    def test_read_only_register_uses_entry_cards(self):
        self.draft(asha="PRESENT", ravi="PRESENT", bina="ABSENT")
        register = self.register()
        register.submit(actor=self.rao)
        page = self.teacher.get(reverse("core:my-attendance-register", args=[register.pk]))
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily.HistoryTests --noinput`
Expected: FAIL with `KeyError: 'previous_month'` and template assertion failures.

- [ ] **Step 3: Add context in `core/views.py` `my_attendance_assignment`**

`core/views.py` has no `datetime` import; build the label from `month_start` (a `date` returned by `reports.month_bounds`). After `month_start, month_end = reports.month_bounds(*chosen)`, add:

```python
    index = months.index(chosen)
    previous_month = months[index - 1] if index > 0 else None
    next_month = months[index + 1] if index + 1 < len(months) else None
```

and add to the render context dict:

```python
            "previous_month": f"{previous_month[0]:04d}-{previous_month[1]:02d}"
            if previous_month else None,
            "next_month": f"{next_month[0]:04d}-{next_month[1]:02d}" if next_month else None,
            "chosen_label": month_start.strftime("%B %Y"),
```

- [ ] **Step 4: Rewrite `core/templates/core/my_attendance_history.html`**

```django
{% extends "base.html" %}
{% block title %}My attendance history{% endblock %}
{% block content %}
<h1 class="h3 mb-1">Attendance history</h1>
<p class="text-muted">You can see each Section's attendance for the dates you were its class teacher.</p>
{% for row in rows %}
<a class="erp-card d-block text-decoration-none text-reset" href="{% url 'core:my-attendance-assignment' row.pk %}">
    <div class="erp-card-row">
        <div>
            <p class="erp-card-title">{{ row.section }}</p>
            <p class="erp-card-meta">{{ row.academic_year.name }} &middot; from {{ row.start_date|date:"j M Y" }} until {% if row.end_date %}{{ row.end_date|date:"j M Y" }}{% else %}now{% endif %}</p>
        </div>
        <span class="text-primary">Open ›</span>
    </div>
</a>
{% empty %}
{% include "partials/_empty.html" with text="You have not been a class teacher yet." %}
{% endfor %}
{% endblock %}
```

- [ ] **Step 5: Rewrite `core/templates/core/my_attendance_assignment.html`**

```django
{% extends "base.html" %}
{% block title %}Attendance {{ row.section }}{% endblock %}
{% block content %}
<p class="mb-2"><a href="{% url 'core:my-attendance-history' %}">‹ All my Sections</a></p>
<h1 class="h3 mb-1">Attendance: {{ row.section }}</h1>
<p class="text-muted">{{ row.academic_year.name }} &middot; showing {{ start }} to {{ end }}</p>

<nav class="erp-month-nav" aria-label="Month">
    {% if previous_month %}<a href="?month={{ previous_month }}">‹ Previous</a>{% else %}<span></span>{% endif %}
    <strong>{{ chosen_label }}</strong>
    {% if next_month %}<a href="?month={{ next_month }}">Next ›</a>{% else %}<span></span>{% endif %}
</nav>

<p class="erp-stat-line">Expected {{ summary.totals.expected_days }} &middot; Submitted {{ summary.totals.submitted_days }} &middot; Missing {{ summary.totals.missing_days }}{% if summary.totals.percentage is not None %} &middot; {{ summary.totals.percentage }}% present{% endif %}</p>

<h2 class="erp-section-title">Students</h2>
<ul class="erp-student-rows list-unstyled">
    {% for student_row in summary.rows %}
    <li><span>{{ student_row.student.full_name }}</span><span>{{ student_row.present }} P &middot; {{ student_row.absent }} A &middot; {% if student_row.percentage is not None %}{{ student_row.percentage }}%{% else %}&ndash;{% endif %}</span></li>
    {% empty %}
    <li>No Students in this period.</li>
    {% endfor %}
</ul>

<h2 class="erp-section-title">Registers</h2>
{% for register in registers %}
<a class="erp-card d-block text-decoration-none text-reset" href="{% url 'core:my-attendance-register' register.pk %}">
    <div class="erp-card-row">
        <p class="erp-card-title">{{ register.date|date:"D j M" }}</p>
        <span class="erp-pill{% if register.status == 'SUBMITTED' %} is-submitted{% else %} is-draft{% endif %}">{{ register.get_status_display }}</span>
    </div>
    <p class="erp-card-meta">Present {{ register.present }} &middot; Absent {{ register.absent }}</p>
</a>
{% empty %}
<p>No registers in this period.</p>
{% endfor %}

{% if missing %}
<h2 class="erp-section-title">Not taken</h2>
<p>{% for item in missing %}<span class="erp-pill is-pending me-1">{{ item.date|date:"D j M" }}</span>{% endfor %}</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Update `core/templates/core/my_attendance_register.html`**

Read the file first and keep its heading and any text tests assert (`grep -rn "my-attendance-register" core/tests`). Replace its entries table with `{% include "core/_attendance_entries.html" %}` and show the register status as `<span class="erp-pill is-submitted">Submitted</span>` or `<span class="erp-pill is-draft">Draft</span>` according to `register.is_submitted`.

- [ ] **Step 7: Append CSS**

```css
.erp-month-nav {
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: .5rem;
  background: var(--erp-surface); border: 1px solid var(--erp-rule); border-radius: var(--erp-radius);
  padding: .5rem .75rem; margin-bottom: .75rem;
}
.erp-month-nav > :last-child { justify-self: end; }
.erp-stat-line { font-weight: 600; }
.erp-student-rows li {
  display: flex; justify-content: space-between; gap: .75rem; padding: .45rem 0;
  border-bottom: 1px solid var(--erp-rule);
}
.erp-student-rows li span:last-child { white-space: nowrap; color: var(--erp-ink-soft); }
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe manage.py test core.tests.test_ui_teacher_daily core.tests.test_phase5_attendance_views core.tests.test_authorization --noinput`
Expected: `OK`

- [ ] **Step 9: Commit**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
git add core/views.py core/templates/core/my_attendance_history.html core/templates/core/my_attendance_assignment.html core/templates/core/my_attendance_register.html static/css/erp.css core/tests/test_ui_teacher_daily.py
git commit -m "feat(ui): attendance history cards and month page with prev/next"
```

---

### Task 6: Verification and docs

**Files:**
- Modify: `docs/UI_REFERENCES.md` (status line), `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md` (U2 row)

- [ ] **Step 1: Full suite, serial**

Run: `.\.venv\Scripts\python.exe manage.py test --noinput`
Expected: `OK`. The known date-dependent `core.tests.test_models.AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates` may fail if it also fails on `main`; confirm by running that one test on `main` and record the result in the PR.

- [ ] **Step 2: Lint**

Run: `.\.venv\Scripts\python.exe -m ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Manual check**

`.\.venv\Scripts\python.exe manage.py seed_demo` (if not seeded) and `.\.venv\Scripts\python.exe manage.py runserver`. As a class teacher from `seed_demo`, at 360 px and 1280 px: My day; start register; tap Present/Absent (counts update, note appears on Absent); filter tabs; Mark unanswered as present; Save draft (tab bar hidden, action bar sticky); Save and submit with one row unmarked (error shown, draft kept); complete and submit; history list; month page previous/next. As an administrator: office register page draft. With JS disabled: all rows visible, static count line, submit works. No horizontal page scroll at 360 px.

- [ ] **Step 4: Update docs and commit**

In `docs/UI_REFERENCES.md` update the status line to say U2 is implemented on `ui/u2-teacher-daily`. In the roadmap table, change the U2 plan cell to `**U2 Teacher daily screens** (written: \`2026-10-15-ui-u2-teacher-daily.md\`)`.

```powershell
git add docs/UI_REFERENCES.md docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md
git commit -m "docs(ui): mark U2 teacher daily screens implemented"
```
