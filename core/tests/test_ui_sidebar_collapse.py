"""Desktop admin sidebar can be hidden and shown from the top bar (phones keep the drawer).

Behaviour (click, remembered state, focus) lives in static/js/erp.js and was checked in a real
browser; these tests pin the server-rendered contract the script relies on.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import School

User = get_user_model()
STATIC = Path(settings.BASE_DIR) / "static"


class SidebarCollapseTests(TestCase):
    def setUp(self):
        School.objects.create(name="Sri Vidya School")
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse("core:admin-overview")).content.decode()

    def toggle(self):
        match = re.search(r"<button[^>]*data-erp-sidebar-toggle[^>]*>.*?</button>", self.html, re.S)
        self.assertIsNotNone(match, "desktop sidebar toggle missing")
        return match.group(0)

    def test_admin_pages_have_a_desktop_toggle_wired_to_the_sidebar(self):
        button = self.toggle()
        self.assertIn('aria-controls="erp-sidebar"', button)
        self.assertIn('aria-expanded="true"', button)
        self.assertIn('aria-label="Menu"', button)
        self.assertIn('aria-hidden="true"', button)  # the icon is decorative

    def test_toggle_starts_hidden_so_no_js_users_never_see_a_dead_button(self):
        self.assertRegex(self.toggle(), r"<button[^>]*\shidden[\s>]")

    def test_toggle_is_separate_from_the_phone_menu_button(self):
        self.assertNotIn("erp-menu-btn", self.toggle())
        self.assertNotIn("data-bs-toggle", self.toggle())
        self.assertRegex(self.html, r'<button[^>]*erp-menu-btn[^>]*d-lg-none')

    def test_saved_state_is_applied_in_the_head_before_first_paint(self):
        head = self.html.split("</head>", 1)[0]
        self.assertIn('localStorage.getItem("erp.nav.collapsed")', head)
        self.assertIn("erp-nav-collapsed", head)

    def test_pages_without_the_admin_sidebar_get_neither(self):
        self.client.logout()
        login = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("data-erp-sidebar-toggle", login)
        self.assertNotIn("erp.nav.collapsed", login)

    def test_collapse_only_applies_on_desktop_and_hides_the_sidebar_from_keyboard(self):
        css = (STATIC / "css" / "erp.css").read_text(encoding="utf-8")
        block = css.split("/* ---------- Desktop sidebar collapse ---------- */", 1)[1]
        self.assertIn("@media (min-width: 992px)", block)
        self.assertIn("html.erp-nav-collapsed body.has-sidebar .erp-sidebar", block)
        self.assertIn("visibility: hidden", block)  # collapsed links leave the tab order
        self.assertIn("html.erp-nav-collapsed body.has-sidebar .erp-main { margin-left: 0; }", block)

    def test_script_remembers_the_choice_and_updates_aria_expanded(self):
        js = (STATIC / "js" / "erp.js").read_text(encoding="utf-8")
        self.assertIn('"erp.nav.collapsed"', js)
        self.assertIn("data-erp-sidebar-toggle", js)
        self.assertIn('setAttribute("aria-expanded"', js)
