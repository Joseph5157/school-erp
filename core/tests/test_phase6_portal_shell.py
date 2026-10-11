"""Phase 6 Gate 3: Guardian Portal shell, child switcher, multi-role navigation."""

import uuid
from datetime import date

from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import URLPattern, reverse

from core import guardian_accounts as ga
from core import portal_urls
from core.tests.test_phase6_access_boundary import BoundaryFixture


class PortalFixture(BoundaryFixture):
    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()

    def child_url(self, grant):
        return reverse("portal:child", args=[grant.public_id])


class LandingTests(PortalFixture, TestCase):
    def test_guardian_only_lands_in_portal(self):
        client = self.client_class()
        response = client.post(reverse("login"), {"username": "meena",
                                                  "password": self.password}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("portal:home"))

    def test_teacher_guardian_chooses_explicitly(self):
        self.user.groups.add(Group.objects.get(name="Teachers"))
        self.assertRedirects(self.portal.get(reverse("home")), reverse("choose-area"),
                             fetch_redirect_response=False)
        page = self.portal.get(reverse("choose-area"))
        self.assertEqual([key for key, _, _ in page.context["areas"]], ["teacher", "guardian"])
        self.assertContains(page, reverse("core:my-home"))
        self.assertContains(page, reverse("portal:home"))

    def test_admin_teacher_guardian_sees_all_three(self):
        self.user.groups.add(Group.objects.get(name="Teachers"), self.admins)
        page = self.portal.get(reverse("choose-area"))
        self.assertEqual([key for key, _, _ in page.context["areas"]],
                         ["admin", "teacher", "guardian"])

    def test_single_area_skips_the_choice(self):
        self.assertRedirects(self.portal.get(reverse("choose-area")), reverse("home"),
                             fetch_redirect_response=False)

    def test_role_aware_navigation_both_ways(self):
        self.user.groups.add(Group.objects.get(name="Teachers"))
        self.assertContains(self.portal.get(reverse("core:my-home")), reverse("portal:home"))
        self.assertContains(self.portal.get(reverse("portal:home")), reverse("core:my-home"))


class PortalHomeTests(PortalFixture, TestCase):
    def test_lists_only_granted_students(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertEqual([item["student"] for item in page.context["children"]], [self.asha])
        self.assertContains(page, self.child_url(self.asha_grant))
        self.assertNotContains(page, "Ravi Rao")   # related but not granted
        self.assertNotContains(page, "Bina Other")  # another family

    def test_pending_review_listed_without_link(self):
        self.today = date(2027, 4, 5)
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, "access under review by the school")
        self.assertNotContains(page, self.child_url(self.asha_grant))

    def test_no_database_ids_and_no_excluded_features(self):
        page = self.portal.get(reverse("portal:home")).content.decode().lower()
        self.assertNotIn(f"/students/{self.asha.pk}/", page)
        for word in ("fee", "announcement", "pdf", "download"):
            self.assertNotIn(word, page)

    def test_switcher_shows_every_visible_child(self):
        ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        page = self.portal.get(self.child_url(self.asha_grant))
        self.assertContains(page, "Ravi Rao")
        self.assertContains(page, "Asha Rao")

    def test_query_count_constant(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.portal.get(reverse("portal:home")).status_code, 200)
            return len(ctx.captured_queries)

        small = count()
        ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        for i in range(3):
            student, _ = self.make_student(f"Sibling {i}")
            ga.grant_student_access(student_guardian=self.relate(student, self.meena),
                                    actor=self.admin)
        self.assertEqual(count(), small)


class ChildPageTests(PortalFixture, TestCase):
    def test_own_child(self):
        self.assertContains(self.portal.get(self.child_url(self.asha_grant)), "Asha Rao")

    def test_everything_else_is_404(self):
        revoked = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        ga.revoke_student_access(grant=revoked, actor=self.admin, reason="x")
        for public_id in (self.bina_grant.public_id, revoked.public_id, uuid.uuid4()):
            with self.subTest(public_id=public_id):
                url = reverse("portal:child", args=[public_id])
                self.assertEqual(self.portal.get(url).status_code, 404)

    def test_pending_review_is_404(self):
        self.today = date(2027, 4, 5)
        self.assertEqual(self.portal.get(self.child_url(self.asha_grant)).status_code, 404)

    def test_portal_is_read_only(self):
        self.assertEqual(self.portal.post(self.child_url(self.asha_grant)).status_code, 405)


class PortalSweepTests(PortalFixture, TestCase):
    """Every portal URL refuses non-guardians and anonymous users."""

    def urls(self):
        for pattern in portal_urls.urlpatterns:
            assert isinstance(pattern, URLPattern)
            kwargs = {name: self.asha_grant.public_id for name in pattern.pattern.regex.groupindex}
            yield reverse(f"portal:{pattern.name}", kwargs=kwargs)

    def test_anonymous_goes_to_login(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client_class().get(url)
                self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_non_guardians_are_forbidden(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        for client in (self.client, teacher):  # administrator, teacher
            for url in self.urls():
                with self.subTest(url=url):
                    self.assertEqual(client.get(url).status_code, 403)

    def test_revoked_link_sees_nothing(self):
        ga.revoke_account_link(account=self.account, actor=self.admin, reason="x")
        client = self.client_class()
        client.login(username="meena", password=self.password)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)
