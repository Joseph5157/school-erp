"""UI-D1-6E: Bulk imports (list, upload, detail) presentation, safeguards and the 200-row regression scenario.

Presentation only. The import services, validation, the reviewed-warnings requirement, the 24-hour window and the
atomic commit are unchanged; these tests re-prove them through the pages.
"""

import datetime
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from accounts.models import SecurityEvent
from core import imports
from core.breadcrumbs import breadcrumb_context
from core.models import (
    Applicant,
    ClassGrade,
    Guardian,
    ImportBatch,
    ImportRowResult,
    Section,
    Student,
)
from core.tests.test_phase7_import import ImportFixture, student_row, workbook

User = get_user_model()
ACTIVE_LINK = r'<a class="nav-link active" href="([^"]+)"'
LIST = reverse("core:import-list")
UPLOAD = reverse("core:import-upload")
REVIEW_BOX = '<input class="form-check-input" type="checkbox" name="reviewed_warnings" value="yes" id="reviewed" required>'
LONG = "Longname" * 10


def html(response):
    return response.content.decode()


def after_lifetime():
    later = timezone.now() + imports.PENDING_LIFETIME + datetime.timedelta(minutes=1)
    return mock.patch("core.imports.timezone", now=lambda: later)


class Base(ImportFixture):
    def client_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._viewers}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def teacher(self):
        User.objects.create_user(username="teacher1", password="pass-12345")
        client = self.client_class()
        client.login(username="teacher1", password="pass-12345")
        return client

    def detail(self, batch):
        return reverse("core:import-detail", args=[batch.pk])

    def commit_url(self, batch):
        return reverse("core:import-commit", args=[batch.pk])

    def discard_url(self, batch):
        return reverse("core:import-discard", args=[batch.pk])

    def page(self, batch, client=None):
        return html((client or self.client).get(self.detail(batch)))

    def clean(self, name="Asha"):
        return self.batch_for(workbook([student_row(name)]))

    def with_warning(self, name="Asha"):
        Guardian.objects.create(full_name="Someone Else", phone="9876543210")
        return self.batch_for(workbook([student_row(name)]))

    def rejected(self):
        return self.batch_for(workbook([student_row("Asha", cls="Nope")]))

    def events(self):
        return SecurityEvent.objects.filter(event_type=SecurityEvent.EventType.IMPORT_COMMITTED).count()


class StateMatrixTests(Base):
    def test_validated_clean_has_confirm_discard_and_the_24_hour_note(self):
        batch = self.clean()
        page = self.page(batch)
        self.assertRegex(page, rf'<h1 class="erp-page-title">Import {batch.pk}</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('erp-status--pending"><span class="visually-hidden">Status: </span>Validated — awaiting confirmation', page)
        self.assertIn("Confirm import", page)
        self.assertNotIn("reviewed_warnings", page)
        self.assertIn("Nothing is imported and the file is discarded.", page)
        self.assertIn("A checked file can be confirmed within 24 hours of upload.", page)
        self.assertIn(f'<a class="btn btn-outline-secondary" href="{LIST}">All imports</a>', page)
        self.assertIn(f'action="{self.commit_url(batch)}"', page)
        self.assertIn(f'action="{self.discard_url(batch)}"', page)

    def test_preview_counts_and_students_region(self):
        page = self.page(self.clean())
        self.assertIn('role="region" aria-label="Students to import (1)" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertIn("<dt>Students</dt><dd>1</dd>", page)
        self.assertIn("Confirming will create 1 students", page)
        self.assertIn("Class 5 - A", page)
        self.assertEqual(page.count('scope="col"'), 7)

    def test_warnings_need_the_exact_review_checkbox_and_show_a_labelled_table(self):
        batch = self.with_warning()
        page = self.page(batch)
        self.assertIn(REVIEW_BOX, page)
        self.assertIn('<label class="form-check-label" for="reviewed">I have reviewed the warnings.</label>', page)
        self.assertIn('role="region" aria-label="Warnings (1)" tabindex="0"', page)
        self.assertIn("Warning</span>", page)
        self.assertIn(f'<a href="{reverse("core:import-issues-csv", args=[batch.pk])}">Download problems as CSV</a>', page)

    def test_new_warnings_since_the_check_still_require_review(self):
        batch = self.clean()
        Guardian.objects.create(full_name="Someone Else", phone="9876543210")
        page = self.page(batch)
        self.assertIn("New warnings since this file was checked:", page)
        self.assertIn(REVIEW_BOX, page)

    def test_live_errors_hide_confirm_but_keep_discard_and_the_exact_notice(self):
        batch = self.clean()
        Section.objects.filter(class_grade__name="Class 5").delete()
        ClassGrade.objects.filter(name="Class 5").delete()
        page = self.page(batch)
        self.assertIn("School records changed since this file was checked:", page)
        self.assertIn("Upload the file again.", page)
        self.assertIn('role="alert"', page)
        self.assertNotIn("Confirm import", page)
        self.assertNotIn(f'action="{self.commit_url(batch)}"', page)
        self.assertIn(f'action="{self.discard_url(batch)}"', page)
        self.assertIn("Confirm is not available", page)

    def test_rejected_shows_errors_and_no_actions(self):
        batch = self.rejected()
        page = self.page(batch)
        self.assertIn("erp-status--revoked", page)
        self.assertIn("Rejected — has errors", page)
        self.assertIn("This file has 1 error. Nothing was imported. Fix the file and upload it again.", page)
        self.assertIn('role="region" aria-label="Errors (1)" tabindex="0"', page)
        self.assertIn("does not exist", page)
        self.assertNotIn("Confirm import", page)
        self.assertNotIn("Confirm or discard", page)
        self.assertNotIn("Students to import", page)

    def test_committed_state(self):
        committed = self.clean("Asha")
        self.client.post(self.commit_url(committed))
        page = self.page(committed)
        self.assertIn("erp-status--finalized", page)
        self.assertRegex(page, r"Imported 1 students; created 0 classes,\s+0 sections and 1 guardians;\s+reused 0 existing guardians\.")
        self.assertNotIn("Confirm or discard", page)

    def test_discarded_state(self):
        discarded = self.clean("Arjun")
        self.client.post(self.discard_url(discarded))
        page = self.page(discarded)
        self.assertIn("erp-status--inactive", page)
        self.assertIn("Discarded", page)
        self.assertNotIn("Confirm or discard", page)

    def test_expired_state_has_no_parsed_rows(self):
        stale = self.clean("Ravi")
        with after_lifetime():
            page = self.page(stale)
        self.assertIn("erp-status--stale", page)
        self.assertIn("Expired", page)
        self.assertNotIn("Confirm or discard", page)
        self.assertNotIn("Students to import", page)

    def test_failed_state_shows_the_reason(self):
        failing = self.batch_for(workbook([student_row("Meera", adm="M-1")]))
        other = Applicant.objects.create(full_name="Other", admission_status="ACCEPTED")
        other.progress_to_student().set_admission_number("M-1")
        self.client.post(self.commit_url(failing))
        page = self.page(failing)
        self.assertIn("Failed at import", page)
        self.assertIn("erp-status--revoked", page)
        self.assertIn('<dt class="col-sm-3">Reason</dt>', page)
        self.assertNotIn("Confirm or discard", page)


class CommitSafeguardTests(Base):
    def test_unreviewed_warnings_do_not_commit_and_reviewed_ones_do_exactly_once(self):
        batch = self.with_warning()
        response = self.client.post(self.commit_url(batch), follow=True)
        self.assertContains(response, "Confirm that you have reviewed the warnings before importing.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.VALIDATED)
        self.assertEqual((Student.objects.count(), self.events()), (0, 0))
        response = self.client.post(self.commit_url(batch), {"reviewed_warnings": "yes"}, follow=True)
        self.assertContains(response, "Imported 1 students.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.COMMITTED)
        self.assertEqual((Student.objects.count(), self.events()), (1, 1))

    def test_repeated_confirmation_changes_nothing(self):
        batch = self.clean()
        self.client.post(self.commit_url(batch))
        results = ImportRowResult.objects.count()
        response = self.client.post(self.commit_url(batch), follow=True)
        self.assertContains(response, "This import is no longer waiting for confirmation.")
        self.assertEqual((Student.objects.count(), self.events(), ImportRowResult.objects.count()), (1, 1, results))

    def test_commit_and_discard_are_post_only_csrf_protected_and_audited(self):
        batch = self.clean()
        self.assertEqual(self.client.get(self.commit_url(batch)).status_code, 405)
        self.assertEqual(self.client.get(self.discard_url(batch)).status_code, 405)
        strict = self.client_class(enforce_csrf_checks=True)
        strict.login(username="admin1", password="pass-12345")
        self.assertEqual(strict.post(self.commit_url(batch)).status_code, 403)
        self.assertEqual(strict.post(self.discard_url(batch)).status_code, 403)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.VALIDATED)
        self.client.post(self.commit_url(batch))
        event = SecurityEvent.objects.get(event_type=SecurityEvent.EventType.IMPORT_COMMITTED)
        self.assertEqual((event.actor, event.detail["batch"]), (self.admin, batch.pk))

    def test_discard_records_nothing_imported(self):
        batch = self.clean()
        response = self.client.post(self.discard_url(batch), follow=True)
        self.assertContains(response, "Import discarded. Nothing was imported.")
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.payload, Student.objects.count()),
                         (ImportBatch.Status.DISCARDED, {}, 0))

    def test_records_changed_fail_the_whole_batch(self):
        batch = self.batch_for(workbook([student_row("Asha", adm="A-1"), student_row("Arjun", adm="A-2")]))
        other = Applicant.objects.create(full_name="Other", admission_status="ACCEPTED")
        other.progress_to_student().set_admission_number("A-2")
        before = Student.objects.count()
        response = self.client.post(self.commit_url(batch), follow=True)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.FAILED)
        self.assertEqual(Student.objects.count(), before)
        self.assertContains(response, "School records changed since the file was checked")

    def test_csv_download_is_unchanged(self):
        batch = self.rejected()
        response = self.client.get(reverse("core:import-issues-csv", args=[batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="import-{batch.pk}-problems.csv"')
        self.assertIn(b"does not exist", response.content)


class ListTests(Base):
    def test_empty_state_header_and_actions(self):
        page = html(self.client.get(LIST))
        self.assertRegex(page, r'<h1 class="erp-page-title">Bulk imports</h1>')
        self.assertIn(f'<a class="btn btn-outline-secondary" href="{reverse("core:import-template")}">Download template</a>', page)
        self.assertIn(f'<a class="btn btn-primary" href="{UPLOAD}">New import</a>', page)
        self.assertIn("No imports yet.", page)
        self.assertIn(f'<br><a class="btn btn-outline-primary btn-sm mt-2" href="{UPLOAD}">Start an import</a>', page)
        self.assertIn('role="region" aria-label="Import batches" tabindex="0"', page)
        self.assertEqual(page.count('scope="col"'), 7)

    def test_every_status_is_a_text_badge_and_ids_are_row_headers(self):
        committed = self.clean("A1")
        self.client.post(self.commit_url(committed))
        discarded = self.clean("A2")
        self.client.post(self.discard_url(discarded))
        self.clean("A3")
        self.rejected()
        self.clean("A4")
        with after_lifetime():
            self.client.get(LIST)                                    # expires the stale batches
        page = html(self.client.get(LIST))
        for label in ("Imported", "Discarded", "Rejected — has errors", "Expired"):
            with self.subTest(label=label):
                self.assertRegex(page, rf'<span class="visually-hidden">Status: </span>{label}</span>')
        self.assertIn(
            f'<th scope="row" class="fw-semibold"><a href="{self.detail(committed)}">{committed.pk}'
            '<span class="visually-hidden"> (students.xlsx)</span></a></th>', page)
        self.assertNotIn("No imports yet.", page)

    def test_view_only_users_get_no_actions(self):
        _, viewer = self.client_with("view_importbatch")
        page = html(viewer.get(LIST))
        self.assertNotIn(UPLOAD, page)
        self.assertNotIn("Download template", page)
        self.assertIn("No imports yet.", page)
        self.clean()
        self.assertNotIn(UPLOAD, html(viewer.get(LIST)))


class UploadTests(Base):
    def test_structure_and_field_names(self):
        page = html(self.client.get(UPLOAD))
        self.assertRegex(page, r'<h1 class="erp-page-title">New import</h1>')
        self.assertIn('<form method="post" enctype="multipart/form-data" class="erp-form">', page)
        self.assertIn("Fields marked with an asterisk are required.", page)
        for name in ("academic_year", "enrollment_start_date", "file"):
            self.assertIn(f'name="{name}"', page)
        self.assertIn("An .xlsx workbook based on the import template, up to 2 MB.", page)
        self.assertIn("What happens next:", page)
        self.assertIn(f'<a href="{reverse("core:import-template")}">import template</a>', page)
        self.assertIn("Check file", page)
        self.assertIn(f'<a class="btn btn-link" href="{LIST}">Cancel</a>', page)

    def test_invalid_file_shows_a_linked_error_summary_and_creates_nothing(self):
        page = html(self.upload(b"name,class\n", name="students.csv"))
        self.assertIn('id="form-error-summary"', page)
        self.assertIn("Fix 1 problem before checking the file:", page)
        self.assertIn('href="#id_file"', page)
        self.assertIn("Upload an Excel .xlsx workbook.", page)
        page = html(self.upload(b"garbage", name="students.xlsx"))
        self.assertIn("This is not an Excel .xlsx workbook.", page)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_a_valid_upload_redirects_to_the_preview(self):
        response = self.upload(workbook([student_row("Asha")]))
        batch = ImportBatch.objects.get()
        self.assertRedirects(response, self.detail(batch))
        self.assertEqual(Student.objects.count(), 0)

    def test_cancel_is_gated_by_view_importbatch(self):
        _, runner = self.client_with("run_import")
        page = html(runner.get(UPLOAD))
        self.assertIn("Check file", page)
        self.assertNotIn(">Cancel</a>", page)


class PermissionTests(Base):
    def test_matrix(self):
        batch = self.rejected()
        pending = self.clean()
        urls = {
            "list": LIST, "detail": self.detail(batch),
            "csv": reverse("core:import-issues-csv", args=[batch.pk]),
            "upload": UPLOAD, "template": reverse("core:import-template"),
        }
        anonymous, teacher = self.client_class(), self.teacher()
        _, viewer = self.client_with("view_importbatch")
        _, runner = self.client_with("run_import")
        expected = {
            "list": (302, 403, 200, 403), "detail": (302, 403, 200, 403), "csv": (302, 403, 200, 403),
            "upload": (302, 403, 403, 200), "template": (302, 403, 403, 200),
        }
        for name, url in urls.items():
            with self.subTest(page=name):
                got = tuple(c.get(url).status_code for c in (anonymous, teacher, viewer, runner))
                self.assertEqual(got, expected[name])
        for url in (self.commit_url(pending), self.discard_url(pending)):
            self.assertEqual(teacher.post(url).status_code, 403)
            self.assertEqual(viewer.post(url).status_code, 403)
        pending.refresh_from_db()
        self.assertEqual(pending.status, ImportBatch.Status.VALIDATED)

    def test_view_only_user_sees_the_batch_but_no_confirm_or_discard(self):
        batch = self.with_warning()
        _, viewer = self.client_with("view_importbatch")
        page = self.page(batch, viewer)
        self.assertIn("Warnings (1)", page)
        self.assertNotIn("Confirm import", page)
        self.assertNotIn("Confirm or discard", page)
        self.assertNotIn("reviewed_warnings", page)


class NavigationTests(Base):
    def labels(self, url, user=None):
        context = breadcrumb_context(resolve(url), user)
        return [c["label"] for c in context["breadcrumbs"]], context["nav_section"]

    def test_rules_and_permission_matrix(self):
        batch = self.clean()
        self.assertEqual(self.labels(LIST), (["Overview", "Bulk imports"], "import-list"))
        self.assertEqual(self.labels(UPLOAD), (["Overview", "Bulk imports", "New import"], "import-list"))
        self.assertEqual(self.labels(self.detail(batch)), (["Overview", "Bulk imports", "Import"], "import-list"))
        runner, _ = self.client_with("run_import")
        self.assertEqual(self.labels(UPLOAD, runner)[0], [])
        user, _ = self.client_with("run_import", "view_school")
        self.assertEqual(self.labels(UPLOAD, user)[0], ["Overview", "New import"])
        user, _ = self.client_with("run_import", "view_school", "view_importbatch")
        self.assertEqual(self.labels(UPLOAD, user)[0], ["Overview", "Bulk imports", "New import"])
        user, _ = self.client_with("view_importbatch")
        self.assertEqual(self.labels(self.detail(batch), user)[0], ["Bulk imports", "Import"])

    def test_list_crumb_never_carries_a_pk(self):
        first, second = self.clean("A"), self.clean("B")
        for batch in (first, second):
            trail = breadcrumb_context(resolve(self.detail(batch)))["breadcrumbs"]
            self.assertEqual(trail[1]["url"], LIST)

    def test_sidebar_highlights_import_on_every_state(self):
        clean, rejected = self.clean(), self.rejected()
        committed = self.clean("Arjun")
        self.client.post(self.commit_url(committed))
        pages = {
            "list": self.client.get(LIST), "upload": self.client.get(UPLOAD),
            "upload-invalid": self.upload(b"x", name="a.csv"),
            "pending": self.client.get(self.detail(clean)),
            "rejected": self.client.get(self.detail(rejected)),
            "committed": self.client.get(self.detail(committed)),
            "after-discard": self.client.post(self.discard_url(clean), follow=True),
        }
        for name, response in pages.items():
            with self.subTest(page=name):
                self.assertEqual(re.findall(ACTIVE_LINK, html(response)), [LIST])


class LargeBatchTests(Base):
    """200 Student rows, 200 warnings and 200 errors with long names and messages: every row renders, nothing
    paginates, and the query count does not depend on the number of rows."""

    def students(self, count):
        return [
            student_row(f"Student {i:03d} {LONG}", adm=f"ADM-{i:04d}",
                        g1=(f"Parent {i:03d}", "Father", f"9{i:09d}", ""))
            for i in range(count)
        ]

    def pending(self, count):
        # one existing Guardian per row with the same phone but another name: one warning per row
        Guardian.objects.bulk_create(
            Guardian(full_name=f"Existing {i:03d}", phone=f"9{i:09d}")
            for i in range(count) if not Guardian.objects.filter(phone=f"9{i:09d}").exists())
        batch = self.batch_for(workbook(self.students(count)))
        self.assertEqual(batch.status, ImportBatch.Status.VALIDATED)
        return batch

    def long_rejected(self, count):
        batch = ImportBatch.objects.create(
            uploaded_by=self.admin, file_name=f"{LONG}.xlsx", file_sha256="0" * 64, academic_year=self.year,
            enrollment_start_date=self.start, student_rows=count, status=ImportBatch.Status.REJECTED,
            error_count=count, finished_at=timezone.now())
        ImportRowResult.objects.bulk_create(
            ImportRowResult(
                batch=batch, sheet="Students", row_number=i + 2, column=f"Column {i}"[:50], level="ERROR",
                message=(f"Row {i}: " + "This value is not accepted because it is far too long. " * 9)[:500])
            for i in range(count))
        return batch

    def queries(self, batch):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.detail(batch))
        self.assertEqual(response.status_code, 200)
        return len(ctx), html(response)

    def test_200_rows_render_in_full_with_no_pagination(self):
        batch = self.pending(200)
        self.assertEqual(batch.warning_count, 200)
        _, page = self.queries(batch)
        self.assertIn('aria-label="Students to import (200)"', page)
        self.assertIn('aria-label="Warnings (200)"', page)
        students = page.split('aria-label="Students to import (200)"')[1].split("</section>")[0]
        self.assertEqual(students.count("<tr>") - 1, 200)
        self.assertIn(f"Student 199 {LONG}", page)
        warnings = page.split('aria-label="Warnings (200)"')[1].split("</section>")[0]
        self.assertEqual(warnings.count("<tr>") - 1, 200)
        for marker in ("?page=", "Next page", "pagination"):
            self.assertNotIn(marker, page)

    def test_200_long_error_rows_render_in_full(self):
        batch = self.long_rejected(200)
        _, page = self.queries(batch)
        self.assertIn('aria-label="Errors (200)"', page)
        errors = page.split('aria-label="Errors (200)"')[1].split("</section>")[0]
        self.assertEqual(errors.count("<tr>") - 1, 200)
        self.assertEqual(len(re.findall(r"Row \d+: This value", errors)), 200)
        self.assertIn(LONG, page)                                    # the long file name

    def test_query_count_does_not_grow_with_rows(self):
        small, _ = self.queries(self.pending(20))
        large, _ = self.queries(self.pending(200))
        self.assertEqual(small, large)
        small_rejected, _ = self.queries(self.long_rejected(20))
        large_rejected, _ = self.queries(self.long_rejected(200))
        self.assertEqual(small_rejected, large_rejected)

    def test_the_big_batch_still_commits_atomically_after_review(self):
        batch = self.pending(200)
        self.client.post(self.commit_url(batch), {"reviewed_warnings": "yes"})
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.COMMITTED)
        self.assertEqual((Student.objects.count(), self.events()), (200, 1))
