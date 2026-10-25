"""UI-11: the office and teacher header shows the school name and current academic year."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import TEACHERS_GROUP_NAME, AcademicYear, School, business_today
from core.tests.test_phase6_access_boundary import BoundaryFixture

User = get_user_model()
SCHOOL_SPAN = 'class="erp-topbar-school'
YEAR_SPAN = 'class="erp-topbar-year'


class HeaderContextTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Sri Vidya School")
        today = business_today()
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=today - timedelta(days=30), end_date=today + timedelta(days=300)
        )
        self.admin = User.objects.create_user(username="admin", password="pass-12345")
        self.admin.groups.add(Group.objects.get(name="School Administrators"))
        self.teacher = User.objects.create_user(username="rao", password="pass-12345")
        self.teacher.groups.add(Group.objects.get(name=TEACHERS_GROUP_NAME))

    def page(self, user, name):
        client = self.client_class()
        client.force_login(user)
        return client.get(reverse(name))

    def test_admin_header_shows_school_and_year(self):
        page = self.page(self.admin, "core:school-detail")
        self.assertContains(page, SCHOOL_SPAN)
        self.assertContains(page, ">Sri Vidya School</span>")
        self.assertContains(page, YEAR_SPAN)
        self.assertContains(page, '<span class="visually-hidden">Academic year </span>2026-2027</span>')

    def test_no_academic_year_means_no_chip(self):
        AcademicYear.objects.all().delete()
        page = self.page(self.admin, "core:school-detail")
        self.assertContains(page, SCHOOL_SPAN)
        self.assertNotContains(page, YEAR_SPAN)

    def test_no_school_row_means_no_school_name(self):
        School.objects.all().delete()
        page = self.page(self.admin, "core:academic-year-list")
        self.assertNotContains(page, SCHOOL_SPAN)
        self.assertContains(page, YEAR_SPAN)

    def test_teacher_area_shows_school_and_year(self):
        page = self.page(self.teacher, "core:my-home")
        self.assertContains(page, ">Sri Vidya School</span>")
        self.assertContains(page, "2026-2027</span>")
        self.assertContains(page, YEAR_SPAN)

    def test_brand_text_is_unchanged(self):
        for user, name in ((self.admin, "core:school-detail"), (self.teacher, "core:my-home")):
            with self.subTest(user=user.username):
                self.assertContains(self.page(user, name), "School ERP</a>")

    def test_login_page_shows_neither_and_runs_no_school_or_year_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            page = self.client_class().get(reverse("login"))
        self.assertNotContains(page, SCHOOL_SPAN)
        self.assertNotContains(page, YEAR_SPAN)
        sql = " ".join(q["sql"].lower() for q in ctx.captured_queries)
        self.assertNotIn("core_school", sql)
        self.assertNotIn("core_academicyear", sql)


class GuardianHeaderUnchangedTests(BoundaryFixture, TestCase):
    def test_portal_header_has_no_school_or_year(self):
        AcademicYear.objects.get_or_create(
            name="2026-2027", defaults={"start_date": "2026-06-01", "end_date": "2027-04-30"}
        )
        School.objects.get_or_create(name="Sri Vidya School")
        page = self.guardian_client().get(reverse("portal:home"))
        self.assertContains(page, "Guardian Portal</a>")
        self.assertNotContains(page, SCHOOL_SPAN)
        self.assertNotContains(page, YEAR_SPAN)
        self.assertEqual(page.context["school_name"], "")
        self.assertEqual(page.context["current_year_name"], "")
