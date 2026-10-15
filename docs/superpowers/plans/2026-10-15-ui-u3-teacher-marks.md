# U3 Teacher Marks and Students Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phone-friendly marks entry, a read-only gradebook per teaching assignment, and today's attendance chips on My students — without changing how marks or attendance are saved.

**Architecture:** Marks entry keeps `ResultEntryForm` and its POST names; only widgets change (status rendered as three radios, score input gets phone keypad hints) plus a `counts()` helper. A new `my_gradebook` view reads results for one `AssessmentTeacherAssignment`. `my_students` gains per-enrollment attendance status from today's submitted registers. Styling reuses U2 components; one new JS block keyed off `[data-erp-marks]`.

**Tech Stack:** Python 3.13, Django 5.2.17, Bootstrap 5.3.3, Django `TestCase`, ruff.

**Spec:** `docs/superpowers/specs/2026-10-15-ui-u3-teacher-marks-design.md` (approved 2026-10-15).

## Global Constraints

- Branch `ui/u3-teacher-marks` (from `ui/u2-teacher-daily`; rebase onto `main` after PR #47 merges). Uses U2 classes `.erp-card`, `.erp-card-row`, `.erp-card-title`, `.erp-card-meta`, `.erp-roster-row`, `.erp-roster-name`, `.erp-initials`, `.erp-toggles`, `.erp-toggle`, `.erp-note`, `.erp-actionbar`, `.erp-count-tabs`, `.erp-count-line`, `.erp-section-title`, `.erp-entries`, `.erp-entry`, `.erp-entry-name`, `.erp-pill`.
- No model, migration or permission changes. One new view + URL: `my/gradebook/<int:pk>/`, name `core:my-gradebook`.
- Marks entry POST unchanged: `status_<enrollment pk>` = `""` / `MARKED` / `ABSENT`, `score_<enrollment pk>` = decimal or empty. A score with no status still counts as Marked (existing `clean()`).
- Blank is "Not entered" — never zero, never absent. Keep these existing strings exactly: "blank is <strong>not</strong> absent", "An absent Student has no score.", "Not entered", "Absent", "This assessment is finalized", "Marks entry opens on", "My assessments", "Marks saved as draft.", "Marks were not saved. Fix the highlighted rows.".
- No totals, averages, percentages-of-total or ranks in any teacher view added or changed here.
- Works with JS off; every page usable at 360 px; the gradebook table scrolls inside its own box.
- `_assessment_results.html` (office partial with Correct links) is not changed; teacher pages use a new card partial.
- Python line length 100; ruff rules E, F, I, UP, B.
- Quick runs: `env -u DB_NAME .venv/Scripts/python.exe manage.py test <labels> --noinput` (Git Bash, SQLite). Full suite on PostgreSQL in Task 5.

## Review Focus

1. **Invalid POST re-renders the bound form** (unlike attendance, marks entry does not redirect on error) — counts and toggles must show what the teacher typed, not the database. Pinned in Task 1 (`test_counts_use_bound_data`) and Task 2 (`test_invalid_post_keeps_typed_values`).
2. **A score of 0** — "0" is a real mark and must count as marked and show as "0" in the gradebook, not as blank. Pinned in Task 1 (`test_zero_score_counts_as_marked`) and Task 3 (`test_zero_score_shows_zero`).
3. **Another teacher's assignment id in the gradebook URL** — must be 404, never another class's marks. Pinned in Task 3 (`test_other_teachers_assignment_is_404`).
4. **Draft register today** — My students must not show draft entries as Present/Absent. Pinned in Task 4 (`test_draft_register_shows_no_chips`).
5. **Students who joined the Section mid-term** — gradebook rows come from each assessment's own roster; a student only on a later roster still appears with empty cells for earlier assessments. Pinned in Task 3 (`test_rows_union_of_rosters`).

---

## File structure

| File | Responsibility |
|---|---|
| `core/forms.py` (modify `ResultEntryForm`) | Widgets, `counts()` |
| `core/templates/core/assessment_marks_entry.html` (rewrite) | Phone marks entry |
| `core/templates/core/_assessment_result_cards.html` (create) | Teacher read-only results |
| `core/views.py` (add `my_gradebook`; modify `my_students`) | Gradebook data; attendance chips |
| `core/urls.py` (modify) | Gradebook route |
| `core/templates/core/my_gradebook.html` (create) | Gradebook grid |
| `core/templates/core/my_assessments.html` (modify) | Duty cards with Gradebook links |
| `core/templates/core/my_students.html` (rewrite) | Rows with initials and chips |
| `static/css/erp.css`, `static/js/erp.js` (modify) | `.erp-score`, `.erp-grid*`, marks JS |
| `core/tests/test_ui_teacher_marks.py` (create) | All U3 tests |

---

### Task 1: `ResultEntryForm` widgets and `counts()`

**Files:**
- Modify: `core/forms.py` (`ResultEntryForm.__init__`, add `counts()`)
- Create: `core/tests/test_ui_teacher_marks.py`

**Interfaces:**
- Produces: status fields render as radios with choices `("", "Not entered")`, `("MARKED", "Marked")`, `("ABSENT", "Absent")`; score widget attrs `inputmode="decimal"`, `enterkeyhint="next"`, `class="form-control erp-score"`, `step="0.01"`; `ResultEntryForm.counts() -> dict` with int values for `all`, `marked`, `absent`, `unmarked`.
- Produces (tests): fixture `MarksFixture` — business day `MONDAY = date(2026, 10, 12)` patched in `core.views` and `core.models`; enrollments `self.asha`, `self.bina`, `self.ravi` in 6A; `self.duty = self.assign(self.rao, self.maths, self.six_a)`; `self.test1` ("Unit Test 1", 15 Jul 2026), `self.test2` ("Unit Test 2", 22 Jul 2026); logged-in client `self.teacher` (rao); `self.entry_url(assessment)`; `self.result(assessment, enrollment, status, score=None)` saves a draft result.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_ui_teacher_marks.py`:

```python
"""U3 teacher marks and students: marks entry, gradebook, My students."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.forms import ResultEntryForm
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class MarksFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        _, self.asha = self.make_student("Asha")
        _, self.bina = self.make_student("Bina")
        _, self.ravi = self.make_student("Ravi")
        self.duty = self.assign(self.rao, self.maths, self.six_a)
        self.test1 = self.make_assessment(name="Unit Test 1", on=date(2026, 7, 15))
        self.test2 = self.make_assessment(name="Unit Test 2", on=date(2026, 7, 22))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def entry_url(self, assessment):
        return reverse("core:assessment-marks-entry", args=[assessment.pk])

    def result(self, assessment, enrollment, status, score=None):
        assessment.save_draft_result(
            enrollment=enrollment, status=status,
            score=Decimal(score) if score is not None else None, actor=self.rao,
        )


class ResultFormTests(MarksFixture, TestCase):
    def test_counts_use_saved_results(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        form = ResultEntryForm(assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "12",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": "",
                f"status_{self.ravi.pk}": "", f"score_{self.ravi.pk}": ""}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_zero_score_counts_as_marked(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0"}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts()["marked"], 1)

    def test_status_is_three_radios_and_score_has_keypad_hints(self):
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value=""')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="MARKED"')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="ABSENT"')
        self.assertContains(page, 'inputmode="decimal"')
        self.assertContains(page, 'enterkeyhint="next"')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks --noinput`
Expected: 3 errors `AttributeError: 'ResultEntryForm' object has no attribute 'counts'`; `test_status_is_three_radios…` FAIL (status renders as a `<select>`).

- [ ] **Step 3: Implement**

In `core/forms.py` `ResultEntryForm.__init__`, change the two field constructors to:

```python
            self.fields[self.status_name(enrollment)] = forms.ChoiceField(
                choices=[("", "Not entered"), *ResultStatus.choices],
                required=False,
                label=str(enrollment.student),
                initial=result.status if result else "",
                widget=forms.RadioSelect,
            )
            self.fields[self.score_name(enrollment)] = forms.DecimalField(
                required=False,
                min_value=0,
                max_value=assessment.maximum_marks,
                decimal_places=2,
                max_digits=6,
                label="Score",
                initial=result.score if result else None,
                widget=forms.NumberInput(attrs={
                    "step": "0.01", "inputmode": "decimal", "enterkeyhint": "next",
                    "class": "form-control erp-score",
                }),
            )
```

and add after `rows()`:

```python
    def counts(self):
        """Display counts: a score with no status is marked; blank is never absent."""
        marked = absent = 0
        for enrollment in self.enrollments:
            status = self[self.status_name(enrollment)].value() or ""
            score = self[self.score_name(enrollment)].value()
            if status == ResultStatus.ABSENT:
                absent += 1
            elif status == ResultStatus.MARKED or score not in (None, ""):
                marked += 1
        total = len(self.enrollments)
        return {"all": total, "marked": marked, "absent": absent,
                "unmarked": total - marked - absent}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks core.tests.test_phase4_results core.tests.test_phase4_acceptance --noinput`
Expected: `OK`. If an existing test asserted the `<select>` or the "—" option, record a ruling and update it to the radio markup.

- [ ] **Step 5: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/forms.py core/tests/test_ui_teacher_marks.py
git commit -m "feat(ui): marks entry radios, keypad hints and counts helper"
```

---

### Task 2: Phone marks entry page and teacher result cards

**Files:**
- Rewrite: `core/templates/core/assessment_marks_entry.html`
- Create: `core/templates/core/_assessment_result_cards.html`
- Modify: `static/css/erp.css`, `static/js/erp.js`
- Test: `core/tests/test_ui_teacher_marks.py`

**Interfaces:**
- Consumes: Task 1 widgets and `counts()`; view context from `_assessment_context(assessment)` (`assessment`, `rows` = list of `(enrollment, result-or-None)`, `marked_count`, …) plus `form`.
- Produces: hooks `[data-erp-marks]`, `[data-erp-row]`, `[data-erp-tabs]`, `[data-erp-filter]`, `[data-erp-count]`, `[data-erp-static-counts]`, `[data-erp-hint]`; CSS `.erp-score`, `.erp-toggles-3`, `.erp-toggle.is-blank`, `.erp-toggle.is-marked`.

- [ ] **Step 1: Write the failing tests**

```python
class MarksEntryPageTests(MarksFixture, TestCase):
    def test_rows_are_fieldsets_with_static_counts(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, '<legend class="visually-hidden">Asha</legend>')
        self.assertEqual(page.content.decode().count("<fieldset"), 3)
        self.assertContains(page, "All 3 · Not entered 2 · Marked 1 · Absent 0")
        self.assertContains(page, "2 not entered")
        self.assertContains(page, "data-erp-marks")
        self.assertContains(page, "blank is <strong>not</strong> absent")

    def test_invalid_post_keeps_typed_values(self):
        data = {f"status_{self.asha.pk}": "ABSENT", f"score_{self.asha.pk}": "5",
                f"status_{self.bina.pk}": "", f"score_{self.bina.pk}": "11"}
        page = self.teacher.post(self.entry_url(self.test1), data)
        self.assertContains(page, "An absent Student has no score.")
        self.assertContains(page, 'value="11"')
        self.assertContains(page, "All 3 · Not entered 1 · Marked 1 · Absent 1")

    def test_saving_still_works(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": ""}
        response = self.teacher.post(self.entry_url(self.test1), data, follow=True)
        self.assertContains(response, "Marks saved as draft.")
        results = {r.academic_enrollment_id: (r.status, r.score)
                   for r in self.test1.results.all()}
        self.assertEqual(results[self.asha.pk], ("MARKED", Decimal("0")))
        self.assertEqual(results[self.bina.pk][0], "ABSENT")
        self.assertNotIn(self.ravi.pk, results)

    def test_finalized_shows_cards_with_not_entered(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        self.force_finalize(self.test1)
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, "This assessment is finalized")
        self.assertContains(page, "18 / 20")
        self.assertContains(page, "Not entered")
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
        self.assertNotContains(page, "<table")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks.MarksEntryPageTests --noinput`
Expected: FAIL on the fieldset/count assertions and the finalized-card assertions (`test_saving_still_works` may already pass — it guards the POST contract).

- [ ] **Step 3: Create `core/templates/core/_assessment_result_cards.html`**

```django
{# Teacher read-only results. Context: assessment, rows [(enrollment, result-or-None)], marked_count. #}
<p class="text-muted">Roster on {{ assessment.assessment_date }}: {{ rows|length }} Student(s); results entered: {{ marked_count }}. A Student without a result is <strong>not</strong> absent &mdash; entry is incomplete.</p>
<ul class="erp-entries list-unstyled">
    {% for enrollment, result in rows %}
    <li class="erp-entry">
        <span class="erp-entry-name">{{ enrollment.student.full_name }}</span>
        {% if not result %}<span class="text-muted">Not entered</span>
        {% elif result.status == "ABSENT" %}<span class="erp-pill is-absent">Absent</span>
        {% else %}<span>{{ result.score|floatformat:"-2" }} / {{ assessment.maximum_marks|floatformat:"-2" }}{% if result.grade %} &middot; {{ result.grade }}{% endif %}</span>{% endif %}
    </li>
    {% empty %}
    <li>No Students are enrolled in this Section on the assessment date.</li>
    {% endfor %}
</ul>
```

- [ ] **Step 4: Rewrite `core/templates/core/assessment_marks_entry.html`**

```django
{% extends "base.html" %}
{% block title %}Marks: {{ assessment.name }}{% endblock %}
{% block tabbar_class %}{% if not form.enrollments %}{{ block.super }}{% endif %}{% endblock %}
{% block tabbar %}{% if not form.enrollments %}{{ block.super }}{% endif %}{% endblock %}
{% block content %}
<p class="mb-2"><a href="{% url 'core:my-assessments' %}">‹ My assessments</a></p>
<h1 class="h3 mb-1">{{ assessment.offering.subject.name }} {{ assessment.section }}: {{ assessment.name }}</h1>
<p class="text-muted mb-3">{{ assessment.term.name }} &middot; {{ assessment.assessment_date }} &middot; out of {{ assessment.maximum_marks|floatformat:"-2" }}{% if assessment.pass_mark is not None %} &middot; pass mark {{ assessment.pass_mark|floatformat:"-2" }}{% endif %}
    <span class="erp-pill{% if assessment.is_finalized %} is-submitted{% else %} is-draft{% endif %}">{{ assessment.get_status_display }}</span></p>
{% if form %}
<p class="text-muted">Enter a score, or choose Absent. Leave a row blank if you have not marked that Student yet &mdash; blank is <strong>not</strong> absent. An administrator finalizes the results.</p>
{% if form.enrollments %}
<form method="post">
    {% csrf_token %}
    {% with counts=form.counts %}
    <div class="erp-roster" data-erp-marks>
        <p class="erp-count-line" data-erp-static-counts>All {{ counts.all }} · Not entered {{ counts.unmarked }} · Marked {{ counts.marked }} · Absent {{ counts.absent }}</p>
        <div class="erp-count-tabs" data-erp-tabs hidden>
            <button type="button" data-erp-filter="all" aria-pressed="true">All <span data-erp-count="all">{{ counts.all }}</span></button>
            <button type="button" data-erp-filter="unmarked" aria-pressed="false">Not entered <span data-erp-count="unmarked">{{ counts.unmarked }}</span></button>
            <button type="button" data-erp-filter="marked" aria-pressed="false">Marked <span data-erp-count="marked">{{ counts.marked }}</span></button>
            <button type="button" data-erp-filter="absent" aria-pressed="false">Absent <span data-erp-count="absent">{{ counts.absent }}</span></button>
        </div>
        {% for enrollment, status_field, score_field in form.rows %}
        <fieldset class="erp-roster-row" data-erp-row>
            <legend class="visually-hidden">{{ enrollment.student.full_name }}</legend>
            <span class="erp-roster-name" aria-hidden="true">{{ enrollment.student.full_name }}</span>
            <span class="erp-initials" aria-hidden="true">{{ enrollment.student.full_name|slice:":1"|upper }}</span>
            <div class="erp-note is-filled">
                <label class="form-label small mb-1" for="{{ score_field.id_for_label }}">Score out of {{ assessment.maximum_marks|floatformat:"-2" }}<span class="visually-hidden"> for {{ enrollment.student.full_name }}</span></label>
                {{ score_field }}
            </div>
            <div class="erp-toggles erp-toggles-3">
                {% for radio in status_field %}{{ radio.tag }}<label for="{{ radio.id_for_label }}" class="erp-toggle is-{{ radio.data.value|lower|default:'blank' }}">{{ radio.choice_label }}</label>{% endfor %}
            </div>
            {% for error in status_field.errors %}<div class="small text-danger erp-row-error">{{ error }}</div>{% endfor %}
            {% for error in score_field.errors %}<div class="small text-danger erp-row-error">{{ error }}</div>{% endfor %}
        </fieldset>
        {% endfor %}
        <div class="erp-actionbar">
            <span class="erp-actionbar-status" data-erp-hint aria-live="polite">{{ counts.unmarked }} not entered</span>
            <button type="submit" class="btn btn-primary">Save draft</button>
        </div>
    </div>
    {% endwith %}
</form>
{% else %}
{% include "partials/_empty.html" with text="No Students are enrolled in this Section on the assessment date." %}
{% endif %}
{% elif assessment.is_finalized %}
<div class="alert alert-info">This assessment is finalized. Ask an administrator if a result needs correcting.</div>
{% include "core/_assessment_result_cards.html" %}
{% else %}
<div class="alert alert-secondary">Marks entry opens on {{ assessment.assessment_date }}.</div>
{% include "core/_assessment_result_cards.html" %}
{% endif %}
{% endblock %}
```

The old page's submit button had no `name`; the POST stays the same.

- [ ] **Step 5: CSS** — append to `static/css/erp.css` before `/* Wide tables scroll …`:

```css
/* ---------- U3: marks entry ---------- */
.erp-score { font-size: 1.25rem; min-height: 2.75rem; max-width: 10rem; }
.erp-toggles-3 { grid-template-columns: repeat(3, 1fr); }
.erp-toggles input:checked + .erp-toggle.is-marked {
  background: var(--erp-accent); border-color: var(--erp-accent); color: #fff;
}
.erp-toggles input:checked + .erp-toggle.is-blank {
  background: var(--erp-ink-soft); border-color: var(--erp-ink-soft); color: #fff;
}
.erp-toggle.is-blank, .erp-toggle.is-marked { font-size: .9rem; }
.erp-row-error { grid-column: 1 / -1; }
```

- [ ] **Step 6: JS** — append inside the IIFE in `static/js/erp.js`:

```js
  // Marks entry: live counts and filter tabs; typing a score selects Marked;
  // Absent clears and disables the score box. Without JS the server rules apply.
  document.querySelectorAll("[data-erp-marks]").forEach(function (sheet) {
    var rows = Array.prototype.slice.call(sheet.querySelectorAll("[data-erp-row]"));
    var tabs = sheet.querySelector("[data-erp-tabs]");
    var staticCounts = sheet.querySelector("[data-erp-static-counts]");
    var hint = sheet.querySelector("[data-erp-hint]");
    var filter = "all";

    function parts(row) {
      return {
        score: row.querySelector("input.erp-score"),
        checked: row.querySelector('input[type="radio"]:checked'),
        marked: row.querySelector('input[type="radio"][value="MARKED"]'),
      };
    }

    function statusOf(row) {
      var p = parts(row);
      var value = p.checked ? p.checked.value : "";
      if (value === "ABSENT") return "absent";
      if (value === "MARKED" || (p.score && p.score.value.trim() !== "")) return "marked";
      return "unmarked";
    }

    function refresh() {
      var counts = { all: rows.length, marked: 0, absent: 0, unmarked: 0 };
      rows.forEach(function (row) {
        var status = statusOf(row);
        counts[status] += 1;
        row.hidden = filter !== "all" && filter !== status;
        var p = parts(row);
        if (p.score) p.score.disabled = status === "absent";
      });
      Object.keys(counts).forEach(function (key) {
        var target = sheet.querySelector('[data-erp-count="' + key + '"]');
        if (target) target.textContent = counts[key];
      });
      if (hint) hint.textContent = counts.unmarked + " not entered";
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

    sheet.addEventListener("input", function (event) {
      if (!event.target.classList.contains("erp-score")) return;
      var p = parts(event.target.closest("[data-erp-row]"));
      if (event.target.value.trim() !== "" && (!p.checked || p.checked.value === "")) {
        p.marked.checked = true;
      }
      refresh();
    });
    sheet.addEventListener("change", function (event) {
      if (event.target.type !== "radio") return;
      var p = parts(event.target.closest("[data-erp-row]"));
      if (event.target.value === "ABSENT" && p.score) p.score.value = "";
      refresh();
    });
    refresh();
  });
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks core.tests.test_phase4_results core.tests.test_phase4_acceptance core.tests.test_phase4_finalization core.tests.test_phase5_acceptance --noinput`
Expected: `OK`. Keep any string those tests assert.

- [ ] **Step 8: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/templates/core/assessment_marks_entry.html core/templates/core/_assessment_result_cards.html static/css/erp.css static/js/erp.js core/tests/test_ui_teacher_marks.py
git commit -m "feat(ui): phone marks entry with toggles, counts and result cards"
```

---

### Task 3: Gradebook and My assessments cards

**Files:**
- Modify: `core/views.py` (add `my_gradebook` after `my_assessments`), `core/urls.py`, `core/templates/core/my_assessments.html`
- Create: `core/templates/core/my_gradebook.html`
- Modify: `static/css/erp.css`
- Test: `core/tests/test_ui_teacher_marks.py`

**Interfaces:**
- Consumes: `teacher_assignments(user)` (queryset of `AssessmentTeacherAssignment` with `offering`, `section`); `_assessments()`; `Assessment.roster()` (enrollments); `StudentResult` (`assessment`, `academic_enrollment`, `status`, `score`); `teacher_required`.
- Produces: URL name `core:my-gradebook` (`my/gradebook/<int:pk>/`); context `duty`, `assessments` (list), `rows` (list of `{"student": Student, "cells": [StudentResult | None, …]}` in assessment order; students ordered by name).

- [ ] **Step 1: Write the failing tests**

```python
class GradebookTests(MarksFixture, TestCase):
    def url(self, duty=None):
        return reverse("core:my-gradebook", args=[(duty or self.duty).pk])

    def test_cells_show_score_abs_or_empty(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        page = self.teacher.get(self.url())
        rows = {row["student"].full_name: row["cells"] for row in page.context["rows"]}
        self.assertEqual(rows["Asha"][0].score, Decimal("18"))
        self.assertEqual(rows["Bina"][0].status, "ABSENT")
        self.assertIsNone(rows["Ravi"][0])
        self.assertIsNone(rows["Asha"][1])
        self.assertContains(page, ">Abs<")

    def test_zero_score_shows_zero(self):
        self.result(self.test1, self.asha, "MARKED", "0")
        self.assertContains(self.teacher.get(self.url()), ">0<")

    def test_no_totals_or_ranks(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.url())
        for word in ("Total", "Average", "Rank"):
            self.assertNotContains(page, word)

    def test_students_by_name_and_headers_link_to_entry(self):
        page = self.teacher.get(self.url())
        self.assertEqual([r["student"].full_name for r in page.context["rows"]],
                         ["Asha", "Bina", "Ravi"])
        self.assertContains(page, self.entry_url(self.test1))
        self.assertContains(page, self.entry_url(self.test2))

    def test_draft_and_finalized_columns_differ(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test2, self.asha, "MARKED", "15")
        self.force_finalize(self.test2)
        page = self.teacher.get(self.url()).content.decode()
        self.assertEqual(page.count('class="is-draft"'), 1)
        self.assertEqual(page.count("(draft)"), 1)

    def test_rows_union_of_rosters(self):
        later = self.make_assessment(name="Unit Test 3", on=date(2026, 9, 10))
        _, kiran = self.make_student("Kiran", start=date(2026, 8, 1))
        page = self.teacher.get(self.url())
        cells = {r["student"].full_name: r["cells"] for r in page.context["rows"]}
        self.assertEqual(len(cells["Kiran"]), 3)
        self.assertIsNone(cells["Kiran"][0])
        self.assertTrue(later.roster().filter(pk=kiran.pk).exists())

    def test_other_teachers_assignment_is_404(self):
        other = self.assign(self.iyer, self.sanskrit, self.six_b)
        self.assertEqual(self.teacher.get(self.url(other)).status_code, 404)

    def test_non_teacher_is_forbidden(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_my_assessments_links_gradebook(self):
        page = self.teacher.get(reverse("core:my-assessments"))
        self.assertContains(page, "My assessments")
        self.assertContains(page, self.url())
        self.assertContains(page, "Unit Test 1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks.GradebookTests --noinput`
Expected: ERROR — `NoReverseMatch: Reverse for 'my-gradebook' not found`.

- [ ] **Step 3: View and URL**

In `core/views.py`, after `my_assessments` (`StudentResult`, `teacher_assignments`, `teacher_required` and `_assessments` are already available in the module — check with grep):

```python
@teacher_required
def my_gradebook(request, pk):
    """Read-only marks for one of the teacher's Subject + Section assignments."""
    duty = get_object_or_404(teacher_assignments(request.user), pk=pk)
    assessments = list(
        _assessments()
        .filter(offering=duty.offering, section=duty.section)
        .order_by("assessment_date", "name", "pk")
    )
    students = {}
    for assessment in assessments:
        for enrollment in assessment.roster().select_related("student"):
            students[enrollment.student_id] = enrollment.student
    results = {
        (result.academic_enrollment.student_id, result.assessment_id): result
        for result in StudentResult.objects.filter(assessment__in=assessments).select_related(
            "academic_enrollment", "assessment"
        )
    }
    rows = [
        {"student": student, "cells": [results.get((student.pk, a.pk)) for a in assessments]}
        for student in sorted(students.values(), key=lambda s: (s.full_name.casefold(), s.pk))
    ]
    return render(
        request,
        "core/my_gradebook.html",
        {"duty": duty, "assessments": assessments, "rows": rows},
    )
```

In `core/urls.py`, next to the other teacher routes (check their prefix with `grep -n '"my/' core/urls.py` and match it):

```python
    path("my/gradebook/<int:pk>/", views.my_gradebook, name="my-gradebook"),
```

- [ ] **Step 4: Templates**

`core/templates/core/my_gradebook.html`:

```django
{% extends "base.html" %}
{% block title %}Gradebook {{ duty.offering.subject.name }} {{ duty.section }}{% endblock %}
{% block content %}
<p class="mb-2"><a href="{% url 'core:my-assessments' %}">‹ My assessments</a></p>
<h1 class="h3 mb-1">Gradebook</h1>
<p class="text-muted">{{ duty.offering.subject.name }} &middot; {{ duty.section }} &middot; {{ duty.offering.academic_year.name }}. Empty means not entered yet, not absent.</p>
{% if assessments %}
<div class="erp-grid-scroll">
<table class="erp-grid erp-keep">
    <caption class="visually-hidden">Marks for {{ duty.offering.subject.name }}, {{ duty.section }}</caption>
    <thead><tr>
        <th scope="col">Student</th>
        {% for assessment in assessments %}
        <th scope="col"><a href="{% url 'core:assessment-marks-entry' assessment.pk %}">{{ assessment.name }}</a>
            <span class="erp-grid-meta">{{ assessment.assessment_date|date:"j M" }} &middot; / {{ assessment.maximum_marks|floatformat:"-2" }}</span>
            <span class="erp-pill{% if assessment.is_finalized %} is-submitted{% else %} is-draft{% endif %}">{{ assessment.get_status_display }}</span></th>
        {% endfor %}
    </tr></thead>
    <tbody>
        {% for row in rows %}
        <tr>
            <th scope="row">{{ row.student.full_name }}</th>
            {% for result in row.cells %}
            <td{% if result and not result.assessment.is_finalized %} class="is-draft"{% endif %}>{% if result %}{% if result.status == "ABSENT" %}Abs{% else %}{{ result.score|floatformat:"-2" }}{% endif %}{% if not result.assessment.is_finalized %}<span class="visually-hidden"> (draft)</span>{% endif %}{% endif %}</td>
            {% endfor %}
        </tr>
        {% endfor %}
    </tbody>
</table>
</div>
{% else %}
{% include "partials/_empty.html" with text="No assessments for this Subject and Section yet." %}
{% endif %}
{% endblock %}
```

`core/templates/core/my_assessments.html` — read the current file; keep the heading "My assessments" and the whole "Term remarks" section unchanged; replace the intro paragraph and the assessments table with:

```django
{% for duty in duties %}
<div class="erp-card">
    <div class="erp-card-row">
        <p class="erp-card-title">{{ duty.offering.subject.name }} &middot; {{ duty.section }} <span class="erp-card-meta">({{ duty.offering.academic_year.name }})</span></p>
        <a class="btn btn-outline-primary btn-sm" href="{% url 'core:my-gradebook' duty.pk %}">Gradebook</a>
    </div>
    <ul class="list-unstyled mb-0 mt-2">
        {% for assessment in assessments %}{% if assessment.offering_id == duty.offering_id and assessment.section_id == duty.section_id %}
        <li class="d-flex justify-content-between gap-2 py-1"><a href="{% url 'core:assessment-marks-entry' assessment.pk %}">{{ assessment.name }}</a><span class="text-muted small">{{ assessment.assessment_date|date:"j M" }} &middot; <span class="erp-pill{% if assessment.is_finalized %} is-submitted{% else %} is-draft{% endif %}">{{ assessment.get_status_display }}</span></span></li>
        {% endif %}{% endfor %}
    </ul>
</div>
{% empty %}
<p class="text-muted">You enter marks for nothing yet &mdash; ask an administrator to assign you.</p>
{% endfor %}
```

- [ ] **Step 5: CSS** — append:

```css
/* ---------- U3: gradebook ---------- */
.erp-grid-scroll { overflow-x: auto; border: 1px solid var(--erp-rule); border-radius: var(--erp-radius); background: var(--erp-surface); }
.erp-grid { border-collapse: separate; border-spacing: 0; font-size: .9rem; }
.erp-grid th, .erp-grid td { padding: .45rem .6rem; border-bottom: 1px solid var(--erp-rule); text-align: center; white-space: nowrap; }
.erp-grid thead th { vertical-align: bottom; font-weight: 600; }
.erp-grid tbody th, .erp-grid thead th:first-child {
  position: sticky; left: 0; z-index: 1; background: var(--erp-surface); text-align: left;
  border-right: 1px solid var(--erp-rule);
}
.erp-grid-meta { display: block; font-weight: 400; color: var(--erp-ink-soft); font-size: .8rem; }
.erp-grid td.is-draft { font-style: italic; color: var(--erp-ink-soft); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks core.tests.test_phase4_results core.tests.test_phase5_acceptance --noinput`
Expected: `OK`. If an existing test asserted the old My assessments table text, keep that text (record a ruling).

- [ ] **Step 7: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/views.py core/urls.py core/templates/core/my_gradebook.html core/templates/core/my_assessments.html static/css/erp.css core/tests/test_ui_teacher_marks.py
git commit -m "feat(ui): teacher gradebook and My assessments cards"
```

---

### Task 4: My students rows and today's attendance chips

**Files:**
- Modify: `core/views.py` (`my_students`)
- Rewrite: `core/templates/core/my_students.html`
- Test: `core/tests/test_ui_teacher_marks.py`

**Interfaces:**
- Consumes: existing `groups` context (list of `{"section", "is_class_teacher", "enrollments"}`); `AttendanceRegister` (`date`, `section`, `status`, `Status.SUBMITTED`), `AttendanceEntry` (`register`, `academic_enrollment`, `status`).
- Produces: each enrollment object gets attribute `today_status` (`"PRESENT"`, `"ABSENT"` or `None`); each group dict gets `"attendance_submitted": bool`. Existing context keys unchanged.

- [ ] **Step 1: Write the failing tests**

Add `from core.models import AttendanceRegister, SectionClassTeacher` to the imports, then append:

```python
class MyStudentsTests(MarksFixture, TestCase):
    def setUp(self):
        super().setUp()
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 6, 1))
        self.url = reverse("core:my-students")

    def register(self, submit):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY
        )
        register.save_draft_entry(enrollment=self.asha, status="PRESENT")
        register.save_draft_entry(enrollment=self.bina, status="ABSENT")
        register.save_draft_entry(enrollment=self.ravi, status="PRESENT")
        if submit:
            register.submit(actor=self.rao)
        return register

    def test_submitted_register_shows_chips(self):
        self.register(submit=True)
        page = self.teacher.get(self.url)
        self.assertContains(page, '<span class="erp-pill is-present">Present</span>', count=2)
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>', count=1)
        self.assertNotContains(page, "not submitted yet")

    def test_draft_register_shows_no_chips(self):
        self.register(submit=False)
        page = self.teacher.get(self.url)
        self.assertNotContains(page, "erp-pill is-present")
        self.assertNotContains(page, "erp-pill is-absent")
        self.assertContains(page, "Today's attendance not submitted yet")

    def test_subject_only_section_has_no_chips_or_note(self):
        self.make_student("Kiran", section=self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.register(submit=True)
        page = self.teacher.get(self.url).content.decode()
        six_b_part = page[page.index(str(self.six_b)):]
        self.assertNotIn("erp-pill is-present", six_b_part)
        self.assertNotIn("not submitted yet", six_b_part)

    def test_rows_have_initials_and_links(self):
        page = self.teacher.get(self.url)
        self.assertContains(page, 'class="erp-initials"')
        self.assertContains(page, reverse("core:my-student-detail", args=[self.asha.student.pk]))
```

(`test_subject_only_section_has_no_chips_or_note` assumes the 6B group renders after 6A, as groups are ordered by Section name.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks.MyStudentsTests --noinput`
Expected: FAIL (no chips, no note, no initials).

- [ ] **Step 3: View**

In `core/views.py` `my_students`, after `class_sections = set(...)` and before the groups loop (add `AttendanceEntry` to the `core.models` import list if missing):

```python
    submitted_sections = set(
        AttendanceRegister.objects.filter(
            date=today, section_id__in=class_sections,
            status=AttendanceRegister.Status.SUBMITTED,
        ).values_list("section_id", flat=True)
    )
    today_status = dict(
        AttendanceEntry.objects.filter(
            register__date=today, register__section_id__in=submitted_sections,
            register__status=AttendanceRegister.Status.SUBMITTED,
        ).values_list("academic_enrollment_id", "status")
    )
```

In the loop, set `enrollment.today_status = today_status.get(enrollment.pk)` for every enrollment, and add `"attendance_submitted": enrollment.section_id in submitted_sections` to each new group dict.

- [ ] **Step 4: Template `core/templates/core/my_students.html`**

```django
{% extends "base.html" %}
{% block title %}My students{% endblock %}
{% block content %}
<h1 class="h3 mb-1">My students</h1>
<p class="text-muted">Students enrolled today ({{ today }}) in Sections you are class teacher of or teach a Subject in.</p>
{% for group in groups %}
<h2 class="erp-section-title">{{ group.section }} {% if group.is_class_teacher %}<span class="erp-pill is-accepted">Class teacher</span>{% endif %}</h2>
{% if group.is_class_teacher and not group.attendance_submitted %}<p class="text-muted small mb-2">Today's attendance not submitted yet.</p>{% endif %}
<ul class="erp-entries list-unstyled">
    {% for enrollment in group.enrollments %}
    <li class="erp-entry">
        <span class="erp-initials" aria-hidden="true">{{ enrollment.student.full_name|slice:":1"|upper }}</span>
        <a class="erp-entry-name" href="{% url 'core:my-student-detail' enrollment.student.pk %}">{{ enrollment.student.full_name }}</a>
        {% if group.is_class_teacher and enrollment.today_status %}<span class="erp-pill is-{{ enrollment.today_status|lower }}">{% if enrollment.today_status == "PRESENT" %}Present{% else %}Absent{% endif %}</span>{% endif %}
    </li>
    {% endfor %}
</ul>
{% empty %}
{% include "partials/_empty.html" with text="No Students in your Sections today." %}
{% endfor %}
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_ui_teacher_marks core.tests.test_phase5_student_access core.tests.test_phase5_acceptance --noinput`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
.venv/Scripts/python.exe -m ruff check .
git add core/views.py core/templates/core/my_students.html core/tests/test_ui_teacher_marks.py
git commit -m "feat(ui): My students rows with initials and today's attendance chips"
```

---

### Task 5: Verification and docs

**Files:**
- Modify: `docs/UI_REFERENCES.md` (status line), `docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md` (U3 row)

- [ ] **Step 1: Full suite on PostgreSQL** (PowerShell, DB variables loaded): `.\.venv\Scripts\python.exe -m ruff check .`; `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`; `.\.venv\Scripts\python.exe manage.py test --noinput` (add `--parallel 4` if PR #48 is merged). Expected: clean, `No changes detected`, all pass except the known pre-existing date-dependent failure.

- [ ] **Step 2: Manual check** — throwaway SQLite database as for U2 (scratch settings module, `migrate`, seed `Phase4Fixture` + `assign(rao, maths, six_a)` + two assessments + five students + class-teacher duty), dev server, as `rao` at 360 px and 1280 px: marks entry (typing a score selects Marked, Absent clears the score, counts/tabs update, Save draft), finalized view cards, gradebook scrolls sideways with the name column fixed, My assessments cards, My students chips after submitting today's register. No horizontal page scroll.

- [ ] **Step 3: Docs and commit** — status line in `docs/UI_REFERENCES.md` adds "U3 Teacher marks and students implemented on branch `ui/u3-teacher-marks`"; roadmap U3 cell becomes `**U3 Teacher marks and students** (written: \`2026-10-15-ui-u3-teacher-marks.md\`)`.

```bash
git add docs/UI_REFERENCES.md docs/superpowers/plans/2026-10-14-ui-redesign-roadmap.md
git commit -m "docs(ui): mark U3 teacher marks and students implemented"
```
