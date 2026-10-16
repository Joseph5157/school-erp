"""Phase 3B: announcement preview before publishing (F07) and conditional fields (F23)."""

from django.test import TestCase
from django.urls import reverse

from core import announcements
from core import guardian_accounts as ga
from core.models import (
    Announcement,
    Applicant,
    ClassGrade,
    Guardian,
    Notification,
    Section,
    Student,
)
from core.tests.test_authorization import AuthorizationClientsMixin
from core.tests.test_phase6_access_boundary import METHOD
from core.tests.test_phase7_announcements import AnnouncementFixture

ALL = Announcement.Audience.ALL
CLASS = Announcement.Audience.CLASS
SECTION = Announcement.Audience.SECTION


class PreviewFixture(AuthorizationClientsMixin, AnnouncementFixture):
    """Whole school = 3 guardians (2 opted in); Grade 6 = 2; Grade 7 = 1; 6B = 0."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:announcement-create")
        self.grade7 = ClassGrade.objects.create(name="Grade 7")
        self.seven_a = Section.objects.create(class_grade=self.grade7, name="A")
        student = Student.objects.create(
            applicant=Applicant.objects.create(
                admission_status="ACCEPTED", full_name="Third Child"
            ),
            full_name="Third Child")
        student.enroll(academic_year=self.year, class_grade=self.grade7,
                       section=self.seven_a, start_date=self.today.replace(month=6, day=1))
        third = Guardian.objects.create(full_name="Third Parent")
        link = self.relate(student, third)
        ga.create_guardian_account(guardian=third, username="third", method=METHOD,
                                   note="known", actor=self.admin)
        ga.grant_student_access(student_guardian=link, actor=self.admin)

    def data(self, **overrides):
        data = {"title": "Sports Day", "body": "Line one\nLine two <b>x</b>", "audience": "ALL"}
        data.update(overrides)
        return data

    def post(self, client=None, **overrides):
        return (client or self.administrator).post(self.url, self.data(**overrides))


class PreviewStepTests(PreviewFixture, TestCase):
    def test_preview_saves_nothing_and_shows_the_notice(self):
        page = self.post()
        self.assertEqual(page.status_code, 200)
        self.assertFalse(Announcement.objects.exists())
        self.assertEqual(Notification.objects.count(), 0)
        self.assertTemplateUsed(page, "core/announcement_preview.html")
        self.assertContains(page, "Sports Day")
        self.assertContains(page, "Line one<br>Line two &lt;b&gt;x&lt;/b&gt;")
        self.assertContains(page, "Whole school")
        self.assertContains(page, "Publish notice")
        self.assertContains(page, "Back to edit")
        self.assertContains(page, 'name="confirm"')
        self.assertContains(page, 'name="edit"')

    def test_preview_counts_match_the_published_notice(self):
        cases = (
            (self.data(), {"audience": ALL}),
            (self.data(audience="CLASS", class_grade=self.grade7.pk),
             {"audience": CLASS, "class_grade": self.grade7}),
            (self.data(audience="CLASS", class_grade=self.grade6.pk),
             {"audience": CLASS, "class_grade": self.grade6}),
            (self.data(audience="SECTION", section=self.six_a.pk),
             {"audience": SECTION, "section": self.six_a}),
            (self.data(audience="SECTION", section=self.six_b.pk),
             {"audience": SECTION, "section": self.six_b}),
        )
        seen = set()
        for data, kwargs in cases:
            with self.subTest(data=data):
                page = self.administrator.post(self.url, data)
                shown = page.context["counts"]
                notice = announcements.publish(
                    title="t", body="b", actor=self.admin, **kwargs)
                self.assertEqual(shown, announcements.audience_counts(notice))
                self.assertContains(page, f"<strong>{shown['guardians']}</strong>")
                self.assertContains(page, f"<strong>{shown['opted_in']}</strong>")
                seen.add((shown["guardians"], shown["opted_in"]))
        self.assertEqual(announcements.preview_counts(audience=ALL),
                         {"guardians": 3, "opted_in": 2})
        self.assertEqual(announcements.preview_counts(audience=CLASS, class_grade=self.grade7),
                         {"guardians": 1, "opted_in": 0})
        self.assertEqual(announcements.preview_counts(audience=CLASS, class_grade=self.grade6),
                         {"guardians": 2, "opted_in": 2})
        self.assertGreater(len(seen), 2)

    def test_preview_counts_ignore_irrelevant_targets(self):
        self.assertEqual(
            announcements.preview_counts(audience=ALL, class_grade=self.grade7,
                                         section=self.six_a),
            announcements.preview_counts(audience=ALL))
        self.assertFalse(Announcement.objects.exists())

    def test_preview_shows_class_and_section_labels(self):
        page = self.post(audience="CLASS", class_grade=self.grade7.pk)
        self.assertContains(page, "Grade 7")
        page = self.post(audience="SECTION", section=self.six_a.pk)
        self.assertContains(page, "Grade 6 - A")

    def test_nobody_can_see_notice_when_no_guardians(self):
        page = self.post(audience="SECTION", section=self.six_b.pk)
        self.assertEqual(page.context["counts"]["guardians"], 0)
        self.assertContains(page, "Nobody can see this notice yet")
        self.assertContains(page, "Publish notice")

    def test_no_warning_when_guardians_can_see_it(self):
        self.assertNotContains(self.post(), "Nobody can see this notice yet")

    def test_hidden_fields_carry_the_values_escaped(self):
        page = self.post(audience="SECTION", section=self.six_a.pk, title='A "quoted" <t>')
        self.assertContains(page, 'name="audience" value="SECTION"')
        self.assertContains(page, f'name="section" value="{self.six_a.pk}"')
        self.assertContains(page, 'value="A &quot;quoted&quot; &lt;t&gt;"')

    def test_confirm_publishes_exactly_one_and_redirects(self):
        page = self.post(confirm="1")
        notice = Announcement.objects.get()
        self.assertRedirects(page, reverse("core:announcement-detail", args=[notice.pk]))
        self.assertEqual((notice.title, notice.published_by.username),
                         ("Sports Day", "administrator"))

    def test_stale_class_is_dropped_for_whole_school_through_preview_and_confirm(self):
        preview = self.post(class_grade=self.grade7.pk, section=self.six_a.pk)
        self.assertEqual(preview.context["counts"], {"guardians": 3, "opted_in": 2})
        self.assertIsNone(preview.context["notice"].class_grade)
        self.assertFalse(Announcement.objects.exists())
        self.post(confirm="1", class_grade=self.grade7.pk, section=self.six_a.pk)
        notice = Announcement.objects.get()
        self.assertEqual((notice.audience, notice.class_grade, notice.section), (ALL, None, None))

    def test_confirm_shows_success_message(self):
        page = self.administrator.post(self.url, self.data(confirm="1"), follow=True)
        self.assertContains(page, "Notice published. Guardians can read it in the portal now.")

    def test_edit_returns_the_prefilled_form_without_errors(self):
        page = self.post(edit="1", title="", audience="CLASS", body="Keep me")
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, "core/announcement_form.html")
        self.assertContains(page, "Keep me")
        self.assertNotContains(page, "This field is required")
        self.assertNotContains(page, "Choose the class.")
        self.assertFalse(Announcement.objects.exists())

    def test_edit_keeps_chosen_values(self):
        page = self.post(edit="1", audience="SECTION", section=self.six_a.pk)
        self.assertContains(page, "Sports Day")
        self.assertContains(page, f'<option value="{self.six_a.pk}" selected>')
        form = page.context["form"]
        self.assertEqual(form["audience"].value(), "SECTION")


class InvalidInputTests(PreviewFixture, TestCase):
    def test_missing_title_rerenders_form_without_preview(self):
        page = self.post(title="")
        self.assertTemplateUsed(page, "core/announcement_form.html")
        self.assertTemplateNotUsed(page, "core/announcement_preview.html")
        self.assertContains(page, "This field is required")
        self.assertFalse(Announcement.objects.exists())

    def test_class_audience_without_class_has_no_preview(self):
        page = self.post(audience="CLASS")
        self.assertTemplateNotUsed(page, "core/announcement_preview.html")
        self.assertContains(page, "Choose the class.")
        self.assertFalse(Announcement.objects.exists())

    def test_confirm_revalidates_and_rejects_bad_data(self):
        bad = (dict(title=""), dict(body=""), dict(audience="CLASS"),
               dict(audience="SECTION"), dict(audience="BOGUS"),
               dict(audience="CLASS", class_grade=99999),
               dict(title="x" * 121))
        for overrides in bad:
            with self.subTest(overrides=overrides):
                page = self.post(confirm="1", **overrides)
                self.assertEqual(page.status_code, 200)
                self.assertTemplateUsed(page, "core/announcement_form.html")
                self.assertFalse(Announcement.objects.exists())

    def test_confirm_with_missing_fields_is_rejected(self):
        page = self.administrator.post(self.url, {"confirm": "1"})
        self.assertEqual(page.status_code, 200)
        self.assertFalse(Announcement.objects.exists())


class AccessTests(PreviewFixture, TestCase):
    def test_non_admin_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)
        for extra in ({}, {"confirm": "1"}, {"edit": "1"}):
            self.assertEqual(self.non_admin.post(self.url, self.data(**extra)).status_code, 403)
        self.assertFalse(Announcement.objects.exists())

    def test_anonymous_redirected_to_login(self):
        for response in (self.anonymous.get(self.url),
                         self.anonymous.post(self.url, self.data(confirm="1"))):
            self.assertRedirects(response, f"{reverse('login')}?next={self.url}",
                                 fetch_redirect_response=False)
        self.assertFalse(Announcement.objects.exists())


class FormPageTests(PreviewFixture, TestCase):
    def test_form_copy_button_and_js_hooks(self):
        page = self.administrator.get(self.url)
        self.assertContains(
            page, "You'll see a preview before anything is sent. Published notices "
                  "can't be edited; withdraw and republish to correct one.", html=False)
        self.assertNotContains(page, "Saving publishes")
        self.assertContains(page, "Preview notice")
        self.assertContains(page, "data-erp-audience-form")
        self.assertContains(page, 'data-erp-audience-field="CLASS"')
        self.assertContains(page, 'data-erp-audience-field="SECTION"')

    def test_preview_publish_button_is_single_use(self):
        page = self.post()
        self.assertContains(page, "data-erp-once")
        self.assertContains(page, '<input type="hidden" name="confirm" value="1">', html=True)
