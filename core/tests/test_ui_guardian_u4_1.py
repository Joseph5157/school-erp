"""U4-1: Guardian Home cards, Child Overview and the child switcher."""

from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core import guardian_access
from core import guardian_accounts as ga
from core.tests.test_phase6_portal_shell import PortalFixture


class ChildOverviewTests(PortalFixture, TestCase):
    def get(self, grant=None):
        return self.portal.get(reverse("portal:child", args=[(grant or self.asha_grant).public_id]))

    def test_overview_shows_header_summary_and_school_details(self):
        page = self.get()
        self.assertContains(page, 'class="erp-child-title"')
        self.assertContains(page, "School details")
        for label in ("Academic Year", "Class/Grade", "Section", "Enrolment status"):
            self.assertContains(page, f"<dt>{label}</dt>")
        self.assertContains(page, "Latest report card")
        self.assertEqual(page.context["summary"]["name"], "Asha Rao")

    def test_no_attendance_is_honest_not_zero_percent(self):
        page = self.get()
        self.assertIsNone(page.context["summary"]["attendance"])
        self.assertContains(page, "No attendance recorded yet")
        self.assertNotContains(page, "0%")

    def test_no_published_report_card_is_honest(self):
        page = self.get()
        self.assertContains(page, "No report cards published yet")

    def test_single_child_has_no_switcher(self):
        self.assertNotContains(self.get(), "data-erp-switcher")


class ChildSwitcherTests(PortalFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.ravi_grant = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)

    def test_multiple_visible_children_get_plain_link_switcher(self):
        page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, "data-erp-switcher")
        self.assertEqual(
            [i["student"].full_name for i in page.context["switcher_children"]],
            ["Asha Rao", "Ravi Rao"],
        )
        # JS-off: switching is an ordinary link to that child's Overview.
        self.assertContains(
            page, f'href="{reverse("portal:child", args=[self.ravi_grant.public_id])}"'
        )
        self.assertContains(page, 'aria-current="true"', count=1)

    def test_switching_keeps_nav_following_the_selected_child(self):
        page = self.portal.get(reverse("portal:child", args=[self.ravi_grant.public_id]))
        self.assertEqual(page.context["nav_grant"], self.ravi_grant)
        self.assertContains(
            page, reverse("portal:attendance", args=[self.ravi_grant.public_id])
        )

    def test_under_review_child_is_never_listed(self):
        real = guardian_access.pending_map

        def pending_ravi(grants):
            states = real(grants)
            return {
                g.pk: (True, *states[g.pk][1:]) if g.pk == self.ravi_grant.pk else states[g.pk]
                for g in grants
            }

        with mock.patch("core.portal.guardian_access.pending_map", side_effect=pending_ravi):
            page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
            home = self.portal.get(reverse("portal:home"))
        self.assertEqual(page.context["switcher_children"], [])
        self.assertNotContains(page, "data-erp-switcher")
        self.assertNotContains(page, reverse("portal:child", args=[self.ravi_grant.public_id]))
        self.assertContains(home, "Access under review")
        self.assertContains(home, "Ravi Rao")
        self.assertNotContains(home, reverse("portal:child", args=[self.ravi_grant.public_id]))


class HomeCardTests(PortalFixture, TestCase):
    def test_card_leads_with_name_and_keeps_notices_after_cards(self):
        page = self.portal.get(reverse("portal:home"))
        html = page.content.decode()
        self.assertIn('class="erp-child-name"', html)
        self.assertContains(page, "No attendance recorded yet")
        self.assertContains(page, "No report cards published yet")
        self.assertNotIn("data-erp-switcher", html)
