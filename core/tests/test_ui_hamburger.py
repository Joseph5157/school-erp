"""The admin phone/tablet menu button is a hamburger icon with an accessible name, not the word "Menu"."""

import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import AcademicYear, School

User = get_user_model()


class HamburgerButtonTests(TestCase):
    def setUp(self):
        School.objects.create(name="Sri Vidya School")
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))

    def test_admin_menu_button_is_an_icon_with_an_accessible_name(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("core:school-detail")).content.decode()
        button = re.search(r"<button[^>]*erp-menu-btn[^>]*>.*?</button>", html, re.S)
        self.assertIsNotNone(button)
        markup = button.group(0)
        self.assertIn('aria-label="Menu"', markup)
        self.assertIn('data-bs-target="#erp-sidebar"', markup)
        self.assertIn('<svg class="erp-hamburger"', markup)
        self.assertIn('aria-hidden="true"', markup)
        self.assertNotIn(">Menu</button>", markup)
        self.assertEqual(markup.count("<path"), 1)

    def test_button_stays_below_the_desktop_sidebar_breakpoint(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("core:school-detail")).content.decode()
        self.assertRegex(html, r'<button[^>]*erp-menu-btn[^>]*d-lg-none')

    def test_anonymous_login_page_has_no_menu_button(self):
        self.assertNotContains(self.client.get(reverse("login")), "erp-menu-btn")


class DrawerContextTests(TestCase):
    """The menu button reports its state and the drawer names the school and year (below md only)."""

    def _admin(self):
        user = User.objects.create_user(username="admin", password="pass-12345")
        user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(user)

    def _drawer_line(self, html):
        return re.search(r'<p[^>]*erp-drawer-context[^>]*>.*?</p>', html, re.S)

    def test_menu_button_starts_collapsed(self):
        School.objects.create(name="Sri Vidya School")
        self._admin()
        html = self.client.get(reverse("core:school-detail")).content.decode()
        button = re.search(r"<button[^>]*erp-menu-btn[^>]*>", html, re.S).group(0)
        self.assertIn('aria-expanded="false"', button)

    def test_erp_js_syncs_menu_state(self):
        script = (Path(settings.BASE_DIR) / "static" / "js" / "erp.js").read_text(encoding="utf-8")
        self.assertIn("shown.bs.offcanvas", script)
        self.assertIn("hidden.bs.offcanvas", script)
        self.assertIn("aria-expanded", script)

    def test_drawer_shows_school_and_year(self):
        School.objects.create(name="Sri Vidya School")
        today = date.today()
        AcademicYear.objects.create(
            name="2026-27", start_date=date(today.year - 1, 1, 1), end_date=date(today.year + 1, 12, 31)
        )
        self._admin()
        html = self.client.get(reverse("core:school-detail")).content.decode()
        line = self._drawer_line(html)
        self.assertIsNotNone(line)
        self.assertIn("Sri Vidya School", line.group(0))
        self.assertIn("2026-27", line.group(0))
        self.assertIn("d-md-none", line.group(0))
        self.assertIn(line.group(0), html[html.index('id="erp-sidebar"'):])

    def test_drawer_handles_no_school_or_year(self):
        self._admin()
        response = self.client.get(reverse("core:school-create"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIsNone(self._drawer_line(html))
        # With nothing to name, the header falls back to "Menu" at every drawer width.
        self.assertIn('<span class="erp-drawer-title h6 mb-0">Menu</span>', html)


class DrawerShellTests(TestCase):
    """Phone/tablet drawer: brand header and a signed-in footer with Log out (hidden on desktop)."""

    def setUp(self):
        School.objects.create(name="Sri Vidya School")
        user = User.objects.create_user(username="office1", password="pass-12345")
        user.groups.add(Group.objects.get(name="School Administrators"))
        self.client.force_login(user)
        html = self.client.get(reverse("core:school-detail")).content.decode()
        self.drawer = html[html.index('id="erp-sidebar"'):html.index("</nav>", html.index('id="erp-sidebar"'))]

    def test_header_shows_the_mark_without_a_logo(self):
        head = re.search(r'<div class="offcanvas-header erp-drawer-head">.*?</div>', self.drawer, re.S).group(0)
        self.assertRegex(head, r'<span class="erp-drawer-logo">\s*<svg class="erp-brand-mark"')
        self.assertIn("Sri Vidya School", head)
        self.assertIn('d-none d-md-inline">Menu</span>', head)

    def test_footer_names_the_user_and_posts_logout(self):
        foot = re.search(r'<div class="erp-drawer-foot d-lg-none">.*?</form>', self.drawer, re.S)
        self.assertIsNotNone(foot)
        foot = foot.group(0)
        self.assertIn("Signed in as </span>office1", foot)
        self.assertIn(f'<form method="post" action="{reverse("logout")}">', foot)
        self.assertIn('name="csrfmiddlewaretoken"', foot)

    def test_drawer_styles_stay_below_the_desktop_breakpoint(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "erp.css").read_text(encoding="utf-8")
        block = css[css.index("/* ---------- Admin drawer (below 992px) ---------- */"):]
        self.assertIn("@media (max-width: 991.98px) {\n  .erp-sidebar.offcanvas-lg {", block)
        self.assertIn("--bs-offcanvas-width: min(20rem, 86vw);", block)
