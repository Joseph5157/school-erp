# Phase 7 Piece C — Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Office staff issue bonafide certificates, report card PDFs and attendance summaries as serial-numbered PDFs; guardians download their own child's current published report card PDF; Telugu and English render correctly.

**Architecture:** WeasyPrint renders HTML templates to PDF with bundled Noto fonts. Every issued document is an immutable `IssuedDocument` row holding a JSON snapshot (letterhead included); reprints render from that snapshot. Serials come from a locked per-type-per-year counter. Each issue and download writes a `SecurityEvent`.

**Tech Stack:** Django 5.2, WeasyPrint, Noto Sans + Noto Sans Telugu (OFL), PostgreSQL and SQLite triggers (same pattern as `core/migrations/0061_announcement_history_guards.py`).

**Spec:** `docs/superpowers/specs/2026-10-15-phase7-documents-design.md`

## Global Constraints

- Serial format: `<PREFIX>/<academic-year name>/<0001>`, prefixes `BON`, `RC`, `ATT`, numbered per type and academic year.
- `IssuedDocument` is immutable: triggers refuse DELETE and every UPDATE on PostgreSQL and SQLite.
- Reprints render from `payload`, never live data; only the first issue consumes a serial.
- Report card PDF: only PUBLISHED publications whose `publication.guardian_visible(pub)` is true; STALE, SUPERSEDED, WITHDRAWN give nothing.
- New permission `core.issue_document`, granted to School Administrators by migration; guardians use the portal's visibility rule; teachers get nothing.
- Every issue and every download writes a `SecurityEvent` (HISTORY class).
- WeasyPrint is imported lazily inside `render_pdf` so the app and non-PDF tests run without system libraries.
- In new modules read "today" as `core_models.business_today()` (attribute access on `core.models`) so the tests' patch of `core.models.business_today` applies.
- Run quick tests with `env -u DB_NAME .venv/Scripts/python.exe manage.py test <labels> --noinput` (SQLite). Full PostgreSQL suite per the memory note; one known date-dependent failure (`AttendanceReportingTests.test_missing_report_skips_sections_without_students_and_future_dates`).
- Ruff clean (`.venv/Scripts/ruff.exe check .`), no pending migrations (`makemigrations --check --dry-run`).

## Rulings made while planning (review these)

1. **Logo deferred.** The spec listed an optional logo, but the app has no Pillow, no media storage and the host disk is ephemeral. The letterhead carries address, affiliation number and principal's name only; a logo is a follow-up once file storage exists. Cost if wrong: letterhead has no logo.
2. **Fonts.** Noto Sans Telugu has almost no Latin letters, so both Noto Sans (Latin) and Noto Sans Telugu are bundled; the CSS font stack falls back from Latin to Telugu.
3. **Telugu shaping check is visual.** PDF text extraction is unreliable for shaped Indic text, so the automated test asserts a valid PDF with both fonts embedded, and the implementer must also open the spike PDF and confirm conjuncts look right (Task 1 Step 6).
4. **Attendance summary year.** The date range must lie inside one academic year (the one containing the start date); that year labels the serial.
5. **Office report-card lookup.** A page with a student selector lists that student's printable cards; no per-student page is added.
6. **Guardian first download.** `issued_by` is null for a report card first downloaded by a guardian.

## Review Focus

- Report card whose results were corrected after publishing (STALE): no PDF for guardian or office (Task 6 test).
- Two simultaneous issues of the same document type and year: distinct serials (Task 3 test).
- Letterhead edited after a document was issued: reprint still shows the old letterhead (Task 4 test).
- Student whose enrollment ended or whose year ended: no bonafide, clear message (Task 5 test).
- Attendance range crossing two academic years or with end before start: rejected with a message (Task 7 test).

---

### Task 1: PDF engine, fonts and the Telugu spike

**Files:**
- Modify: `requirements.txt`
- Create: `static/fonts/NotoSans-Regular.ttf`, `static/fonts/NotoSans-Bold.ttf`, `static/fonts/NotoSansTelugu-Regular.ttf`, `static/fonts/OFL.txt`
- Create: `core/documents/__init__.py` (empty), `core/documents/engine.py`
- Create: `templates/documents/base.html`, `templates/documents/_engine_check.html`
- Create: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Produces: `core.documents.engine.render_pdf(template_name: str, context: dict) -> bytes`; `templates/documents/base.html` with blocks `title` and `body`, defining the `@page` A4 rules and the font stack.

- [ ] **Step 1: Install and pin WeasyPrint**

Run: `.venv/Scripts/python.exe -m pip install weasyprint==66.0` then `.venv/Scripts/python.exe -c "import weasyprint; print(weasyprint.__version__)"`.
Expected: prints a version. If `import weasyprint` or the first render fails with a missing GTK/Pango library error on Windows, **stop and report BLOCKED** with the exact error (spec: no silent engine swap). If 66.0 does not exist, install the latest release and pin that version.
Add `weasyprint==<installed version>` to `requirements.txt`.

- [ ] **Step 2: Fetch the fonts**

```bash
mkdir -p static/fonts
base=https://github.com/notofonts/notofonts.github.io/raw/main/fonts
curl -L -o static/fonts/NotoSans-Regular.ttf $base/NotoSans/hinted/ttf/NotoSans-Regular.ttf
curl -L -o static/fonts/NotoSans-Bold.ttf $base/NotoSans/hinted/ttf/NotoSans-Bold.ttf
curl -L -o static/fonts/NotoSansTelugu-Regular.ttf $base/NotoSansTelugu/hinted/ttf/NotoSansTelugu-Regular.ttf
curl -L -o static/fonts/OFL.txt https://raw.githubusercontent.com/notofonts/telugu/main/OFL.txt
```
Expected: each `.ttf` is over 50 KB and its first four bytes are `00 01 00 00` (TrueType). If a URL 404s, find the current path in the notofonts repository and use it. The files must be real fonts, not HTML error pages.

- [ ] **Step 3: Write the failing test**

Create `core/tests/test_phase7_documents.py`:

```python
"""Phase 7 piece C: documents (spec 2026-10-15-phase7-documents-design.md)."""

from datetime import date

from django.test import SimpleTestCase, TestCase

from core.documents.engine import render_pdf

TELUGU = "క్ష స్త్ర శ్రీ విద్యార్థి"  # conjuncts: ksha, stra, shri, vidyarthi


class EngineTests(SimpleTestCase):
    def test_renders_pdf_with_both_scripts_and_embedded_fonts(self):
        pdf = render_pdf("documents/_engine_check.html",
                         {"latin": "Bonafide certificate 2026-27", "telugu": TELUGU})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"NotoSansTelugu", pdf)
        self.assertIn(b"NotoSans", pdf)
        self.assertGreater(len(pdf), 5_000)
```

- [ ] **Step 4: Run it to see it fail**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_documents --noinput`
Expected: ERROR, `ModuleNotFoundError: No module named 'core.documents'`.

- [ ] **Step 5: Implement the engine and templates**

`core/documents/engine.py`:

```python
"""HTML-to-PDF rendering for issued documents (spec D6: WeasyPrint)."""

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

FONT_DIR = Path(settings.BASE_DIR) / "static" / "fonts"

_FONT_CSS = """
@font-face {{ font-family: 'DocLatin'; font-weight: 400; src: url('{regular}'); }}
@font-face {{ font-family: 'DocLatin'; font-weight: 700; src: url('{bold}'); }}
@font-face {{ font-family: 'DocTelugu'; src: url('{telugu}'); }}
"""


def render_pdf(template_name, context):
    """Render a template to PDF bytes. Fonts are bundled, never the server's."""
    from weasyprint import CSS, HTML  # lazy: needs system libraries (Pango)

    fonts = CSS(string=_FONT_CSS.format(
        regular=(FONT_DIR / "NotoSans-Regular.ttf").as_uri(),
        bold=(FONT_DIR / "NotoSans-Bold.ttf").as_uri(),
        telugu=(FONT_DIR / "NotoSansTelugu-Regular.ttf").as_uri(),
    ))
    html = render_to_string(template_name, context)
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(stylesheets=[fonts])
```

`templates/documents/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{% block title %}Document{% endblock %}</title>
<style>
  @page { size: A4; margin: 22mm 18mm; }
  body { font-family: 'DocLatin', 'DocTelugu', sans-serif; font-size: 12pt; line-height: 1.5; color: #111; }
  h1 { font-size: 18pt; text-align: center; margin: 18mm 0 10mm; text-transform: uppercase; }
  .letterhead { text-align: center; border-bottom: 1px solid #111; padding-bottom: 4mm; }
  .letterhead .name { font-size: 16pt; font-weight: 700; }
  .meta { display: flex; justify-content: space-between; margin-top: 6mm; }
  .signature { margin-top: 28mm; text-align: right; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #555; padding: 2mm 3mm; text-align: left; }
</style>
</head>
<body>{% block body %}{% endblock %}</body>
</html>
```

`templates/documents/_engine_check.html`:

```html
{% extends "documents/base.html" %}
{% block body %}<p>{{ latin }}</p><p>{{ telugu }}</p>{% endblock %}
```

- [ ] **Step 6: Run the test and look at the output**

Run the Step 4 command. Expected: PASS.
Then write the PDF to the scratchpad and open it with the Read tool (`pages: "1"`) to confirm the Telugu conjuncts are shaped (not separate vowel signs or boxes):
`env -u DB_NAME .venv/Scripts/python.exe manage.py shell -c "from core.documents.engine import render_pdf; open(r'<scratchpad>/spike.pdf','wb').write(render_pdf('documents/_engine_check.html', {'latin':'Bonafide 2026-27','telugu':'క్ష స్త్ర శ్రీ విద్యార్థి'}))"`
If the Telugu is broken, stop and report BLOCKED with a description.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt static/fonts core/documents templates/documents core/tests/test_phase7_documents.py
git commit -m "feat(phase7): PDF engine with bundled Noto fonts and Telugu check"
```

---

### Task 2: Letterhead fields on the School

**Files:**
- Modify: `core/models.py` (class `School`, after `name`), `core/forms.py` (`SchoolForm.Meta.fields`), `core/templates/core/school_detail.html`
- Create: migration `core/migrations/0063_school_letterhead.py` (generated)
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Produces: `School.address` (TextField blank), `School.affiliation_number` (CharField 50 blank), `School.principal_name` (CharField 120 blank); `core.documents.service.letterhead(school) -> dict` (added in Task 4, reading these).

- [ ] **Step 1: Write the failing test** (append to the test file)

```python
from core.forms import SchoolForm


class SchoolLetterheadTests(TestCase):
    def test_form_saves_letterhead_fields_and_they_are_optional(self):
        form = SchoolForm({"name": "Sri Vidya School", "notification_channel": "PORTAL_ONLY"})
        self.assertTrue(form.is_valid(), form.errors)
        school = form.save()
        self.assertEqual((school.address, school.affiliation_number, school.principal_name),
                         ("", "", ""))
        form = SchoolForm({"name": "Sri Vidya School", "notification_channel": "PORTAL_ONLY",
                           "address": "1 Main Road, Guntur", "affiliation_number": "AP/123",
                           "principal_name": "K. Lakshmi"}, instance=school)
        self.assertTrue(form.is_valid(), form.errors)
        school = form.save()
        self.assertEqual(school.principal_name, "K. Lakshmi")
```

- [ ] **Step 2: Run to see it fail**

Expected: the `principal_name` assertion fails (or `address` is ignored) because the form lacks the fields.

- [ ] **Step 3: Implement**

In `School` add:

```python
    address = models.TextField(blank=True)
    affiliation_number = models.CharField(max_length=50, blank=True)
    principal_name = models.CharField(max_length=120, blank=True)
```

In `SchoolForm.Meta`: `fields = ["name", "address", "affiliation_number", "principal_name", "notification_channel"]`. Add the three values to `school_detail.html` next to the name (read the file first and follow its markup). `school_form.html` uses `form.as_p`, so it needs no change.
Run `.venv/Scripts/python.exe manage.py makemigrations core -n school_letterhead`.

- [ ] **Step 4: Run the test, then the model tests**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_documents core.tests.test_models --noinput`
Expected: PASS apart from the one known failure.

- [ ] **Step 5: Commit** — `feat(phase7): letterhead fields on the school settings`

---

### Task 3: IssuedDocument, serial counter, history guards, permission, audit events

**Files:**
- Modify: `core/models.py` (after `Announcement`), `accounts/models.py` (`SecurityEvent.EventType`: add `DOCUMENT_ISSUED`, `DOCUMENT_DOWNLOADED`)
- Create: `core/documents/serials.py`
- Create migrations (generated then hand-written): core `0064_issued_documents`, `0065_issued_document_history_guards`, `0066_issue_document_permission`; accounts `0006_document_events` (generated)
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Produces:
  - `IssuedDocument` fields: `public_id` (UUID unique), `document_type` (`BONAFIDE|REPORT_CARD|ATTENDANCE_SUMMARY`), `serial` (CharField 40 unique), `academic_year` (FK PROTECT), `student` (FK PROTECT null), `publication` (OneToOne to TermPublication PROTECT null), `payload` (JSONField), `issued_by` (FK user PROTECT null), `issued_at` (default `timezone.now`). `Meta.permissions = [("issue_document", "Can issue documents")]`, ordering `["-issued_at", "-pk"]`.
  - `DocumentSerialCounter(document_type, academic_year FK PROTECT, last_number PositiveInteger default 0)`, unique on `(document_type, academic_year)`.
  - `core.documents.serials.next_serial(document_type: str, academic_year) -> str`; must be called inside `transaction.atomic()`.
  - `IssuedDocument.DocumentType` TextChoices with `BONAFIDE`, `REPORT_CARD`, `ATTENDANCE_SUMMARY`.

- [ ] **Step 1: Write the failing tests**

```python
from django.db import DatabaseError, transaction

from core.documents import serials
from core.models import AcademicYear, IssuedDocument


class SerialTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31))

    def test_serials_count_per_type_and_year(self):
        with transaction.atomic():
            self.assertEqual(serials.next_serial("BONAFIDE", self.year), "BON/2026-27/0001")
            self.assertEqual(serials.next_serial("BONAFIDE", self.year), "BON/2026-27/0002")
            self.assertEqual(serials.next_serial("REPORT_CARD", self.year), "RC/2026-27/0001")
            self.assertEqual(serials.next_serial("ATTENDANCE_SUMMARY", self.year),
                             "ATT/2026-27/0001")

    def test_unknown_type_is_refused(self):
        with transaction.atomic(), self.assertRaises(ValueError):
            serials.next_serial("NOPE", self.year)


class IssuedDocumentHistoryTests(TestCase):
    def setUp(self):
        year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31))
        self.doc = IssuedDocument.objects.create(
            document_type="BONAFIDE", serial="BON/2026-27/0001", academic_year=year,
            payload={"student_name": "Asha"})

    def test_update_and_delete_are_refused(self):
        self.doc.payload = {"student_name": "Other"}
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.doc.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            IssuedDocument.objects.filter(pk=self.doc.pk).delete()
```

(Check `AcademicYear` required fields in `core/models.py` and adjust the `create` calls — in particular the field that holds the label, written `name` here.)

- [ ] **Step 2: Run to see them fail** — Expected: ImportError for `serials` / `IssuedDocument`.

- [ ] **Step 3: Implement the models**

Add to `core/models.py` after `Announcement`:

```python
class IssuedDocument(models.Model):
    """A serial-numbered document issued by the school (Phase 7 piece C).

    `payload` is the exact content printed, letterhead included; reprints
    render from it, never from live data. Database triggers refuse every
    UPDATE and DELETE.
    """

    class DocumentType(models.TextChoices):
        BONAFIDE = "BONAFIDE", "Bonafide certificate"
        REPORT_CARD = "REPORT_CARD", "Report card"
        ATTENDANCE_SUMMARY = "ATTENDANCE_SUMMARY", "Attendance summary"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    serial = models.CharField(max_length=40, unique=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True, related_name="issued_documents"
    )
    publication = models.OneToOneField(
        "TermPublication", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    payload = models.JSONField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+",
    )
    issued_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-issued_at", "-pk"]
        permissions = [("issue_document", "Can issue documents")]

    def __str__(self):
        return self.serial


class DocumentSerialCounter(models.Model):
    """Last number used per document type and academic year (locked on use)."""

    document_type = models.CharField(max_length=20)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "academic_year"], name="documentserialcounter_unique"
            ),
        ]
```

`core/documents/serials.py`:

```python
"""Serial numbers for issued documents. Call inside transaction.atomic()."""

from django.db import IntegrityError, transaction

from core.models import DocumentSerialCounter

PREFIXES = {"BONAFIDE": "BON", "REPORT_CARD": "RC", "ATTENDANCE_SUMMARY": "ATT"}


def next_serial(document_type, academic_year):
    if document_type not in PREFIXES:
        raise ValueError(f"Unknown document type: {document_type}")
    try:
        with transaction.atomic():
            DocumentSerialCounter.objects.get_or_create(
                document_type=document_type, academic_year=academic_year)
    except IntegrityError:
        pass  # a concurrent request created it first
    counter = DocumentSerialCounter.objects.select_for_update().get(
        document_type=document_type, academic_year=academic_year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{PREFIXES[document_type]}/{academic_year.name}/{counter.last_number:04d}"
```

(If the academic year's label field is not `name`, adjust the code and the tests.)
In `accounts/models.py` add to `EventType`:
```python
        DOCUMENT_ISSUED = "DOCUMENT_ISSUED", "Document issued"
        DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED", "Document downloaded"
```
Run `makemigrations accounts core` (core migration named `issued_documents`; rename to match the Files list if the generator picks other names).

- [ ] **Step 4: History-guard migration `0065`**

Copy `core/migrations/0061_announcement_history_guards.py` and adapt: table `core_issueddocument`, names `core_issueddoc_*`, message `"Issued documents cannot be changed or deleted."`, no allowed columns. SQLite: two triggers, `BEFORE DELETE` and `BEFORE UPDATE`, both `RAISE(ABORT, ...)`. PostgreSQL: one function raising `integrity_constraint_violation`, trigger `BEFORE UPDATE OR DELETE ... FOR EACH ROW`. Dependency `("core", "0064_issued_documents")`. Reverse drops triggers and function.

- [ ] **Step 5: Permission migration `0066`**

Copy `0062_announcement_permissions_and_text.py`, `CODENAMES = ["issue_document", "view_issueddocument"]`, drop the template-seeding part, dependency on `0065`.

- [ ] **Step 6: Run the tests**

Run: `env -u DB_NAME .venv/Scripts/python.exe manage.py test core.tests.test_phase7_documents core.tests.test_authorization --noinput`
Expected: documents tests PASS. `test_authorization` pins the administrators' exact permission set: add `issue_document` and `view_issueddocument` to the expected set (as Gate 3 did) and ledger it as a ruling.

- [ ] **Step 7: Concurrency check and commit**

Add one PostgreSQL-only test guarded by `@skipUnless(connection.vendor == "postgresql", ...)` using `TransactionTestCase` and two threads each calling `next_serial` inside `transaction.atomic()`; assert the two serials are distinct. Run it once against PostgreSQL (env vars per the memory note).
Commit: `feat(phase7): issued documents, serial counter, history guards, permission`

---

### Task 4: Issue and reprint service with audit

**Files:**
- Create: `core/documents/service.py`
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Consumes: `serials.next_serial`, `IssuedDocument`, `School`, `SecurityEvent.record`, `engine.render_pdf`.
- Produces:
  - `letterhead(school=None) -> dict` with keys `school_name`, `address`, `affiliation_number`, `principal_name` (strings, may be empty; uses `School.objects.first()` when `school` is None; empty strings if there is no School row).
  - `issue(*, document_type, academic_year, payload, actor, student=None, publication=None) -> IssuedDocument`: atomic; allocates the serial; stores `payload` with the letterhead merged in under `"letterhead"`; records `DOCUMENT_ISSUED` (detail: serial, document_type; `student=` the student).
  - `pdf_for(document, *, actor) -> bytes`: renders `TEMPLATES[document.document_type]` with `{"doc": document, "payload": document.payload, "serial": document.serial}`; records `DOCUMENT_DOWNLOADED` (detail: serial). `actor` may be a guardian's user.
  - `TEMPLATES = {"BONAFIDE": "documents/bonafide.html", "REPORT_CARD": "documents/report_card.html", "ATTENDANCE_SUMMARY": "documents/attendance_summary.html"}` (templates created in Tasks 5-7).

- [ ] **Step 1: Write the failing tests**

```python
from unittest import mock

from accounts.models import SecurityEvent
from core.documents import service
from core.models import School


class IssueServiceTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2026-27", start_date=date(2026, 6, 1), end_date=date(2027, 3, 31))
        self.school = School.objects.create(
            name="Sri Vidya", address="1 Main Road", affiliation_number="AP/1",
            principal_name="K. Lakshmi")

    def issue(self):
        return service.issue(document_type="BONAFIDE", academic_year=self.year,
                             payload={"student_name": "Asha"}, actor=None)

    def test_issue_stores_letterhead_and_records_event(self):
        doc = self.issue()
        self.assertEqual(doc.serial, "BON/2026-27/0001")
        self.assertEqual(doc.payload["letterhead"]["principal_name"], "K. Lakshmi")
        event = SecurityEvent.objects.get(event_type="DOCUMENT_ISSUED")
        self.assertEqual(event.detail["serial"], doc.serial)

    def test_reprint_keeps_the_letterhead_it_was_issued_with(self):
        doc = self.issue()
        self.school.principal_name = "New Principal"
        self.school.save()
        captured = {}

        def fake_render(template, context):
            captured.update(context)
            return b"%PDF-fake"

        with mock.patch("core.documents.service.render_pdf", fake_render):
            service.pdf_for(doc, actor=None)
        self.assertEqual(captured["payload"]["letterhead"]["principal_name"], "K. Lakshmi")
        self.assertEqual(SecurityEvent.objects.filter(
            event_type="DOCUMENT_DOWNLOADED").count(), 1)
        self.assertEqual(IssuedDocument.objects.count(), 1)  # a reprint adds no row
```

- [ ] **Step 2: Run to see them fail** — Expected: ImportError on `core.documents.service`.

- [ ] **Step 3: Implement `core/documents/service.py`**

```python
"""Issue and reprint serial-numbered documents (spec 2026-10-15)."""

from django.db import transaction
from django.http import HttpResponse

from accounts.models import SecurityEvent
from core.documents import serials
from core.documents.engine import render_pdf
from core.models import IssuedDocument, School

Event = SecurityEvent.EventType

TEMPLATES = {
    "BONAFIDE": "documents/bonafide.html",
    "REPORT_CARD": "documents/report_card.html",
    "ATTENDANCE_SUMMARY": "documents/attendance_summary.html",
}


def letterhead(school=None):
    school = school or School.objects.first()
    if school is None:
        return {"school_name": "", "address": "", "affiliation_number": "",
                "principal_name": ""}
    return {
        "school_name": school.name,
        "address": school.address,
        "affiliation_number": school.affiliation_number,
        "principal_name": school.principal_name,
    }


def issue(*, document_type, academic_year, payload, actor, student=None, publication=None):
    with transaction.atomic():
        document = IssuedDocument.objects.create(
            document_type=document_type,
            serial=serials.next_serial(document_type, academic_year),
            academic_year=academic_year,
            student=student,
            publication=publication,
            payload={**payload, "letterhead": letterhead()},
            issued_by=actor if getattr(actor, "pk", None) else None,
        )
        SecurityEvent.record(
            Event.DOCUMENT_ISSUED, actor=actor, student=student,
            detail={"serial": document.serial, "document_type": document_type},
        )
    return document


def pdf_for(document, *, actor):
    """Render from the stored snapshot; every call is audited."""
    pdf = render_pdf(TEMPLATES[document.document_type], {
        "doc": document, "payload": document.payload, "serial": document.serial,
    })
    SecurityEvent.record(
        Event.DOCUMENT_DOWNLOADED, actor=actor, student=document.student,
        detail={"serial": document.serial, "document_type": document.document_type},
    )
    return pdf


def pdf_response(document, *, actor):
    response = HttpResponse(pdf_for(document, actor=actor), content_type="application/pdf")
    name = document.serial.replace("/", "-")
    response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response
```

- [ ] **Step 4: Run tests** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(phase7): issue and reprint documents with audit`

---

### Task 5: Bonafide certificate (office)

**Files:**
- Create: `core/documents/bonafide.py`, `core/document_views.py`, `core/templates/core/document_index.html`, `core/templates/core/bonafide_form.html`, `templates/documents/bonafide.html`, `templates/documents/_letterhead.html`
- Modify: `core/forms.py` (`BonafideForm`), `core/urls.py`, `core/navigation.py`
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Consumes: `service.issue`, `service.pdf_response`, the Gate 3 enrollment rule (effective today and `academic_year__end_date__gte` today).
- Produces:
  - `bonafide.PURPOSES`: `[("BANK", "Opening a bank account"), ("PASSPORT", "Passport application"), ("SCHOLARSHIP", "Scholarship application"), ("OTHER", "Other")]`.
  - `bonafide.current_enrollment(student) -> AcademicEnrollment | None`.
  - `bonafide.issue_bonafide(*, student, purpose_key, purpose_text, actor) -> IssuedDocument`; raises `ValidationError` ("This student has no current enrolment.", "Say what the certificate is for.", "Choose a purpose.").
  - URLs (office, `administrator_required("core.issue_document")`): `documents/` (`core:document-index`), `documents/bonafide/` (`core:bonafide-create`, GET form / POST issue → redirect to the PDF), `documents/<uuid:public_id>/pdf/` (`core:document-pdf`, serves any `IssuedDocument` inline as `application/pdf` via `service.pdf_response`).
  - Nav link "Documents" → `core:document-index`, permission `core.issue_document`.

- [ ] **Step 1: Write the failing tests**

Reuse the Gate 3 fixture (read `AnnouncementFixture` / `AlertFixture`: today pinned to 2026-10-12, `self.client` logged in as the administrator, students `self.asha` in `self.six_a` with a current enrollment, `self.ravi` in `self.six_b`). Create a student with no enrollment in the test.

```python
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.documents import bonafide
from core.models import Student
from core.tests.test_phase7_announcements import AnnouncementFixture


class BonafideTests(AnnouncementFixture, TestCase):
    def issue(self, student=None, key="BANK", text=""):
        return bonafide.issue_bonafide(student=student or self.asha, purpose_key=key,
                                       purpose_text=text, actor=self.admin)

    def test_issue_for_enrolled_student(self):
        doc = self.issue()
        self.assertTrue(doc.serial.startswith("BON/"))
        self.assertEqual(doc.payload["student_name"], self.asha.full_name)
        self.assertEqual(doc.payload["section_label"], self.six_a.name)
        self.assertEqual(doc.payload["purpose"], "Opening a bank account")
        self.assertEqual(doc.student, self.asha)

    def test_other_requires_text_and_uses_it(self):
        with self.assertRaises(ValidationError):
            self.issue(key="OTHER", text="  ")
        doc = self.issue(key="OTHER", text="Visa application")
        self.assertEqual(doc.payload["purpose"], "Visa application")

    def test_student_without_current_enrolment_is_refused(self):
        stranger = Student.objects.create(full_name="No Enrolment")
        with self.assertRaises(ValidationError) as caught:
            self.issue(student=stranger)
        self.assertIn("no current enrolment", caught.exception.messages[0])

    def test_view_issues_and_serves_pdf(self):
        page = self.client.post(reverse("core:bonafide-create"), {
            "student": self.asha.pk, "purpose": "PASSPORT", "purpose_text": ""})
        doc = IssuedDocument.objects.get()
        self.assertRedirects(page, reverse("core:document-pdf", args=[doc.public_id]),
                             fetch_redirect_response=False)
        pdf = self.client.get(reverse("core:document-pdf", args=[doc.public_id]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
```

Also add `test_teacher_gets_403`: log in as a non-administrator using the project's existing way (see `core/tests/test_authorization.py`) and assert `self.client.get(reverse("core:bonafide-create")).status_code == 403`.

- [ ] **Step 2: Run to see them fail** — Expected: ImportError `core.documents.bonafide`.

- [ ] **Step 3: Implement**

`core/documents/bonafide.py`:

```python
"""Bonafide certificate: confirms current enrolment (spec decision 7)."""

from django.core.exceptions import ValidationError

from core import models as core_models
from core.documents import service
from core.models import AcademicEnrollment, IssuedDocument

PURPOSES = [
    ("BANK", "Opening a bank account"),
    ("PASSPORT", "Passport application"),
    ("SCHOLARSHIP", "Scholarship application"),
    ("OTHER", "Other"),
]


def current_enrollment(student):
    today = core_models.business_today()
    return (
        AcademicEnrollment.objects.effective_on(today)
        .filter(student=student, academic_year__end_date__gte=today)
        .select_related("academic_year", "class_grade", "section")
        .first()
    )


def issue_bonafide(*, student, purpose_key, purpose_text, actor):
    enrollment = current_enrollment(student)
    if enrollment is None:
        raise ValidationError("This student has no current enrolment.")
    labels = dict(PURPOSES)
    if purpose_key == "OTHER":
        purpose = (purpose_text or "").strip()[:120]
        if not purpose:
            raise ValidationError("Say what the certificate is for.")
    elif purpose_key in labels:
        purpose = labels[purpose_key]
    else:
        raise ValidationError("Choose a purpose.")
    payload = {
        "student_name": student.full_name,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else "",
        "admission_number": student.admission_number or "",
        "class_label": enrollment.class_grade.name,
        "section_label": enrollment.section.name,
        "academic_year_label": enrollment.academic_year.name,
        "purpose": purpose,
        "issued_on": core_models.business_today().isoformat(),
    }
    return service.issue(
        document_type=IssuedDocument.DocumentType.BONAFIDE,
        academic_year=enrollment.academic_year, payload=payload, actor=actor, student=student,
    )
```

(Check the field names `class_grade.name`, `section.name`, `academic_year.name`, `admission_number` against `core/models.py`; adjust code and tests to the real names.)

`BonafideForm` in `core/forms.py`: `student = ModelChoiceField(Student.objects.order_by("full_name"))`, `purpose = ChoiceField(choices=bonafide.PURPOSES)`, `purpose_text = CharField(max_length=120, required=False)`.

`core/document_views.py`:

```python
"""Office document pages (spec 2026-10-15). Permission core.issue_document."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from core.authorization import administrator_required
from core.documents import bonafide, service
from core.forms import BonafideForm
from core.models import IssuedDocument


@administrator_required("core.issue_document")
def document_index(request):
    recent = IssuedDocument.objects.select_related("student", "academic_year")[:50]
    return render(request, "core/document_index.html", {"recent": recent})


@administrator_required("core.issue_document")
def bonafide_create(request):
    form = BonafideForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            document = bonafide.issue_bonafide(
                student=form.cleaned_data["student"],
                purpose_key=form.cleaned_data["purpose"],
                purpose_text=form.cleaned_data["purpose_text"], actor=request.user)
        except ValidationError as problem:
            form.add_error(None, problem.messages[0])
        else:
            messages.success(request, f"Certificate {document.serial} issued.")
            return redirect("core:document-pdf", public_id=document.public_id)
    return render(request, "core/bonafide_form.html", {"form": form})


@administrator_required("core.issue_document")
def document_pdf(request, public_id):
    document = get_object_or_404(IssuedDocument, public_id=public_id)
    return service.pdf_response(document, actor=request.user)
```

Add URLs to `core/urls.py` (`from core import document_views`; route names `document-index`, `bonafide-create`, `document-pdf`), the nav link in `core/navigation.py`, and templates:
- `templates/documents/_letterhead.html`: a `div.letterhead` with `payload.letterhead.school_name` (class `name`), the address (`linebreaksbr`) and "Affiliation no. …", each only when present.
- `templates/documents/bonafide.html`: extends base; includes the letterhead; meta row with serial and issue date; `<h1>Bonafide certificate</h1>`; one paragraph: "This is to certify that **{{ payload.student_name }}** (date of birth …, only when present) is a bonafide student of this school, studying in Class {{ payload.class_label }}, Section {{ payload.section_label }}, in the academic year {{ payload.academic_year_label }}. This certificate is issued for {{ payload.purpose }}."; signature block "Principal" plus the principal's name when present.
- `core/templates/core/document_index.html` and `bonafide_form.html`: follow `announcement_list.html` and `announcement_form.html`.

- [ ] **Step 4: Run tests** — Expected: PASS (uses the real engine; Task 1 proved it works).
- [ ] **Step 5: Commit** — `feat(phase7): bonafide certificate`

---

### Task 6: Report card PDF (guardian and office)

**Files:**
- Create: `core/documents/report_card.py`, `templates/documents/report_card.html`, `core/templates/core/document_report_cards.html`
- Modify: `core/document_views.py`, `core/urls.py`, `core/portal_views.py`, `core/portal_urls.py`, `templates/portal/report_card.html` (Download button), `core/forms.py` (a one-field student selector form)
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Consumes: `service.issue`, `service.pdf_response`, `publication.guardian_visible`, `portal.visible_publications`, `TermPublication.entries`.
- Produces:
  - `report_card.document_for(pub, *, actor) -> IssuedDocument | None`: returns the existing `IssuedDocument` for the publication, or issues one. Returns `None` unless `pub.status == "PUBLISHED"` and `publication.guardian_visible(pub)`. Handles two first downloads at once by catching `IntegrityError` and re-reading.
  - Payload keys: `student_name`, `admission_number`, `term_label`, `academic_year_label`, `class_label`, `section_label`, `is_partial`, `remark_text`, `entries` (list of dicts: `subject`, `assessment`, `date` ISO, `status`, `score`, `maximum_marks`, `percentage`, `grade`, `pass_fail`, all strings, empty for None), `issued_on`.
  - Portal URL `children/<uuid:public_id>/report-cards/<uuid:publication_id>/pdf/` (`portal:report-card-pdf`).
  - Office URLs: `documents/report-cards/` (`core:document-report-cards`, GET `student` selects; lists that student's visible cards) and `documents/report-cards/<uuid:publication_id>/pdf/` (`core:document-report-card-pdf`).

- [ ] **Step 1: Write the failing tests**

Use `PublicationFixture` from `core/tests/test_phase6_publication.py` (admin logged in on `self.client`, guardian on `self.portal`, `self.publish()`, `self.asha_grant`, `self.bina_grant`, `self.term1`, `self.asha_e`).

```python
from accounts.models import SecurityEvent
from core import publication
from core.models import StudentResult, TermPublication
from core.tests.test_phase6_publication import PublicationFixture


class ReportCardPdfTests(PublicationFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = TermPublication.objects.get(student=self.asha, term=self.term1)
        self.guardian_url = reverse(
            "portal:report-card-pdf", args=[self.asha_grant.public_id, self.pub.public_id])

    def test_guardian_downloads_own_childs_card(self):
        response = self.portal.get(self.guardian_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        doc = IssuedDocument.objects.get()
        self.assertTrue(doc.serial.startswith("RC/"))
        self.assertIsNone(doc.issued_by)
        self.assertEqual(doc.payload["entries"][0]["score"], "15.00")

    def test_second_download_reuses_serial_and_snapshot(self):
        self.portal.get(self.guardian_url)
        self.portal.get(self.guardian_url)
        self.assertEqual(IssuedDocument.objects.count(), 1)
        self.assertEqual(SecurityEvent.objects.filter(
            event_type="DOCUMENT_DOWNLOADED").count(), 2)

    def test_other_guardians_child_is_404(self):
        bina_pub = TermPublication.objects.get(student=self.bina, term=self.term1)
        url = reverse("portal:report-card-pdf",
                      args=[self.asha_grant.public_id, bina_pub.public_id])
        self.assertEqual(self.portal.get(url).status_code, 404)

    def test_stale_publication_gives_nothing(self):
        result = StudentResult.objects.get(academic_enrollment=self.asha_e)
        publication.mark_stale_for_result(result, actor=self.admin)
        self.assertEqual(self.portal.get(self.guardian_url).status_code, 404)
        office = reverse("core:document-report-card-pdf", args=[self.pub.public_id])
        self.assertEqual(self.client.get(office).status_code, 404)

    def test_office_prints_any_published_card(self):
        office = reverse("core:document-report-card-pdf", args=[self.pub.public_id])
        response = self.client.get(office)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(IssuedDocument.objects.get().issued_by, self.admin)
```

(`self.asha_e` may have several results; if `StudentResult.objects.get(...)` finds more than one, use `self.result` from the fixture.)

- [ ] **Step 2: Run to see them fail** — Expected: `NoReverseMatch` for `portal:report-card-pdf`.

- [ ] **Step 3: Implement `core/documents/report_card.py`**

```python
"""Report card PDF from the immutable publication snapshot (spec decision 5)."""

from django.db import IntegrityError, transaction

from core import models as core_models
from core import publication as publication_rules
from core.documents import service
from core.models import IssuedDocument, TermPublication


def _text(value):
    return "" if value is None else str(value)


def _payload(pub):
    return {
        "student_name": pub.student.full_name,
        "admission_number": pub.student.admission_number or "",
        "term_label": pub.term_label,
        "academic_year_label": pub.academic_year_label,
        "class_label": pub.class_grade_label,
        "section_label": pub.section_label,
        "is_partial": pub.is_partial,
        "remark_text": pub.remark_text or "",
        "entries": [
            {
                "subject": e.subject_label,
                "assessment": e.assessment_label,
                "date": e.assessment_date.isoformat(),
                "status": e.status,
                "score": _text(e.score),
                "maximum_marks": _text(e.maximum_marks),
                "percentage": _text(e.percentage),
                "grade": _text(e.grade_label),
                "pass_fail": _text(e.pass_fail_label),
            }
            for e in pub.entries.all()
        ],
        "issued_on": core_models.business_today().isoformat(),
    }


def document_for(pub, *, actor):
    if pub.status != TermPublication.Status.PUBLISHED:
        return None
    if not publication_rules.guardian_visible(pub):
        return None
    existing = IssuedDocument.objects.filter(publication=pub).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return service.issue(
                document_type=IssuedDocument.DocumentType.REPORT_CARD,
                academic_year=pub.term.academic_year, payload=_payload(pub),
                actor=actor, student=pub.student, publication=pub,
            )
    except IntegrityError:
        return IssuedDocument.objects.filter(publication=pub).first()
```

Portal view (in `core/portal_views.py`, `@require_safe @guardian_required`):

```python
def report_card_pdf(request, public_id, publication_id):
    grant = _visible_grant_or_404(request, public_id)
    student = grant.student_guardian.student
    pub = next((p for p in visible_publications(student) if p.public_id == publication_id), None)
    document = report_card.document_for(pub, actor=request.user) if pub else None
    if document is None:
        raise Http404("No such report card.")
    return service.pdf_response(document, actor=request.user)
```

Office views `document_report_cards` (student selector via GET; lists `visible_publications(student)` with links) and `document_report_card_pdf` (`get_object_or_404(TermPublication, public_id=...)`, then `document_for(...)` or 404), both `administrator_required("core.issue_document")`. Add the portal link in `templates/portal/report_card.html` under the heading: `<a class="btn btn-outline-primary btn-sm" href="{% url 'portal:report-card-pdf' grant.public_id pub.public_id %}">Download PDF</a>`.
`templates/documents/report_card.html`: base + letterhead + `<h1>{{ payload.term_label }} report card</h1>`, a student/year/class line, the entries table mirroring `templates/portal/report_card.html` (Subject, Assessment, Date, Marks, %, Grade, Pass/Fail; "Absent" when status is not MARKED), the partial notice, the remark, the serial in the meta row, and the "no totals, weighting or ranks" footnote.

- [ ] **Step 4: Run tests** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(phase7): report card PDF for guardians and office`

---

### Task 7: Attendance summary

**Files:**
- Create: `core/documents/attendance_summary.py`, `core/templates/core/attendance_summary.html`, `templates/documents/attendance_summary.html`
- Modify: `core/forms.py` (`AttendanceSummaryForm`), `core/document_views.py`, `core/urls.py`, `core/templates/core/document_index.html`
- Test: `core/tests/test_phase7_documents.py`

**Interfaces:**
- Consumes: `core.reports.reportable_entries`, `core.reports.counts`, `AttendanceEntry`.
- Produces:
  - `attendance_summary.build(section, start, end) -> dict` with `academic_year` (the `AcademicYear` containing `start`), `rows` (per student: `student_name`, `present`, `absent`, `total`, `percentage` string or `""`), `totals` (same keys, whole section), `section_label`, `class_label`, `start`, `end` (ISO strings). Raises `ValidationError` for end before start, no academic year containing start, or `end` after that year's end date.
  - `attendance_summary.issue_summary(section, start, end, *, actor) -> IssuedDocument` (type `ATTENDANCE_SUMMARY`, `student=None`).
  - URL `documents/attendance/` (`core:attendance-summary`): GET with `section`, `start`, `end` shows the table; POST issues and redirects to `core:document-pdf`.

- [ ] **Step 1: Write the failing tests**

Reuse `AlertFixture`'s `register(on_date, asha=..., ...)` helper from `core/tests/test_phase7_alerts.py` (read its signature first; it creates a submitted register for 6A with entries for Asha and Bina).

```python
from core.documents import attendance_summary
from core.tests.test_phase7_alerts import AlertFixture


class AttendanceSummaryTests(AlertFixture, TestCase):
    def test_counts_only_submitted_eligible_entries(self):
        self.register(date(2026, 10, 7))                      # Asha absent (default)
        self.register(date(2026, 10, 8), asha=AttendanceStatus.PRESENT)
        data = attendance_summary.build(self.six_a, date(2026, 10, 1), date(2026, 10, 12))
        asha = next(r for r in data["rows"] if r["student_name"] == self.asha.full_name)
        self.assertEqual((asha["present"], asha["absent"], asha["total"]), (1, 1, 2))
        self.assertEqual(asha["percentage"], "50.0")

    def test_draft_register_is_not_counted(self):
        # create a DRAFT register with entries directly (AttendanceRegister default status)
        ...
        data = attendance_summary.build(self.six_a, date(2026, 10, 1), date(2026, 10, 12))
        self.assertEqual(data["totals"]["total"], 0)

    def test_bad_ranges_are_refused(self):
        for start, end in ((date(2026, 10, 12), date(2026, 10, 1)),
                           (date(2026, 10, 1), date(2027, 6, 1)),
                           (date(2020, 1, 1), date(2020, 2, 1))):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError):
                attendance_summary.build(self.six_a, start, end)

    def test_issue_records_serial_and_pdf(self):
        self.register(date(2026, 10, 7))
        doc = attendance_summary.issue_summary(
            self.six_a, date(2026, 10, 1), date(2026, 10, 12), actor=self.admin)
        self.assertTrue(doc.serial.startswith("ATT/"))
        self.assertIsNone(doc.student)
        response = self.client.get(reverse("core:document-pdf", args=[doc.public_id]))
        self.assertTrue(response.content.startswith(b"%PDF"))
```

Replace the `...` in the draft test with creating an `AttendanceRegister` (status left DRAFT) plus one `AttendanceEntry` using the same models `register()` uses. Import `AttendanceStatus` where `test_phase7_alerts.py` imports it.

- [ ] **Step 2: Run to see them fail** — Expected: ImportError for `attendance_summary`.

- [ ] **Step 3: Implement**

```python
"""Attendance summary for one section and date range (spec decision 8)."""

from django.core.exceptions import ValidationError

from core import models as core_models
from core import reports
from core.documents import service
from core.models import AcademicYear, AttendanceEntry, IssuedDocument


def _plain(counts):
    return {
        "present": counts["present"], "absent": counts["absent"], "total": counts["total"],
        "percentage": "" if counts["percentage"] is None else str(counts["percentage"]),
    }


def build(section, start, end):
    if end < start:
        raise ValidationError("The end date is before the start date.")
    year = AcademicYear.objects.filter(start_date__lte=start, end_date__gte=start).first()
    if year is None:
        raise ValidationError("No academic year contains the start date.")
    if end > year.end_date:
        raise ValidationError("The range must stay inside one academic year.")
    entries = reports.reportable_entries(AttendanceEntry.objects.filter(
        academic_enrollment__section=section,
        register__date__gte=start, register__date__lte=end))
    students = entries.order_by().values_list(
        "academic_enrollment__student_id", "academic_enrollment__student__full_name"
    ).distinct()
    rows = []
    for student_id, name in sorted(students, key=lambda item: item[1]):
        counts = reports.counts(entries.filter(academic_enrollment__student_id=student_id))
        rows.append({"student_name": name, **_plain(counts)})
    return {
        "academic_year": year,
        "section_label": section.name,
        "class_label": section.class_grade.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rows": rows,
        "totals": _plain(reports.counts(entries)),
    }


def issue_summary(section, start, end, *, actor):
    data = build(section, start, end)
    year = data.pop("academic_year")
    data["issued_on"] = core_models.business_today().isoformat()
    return service.issue(
        document_type=IssuedDocument.DocumentType.ATTENDANCE_SUMMARY,
        academic_year=year, payload=data, actor=actor,
    )
```

(Confirm `reports.counts` returns ints and a float/None percentage as `core/reports.py` shows.)
`AttendanceSummaryForm` (section ModelChoiceField, `start` and `end` DateFields). View `attendance_summary` in `core/document_views.py`, `administrator_required("core.issue_document")`: GET with params shows the table via `build` (a `ValidationError` becomes a form error); POST issues and redirects to the PDF. Templates: `core/attendance_summary.html` (form, table, "Issue PDF" POST button with hidden section/start/end) and `documents/attendance_summary.html` (base + letterhead + title "Attendance summary", section/class, range, serial, table of Student, Present, Absent, Days, %, with a totals row). Link both from `document_index.html`.

- [ ] **Step 4: Run tests** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(phase7): attendance summary document`

---

### Task 8: Index page, notes and full suite

**Files:**
- Modify: `core/templates/core/document_index.html` (links to bonafide, report cards, attendance summary; recent issued list with PDF links), `docs/PHASE_7_COMMUNICATION_DOCUMENTS_IMPORT_PLAN.md` (implementation notes for Gates 5, 6 and the Gate 7 attendance part, in the style of the existing Gate notes), `README.md` (system packages note)
- Test: `core/tests/test_phase7_documents.py`

- [ ] **Step 1: Write the failing test**

```python
class DocumentIndexTests(AnnouncementFixture, TestCase):
    def test_index_lists_links_and_recent_documents(self):
        doc = bonafide.issue_bonafide(student=self.asha, purpose_key="BANK",
                                      purpose_text="", actor=self.admin)
        page = self.client.get(reverse("core:document-index"))
        self.assertContains(page, doc.serial)
        self.assertContains(page, reverse("core:bonafide-create"))
        self.assertContains(page, reverse("core:attendance-summary"))
        self.assertContains(page, reverse("core:document-report-cards"))
```

- [ ] **Step 2: Run to see it fail** — Expected: links missing from the page.
- [ ] **Step 3: Implement** the index template links and the recent-documents table (serial, type, student, issued date, "PDF" link to `core:document-pdf`). Write the plan notes: what was built, the rulings from this plan, the deploy note (**WeasyPrint needs Pango on Linux**: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b`, or the nixpacks equivalent; fonts are bundled so no font package is needed), and the follow-ups (logo, Transfer Certificate).
- [ ] **Step 4: Run the full suites**

Quick: `env -u DB_NAME .venv/Scripts/python.exe manage.py test --parallel 4 --noinput` (SQLite). Then the PostgreSQL suite per the memory note.
Expected: all pass except the one known date-dependent failure. `ruff check .` clean; `makemigrations --check --dry-run` clean.

- [ ] **Step 5: Commit** — `docs(phase7): documents implementation notes and index page`
