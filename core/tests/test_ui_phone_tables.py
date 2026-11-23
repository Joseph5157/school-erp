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
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import AcademicYear, GradingScale
from core.tests.test_ui_admin_desktop_d1_5a_grading_scales import ScaleFixture
from core.tests.test_ui_admin_desktop_d1_5b_assessments import AssessmentFixture

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
        r'(<div class="erp-table-scroll erp-table-scroll--stack"[^>]*>)\s*(<table class="[^"]*\berp-table--stack\b[^"]*">.*?</table>)',
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
