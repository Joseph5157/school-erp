"""Package C: opt-in stacked tables on phones (erp-table--stack).

Under 576px a converted table shows each row as a block, every value beside its column name. The
layout is CSS only and the real table markup stays, so these tests pin the markup contract the CSS
relies on (classes, labels taken from the headers, the labelled region) and that every rule for the
modifiers sits inside the phone media query. The layout itself is checked in a browser at 360, 390,
576 and 1366px.
"""

import re
from datetime import date
from html import unescape

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import AcademicYear, GradingScale, SchoolCalendarDay, Section, TermPublication
from core.tests.test_phase6_access_boundary import BoundaryFixture
from core.tests.test_ui_admin_desktop_d1_3c_access_reviews import AccessReviewsD13CBase
from core.tests.test_ui_admin_desktop_d1_5a_grading_scales import ScaleFixture
from core.tests.test_ui_admin_desktop_d1_5b_assessments import AssessmentFixture
from core.tests.test_ui_admin_desktop_d1_5c_result_reports import ReportFixture
from core.tests.test_ui_admin_desktop_d1_5d_term_publication import UiFixture
from core.tests.test_ui_admin_structure_s2 import Fixture as StructureFixture

PHONE_QUERY = "@media (max-width: 575.98px)"
MODIFIERS = ("erp-table--stack", "erp-table-scroll--stack", "erp-stack-actions")


def text(fragment):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def header_texts(table):
    """Column header names, ignoring decorative aria-hidden spans such as the sort arrow."""
    return [
        text(re.sub(r'<span[^>]*aria-hidden="true"[^>]*>.*?</span>', "", h, flags=re.S))
        for h in re.findall(r'<th scope="col"[^>]*>(.*?)</th>', table, re.S)
    ]


def stacked_tables(page):
    """(wrapper open tag, table html) for each stacked table on the page."""
    return re.findall(
        r'(<div class="erp-table-scroll erp-table-scroll--stack(?: [^"]*)?"[^>]*>)\s*(<table class="[^"]*\berp-table--stack\b[^"]*">.*?</table>)',
        page,
        re.S,
    )


class StackedTableContractMixin:
    """The markup contract every converted table must keep."""

    def assert_stacked_contract(self, page):
        tables = stacked_tables(page)
        self.assertTrue(tables, "no stacked table found")
        for wrapper, table in tables:
            # The labelled region keeps desktop keyboard scrolling.
            self.assertIn('role="region"', wrapper)
            self.assertRegex(wrapper, r'aria-label="[^"]+"')
            self.assertIn('tabindex="0"', wrapper)
            headers = header_texts(table)
            self.assertTrue(headers, "the column headers stay in the markup")
            body = re.search(r"<tbody\b[^>]*>(.*?)</tbody>", table, re.S).group(1)
            rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, re.S)
            self.assertTrue(rows, "the table body has rows")
            for row in rows:
                cells = re.findall(r"<(th|td)\b([^>]*)>", row)
                if len(cells) == 1 and "colspan=" in cells[0][1]:
                    # Empty-state row: one message spanning every column.
                    self.assertIn(f'colspan="{len(headers)}"', cells[0][1])
                    continue
                self.assertEqual(cells[0][0], "th")
                self.assertIn('scope="row"', cells[0][1])
                self.assertEqual(len(cells), len(headers), "one cell per column header")
                for column, (_, attrs) in enumerate(cells[1:], start=1):
                    if "erp-stack-actions" in attrs:
                        continue
                    label = re.search(r'data-label="([^"]*)"', attrs)
                    self.assertIsNotNone(label, f"cell under {headers[column]!r} has no data-label")
                    # The label is the column header, never inferred from position in CSS.
                    self.assertEqual(unescape(label.group(1)), headers[column])


class GradingScalesStackedTests(StackedTableContractMixin, ScaleFixture, TestCase):
    def setUp(self):
        self.build()

    def page(self):
        return self.client.get(self.list_url).content.decode()

    def test_grading_table_is_stacked_with_header_labels(self):
        self.assert_stacked_contract(self.page())

    def test_every_scale_row_is_labelled(self):
        ((_, table),) = stacked_tables(self.page())
        self.assertEqual(table.count('data-label="Status"'), 3)
        self.assertEqual(table.count('data-label="Applies to"'), 3)
        self.assertEqual(table.count('data-label="Grade bands"'), 3)

    def test_empty_state_row_needs_no_label(self):
        GradingScale.objects.all().delete()
        page = self.page()
        self.assert_stacked_contract(page)
        self.assertIn("No grading scales yet.", page)

    def test_table_keeps_its_existing_classes_and_caption(self):
        ((_, table),) = stacked_tables(self.page())
        self.assertIn('class="table erp-keep erp-grading-table erp-table--stack"', table)
        self.assertIn("<caption", table)


class AssessmentListStackedTests(StackedTableContractMixin, AssessmentFixture, TestCase):
    HEADERS = ["Assessment", "Status", "Subject", "Section", "Date", "Term", "Max", "Pass"]

    def setUp(self):
        self.build()
        # Same name as the draft, other section and date: the stacked rows must still tell them apart.
        self.quiz_b = self.unique_assessment("Quiz 1", section=self.six_b, on=date(2026, 7, 20))

    def page(self, params=None, url=None):
        return self.client.get(url or self.list_url, params or {}).content.decode()

    def rows(self, page):
        ((_, table),) = stacked_tables(page)
        body = re.search(r"<tbody\b[^>]*>(.*?)</tbody>", table, re.S).group(1)
        return re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, re.S)

    def test_wrapper_opts_into_stacking(self):
        self.assertEqual(len(stacked_tables(self.page())), 1)

    def test_table_keeps_its_existing_classes(self):
        self.assertIn(
            'class="table erp-assessment-table erp-assessment-list-table erp-rows-link erp-table--stack"',
            self.page(),
        )

    def test_wrapper_keeps_its_labelled_region(self):
        self.assertIn(
            f'role="region" aria-label="Assessments for {self.year.name}" tabindex="0"', self.page()
        )

    def test_every_cell_is_labelled_with_its_header(self):
        page = self.page()
        self.assert_stacked_contract(page)
        self.assertNotIn('data-label=""', page)
        ((_, table),) = stacked_tables(page)
        self.assertEqual(len(self.rows(page)), 3)
        for header in self.HEADERS[1:]:
            self.assertEqual(table.count(f'data-label="{header}"'), 3, header)

    def test_same_name_rows_stay_distinguishable(self):
        rows = self.rows(self.page())
        quizzes = [row for row in rows if ">Quiz 1</a>" in row]
        self.assertEqual(len(quizzes), 2)
        self.assertTrue(any(
            'data-label="Section">Grade 6 - A<' in r and 'data-label="Date">15 Jul 2026<' in r
            for r in quizzes
        ))
        self.assertTrue(any(
            'data-label="Section">Grade 6 - B<' in r and 'data-label="Date">20 Jul 2026<' in r
            for r in quizzes
        ))
        (midterm,) = [row for row in rows if ">Midterm</a>" in row]
        self.assertIn('data-label="Term">Term 2<', midterm)

    def test_filtered_empty_state_spans_every_column(self):
        page = self.page({"status": "FINALIZED", "term": self.term1.pk})
        self.assert_stacked_contract(page)
        self.assertIn('colspan="8"', page)
        self.assertIn("No assessments match these filters.", page)

    def test_unfiltered_empty_state_spans_every_column(self):
        other_year = AcademicYear.objects.create(
            name="2027-28", start_date=date(2027, 6, 1), end_date=date(2028, 3, 31)
        )
        page = self.page(url=reverse("core:academic-year-assessments", args=[other_year.pk]))
        self.assert_stacked_contract(page)
        self.assertIn('colspan="8"', page)
        self.assertIn("No assessments have been planned for this Academic Year yet.", page)

    def test_row_links_and_header_actions_are_unchanged(self):
        page = self.page()
        for assessment in (self.draft, self.final, self.quiz_b):
            detail = reverse("core:assessment-detail", args=[assessment.pk])
            self.assertIn(
                f'<th scope="row" class="fw-semibold"><a class="erp-row-link" href="{detail}">'
                f"{assessment.name}</a></th>",
                page,
            )
        self.assertIn(f'href="{reverse("core:assessment-create", args=[self.year.pk])}"', page)
        self.assertIn(
            f'href="{reverse("core:report-subject-section-results", args=[self.year.pk])}"', page
        )

    def test_no_progress_column_but_the_progress_filter_stays(self):
        page = self.page()
        ((_, table),) = stacked_tables(page)
        self.assertEqual(header_texts(table), self.HEADERS)
        thead = re.search(r"<thead\b.*?</thead>", table, re.S).group(0)
        self.assertNotIn("Progress", thead)
        self.assertIn('name="progress"', page)


def body_rows(table):
    body = re.search(r"<tbody\b[^>]*>(.*?)</tbody>", table, re.S).group(1)
    return re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, re.S)


def row_for(table, name):
    """The one body row whose row header shows name."""
    pattern = rf'<th scope="row"[^>]*>(?:<a [^>]*>)?{re.escape(name)}<'
    (row,) = [r for r in body_rows(table) if re.search(pattern, r)]
    return row


class AssessmentResultsStackedTests(StackedTableContractMixin, AssessmentFixture, TestCase):
    """Assessment detail: the results table, or the roster for viewers without marks."""

    def setUp(self):
        self.build()

    def page(self, url, client=None):
        return (client or self.client).get(url).content.decode()

    def only_table(self, page):
        ((wrapper, table),) = stacked_tables(page)
        return wrapper, table

    def empty_roster(self, *, pass_mark, finalized):
        section = Section.objects.create(class_grade=self.grade6, name="Empty")
        assessment = self.unique_assessment("Empty roster", section=section, pass_mark=pass_mark)
        if finalized:
            self.force_finalize(assessment)
        return reverse("core:assessment-detail", args=[assessment.pk])

    def test_draft_results_table_is_stacked_with_header_labels(self):
        page = self.page(self.draft_url)
        wrapper, table = self.only_table(page)
        self.assert_stacked_contract(page)
        self.assertNotIn('data-label=""', page)
        self.assertIn('role="region" aria-label="Results for Quiz 1" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-assessment-table erp-table--stack">', table)
        self.assertEqual(
            header_texts(table),
            ["Student", "Result", "Score", "%", "Grade", "Pass/Fail", "Entered by"],
        )
        ravi = row_for(table, "Ravi Rao")
        self.assertIn('<th scope="row" class="fw-semibold">Ravi Rao</th>', ravi)
        self.assertIn('data-label="Result">Marked<', ravi)
        self.assertIn('data-label="Score">17.00 / 20.00<', ravi)
        self.assertIn(
            'data-label="Result"><span class="text-muted">Not entered</span>', row_for(table, "Dev Rao")
        )
        self.assertIn('data-label="Result">Absent<', row_for(table, "Meera Rao"))
        self.assertNotIn("erp-stack-actions", table)  # a draft has no Correct column

    def test_correct_link_sits_in_the_actions_cell_and_names_assessment_and_student(self):
        page = self.page(self.final_url)
        _, table = self.only_table(page)
        self.assert_stacked_contract(page)
        self.assertEqual(
            header_texts(table), ["Student", "Result", "Score", "%", "Grade", "Entered by", "Actions"]
        )
        correct = reverse("core:result-correct", args=[self.zoya_result.pk])
        zoya = row_for(table, "Zoya Iyer")
        self.assertIn('data-label="Score">40.00 / 50.00<', zoya)
        self.assertIn(
            f'<td class="erp-stack-actions"><a href="{correct}" '
            'aria-label="Correct Midterm result for Zoya Iyer">Correct</a></td>',
            zoya,
        )

    def test_viewer_without_correct_permission_gets_no_actions_column(self):
        _, viewer = self.client_with("view_assessment", "view_studentresult")
        page = self.page(self.final_url, viewer)
        _, table = self.only_table(page)
        self.assert_stacked_contract(page)
        self.assertEqual(
            header_texts(table), ["Student", "Result", "Score", "%", "Grade", "Entered by"]
        )
        self.assertNotIn("erp-stack-actions", table)
        self.assertNotIn(reverse("core:result-correct", args=[self.zoya_result.pk]), page)

    def test_empty_results_roster_spans_every_column_for_each_role(self):
        _, viewer = self.client_with("view_assessment", "view_studentresult")
        url = self.empty_roster(pass_mark="8", finalized=True)
        for client, columns in ((self.client, 8), (viewer, 7)):
            with self.subTest(columns=columns):
                page = self.page(url, client)
                self.assert_stacked_contract(page)
                self.assertIn(f'<td colspan="{columns}">No Students are enrolled', page)

    def test_roster_without_marks_is_stacked(self):
        _, viewer = self.client_with("view_assessment")
        page = self.page(self.draft_url, viewer)
        wrapper, table = self.only_table(page)
        self.assert_stacked_contract(page)
        self.assertIn('role="region" aria-label="Roster for Quiz 1" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-assessment-table erp-table--stack">', table)
        self.assertEqual(header_texts(table), ["Student"])
        self.assertEqual(len(body_rows(table)), 3)
        self.assertNotIn("data-label", table)  # the row header is the only cell
        self.assertNotIn("17.00", page)

    def test_empty_roster_without_marks_spans_the_column(self):
        _, viewer = self.client_with("view_assessment")
        page = self.page(self.empty_roster(pass_mark=None, finalized=False), viewer)
        self.assert_stacked_contract(page)
        self.assertIn('<td colspan="1">No Students are on this roster.</td>', page)


class ResultSheetStackedTests(StackedTableContractMixin, ReportFixture, TestCase):
    def setUp(self):
        self.build()

    def test_result_sheet_is_stacked_with_header_labels(self):
        page = self.client.get(self.sheet_url).content.decode()
        ((wrapper, table),) = stacked_tables(page)
        self.assert_stacked_contract(page)
        self.assertNotIn('data-label=""', page)
        self.assertIn('role="region" aria-label="Result sheet for UT1" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-result-table erp-table--stack">', table)
        self.assertEqual(header_texts(table), ["Student", "Marks", "%", "Grade", "Pass/Fail"])
        self.assertIn('data-label="Marks">18.00 / 20.00<', row_for(table, "Asha Rao"))
        ravi = row_for(table, "Ravi Rao")
        self.assertIn('data-label="Marks">Absent<', ravi)
        self.assertIn('data-label="Grade">Not graded<', ravi)
        self.assertIn('data-label="Pass/Fail">Fail<', row_for(table, "Meera Rao"))


class ReportCardStackedTests(StackedTableContractMixin, ReportFixture, TestCase):
    def setUp(self):
        self.build()

    def check_card(self, page):
        ((wrapper, table),) = stacked_tables(page)
        self.assert_stacked_contract(page)
        self.assertNotIn('data-label=""', page)
        self.assertIn('role="region" aria-label="Mathematics results" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-result-table erp-table--stack">', table)
        self.assertEqual(
            header_texts(table), ["Assessment", "Date", "Marks", "%", "Grade", "Pass/Fail"]
        )
        ut1 = row_for(table, "UT1")
        self.assertIn('<td class="text-nowrap" data-label="Date">', ut1)
        self.assertIn('data-label="Marks">18.00 / 20.00<', ut1)

    def test_administrator_report_card_is_stacked(self):
        self.check_card(self.client.get(self.card_url).content.decode())

    def test_teacher_report_card_is_stacked(self):
        self.class_teacher(self.rao)
        self.check_card(self.login("rao").get(self.my_card).content.decode())

    def test_no_results_state_has_no_table(self):
        newcomer, _ = self.make_student("Nia Rao")
        url = reverse("core:report-term-report-card", args=[newcomer.pk, self.term1.pk])
        page = self.client.get(url).content.decode()
        self.assertEqual(stacked_tables(page), [])
        self.assertIn("No finalized results for this Term yet.", page)


class SharedResultCellsTests(ReportFixture, TestCase):
    """Callers of _result_cells.html that don't pass stacked render it exactly as before."""

    def setUp(self):
        self.build()

    def test_non_stacked_callers_get_no_labels(self):
        self.class_teacher(self.rao)
        for client, url in (
            (self.client, self.student_url),
            (self.login("rao"), reverse("core:my-student-detail", args=[self.asha.pk])),
        ):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertIn("core/_result_cells.html", [t.name for t in response.templates])
                self.assertContains(response, "18.00 / 20.00")
                self.assertNotContains(response, "data-label")
                self.assertNotContains(response, "erp-table--stack")


class PublicationDetailStackedTests(StackedTableContractMixin, UiFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = TermPublication.objects.get(student=self.asha, term=self.term1)
        self.url = reverse("core:publication-detail", args=[self.pub.pk])

    def test_both_tables_are_stacked_with_header_labels(self):
        page = self.client.get(self.url).content.decode()
        (entries_wrapper, entries), (versions_wrapper, versions) = stacked_tables(page)
        self.assert_stacked_contract(page)
        self.assertNotIn('data-label=""', page)
        self.assertIn(
            'role="region" aria-label="Results as released in version 1" tabindex="0"',
            entries_wrapper,
        )
        self.assertIn(
            'role="region" aria-label="All versions of this report card" tabindex="0"',
            versions_wrapper,
        )
        for table in (entries, versions):
            self.assertIn('<table class="table erp-publication-table erp-table--stack">', table)
        self.assertEqual(
            header_texts(entries),
            ["Subject", "Assessment", "Date", "Marks", "%", "Grade", "Pass/Fail"],
        )
        self.assertEqual(
            header_texts(versions), ["Version", "Status", "Published", "Status changed"]
        )
        (entry,) = body_rows(entries)
        self.assertIn('data-label="Assessment">UT1<', entry)
        self.assertIn('<td class="text-nowrap" data-label="Date">', entry)
        self.assertIn('data-label="Marks">15 / 20<', entry)
        (version,) = body_rows(versions)
        self.assertIn(f'<a href="{self.url}">Version 1</a>', version)
        self.assertIn(
            '<td class="text-break" data-label="Status changed"><span class="text-muted">Not changed</span>',
            version,
        )
        # The actions sit outside the tables and keep their permission gate.
        self.assertIn(reverse("core:publication-withdraw", args=[self.pub.pk]), page)

    def test_viewer_without_marks_sees_only_the_stacked_versions_table(self):
        _, viewer = self.client_with("view_termpublication")
        page = viewer.get(self.url).content.decode()
        ((wrapper, _),) = stacked_tables(page)
        self.assert_stacked_contract(page)
        self.assertIn('aria-label="All versions of this report card"', wrapper)
        self.assertNotIn("Results as released in version", page)
        self.assertNotIn(reverse("core:publication-withdraw", args=[self.pub.pk]), page)


def limited_client(test, username, *codenames):
    user = get_user_model().objects.create_user(username=username, password="pass-12345")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = test.client_class()
    client.login(username=username, password="pass-12345")
    return client


def guardians_table(page):
    (table,) = [t for w, t in stacked_tables(page) if 'aria-label="Guardians"' in w]
    return table


class StudentRecordGuardiansStackedTests(StackedTableContractMixin, BoundaryFixture, TestCase):
    """C5: the Guardians table on the student record; its actions keep their permission gates."""

    VIEW = ("view_student", "view_guardian")

    def page(self, client=None, student=None):
        url = reverse("core:student-detail", args=[(student or self.asha).pk])
        response = (client or self.client).get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_guardians_table_is_stacked_with_named_actions(self):
        page = self.page()
        self.assert_stacked_contract(page)
        self.assertEqual(len(stacked_tables(page)), 1)  # the history tables already have phone cards
        table = guardians_table(page)
        self.assertIn('<table class="table erp-row-heads-plain erp-table--stack">', table)
        self.assertEqual(header_texts(table), ["Guardian", "Relationship", "Actions"])
        edit = reverse("core:student-guardian-edit", args=[self.asha_link.pk])
        end = reverse("core:student-guardian-end", args=[self.asha_link.pk])
        self.assertIn(
            f'<td class="erp-stack-actions"><a href="{edit}">Change relationship'
            '<span class="erp-sr-only"> with Meena Rao</span></a>'
            f'<a class="ms-3 text-danger" href="{end}">End'
            '<span class="erp-sr-only"> relationship with Meena Rao</span></a></td>',
            table,
        )
        self.assertIn('data-label="Relationship">Mother<', table)

    def test_change_without_end_permission_keeps_only_change(self):
        client = limited_client(self, "changer", *self.VIEW, "change_studentguardian")
        table = guardians_table(self.page(client))
        self.assertIn(reverse("core:student-guardian-edit", args=[self.asha_link.pk]), table)
        self.assertNotIn(reverse("core:student-guardian-end", args=[self.asha_link.pk]), table)
        self.assertIn('<td class="erp-stack-actions">', table)

    def test_viewer_gets_no_actions_column(self):
        page = self.page(limited_client(self, "viewer", *self.VIEW))
        self.assert_stacked_contract(page)
        table = guardians_table(page)
        self.assertEqual(header_texts(table), ["Guardian", "Relationship"])
        self.assertNotIn("erp-stack-actions", table)
        self.assertNotIn(reverse("core:student-guardian-edit", args=[self.asha_link.pk]), page)

    def test_empty_state_spans_every_column_for_each_role(self):
        newcomer, _ = self.make_student("Nia Rao")
        viewer = limited_client(self, "viewer", *self.VIEW)
        for client, columns in ((self.client, 3), (viewer, 2)):
            with self.subTest(columns=columns):
                page = self.page(client, newcomer)
                self.assert_stacked_contract(page)
                self.assertIn(f'<td colspan="{columns}">No Guardians associated yet.</td>', page)

    def test_edit_links_get_the_tap_target_class(self):
        page = self.page()
        admission = reverse("core:student-admission-number", args=[self.asha.pk])
        roll = reverse("core:enrollment-roll-number", args=[self.asha_e.pk])
        self.assertIn(f'<a class="ms-2 small erp-edit-link" href="{admission}">Edit', page)
        # The desktop table and the phone card each carry the roll number link.
        self.assertEqual(page.count(f'<a class="ms-2 small erp-edit-link" href="{roll}">Edit'), 2)


class CalendarStackedTests(StackedTableContractMixin, StructureFixture, TestCase):
    """C6: calendar exceptions; Edit label and Remove stay behind their permissions."""

    def setUp(self):
        super().setUp()
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=date(2026, 9, 12), is_instructional=True, label="Make-up day"
        )
        self.url = reverse("core:academic-year-calendar", args=[self.year.pk])

    def page(self, client=None):
        return (client or self.administrator).get(self.url).content.decode()

    def test_exceptions_table_is_stacked_with_header_labels(self):
        page = self.page()
        self.assert_stacked_contract(page)
        ((wrapper, table),) = stacked_tables(page)
        self.assertIn('role="region" aria-label="Calendar exceptions" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-keep erp-row-heads-plain erp-table--stack">', table)
        self.assertEqual(header_texts(table), ["Date", "Day", "Type", "Label", "Actions"])
        self.assertEqual(len(body_rows(table)), 2)
        self.assertIn('data-label="Type">Extra instructional day<', table)
        self.assertIn('data-label="Label">Holiday<', table)

    def test_actions_cell_names_the_date(self):
        ((_, table),) = stacked_tables(self.page())
        update = reverse("core:calendar-day-update", args=[self.day.pk])
        delete = reverse("core:calendar-day-delete", args=[self.day.pk])
        self.assertRegex(
            table,
            rf'<td class="text-end erp-stack-actions">\s*<a class="btn btn-link btn-sm" href="{update}">'
            r'Edit label<span class="erp-sr-only"> for [^<]+</span></a>\s*'
            rf'<a class="btn btn-outline-danger btn-sm" href="{delete}">Remove<span class="erp-sr-only"> [^<]+</span></a>',
        )

    def test_viewer_gets_no_actions(self):
        page = self.page(limited_client(self, "viewer", "view_schoolcalendarday"))
        self.assert_stacked_contract(page)
        self.assertNotIn(reverse("core:calendar-day-update", args=[self.day.pk]), page)
        self.assertNotIn(reverse("core:calendar-day-delete", args=[self.day.pk]), page)

    def test_empty_state_spans_every_column(self):
        SchoolCalendarDay.objects.all().delete()
        page = self.page()
        self.assert_stacked_contract(page)
        self.assertIn('<td colspan="5">No exceptions.', page)


class AccessReviewsStackedTests(StackedTableContractMixin, AccessReviewsD13CBase, TestCase):
    """C6: pending access reviews; the Decision form sits in the stacked row's actions cell."""

    def test_reviews_table_is_stacked_with_decision_form_in_the_row(self):
        grant = self.pending("Asha Rao", "Meena Rao")
        page = self.client.get(self.url).content.decode()
        self.assert_stacked_contract(page)
        ((wrapper, table),) = stacked_tables(page)
        self.assertIn('role="region" aria-label="Pending access reviews" tabindex="0"', wrapper)
        self.assertEqual(header_texts(table), ["Student", "Guardian", "Last placement", "Decision"])
        (row,) = body_rows(table)
        self.assertIn('<th scope="row" class="text-break">Asha Rao</th>', row)
        self.assertIn('data-label="Last placement"><span class="text-muted">No enrollment</span>', row)
        actions = re.search(r'<td class="erp-stack-actions">(.*?)</td>', row, re.S).group(1)
        decide = reverse("core:guardian-access-review-decide", args=[grant.pk])
        self.assertIn(f'action="{decide}"', actions)
        self.assertIn('name="csrfmiddlewaretoken"', actions)
        self.assertIn('aria-label="Record decision for Asha Rao and guardian Meena Rao">Record</button>', actions)

    def test_viewer_gets_an_empty_decision_cell_and_no_form(self):
        self.pending("Asha Rao", "Meena Rao")
        page = self.client_with("view_guardianaccessreview").get(self.url).content.decode()
        self.assert_stacked_contract(page)
        ((_, table),) = stacked_tables(page)
        self.assertNotIn("<form", table)
        self.assertRegex(table, r'<td class="erp-stack-actions">\s*</td>')

    def test_empty_state_spans_every_column(self):
        page = self.client.get(self.url).content.decode()
        self.assert_stacked_contract(page)
        self.assertIn('<tr><td colspan="4">', page)


class StalePublicationsStackedTests(StackedTableContractMixin, UiFixture, TestCase):
    def test_stale_table_is_stacked_with_named_review_link(self):
        self.publish()
        self.correct()
        pub = self.pub_for(self.asha)
        page = self.client.get(reverse("core:publications-stale")).content.decode()
        self.assert_stacked_contract(page)
        ((wrapper, table),) = stacked_tables(page)
        self.assertIn('role="region" aria-label="Stale publications" tabindex="0"', wrapper)
        self.assertIn('<table class="table erp-publication-table erp-table--stack">', table)
        self.assertEqual(header_texts(table), ["Student", "Term", "Version", "Status", "Reason", "Review"])
        row = row_for(table, "Asha Rao")
        self.assertIn('data-label="Version">Version 1<', row)
        self.assertIn(f'data-label="Reason">{pub.status_reason}<', row)
        detail = reverse("core:publication-detail", args=[pub.pk])
        self.assertIn(
            f'<td class="erp-stack-actions"><a href="{detail}">Review'
            '<span class="erp-sr-only"> Asha Rao, Term 1 version 1</span></a></td>',
            row,
        )

    def test_empty_state_spans_every_column(self):
        page = self.client.get(reverse("core:publications-stale")).content.decode()
        self.assert_stacked_contract(page)
        self.assertIn('<tr><td colspan="6">', page)


class StackedTableContractCheckTests(StackedTableContractMixin, SimpleTestCase):
    """The contract check itself must not pass vacuously (rows with attributes, short colspans)."""

    def page(self, rows):
        return (
            '<div class="erp-table-scroll erp-table-scroll--stack" role="region" aria-label="T" tabindex="0">'
            '<table class="table erp-table--stack"><thead><tr><th scope="col">Name</th><th scope="col">Score</th>'
            f"</tr></thead><tbody>{rows}</tbody></table></div>"
        )

    def test_row_with_a_class_and_no_label_fails(self):
        with self.assertRaises(AssertionError):
            self.assert_stacked_contract(
                self.page('<tr class="table-warning"><th scope="row">A</th><td>9</td></tr>')
            )

    def test_row_with_a_class_and_a_label_passes(self):
        self.assert_stacked_contract(
            self.page(
                '<tr class="table-warning"><th scope="row">A</th><td data-label="Score">9</td></tr>'
            )
        )

    def test_empty_state_must_span_every_column(self):
        with self.assertRaises(AssertionError):
            self.assert_stacked_contract(self.page('<tr><td colspan="1">None</td></tr>'))
        self.assert_stacked_contract(self.page('<tr><td colspan="2">None</td></tr>'))

    def sortable_page(self, label):
        return (
            '<div class="erp-table-scroll erp-table-scroll--stack" role="region" aria-label="T" tabindex="0">'
            '<table class="table erp-table--stack"><thead><tr><th scope="col">Name</th>'
            '<th scope="col" aria-sort="ascending"><a class="erp-sort-link" href="?sort=-date">Date'
            '<span class="erp-sort-arrow" aria-hidden="true">&#9650;</span></a></th></tr></thead>'
            f'<tbody><tr><th scope="row">A</th><td data-label="{label}">1 Jul</td></tr></tbody></table></div>'
        )

    def test_sort_arrow_is_not_part_of_the_header_label(self):
        self.assert_stacked_contract(self.sortable_page("Date"))
        with self.assertRaises(AssertionError):
            self.assert_stacked_contract(self.sortable_page("Term"))


class StackedTableCssTests(SimpleTestCase):
    def setUp(self):
        css = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        self.css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    def rules(self):
        """(enclosing at-rule or '', selector, body) for every style rule in the file."""
        out, stack, buf = [], [], ""
        for char in self.css:
            if char == "{":
                stack.append(buf.strip())
                buf = ""
            elif char == "}":
                selector = stack.pop() if stack else ""
                if not selector.startswith("@"):
                    out.append((stack[-1] if stack else "", selector, buf.strip()))
                buf = ""
            else:
                buf += char
        return out

    def stack_rules(self):
        return [rule for rule in self.rules() if any(m in rule[1] for m in MODIFIERS)]

    def test_stack_rules_exist(self):
        selectors = " ".join(selector for _, selector, _ in self.stack_rules())
        for modifier in MODIFIERS:
            self.assertIn(modifier, selectors)

    def test_every_stack_rule_is_inside_the_phone_query(self):
        for media, selector, _ in self.stack_rules():
            # The phone query, optionally narrowed further (e.g. "and (hover: hover)").
            self.assertTrue(
                media.startswith(PHONE_QUERY), f"{selector!r} must only apply on phones"
            )

    def test_labels_come_from_data_label_not_position(self):
        rules = self.stack_rules()
        self.assertTrue(any("attr(data-label)" in body for _, _, body in rules))
        for _, selector, _ in rules:
            self.assertNotIn("nth-child", selector)
            self.assertNotIn("nth-of-type", selector)

    def test_headers_stay_in_the_accessibility_tree(self):
        thead_rules = [body for _, selector, body in self.stack_rules() if "thead" in selector]
        self.assertTrue(thead_rules)
        for body in thead_rules:
            self.assertNotIn("display: none", body)
            self.assertNotIn("visibility: hidden", body)

    def test_wrapper_stops_scrolling_sideways_on_phones(self):
        bodies = " ".join(
            body
            for _, selector, body in self.stack_rules()
            if selector.strip().endswith("erp-table-scroll--stack")
        )
        # Both axes: with the base wrapper's overflow-y: hidden, overflow-x: visible alone computes to auto.
        self.assertIn("overflow: visible", bodies)
        self.assertIn("contain: none", bodies)

    def test_important_actions_are_44px_tall_and_a_lone_action_is_full_width(self):
        rules = [
            (selector, body)
            for _, selector, body in self.stack_rules()
            if "erp-stack-actions" in selector
        ]
        self.assertIn("min-height: 44px", " ".join(body for _, body in rules))
        self.assertTrue(any(":only-child" in s and "width: 100%" in b for s, b in rules))

    def label_rules(self):
        return [(s, b) for _, s, b in self.stack_rules() if "td[data-label]" in s]

    def test_label_is_not_read_twice_by_screen_readers(self):
        # Empty alternative text for the generated label: the column header already names the cell.
        before = " ".join(b for s, b in self.label_rules() if "::before" in s)
        self.assertIn('content: attr(data-label) / ""', before)

    def test_cells_with_several_children_keep_them_beside_the_label(self):
        # A grid cell would push a second child under the label column; the label floats instead.
        for selector, body in self.label_rules():
            self.assertNotIn("display: grid", body, selector)
        self.assertIn("float: left", " ".join(b for s, b in self.label_rules() if "::before" in s))

    def test_stacked_cells_drop_any_max_width_cap(self):
        # A table's own cell max-width (e.g. a clamped column) would leave a narrow block on phones.
        cell = ".erp-content .erp-table-scroll--stack > table.erp-table--stack > tbody > tr > *"
        rules = [
            (m, b)
            for m, s, b in self.stack_rules()
            if cell in [part.strip() for part in s.split(",")] and "display: block" in b
        ]
        self.assertTrue(rules)
        for media, body in rules:
            self.assertTrue(media.startswith(PHONE_QUERY))
            self.assertIn("max-width: none", body)

    def test_long_values_wrap_even_in_nowrap_columns(self):
        # Bootstrap's .text-nowrap is !important; a stacked value must still wrap rather than leave the screen.
        cell = [b for s, b in self.label_rules() if "::before" not in s and "display: flow-root" in b]
        self.assertEqual(len(cell), 1)
        self.assertIn("white-space: normal !important", cell[0])

    def test_sortable_tables_keep_visible_sort_links_on_phones(self):
        # A hidden header would hide the sort links and leave keyboard focus on invisible links.
        rules = {s.strip(): b for _, s, b in self.stack_rules() if "erp-sort-link" in s}
        strip = next(b for s, b in rules.items() if s.endswith("> thead:has(.erp-sort-link)"))
        self.assertIn("position: static", strip)
        self.assertIn("clip: auto", strip)
        sortable = next(b for s, b in rules.items() if s.endswith("> th:has(.erp-sort-link)"))
        self.assertIn("display: block", sortable)
        others = next(b for s, b in rules.items() if s.endswith("> th:not(:has(.erp-sort-link))"))
        self.assertIn("clip: rect(0, 0, 0, 0)", others)  # visually hidden, still a column header
        self.assertIn("min-height: 24px", " ".join(rules.values()))

    def test_hover_tints_the_whole_stacked_row(self):
        hover = [(m, b) for m, s, b in self.stack_rules() if "tr:hover" in s]
        self.assertTrue(hover)
        for media, body in hover:
            self.assertIn("(hover: hover)", media)
            self.assertIn("background:", body)

    def test_edit_link_has_a_24px_tap_target(self):
        # C5: global on purpose (the target applies at every width); the box grows only to 24px.
        (body,) = [b for _, s, b in self.rules() if s.strip() == ".erp-edit-link"]
        self.assertIn("display: inline-flex", body)
        self.assertIn("min-width: 24px", body)
        self.assertIn("min-height: 24px", body)
