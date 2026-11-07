"""Security Gate 4B: an import batch's staged rows need `run_import`; problems carry no cell values.

`view_importbatch` shows a batch's status, counts and sanitised problems. The staged student
rows (names, dates of birth, admission numbers) are the uploader's working data and need
`run_import`. Problem output, on the page and in the CSV, never repeats an original cell value,
including a column header, and that holds for everyone, whatever their permissions.
"""

from django.urls import reverse

from core.tests.gate4b_support import holders
from core.tests.test_phase7_import import STUDENT_HEADER, ImportFixture, student_row, workbook

VIEW_BATCH = "core.view_importbatch"
RUN_IMPORT = "core.run_import"
ODD_HEADER = "Mira Das 2011-01-01"


class ImportBatchPermissionTests(ImportFixture):
    def pending_batch(self):
        """A clean batch with one distinctive student and a data-looking extra header."""
        data = workbook(
            [student_row("Zed Quirk", dob="04/03/2012", adm="ADM-7788")],
            student_header=[*STUDENT_HEADER, ODD_HEADER],
        )
        return self.batch_for(data)

    def failed_batch(self):
        """A batch whose row is rejected (impossible date), with values that must not leak."""
        data = workbook(
            [student_row("Quill Vance", dob="31/02/2012", adm="ADM-5566",
                         g1=("Sita Vance", "Mother", "9123456780", ""))],
        )
        return self.batch_for(data)

    def detail(self, batch):
        return reverse("core:import-detail", args=[batch.pk])

    def csv_url(self, batch):
        return reverse("core:import-issues-csv", args=[batch.pk])

    def test_view_importbatch_shows_status_and_counts_but_not_staged_rows(self):
        batch = self.pending_batch()
        self.assertTrue(batch.is_pending)
        for how, client in holders(self.client_class, VIEW_BATCH):
            with self.subTest(how=how):
                page = client.get(self.detail(batch))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "1 student rows")
                for staged in ("Zed Quirk", "ADM-7788", "2012"):
                    self.assertNotContains(page, staged)
                self.assertIsNone(page.context["plan"])
                self.assertContains(page, "Unknown column ignored")  # problems stay visible

    def test_run_import_shows_the_staged_rows(self):
        batch = self.pending_batch()
        for how, client in holders(self.client_class, VIEW_BATCH, RUN_IMPORT):
            with self.subTest(how=how):
                page = client.get(self.detail(batch))
                self.assertContains(page, "Zed Quirk")
                self.assertContains(page, "ADM-7788")
                self.assertIsNotNone(page.context["plan"])

    def test_problem_output_has_no_original_cell_values(self):
        failed = self.failed_batch()
        pending = self.pending_batch()
        leaks = (
            "Quill Vance", "31/02/2012", "ADM-5566", "Sita Vance", "9123456780",
            ODD_HEADER, "Mira Das", "2011-01-01",
        )
        clients = [("administrator", self.client)]
        clients += holders(self.client_class, VIEW_BATCH) + holders(
            self.client_class, VIEW_BATCH, RUN_IMPORT
        )
        for who, client in clients:
            for batch in (failed, pending):
                with self.subTest(who=who, batch=batch.pk):
                    page = client.get(self.detail(batch))
                    csv_response = client.get(self.csv_url(batch))
                    self.assertEqual(csv_response.status_code, 200)
                    for leak in leaks:
                        self.assertNotIn(leak, page.content.decode())
                        self.assertNotIn(leak, csv_response.content.decode())

    def test_stored_problems_use_a_column_letter_for_unknown_headers(self):
        batch = self.pending_batch()
        columns = list(batch.row_results.filter(level="WARNING").values_list("column", flat=True))
        self.assertTrue(columns)
        self.assertTrue(all(column.startswith("Column ") for column in columns), columns)

    def test_a_viewer_cannot_run_or_discard(self):
        batch = self.pending_batch()
        for how, client in holders(self.client_class, VIEW_BATCH):
            with self.subTest(how=how):
                for name in ("core:import-commit", "core:import-discard"):
                    response = client.post(reverse(name, args=[batch.pk]))
                    self.assertEqual(response.status_code, 403)
