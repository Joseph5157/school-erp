"""Audits 15-16 (PR 3): colour contrast, forced colours, below-target wording, static warnings, toast names."""

import re

from django.conf import settings
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import SimpleTestCase

CSS = (settings.BASE_DIR / "static" / "css" / "erp.css").read_text(encoding="utf-8")
PAPER, WHITE, INK = "#f5f6f3", "#ffffff", "#18212b"


def _luminance(colour):
    colour = colour.lstrip("#")
    channels = [int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def token(name):
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}});", CSS).group(1)


def rgb_token(name):
    r, g, b = (int(x) for x in re.search(rf"--{name}:\s*(\d+),\s*(\d+),\s*(\d+);", CSS).groups())
    return f"#{r:02x}{g:02x}{b:02x}"


class BootstrapUtilityColourTests(SimpleTestCase):
    """CLR-02: .text-secondary / .text-danger resolve to ERP colours that pass on paper and white."""

    def test_secondary_and_danger_rgb_map_to_erp_tokens_and_pass(self):
        self.assertEqual(rgb_token("bs-secondary-rgb"), token("erp-ink-soft").lower())
        self.assertEqual(rgb_token("bs-danger-rgb"), token("erp-bad").lower())
        for name in ("bs-secondary-rgb", "bs-danger-rgb"):
            for surface in (PAPER, WHITE):
                with self.subTest(token=name, surface=surface):
                    self.assertGreaterEqual(contrast(rgb_token(name), surface), 4.5)


class HeatmapContrastTests(SimpleTestCase):
    """CLR-03: every heatmap text/background pair reaches 4.5:1 for the small day numbers."""

    def test_every_tier_pair_passes(self):
        pairs = {
            "t1 white": (token("erp-viz-low"), WHITE),
            "t2 ink": (token("erp-viz-heat-1"), INK),
            "t3 white": (token("erp-viz-heat-2"), WHITE),
            "t4 white": (token("erp-viz-heat-3"), WHITE),
        }
        for name, (background, text) in pairs.items():
            with self.subTest(pair=name):
                self.assertGreaterEqual(contrast(background, text), 4.5)

    def test_tiers_stay_ordered_light_to_dark(self):
        heat = [_luminance(token(f"erp-viz-heat-{n}")) for n in (1, 2, 3)]
        self.assertGreater(heat[0], heat[1])
        self.assertGreater(heat[1], heat[2])


class StudentChartForcedColoursTests(SimpleTestCase):
    """CLR-04: the student bullet and radar charts take system colours in High Contrast."""

    def test_student_charts_have_a_forced_colours_block(self):
        blocks = re.findall(r"@media \(forced-colors: active\) \{(.*?)\n\}", CSS, re.S)
        student = next((b for b in blocks if ".erp-radar-outline--student" in b), "")
        for selector in (
            ".erp-bullet-bar", ".erp-bullet-marker", ".erp-bullet-track",
            ".erp-radar-outline--student", ".erp-radar-outline--section", ".erp-radar-label",
            ".erp-key--student", ".erp-key--section",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, student)
        self.assertIn("stroke-dasharray", student)  # the class-average outline stays dashed


class BelowTargetBarTests(SimpleTestCase):
    """CLR-05: a red (below-target) phone bar says so in words, not colour alone."""

    def render(self):
        rows = [
            {"label": "Grade 6", "value": 72.0, "display": "72%", "low": True, "url": None},
            {"label": "Grade 7", "value": 96.0, "display": "96%", "low": False, "url": None},
        ]
        return render_to_string(
            "partials/charts/_bars.html", {"rows": rows, "colour": "attendance", "target": 90}
        )

    def test_low_bar_names_the_target_and_on_target_bar_does_not(self):
        html = self.render()
        self.assertIn('aria-label="Grade 6, below the 90% attendance target"', html)
        self.assertIn('aria-label="Grade 7"', html)

    def test_phone_branch_explains_red(self):
        source = (
            settings.BASE_DIR / "templates" / "partials" / "_attendance_analytics.html"
        ).read_text(encoding="utf-8")
        phone = source.split('<div class="erp-class-phone">')[1].split("</div>")[0]
        self.assertIn("Red is under {{ a.attendance_target }}%", phone)
        self.assertIn("target=a.attendance_target", phone)


class StaticWarningRoleTests(SimpleTestCase):
    """NOTIF-04: warnings already on the page when it loads are notes, not assertive alerts."""

    TEMPLATES = [
        "announcement_prepare_confirm", "announcement_withdraw_confirm",
        "applicant_decision_confirm", "applicant_progress_confirm", "archive_confirm",
        "attendance_submit_confirm", "calendar_day_delete_confirm",
        "guardian_access_grant_confirm", "school_logo_remove_confirm",
        "student_deactivate_confirm", "student_reactivate_confirm", "teacher_deactivate_confirm",
    ]

    def test_confirm_pages_use_note_not_alert(self):
        for name in self.TEMPLATES:
            source = (
                settings.BASE_DIR / "core" / "templates" / "core" / f"{name}.html"
            ).read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertNotIn('role="alert"', source)
                self.assertIn('role="note"', source)


class ToastDismissNameTests(SimpleTestCase):
    """Audit 15: each toast's Dismiss button names the message it closes."""

    def test_dismiss_buttons_are_told_apart(self):
        html = render_to_string(
            "partials/_messages.html",
            {"messages": [
                Message(constants.SUCCESS, "Attendance saved."),
                Message(constants.ERROR, "Upload failed."),
            ]},
        )
        self.assertIn('aria-label="Dismiss: Attendance saved."', html)
        self.assertIn('aria-label="Dismiss: Upload failed."', html)
