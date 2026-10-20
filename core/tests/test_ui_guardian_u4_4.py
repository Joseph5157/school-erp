"""U4-4: final Guardian portal hardening (switcher destinations, nav, state matrix)."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from core import guardian_access, publication
from core import guardian_accounts as ga
from core.models import (
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianAccessReview,
    StudentResult,
)
from core.tests.test_phase6_access_boundary import METHOD
from core.tests.test_ui_guardian_u4_3b import CardFixture

NAV = re.compile(r'<nav class="(?:erp-portal-nav|erp-tabbar)[^"]*".*?</nav>', re.S)
CURRENT = re.compile(r'<a href="[^"]*" class="active" aria-current="page">(.*?)</a>')


class PortalFixture(CardFixture):
    def setUp(self):
        super().setUp()
        self.ravi_grant = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)

    def review_child(self, name):
        """A linked child with no placement and no decision: access under review."""
        student, enrollment = self.make_student(name)
        enrollment.delete()
        grant = ga.grant_student_access(
            student_guardian=self.relate(student, self.meena), actor=self.admin)
        return student, grant

    def url(self, name, grant, *args):
        return reverse(name, args=[grant.public_id, *args])

    def navs(self, page):
        return [m.group(0) for m in NAV.finditer(page.content.decode())]

    def switcher(self, page):
        return [(i["student"].full_name, i["url"]) for i in page.context["switcher_children"]]


class SwitcherDestinationTests(PortalFixture, TestCase):
    def assert_switch(self, page, route):
        expected = [("Asha Rao", reverse(route, args=[self.asha_grant.public_id])),
                    ("Ravi Rao", reverse(route, args=[self.ravi_grant.public_id]))]
        self.assertEqual(self.switcher(page), expected)
        html = page.content.decode()
        start = html.index("data-erp-switcher")
        block = html[start:html.index("</details>", start)]
        for _, href in expected:  # plain links inside a native <details>: works with JS off
            self.assertIn(f'href="{href}"', block)
        self.assertIn("<details", html[html.index("data-erp-switcher") - 40:])

    def test_overview_switches_to_the_other_childs_overview(self):
        self.assert_switch(self.portal.get(self.url("portal:child", self.asha_grant)),
                           "portal:child")

    def test_attendance_switches_to_the_other_childs_attendance(self):
        self.assert_switch(self.portal.get(self.url("portal:attendance", self.asha_grant)),
                           "portal:attendance")

    def test_report_cards_list_switches_to_the_other_childs_list(self):
        self.assert_switch(self.portal.get(self.url("portal:report-cards", self.asha_grant)),
                           "portal:report-cards")

    def test_individual_report_card_switches_to_the_other_childs_list_never_a_publication(self):
        card = self.asha_card()
        page = self.portal.get(self.url("portal:report-card", self.asha_grant, card.public_id))
        self.assert_switch(page, "portal:report-cards")
        self.assertNotIn(str(card.public_id), " ".join(url for _, url in self.switcher(page)))

    def test_switching_works_from_the_other_child_too(self):
        page = self.portal.get(self.url("portal:attendance", self.ravi_grant))
        self.assertEqual([url for _, url in self.switcher(page)],
                         [reverse("portal:attendance", args=[g.public_id])
                          for g in (self.asha_grant, self.ravi_grant)])

    def test_under_review_child_never_appears_and_stays_inaccessible(self):
        review, review_grant = self.review_child("Zed Review")
        for name in ("portal:child", "portal:attendance", "portal:report-cards"):
            page = self.portal.get(self.url(name, self.asha_grant))
            self.assertEqual([n for n, _ in self.switcher(page)], ["Asha Rao", "Ravi Rao"])
            self.assertNotContains(page, str(review_grant.public_id))
            self.assertNotContains(page, "Zed Review")
            self.assertEqual(self.portal.get(self.url(name, review_grant)).status_code, 404)

    def test_no_switcher_for_a_single_visible_child(self):
        self.review_child("Zed Review")
        ga.revoke_student_access(grant=self.ravi_grant, actor=self.admin, reason="x")
        page = self.portal.get(self.url("portal:child", self.asha_grant))
        self.assertEqual(page.context["switcher_children"], [])
        self.assertNotContains(page, "data-erp-switcher")


class NavigationConsistencyTests(PortalFixture, TestCase):
    # (route, desktop label, mobile tab-bar label); the tab bar shortens "Report cards".
    PAGES = (("portal:child", "Overview", "Overview"),
             ("portal:attendance", "Attendance", "Attendance"),
             ("portal:report-cards", "Report cards", "Reports"))

    def current(self, page):
        return CURRENT.findall("".join(self.navs(page)))

    def test_nav_follows_the_selected_child_on_every_child_page(self):
        card = self.asha_card()
        cases = [(name, (), labels) for name, *labels in self.PAGES]
        cases.append(("portal:report-card", (card.public_id,), ["Report cards", "Reports"]))
        for mine, other in ((self.asha_grant, self.ravi_grant), (self.ravi_grant, self.asha_grant)):
            for name, extra, labels in cases:
                if name == "portal:report-card" and mine is self.ravi_grant:
                    continue  # the card belongs to Asha
                with self.subTest(page=name, child=mine.public_id):
                    page = self.portal.get(self.url(name, mine, *extra))
                    self.assertEqual(page.status_code, 200)
                    navs = self.navs(page)
                    self.assertEqual(len(navs), 2)  # desktop header + mobile tab bar
                    for nav in navs:
                        self.assertIn(str(mine.public_id), nav)
                        self.assertNotIn(str(other.public_id), nav)
                        self.assertNotIn(str(card.public_id), nav)
                    self.assertEqual(self.current(page), labels)  # desktop, mobile

    def test_home_and_notices_mark_their_own_tab_current(self):
        for name, label in (("portal:home", "Home"), ("portal:notices", "Notices")):
            with self.subTest(page=name):
                page = self.portal.get(reverse(name))
                self.assertEqual(self.current(page), [label, label])

    def test_nav_on_home_and_notices_never_targets_an_under_review_child(self):
        _, review_grant = self.review_child("Aaron Review")  # sorts before Asha
        for name in ("portal:home", "portal:notices"):
            page = self.portal.get(reverse(name))
            self.assertEqual(page.context["nav_grant"], self.asha_grant)
            for nav in self.navs(page):
                self.assertNotIn(str(review_grant.public_id), nav)

    def test_skip_link_and_heading_hierarchy(self):
        card = self.asha_card()
        for url in (reverse("portal:home"), self.url("portal:child", self.asha_grant),
                    self.url("portal:attendance", self.asha_grant),
                    self.url("portal:report-cards", self.asha_grant),
                    self.url("portal:report-card", self.asha_grant, card.public_id)):
            with self.subTest(url=url):
                html = self.portal.get(url).content.decode()
                self.assertIn('<a class="visually-hidden-focusable" href="#main">', html)
                self.assertIn('id="main"', html)
                self.assertEqual(html.count("<h1"), 1)
                levels = [int(n) for n in re.findall(r"<h([1-6])[ >]", html)]
                for before, after in zip(levels, levels[1:], strict=False):
                    self.assertLessEqual(after, before + 1)  # no skipped heading levels


class StateMatrixTests(PortalFixture, TestCase):
    def register(self, on_date, status):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date)
        register.save_draft_entry(enrollment=self.asha_e, status=status)
        register.save_draft_entry(enrollment=self.bina.enrollments.get(),
                                  status=AttendanceStatus.PRESENT)
        register.submit(actor=self.admin)

    def home(self):
        return self.portal.get(reverse("portal:home"))

    def test_zero_children_is_honest_and_usable(self):
        stranger = Guardian.objects.create(full_name="No Children")
        account, password = ga.create_guardian_account(
            guardian=stranger, username="nokids", method=METHOD, note="known", actor=self.admin)
        account.user.must_change_password = False
        account.user.save()
        client = self.client_class()
        self.assertTrue(client.login(username="nokids", password=password))
        page = client.get(reverse("portal:home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "No students yet")
        self.assertIsNone(page.context["nav_grant"])
        self.assertNotContains(page, "/guardian/children/")
        self.assertEqual(client.get(reverse("portal:notices")).status_code, 200)

    def test_one_visible_child_has_no_switcher(self):
        ga.revoke_student_access(grant=self.ravi_grant, actor=self.admin, reason="x")
        page = self.portal.get(self.url("portal:child", self.asha_grant))
        self.assertNotContains(page, "data-erp-switcher")
        self.assertEqual(len(self.home().context["summaries"]), 1)

    def test_multiple_visible_children_get_cards_and_a_switcher(self):
        home = self.home()
        self.assertEqual([s["name"] for s in home.context["summaries"]], ["Asha Rao", "Ravi Rao"])
        page = self.portal.get(self.url("portal:child", self.asha_grant))
        self.assertContains(page, "data-erp-switcher")

    def test_visible_child_plus_child_under_review(self):
        review, review_grant = self.review_child("Zed Review")
        home = self.home()
        self.assertEqual([s["name"] for s in home.context["summaries"]], ["Asha Rao", "Ravi Rao"])
        self.assertContains(home, "Access under review")
        self.assertContains(home, "Zed Review</strong> &mdash; access under review by the school.")
        self.assertNotContains(home, str(review_grant.public_id))
        self.assertEqual(self.portal.get(self.url("portal:child", review_grant)).status_code, 404)

    def test_only_under_review_children_show_review_notice_not_empty_state(self):
        for grant in (self.asha_grant, self.ravi_grant):
            ga.revoke_student_access(grant=grant, actor=self.admin, reason="x")
        self.review_child("Zed Review")
        home = self.home()
        self.assertContains(home, "access under review by the school")
        self.assertNotContains(home, "No students yet")
        self.assertEqual(home.context["summaries"], [])

    def test_no_current_placement_is_shown_honestly_after_a_retained_review(self):
        self.today = date(2027, 4, 5)  # after the academic year
        guardian_access.decide_date_review(
            grant=self.asha_grant, decision=GuardianAccessReview.Decision.RETAINED,
            actor=self.admin, note="Still in contact")
        home = self.home()
        summary = next(s for s in home.context["summaries"] if s["name"] == "Asha Rao")
        self.assertIsNone(summary["placement"])
        self.assertContains(home, "No current placement")
        overview = self.portal.get(self.url("portal:child", self.asha_grant))
        self.assertContains(overview, "No current placement")
        self.assertContains(overview, "None at present")
        self.assertNotContains(overview, "Grade 6-A")

    def test_no_recorded_attendance_shows_no_fake_percentage_anywhere(self):
        home = self.home()
        self.assertContains(home, "No attendance recorded yet")
        attendance = self.portal.get(self.url("portal:attendance", self.asha_grant))
        self.assertContains(attendance, "No attendance has been recorded yet")
        for page in (home, attendance,
                     self.portal.get(self.url("portal:child", self.asha_grant))):
            self.assertNotContains(page, "0%")

    def test_no_published_report_cards(self):
        self.assertContains(self.home(), "No report cards published yet")
        self.assertContains(self.portal.get(self.url("portal:report-cards", self.asha_grant)),
                            "No report cards have been published yet.")

    def test_partial_card_is_listed_and_flagged(self):
        self.make_assessment(name="UT3", on=date(2026, 9, 1))  # DRAFT
        card = self.asha_card(self.publish(include=[self.asha.pk]))
        listing = self.portal.get(self.url("portal:report-cards", self.asha_grant))
        self.assertEqual([p.pk for p in listing.context["publications"]], [card.pk])
        page = self.portal.get(self.url("portal:report-card", self.asha_grant, card.public_id))
        self.assertContains(page, "Some results for this Term are not yet published.")

    def test_stale_and_withdrawn_cards_vanish_from_every_page(self):
        stale = self.asha_card()
        result = StudentResult.objects.filter(academic_enrollment=self.asha_e).first()
        publication.mark_stale_for_result(result, actor=self.admin)
        for url in (reverse("portal:home"), self.url("portal:child", self.asha_grant),
                    self.url("portal:report-cards", self.asha_grant)):
            with self.subTest(url=url):
                self.assertNotContains(self.portal.get(url), str(stale.public_id))
        self.assertContains(self.portal.get(reverse("portal:home")),
                            "No report cards published yet")

    def test_populated_state_shows_real_attendance_and_the_latest_card(self):
        self.register(date(2026, 10, 5), AttendanceStatus.PRESENT)
        self.register(date(2026, 10, 6), AttendanceStatus.ABSENT)
        card = self.asha_card()
        home = self.home()
        summary = next(s for s in home.context["summaries"] if s["name"] == "Asha Rao")
        self.assertEqual((summary["attendance"]["present"], summary["attendance"]["absent"]),
                         (1, 1))
        self.assertEqual(summary["latest_report_card"].pk, card.pk)
        self.assertContains(home, "50.0%")
        self.assertContains(home, self.url("portal:report-card", self.asha_grant, card.public_id))
