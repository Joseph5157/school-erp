# Admin UI/UX Phase 0 – Safety & Correctness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six Phase 0 findings from the Administrator UI/UX audit (F02, F03, F06, F11, F16, F24) so destructive admin actions are confirmed and audited and the most visible data-display defects are gone.

**Architecture:** Server-rendered Django. High-impact actions (student deactivation, applicant accept/reject) get a GET confirm page that shows consequences and collects a mandatory reason, then POST to the existing endpoint, which now validates the reason and stores it. Reasons are stored on a new field and a new audit row (one migration). Display fixes are template/query-only.

**Tech Stack:** Django, Postgres (dev) / SQLite fallback, Bootstrap classes already in `base.html`, `django.test.TestCase`.

**Spec:** `School_ERP_Admin_UI_UX_Audit.pdf` (repo root) – findings F02, F03, F06, F11, F16, F24; Phase 0 list on p.14. ADR constraints: `docs/adr/0003-phase-1-status-and-transition-rules.md` (ACCEPTED/REJECTED are final; Student status is ACTIVE/INACTIVE only).

## Global Constraints

- Button text names the outcome, sentence case: "Deactivate student", "Accept applicant", "Reject applicant" (audit content rules, p.13).
- Empty grade display is exactly `Not graded`.
- Reactivating a student (INACTIVE→ACTIVE) stays a direct POST with no reason (the audit only flags deactivation).
- The existing guardian access-review step for deactivation (`student_access_review.html`, `_grants_needing_review`) must keep working; the reason step comes first, the access review second.
- New views use `@administrator_required("core.change_student")` / `("core.change_applicant")`, same as the endpoints they front.
- Run tests with `.venv\Scripts\python.exe manage.py test --parallel 4` (one date-dependent test already fails on main – memory `test-suite-running`).
- One commit per task; branch `ui/phase0-safety-fixes` (already created).

## Review Focus

1. Double decision: POSTing Accept after Reject (or two quick Accepts) must not change the record and must show the model's error, not a 500. (Task 4)
2. Deactivate POST with blank/whitespace reason is rejected; student stays ACTIVE. (Task 3)
3. Student with active guardian grants: reason page → access-review page → saved, with the reason preserved through the hidden-field round trip. (Task 3)
4. Student search label must still show when the query is non-empty or returns no results. (Task 6)
5. Two registers on the same date must order deterministically (section tiebreak). (Task 1)

---

## File Structure

| File | Responsibility |
|---|---|
| `core/models.py` | `Applicant.admission_decision_reason`; new `StudentStatusChange` audit row; `record_admission_decision(decision, reason="")`; `Student.record_status_change(..., reason="")` writes the audit row |
| `core/migrations/0067_phase0_decision_reasons.py` | Generated migration for the two model changes |
| `core/forms.py` | `AdmissionDecisionForm` and `StudentStatusForm` gain optional `reason` |
| `core/views.py` | new `student_deactivate_confirm`, `applicant_decision_confirm`; update `student_status_change`, `applicant_admission_decision`; sort fix (already edited) |
| `core/urls.py` | two new routes |
| `core/templates/core/student_deactivate_confirm.html` | consequence summary + reason form |
| `core/templates/core/applicant_decision_confirm.html` | consequence summary + reason form |
| `core/templates/core/student_detail.html`, `applicant_detail.html` | buttons become links to confirm pages; show stored reason/history |
| `core/templates/core/_result_cells.html`, `_assessment_results.html`, `publication_detail.html` | `Not graded` |
| `core/templates/core/student_list.html` | search label + clear link |
| `core/templates/core/attendance_correction_form.html` | Cancel link |
| `core/tests/test_ui_admin_phase0.py` | all new tests for this plan |
| `core/tests/test_acceptance.py`, `test_authorization.py`, `test_phase4_acceptance.py`, `test_phase6_access_boundary.py` | update the 16 existing direct POSTs to include the new `reason` |

---

### Task 1: F06 – Attendance register list newest-first

**Files:**
- Modify: `core/views.py` (`attendance_register_list` `.order_by(...)` – already edited, uncommitted)
- Create: `core/tests/test_ui_admin_phase0.py`

- [ ] **Step 1: Write the failing test**

Reuse the fixture used by `AttendanceCorrectionAuthorizationTests` (`AuthorizationClientsMixin`, `AttendanceFixtureMixin`, both in `core/tests/test_authorization.py`).

```python
from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import AttendanceRegister
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin


class AttendanceListOrderTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()

    def test_registers_listed_newest_date_first(self):
        base = AttendanceRegister.objects.first()
        for day in (1, 13, 8):
            AttendanceRegister.objects.create(
                academic_year=base.academic_year, class_grade=base.class_grade,
                section=base.section, date=date(2026, 9, day),
            )
        response = self.administrator.get(reverse("core:attendance-register-list"))
        dates = [r.date for r in response.context["registers"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
```

If `create` needs more required fields, copy the construction used inside `AttendanceFixtureMixin.build_attendance_fixture`.

- [ ] **Step 2: Run to verify it fails**

`git stash push core/views.py`, then `.venv\Scripts\python.exe manage.py test core.tests.test_ui_admin_phase0.AttendanceListOrderTests` → FAIL (not descending). Then `git stash pop`.

- [ ] **Step 3: Implementation** – already in the working tree: `.order_by("-date", "section__class_grade", "section")`.

- [ ] **Step 4: Run test → PASS**

- [ ] **Step 5: Commit**
```bash
git add core/views.py core/tests/test_ui_admin_phase0.py
git commit -m "fix(ui): list attendance registers newest first (F06)"
```

---

### Task 2: F16 – "Not graded" instead of blank grade cells

**Files:**
- Modify: `core/templates/core/_result_cells.html:4`, `core/templates/core/_assessment_results.html:15`, `core/templates/core/publication_detail.html:15`
- Test: `core/tests/test_ui_admin_phase0.py`

**Interfaces:** Produces the display string `Not graded` (exact), asserted by tests.

- [ ] **Step 1: Failing test**

```python
from types import SimpleNamespace
from django.template.loader import render_to_string


class NotGradedDisplayTests(TestCase):
    def render_cells(self, grade):
        result = SimpleNamespace(
            status="MARKED", score=7, percentage=70, grade=grade, pass_fail="PASS",
            assessment=SimpleNamespace(maximum_marks=10),
        )
        return render_to_string("core/_result_cells.html", {"result": result})

    def test_blank_grade_shows_not_graded(self):
        self.assertIn("Not graded", self.render_cells(""))

    def test_real_grade_is_shown_not_placeholder(self):
        html = self.render_cells("A")
        self.assertIn(">A<", html)
        self.assertNotIn("Not graded", html)
```

- [ ] **Step 2: Run** → first test FAILS.
- [ ] **Step 3: Implement.** `_result_cells.html` line 4 and `_assessment_results.html` line 15: `{{ result.grade|default:"" }}` → `{{ result.grade|default:"Not graded" }}`. `publication_detail.html` line 15: `{{ e.grade_label|default:"" }}` → `{{ e.grade_label|default:"Not graded" }}`.
- [ ] **Step 4: Run both tests plus** `core.tests.test_phase4_results core.tests.test_phase6_publication` → PASS.
- [ ] **Step 5: Commit** `fix(ui): show "Not graded" for blank grades (F16)`

---

### Task 3: F02 – Student deactivation: confirm page + mandatory reason + audit row

**Files:**
- Modify: `core/models.py` (add `StudentStatusChange`; extend `Student.record_status_change`), `core/forms.py` (`StudentStatusForm`), `core/views.py` (`student_status_change`, new `student_deactivate_confirm`), `core/urls.py` (near line 223), `core/templates/core/student_detail.html:26-40`
- Create: `core/templates/core/student_deactivate_confirm.html`; migration is generated once in Task 4 Step 3 for both model changes
- Test: `core/tests/test_ui_admin_phase0.py`

**Interfaces:**
- Produces: `StudentStatusChange(student FK related_name="status_changes", previous_status, new_status, reason, changed_by FK null, created_at)`.
- Produces: `Student.record_status_change(new_status, *, actor=None, access_decisions=None, access_note="", reason="")`. For INACTIVE with blank `reason.strip()` it raises `ValidationError("A reason is required to deactivate a Student.")`. Every successful change writes one `StudentStatusChange` row in the same transaction.
- Produces: URL name `core:student-deactivate-confirm` (`students/<int:pk>/deactivate/`, GET).
- Consumes: existing `_grants_needing_review`, `_access_review_page`. The page re-posts every POST field as hidden inputs, so `reason` survives the access-review step unchanged.

- [ ] **Step 1: Failing tests**

```python
class DeactivateStudentTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = Student.objects.create(full_name="Asha Rao")  # ACTIVE by default
        self.url = reverse("core:student-status-change", args=[self.student.pk])

    def test_confirm_page_shows_student_and_reason_field(self):
        r = self.administrator.get(reverse("core:student-deactivate-confirm", args=[self.student.pk]))
        self.assertContains(r, "Asha Rao")
        self.assertContains(r, 'name="reason"')

    def test_post_without_reason_is_rejected_and_student_stays_active(self):
        self.administrator.post(self.url, {"status": "INACTIVE", "reason": "   "})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "ACTIVE")
        self.assertFalse(self.student.status_changes.exists())

    def test_post_with_reason_deactivates_and_records_audit_row(self):
        self.administrator.post(self.url, {"status": "INACTIVE", "reason": "Left the school"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "INACTIVE")
        change = self.student.status_changes.get()
        self.assertEqual((change.previous_status, change.new_status, change.reason),
                         ("ACTIVE", "INACTIVE", "Left the school"))
        self.assertEqual(change.changed_by, self.admin_user)

    def test_reactivation_needs_no_reason(self):
        self.administrator.post(self.url, {"status": "INACTIVE", "reason": "x"})
        self.administrator.post(self.url, {"status": "ACTIVE"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "ACTIVE")
        self.assertEqual(self.student.status_changes.count(), 2)

    def test_confirm_page_requires_permission(self):
        url = reverse("core:student-deactivate-confirm", args=[self.student.pk])
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        self.assertEqual(self.anonymous.get(url).status_code, 302)

    def test_confirm_page_for_inactive_student_redirects_to_detail(self):
        self.administrator.post(self.url, {"status": "INACTIVE", "reason": "x"})
        r = self.administrator.get(reverse("core:student-deactivate-confirm", args=[self.student.pk]))
        self.assertRedirects(r, reverse("core:student-detail", args=[self.student.pk]))
```

Also add a grants test using the guardian-grant fixture style from `core/tests/test_phase6_access_boundary.py`: student with an active grant → POST INACTIVE + reason returns the access-review page containing `<input type="hidden" name="reason" value="…">`; second POST with `access_review=1` and decisions completes and the stored `change.reason` equals the typed reason.

- [ ] **Step 2: Run** → FAIL (no URL / no `status_changes`).
- [ ] **Step 3: Implement**
  - Model (`core/models.py`, after `Student`):
    ```python
    class StudentStatusChange(models.Model):
        student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="status_changes")
        previous_status = models.CharField(max_length=10, choices=Student.Status.choices)
        new_status = models.CharField(max_length=10, choices=Student.Status.choices)
        reason = models.TextField(blank=True)
        changed_by = models.ForeignKey(
            settings.AUTH_USER_MODEL, null=True, blank=True,
            on_delete=models.PROTECT, related_name="+",
        )
        created_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            ordering = ["-created_at", "-pk"]
    ```
    Match whatever user-model import `models.py` already uses for other `changed_by`/`decided_by` FKs.
  - `Student.record_status_change`: add `reason=""`; after the allowed/no-op checks, `if new_status == INACTIVE and not reason.strip(): raise ValidationError("A reason is required to deactivate a Student.")`; capture `previous = self.status`; after the `self.save(...)` inside the atomic block: `StudentStatusChange.objects.create(student=self, previous_status=previous, new_status=new_status, reason=reason.strip(), changed_by=actor)`.
  - Form: `StudentStatusForm.reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))`.
  - View `student_status_change`: pass `reason=form.cleaned_data["reason"]` to `record_status_change`. The existing `ValidationError` branch flashes the message and redirects to the detail page. Note the reason check must happen **before** the access-review page would be shown, so in the `INACTIVE` branch at the top of the view add:
    ```python
    if form.cleaned_data["status"] == Student.Status.INACTIVE and not form.cleaned_data["reason"].strip():
        messages.error(request, "A reason is required to deactivate a Student.")
        return redirect("core:student-deactivate-confirm", pk=student.pk)
    ```
  - New view:
    ```python
    @administrator_required("core.change_student")
    def student_deactivate_confirm(request, pk):
        student = get_object_or_404(Student, pk=pk)
        if student.status != Student.Status.ACTIVE:
            return redirect("core:student-detail", pk=student.pk)
        return render(request, "core/student_deactivate_confirm.html", {
            "student": student,
            "grants": list(guardian_access.active_grants_for(student)),
            "placement": student.enrollments.filter(
                status=AcademicEnrollment.Status.ACTIVE
            ).first(),
        })
    ```
  - Template `student_deactivate_confirm.html` (extends `base.html`): H1 "Deactivate student"; `{{ student.full_name }}`; bullet list of consequences – student leaves active student lists; current placement `{{ placement|default:"none" }}` stays as history; `{{ grants|length }}` guardian(s) with portal access need a retain/revoke decision on the next step (only when `grants`); this is recorded in the student's status history. Form posts to `{% url 'core:student-status-change' student.pk %}` with `{% csrf_token %}`, hidden `status=INACTIVE`, `<label for="reason">Reason (required)</label><textarea name="reason" id="reason" rows="3" class="form-control" required></textarea>`, primary button "Deactivate student", `Cancel` link to `core:student-detail`.
  - `student_detail.html`: replace the Deactivate `<form>` (lines 29-33) with `<a class="btn btn-warning" href="{% url 'core:student-deactivate-confirm' student.pk %}">Deactivate student…</a>`; keep the Reactivate form; add a "Status history" table (`student.status_changes.all`: When, From, To, Reason, By).
  - URLs: `path("students/<int:pk>/deactivate/", views.student_deactivate_confirm, name="student-deactivate-confirm")` beside the `student-status-change` route.
- [ ] **Step 4: Run (after Task 4 Step 3 has created the migration)** the new tests → PASS.
- [ ] **Step 5: Commit** `feat(ui): confirm page, mandatory reason and audit row for student deactivation (F02)`

---

### Task 4: F03 – Applicant accept/reject: review step, rejection reason, no double decisions

**Files:**
- Modify: `core/models.py` (`Applicant.admission_decision_reason`, `record_admission_decision`), `core/forms.py` (`AdmissionDecisionForm`), `core/views.py` (`applicant_admission_decision`, new `applicant_decision_confirm`), `core/urls.py`, `core/templates/core/applicant_detail.html:20-34`
- Create: `core/templates/core/applicant_decision_confirm.html`, `core/migrations/0067_phase0_decision_reasons.py`
- Test: `core/tests/test_ui_admin_phase0.py`

**Interfaces:**
- Produces: `Applicant.admission_decision_reason = TextField(blank=True, default="")`.
- Produces: `record_admission_decision(decision, reason="")`; for REJECTED with blank reason raises `ValidationError("A reason is required to reject an applicant.")`. The existing `admission_status != PENDING` check stays and is the double-decision guard.
- Produces: URL name `core:applicant-decision-confirm` (`applicants/<int:pk>/decide/<str:decision>/`, GET; `decision` must be `ACCEPTED` or `REJECTED`, else 404). Place beside the existing `applicant-admission-decision` route.

- [ ] **Step 1: Failing tests**

```python
class ApplicantDecisionTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.applicant = Applicant.objects.create(full_name="Ravi Kumar")  # PENDING by default
        self.decide_url = reverse("core:applicant-admission-decision", args=[self.applicant.pk])

    def test_confirm_page_for_each_decision(self):
        for decision in ("ACCEPTED", "REJECTED"):
            r = self.administrator.get(
                reverse("core:applicant-decision-confirm", args=[self.applicant.pk, decision]))
            self.assertContains(r, "Ravi Kumar")

    def test_confirm_page_unknown_decision_404(self):
        r = self.administrator.get(
            reverse("core:applicant-decision-confirm", args=[self.applicant.pk, "PENDING"]))
        self.assertEqual(r.status_code, 404)

    def test_reject_without_reason_keeps_pending(self):
        self.administrator.post(self.decide_url, {"decision": "REJECTED", "reason": ""})
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, "PENDING")

    def test_reject_with_reason_is_stored(self):
        self.administrator.post(self.decide_url, {"decision": "REJECTED", "reason": "No seat"})
        self.applicant.refresh_from_db()
        self.assertEqual((self.applicant.admission_status, self.applicant.admission_decision_reason),
                         ("REJECTED", "No seat"))

    def test_accept_needs_no_reason(self):
        self.administrator.post(self.decide_url, {"decision": "ACCEPTED"})
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, "ACCEPTED")

    def test_second_decision_does_not_change_record_and_does_not_500(self):
        self.administrator.post(self.decide_url, {"decision": "REJECTED", "reason": "No seat"})
        r = self.administrator.post(self.decide_url, {"decision": "ACCEPTED"}, follow=True)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.admission_status, "REJECTED")
        self.assertEqual(r.status_code, 200)

    def test_confirm_page_for_decided_applicant_redirects_to_detail(self):
        self.administrator.post(self.decide_url, {"decision": "ACCEPTED"})
        r = self.administrator.get(
            reverse("core:applicant-decision-confirm", args=[self.applicant.pk, "REJECTED"]))
        self.assertRedirects(r, reverse("core:applicant-detail", args=[self.applicant.pk]))
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - Model: add the field to `Applicant`; change `record_admission_decision(self, decision, reason="")`; after the existing checks add `if decision == REJECTED and not reason.strip(): raise ValidationError("A reason is required to reject an applicant.")`; set `self.admission_decision_reason = reason.strip()` and add it to `update_fields`.
  - Form: `AdmissionDecisionForm.reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))`.
  - View `applicant_admission_decision`: `applicant.record_admission_decision(form.cleaned_data["decision"], reason=form.cleaned_data["reason"])`. On `ValidationError` for a blank rejection reason, redirect to the confirm page for that decision; for any other error keep redirecting to detail:
    ```python
    except ValidationError as error:
        messages.error(request, error.messages[0])
        if (form.cleaned_data["decision"] == Applicant.AdmissionStatus.REJECTED
                and applicant.admission_status == Applicant.AdmissionStatus.PENDING):
            return redirect("core:applicant-decision-confirm", pk=applicant.pk, decision="REJECTED")
        return redirect("core:applicant-detail", pk=applicant.pk)
    ```
  - New view `applicant_decision_confirm(request, pk, decision)` with `@administrator_required("core.change_applicant")`: `if decision not in ("ACCEPTED", "REJECTED"): raise Http404`; redirect to detail if not PENDING; render the template with `applicant`, `decision`, `decision_label` ("Accept"/"Reject").
  - Template `applicant_decision_confirm.html`: H1 "{{ decision_label }} applicant"; consequence text – ACCEPTED: "This decision is final. You can then progress this applicant to a Student."; REJECTED: "This decision is final and cannot be reversed. No Student record will be created."; form to `core:applicant-admission-decision` with hidden `decision`; reason textarea (`id="reason"`) labelled "Reason (required)" with `required` for REJECTED, "Note (optional)" for ACCEPTED; primary button "{{ decision_label }} applicant"; Cancel link to applicant detail.
  - `applicant_detail.html`: replace the two inline forms (lines 22-33) with links `Accept applicant…` (`btn-success`) and `Reject applicant…` (`btn-danger`) to the confirm URLs; add a `Decision reason` row in the `<dl>` when `applicant.admission_decision_reason`.
  - Migration: `.venv\Scripts\python.exe manage.py makemigrations core -n phase0_decision_reasons` → expect `0067_phase0_decision_reasons.py` containing `CreateModel StudentStatusChange` and `AddField applicant.admission_decision_reason`. Then `manage.py migrate` (needs the Postgres env vars from memory `local-postgres-setup`, otherwise it falls back to SQLite).
- [ ] **Step 4: Run Task 3 + Task 4 tests → PASS**
- [ ] **Step 5: Commit** `feat(ui): confirm step and rejection reason for admission decisions (F03)`

---

### Task 5: Update existing tests broken by the new reason rule

**Files (modify):** `core/tests/test_acceptance.py`, `core/tests/test_authorization.py`, `core/tests/test_phase4_acceptance.py`, `core/tests/test_phase6_access_boundary.py` – 16 call sites of `student-status-change` / `applicant-admission-decision`.

- [ ] **Step 1:** `Grep` `student-status-change|applicant-admission-decision` in `core/tests`; run the four modules and list failures (expected: POSTs with `"status": "INACTIVE"` and `"decision": "REJECTED"`).
- [ ] **Step 2:** Add `"reason": "Test reason"` to those payloads only. ACTIVE and ACCEPTED payloads need no change. Do not weaken assertions.
- [ ] **Step 3:** Run the four modules → PASS.
- [ ] **Step 4:** Commit `test: add decision reasons to existing deactivate/reject posts`. Do this task before the final commits of Tasks 3/4 if green commits are wanted.

---

### Task 6: F11 – Student search: accessible name + Clear

**Files:** Modify `core/templates/core/student_list.html:5-10`; Test `core/tests/test_ui_admin_phase0.py`

- [ ] **Step 1: Failing test**
```python
class StudentSearchLabelTests(AuthorizationClientsMixin, TestCase):
    def test_search_input_has_label_and_clear_link_when_filtered(self):
        url = reverse("core:student-list")
        plain = self.administrator.get(url)
        self.assertContains(plain, '<label for="student-search"')
        self.assertContains(plain, 'id="student-search"')
        self.assertNotContains(plain, "Clear search")
        filtered = self.administrator.get(url, {"q": "zzz"})
        self.assertContains(filtered, '<label for="student-search"')
        self.assertContains(filtered, "Clear search")
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** – replace the form block:
```html
<form method="get" class="mb-3" role="search" aria-label="Search students">
    <label for="student-search" class="form-label">Search students</label>
    <div class="input-group">
        <input type="search" id="student-search" name="q" value="{{ query }}" class="form-control" placeholder="Name, email, or phone">
        <button type="submit" class="btn btn-outline-secondary">Search</button>
        {% if query %}<a class="btn btn-link" href="{% url 'core:student-list' %}">Clear search</a>{% endif %}
    </div>
</form>
```
- [ ] **Step 4:** Run the test plus the student-list tests in `core.tests.test_authorization` → PASS.
- [ ] **Step 5:** Commit `fix(a11y): label student search and add Clear (F11)`

---

### Task 7: F24 – Cancel link on attendance correction

**Files:** Modify `core/templates/core/attendance_correction_form.html:22-26`; Test `core/tests/test_ui_admin_phase0.py`

- [ ] **Step 1: Failing test** (fixture as in `AttendanceCorrectionAuthorizationTests.setUp`, giving `self.entry`)
```python
    def test_correction_form_has_cancel_back_to_register(self):
        r = self.administrator.get(reverse("core:attendance-entry-correct", args=[self.entry.pk]))
        back = reverse("core:attendance-register-detail", args=[self.entry.register_id])
        self.assertContains(r, f'href="{back}"')
        self.assertContains(r, "Cancel")
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** – inside the form after the submit button:
```html
    <a class="btn btn-link" href="{% url 'core:attendance-register-detail' entry.register_id %}">Cancel</a>
```
- [ ] **Step 4:** Run → PASS. **Step 5:** Commit `fix(ui): add Cancel to attendance correction (F24)`

---

### Task 8: Verification and PR

- [ ] **Step 1:** Run the whole suite: `.venv\Scripts\python.exe manage.py test --parallel 4` → only the known date-dependent failure remains.
- [ ] **Step 2:** `manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Step 3:** Browser smoke test (Playwright) with the demo admin: deactivate a student with and without a reason; reject an applicant; open the student list; open the correction page. Screenshot each.
- [ ] **Step 4:** Append a "Phase 0 notes" section to this plan listing what shipped against F02, F03, F06, F11, F16, F24.
- [ ] **Step 5:** Push the branch and open a PR to `main` ("UI Phase 0: admin safety & correctness fixes") – only when the user asks.

---

## Self-Review

- **Spec coverage:** F06→Task 1, F16→Task 2, F02→Task 3, F03→Task 4, F11→Task 6, F24→Task 7. The existing-test fallout is Task 5. F12 (table captions, scope, blank action headers) is deliberately out of scope: the audit's own Phase 0 list (p.14) omits it and it belongs to the data-table component in Phase 1/3.
- **Placeholder scan:** no TBD/TODO. The only open point is fixture construction (`Student.objects.create(full_name=...)`, `Applicant.objects.create(full_name=...)`, attendance `create` kwargs), which the executor must verify against the model's required fields and the fixtures named in each task.
- **Type consistency:** `reason` kwarg, `status_changes` related name, `admission_decision_reason`, and URL names `student-deactivate-confirm` / `applicant-decision-confirm` are used identically in every task.

## Phase 0 notes

- **F02:** Student deactivation now has a consequence review page, requires a reason, preserves that reason through guardian-access review, and records every successful status transition in `StudentStatusChange`.
- **F03:** Applicant acceptance and rejection now have final-decision review pages. Rejection requires and stores a reason; repeat decisions remain blocked and surface the model validation message.
- **F06:** Attendance registers are ordered newest-first with a deterministic section tiebreak.
- **F11:** Student search has a persistent visible label and a conditional **Clear search** link.
- **F16:** Empty grade cells display `Not graded` across result, assessment, and publication views.
- **F24:** Attendance correction includes a Cancel link back to its register.
- **Verification:** 19 focused Phase 0 tests and 269 affected legacy tests pass. The full 1,234-test suite has only the pre-existing date-dependent failure in `AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates`. `makemigrations --check --dry-run` reports no changes, and the isolated seeded browser smoke test passed for search, deactivation, rejection, attendance ordering, and correction cancellation.
