"""Package C: opt-in stacked tables on phones (erp-table--stack).

Under 576px a converted table shows each row as a block, every value beside its column name. The
layout is CSS only and the real table markup stays, so these tests pin the markup contract the CSS
relies on (classes, labels taken from the headers, the labelled region) and that every rule for the
modifiers sits inside the phone media query. The layout itself is checked in a browser at 360, 390,
576 and 1366px.
"""

import re
from html import unescape

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.models import GradingScale
from core.tests.test_ui_admin_desktop_d1_5a_grading_scales import ScaleFixture

PHONE_QUERY = "@media (max-width: 575.98px)"
MODIFIERS = ("erp-table--stack", "erp-table-scroll--stack", "erp-stack-actions")


def text(fragment):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


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
            headers = [text(h) for h in re.findall(r'<th scope="col"[^>]*>(.*?)</th>', table, re.S)]
            self.assertTrue(headers, "the column headers stay in the markup")
            body = re.search(r"<tbody>(.*?)</tbody>", table, re.S).group(1)
            for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
                cells = re.findall(r"<(th|td)([^>]*)>", row)
                if len(cells) == 1 and "colspan=" in cells[0][1]:
                    continue  # empty-state row: one message spanning the table
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
            self.assertEqual(media, PHONE_QUERY, f"{selector!r} must only apply on phones")

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
            body for _, selector, body in self.stack_rules()
            if selector.strip().endswith("erp-table-scroll--stack")
        )
        # Both axes: with the base wrapper's overflow-y: hidden, overflow-x: visible alone computes to auto.
        self.assertIn("overflow: visible", bodies)
        self.assertIn("contain: none", bodies)

    def test_important_actions_are_44px_tall(self):
        bodies = " ".join(body for _, selector, body in self.stack_rules() if "erp-stack-actions" in selector)
        self.assertIn("min-height: 44px", bodies)
