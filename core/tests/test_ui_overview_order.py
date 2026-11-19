"""Overview order: work first, then the context."""

import datetime

from django.test import TestCase
from django.urls import reverse

from core.models import AcademicTerm, Applicant, School
from core.tests.test_admin_overview_analytics import A, AnalyticsFixture, P
from core.tests.test_authorization import AuthorizationClientsMixin


def overview_html(client):
    return client.get(reverse("core:admin-overview")).content.decode()


class OverviewOrderTests(AnalyticsFixture, TestCase):
    def setUp(self):
        super().setUp()
        School.objects.create(name="Greenwood High")
        Applicant.objects.create(full_name="Pending One")
        AcademicTerm.objects.create(
            academic_year=self.year, name="Term 1", start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 9, 30), display_order=1,
        )
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})

    def test_needs_attention_comes_before_status_and_analytics(self):
        html = overview_html(self.administrator)
        attention = html.index('id="attention-title"')
        self.assertLess(attention, html.index('id="glance-title"'))
        self.assertLess(attention, html.index('id="analytics-title"'))



class EmptySchoolOverviewTests(AuthorizationClientsMixin, TestCase):
    def test_empty_school_still_renders(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up your school")
