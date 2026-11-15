"""Guardian portal on phones: one title style, and navigation that leans on the tab bar.

- Every portal page uses the same title (`erp-child-title` inside `erp-child-head`).
- Tab pages (Home, Notices, Overview, Attendance, Report cards) have no back link, and
  the child's name is plain text (the Overview tab and the switcher already go there).
- Pages one level below a tab (a notice, a report card) have one back link at the top.
- Change password and Install keep the Guardian Portal header and tab bar for a
  guardian-only user, so they never feel like leaving the portal.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.portal import default_nav_grant
from core.tests.test_phase6_portal_shell import PortalFixture
from core.tests.test_phase7_announcements import AnnouncementFixture
from core.tests.test_ui_guardian_u4_3b import CardFixture

TITLE = 'class="erp-child-title"'


def _back_links(html):
    return html.count('class="erp-back"')


def _head(html):
    """The page header block (title, meta line), up to its closing tag."""
    start = html.index('class="erp-child-head')
    return html[start: html.index("</header>", start)]


class TabPageTests(PortalFixture, TestCase):
    def tab_urls(self):
        g = self.asha_grant.public_id
        return {
            "home": reverse("portal:home"),
            "notices": reverse("portal:notices"),
            "overview": reverse("portal:child", args=[g]),
            "attendance": reverse("portal:attendance", args=[g]),
            "report-cards": reverse("portal:report-cards", args=[g]),
        }

    def test_home_has_no_visible_title_but_keeps_a_page_heading(self):
        html = self.portal.get(reverse("portal:home")).content.decode()
        self.assertIn('<h1 class="visually-hidden">Home</h1>', html)
        self.assertNotIn(TITLE, html)
        self.assertNotIn("Your students", html)
        self.assertNotIn("the latest for your children", html)

    def test_every_tab_page_uses_the_shared_title_style(self):
        for name, url in self.tab_urls().items():
            if name == "home":
                continue  # Home has no visible title (see the test above)
            with self.subTest(page=name):
                html = self.portal.get(url).content.decode()
                self.assertEqual(html.count(TITLE), 1)
                self.assertIn('class="erp-child-head"', html)
                self.assertNotIn('<h1 class="h3', html)

    def test_tab_pages_have_no_back_link(self):
        for name, url in self.tab_urls().items():
            with self.subTest(page=name):
                self.assertEqual(_back_links(self.portal.get(url).content.decode()), 0)

    def test_child_name_under_the_title_is_plain_text(self):
        overview = reverse("portal:child", args=[self.asha_grant.public_id])
        for name in ("attendance", "report-cards"):
            with self.subTest(page=name):
                head = _head(self.portal.get(self.tab_urls()[name]).content.decode())
                self.assertIn(self.asha.full_name, head)
                self.assertNotIn(f'href="{overview}"', head)


class NoticeDetailTests(AnnouncementFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def test_notice_has_one_back_link_to_notices_above_the_title(self):
        notice = self.notice(title="Sports Day")
        html = self.portal.get(reverse("portal:notice", args=[notice.public_id])).content.decode()
        back = f'<a class="erp-back" href="{reverse("portal:notices")}">&larr; Notices</a>'
        self.assertIn(back, html)
        self.assertEqual(_back_links(html), 1)
        self.assertLess(html.index(back), html.index(TITLE))
        self.assertNotIn("All notices", html)


class ReportCardDetailTests(CardFixture, TestCase):
    def test_one_back_link_on_top_and_child_name_plain(self):
        html = self.portal.get(self.card_url(self.asha_card())).content.decode()
        back = f'<a class="erp-back" href="{self.list_url()}">&larr; Report cards</a>'
        self.assertIn(back, html)
        self.assertEqual(_back_links(html), 1)
        self.assertLess(html.index(back), html.index(TITLE))
        head = _head(html)
        self.assertIn(self.asha.full_name, head)
        overview = reverse("portal:child", args=[self.asha_grant.public_id])
        self.assertNotIn(f'href="{overview}"', head)


class PhoneTabBarTests(PortalFixture, TestCase):
    """The phone tab bar matches the Teacher bar: an icon above a one-line label."""

    def bar(self, html):
        start = html.index('<nav class="erp-tabbar')
        return html[start: html.index("</nav>", start)]

    def test_every_tab_has_an_icon_above_its_label(self):
        bar = self.bar(self.portal.get(reverse("portal:home")).content.decode())
        self.assertIn("erp-tabbar--icons", bar)
        items = re.findall(r"<li>(.*?)</li>", bar, re.DOTALL)
        labels = []
        for item in items:
            self.assertIn('class="erp-tab-icon"', item)
            self.assertLess(item.index("<svg"), item.index('class="erp-tab-label"'))
            labels.append(re.search(r'<span class="erp-tab-label">([^<]+)</span>', item).group(1))
        self.assertEqual(labels, ["Home", "Notices", "Overview", "Attendance", "Reports"])

    def test_desktop_header_nav_stays_text_only(self):
        html = self.portal.get(reverse("portal:home")).content.decode()
        start = html.index('class="erp-portal-nav')
        self.assertNotIn("<svg", html[start: html.index("</nav>", start)])

    def test_every_portal_icon_exists_in_the_tab_partial(self):
        partial = (Path(__file__).resolve().parents[2] / "templates" / "partials"
                   / "_tab_icon.html").read_text()
        for name in ("home", "notices", "overview", "attendance", "results"):
            self.assertIn(f'name == "{name}"', partial)


class AccountPagesKeepPortalShellTests(PortalFixture, TestCase):
    def test_password_and_install_show_portal_header_and_tabs(self):
        attendance = reverse("portal:attendance", args=[self.asha_grant.public_id])
        for url in (reverse("password_change"), reverse("pwa-install")):
            with self.subTest(url=url):
                page = self.portal.get(url)
                self.assertContains(page, "Guardian Portal</a>")
                self.assertContains(page, 'class="erp-tabbar erp-tabbar--icons d-lg-none"')
                self.assertContains(page, attendance)
                self.assertContains(page, "has-tabbar")
                # No tab claims to be the current page.
                self.assertNotContains(page, 'aria-current="page"')

    def test_install_title_matches_portal_titles_for_guardian(self):
        self.assertContains(self.portal.get(reverse("pwa-install")), TITLE)

    def test_forced_password_change_has_no_tabs_to_leave_by(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        page = self.portal.get(reverse("password_change"))
        self.assertNotContains(page, 'class="erp-tabbar')
        self.assertNotContains(page, "Guardian Portal</a>")

    def test_staff_keep_the_school_shell_on_account_pages(self):
        for url in (reverse("password_change"), reverse("pwa-install")):
            with self.subTest(url=url):
                page = self.client.get(url)  # BoundaryFixture signs in the administrator
                self.assertNotContains(page, "Guardian Portal")
                self.assertNotContains(page, 'class="erp-tabbar erp-tabbar--icons d-lg-none"')
                self.assertNotContains(page, TITLE)


class DefaultNavGrantTests(SimpleTestCase):
    """Portal pages and guardian account pages pick the default tab child the same way."""

    def test_first_visible_child_is_chosen(self):
        children = [{"grant": "under-review", "visible": False},
                    {"grant": "asha", "visible": True},
                    {"grant": "ravi", "visible": True}]
        self.assertEqual(default_nav_grant(children), "asha")

    def test_no_visible_child_gives_none(self):
        self.assertIsNone(default_nav_grant([{"grant": "x", "visible": False}]))
        self.assertIsNone(default_nav_grant([]))
