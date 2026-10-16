from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from core.models import Applicant
from core.tables import Column, build_table, parse_choice

COLUMNS = (
    Column("Name", "name", ("full_name",)),
    Column("Status", "status", ("admission_status",)),
    Column("Notes"),
    Column("Actions", action=True),
)


class BuildTableTests(TestCase):
    def setUp(self):
        for index in range(30):
            Applicant.objects.create(full_name=f"Person {index:02d}")

    def table(self, query="", per_page=10, default_sort="name"):
        request = RequestFactory().get("/applicants/" + query)
        return build_table(
            request, Applicant.objects.all(), COLUMNS, default_sort, per_page=per_page
        )

    def names(self, table):
        return [applicant.full_name for applicant in table.page]

    def test_default_sort_ascending_with_aria_sort(self):
        table = self.table()
        self.assertEqual(self.names(table)[0], "Person 00")
        self.assertEqual(table.headers[0].aria_sort, "ascending")
        self.assertEqual(table.headers[1].aria_sort, "")
        self.assertEqual(table.sorted_by, "Name, ascending")

    def test_descending_sort_and_toggle_link(self):
        table = self.table("?sort=-name")
        self.assertEqual(self.names(table)[0], "Person 29")
        self.assertEqual(table.headers[0].aria_sort, "descending")
        self.assertIn("sort=name", table.headers[0].url)
        self.assertNotIn("sort=-name", table.headers[0].url)

    def test_ascending_header_links_to_descending(self):
        table = self.table()
        self.assertIn("sort=-name", table.headers[0].url)

    def test_unknown_or_unsortable_sort_falls_back_to_default(self):
        for raw in ("garbage", "-", "--name", "notes", "actions", "full_name"):
            with self.subTest(raw=raw):
                table = self.table(f"?sort={raw}")
                self.assertEqual(self.names(table)[0], "Person 00")

    def test_page_is_clamped_never_raises(self):
        self.assertEqual(self.table("?page=999").page.number, 3)
        self.assertEqual(self.table("?page=abc").page.number, 1)
        self.assertEqual(self.table("?page=0").page.number, 3)  # get_page clamps

    def test_count_text(self):
        self.assertEqual(self.table("?page=2").count_text, "Showing 11–20 of 30")

    def test_empty_queryset_says_no_results(self):
        request = RequestFactory().get("/applicants/?status=PENDING")
        table = build_table(request, Applicant.objects.none(), COLUMNS, "name")
        self.assertEqual(table.count_text, "No results")
        self.assertTrue(table.filtered)
        self.assertEqual(table.clear_url, "/applicants/")

    def test_header_links_keep_filters_and_drop_page(self):
        table = self.table("?status=PENDING&page=2")
        url = table.headers[0].url
        self.assertIn("status=PENDING", url)
        self.assertNotIn("page=", url)

    def test_page_links_keep_sort_and_filters(self):
        table = self.table("?status=PENDING&sort=-name&page=2")
        self.assertIn("sort=-name", table.next_url)
        self.assertIn("status=PENDING", table.next_url)
        self.assertIn("page=3", table.next_url)
        self.assertIn("page=1", table.prev_url)
        current = [link for link in table.page_links if link["current"]]
        self.assertEqual([link["number"] for link in current], [2])

    def test_first_and_last_page_have_no_prev_next(self):
        self.assertEqual(self.table().prev_url, "")
        self.assertEqual(self.table("?page=3").next_url, "")

    def test_action_and_plain_columns_are_not_sortable(self):
        table = self.table()
        self.assertFalse(table.headers[2].sortable)
        self.assertTrue(table.headers[3].action)
        self.assertFalse(table.headers[3].sortable)

    def test_ordering_is_deterministic_across_pages_with_ties(self):
        Applicant.objects.all().update(full_name="Same")
        seen = []
        for page in (1, 2, 3):
            seen += [a.pk for a in self.table(f"?page={page}").page]
        self.assertEqual(len(seen), 30)
        self.assertEqual(len(set(seen)), 30)

    def test_descending_override_is_used(self):
        columns = (
            Column("Date", "date", ("created_at", "full_name"), ("-created_at", "full_name")),
        )
        request = RequestFactory().get("/x/?sort=-date")
        table = build_table(request, Applicant.objects.all(), columns, "-date")
        self.assertEqual(table.sorted_by, "Date, descending")
        self.assertEqual(
            columns[0].order_by(True), ("-created_at", "full_name")
        )
        self.assertEqual(columns[0].order_by(False), ("created_at", "full_name"))

    def test_flipped_descending_when_no_override(self):
        column = Column("Name", "name", ("full_name", "-pk"))
        self.assertEqual(column.order_by(True), ("-full_name", "pk"))


class ParseChoiceTests(TestCase):
    CHOICES = [("PENDING", "Pending"), ("ACCEPTED", "Accepted")]

    def parse(self, query):
        return parse_choice(RequestFactory().get("/" + query), "status", self.CHOICES)

    def test_valid_value_returned(self):
        self.assertEqual(self.parse("?status=PENDING"), "PENDING")

    def test_invalid_or_missing_value_is_empty(self):
        self.assertEqual(self.parse("?status=BOGUS"), "")
        self.assertEqual(self.parse(""), "")


class PartialRenderingTests(TestCase):
    def setUp(self):
        for index in range(30):
            Applicant.objects.create(full_name=f"Person {index:02d}")
        request = RequestFactory().get("/applicants/?page=2")
        self.table = build_table(request, Applicant.objects.all(), COLUMNS, "name", per_page=10)

    def test_head_has_caption_scope_aria_sort_and_action_label(self):
        html = render_to_string(
            "partials/_table_head.html", {"table": self.table, "caption": "Applicants"}
        )
        self.assertIn("<caption", html)
        self.assertIn("Applicants", html)
        self.assertIn("Sorted by Name, ascending", html)
        self.assertIn('scope="col"', html)
        self.assertIn('aria-sort="ascending"', html)
        self.assertIn("Actions", html)

    def test_footer_has_count_and_pagination_nav(self):
        html = render_to_string("partials/_table_footer.html", {"table": self.table})
        self.assertIn("Showing 11–20 of 30", html)
        self.assertIn('aria-label="Pagination"', html)
        self.assertIn('aria-current="page"', html)

    def test_footer_hides_pagination_for_single_page(self):
        request = RequestFactory().get("/applicants/")
        table = build_table(request, Applicant.objects.all(), COLUMNS, "name", per_page=100)
        html = render_to_string("partials/_table_footer.html", {"table": table})
        self.assertNotIn('aria-label="Pagination"', html)
        self.assertIn("Showing 1–30 of 30", html)

    def test_footer_offers_clear_filters_when_filtered_and_empty(self):
        request = RequestFactory().get("/applicants/?status=PENDING")
        table = build_table(request, Applicant.objects.none(), COLUMNS, "name")
        html = render_to_string("partials/_table_footer.html", {"table": table})
        self.assertIn("No results", html)
        self.assertIn("Clear filters", html)
