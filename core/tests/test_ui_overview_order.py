"""Overview order: work first, then the quiet checklist, then the context (gauge and rings)."""

import datetime

from django.test import TestCase
from django.urls import reverse

from core.dashboard import system_checklist
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
        self.assertLess(attention, html.index('id="clear-title"'))
        self.assertLess(attention, html.index('id="glance-title"'))
        self.assertLess(attention, html.index('id="analytics-title"'))

    def test_gauge_and_rings_are_kept(self):
        html = overview_html(self.administrator)
        attention = html.index('id="attention-title"')
        self.assertGreater(html.index("erp-gauge"), attention)
        self.assertGreater(html.index('class="erp-rings"'), attention)

    def test_checklist_lists_clear_items_quietly(self):
        html = overview_html(self.administrator)
        clear = html[html.index('id="clear-title"'):html.index('id="glance-title"')]
        self.assertIn("Attendance today", clear)
        self.assertNotIn("Applicants awaiting decision", clear)
        self.assertNotIn("erp-stat-card", clear)


class EmptySchoolOverviewTests(AuthorizationClientsMixin, TestCase):
    def test_empty_school_still_renders(self):
        response = self.administrator.get(reverse("core:admin-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set up your school")
        self.assertContains(response, 'id="clear-title"')


class SystemChecklistTests(TestCase):
    CLEAR = [{"title": "Missing attendance", "url": "/a/"}]

    def test_checklist_item_with_work_links_to_the_work(self):
        steps = [{"done": True, "url": "/x/"}, {"done": False, "url": "/fix/"}]
        items = system_checklist(self.CLEAR, steps)
        self.assertEqual(items[0], {"label": "Missing attendance", "ok": True, "url": "/a/"})
        self.assertEqual(items[-1], {"label": "Finish school setup", "ok": False, "url": "/fix/"})

    def test_setup_item_is_ok_when_every_step_is_done(self):
        items = system_checklist([], [{"done": True, "url": "/x/"}])
        self.assertEqual(items, [{"label": "School setup complete", "ok": True, "url": ""}])
