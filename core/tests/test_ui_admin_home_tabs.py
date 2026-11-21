"""Admin home tab shell: four tabs by job, each its own URL (?tab=)."""

import datetime
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import announcements
from core.models import (
    AcademicEnrollment,
    Announcement,
    Assessment,
    ClassGrade,
    Guardian,
    GuardianAccount,
    GuardianStudentAccess,
    Section,
    Student,
    StudentGuardian,
    StudentResult,
)
from core.tests.test_admin_overview_analytics import TODAY, A, MarksFixture, P

URL = reverse("core:admin-overview")
TAB_KEYS = ("today", "attendance", "academics", "parents")


def seed_academics(fx, extra_classes=3):
    """Data for every Academics card: finalized marks in both terms, a ready and an in-progress draft, no publications.

    Grade 1: s1 rises 40 points (improver), s2 falls 40 points (at risk). Each extra class has one
    student with steady marks, so four classes have results (best and worst show).
    """
    for term, (m1, m2) in ((fx.term_a, (10, 18)), (fx.term_b, (18, 10))):
        for n in (1, 2):
            fx.assessment({fx.s1: m1, fx.s2: m2}, name=f"Quiz {n}", term=term, pass_mark=10)
    for i in range(extra_classes):
        grade = ClassGrade.objects.create(name=f"Grade {i + 2}")
        section = Section.objects.create(class_grade=grade, name="A")
        student = fx.enroll_student(f"Steady Pupil {i}", grade, section)
        for term in (fx.term_a, fx.term_b):
            for n in (1, 2):
                fx.assessment(
                    {student: 10 + 2 * i}, name=f"Quiz {n}", term=term, class_grade=grade,
                    section=section, pass_mark=10,
                )
    fx.assessment({fx.s1: 15, fx.s2: 15}, name="Draft ready", finalize=False)
    fx.assessment({fx.s1: 12}, name="Draft marking", finalize=False)  # s2 unmarked: in progress


def add_portal_parent(fx, enrollment, name, username):
    """A guardian with a login and an active grant on the enrollment's student. Returns the grant."""
    guardian = Guardian.objects.create(full_name=name)
    link = StudentGuardian.objects.create(
        student=enrollment.student, guardian=guardian, relationship_type="FATHER"
    )
    user = get_user_model().objects.create_user(username=username)
    GuardianAccount.objects.create(
        user=user, guardian=guardian, identity_verified_by=fx.admin_user,
        identity_verification_method="OTHER", identity_verification_note="x",
        created_by=fx.admin_user,
    )
    return GuardianStudentAccess.objects.create(student_guardian=link, granted_by=fx.admin_user)


def seed_parents(fx):
    """s1 has a portal parent; a third student has a pending-review grant (placement ended); one published notice."""
    add_portal_parent(fx, fx.s1, "Rajesh Rao", "seed-parent1")
    fx.s3 = fx.enroll_student("Leaver Lal", fx.class_grade, fx.section)
    fx.review_grant = add_portal_parent(fx, fx.s3, "Sunita Lal", "seed-parent2")
    AcademicEnrollment.objects.filter(pk=fx.s3.pk).update(
        status="COMPLETED", end_date=datetime.date(2026, 7, 1)
    )
    fx.notice = announcements.publish(
        title="Sports day", body="Bring a hat", audience=Announcement.Audience.ALL,
        actor=fx.admin_user,
    )


def card_html(html, name):
    """The text of one card, from its class to the next card (or the end of the section)."""
    start = html.index(f"erp-card--{name}")
    ends = [html.find("erp-card erp-card--", start + 10), html.find("</section>", start)]
    return html[start:min(e for e in ends if e != -1)]


def tab_nav(html):
    match = re.search(r'<nav class="erp-home-tabs" aria-label="Overview sections">(.*?)</nav>', html, re.S)
    assert match, "no tab bar"
    return match.group(1)


def tab_links(html):
    """[(label, href, current)] in page order."""
    return [
        (label, href, bool(current))
        for href, current, label in re.findall(
            r'<a class="erp-home-tab" href="([^"]*)"( aria-current="page")?>([^<]*)</a>', tab_nav(html)
        )
    ]


class HomeTabsTests(MarksFixture, TestCase):
    def get(self, client=None, **params):
        response = (client or self.administrator).get(URL, params)
        self.assertEqual(response.status_code, 200)
        return response

    def current_tab(self, response):
        return [label for label, _, current in tab_links(response.content.decode()) if current]

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def test_default_tab_is_today_and_marked_current(self):
        response = self.get()
        links = tab_links(response.content.decode())
        self.assertEqual([label for label, _, _ in links], ["Today", "Attendance", "Academics", "Parents"])
        self.assertEqual(
            [href for _, href, _ in links],
            [URL, f"{URL}?tab=attendance", f"{URL}?tab=academics", f"{URL}?tab=parents"],
        )
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertEqual(response.context["tab"], "today")

    def test_each_tab_has_its_own_url(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        response = self.get(tab="attendance")
        self.assertEqual(self.current_tab(response), ["Attendance"])
        self.assertContains(response, "Attendance heatmap")
        self.assertNotContains(response, "Birthdays")
        self.assertNotContains(response, "School at a glance")
        for key, label in (("academics", "Academics"), ("parents", "Parents")):
            with self.subTest(tab=key):
                self.assertEqual(self.current_tab(self.get(tab=key)), [label])

    def test_exactly_one_tab_context_is_built(self):
        names = {"today": "today", "attendance": "attendance_tab",
                 "academics": "academics_tab", "parents": "parents_tab"}
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                context = self.get(tab=key).context
                present = [name for name in names.values() if name in context]
                self.assertEqual(present, [names[key]])

    def test_unknown_or_empty_tab_shows_today(self):
        for value in ("nonsense", ""):
            with self.subTest(tab=value):
                response = self.get(tab=value)
                self.assertEqual(self.current_tab(response), ["Today"])
                self.assertIn("today", response.context)

    def test_old_period_links_are_ignored(self):
        response = self.get(period="term")
        self.assertEqual(self.current_tab(response), ["Today"])
        self.assertNotContains(response, "Custom range")
        self.assertNotContains(response, "erp-period")
        self.assertNotContains(response, 'role="status"')

    def test_only_the_active_tab_is_queried(self):
        self.get()  # warm per-process caches
        with CaptureQueriesContext(connection) as today:
            self.get()
        with CaptureQueriesContext(connection) as parents:
            self.get(tab="parents")
        self.assertLess(len(parents), len(today))

    def test_removed_parts_are_gone(self):
        self.day(datetime.date(2026, 7, 1), {self.s1: P, self.s2: A})
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(tab=key)
                for gone in ("Still to finish", "Score bands", "Daily attendance",
                             "erp-ring", "erp-gauge", "Checklist"):
                    self.assertNotContains(response, gone)

    def test_viewer_without_student_permission_sees_no_names(self):
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        Student.objects.filter(pk=self.s2.student_id).update(date_of_birth=datetime.date(2015, 7, 14))
        client = self.viewer("no-students", "view_school", "view_attendanceentry")
        birthdays = self.get(client).context["today"]["birthdays"]
        self.assertEqual(birthdays["count"], 1)
        self.assertEqual((birthdays["today"], birthdays["later"]), ([], []))
        response = self.get(client, tab="attendance")
        self.assertIsNone(response.context["attendance_tab"]["absentees"])
        self.assertNotContains(response, "Frequent absentees")
        self.assertNotContains(response, "Meena Das")
        # Holding students too brings the names back.
        both = self.viewer("both", "view_school", "view_attendanceentry", "view_student")
        self.assertEqual(self.get(both).context["today"]["birthdays"]["today"][0]["name"], "Meena Das")

    def test_nothing_repeats_across_tabs(self):
        for key in TAB_KEYS:
            with self.subTest(tab=key):
                response = self.get(self.superuser_client, tab=key)
                if key == "parents":
                    self.assertContains(response, "Guardian access")
                else:
                    self.assertNotContains(response, "Guardian access")
                if key != "today":
                    self.assertNotContains(response, "Attendance today")
                    self.assertNotContains(response, "School at a glance")
        today = self.get(self.superuser_client).context["today"]
        self.assertNotIn("access_reviews", [c["key"] for c in today["cards"]])
        self.assertNotIn("attendance", [c["key"] for c in today["cards"]])
        self.assertIn("attendance", today)

    def test_today_context_is_pinned_to_the_business_date(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        today = self.get(self.superuser_client).context["today"]
        self.assertEqual((today["attendance"]["present"], today["attendance"]["absent"]), (1, 1))
        for key in ("compliance", "overdue_marks", "assessments", "birthdays", "glance_cards"):
            self.assertIn(key, today)

    def test_compliance_and_overdue_marks_need_their_view_permissions(self):
        today = self.get(self.viewer("plain", "view_school")).context["today"]
        self.assertIsNone(today["compliance"])
        self.assertIsNone(today["overdue_marks"])
        today = self.get(
            self.viewer("ops", "view_school", "view_attendanceregister", "view_assessment")
        ).context["today"]
        self.assertIsNotNone(today["compliance"])
        self.assertEqual(today["overdue_marks"], [])

    def test_not_taken_registers_need_view_attendanceregister(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        attendance = self.get(self.viewer("school-only", "view_school")).context["today"]["attendance"]
        self.assertIsNone(attendance["not_taken"])  # sections and their teachers are not listed
        self.assertTrue(attendance["school_day"])
        rows = self.get(
            self.viewer("registers", "view_school", "view_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertEqual([r["class_name"] for r in rows], ["Grade 1"])
        self.assertIsNotNone(rows[0]["url"])  # the draft opens on the register page
        rows = self.get(
            self.viewer("add-only", "view_school", "add_attendanceregister")
        ).context["today"]["attendance"]["not_taken"]
        self.assertIsNone(rows)

    def parents_page(self, client=None):
        return self.get(client or self.superuser_client, tab="parents").content.decode()

    def test_parents_tab_shows_three_cards(self):
        seed_parents(self)
        html = self.parents_page()
        for name, title in (("notice", "New announcement"), ("engagement", "Parent engagement"),
                            ("access", "Guardian access")):
            self.assertIn(title, card_html(html, name))
        self.assertNotIn("Parents at a glance", html)
        self.assertNotIn("Pending access reviews", html)

    def test_card_form_posts_to_the_preview_page(self):
        html = card_html(self.parents_page(), "notice")
        self.assertIn(f'action="{reverse("core:announcement-create")}"', html)
        self.assertIn("data-erp-audience-form", html)
        self.assertIn('class="erp-btn erp-btn--primary"', html)
        self.assertIn("Message", html)
        self.assertIn("You'll see a preview before anything is sent.", html)

    def test_card_form_errors_land_on_new_notice_page(self):
        response = self.superuser_client.post(
            reverse("core:announcement-create"), {"title": "", "body": "Hello", "audience": "ALL"}
        )
        self.assertTemplateUsed(response, "core/announcement_form.html")
        self.assertContains(response, "Hello")

    def test_card_form_preview_then_publish_still_works(self):
        response = self.superuser_client.post(
            reverse("core:announcement-create"), {"title": "Trip", "body": "Bring lunch", "audience": "ALL"}
        )
        self.assertTemplateUsed(response, "core/announcement_preview.html")
        self.assertFalse(Announcement.objects.filter(title="Trip").exists())

    def test_sent_list_newest_first_links_to_detail(self):
        seed_parents(self)
        newer = announcements.publish(
            title="Fee reminder", body="Due soon", audience=Announcement.Audience.ALL,
            actor=self.admin_user,
        )
        announcements.withdraw(newer, actor=self.admin_user, reason="Wrong date")
        html = card_html(self.parents_page(), "notice")
        self.assertLess(html.index("Fee reminder"), html.index("Sports day"))
        self.assertIn(reverse("core:announcement-detail", args=[self.notice.pk]), html)
        self.assertIn("Whole school", html)
        self.assertIn("Withdrawn", html)
        self.assertIn(reverse("core:announcement-list"), html)
        self.assertIn("All announcements", html)

    def test_sent_list_empty_message(self):
        self.assertIn("No notices sent yet.", card_html(self.parents_page(), "notice"))

    def test_engagement_card_shows_percent_and_counts(self):
        seed_parents(self)
        html = card_html(self.parents_page(), "engagement")
        self.assertIn("50%", html)
        self.assertIn("1 of 2", html)
        self.assertIn("Students with a parent on the portal", html)
        self.assertIn("Parents who logged in this month", html)
        self.assertIn("Notice reads aren't tracked yet.", html.replace("&#x27;", "'"))
        self.assertIn(reverse("core:guardian-list"), html)

    def test_engagement_card_without_students_shows_dash(self):
        # The fixture always enrolls two students; a date past every placement leaves none.
        with mock.patch("core.views.business_today", return_value=datetime.date(2030, 1, 1)):
            html = card_html(self.parents_page(), "engagement")
        self.assertIn("&ndash;", html)
        self.assertIn("No students in a class yet", html)
        self.assertIn("No parents on the portal yet", html)
        self.assertNotIn("%", html)

    def test_missing_rows_invite_link_needs_student_and_guardian(self):
        seed_parents(self)
        html = card_html(self.parents_page(), "access")
        self.assertIn("Missing a parent on the portal", html)
        self.assertIn("1 of 2 students", html)
        invite = f'{reverse("core:student-list")}?section={self.section.pk}&amp;chip=no_portal'
        self.assertIn(invite, html)
        self.assertIn("Invite", html)
        # Without view_guardian the per-section counts are hidden altogether.
        client = self.viewer("no-invite", "view_school", "view_student", "view_guardianaccessreview")
        response = self.get(client, tab="parents")
        self.assertIsNone(response.context["parents_tab"]["missing"])
        html = card_html(response.content.decode(), "access")
        self.assertNotIn("Missing a parent on the portal", html)
        self.assertNotIn("of 2 students", html)
        self.assertNotIn("Invite", html)

    def test_missing_rows_need_view_guardian(self):
        seed_parents(self)
        plain = self.get(self.viewer("m-plain", "view_school", "view_student"), tab="parents")
        html = plain.content.decode()
        self.assertIsNone(plain.context["parents_tab"]["missing"])
        self.assertNotIn("Missing a parent on the portal", html)
        self.assertNotIn("of 2 students", html)
        guardian = self.get(self.viewer("m-guard", "view_school", "view_guardian"), tab="parents")
        self.assertIsNotNone(guardian.context["parents_tab"]["missing"])
        html = guardian.content.decode()
        self.assertIn("Missing a parent on the portal", html)
        self.assertIn("1 of 2 students", html)

    def test_access_card_hidden_without_guardian_or_review_permission(self):
        seed_parents(self)
        html = self.parents_page(self.viewer("a-plain", "view_school"))
        self.assertNotIn("erp-card--access", html)
        self.assertIn("erp-card--engagement", html)

    def test_parents_tab_computes_placements_once(self):
        from core import home_parents

        with mock.patch.object(home_parents, "_placements", wraps=home_parents._placements) as spy:
            self.parents_page()
        self.assertEqual(spy.call_count, 1)

    def test_missing_empty_messages(self):
        with mock.patch("core.views.business_today", return_value=datetime.date(2030, 1, 1)):
            html = card_html(self.parents_page(), "access")
        self.assertIn("No students in a class yet.", html)
        add_portal_parent(self, self.s1, "Rajesh Rao", "p1")
        add_portal_parent(self, self.s2, "Meena Parent", "p2")
        html = card_html(self.parents_page(), "access")
        self.assertIn("Every student in a class has a parent on the portal.", html)

    def test_reviews_need_view_guardianaccessreview(self):
        seed_parents(self)
        plain = self.get(self.viewer("plain-parents", "view_school"), tab="parents")
        self.assertIsNone(plain.context["parents_tab"]["reviews"])
        self.assertNotIn("Access reviews", plain.content.decode())
        self.assertIn("Access reviews", self.parents_page())

    def test_review_names_need_student_and_guardian(self):
        seed_parents(self)
        client = self.viewer("reviewer", "view_school", "view_guardianaccessreview")
        response = self.get(client, tab="parents")
        reviews = response.context["parents_tab"]["reviews"]
        self.assertIsNone(reviews["rows"])
        html = card_html(response.content.decode(), "access")
        self.assertIn("1 waiting", html)
        self.assertIn(reverse("core:guardian-access-reviews"), html)
        self.assertNotIn("Leaver Lal", html)
        self.assertIn("Leaver Lal", card_html(self.parents_page(), "access"))

    def test_no_reviews_waiting_message(self):
        html = card_html(self.parents_page(), "access")
        self.assertIn("No access reviews waiting.", html)

    def test_review_rows_link_to_decide_with_add_permission(self):
        seed_parents(self)
        decide = reverse("core:guardian-access-review-decide", args=[self.review_grant.pk])
        self.assertIn(decide, card_html(self.parents_page(), "access"))
        client = self.viewer(
            "no-add", "view_school", "view_guardianaccessreview", "view_student", "view_guardian"
        )
        html = card_html(self.parents_page(client), "access")
        self.assertNotIn(decide, html)
        self.assertIn(reverse("core:guardian-access-reviews"), html)

    def test_notice_card_permissions(self):
        seed_parents(self)
        html = self.parents_page(self.viewer("p-plain", "view_school"))
        self.assertNotIn("erp-card--notice", html)
        self.assertIn("erp-analytics--no-notice", html)
        self.assertNotIn("data-erp-audience-form", html)
        add_only = self.parents_page(self.viewer("p-add", "view_school", "add_announcement"))
        self.assertIn("data-erp-audience-form", add_only)
        self.assertNotIn("Sports day", add_only)
        self.assertNotIn("erp-analytics--no-notice", add_only)
        view_only = self.parents_page(self.viewer("p-view", "view_school", "view_announcement"))
        self.assertIn("Sports day", view_only)
        self.assertNotIn("data-erp-audience-form", view_only)

    def test_parents_tab_queries_do_not_grow_with_sections(self):
        seed_parents(self)
        self.parents_page()
        with CaptureQueriesContext(connection) as before:
            self.parents_page()
        for i in range(5):
            grade = ClassGrade.objects.create(name=f"Grade {i + 5}")
            section = Section.objects.create(class_grade=grade, name="A")
            first = self.enroll_student(f"Extra A{i}", grade, section)
            self.enroll_student(f"Extra B{i}", grade, section)
            add_portal_parent(self, first, f"Extra Parent {i}", f"extra-parent{i}")
        with CaptureQueriesContext(connection) as after:
            self.parents_page()
        self.assertEqual(len(before), len(after))

    def test_tab_bar_markup_and_phone_css(self):
        from pathlib import Path

        from django.conf import settings

        html = self.get().content.decode()
        self.assertIn('<nav class="erp-home-tabs" aria-label="Overview sections">', html)
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.erp-home-tab \{[^}]*min-height: 2\.75rem")

    def test_today_cards_in_order(self):
        html = self.get().content.decode()
        positions = [
            html.index(f'id="{anchor}"')
            for anchor in (
                "glance-title", "att-today-title", "compliance-title", "assess-title", "bday-title",
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_not_taken_row_shows_teacher_and_open_link(self):
        self.day(TODAY, {self.s1: P, self.s2: A}, submit=False)
        response = self.get()
        self.assertContains(response, "Not taken yet")
        row = response.context["today"]["attendance"]["not_taken"][0]
        self.assertContains(response, f"{row['class_name']} {row['section_name']}")
        self.assertContains(response, f'href="{row["url"]}">Open')

    def test_all_registers_in_message(self):
        self.day(TODAY, {self.s1: P, self.s2: A})
        self.assertContains(self.get(), "All registers are in.")

    def test_before_cutoff_shows_due_by_line(self):
        from unittest import mock

        from django.utils import timezone

        early = timezone.make_aware(datetime.datetime.combine(TODAY, datetime.time(9, 0)))
        with mock.patch("django.utils.timezone.now", return_value=early):
            response = self.get()
        self.assertContains(response, "Registers are due by 10:00.")
        self.assertNotContains(response, "Not submitted yet")

    def test_non_school_day_has_no_due_by_line(self):
        from unittest import mock

        from django.utils import timezone

        saturday = datetime.date(2026, 7, 18)
        early = timezone.make_aware(datetime.datetime.combine(saturday, datetime.time(9, 0)))
        with (
            mock.patch("django.utils.timezone.now", return_value=early),
            mock.patch("core.views.business_today", return_value=saturday),
            mock.patch("core.reports.business_today", return_value=saturday),
        ):
            response = self.get()
        self.assertContains(response, "No school day today.")
        self.assertNotContains(response, "Registers are due by")
        self.assertNotContains(response, "Everyone is on time.")
        self.assertContains(response, "Nothing to check today.")

    def test_compliance_hidden_without_register_permission(self):
        response = self.get(self.viewer("no-reg", "view_school"))
        self.assertNotContains(response, "Teacher compliance")
        self.assertNotContains(response, "Not taken yet")

    def test_home_card_css_is_pinned(self):
        from pathlib import Path

        from django.conf import settings

        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-home-tabs {", css)
        self.assertIn('.erp-home-tab[aria-current="page"]', css)
        self.assertIn(".erp-home-grid {", css)
        self.assertRegex(css, r"@media \(min-width: 992px\) \{ \.erp-home-grid \{ grid-template-columns: repeat\(2")

    def _add_sections(self, count):
        from core.models import ClassGrade, Section

        for i in range(count):
            grade = ClassGrade.objects.create(name=f"Grade {20 + i}")
            section = Section.objects.create(class_grade=grade, name="A")
            self.enroll_student(f"Fold Pupil {i}", grade, section)

    def test_not_taken_list_folds_after_five(self):
        self._add_sections(6)  # plus Grade 1 = 7 sections, none submitted
        html = self.get().content.decode()
        card = html.split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 7)
        self.assertEqual(card.count("<details"), 1)
        self.assertIn("Show all 7 classes", card)
        visible = card.split("<details", 1)[0]
        self.assertEqual(visible.count('class="erp-home-row"'), 5)

    def test_not_taken_list_does_not_fold_at_five_or_fewer(self):
        self._add_sections(4)  # 5 sections in all
        card = self.get().content.decode().split('id="att-today-title"', 1)[1].split('id="compliance-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 5)
        self.assertNotIn("<details", card)

    def _week_assessments(self, count):
        from core.models import Assessment

        for i in range(count):
            a = self.assessment({}, name=f"Quiz {i}", finalize=False)
            Assessment.objects.filter(pk=a.pk).update(assessment_date=TODAY)

    def test_assessments_fold_after_five(self):
        self._week_assessments(7)
        html = self.get().content.decode()
        card = html.split('id="assess-title"', 1)[1].split('id="bday-title"', 1)[0]
        self.assertEqual(card.count('class="erp-home-row"'), 7)
        self.assertEqual(card.count("<details"), 1)
        self.assertIn("Show all 7 assessments", card)
        self.assertEqual(card.split("<details", 1)[0].count('class="erp-home-row"'), 5)

    def test_birthdays_fold_after_five(self):
        Student.objects.filter(pk=self.s1.student_id).update(date_of_birth=datetime.date(2015, 7, 14))
        for i in range(6):
            self.enroll_student(f"Born Pupil {i}", self.class_grade, self.section)
        Student.objects.update(date_of_birth=datetime.date(2015, 7, 14))
        html = self.get().content.decode()
        card = html.split('id="bday-title"', 1)[1]
        self.assertGreaterEqual(card.count('class="erp-home-row"'), 6)
        self.assertEqual(card.count("<details"), 1)
        self.assertRegex(card, r"Show all \d+ birthdays")
        self.assertEqual(card.split("<details", 1)[0].count('class="erp-home-row"'), 5)

    def test_overdue_marks_hidden_without_view_assessment(self):
        response = self.get(self.viewer("regs-only", "view_school", "view_attendanceregister"))
        self.assertContains(response, "Teacher compliance")
        self.assertNotContains(response, "Marks overdue")


    def seed_attendance(self):
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})

    def four_classes(self):
        from core.models import ClassGrade, Section

        for i in range(2, 5):
            grade = ClassGrade.objects.create(name=f"Grade {i}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Class Pupil {i}", grade, section)
            self.day(datetime.date(2026, 7, 2), {student: P}, section=section, class_grade=grade)

    def test_attendance_cards_in_order(self):
        self.seed_attendance()
        html = self.get(tab="attendance").content.decode()
        order = [html.index(t) for t in ("Attendance this month", "Attendance heatmap", "Day of the week", "Absentees")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("Best and worst classes", html)  # one class only

    def test_absentee_switch_links_and_current(self):
        self.seed_attendance()
        month = self.get(tab="attendance").content.decode()
        self.assertIn('href="?tab=attendance&amp;absent=term"', month)
        self.assertRegex(month, r'<a class="erp-seg-link" href="\?tab=attendance" aria-current="page">This month</a>')
        term = self.get(tab="attendance", absent="term")
        self.assertEqual(term.context["attendance_tab"]["absent_view"], "term")
        self.assertContains(term, "Meena Das")
        self.assertContains(term, '<span class="erp-home-meta">0.0%</span>')
        self.assertNotContains(term, "days absent")
        self.assertContains(self.get(tab="attendance"), '<span class="erp-home-meta">6 days absent</span>')
        self.assertEqual(self.get(tab="attendance", absent="x").context["attendance_tab"]["absent_view"], "month")

    def test_no_names_in_either_absentee_view_without_view_student(self):
        self.seed_attendance()
        client = self.viewer("att-only", "view_school", "view_attendanceentry")
        for view in ("month", "term"):
            response = self.get(client, tab="attendance", absent=view)
            self.assertNotContains(response, "Meena Das")
            self.assertNotContains(response, "erp-seg")
            self.assertContains(response, "erp-analytics--no-absent")

    def test_class_links_need_view_classgrade(self):
        self.seed_attendance()
        self.four_classes()
        self.assertContains(self.get(tab="attendance"), "erp-class-link")
        client = self.viewer("no-classes", "view_school", "view_attendanceentry", "view_student")
        response = self.get(client, tab="attendance")
        self.assertContains(response, "Best and worst classes")
        self.assertNotContains(response, "erp-class-link")

    def test_attendance_tab_queries_do_not_grow_with_classes(self):
        self.seed_attendance()
        self.four_classes()
        self.get(tab="attendance")
        with CaptureQueriesContext(connection) as before:
            self.get(tab="attendance")
        from core.models import ClassGrade, Section

        for i in range(5, 8):
            grade = ClassGrade.objects.create(name=f"Grade {i}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Class Pupil {i}", grade, section)
            self.day(datetime.date(2026, 7, 2), {student: P}, section=section, class_grade=grade)
        with CaptureQueriesContext(connection) as after:
            self.get(tab="attendance")
        self.assertEqual(len(before), len(after))

    def test_capped_absentee_list_does_not_say_show_all(self):
        extra = [self.enroll_student(f"Many Absent {i}", self.class_grade, self.section) for i in range(11)]
        for d in (1, 2, 3):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A, **{s: A for s in extra}})
        html = self.get(tab="attendance").content.decode()
        self.assertNotIn("Show all", html)
        self.assertIn("Show 5 more students", html)
        self.assertIn("Showing 10 of 12.", html)

    def test_absentee_row_omits_class_when_empty(self):
        from django.template.loader import render_to_string

        row = {"student_id": 1, "name": "No Class", "class_name": "", "absent_days": 3}
        html = render_to_string("partials/home/_absentee_row.html", {"r": row, "view": "month"})
        self.assertIn("No Class", html)
        self.assertNotIn("&middot;", html)

    def test_min_days_comes_from_context(self):
        from core import analytics

        self.seed_attendance()
        context = self.get(tab="attendance", absent="term").context["attendance_tab"]
        self.assertEqual(context["low_min_days"], analytics.LOW_ATTENDANCE_MIN_DAYS)
        self.assertContains(self.get(tab="attendance", absent="term"), f"({analytics.LOW_ATTENDANCE_MIN_DAYS} or more days marked)")

    def test_attendance_card_css_is_pinned(self):
        css = Path(settings.BASE_DIR, "static/css/erp.css").read_text(encoding="utf-8")
        for rule in ('.erp-seg-link[aria-current="page"]', ".erp-trend-figure",
                     ".erp-home .erp-analytics > .erp-card--trend { grid-column: span 12; }",
                     ".erp-home .erp-analytics > .erp-card--heat { grid-column: span 7; }",
                     ".erp-home .erp-analytics > .erp-card--weekday { grid-column: span 5; }",
                     ".erp-home .erp-analytics > .erp-card--absent { grid-column: span 6;",
                     ".erp-home .erp-analytics--no-classes > .erp-card--absent { grid-column: span 12; }",
                     ".erp-home .erp-analytics--no-absent > .erp-card--classes { grid-column: span 12; }"):
            self.assertIn(rule, css)

    def test_parents_css(self):
        css = Path(settings.BASE_DIR, "static", "css", "erp.css").read_text(encoding="utf-8")
        self.assertIn(".erp-stage-list--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }", css)
        self.assertRegex(css, r"\.erp-stage-meta \{[^}]*font-size: var\(--erp-text-sm\)")
        self.assertIn(".erp-home .erp-analytics > .erp-card--notice { grid-column: span 7; grid-row: span 2; }", css)
        self.assertIn(".erp-home .erp-analytics > .erp-card--engagement { grid-column: span 5; align-self: start; }", css)
        self.assertIn(".erp-home .erp-analytics > .erp-card--access { grid-column: span 5; align-self: start; }", css)
        self.assertIn(".erp-home .erp-analytics--no-notice > .erp-card--engagement { grid-column: span 12; }", css)
        self.assertIn(".erp-home .erp-analytics--no-notice > .erp-card--access { grid-column: span 12; }", css)
        self.assertIn(".erp-notice-form .erp-field { margin-bottom: 0; }", css)
        self.assertIn(".erp-home .erp-analytics--parents { grid-template-rows: auto 1fr; }", css)


class AcademicsTabTests(MarksFixture, TestCase):
    url = reverse("core:admin-overview") + "?tab=academics"
    CARDS = ("results", "pass", "best", "subjects", "attention", "improvers")

    def viewer(self, username, *codenames):
        user = get_user_model().objects.create_user(username=username, password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=username, password="pass-12345")
        return client

    def page(self, client=None):
        response = (client or self.administrator).get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_academics_cards_in_spec_order(self):
        seed_academics(self)
        html = self.page()
        positions = [html.index(f"erp-card--{name}") for name in self.CARDS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), 6)
        self.assertNotIn("erp-analytics--no-", html)

    def test_ready_draft_is_listed_with_open_link(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("Ready to finalize", card)
        self.assertIn("Draft ready", card)
        pk = Assessment.objects.get(name="Draft ready").pk
        self.assertIn(reverse("core:assessment-detail", args=[pk]), card)

    def test_in_progress_count_link_has_a_screen_reader_name(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("assessments with marking in progress</span></a>", card)

    def test_at_risk_empty_text_with_a_previous_term_and_no_pass_marks(self):
        self.assessment({self.s1: 15}, term=self.term_a)
        self.assessment({self.s1: 15})
        card = card_html(self.page(), "attention")
        self.assertIn(
            "No pass marks are set for Term 2, and nobody's average is down 10+ points.", card
        )

    def test_stage_counts_and_labels(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        self.assertIn("Results to finish, Term 2", card)
        for label in ("Marking in progress", "Ready to finalize", "Finalized, not published"):
            self.assertIn(label, card)
        self.assertEqual(card.count('class="erp-stage"'), 3)
        self.assertIn("status=DRAFT", card)

    def test_unpublished_section_has_publish_link(self):
        seed_academics(self)
        card = card_html(self.page(), "results")
        link = reverse("core:term-publication", args=[self.term_b.pk]) + f"?section={self.section.pk}"
        self.assertIn(link, card)
        self.assertIn(">Publish<", card.replace("Publish<span", "Publish<"))
        self.assertIn("To publish", card)

    def test_nothing_to_finish_says_so(self):
        self.assessment({self.s1: 15, self.s2: 10}, name="Done")
        self.assertIn("Finalized, not published", card_html(self.page(), "results"))
        StudentResult.objects.all().delete()
        Assessment.objects.all().delete()
        self.assertIn("Nothing to finish for Term 2.", card_html(self.page(), "results"))

    def test_without_publication_permission_no_publish_rows(self):
        seed_academics(self)
        link = reverse("core:term-publication", args=[self.term_b.pk])
        self.assertIn(link, card_html(self.page(), "results"))
        client = self.viewer("no-pub", "view_school", "view_assessment", "view_studentresult")
        card = card_html(self.page(client), "results")
        self.assertIn("Finalized, not published", card)
        self.assertNotIn("To publish", card)
        self.assertNotIn(link, card)

    def test_without_assessment_permission_no_results_card(self):
        seed_academics(self)
        self.assertIn("erp-card--results", self.page())
        client = self.viewer("no-assess", "view_school", "view_studentresult")
        html = self.page(client)
        self.assertNotIn("erp-card--results", html)
        self.assertNotIn("Draft ready", html)
        self.assertIn("erp-card--subjects", html)

    def test_without_student_permission_no_names_and_no_name_cards(self):
        seed_academics(self)
        name = self.s1.student.full_name
        full = self.page()
        self.assertIn("erp-card--attention", full)
        self.assertIn("erp-card--improvers", full)
        self.assertIn(name, full)
        client = self.viewer(
            "no-students", "view_school", "view_assessment", "view_studentresult",
            "view_attendanceentry", "view_classgrade",
        )
        html = self.page(client)
        self.assertNotIn("erp-card--attention", html)
        self.assertNotIn("erp-card--improvers", html)
        self.assertNotIn(name, html)
        self.assertNotIn(self.s2.student.full_name, html)
        self.assertIn("erp-analytics--no-attention", html)
        self.assertIn("erp-analytics--no-improvers", html)

    def test_class_rows_link_only_with_classgrade_permission(self):
        seed_academics(self)
        link = reverse("core:class-grade-detail", args=[self.class_grade.pk])
        full = self.page()
        self.assertIn(link, card_html(full, "pass"))
        client = self.viewer("no-classes", "view_school", "view_studentresult")
        html = self.page(client)
        self.assertIn("Grade 1", card_html(html, "pass"))
        self.assertNotIn(link, html)
        self.assertNotIn("erp-class-link", html)

    def test_class_rows_show_pass_rate_and_grades(self):
        seed_academics(self)
        Assessment.objects.filter(status=Assessment.Status.FINALIZED).update(
            grading_snapshot={"scale": "S", "bands": [["80", "A"], ["50", "B"], ["0", "C"]]}
        )
        card = card_html(self.page(), "pass")
        self.assertIn("Pass rate and grades by class, Term 2", card)
        self.assertIn("Pass rate 100%", card)
        self.assertIn("Pass rate 100% &middot; A 2 · B 2", card)

    def test_no_pass_mark_says_so(self):
        self.assessment({self.s1: 15, self.s2: 10})
        card = card_html(self.page(), "pass")
        self.assertIn("No pass mark set", card)
        self.assertNotIn("Pass rate 0%", card)

    def test_first_term_says_no_comparison_yet(self):
        for n in (1, 2):
            self.assessment({self.s1: 15, self.s2: 10}, name=f"Only {n}", pass_mark=10)
        html = self.page()
        self.assertIn("No comparison yet", card_html(html, "subjects"))
        self.assertIn("No comparison yet", card_html(html, "improvers"))

    def test_improver_row_and_subject_change_words(self):
        seed_academics(self)
        html = self.page()
        improvers = card_html(html, "improvers")
        self.assertIn(self.s1.student.full_name, improvers)
        self.assertIn("Up 40 points (50% \u2192 90%)", improvers)
        self.assertIn(reverse("core:student-detail", args=[self.s1.student_id]), improvers)
        self.assertIn("Change since Term 1", card_html(html, "subjects"))

    def test_marks_cards_name_the_reporting_term(self):
        for n in (1, 2):
            self.assessment({self.s1: 15, self.s2: 10}, name=f"Old {n}", term=self.term_a)
        self.assessment({self.s1: 15}, name="Open draft", term=self.term_b, finalize=False)
        html = self.page()
        self.assertIn("Results to finish, Term 2", card_html(html, "results"))
        self.assertIn("by class, Term 1", card_html(html, "pass"))
        self.assertIn("Subjects, Term 1", card_html(html, "subjects"))

    def test_falling_threshold_is_ten_points(self):
        for term, a, b in ((self.term_a, 80, 80), (self.term_b, 70, 70.1)):
            for n in (1, 2):
                self.assessment({self.s1: a, self.s2: b}, name=f"Cut {n}", term=term, maximum="100")
        context = self.administrator.get(self.url).context["academics_tab"]
        names = [r["name"] for r in context["attention"]["rows"]]
        self.assertIn(self.s1.student.full_name, names)  # exactly -10.0
        self.assertNotIn(self.s2.student.full_name, names)  # -9.9
        self.assertIn("Average down 10 points since Term 1", card_html(self.page(), "attention"))

    def test_academics_query_count_does_not_grow(self):
        seed_academics(self, extra_classes=3)
        self.page()
        with CaptureQueriesContext(connection) as before:
            self.page()
        for i in range(3, 5):
            grade = ClassGrade.objects.create(name=f"Grade {i + 2}")
            section = Section.objects.create(class_grade=grade, name="A")
            student = self.enroll_student(f"Late Pupil {i}", grade, section)
            for term in (self.term_a, self.term_b):
                for n in (1, 2):
                    self.assessment(
                        {student: 12}, name=f"Quiz {n}", term=term, class_grade=grade,
                        section=section, pass_mark=10,
                    )
        with CaptureQueriesContext(connection) as after:
            self.page()
        self.assertEqual(len(before), len(after))

    def test_academics_css_is_pinned(self):
        css = Path(settings.BASE_DIR, "static/css/erp.css").read_text(encoding="utf-8")
        for rule in (
            ".erp-home .erp-analytics > .erp-card--results { grid-column: span 12; }",
            ".erp-home .erp-analytics > .erp-card--pass { grid-column: span 7; }",
            ".erp-home .erp-analytics > .erp-card--best { grid-column: span 5; }",
            ".erp-home .erp-analytics > .erp-card--subjects { grid-column: span 12; }",
            ".erp-home .erp-analytics > .erp-card--attention { grid-column: span 7; align-self: start; }",
            ".erp-home .erp-analytics > .erp-card--improvers { grid-column: span 5; align-self: start; }",
            ".erp-home .erp-analytics--no-best > .erp-card--pass { grid-column: span 12; }",
            ".erp-home .erp-analytics--no-attention > .erp-card--improvers { grid-column: span 12; }",
            ".erp-home .erp-analytics--no-improvers > .erp-card--attention { grid-column: span 12; }",
            ".erp-stage-list {",
            ".erp-class-note {",
        ):
            self.assertIn(rule, css)


class OverviewNoBootstrapTests(MarksFixture, TestCase):
    BANNED = ('class="btn', " btn-", "visually-hidden", "text-muted", '"progress"', "progress-bar", "mt-auto", "align-self-start")

    OLD_CARD_NAMES = ("erp-home-card", "erp-chart-card", "erp-analytics-card", "erp-home-empty", "erp-analytics-empty")

    def test_overview_cards_use_erp_card(self):
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        for tab, extra in (("today", {}), ("attendance", {}), ("attendance", {"absent": "term"}), ("academics", {}), ("parents", {})):
            html = self.administrator.get(URL, {"tab": tab, **extra}).content.decode()
            body = html[html.index('class="erp-page-header'):html.index("</main>")]
            with self.subTest(tab=tab, extra=extra):
                self.assertIn("erp-card", body)
                for old in self.OLD_CARD_NAMES:
                    self.assertNotIn(old, body)

    def test_overview_uses_no_bootstrap_classes(self):
        saw_setup = False
        saw_attention = False
        for d in (1, 2, 3, 6, 7, 8):
            self.day(datetime.date(2026, 7, d), {self.s1: P, self.s2: A})
        seed_academics(self)
        seed_parents(self)
        pages = [(tab, {}) for tab in TAB_KEYS] + [("attendance", {"absent": "term"})]
        for tab, extra in pages:
            response = self.administrator.get(URL, {"tab": tab, **extra})
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            saw_setup = saw_setup or "Set up your school" in html
            saw_attention = saw_attention or "erp-stat-card--attention" in html
            # Page header to the end of main: the base shell (sidebar, top bar) may still use Bootstrap.
            body = html[html.index('class="erp-page-header'):html.index("</main>")]
            for banned in self.BANNED:
                with self.subTest(tab=tab, extra=extra, banned=banned):
                    self.assertNotIn(banned, body)
        self.assertTrue(saw_setup, "fixture should show the setup card")
