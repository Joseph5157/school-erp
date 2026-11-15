"""Guardian Portal server work (modern-web audit 08: P8-03..P8-06).

- Each portal page has a ceiling on database queries (before this change: 25-33 per page).
- The work stays the same however many notices the school has posted.
- Home loads only its three notices; a notice page loads one; the list goes a page at a time.
- Portal pages don't look up the school or its logo (the portal header shows neither).
- Role lookups are remembered for the signed-in person's own request only.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts import request_cache
from core.portal_views import NOTICES_PER_PAGE
from core.tests.test_phase7_announcements import SECTION, AnnouncementFixture

# Measured after the change, so any extra repeated lookup fails here first.
CEILINGS = {"home": 17, "child": 16, "attendance": 17, "report-cards": 13, "notices": 15, "notice": 14}


class PortalQueryBudgetTests(AnnouncementFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()
        self.first_notice = self.notice(title="Sports Day")

    def pages(self):
        grant = self.asha_grant.public_id
        return {
            "home": reverse("portal:home"),
            "child": reverse("portal:child", args=[grant]),
            "attendance": reverse("portal:attendance", args=[grant]),
            "report-cards": reverse("portal:report-cards", args=[grant]),
            "notices": reverse("portal:notices"),
            "notice": reverse("portal:notice", args=[self.first_notice.public_id]),
        }

    def captured(self, url):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.portal.get(url).status_code, 200)
        return [query["sql"] for query in ctx.captured_queries]

    def test_each_page_stays_under_its_query_ceiling(self):
        for name, url in self.pages().items():
            with self.subTest(page=name):
                self.assertLessEqual(len(self.captured(url)), CEILINGS[name])

    def test_more_notices_do_not_mean_more_queries(self):
        before = {name: len(self.captured(self.pages()[name])) for name in ("home", "notices")}
        for number in range(30):
            self.notice(title=f"Notice {number}")
        for name, count in before.items():
            with self.subTest(page=name):
                self.assertEqual(len(self.captured(self.pages()[name])), count)

    def test_portal_pages_skip_the_school_and_logo_lookups(self):
        for name, url in self.pages().items():
            with self.subTest(page=name):
                sql = " ".join(self.captured(url))
                self.assertNotIn('"core_school"', sql)
                self.assertNotIn('"core_schoollogo"', sql)

    def test_an_office_login_refused_at_a_portal_address_keeps_the_school_header(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("portal:home"))
        self.assertEqual(page.status_code, 403)
        self.assertEqual(page.context["current_area"], "admin")
        self.assertEqual(page.context["school_name"], self.school.name)

    def test_the_guardian_account_is_looked_up_once(self):
        sql = self.captured(self.pages()["home"])
        self.assertEqual(sum('FROM "core_guardianaccount"' in query for query in sql), 1)


class PortalNoticeTests(AnnouncementFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def test_home_shows_the_newest_three_and_limits_in_the_database(self):
        for number in range(5):
            self.notice(title=f"Notice {number}")
        with CaptureQueriesContext(connection) as ctx:
            page = self.portal.get(reverse("portal:home"))
        self.assertEqual([n.title for n in page.context["notices"]], ["Notice 4", "Notice 3", "Notice 2"])
        notice_sql = [q["sql"] for q in ctx.captured_queries if 'FROM "core_announcement"' in q["sql"]]
        self.assertEqual(len(notice_sql), 1)
        self.assertIn("LIMIT 3", notice_sql[0])

    def test_notice_list_goes_a_page_at_a_time(self):
        for number in range(NOTICES_PER_PAGE + 2):
            self.notice(title=f"Notice {number:02d}")
        first = self.portal.get(reverse("portal:notices"))
        self.assertEqual(len(first.context["notices"]), NOTICES_PER_PAGE)
        self.assertContains(first, "Page 1 of 2")
        self.assertContains(first, '<a href="?page=2" rel="next">Older</a>')
        second = self.portal.get(reverse("portal:notices"), {"page": 2})
        self.assertEqual([n.title for n in second.context["notices"]], ["Notice 01", "Notice 00"])
        self.assertContains(second, '<a href="?page=1" rel="prev">Newer</a>')
        self.assertEqual(self.portal.get(reverse("portal:notices"), {"page": "x"}).status_code, 200)

    def test_one_page_of_notices_has_no_pager(self):
        self.notice()
        self.assertNotContains(self.portal.get(reverse("portal:notices")), "erp-pagination")

    def test_a_notice_for_another_section_is_not_found(self):
        mine = self.notice(SECTION, section=self.six_a, title="6A")
        other = self.notice(SECTION, section=self.six_b, title="6B")
        self.assertEqual(self.portal.get(reverse("portal:notice", args=[mine.public_id])).status_code, 200)
        self.assertEqual(self.portal.get(reverse("portal:notice", args=[other.public_id])).status_code, 404)


class RequestRoleCacheTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cache-check", password="pass-12345")

    def test_a_user_object_outside_a_request_always_asks_again(self):
        calls = []
        for _ in range(2):
            request_cache.remember(self.user, "teacher", lambda: calls.append(1))
        self.assertEqual(len(calls), 2)

    def test_the_signed_in_user_asks_once_per_request(self):
        request_cache.enable(self.user)
        calls = []
        for _ in range(2):
            request_cache.remember(self.user, "teacher", lambda: calls.append(1) or True)
        self.assertEqual(len(calls), 1)

    def test_middleware_turns_the_cache_on_for_request_user(self):
        from accounts.middleware import AccountSecurityMiddleware

        seen = {}
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = self.client.session

        def view(req):
            seen["enabled"] = "_erp_request_cache" in req.user.__dict__
            from django.http import HttpResponse
            return HttpResponse()

        AccountSecurityMiddleware(view)(request)
        self.assertTrue(seen["enabled"])
