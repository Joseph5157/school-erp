"""UI-D1-6B: Announcements (list, form, preview, detail) presentation, accessibility and navigation.

Presentation only: the form -> preview -> confirm workflow, hidden fields, JS hooks, counts, permissions and
withdrawal rules are the existing ones and are re-proved here.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core import announcements
from core.breadcrumbs import breadcrumb_context
from core.models import Announcement, Notification, School
from core.tests.test_phase7_announcements import CLASS, SECTION
from core.tests.test_ui_admin_phase3b import PreviewFixture

User = get_user_model()
ACTIVE_LINK = r'<a class="nav-link active" href="([^"]+)"'
LIST = reverse("core:announcement-list")
CREATE = reverse("core:announcement-create")


def html(response):
    return response.content.decode()


class Base(PreviewFixture):
    def client_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(username=f"viewer{self._viewers}", password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return user, client

    def detail_url(self, notice):
        return reverse("core:announcement-detail", args=[notice.pk])


class ListTests(Base, TestCase):
    def test_header_table_and_empty_state(self):
        page = html(self.administrator.get(LIST))
        self.assertRegex(page, r'<h1 class="erp-page-title">Announcements</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertIn('<a class="btn btn-primary" href="%s">New notice</a>' % CREATE, page)
        self.assertIn("No notices yet.", page)
        self.assertIn('<br><a class="btn btn-outline-primary btn-sm mt-2" href="%s">Publish a notice</a>' % CREATE, page)
        self.assertIn('role="region" aria-label="Announcements" tabindex="0"', page)
        self.assertIn("<caption", page)
        self.assertEqual(page.count('scope="col"'), 4)

    def test_rows_use_row_headers_and_distinct_text_badges(self):
        live = self.notice(title="Sports Day")
        gone = self.notice(title="Old news")
        announcements.withdraw(gone, actor=self.admin, reason="Wrong date")
        page = html(self.administrator.get(LIST))
        self.assertRegex(page, r'<th scope="row"[^>]*><a href="%s">Sports Day</a></th>' % self.detail_url(live))
        self.assertRegex(page, r"erp-status--published\"><span class=\"visually-hidden\">Status: </span>Live")
        self.assertRegex(page, r"erp-status--revoked\"><span class=\"visually-hidden\">Status: </span>Withdrawn")
        self.assertEqual(page.count('scope="row"'), 2)
        self.assertNotIn("No notices yet.", page)

    def test_titles_are_escaped(self):
        self.notice(title="<script>alert(1)</script>")
        page = html(self.administrator.get(LIST))
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_viewer_without_add_permission_gets_no_action(self):
        _, viewer = self.client_with("view_announcement")
        page = html(viewer.get(LIST))
        self.assertIn("No notices yet.", page)
        self.assertNotIn(CREATE, page)
        self.notice()
        self.assertNotIn(CREATE, html(viewer.get(LIST)))

    def test_permission_outcomes_are_unchanged(self):
        self.assertEqual(self.anonymous.get(LIST).status_code, 302)
        self.assertEqual(self.non_admin.get(LIST).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(LIST).status_code, 403)


class FormTests(Base, TestCase):
    def test_structure_and_js_hooks_survive(self):
        page = html(self.administrator.get(CREATE))
        self.assertRegex(page, r'<h1 class="erp-page-title">New notice</h1>')
        self.assertIn("You'll see a preview before anything is sent.", page)
        self.assertIn('<form method="post" class="erp-form" data-erp-audience-form>', page)
        self.assertIn("Fields marked with an asterisk are required.", page)
        self.assertEqual(page.count('data-erp-audience-field="CLASS"'), 1)
        self.assertEqual(page.count('data-erp-audience-field="SECTION"'), 1)
        # no-JS rendering: neither selector carries the hidden attribute
        self.assertNotRegex(page, r'data-erp-audience-field="[A-Z]+"[^>]*hidden')
        radios = re.findall(r'<input type="radio" name="audience" value="([A-Z]+)"', page)
        self.assertEqual(radios, ["ALL", "CLASS", "SECTION"])
        group = re.search(r"<fieldset.*?</fieldset>", page, re.S).group(0)
        self.assertIn("<legend", group)
        for name in ("title", "body", "class_grade", "section"):
            self.assertIn(f'name="{name}"', page)
        self.assertIn(f'<a class="btn btn-link" href="{LIST}">Cancel</a>', page)

    def test_invalid_post_shows_summary_linked_to_the_field(self):
        page = html(self.post(audience="CLASS"))
        self.assertIn('id="form-error-summary"', page)
        self.assertIn("Fix 1 problem before previewing:", page)
        self.assertIn('href="#id_class_grade"', page)
        self.assertIn("Choose the class.", page)
        self.assertFalse(Announcement.objects.exists())
        page = html(self.post(title="", body=""))
        self.assertIn("Fix 2 problems before previewing:", page)
        self.assertIn('href="#id_title"', page)

    def test_back_to_edit_refills_without_a_summary(self):
        page = html(self.post(edit="1", title="", audience="CLASS", body="Keep me"))
        self.assertNotIn("form-error-summary", page)
        self.assertIn("Keep me", page)

    def test_cancel_is_gated_by_view_announcement(self):
        _, adder = self.client_with("add_announcement")
        page = html(adder.get(CREATE))
        self.assertIn("Preview notice", page)
        self.assertNotIn(">Cancel</a>", page)
        _, both = self.client_with("add_announcement", "view_announcement")
        self.assertIn(">Cancel</a>", html(both.get(CREATE)))

    def test_permission_outcomes_are_unchanged(self):
        self.assertEqual(self.anonymous.get(CREATE).status_code, 302)
        self.assertEqual(self.non_admin.get(CREATE).status_code, 403)
        _, viewer = self.client_with("view_announcement")
        self.assertEqual(viewer.get(CREATE).status_code, 403)
        self.assertEqual(viewer.post(CREATE, self.data()).status_code, 403)


class PreviewTests(Base, TestCase):
    def forms(self, page):
        return re.findall(r'<form method="post" action="([^"]*)">(.*?)</form>', page, re.S)

    def test_preview_writes_nothing_and_keeps_both_forms_exactly(self):
        response = self.post()
        page = html(response)
        self.assertTemplateUsed(response, "core/announcement_preview.html")
        self.assertFalse(Announcement.objects.exists())
        self.assertEqual(Notification.objects.count(), 0)
        self.assertRegex(page, r'<h1 class="erp-page-title">Preview notice</h1>')
        forms = [f for f in self.forms(page) if f[0] == CREATE]
        self.assertEqual(len(forms), 2)
        expected = ["csrfmiddlewaretoken", "title", "body", "audience", "class_grade", "section"]
        for (_, body), extra in zip(forms, ("confirm", "edit")):
            self.assertEqual(re.findall(r'name="([^"]+)"', body), expected + [extra])
            self.assertIn(f'<input type="hidden" name="{extra}" value="1">', body)
            self.assertIn('<input type="hidden" name="title" value="Sports Day">', body)
        self.assertIn("data-erp-once", forms[0][1])
        self.assertNotIn("data-erp-once", forms[1][1])
        self.assertIn(">Publish notice</button>", forms[0][1])
        self.assertIn(">Back to edit</button>", forms[1][1])

    def test_audience_variations_show_service_counts_and_labels(self):
        cases = (
            (self.data(), "Whole school"),
            (self.data(audience="CLASS", class_grade=self.grade7.pk), "Grade 7"),
            (self.data(audience="CLASS", class_grade=self.grade6.pk), "Grade 6"),
            (self.data(audience="SECTION", section=self.six_b.pk), "Grade 6 - B"),
        )
        for data, label in cases:
            with self.subTest(label=label):
                response = self.administrator.post(CREATE, data)
                page = html(response)
                counts = response.context["counts"]
                self.assertIn(label, page)
                self.assertIn(f"<dd class=\"col-sm-7\"><strong>{counts['guardians']}</strong></dd>", page)
                self.assertIn(f"<dd class=\"col-sm-7\"><strong>{counts['opted_in']}</strong></dd>", page)

    def test_nobody_note_is_a_labelled_status_only_for_an_empty_audience(self):
        page = html(self.administrator.post(CREATE, self.data(audience="SECTION", section=self.six_b.pk)))
        self.assertIn('role="status"', page)
        self.assertIn("Nobody can see this notice yet.", page)
        self.assertIn("No guardians yet", page)
        self.assertNotIn("Nobody can see", html(self.post()))

    def test_body_keeps_line_breaks_and_is_escaped(self):
        page = html(self.post())
        self.assertIn("Line one<br>Line two &lt;b&gt;x&lt;/b&gt;", page)

    def test_cancel_is_gated_by_view_announcement(self):
        _, adder = self.client_with("add_announcement")
        page = html(adder.post(CREATE, self.data()))
        self.assertIn("Publish notice", page)
        self.assertNotIn(">Cancel</a>", page)
        _, both = self.client_with("add_announcement", "view_announcement")
        self.assertIn(">Cancel</a>", html(both.post(CREATE, self.data())))

    def test_round_trip_publishes_once_and_edit_refills(self):
        back = self.post(edit="1")
        self.assertTemplateUsed(back, "core/announcement_form.html")
        response = self.administrator.post(CREATE, self.data(confirm="1"), follow=True)
        notice = Announcement.objects.get()
        self.assertRedirects(response, self.detail_url(notice))
        self.assertContains(response, "Notice published. Guardians can read it in the portal now.")

    def test_confirm_revalidates(self):
        page = self.post(confirm="1", audience="CLASS")
        self.assertTemplateUsed(page, "core/announcement_form.html")
        self.assertFalse(Announcement.objects.exists())


class DetailTests(Base, TestCase):
    def test_live_notice_has_facts_counts_and_both_actions(self):
        notice = self.notice(body="Line one\nLine two <b>x</b>")
        response = self.administrator.get(self.detail_url(notice))
        page = html(response)
        self.assertRegex(page, r'<h1 class="erp-page-title">Sports Day</h1>')
        self.assertEqual(page.count("<h1"), 1)
        self.assertRegex(page, r"erp-status--published\"><span class=\"visually-hidden\">Status: </span>Live")
        self.assertIn("Line one<br>Line two &lt;b&gt;x&lt;/b&gt;", page)
        counts = response.context["counts"]
        self.assertEqual(counts, announcements.audience_counts(notice))
        self.assertIn(f'<dd class="col-sm-7"><strong>{counts["guardians"]}</strong></dd>', page)
        self.assertIn(reverse("core:announcement-prepare", args=[notice.pk]), page)
        self.assertIn("Prepare WhatsApp messages", page)
        self.assertIn("Nothing is sent from here.", page)
        self.assertIn("Guardians stop seeing it at once.", page)
        self.assertIn('<a href="%s">All announcements</a>' % LIST, page)

    def test_withdraw_form_has_a_visible_label_and_the_same_field(self):
        notice = self.notice()
        page = html(self.administrator.get(self.detail_url(notice)))
        form = re.search(r'<form method="post" action="%s"[^>]*>(.*?)</form>' %
                         reverse("core:announcement-withdraw", args=[notice.pk]), page, re.S).group(1)
        self.assertRegex(form, r'<label for="withdraw-reason">Reason for withdrawing')
        self.assertNotIn("visually-hidden\" for", form)
        self.assertIn('id="withdraw-reason" name="reason" maxlength="200"', form)
        self.assertNotIn("placeholder", form)
        self.assertIn(">Withdraw</button>", form)

    def test_withdrawn_notice_is_distinct_and_has_no_actions(self):
        notice = self.notice()
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        page = html(self.administrator.get(self.detail_url(notice)))
        self.assertRegex(page, r"erp-status--revoked\"><span class=\"visually-hidden\">Status: </span>Withdrawn")
        self.assertNotIn("erp-status--published", page)
        self.assertIn("Wrong date", page)
        self.assertIn("<dt class=\"col-sm-3\">Withdrawn</dt>", page)
        self.assertNotIn("announcement-withdraw", page)
        self.assertNotIn("announcement-prepare", page)
        self.assertNotIn("Prepare WhatsApp messages", page)

    def test_audience_heading_depends_on_state_and_counts_stay_the_service_values(self):
        notice = self.notice()
        live = self.administrator.get(self.detail_url(notice))
        page = html(live)
        self.assertIn(">Who can see it</h2>", page)
        self.assertNotIn("Current audience eligibility", page)
        self.assertNotIn("not who saw the notice", page)
        counts = announcements.audience_counts(notice)
        self.assertEqual(live.context["counts"], counts)
        announcements.withdraw(notice, actor=self.admin, reason="Wrong date")
        gone = self.administrator.get(self.detail_url(notice))
        page = html(gone)
        self.assertIn(">Current audience eligibility</h2>", page)
        self.assertNotIn("Who can see it", page)
        self.assertIn("not who saw the notice", page)
        self.assertIn("This notice is withdrawn, so guardians cannot see it.", page)
        self.assertNotIn("can see it", page.replace("guardians cannot see it", ""))
        self.assertEqual(gone.context["counts"], counts)
        self.assertIn(f'<dd class="col-sm-7"><strong>{counts["guardians"]}</strong></dd>', page)
        self.assertIn(f'<dd class="col-sm-7"><strong>{counts["opted_in"]}</strong></dd>', page)

    def test_prepare_requires_assist_mode_and_permission(self):
        notice = self.notice()
        prepare = reverse("core:announcement-prepare", args=[notice.pk])
        _, viewer = self.client_with("view_announcement", "withdraw_announcement")
        self.assertNotIn(prepare, html(viewer.get(self.detail_url(notice))))
        _, sender = self.client_with("view_announcement", "send_notification")
        page = html(sender.get(self.detail_url(notice)))
        self.assertIn(prepare, page)
        self.assertNotIn("announcement-withdraw", page)
        School.objects.filter(pk=self.school.pk).update(notification_channel="PORTAL_ONLY")
        self.assertNotIn(prepare, html(sender.get(self.detail_url(notice))))
        self.assertNotIn(prepare, html(self.administrator.get(self.detail_url(notice))))

    def test_withdraw_reason_is_still_required_and_audited(self):
        notice = self.notice()
        url = reverse("core:announcement-withdraw", args=[notice.pk])
        page = self.administrator.post(url, {"reason": " "}, follow=True)
        self.assertContains(page, "Give a reason for withdrawing this notice.")
        notice.refresh_from_db()
        self.assertFalse(notice.is_withdrawn)
        self.administrator.post(url, {"reason": "Wrong date"})
        notice.refresh_from_db()
        self.assertTrue(notice.is_withdrawn)
        self.assertEqual(notice.withdrawal_reason, "Wrong date")
        self.assertEqual(notice.withdrawn_by, self.admin_user)

    def test_title_is_escaped_and_long_body_wraps_in_its_container(self):
        notice = self.notice(title="<i>x</i>", body="y" * 300)
        page = html(self.administrator.get(self.detail_url(notice)))
        self.assertNotIn("<i>x</i>", page)
        self.assertIn('<div class="erp-notice-body">', page)

    def test_permission_outcomes_are_unchanged(self):
        notice = self.notice()
        url = self.detail_url(notice)
        self.assertEqual(self.anonymous.get(url).status_code, 302)
        self.assertEqual(self.non_admin.get(url).status_code, 403)
        _, nobody = self.client_with("view_school")
        self.assertEqual(nobody.get(url).status_code, 403)
        _, viewer = self.client_with("view_announcement")
        self.assertEqual(viewer.get(url).status_code, 200)
        withdraw = reverse("core:announcement-withdraw", args=[notice.pk])
        self.assertEqual(viewer.post(withdraw, {"reason": "x"}).status_code, 403)


class NavigationTests(Base, TestCase):
    def labels(self, url, user=None):
        context = breadcrumb_context(resolve(url), user)
        return [c["label"] for c in context["breadcrumbs"]], context["nav_section"]

    def test_rules(self):
        notice = self.notice()
        self.assertEqual(self.labels(LIST), (["Overview", "Announcements"], "announcement-list"))
        self.assertEqual(self.labels(CREATE),
                         (["Overview", "Announcements", "New announcement"], "announcement-list"))
        self.assertEqual(self.labels(self.detail_url(notice)),
                         (["Overview", "Announcements", "Announcement"], "announcement-list"))

    def test_parent_crumbs_follow_the_destination_permission(self):
        notice = self.notice()
        detail = self.detail_url(notice)
        user, _ = self.client_with("view_school", "add_announcement")
        self.assertEqual(self.labels(CREATE, user)[0], ["Overview", "New announcement"])
        user, _ = self.client_with("view_school", "add_announcement", "view_announcement")
        self.assertEqual(self.labels(CREATE, user)[0], ["Overview", "Announcements", "New announcement"])
        user, _ = self.client_with("view_announcement")
        self.assertEqual(self.labels(detail, user)[0], ["Announcements", "Announcement"])
        user, _ = self.client_with("view_school")
        self.assertEqual(self.labels(LIST, user)[0], ["Overview", "Announcements"])
        user, _ = self.client_with("view_announcement")
        self.assertEqual(self.labels(LIST, user)[0], [])

    def test_list_crumb_never_carries_a_pk(self):
        first, second = self.notice(title="A"), self.notice(title="B")
        for notice in (first, second):
            context = breadcrumb_context(resolve(self.detail_url(notice)))
            self.assertEqual(context["breadcrumbs"][1]["url"], LIST)

    def test_sidebar_highlights_announcements_on_every_page(self):
        notice = self.notice()
        pages = {
            "list": self.administrator.get(LIST),
            "form": self.administrator.get(CREATE),
            "preview": self.post(),
            "invalid": self.post(audience="CLASS"),
            "detail": self.administrator.get(self.detail_url(notice)),
        }
        for name, response in pages.items():
            with self.subTest(page=name):
                self.assertEqual(re.findall(ACTIVE_LINK, html(response)), [LIST])
        # the page a withdraw or prepare POST redirects to is highlighted too
        followed = self.administrator.post(
            reverse("core:announcement-withdraw", args=[notice.pk]), {"reason": "x"}, follow=True)
        self.assertEqual(re.findall(ACTIVE_LINK, html(followed)), [LIST])

    def test_class_and_section_audience_labels_render_on_the_list(self):
        announcements.publish(title="C", body="b", audience=CLASS, class_grade=self.grade6, actor=self.admin)
        announcements.publish(title="S", body="b", audience=SECTION, section=self.six_b, actor=self.admin)
        page = html(self.administrator.get(LIST))
        self.assertIn("Grade 6 - B", page)
        self.assertIn(">Grade 6<", page)
