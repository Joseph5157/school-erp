"""The admin phone/tablet menu button is a hamburger icon with an accessible name, not the word "Menu"."""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import School

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
