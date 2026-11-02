from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core import charts

HIDDEN = "visually-hidden erp-visually-hidden-data"


def _css():
    return (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")


class ChartPartialTests(SimpleTestCase):
    def test_ring_partial_has_fixed_size_and_text_alternative(self):
        html = render_to_string(
            "partials/charts/_ring.html",
            {"c": charts.ring(30, 40), "label": "Registers submitted today"},
        )
        self.assertIn('width="76"', html)
        self.assertIn('height="76"', html)
        self.assertIn('role="img"', html)
        self.assertIn("Registers submitted today", html)
        self.assertIn("75%", html)
        self.assertNotIn("style=", html)

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

    def test_gauge_partial_has_text_alternative_and_target(self):
        html = render_to_string(
            "partials/charts/_gauge.html",
            {"c": charts.gauge(91, 90), "label": "Attendance rate"},
        )
        self.assertIn('role="img"', html)
        self.assertIn("Attendance rate", html)
        self.assertIn("91%", html)
        self.assertIn("target 90%", html)
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
        self.assertIn('role="img"', html)
        self.assertIn(HIDDEN, html)

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

    def test_wide_trend_keeps_a_fixed_height_in_css(self):
        css = _css()
        self.assertIn(".erp-trend--wide { height: 12.5rem;", css)
        self.assertIn(".erp-class-bars { max-width: 32rem;", css)
        self.assertIn("vector-effect: non-scaling-stroke", css)
        self.assertIn(".erp-chart-scroll {", css)
        self.assertIn("overflow-x: auto", css)
