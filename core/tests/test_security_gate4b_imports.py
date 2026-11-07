"""Security Gate 4B: an import batch's staged rows need `run_import`; problems carry no cell values.

`view_importbatch` shows a batch's status, counts and sanitised problems. The staged student
rows (names, dates of birth, admission numbers) are the uploader's working data and need
`run_import`. Problem output, on the page and in the CSV, never repeats an original cell value,
including a column header, and that holds for everyone, whatever their permissions.
"""

import ast
import inspect

from django.urls import reverse
from django.utils import timezone

from core import imports
from core.models import ClassGrade, Section
from core.tests.gate4b_support import holders
from core.tests.test_phase7_import import STUDENT_HEADER, ImportFixture, student_row, workbook

# The only values a problem message may format in: a fixed label or a row number.
ALLOWED_INTERPOLATIONS = {
    "label",
    "file_admission_numbers[key]",
    "file_roll_numbers[section_ref, roll_number]",
    "file_identities[identity]",
    "file_names[name_key(full_name)]",
}


def unsafe_message(node):
    """Why a problem-message expression could carry a cell value, or None when it cannot.

    A message must be a fixed string, or an f-string whose every interpolation is in
    ALLOWED_INTERPOLATIONS (with no conversion or format spec). Anything else (concatenation,
    .format(), % formatting, a variable, a call) is refused, because it could carry a value.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return None
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant):
                continue
            if not isinstance(part, ast.FormattedValue):
                return f"unexpected f-string part {ast.dump(part)}"
            if part.conversion != -1 or part.format_spec is not None:
                return "an interpolation with a conversion or format spec"
            if ast.unparse(part.value) not in ALLOWED_INTERPOLATIONS:
                return f"interpolates {ast.unparse(part.value)!r}"
        return None
    return f"message is {type(node).__name__}, not a string constant or an allowlisted f-string"


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

    def placement_batch(self):
        """Missing and archived Class/Section values on both sheets, all distinctive."""
        quartz = ClassGrade.objects.create(name="Quartz Grade 88")
        section = Section.objects.create(class_grade=quartz, name="Rx-Omega-52")
        archived = {"archived_at": timezone.now(), "archived_by": self.admin}
        Section.objects.filter(pk=section.pk).update(**archived)
        ClassGrade.objects.filter(pk=quartz.pk).update(**archived)
        data = workbook(
            [
                student_row("Dina Moss", cls="Zebra Grade 77", sec="Qx-Zeta-91"),  # missing
                student_row("Eli Park", cls="Quartz Grade 88", sec="Rx-Omega-52"),  # archived
            ],
            classes=[["Quartz Grade 88", "Rx-Omega-52"]],  # archived, on the Classes sheet
        )
        return self.batch_for(data)

    def test_placement_problems_carry_no_class_or_section_values(self):
        batch = self.placement_batch()
        messages = self.messages_of(batch)
        # Each path really fired (so the test is not vacuous) ...
        self.assertTrue(any("does not exist" in m for m in messages), messages)
        self.assertEqual(sum("archived" in m for m in messages), 2, messages)
        leaks = ("Zebra Grade 77", "Qx-Zeta-91", "Quartz Grade 88", "Rx-Omega-52",
                 "Dina Moss", "Eli Park")
        clients = [("administrator", self.client)]
        clients += holders(self.client_class, VIEW_BATCH)
        for who, client in clients:
            with self.subTest(who=who):
                page = client.get(self.detail(batch)).content.decode()
                csv_text = client.get(self.csv_url(batch)).content.decode()
                for leak in leaks:
                    self.assertNotIn(leak, page)
                    self.assertNotIn(leak, csv_text)
                self.assertIn("does not exist", csv_text)
        for message in messages:  # and nothing was stored with a value in it either
            for leak in leaks:
                self.assertNotIn(leak, message)

    def test_no_problem_message_can_interpolate_a_cell_value(self):
        """Every error()/warn() message in validate() is fixed text plus row numbers only.

        The leak tests above prove the paths we know of; this fails the moment anyone writes a
        message that formats a cell value, a name or a header into stored problem text.
        """
        tree = ast.parse(inspect.getsource(imports))
        validate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "validate")
        checked = 0
        for node in ast.walk(validate):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("error", "warn")):
                continue
            checked += 1
            problem = unsafe_message(node.args[3])
            self.assertIsNone(problem, f"line {node.lineno}: {problem}")
        self.assertGreater(checked, 30)

    def test_the_message_guard_rejects_every_unsafe_form(self):
        unsafe = {
            "concatenation": '"Bad " + class_name',
            "reversed concatenation": 'class_name + " is bad"',
            ".format()": '"Bad {}".format(class_name)',
            "% formatting": '"Bad %s" % class_name',
            "a variable": "message",
            "a call": "describe(class_name)",
            "an f-string with a cell value": 'f"Bad {class_name}"',
            "an f-string with an unlisted slice": 'f"Bad {class_name[:100]}"',
            "an f-string with a format spec": 'f"Bad {label:>{class_name}}"',
        }
        for label, source in unsafe.items():
            with self.subTest(label):
                node = ast.parse(source, mode="eval").body
                self.assertIsNotNone(unsafe_message(node), source)
        safe = {
            "fixed text": '"Class is required."',
            "adjacent literals": '"Class and " "Section are required."',
            "a fixed label": 'f"{label} name is required."',
            "a row number": 'f"Same admission number as row {file_admission_numbers[key]}."',
        }
        for label, source in safe.items():
            with self.subTest(label):
                node = ast.parse(source, mode="eval").body
                self.assertIsNone(unsafe_message(node), source)

    def test_original_file_name_needs_run_import(self):
        file_name = "Priya Nair Admissions 2026.xlsx"
        batch = imports.create_batch(
            user=self.admin, file_name=file_name,
            data=workbook([student_row("Zed Quirk")]),
            academic_year=self.year, enrollment_start_date=self.start,
        )
        pages = (reverse("core:import-list"), self.detail(batch))
        for how, client in holders(self.client_class, VIEW_BATCH):
            for url in pages:
                with self.subTest(how=how, url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, "Priya")
                    self.assertNotContains(response, "Admissions 2026")
        for how, client in holders(self.client_class, VIEW_BATCH, RUN_IMPORT):
            for url in pages:
                with self.subTest(how=how, runner=True, url=url):
                    self.assertContains(client.get(url), file_name)
        for url in pages:  # the administrator group holds every permission
            self.assertContains(self.client.get(url), file_name)

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
