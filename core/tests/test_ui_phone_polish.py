"""Phone polish for the admin Overview (buttons, glance tiles, absentee rows, clear links, spacing).

Layout itself was checked in a real browser at 360/390px; these tests pin the markup and the
stylesheet rules the layout depends on.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from core.tests.test_authorization import AuthorizationClientsMixin

CSS = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")


def phone_block(css):
    """Every rule inside `@media (max-width: 767.98px)` blocks, joined."""
    return "\n".join(re.findall(r"@media \(max-width: 767\.98px\) \{(.*?)\n\}", css, re.S))


class GlanceTileTests(AuthorizationClientsMixin, TestCase):
    url = reverse("core:admin-overview")

    def glance_html(self, client):
        html = client.get(self.url).content.decode()
        start = html.index('id="glance-title"')
        return html[start: html.index("</section>", start)]

    def test_glance_figures_are_whole_tappable_tiles_without_open_buttons(self):
        glance = self.glance_html(self.administrator)
        self.assertEqual(glance.count("erp-stat-card--glance"), 4)
        self.assertRegex(
            glance, rf'<a class="erp-glance-tile erp-stat-card erp-stat-card--glance" href="{reverse("core:student-list")}"'
        )
        self.assertNotIn(">Open<", glance)
        self.assertNotIn("btn", glance)

    def test_a_figure_the_user_cannot_open_is_not_a_link(self):
        user = get_user_model().objects.create_user(username="glance-only", password="pass-12345")
        user.user_permissions.add(Permission.objects.get(codename="view_school"))
        client = self.client_class()
        client.login(username="glance-only", password="pass-12345")
        glance = self.glance_html(client)
        self.assertEqual(glance.count("<a "), 0)
        self.assertEqual(glance.count('<div class="erp-glance-tile erp-stat-card erp-stat-card--glance"'), 4)


class PhoneStylesheetTests(TestCase):
    def test_buttons_centre_their_label_in_the_44px_phone_height(self):
        phone = phone_block(CSS)
        self.assertIn(".btn { min-height: 2.75rem; display: inline-flex; align-items: center; justify-content: center; }", phone)
        # The desktop-only sidebar toggle must stay hidden on phones despite the flex rule.
        self.assertIn(".btn.erp-sidebar-toggle { display: none; }", CSS)

    def test_odd_last_glance_tile_spans_the_row(self):
        self.assertIn(".erp-stat-grid--glance > :last-child:nth-child(odd) { grid-column: 1 / -1; }", CSS)

    def test_glance_summaries_are_left_out_on_phones(self):
        self.assertIn(".erp-glance-tile .erp-stat-summary { display: none; }", phone_block(CSS))

    def test_absentee_rows_put_the_class_under_the_name(self):
        self.assertIn(".erp-absentee-class { grid-column: 1; grid-row: 2;", CSS)
        self.assertIn(".erp-absentee-days { grid-column: 2; grid-row: 1 / 3;", CSS)

    def test_attention_cards_are_compact_rows_that_open_from_anywhere_on_phones(self):
        phone = phone_block(CSS)
        # Count at the right end of the row, beside the title and sentence.
        self.assertIn(".erp-stat-grid--attention .erp-stat-value { grid-column: 2; grid-row: 1 / span 2; font-size: 1.5rem; }", phone)
        # The card's own Open link covers the whole card (explicit size beats the stat card button's align-self)...
        self.assertIn("{ position: absolute; inset: 0; width: 100%; height: 100%; margin: 0;", phone)
        # ...is drawn as the same chevron on every card, so no card's link looks more important...
        self.assertIn('.erp-stat-grid--attention .erp-stat-card > .erp-btn::after { content: "\\203A";', phone)
        # ...and keeps a visible keyboard focus ring.
        self.assertIn(".erp-stat-grid--attention .erp-stat-card > .erp-btn:focus-visible { outline: 3px solid var(--erp-focus-color);", phone)
        # Desktop keeps the cards and their Open buttons: none of this is outside the phone block.
        rule = ".erp-stat-grid--attention .erp-stat-card > .erp-btn"
        self.assertEqual(CSS.count(rule), phone.count(rule))
