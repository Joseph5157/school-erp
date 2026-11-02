from django.test import SimpleTestCase

from core import charts


class ChartGeometryTests(SimpleTestCase):
    def test_ring_is_none_with_nothing_to_count(self):
        self.assertIsNone(charts.ring(0, 0))

    def test_ring_zero_done_is_a_real_zero(self):
        self.assertEqual(charts.ring(0, 8)["percent"], 0)
        self.assertEqual(charts.ring(0, 8)["dash"], 0)

    def test_ring_is_100_only_when_everything_is_done(self):
        self.assertEqual(charts.ring(199, 200)["percent"], 99)

    def test_ring_is_0_only_when_nothing_is_done(self):
        r = charts.ring(1, 200)
        self.assertEqual(r["percent"], 1)
        self.assertGreater(r["dash"], 0)

    def test_ring_full_dash_equals_circumference(self):
        r = charts.ring(8, 8)
        self.assertEqual(r["percent"], 100)
        self.assertEqual(r["dash"], r["circumference"])

    def test_donut_shares_total_100_and_empty_is_none(self):
        d = charts.donut([("Present", 412), ("Absent", 38)])
        self.assertEqual(sum(s["share"] for s in d["segments"]), 100)
        self.assertEqual(d["headline_percent"], 92)
        self.assertIsNone(charts.donut([("Present", 0), ("Absent", 0)]))

    def test_donut_keeps_zero_parts_but_draws_nothing_for_them(self):
        d = charts.donut([("Present", 10), ("Late", 0), ("Absent", 10)])
        self.assertEqual([s["label"] for s in d["segments"]], ["Present", "Late", "Absent"])
        self.assertEqual(d["segments"][1]["dash"], 0)

    def test_gauge_none_percent_draws_nothing_and_met_flag(self):
        self.assertIsNone(charts.gauge(None, 80))
        self.assertTrue(charts.gauge(80, 80)["met"])
        self.assertFalse(charts.gauge(79.9, 80)["met"])

    def test_percent_display_rounds_half_up_like_floatformat(self):
        self.assertEqual(charts.percent_display(84.5), "85")
        self.assertEqual(charts.percent_display(84.4), "84")
        self.assertEqual(charts.percent_display(0), "0")
        self.assertEqual(charts.percent_display(100), "100")

    def test_percent_display_shows_a_decimal_when_rounding_would_reach_the_target(self):
        self.assertEqual(charts.percent_display(79.6, 80), "79.6")
        self.assertEqual(charts.percent_display(79.96, 80), "79.9")
        self.assertEqual(charts.percent_display(80, 80), "80")
        self.assertEqual(charts.percent_display(84.5, 80), "85")
        self.assertEqual(charts.percent_display(50, 80), "50")

    def test_gauge_displays_half_up_and_tests_the_unrounded_value(self):
        self.assertEqual(charts.gauge(84.5, 80)["display"], "85")
        self.assertTrue(charts.gauge(84.5, 80)["met"])
        low = charts.gauge(79.6, 80)
        self.assertEqual(low["display"], "79.6")
        self.assertFalse(low["met"])

    def test_donut_headline_is_100_only_when_nothing_else_has_a_count(self):
        d = charts.donut([("Present", 399), ("Absent", 1)])
        self.assertEqual(d["headline_percent"], 99)
        self.assertEqual([s["share"] for s in d["segments"]], [99, 1])
        self.assertEqual(charts.donut([("Present", 400), ("Absent", 0)])["headline_percent"], 100)

    def test_donut_headline_is_0_only_when_the_first_part_has_no_count(self):
        d = charts.donut([("Present", 1), ("Absent", 399)])
        self.assertEqual(d["headline_percent"], 1)
        self.assertEqual(sum(s["share"] for s in d["segments"]), 100)
        self.assertEqual(charts.donut([("Present", 0), ("Absent", 5)])["headline_percent"], 0)

    def test_gauge_zero_percent_is_drawn(self):
        self.assertIsNotNone(charts.gauge(0, 80))

    def test_columns_zero_value_has_no_height(self):
        row = charts.columns([{"label": "1", "value": 0, "display": "0%"}])[0]
        self.assertEqual(row["bar_height"], 0)
        self.assertEqual(row["bar_y"], 120)

    def test_columns_full_value_fills_height(self):
        row = charts.columns([{"label": "1", "value": 100, "display": "100%"}])[0]
        self.assertEqual(row["bar_height"], 120)
        self.assertEqual(row["bar_y"], 0)

    def test_bullet_keeps_zero_score_and_missing_parts(self):
        b = charts.bullet(0, None, None)
        self.assertEqual(b["score"], 0)
        self.assertIsNone(b["pass_width"])
        self.assertIsNone(b["marker_x"])

    def test_bullet_keeps_zero_pass_and_comparison(self):
        b = charts.bullet(50, 0, 0)
        self.assertEqual(b["pass_width"], 0)
        self.assertEqual(b["marker_x"], 0)

    def test_radar_only_draws_3_to_8_axes(self):
        self.assertIsNone(charts.radar(["a", "b"], [{"key": "s", "label": "S", "values": [1, 2]}]))
        self.assertIsNone(
            charts.radar(list("abcdefghi"), [{"key": "s", "label": "S", "values": [1] * 9}])
        )
        self.assertIsNotNone(
            charts.radar(list("abc"), [{"key": "s", "label": "S", "values": [1, 2, 3]}])
        )

    def test_radar_first_axis_points_straight_up_at_100(self):
        r = charts.radar(list("abcd"), [{"key": "s", "label": "S", "values": [100, 0, 0, 0]}])
        x, y = r["outlines"][0]["points"].split()[0].split(",")
        self.assertAlmostEqual(float(x), r["width"] / 2, places=1)
        self.assertLess(float(y), r["height"] / 2)

    def test_radar_refuses_three_outlines(self):
        outline = {"key": "s", "label": "S", "values": [1, 2, 3]}
        with self.assertRaises(ValueError):
            charts.radar(list("abc"), [outline, outline, outline])
