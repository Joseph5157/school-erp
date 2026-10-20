"""Guardian UI Sprint 1 tests (findings G-01, G-02, G-04, G-05, G-07, G-10).

Also covers the pre-staging review follow-ups: the denial-neutral 403 page
(H1), the constant-query batched publication lookup (M1) and behaviour-level
assertions for the Sprint 1 UI (M3).
"""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import guardian_accounts as ga
from core import publication
from core.models import (
    AttendanceRegister,
    AttendanceStatus,
    Guardian,
    GuardianAccount,
    ResultStatus,
    StudentResult,
    TermPublication,
)
from core.portal import report_card_groups
from core.tests.test_phase6_access_boundary import BoundaryFixture
from core.tests.test_phase6_portal_shell import PortalFixture

GRANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PUB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
METHOD = GuardianAccount.VerificationMethod.EXISTING_RECORDS


class ReportCardGradeFallbackTests(TestCase):
    def render(self, grade_label, pass_fail_label="Pass"):
        entry = SimpleNamespace(
            subject_label="Science",
            assessment_label="Unit Test 1",
            assessment_date=date(2026, 7, 15),
            display_order=0,
            status="MARKED",
            score=29,
            maximum_marks=50,
            percentage=58,
            grade_label=grade_label,
            pass_fail_label=pass_fail_label,
        )
        pub = SimpleNamespace(
            term_label="Term 1",
            academic_year_label="2026-27",
            class_grade_label="Grade 6",
            section_label="A",
            public_id=PUB_ID,
            is_partial=False,
            remark_text="",
        )
        student = SimpleNamespace(full_name="Anusha Rao")
        grant = SimpleNamespace(public_id=GRANT_ID)
        return render_to_string(
            "portal/report_card.html",
            {
                "entries": [entry],
                "groups": report_card_groups([entry]),
                "pub": pub,
                "student": student,
                "grant": grant,
                "children": [],
                "user": SimpleNamespace(get_username=lambda: "g"),
            },
        )

    def test_blank_grade_shows_not_graded(self):
        html = self.render("")
        self.assertIn("Not graded", html)
        self.assertIn("Pass", html)

    def test_real_grade_is_shown_not_placeholder(self):
        html = self.render("A2")
        self.assertIn(">A2<", html)
        self.assertNotIn("Not graded", html)


class ForbiddenPageTests(BoundaryFixture, TestCase):
    # BoundaryFixture.setUp already logs self.client in as the administrator.
    NEUTRAL_HEADING = "have access to this page"
    MISLEADING = ("guardian access", "not linked to a student", "Guardian Portal")

    def assert_neutral_403(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'id="forbidden-title"', status_code=403)
        self.assertContains(response, self.NEUTRAL_HEADING, status_code=403)
        self.assertContains(response, reverse("home"), status_code=403)
        for wording in self.MISLEADING + (self.asha.full_name,):
            self.assertNotContains(response, wording, status_code=403)

    def test_admin_requesting_guardian_page_gets_neutral_403(self):
        self.assert_neutral_403(self.client.get(reverse("portal:home")))

    def test_guardian_requesting_admin_page_gets_neutral_403(self):
        guardian = self.guardian_client()
        self.assert_neutral_403(guardian.get(reverse("core:admin-overview")))

    def test_anonymous_still_redirects_not_403(self):
        anonymous = self.client_class()
        response = anonymous.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_anonymous_recovery_actions_render(self):
        html = render_to_string("403.html", {"user": AnonymousUser()})
        self.assertIn(reverse("login"), html)   # sign in
        self.assertIn(reverse("home"), html)    # own area (login-gated)


class PortalNavTests(PortalFixture, TestCase):
    def test_desktop_nav_present_on_home_with_notices_and_child_links(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, 'class="erp-portal-nav')
        self.assertContains(page, reverse("portal:notices"))
        self.assertContains(page, reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))
        self.assertContains(page, reverse("portal:report-cards", args=[self.asha_grant.public_id]))

    def test_tabbar_is_stable_on_notices_page(self):
        page = self.portal.get(reverse("portal:notices"))
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))

    def test_child_tabs_point_at_the_current_child_on_child_page(self):
        page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))

    def test_home_marks_only_home_active(self):
        page = self.portal.get(reverse("portal:home"))
        html = page.content.decode()
        # Desktop nav + mobile tab bar: both mark Home, and nothing else.
        self.assertEqual(html.count('aria-current="page"'), 2)
        self.assertIn(
            f'<a href="{reverse("portal:home")}" class="active" aria-current="page">Home</a>',
            html,
        )
        attendance = reverse("portal:attendance", args=[self.asha_grant.public_id])
        self.assertNotIn(f'<a href="{attendance}" class="active"', html)

    def test_child_page_marks_only_overview_active(self):
        page = self.portal.get(reverse("portal:child", args=[self.asha_grant.public_id]))
        html = page.content.decode()
        overview = reverse("portal:child", args=[self.asha_grant.public_id])
        self.assertIn(
            f'<a href="{overview}" class="active" aria-current="page">Overview</a>', html
        )
        self.assertNotIn(f'<a href="{reverse("portal:home")}" class="active"', html)

    def test_home_nav_defaults_to_first_visible_child(self):
        ravi_grant = ga.grant_student_access(student_guardian=self.ravi_link, actor=self.admin)
        page = self.portal.get(reverse("portal:home"))
        self.assertEqual(
            [item["student"].full_name for item in page.context["children"]],
            ["Asha Rao", "Ravi Rao"],
        )
        self.assertEqual(page.context["nav_grant"], self.asha_grant)
        self.assertContains(page, reverse("portal:attendance", args=[self.asha_grant.public_id]))
        self.assertNotContains(page, reverse("portal:attendance", args=[ravi_grant.public_id]))


class ZeroChildPortalTests(BoundaryFixture, TestCase):
    def test_guardian_with_no_grants_has_no_child_scoped_links(self):
        orphan = Guardian.objects.create(full_name="No Children")
        account, password = ga.create_guardian_account(
            guardian=orphan, username="orphan", method=METHOD, note="known", actor=self.admin
        )
        account.user.must_change_password = False
        account.user.save(update_fields=["must_change_password"])
        client = self.client_class()
        client.login(username="orphan", password=password)

        page = client.get(reverse("portal:home"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["children"], [])
        self.assertIsNone(page.context["nav_grant"])
        dummy = uuid.uuid4()
        for name in ("portal:child", "portal:attendance", "portal:report-cards"):
            self.assertNotContains(page, reverse(name, args=[dummy]))
        self.assertContains(page, "No students yet")


class PendingReviewExclusionTests(PortalFixture, TestCase):
    def test_pending_review_grants_are_excluded_from_dashboard_and_nav(self):
        self.today = date(2027, 4, 5)  # after the academic year -> review pending
        page = self.portal.get(reverse("portal:home"))
        self.assertEqual(page.context["summaries"], [])
        self.assertIsNone(page.context["nav_grant"])
        self.assertNotContains(page, reverse("portal:child", args=[self.asha_grant.public_id]))
        self.assertContains(page, "access under review by the school")


class LoginErrorA11yTests(TestCase):
    def test_empty_submit_associates_errors_with_fields(self):
        response = self.client.post(reverse("login"), {"username": "", "password": ""})
        html = response.content.decode()
        self.assertContains(response, 'aria-invalid="true"', count=2)
        # Each invalid field points at a description that exists in the page.
        self.assertContains(response, 'aria-describedby="id_username_error"')
        self.assertContains(response, 'aria-describedby="id_password_error"')
        self.assertIn('id="id_username_error"', html)
        self.assertIn('id="id_password_error"', html)

    def test_generic_failure_alert_is_announced(self):
        response = self.client.post(
            reverse("login"), {"username": "nobody", "password": "wrong"}
        )
        html = response.content.decode()
        self.assertContains(response, 'id="login-error" role="alert"')
        # The live region actually carries the error text, not just the attribute.
        self.assertRegex(html, r'id="login-error" role="alert">[^<]+</div>')


class HomeDashboardTests(PortalFixture, TestCase):
    def summaries(self):
        page = self.portal.get(reverse("portal:home"))
        return page.context["summaries"]

    def test_one_summary_per_visible_child_with_placement(self):
        rows = self.summaries()
        self.assertEqual([r["name"] for r in rows], ["Asha Rao"])
        self.assertEqual(rows[0]["placement"]["class_grade"], self.asha_e.class_grade.name)

    def test_attendance_is_none_when_nothing_recorded(self):
        self.assertIsNone(self.summaries()[0]["attendance"])

    def test_no_published_report_card_is_none(self):
        self.assertIsNone(self.summaries()[0]["latest_report_card"])

    def test_empty_dashboard_states_are_honest(self):
        page = self.portal.get(reverse("portal:home"))
        self.assertContains(page, "No attendance recorded yet")
        self.assertContains(page, "No report cards published yet")

    def test_related_but_ungranted_child_is_not_summarised(self):
        self.assertEqual([r["name"] for r in self.summaries()], ["Asha Rao"])


class AttendanceDashboardFixture(BoundaryFixture):
    """Meena's child has two submitted attendance days in Term 1."""

    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()
        bina_e = self.bina.enrollments.get()
        roster = ((self.asha, self.asha_e), (self.bina, bina_e))
        for on, asha_status in (
            (date(2026, 7, 6), AttendanceStatus.PRESENT),
            (date(2026, 7, 7), AttendanceStatus.ABSENT),
        ):
            register = AttendanceRegister.objects.create(
                academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on
            )
            for student, enrollment in roster:
                register.capture(
                    enrollment=enrollment,
                    status=(
                        asha_status if student == self.asha else AttendanceStatus.PRESENT
                    ),
                )
            register.submit(actor=self.admin)


class AttendanceCardTests(AttendanceDashboardFixture, TestCase):
    def test_card_shows_numerator_denominator_and_percentage(self):
        page = self.portal.get(reverse("portal:home"))
        row = page.context["summaries"][0]
        self.assertEqual(
            row["attendance"],
            {"present": 1, "absent": 1, "total": 2, "percentage": 50.0},
        )
        self.assertContains(page, "50.0%")
        self.assertContains(page, "1 of 2 recorded days present")


class DashboardPublicationFixture(BoundaryFixture):
    """Meena's three children, each with a published report card for Term 1."""

    def setUp(self):
        super().setUp()
        self.portal = self.guardian_client()
        self.children = [(self.asha, self.asha_e, self.asha_grant)]
        self.extra_grants = []
        for index in range(2):
            student, enrollment = self.make_student(f"Sibling {index}")
            grant = ga.grant_student_access(
                student_guardian=self.relate(student, self.meena), actor=self.admin
            )
            self.children.append((student, enrollment, grant))
            self.extra_grants.append(grant)
        assessment = self.make_assessment(name="UT1", on=date(2026, 7, 15))
        for _student, enrollment, _grant in self.children:
            StudentResult.objects.create(
                assessment=assessment, academic_enrollment=enrollment,
                status=ResultStatus.MARKED, score=Decimal("15"), entered_by=self.rao,
            )
        self.force_finalize(assessment)
        plan = publication.plan_publication(self.term1, self.six_a)
        self.published = publication.confirm_publication(
            term=self.term1, section=self.six_a, include=(), token=plan["token"],
            actor=self.admin,
        )

    def count_home_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.portal.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)


class DashboardPublicationQueryTests(DashboardPublicationFixture, TestCase):
    def test_query_count_constant_with_published_cards(self):
        self.count_home_queries()  # warm-up
        with_three = self.count_home_queries()
        for grant in self.extra_grants:
            ga.revoke_student_access(grant=grant, actor=self.admin, reason="test")
        with_one = self.count_home_queries()
        self.assertEqual(
            with_three, with_one,
            f"dashboard query count grew with published cards: {with_one} -> {with_three}",
        )


class DashboardReportCardTests(DashboardPublicationFixture, TestCase):
    def test_latest_report_card_link_and_label(self):
        page = self.portal.get(reverse("portal:home"))
        rows = {r["name"]: r for r in page.context["summaries"]}
        self.assertEqual(set(rows), {student.full_name for student, _, _ in self.children})
        for student, _enrollment, grant in self.children:
            card = rows[student.full_name]["latest_report_card"]
            self.assertIsNotNone(card)
            self.assertEqual(card.student_id, student.pk)
            self.assertEqual(card.term_label, "Term 1")
            self.assertContains(
                page, reverse("portal:report-card", args=[grant.public_id, card.public_id])
            )
        self.assertContains(page, "Latest report card")
        self.assertContains(page, "Term 1")

    def test_stale_publication_is_hidden_from_dashboard(self):
        card = next(p for p in self.published if p.student_id == self.asha.pk)
        result = StudentResult.objects.get(
            assessment__term=self.term1, academic_enrollment=self.asha_e
        )
        result.correct(
            new_status=ResultStatus.MARKED, new_score="16", actor=self.admin, reason="Recount"
        )
        card.refresh_from_db()
        self.assertEqual(card.status, TermPublication.Status.STALE)
        rows = {
            r["name"]: r for r in self.portal.get(reverse("portal:home")).context["summaries"]
        }
        self.assertIsNone(rows["Asha Rao"]["latest_report_card"])
        self.assertIsNotNone(rows["Sibling 0"]["latest_report_card"])


class GuardianVisibleManyTests(DashboardPublicationFixture, TestCase):
    def test_batch_matches_single_and_handles_empty(self):
        self.assertEqual(publication.guardian_visible_many([]), {})
        cards = list(TermPublication.objects.filter(student__in=[
            student for student, _, _ in self.children
        ]))
        batch = publication.guardian_visible_many(cards)
        self.assertEqual(len(batch), len(cards))
        for card in cards:
            self.assertEqual(batch[card.pk], publication.guardian_visible(card))

    def test_batch_marks_a_stale_publication_not_visible(self):
        stale = next(p for p in self.published if p.student_id == self.asha.pk)
        others = [p for p in self.published if p.pk != stale.pk]
        result = StudentResult.objects.get(
            assessment__term=self.term1, academic_enrollment=self.asha_e
        )
        result.correct(
            new_status=ResultStatus.MARKED, new_score="16", actor=self.admin, reason="Recount"
        )
        stale.refresh_from_db()
        batch = publication.guardian_visible_many([stale, *others])
        self.assertFalse(batch[stale.pk])
        self.assertTrue(all(batch[p.pk] for p in others))
