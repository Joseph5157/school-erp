"""UI-D1-5D: Term publication preview and confirmation, stale list, publication detail with its version
history, withdrawal, and permission-aware breadcrumbs.

Presentation only. These tests pin the preview state matrix (publish, republish, incomplete,
skipped, nothing selected), that the preview, token, hidden fields, row order and confirm button
are exactly what plan_publication() produces, that GET never writes, that a changed preview token
publishes nothing, the distinct Published / Stale / Superseded / Withdrawn presentation, permission
gating of every control, and that guardians never see stale or withdrawn versions as current.
Publication rules themselves are covered by test_phase6_* and are not retested here.
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core import publication
from core.breadcrumbs import breadcrumb_context
from core.models import ResultStatus, Section, TermPublication
from core.tests.test_phase6_publication import PublicationFixture

User = get_user_model()
Status = TermPublication.Status


def html(response):
    return response.content.decode()


class UiFixture(PublicationFixture):
    def setUp(self):
        super().setUp()
        self.preview_url = reverse("core:term-publication", args=[self.term1.pk])
        self.stale_url = reverse("core:publications-stale")

    def preview(self, include=(), client=None, section=None):
        params = {"section": (section or self.six_a).pk}
        if include:
            params["include"] = list(include)
        return (client or self.client).get(self.preview_url, params)

    def client_with(self, *codenames):
        self._users = getattr(self, "_users", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._users}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def teacher_client(self):
        client = self.client_class()
        client.login(username="rao", password="pass-12345")
        return client

    def correct(self, score="16"):
        self.result.correct(new_status=ResultStatus.MARKED, new_score=score, actor=self.admin, reason="Recount")

    def pub_for(self, student, version=None):
        qs = TermPublication.objects.filter(student=student, term=self.term1).order_by("-version")
        return qs.get(version=version) if version else qs.first()

    def names(self, page):
        return re.findall(r'<h3 class="h6 mb-0">([^<]+)</h3>', page)

    def token_in(self, page):
        return re.search(r'name="token" value="([0-9a-f]{64})"', page).group(1)

    def confirm_form(self, page):
        return re.search(r'<form method="post"[^>]*aria-label="Confirm publication">.*?</form>', page, re.S).group(0)


class PreviewTests(UiFixture, TestCase):
    def test_no_section_shows_the_picker_only(self):
        page = html(self.client.get(self.preview_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Publish to guardians</h1>', page)
        self.assertIn("2026-27 Term 1", page)
        self.assertIn('<label for="id_section">Section</label>', page)
        self.assertIn('name="section" id="id_section"', page)
        self.assertNotIn("Preview for", page)
        self.assertNotIn("Confirm publication", page)
        self.assertIn("nothing is written until you confirm", page)
        self.assertIn(self.stale_url, page)

    def test_publish_state_matches_plan_publication_exactly(self):
        plan = self.plan()
        page = html(self.preview())
        self.assertEqual(page.count("Will publish</span>"), 2)
        self.assertNotIn("Will republish</span>", page)
        self.assertEqual(self.names(page), [row["student"].full_name for row in plan["rows"]])  # plan order
        self.assertIn(
            f"<strong>{len(plan['selected'])}</strong> of {len(plan['rows'])} Student(s) selected for release.", page)
        for row in plan["rows"]:
            for entry in row["content"]["entries"]:
                self.assertIn(f"{entry['assessment_label']}: {entry['score']}/{entry['maximum_marks']}", page)
        self.assertIn("Remark: Steady progress.", page)
        self.assertEqual(page.count("Will be released"), 2)

    def test_confirm_form_keeps_token_fields_csrf_and_label(self):
        plan = self.plan()
        page = html(self.preview())
        form = self.confirm_form(page)
        self.assertIn("csrfmiddlewaretoken", form)
        self.assertEqual(self.token_in(page), plan["token"])
        self.assertIn(f'<input type="hidden" name="section" value="{self.six_a.pk}">', form)
        self.assertIn("Confirm and publish 2 report card(s)</button>", form)
        self.assertNotIn("disabled", form)
        self.assertIn("Nothing has been written yet.", form)
        self.assertIn("guardians see the report cards at once", form)

    def test_get_never_writes(self):
        self.preview()
        self.preview(include=[self.asha.pk])
        self.assertEqual(TermPublication.objects.count(), 0)

    def test_incomplete_state_flags_excludes_and_offers_the_include_checkbox(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        page = html(self.preview())
        self.assertIn("Incomplete</span>", page)
        self.assertIn("Not yet finalized: Mathematics UT2", page)
        self.assertRegex(page, rf'<input type="checkbox" name="include" value="{self.asha.pk}">')
        self.assertIn("Publish the finalized results anyway (marked partial)", page)
        self.assertIn("<strong>0</strong> of 2 Student(s) selected for release.", page)
        form = self.confirm_form(page)
        self.assertRegex(form, r"<button[^>]*disabled[^>]*>Confirm and publish 0 report card\(s\)</button>")
        self.assertIn("No report card is selected, so there is nothing to confirm.", form)
        self.assertIn("UT1: 15.00/20.00", page)  # an Incomplete Student's finalized entries stay visible

    def test_including_an_incomplete_student_selects_it_and_keeps_the_hidden_include(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        plan = self.plan(include=[self.asha.pk])
        page = html(self.preview(include=[self.asha.pk]))
        self.assertRegex(page, rf'<input type="checkbox" name="include" value="{self.asha.pk}" checked>')
        self.assertIn("<strong>1</strong> of 2 Student(s) selected for release.", page)
        form = self.confirm_form(page)
        self.assertIn(f'<input type="hidden" name="include" value="{self.asha.pk}">', form)
        self.assertIn("Confirm and publish 1 report card(s)</button>", form)
        self.assertEqual(self.token_in(page), plan["token"])

    def test_already_published_is_skipped_with_its_version_and_hides_the_release_block(self):
        self.publish()
        page = html(self.preview())
        self.assertEqual(page.count("Skipped</span>"), 2)
        self.assertRegex(page, r"erp-status--neutral[^>]*><span[^>]*>Status: </span>Skipped")
        self.assertIn("Already published (version 1)", page)
        self.assertNotIn("Will be released", page)
        self.assertIn("<strong>0</strong> of 2 Student(s) selected for release.", page)
        self.assertRegex(self.confirm_form(page), r"<button[^>]*disabled")

    def test_republish_after_a_correction_names_the_version_it_replaces(self):
        self.publish()
        self.correct()
        page = html(self.preview())
        self.assertIn("Will republish</span>", page)
        self.assertIn("(replaces version 1, Stale — needs review)", page)
        self.assertIn("UT1: 16.00/20.00", page)  # the corrected value is what would be released
        self.assertEqual(self.token_in(page), self.plan()["token"])

    def test_nothing_to_publish_is_skipped(self):
        self.make_student("Nia Newcomer")
        page = html(self.preview())
        self.assertIn("Nothing to publish", page)
        self.assertEqual(page.count("Skipped</span>"), 1)
        self.assertIn("<strong>2</strong> of 3 Student(s) selected for release.", page)

    def test_section_with_no_students(self):
        empty = Section.objects.create(class_grade=self.grade6, name="C")
        page = html(self.preview(section=empty))
        self.assertIn("No Students are placed in this Section for this Term.", page)
        self.assertIn("<strong>0</strong> of 0 Student(s) selected for release.", page)

    def test_update_preview_form_is_a_get_with_the_hidden_section(self):
        page = html(self.preview())
        update = re.search(
            r'<form method="get" aria-label="Preview of what will be released">.*?</form>', page, re.S).group(0)
        self.assertIn(f'<input type="hidden" name="section" value="{self.six_a.pk}">', update)
        self.assertIn("Update preview</button>", update)
        self.assertNotIn("csrfmiddlewaretoken", update)

    def test_context_is_unchanged(self):
        response = self.preview()
        for key in ("term", "sections", "section", "plan", "include"):
            self.assertIn(key, response.context)
        self.assertEqual(response.context["plan"]["token"], self.plan()["token"])


class ConfirmTests(UiFixture, TestCase):
    def test_post_publishes_exactly_the_previewed_selection_and_redirects(self):
        token = self.token_in(html(self.preview()))
        response = self.client.post(self.preview_url, {"section": self.six_a.pk, "token": token})
        self.assertRedirects(response, f"{self.preview_url}?section={self.six_a.pk}")
        self.assertEqual(TermPublication.objects.count(), 2)
        follow = html(self.client.get(f"{self.preview_url}?section={self.six_a.pk}"))
        self.assertEqual(follow.count("Skipped</span>"), 2)
        self.assertEqual(len(self.cards()), 1)  # the guardian sees the current published card

    def test_changed_token_publishes_nothing_and_shows_the_existing_message(self):
        token = self.token_in(html(self.preview()))
        self.correct()  # results change between preview and confirm
        response = self.client.post(self.preview_url, {"section": self.six_a.pk, "token": token}, follow=True)
        self.assertEqual(TermPublication.objects.count(), 0)
        self.assertContains(response, "Results changed since the preview, or this preview was already confirmed.")

    def test_confirming_twice_publishes_nothing_new(self):
        token = self.token_in(html(self.preview()))
        self.client.post(self.preview_url, {"section": self.six_a.pk, "token": token})
        again = self.client.post(self.preview_url, {"section": self.six_a.pk, "token": token}, follow=True)
        self.assertEqual(TermPublication.objects.count(), 2)
        self.assertContains(again, "already confirmed")

    def test_missing_token_publishes_nothing(self):
        self.client.post(self.preview_url, {"section": self.six_a.pk})
        self.assertEqual(TermPublication.objects.count(), 0)

    def test_include_ids_are_carried_through_the_post(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        token = self.token_in(html(self.preview(include=[self.asha.pk])))
        self.client.post(self.preview_url, {"section": self.six_a.pk, "token": token, "include": [self.asha.pk]})
        created = TermPublication.objects.get()
        self.assertEqual(created.student, self.asha)
        self.assertTrue(created.is_partial)


class PermissionTests(UiFixture, TestCase):
    def test_viewer_without_publish_permission_sees_the_preview_but_no_controls(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        _, viewer = self.client_with("view_termpublication")
        page = html(self.preview(client=viewer))
        self.assertIn("Incomplete</span>", page)
        self.assertNotIn('name="include"', page)
        self.assertNotIn("Confirm publication", page)
        self.assertNotIn('name="token"', page)
        self.assertIn("You can preview but not publish", page)
        response = viewer.post(self.preview_url, {"section": self.six_a.pk, "token": "x"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TermPublication.objects.count(), 0)

    def test_routes_keep_their_permission_outcomes(self):
        self.publish()
        pub = self.pub_for(self.asha)
        urls = [
            self.preview_url, self.stale_url,
            reverse("core:publication-detail", args=[pub.pk]),
            reverse("core:publication-withdraw", args=[pub.pk]),
        ]
        anonymous, teacher = self.client_class(), self.teacher_client()
        _, nobody = self.client_with("view_assessment")
        _, viewer = self.client_with("view_termpublication")
        for url in urls:
            self.assertEqual(anonymous.get(url).status_code, 302, url)
            self.assertEqual(teacher.get(url).status_code, 403, url)
            self.assertEqual(nobody.get(url).status_code, 403, url)
            self.assertEqual(self.client.get(url).status_code, 200, url)
        for url in urls[:3]:
            self.assertEqual(viewer.get(url).status_code, 200, url)
        self.assertEqual(viewer.get(urls[3]).status_code, 403)  # withdraw needs the publish permission

    def test_guardian_is_never_sent_into_the_administrator_pages(self):
        self.assertEqual(self.portal.get(self.preview_url).status_code, 403)
        self.assertEqual(self.portal.get(self.stale_url).status_code, 403)


class StaleListTests(UiFixture, TestCase):
    def test_empty_state(self):
        page = html(self.client.get(self.stale_url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Stale publications</h1>', page)
        self.assertIn("None.", page)

    def test_stale_version_is_listed_with_badge_reason_and_link(self):
        self.publish()
        self.correct()
        pub = self.pub_for(self.asha)
        page = html(self.client.get(self.stale_url))
        self.assertIn('role="region" aria-label="Stale publications" tabindex="0"', page)
        self.assertEqual(re.findall(r'<th scope="col">([^<]+)</th>', page),
                         ["Student", "Term", "Version", "Status", "Reason"])
        self.assertRegex(page, r"erp-status--stale[^>]*><span[^>]*>Status: </span>Stale")
        self.assertIn("Asha Rao", page)
        self.assertIn("2026-27 Term 1", page)
        self.assertIn("Version 1", page)
        self.assertIn(pub.status_reason, page)
        self.assertIn(reverse("core:publication-detail", args=[pub.pk]), page)
        self.assertNotIn("Bina Other", page)  # only the corrected Student's card is stale

    def test_published_and_withdrawn_versions_are_not_listed(self):
        self.publish()
        self.assertIn("None.", html(self.client.get(self.stale_url)))
        publication.withdraw(self.pub_for(self.bina), actor=self.admin, reason="Withdrawn in test")
        self.assertIn("None.", html(self.client.get(self.stale_url)))

    def test_context_is_unchanged(self):
        self.publish()
        self.correct()
        self.assertEqual(list(self.client.get(self.stale_url).context["stale"]),
                         list(publication.stale_publications()))


class DetailTests(UiFixture, TestCase):
    def detail(self, pub, client=None):
        return html((client or self.client).get(reverse("core:publication-detail", args=[pub.pk])))

    def test_published_version(self):
        self.publish()
        pub = self.pub_for(self.asha)
        page = self.detail(pub)
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Asha Rao</h1>', page)
        self.assertIn("2026-27 Term 1 · version 1", page)
        self.assertRegex(page, r"erp-status--published[^>]*><span[^>]*>Status: </span>Published")
        self.assertIn('aria-label="Results as released in version 1"', page)
        self.assertIn("UT1", page)
        self.assertIn("15.00 / 20.00", page)
        self.assertIn("Steady progress.", page)
        self.assertNotIn("have changed since release", page)
        self.assertIn(reverse("core:publication-withdraw", args=[pub.pk]), page)
        self.assertIn("Review and republish", page)
        self.assertIn(f"?section={self.six_a.pk}", page)
        self.assertIn("(this version)", page)
        self.assertIn("Withdraw</strong> takes effect at once", page)

    def test_stale_version_has_its_own_status_and_notice(self):
        self.publish()
        self.correct()
        pub = self.pub_for(self.asha)
        page = self.detail(pub)
        self.assertRegex(page, r"erp-status--stale[^>]*><span[^>]*>Status: </span>Stale")
        self.assertIn("Source results or remark have changed since release.", page)
        self.assertIn("Guardians do not see this report card until you review and republish it, or withdraw it.", page)
        self.assertIn(reverse("core:publication-withdraw", args=[pub.pk]), page)
        self.assertIn(pub.status_reason, page)
        self.assertEqual(self.cards(), [])  # guardians do not see a stale card as current

    def test_superseded_version_is_history_with_no_actions(self):
        self.publish()
        self.correct()
        self.publish()
        v1, v2 = self.pub_for(self.asha, 1), self.pub_for(self.asha, 2)
        old = self.detail(v1)
        self.assertRegex(old, r"erp-status--neutral[^>]*><span[^>]*>Status: </span>Superseded")
        self.assertIn("replaced by a later one and is kept permanently as history", old)
        self.assertNotIn(reverse("core:publication-withdraw", args=[v1.pk]), old)
        self.assertNotIn("Review and republish", old)
        self.assertIn("15.00 / 20.00", old)  # the original snapshot is immutable
        new = self.detail(v2)
        self.assertRegex(new, r"erp-status--published[^>]*><span[^>]*>Status: </span>Published")
        self.assertIn("16.00 / 20.00", new)
        self.assertIn("(this version)", new)
        for page in (old, new):
            self.assertIn("Version 2", page)
            self.assertIn("Version 1", page)
        self.assertEqual(len(self.cards()), 1)

    def test_withdrawn_version_is_history_and_hidden_from_guardians(self):
        self.publish()
        pub = self.pub_for(self.asha)
        publication.withdraw(pub, actor=self.admin, reason="Published in error")
        pub.refresh_from_db()
        page = self.detail(pub)
        self.assertRegex(page, r"erp-status--revoked[^>]*><span[^>]*>Status: </span>Withdrawn")
        self.assertIn("This version was withdrawn.", page)
        self.assertIn("Published in error", page)
        self.assertNotIn(reverse("core:publication-withdraw", args=[pub.pk]), page)
        self.assertEqual(self.cards(), [])

    def test_partial_version_is_labelled(self):
        self.make_assessment(name="UT2", on=date(2026, 8, 1))
        self.publish(include=[self.asha.pk])
        page = self.detail(self.pub_for(self.asha))
        self.assertRegex(page, r"erp-status--pending[^>]*><span[^>]*>Status: </span>Partial")
        self.assertIn("1 assessment(s) not finalized at release", page)

    def test_actions_need_the_publish_permission(self):
        self.publish()
        pub = self.pub_for(self.asha)
        _, viewer = self.client_with("view_termpublication")
        page = self.detail(pub, viewer)
        self.assertNotIn("Review and republish", page)
        self.assertNotIn(reverse("core:publication-withdraw", args=[pub.pk]), page)
        self.assertIn("Asha Rao", page)


class WithdrawTests(UiFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = self.pub_for(self.asha)
        self.url = reverse("core:publication-withdraw", args=[self.pub.pk])

    def test_page_structure(self):
        page = html(self.client.get(self.url))
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('class="erp-page-title">Withdraw report card</h1>', page)
        self.assertIn("Asha Rao — Term 1 (version 1)", page)
        self.assertIn("Guardians stop seeing this report card at once. The version is kept permanently as history.", page)
        self.assertIn("erp-required-legend", page)
        self.assertIn('for="id_reason"', page)
        self.assertIn('class="btn btn-danger">Withdraw</button>', page)
        self.assertIn(f'href="{reverse("core:publication-detail", args=[self.pub.pk])}"', page)

    def test_blank_reason_is_summarised_and_associated(self):
        page = html(self.client.post(self.url, {"reason": ""}))
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertIn('href="#id_reason"', page)
        self.assertRegex(page, r'aria-describedby="[^"]*id_reason_error[^"]*"')
        self.assertIn('id="id_reason_error"', page)
        self.assertEqual(self.pub_for(self.asha).status, Status.PUBLISHED)

    def test_post_withdraws_with_the_audited_reason(self):
        response = self.client.post(self.url, {"reason": "Wrong remark"})
        self.assertRedirects(response, reverse("core:publication-detail", args=[self.pub.pk]))
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.status, Status.WITHDRAWN)
        self.assertEqual(self.pub.status_reason, "Wrong remark")
        self.assertEqual(self.pub.status_changed_by, self.admin)
        self.assertEqual(self.cards(), [])

    def test_withdrawing_a_non_current_version_shows_the_service_error(self):
        publication.withdraw(self.pub, actor=self.admin, reason="First")
        page = html(self.client.post(self.url, {"reason": "Again"}))
        self.assertIn('role="alert" id="form-error-summary"', page)

    def test_get_never_withdraws(self):
        self.client.get(self.url)
        self.assertEqual(self.pub_for(self.asha).status, Status.PUBLISHED)


    def test_publish_only_user_gets_no_link_to_the_inaccessible_publication_detail(self):
        _, publisher = self.client_with("publish_termpublication")
        detail = reverse("core:publication-detail", args=[self.pub.pk])
        self.assertEqual(publisher.get(detail).status_code, 403)  # the destination really is closed
        response = publisher.get(self.url)
        page = html(response)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f'href="{detail}"', page)
        self.assertNotIn("Back to publication", page)
        self.assertNotIn(">Cancel</a>", page)
        self.assertIn('class="btn btn-danger">Withdraw</button>', page)  # the form itself still works
        self.assertIn('for="id_reason"', page)

    def test_view_only_user_still_cannot_open_withdraw(self):
        _, viewer = self.client_with("view_termpublication")
        self.assertEqual(viewer.get(self.url).status_code, 403)
        self.assertEqual(viewer.post(self.url, {"reason": "x"}).status_code, 403)
        self.assertEqual(self.pub_for(self.asha).status, Status.PUBLISHED)

    def test_publish_and_view_user_keeps_both_back_links(self):
        _, both = self.client_with("publish_termpublication", "view_termpublication")
        detail = reverse("core:publication-detail", args=[self.pub.pk])
        page = html(both.get(self.url))
        self.assertIn("Back to publication", page)
        self.assertIn(">Cancel</a>", page)
        self.assertEqual(page.count(f'href="{detail}"'), 2)  # header action and Cancel

    def test_publish_only_post_still_withdraws_with_the_audited_reason(self):
        user, publisher = self.client_with("publish_termpublication")
        response = publisher.post(self.url, {"reason": "Sent to the wrong family"})
        self.assertRedirects(response, reverse("core:publication-detail", args=[self.pub.pk]),
                             fetch_redirect_response=False)  # the unchanged view's redirect
        self.pub.refresh_from_db()
        self.assertEqual(self.pub.status, Status.WITHDRAWN)
        self.assertEqual(self.pub.status_reason, "Sent to the wrong family")
        self.assertEqual(self.pub.status_changed_by, user)
        self.assertEqual(self.cards(), [])

    def test_publish_only_blank_reason_shows_the_error_summary_without_a_back_link(self):
        _, publisher = self.client_with("publish_termpublication")
        page = html(publisher.post(self.url, {"reason": ""}))
        self.assertIn('role="alert" id="form-error-summary"', page)
        self.assertNotIn("Back to publication", page)
        self.assertEqual(self.pub_for(self.asha).status, Status.PUBLISHED)

    def test_anonymous_and_teacher_access_is_unchanged(self):
        self.assertEqual(self.client_class().get(self.url).status_code, 302)
        self.assertEqual(self.client_class().post(self.url, {"reason": "x"}).status_code, 302)
        teacher = self.teacher_client()
        self.assertEqual(teacher.get(self.url).status_code, 403)
        self.assertEqual(teacher.post(self.url, {"reason": "x"}).status_code, 403)
        self.assertEqual(self.pub_for(self.asha).status, Status.PUBLISHED)


class BreadcrumbTests(UiFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.publish()
        self.pub = self.pub_for(self.asha)
        self.detail_url = reverse("core:publication-detail", args=[self.pub.pk])
        self.withdraw_url = reverse("core:publication-withdraw", args=[self.pub.pk])

    def trail(self, url, user=None):
        return breadcrumb_context(resolve(url), user)

    def labels(self, context):
        return [c["label"] for c in context["breadcrumbs"]]

    def test_preview_trail_has_only_the_no_id_ancestor(self):
        context = self.trail(self.preview_url)
        self.assertEqual(self.labels(context), ["Overview", "Academic Years", "Publish to guardians"])
        self.assertEqual(context["nav_section"], "academic-year-list")

    def test_preview_header_links_back_to_the_year_terms_with_the_real_year_id(self):
        page = html(self.client.get(self.preview_url))
        self.assertIn(f'href="{reverse("core:academic-year-terms", args=[self.year.pk])}"', page)

    def test_stale_list_keeps_its_sidebar_section_and_drops_a_single_crumb(self):
        context = self.trail(self.stale_url)
        self.assertEqual(self.labels(context), ["Overview", "Stale publications"])
        self.assertEqual(context["nav_section"], "publications-stale")
        user, _ = self.client_with("view_termpublication")
        self.assertEqual(self.trail(self.stale_url, user)["breadcrumbs"], [])

    def test_detail_and_withdraw_trails(self):
        detail = self.trail(self.detail_url)
        self.assertEqual(self.labels(detail), ["Overview", "Stale publications", "Publication"])
        withdraw = self.trail(self.withdraw_url)
        self.assertEqual(self.labels(withdraw), ["Overview", "Stale publications", "Publication", "Withdraw"])
        self.assertEqual(withdraw["breadcrumbs"][2]["url"], self.detail_url)  # own pk, same model
        self.assertEqual(withdraw["breadcrumbs"][1]["url"], self.stale_url)

    def test_parent_crumbs_follow_the_destination_permission(self):
        user, _ = self.client_with("view_school", "publish_termpublication")
        self.assertEqual(self.labels(self.trail(self.withdraw_url, user)), ["Overview", "Withdraw"])
        user, _ = self.client_with("view_school", "publish_termpublication", "view_termpublication")
        self.assertEqual(self.labels(self.trail(self.withdraw_url, user)),
                         ["Overview", "Stale publications", "Publication", "Withdraw"])
        user, _ = self.client_with("view_termpublication")
        self.assertEqual(self.labels(self.trail(self.detail_url, user)),
                         ["Stale publications", "Publication"])  # no Overview without view_school

    def test_rendered_detail_page_shows_the_trail(self):
        page = html(self.client.get(self.detail_url))
        self.assertIn('aria-label="Breadcrumb"', page)
        self.assertIn(f'href="{self.stale_url}"', page)
