"""UI-D1-6A: Sign-in lockouts and the Student guardian-access review step (presentation only).

Both originating Student flows (`student_enroll` -> PLACEMENT_ENDED and `student_status_change` ->
STUDENT_INACTIVE) are exercised end to end: the review step writes nothing, an incomplete or invalid
decision saves nothing, and a complete submission keeps the existing atomic change and audit.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from accounts.models import SecurityEvent
from core.breadcrumbs import breadcrumb_context
from core.models import (
    AcademicEnrollment,
    GuardianAccessReview,
    GuardianStudentAccess,
    Student,
    StudentStatusChange,
)
from core.tests.test_phase6_access_boundary import RETAIN, REVOKE, TODAY, BoundaryFixture
from core.tests.test_phase6_security import ThrottlingFixture

User = get_user_model()
LOCKOUTS = reverse("core:login-lockouts")
ACTIVE_LINK = r'<a class="nav-link active" href="([^"]+)"'


def html(response):
    return response.content.decode()


class ViewerMixin:
    def client_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._viewers}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client


class LockoutPageTests(ViewerMixin, ThrottlingFixture, TestCase):
    def test_empty_state_keeps_the_legacy_text_and_header(self):
        page = html(self.client.get(LOCKOUTS))
        self.assertIn("No usernames are locked.", page)
        self.assertRegex(page, r'<h1 class="erp-page-title">Sign-in lockouts</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn("5 from one network source, or 20 from any, within 15 minutes", page)
        self.assertIn("Lockouts expire on their own; clearing one is recorded.", page)
        self.assertNotIn('name="username"', page)

    def test_populated_table_is_labelled_with_the_username_in_the_clear_name(self):
        self.fail(5)
        page = html(self.client.get(LOCKOUTS))
        self.assertIn('role="region" aria-label="Locked usernames" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertEqual(page.count('scope="col"'), 2)
        self.assertIn('<th scope="row"', page)
        self.assertIn('Clear<span class="visually-hidden"> lockout for meena</span>', page)
        self.assertIn("Lets this username try to sign in again straight away. The clear is recorded.", page)
        self.assertNotIn("No usernames are locked.", page)

    def test_clear_form_is_the_unchanged_post(self):
        self.fail(5)
        page = html(self.client.get(LOCKOUTS))
        forms = re.findall(r'<form method="post"[^>]*>.*?</form>', page, re.S)
        (form,) = [f for f in forms if 'name="username"' in f]
        self.assertIn('name="csrfmiddlewaretoken"', form)
        self.assertIn('<input type="hidden" name="username" value="meena">', form)
        self.assertNotIn("action=", form)  # posts back to the same URL

    def test_clear_still_clears_redirects_and_records_the_event(self):
        self.fail(5)
        response = self.client.post(LOCKOUTS, {"username": "meena"})
        self.assertRedirects(response, LOCKOUTS)
        self.assertTrue(self.signed_in(self.attempt(self.password)))
        events = SecurityEvent.objects.filter(event_type=SecurityEvent.EventType.LOCKOUT_CLEARED)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().detail, {"username": "meena"})
        self.assertEqual(events.get().actor, self.admin)

    def test_clearing_a_username_that_is_not_locked_records_nothing(self):
        self.client.post(LOCKOUTS, {"username": "meena"})
        self.assertFalse(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.LOCKOUT_CLEARED).exists())

    def test_username_is_escaped(self):
        self.fail(5, username="<b>x</b>")
        page = html(self.client.get(LOCKOUTS))
        self.assertNotIn("<b>x</b>", page)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", page)

    def test_permissions_are_unchanged(self):
        anonymous, teacher = self.client_class(), self.client_class()
        teacher.login(username="rao", password="pass-12345")
        _, nobody = self.client_with("view_school")
        _, clearer = self.client_with("clear_login_lockout")
        self.assertEqual(anonymous.get(LOCKOUTS).status_code, 302)
        self.assertEqual(teacher.get(LOCKOUTS).status_code, 403)
        self.assertEqual(nobody.get(LOCKOUTS).status_code, 403)
        self.assertEqual(clearer.get(LOCKOUTS).status_code, 200)
        self.assertEqual(nobody.post(LOCKOUTS, {"username": "meena"}).status_code, 403)
        self.assertEqual(self.guardian_client().get(LOCKOUTS).status_code, 403)

    def test_restricted_clearer_without_overview_gets_no_trail_but_can_clear(self):
        self.fail(5)
        user, clearer = self.client_with("clear_login_lockout")
        page = html(clearer.get(LOCKOUTS))
        self.assertIn('Clear<span class="visually-hidden"> lockout for meena</span>', page)
        self.assertNotIn('aria-label="Breadcrumb"', page)
        self.assertEqual(clearer.post(LOCKOUTS, {"username": "meena"}).status_code, 302)
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.LOCKOUT_CLEARED, actor=user).exists())


class LockoutNavigationTests(ViewerMixin, ThrottlingFixture, TestCase):
    def test_rule_uses_the_sidebar_route_name(self):
        context = breadcrumb_context(resolve(LOCKOUTS))
        self.assertEqual(context["nav_section"], "login-lockouts")
        self.assertEqual([c["label"] for c in context["breadcrumbs"]], ["Overview", "Sign-in lockouts"])

    def test_trail_follows_view_school(self):
        user, _ = self.client_with("clear_login_lockout")
        self.assertEqual(breadcrumb_context(resolve(LOCKOUTS), user)["breadcrumbs"], [])
        user, _ = self.client_with("clear_login_lockout", "view_school")
        trail = breadcrumb_context(resolve(LOCKOUTS), user)["breadcrumbs"]
        self.assertEqual([c["label"] for c in trail], ["Overview", "Sign-in lockouts"])
        self.assertIsNone(trail[-1]["url"])

    def test_sidebar_highlights_the_lockouts_link(self):
        for populated in (False, True):
            if populated:
                self.fail(5)
            with self.subTest(populated=populated):
                page = html(self.client.get(LOCKOUTS))
                self.assertEqual(re.findall(ACTIVE_LINK, page), [LOCKOUTS])
                self.assertIn('aria-label="Breadcrumb"', page)
        # the page a POST redirects to is highlighted too
        page = html(self.client.post(LOCKOUTS, {"username": "meena"}, follow=True))
        self.assertEqual(re.findall(ACTIVE_LINK, page), [LOCKOUTS])


class ReviewFlowMixin(ViewerMixin):
    """Shared assertions for the review step rendered by both Student flows."""

    def snapshot(self):
        return {
            "enrollments": list(
                AcademicEnrollment.objects.order_by("pk").values_list("pk", "status", "section_id")),
            "students": list(Student.objects.order_by("pk").values_list("pk", "status")),
            "status_changes": StudentStatusChange.objects.count(),
            "reviews": GuardianAccessReview.objects.count(),
            "grants": list(GuardianStudentAccess.objects.order_by("pk").values_list("pk", "revoked_at")),
            "events": SecurityEvent.objects.count(),
        }

    def assert_review_page(self, response, *, trigger_label, action, hidden):
        page = html(response)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/student_access_review.html")
        self.assertRegex(page, r'<h1 class="erp-page-title">Guardian access review</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn("Asha Rao", page)
        self.assertIn(trigger_label, page)
        forms = re.findall(r'<form method="post" action="([^"]*)">(.*?)</form>', page, re.S)
        review_forms = [body for url, body in forms if url == action]
        self.assertEqual(len(review_forms), 1)
        body = review_forms[0]
        self.assertEqual(body.count('name="csrfmiddlewaretoken"'), 1)
        self.assertIn('<input type="hidden" name="access_review" value="1">', body)
        for name, value in hidden.items():
            self.assertIn(f'<input type="hidden" name="{name}" value="{value}">', body)
        # the replayed hidden fields are exactly the posted ones plus access_review
        names = re.findall(r'<input type="hidden" name="([^"]+)"', body)
        self.assertEqual(sorted(names), sorted(["csrfmiddlewaretoken", "access_review", *hidden]))
        pk = self.asha_grant.pk
        self.assertEqual(body.count(f'name="decision_{pk}"'), 2)
        for value in (RETAIN, REVOKE):
            self.assertRegex(
                body,
                rf'<input type="radio" id="decision_{pk}_{value}" name="decision_{pk}" value="{value}" required>')
        self.assertEqual(body.count("<fieldset"), 1)
        legend = re.search(r"<legend[^>]*>(.*?)</legend>", body, re.S).group(1)
        self.assertIn("Meena Rao", legend)
        self.assertIn('name="access_note" id="access_note" maxlength="200"', body)
        self.assertIn("Record decisions and continue", body)
        # the other family's grant never appears
        self.assertNotIn(f"decision_{self.bina_grant.pk}", body)
        return page


class EnrollReviewTests(ReviewFlowMixin, BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:student-enroll", args=[self.asha.pk])
        self.data = {"academic_year": self.year.pk, "class_grade": self.grade6.pk,
                     "section": self.six_b.pk, "start_date": TODAY.isoformat()}

    def test_review_step_renders_and_writes_nothing(self):
        before = self.snapshot()
        response = self.client.post(self.url, self.data)
        page = self.assert_review_page(
            response, trigger_label="Placement ended", action=self.url,
            hidden={k: str(v) for k, v in self.data.items()})
        self.assertIn('<dt class="col-sm-3">Review trigger</dt><dd class="col-sm-9">Placement ended</dd>', page)
        self.assertEqual(self.snapshot(), before)

    def test_incomplete_or_invalid_decision_saves_nothing(self):
        before = self.snapshot()
        for extra in ({}, {f"decision_{self.asha_grant.pk}": "MAYBE"}):
            with self.subTest(extra=extra):
                response = self.client.post(self.url, {**self.data, "access_review": "1", **extra})
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "core/enrollment_form.html")
                self.assertTrue(list(response.context["messages"]))
                self.assertEqual(self.snapshot(), before)

    def test_complete_submission_saves_atomically_and_audits(self):
        response = self.client.post(self.url, {**self.data, "access_review": "1",
                                               "access_note": "Moved section",
                                               f"decision_{self.asha_grant.pk}": REVOKE})
        self.assertRedirects(response, reverse("core:student-detail", args=[self.asha.pk]))
        self.assertEqual(self.asha.enrollments.count(), 2)
        self.asha_grant.refresh_from_db()
        self.assertFalse(self.asha_grant.is_active)
        review = GuardianAccessReview.objects.get()
        self.assertEqual((review.trigger, review.decision),
                         (GuardianAccessReview.Trigger.PLACEMENT_ENDED, REVOKE))
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.ACCESS_REVOKED).exists())

    def test_first_placement_has_no_review_step(self):
        self.asha.enrollments.all().delete()
        response = self.client.post(self.url, self.data)
        self.assertNotIn("core/student_access_review.html", [t.name for t in response.templates])

    def test_cancel_is_gated_by_view_student(self):
        _, adder = self.client_with("add_academicenrollment")
        page = html(adder.post(self.url, self.data))
        self.assertIn("Record decisions and continue", page)
        self.assertNotIn("Cancel", page)
        _, both = self.client_with("add_academicenrollment", "view_student")
        page = html(both.post(self.url, self.data))
        detail = reverse("core:student-detail", args=[self.asha.pk])
        self.assertIn(f'<a class="btn btn-link" href="{detail}">Cancel</a>', page)

    def test_permissions_unchanged(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.assertEqual(teacher.post(self.url, self.data).status_code, 403)
        self.assertEqual(self.client_class().post(self.url, self.data).status_code, 302)
        self.assertEqual(self.guardian_client().post(self.url, self.data).status_code, 403)

    def test_page_gets_no_trail_and_no_false_sidebar_highlight(self):
        page = html(self.client.post(self.url, self.data))
        self.assertNotIn('aria-label="Breadcrumb"', page)
        self.assertEqual(re.findall(ACTIVE_LINK, page), [])


class StatusChangeReviewTests(ReviewFlowMixin, BoundaryFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("core:student-status-change", args=[self.asha.pk])
        self.data = {"status": "INACTIVE", "reason": "Left the school"}

    def test_review_step_renders_and_writes_nothing(self):
        before = self.snapshot()
        response = self.client.post(self.url, self.data)
        page = self.assert_review_page(
            response, trigger_label="Student made inactive", action=self.url, hidden=self.data)
        self.assertIn(
            '<dt class="col-sm-3">Review trigger</dt><dd class="col-sm-9">Student made inactive</dd>', page)
        self.assertEqual(self.snapshot(), before)

    def test_incomplete_or_invalid_decision_saves_nothing(self):
        before = self.snapshot()
        for extra in ({}, {f"decision_{self.asha_grant.pk}": "MAYBE"}):
            with self.subTest(extra=extra):
                response = self.client.post(
                    self.url, {**self.data, "access_review": "1", **extra}, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(list(response.context["messages"]))
                self.assertEqual(self.snapshot(), before)

    def test_complete_submission_saves_atomically_and_audits(self):
        response = self.client.post(self.url, {**self.data, "access_review": "1",
                                               "access_note": "Left school",
                                               f"decision_{self.asha_grant.pk}": RETAIN})
        self.assertRedirects(response, reverse("core:student-detail", args=[self.asha.pk]))
        self.asha.refresh_from_db()
        self.asha_grant.refresh_from_db()
        self.assertEqual(self.asha.status, Student.Status.INACTIVE)
        self.assertTrue(self.asha_grant.is_active)
        review = GuardianAccessReview.objects.get()
        self.assertEqual((review.trigger, review.decision),
                         (GuardianAccessReview.Trigger.STUDENT_INACTIVE, RETAIN))
        self.assertIn("Left school", review.note)
        self.assertTrue(SecurityEvent.objects.filter(
            event_type=SecurityEvent.EventType.ACCESS_RETAINED).exists())

    def test_missing_reason_never_reaches_the_review_step(self):
        before = self.snapshot()
        response = self.client.post(self.url, {"status": "INACTIVE", "reason": " "})
        self.assertRedirects(response, reverse("core:student-deactivate-confirm", args=[self.asha.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(self.snapshot(), before)

    def test_cancel_is_gated_by_view_student(self):
        _, changer = self.client_with("change_student")
        page = html(changer.post(self.url, self.data))
        self.assertIn("Record decisions and continue", page)
        self.assertNotIn("Cancel", page)
        _, both = self.client_with("change_student", "view_student")
        self.assertIn(">Cancel</a>", html(both.post(self.url, self.data)))

    def test_permissions_unchanged(self):
        teacher = self.client_class()
        teacher.login(username="rao", password="pass-12345")
        self.assertEqual(teacher.post(self.url, self.data).status_code, 403)
        self.assertEqual(self.guardian_client().post(self.url, self.data).status_code, 403)
