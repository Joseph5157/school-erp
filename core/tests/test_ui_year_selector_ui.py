"""UI-04: academic-year dropdown in the office header and the mobile drawer row."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.models import TEACHERS_GROUP_NAME, AcademicYear, School, business_today
from core.tests.test_phase6_access_boundary import BoundaryFixture

User = get_user_model()
MENU = '<details class="erp-year-menu'
DRAWER = 'class="erp-year-drawer d-lg-none"'
CHIP = '<span class="visually-hidden">Academic year </span>'


class YearSelectorUiTests(TestCase):
    def setUp(self):
        School.objects.create(name="Sri Vidya School")
        today = business_today()
        self.old = AcademicYear.objects.create(
            name="2025-2026", start_date=today - timedelta(days=400), end_date=today - timedelta(days=60)
        )
        self.cur = AcademicYear.objects.create(
            name="2026-2027", start_date=today - timedelta(days=30), end_date=today + timedelta(days=300)
        )
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.teacher = User.objects.create_user(username="rao", password="pass-12345")
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))

    def get(self, user, url):
        client = self.client_class()
        client.force_login(user)
        return client.get(url)

    def test_admin_with_two_years_sees_menu_with_links(self):
        page = self.get(self.admin, reverse("core:school-detail"))
        self.assertContains(page, MENU)
        self.assertContains(page, CHIP + "2026-2027</span>")
        html = page.content.decode()
        panel = html[html.index('<ul class="erp-year-panel">'):]
        panel = panel[: panel.index("</ul>")]
        self.assertIn(">2025-2026</a>", panel)
        self.assertIn('aria-current="true">2026-2027</a>', panel)
        self.assertNotIn('aria-current="true">2025-2026', panel)

    def test_selected_year_follows_the_viewed_year(self):
        url = reverse("core:academic-year-assessments", kwargs={"pk": self.old.pk})
        page = self.get(self.admin, url)
        self.assertContains(page, CHIP + "2025-2026</span>")
        html = page.content.decode()
        panel = html[html.index('<ul class="erp-year-panel">'):]
        panel = panel[: panel.index("</ul>")]
        self.assertIn('aria-current="true">2025-2026</a>', panel)

    def test_single_year_keeps_the_plain_chip(self):
        self.old.delete()
        page = self.get(self.admin, reverse("core:school-detail"))
        self.assertNotContains(page, "erp-year-menu")
        self.assertNotContains(page, "erp-year-drawer")
        self.assertContains(page, CHIP + "2026-2027</span>")
        self.assertContains(page, 'class="erp-topbar-year')

    def test_teacher_has_no_menu_or_drawer_row(self):
        page = self.get(self.teacher, reverse("core:my-home"))
        self.assertNotContains(page, "erp-year-menu")
        self.assertNotContains(page, "erp-year-drawer")

    def test_login_page_has_no_menu(self):
        page = self.client_class().get(reverse("login"))
        self.assertNotContains(page, "erp-year-menu")
        self.assertNotContains(page, "erp-year-drawer")

    def test_drawer_row_present_for_admin_with_two_years(self):
        page = self.get(self.admin, reverse("core:school-detail"))
        self.assertContains(page, DRAWER)
        html = page.content.decode()
        drawer = html[html.index(DRAWER):]
        drawer = drawer[: drawer.index("</ul>")]
        self.assertIn("Academic year", drawer)
        self.assertIn(">2025-2026</a>", drawer)
        self.assertIn('aria-current="true">2026-2027</a>', drawer)
        self.assertLess(html.index(DRAWER), html.index("erp-nav-group"))


class GuardianPortalNoYearMenuTests(BoundaryFixture, TestCase):
    def test_portal_renders_no_menu(self):
        for name, start, end in (("2025-2026", "2025-06-01", "2026-04-30"), ("2026-2027", "2026-06-01", "2027-04-30")):
            AcademicYear.objects.get_or_create(name=name, defaults={"start_date": start, "end_date": end})
        page = self.guardian_client().get(reverse("portal:home"))
        self.assertNotContains(page, "erp-year-menu")
        self.assertNotContains(page, "erp-year-drawer")
