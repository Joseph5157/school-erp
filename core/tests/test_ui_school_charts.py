from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core import charts

HIDDEN = "visually-hidden erp-visually-hidden-data"


def _css():
    return (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")


class ChartPartialTests(SimpleTestCase):
    def test_donut_partial_lists_every_segment_with_title(self):
        html = render_to_string(
            "partials/charts/_donut.html",
            {"c": charts.donut([("Present", 8), ("Absent", 2), ("Late", 0)]), "label": "Today"},
        )
        self.assertIn('width="110"', html)
        self.assertIn('role="img"', html)
        self.assertIn(HIDDEN, html)
        self.assertIn("<title>Present: 8 (80%)</title>", html)
        self.assertIn("Late", html)
        self.assertNotIn("style=", html)

    def test_column_svg_is_24px_wide_whatever_the_card_width(self):
        rows = charts.columns(
            [
                {"label": "1A", "value": 90, "display": "90%"},
                {"label": "1B", "value": 70, "display": "70%", "low": True},
            ]
        )
        html = render_to_string(
            "partials/charts/_columns.html", {"rows": rows, "colour": "attendance", "label": "x"}
        )
        self.assertEqual(html.count('width="24"'), 2)
        self.assertNotIn("style=", html)
        self.assertNotIn('<ul class="erp-cols erp-cols--attendance" role="img"', html)
        self.assertIn('<ul class="erp-cols erp-cols--attendance" aria-label="x">', html)
        self.assertEqual(html.count('role="img"'), 2)
        self.assertIn('aria-label="1A: 90%"', html)
        self.assertNotIn(HIDDEN, html)

    def test_many_columns_scroll_inside_the_card(self):
        html = render_to_string(
            "partials/charts/_columns.html",
            {
                "rows": charts.columns(
                    [{"label": str(i), "value": 90, "display": "90%"} for i in range(25)]
                ),
                "colour": "attendance",
                "label": "x",
            },
        )
        self.assertIn("erp-chart-scroll", html)
        self.assertEqual(html.count('width="24"'), 25)

    def test_column_links_only_when_given_a_url(self):
        rows = charts.columns(
            [
                {"label": "1A", "value": 90, "display": "90%", "url": "/classes/1/"},
                {"label": "1B", "value": 80, "display": "80%"},
            ]
        )
        html = render_to_string(
            "partials/charts/_columns.html", {"rows": rows, "colour": "marks", "label": "x"}
        )
        self.assertEqual(html.count("<a "), 1)
        self.assertIn('<a class="erp-col" href="/classes/1/"', html)

    def test_low_column_is_red_and_labelled(self):
        rows = charts.columns([{"label": "1A", "value": 70, "display": "70%", "low": True}])
        html = render_to_string(
            "partials/charts/_columns.html", {"rows": rows, "colour": "attendance", "label": "x"}
        )
        self.assertIn("erp-col--low", html)
        self.assertIn('<span class="erp-col-value">70%</span>', html)

    def test_bars_partial_uses_progress_and_marks_low(self):
        rows = [
            {"label": "1A", "value": 90, "display": "90%", "low": False, "url": "/c/1/"},
            {"label": "1B", "value": 70, "display": "70%", "low": True},
        ]
        html = render_to_string(
            "partials/charts/_bars.html", {"rows": rows, "colour": "marks", "label": "By class"}
        )
        self.assertEqual(html.count("<progress"), 2)
        self.assertIn("erp-class-bar--marks", html)
        self.assertIn("erp-class-bar--low", html)
        self.assertEqual(html.count("<a "), 1)
        self.assertIn("70%", html)

    def test_class_bars_and_scroll_css_stay(self):
        css = _css()
        self.assertIn(".erp-class-bars { max-width: 32rem;", css)
        self.assertIn(".erp-chart-scroll {", css)
        self.assertIn("overflow-x: auto", css)

    def test_unused_chart_css_is_gone(self):
        css = _css()
        self.assertNotIn(".erp-chart-big", css)
        self.assertNotIn(".erp-donut-seg--2", css)
        self.assertNotIn(".erp-donut-seg--3", css)
        self.assertEqual(css.count(".erp-donut-legend {"), 1)

