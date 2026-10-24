"""UI-D1-4C-1: Attendance Reports index, Daily absent students and Missing attendance.

Presentation only. These tests pin the page structure, permission-gated links, form
error association, the permission-aware breadcrumb trail, and that Draft / Not taken
attendance is never presented or counted as Absent. Calculations are not retested here
(core.reports has its own suites); the pages must simply render what core.reports returns.
"""

import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from core import reports
from core.breadcrumbs import breadcrumb_context
from core.models import AttendanceRegister, AttendanceStatus, SchoolCalendarDay
from core.tests.test_ui_admin_desktop_d1_4a_attendance_list import AttendanceListFixture

User = get_user_model()

MON, TUE, WED = date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)
SUN = date(2026, 7, 12)

ENTRY = "view_attendanceentry"
REGISTER = "view_attendanceregister"
STUDENT = "view_student"
SCHOOL = "view_school"


class ReportsFixture(AttendanceListFixture):
    def build_reports(self):
        self.build()  # logs the admin client in
        self.index = reverse("core:attendance-reports")
        self.absent_url = reverse("core:report-daily-absentees")
        self.missing_url = reverse("core:report-missing-attendance")

    def submitted(self, on_date, *, absent=(), present=(), notes=None):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=on_date
        )
        # A register can only be submitted with every rostered Student marked.
        unmarked = [e for e in (self.asha, self.ravi) if e not in (*absent, *present)]
        for enrollment in (*present, *unmarked):
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.PRESENT)
        for enrollment in absent:
            register.save_draft_entry(
                enrollment=enrollment,
                status=AttendanceStatus.ABSENT,
                absence_note=(notes or {}).get(enrollment.pk, ""),
            )
        register.submit(actor=self.admin)
        return register

    def draft(self, on_date, section=None, *, absent=()):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6,
            section=section or self.six_a, date=on_date,
        )
        for enrollment in absent:
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.ABSENT)
        return register

    def user_with(self, *codenames):
        self._viewers = getattr(self, "_viewers", 0) + 1
        user = User.objects.create_user(
            username=f"u{self._viewers}-" + "-".join(codenames), password="pass-12345"
        )
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        return user

    def client_with(self, *codenames):
        user = self.user_with(*codenames)
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return client


def table_html(content, label):
    """The scroll region labelled `label`, up to its closing </section>."""
    return content.split(f'aria-label="{label}"')[1].split("</section>")[0]


def breadcrumb_nav(content):
    if 'aria-label="Breadcrumb"' not in content:
        return ""
    return content.split('aria-label="Breadcrumb"')[1].split("</nav>")[0]


def breadcrumb_labels(content):
    nav = breadcrumb_nav(content)
    return [re.sub(r"<[^>]+>", "", item).strip() for item in re.findall(r"<li[^>]*>(.*?)</li>", nav, re.S)]


class AriaAssertions:
    def assertDescribedByResolves(self, content, field_ids):
        """Every errored field has aria-invalid and each aria-describedby token is an id."""
        for field_id in field_ids:
            tag = re.search(rf'<(?:input|select)[^>]*\bid="{field_id}"[^>]*>', content)
            self.assertIsNotNone(tag, field_id)
            self.assertIn('aria-invalid="true"', tag.group(0), field_id)
            described = re.search(r'aria-describedby="([^"]+)"', tag.group(0))
            self.assertIsNotNone(described, field_id)
            for token in described.group(1).split():
                self.assertIn(f'id="{token}"', content, f"{field_id} -> {token}")


# --- breadcrumb mechanism -----------------------------------------------------------------


class BreadcrumbMechanismTests(ReportsFixture, TestCase):
    def match(self, name, **kwargs):
        return resolve(reverse(name, kwargs=kwargs))

    def labels(self, name, user=None, **kwargs):
        ctx = breadcrumb_context(self.match(name, **kwargs), user)
        return [crumb["label"] for crumb in ctx["breadcrumbs"]], ctx["nav_section"]

    def setUp(self):
        self.build_reports()

    def test_without_a_user_existing_behaviour_is_unchanged(self):
        self.assertEqual(
            self.labels("core:student-detail", pk=7), (["Overview", "Students", "Student"], "student-list")
        )
        self.assertEqual(
            self.labels("core:report-daily-absentees"),
            (["Overview", "Attendance reports", "Daily absent students"], "attendance-reports"),
        )
        self.assertEqual(
            self.labels("core:attendance-reports"), (["Overview", "Attendance reports"], "attendance-reports")
        )

    def test_overview_crumb_requires_view_school(self):
        with_school = self.user_with(SCHOOL, ENTRY)
        without_school = self.user_with(ENTRY)
        self.assertEqual(
            self.labels("core:report-daily-absentees", with_school)[0],
            ["Overview", "Attendance reports", "Daily absent students"],
        )
        self.assertEqual(
            self.labels("core:report-daily-absentees", without_school)[0],
            ["Attendance reports", "Daily absent students"],
        )

    def test_overview_gate_applies_to_existing_rules_too(self):
        user = self.user_with(STUDENT)
        self.assertEqual(self.labels("core:student-detail", user, pk=7)[0], ["Students", "Student"])

    def test_parent_crumb_is_dropped_without_its_permission(self):
        register_only = self.user_with(SCHOOL, REGISTER)
        labels, section = self.labels("core:report-missing-attendance", register_only)
        self.assertEqual(labels, ["Overview", "Missing attendance"])
        self.assertEqual(section, "attendance-reports")

    def test_a_trail_with_only_the_current_page_is_dropped_but_keeps_the_section(self):
        for name, codename in (("core:report-missing-attendance", REGISTER), ("core:attendance-reports", ENTRY)):
            labels, section = self.labels(name, self.user_with(codename))
            self.assertEqual(labels, [], name)
            self.assertEqual(section, "attendance-reports")

    def test_unmapped_page_and_none_match_stay_empty(self):
        self.assertEqual(
            breadcrumb_context(self.match("core:subject-list"), self.user_with(SCHOOL)),
            {"breadcrumbs": [], "nav_section": None},
        )
        self.assertEqual(breadcrumb_context(None, self.user_with(SCHOOL)), {"breadcrumbs": [], "nav_section": None})

    def test_current_page_crumb_is_never_a_link(self):
        match = self.match("core:report-missing-attendance")
        crumbs = breadcrumb_context(match, self.user_with(SCHOOL, ENTRY))["breadcrumbs"]
        self.assertIsNone(crumbs[-1]["url"])


class RenderedNavigationTests(ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def active_nav(self, response):
        return [
            link["label"] for group in response.context["office_nav"]
            for link in group["links"] if link["active"]
        ]

    def test_sidebar_keeps_attendance_reports_active_on_all_three_pages(self):
        for url in (self.index, self.absent_url, self.missing_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(self.active_nav(response), ["Attendance reports"])

    def test_full_trail_for_an_administrator(self):
        content = self.client.get(self.absent_url).content.decode()
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Attendance reports", "Daily absent students"])
        self.assertIn(f'href="{self.index}"', breadcrumb_nav(content))

    def test_user_without_view_school_is_outside_the_admin_area_and_gets_no_overview_link(self):
        # The admin sidebar and trail are built only for view_school holders (user_areas), so
        # such a user sees neither, and nothing on the page links to the Overview.
        response = self.client_with(ENTRY).get(self.absent_url)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(breadcrumb_nav(content), "")
        self.assertNotIn(f'href="{reverse("core:admin-overview")}"', content)

    def test_viewer_with_school_and_entry_gets_the_full_trail(self):
        content = self.client_with(SCHOOL, ENTRY).get(self.absent_url).content.decode()
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Attendance reports", "Daily absent students"])

    def test_register_only_viewer_has_no_reports_link_in_the_missing_page_trail(self):
        content = self.client_with(SCHOOL, REGISTER).get(self.missing_url).content.decode()
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Missing attendance"])
        self.assertNotIn(f'href="{self.index}"', breadcrumb_nav(content))

    def test_register_only_viewer_without_view_school_has_no_trail_at_all(self):
        content = self.client_with(REGISTER).get(self.missing_url).content.decode()
        self.assertEqual(breadcrumb_nav(content), "")

    def test_index_trail_is_just_overview_for_an_administrator(self):
        content = self.client.get(self.index).content.decode()
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Attendance reports"])


# --- Reports index ------------------------------------------------------------------------


class ReportsIndexTests(ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def test_structure_for_an_administrator(self):
        response = self.client.get(self.index)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "erp-page-header")
        self.assertContains(response, "Percentage = Present / (Present + Absent)")
        for url_name in ("report-daily-absentees", "report-missing-attendance", "report-monthly-section"):
            self.assertContains(response, f'href="{reverse("core:" + url_name)}"')
        self.assertEqual(content.count("stretched-link"), 3)
        # The register list is a separate shortcut (page header), not a report card.
        self.assertContains(response, ">Attendance registers</a>")

    def test_entry_only_viewer_sees_no_missing_card_and_no_registers_shortcut(self):
        response = self.client_with(ENTRY).get(self.index)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{reverse("core:report-missing-attendance")}"')
        self.assertNotContains(response, f'href="{reverse("core:attendance-register-list")}"')
        self.assertEqual(response.content.decode().count("stretched-link"), 2)

    def test_entry_and_register_viewer_sees_everything(self):
        response = self.client_with(ENTRY, REGISTER).get(self.index)
        self.assertContains(response, f'href="{reverse("core:report-missing-attendance")}"')
        self.assertContains(response, f'href="{reverse("core:attendance-register-list")}"')

    def test_students_link_in_the_history_hint_needs_view_student(self):
        self.assertNotContains(self.client_with(ENTRY).get(self.index), reverse("core:student-list"))
        self.assertContains(
            self.client_with(ENTRY, STUDENT).get(self.index), f'href="{reverse("core:student-list")}"'
        )

    def test_no_invented_numbers_or_charts(self):
        content = self.client.get(self.index).content.decode().lower()
        for banned in ("<canvas", "<svg", "erp-stat"):
            self.assertNotIn(banned, content)


# --- Daily absent students ----------------------------------------------------------------


class DailyAbsenteesTests(AriaAssertions, ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def test_pristine_page_guides_without_errors_or_table(self):
        response = self.client.get(self.absent_url)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Choose a date to list the students recorded absent.")
        self.assertNotIn("form-error-summary", content)
        self.assertNotIn("<table", content)
        self.assertNotIn("No submitted absences", content)

    def test_toolbar_is_a_labelled_get_form_with_no_default_date(self):
        content = self.client.get(self.absent_url).content.decode()
        form = content.split('aria-label="Choose a date"')[0].rsplit("<form", 1)[1]
        self.assertIn('method="get"', form)
        self.assertIn("erp-toolbar", form)
        tag = content.split('aria-label="Choose a date"')[1].split("</form>")[0]
        self.assertEqual(re.findall(r'<(?:select|input)[^>]* name="(\w+)"', tag), ["date"])
        self.assertIn(">Show absent students</button>", tag)
        self.assertNotIn('value="2', tag)

    def test_results_table_structure_columns_and_note(self):
        self.submitted(MON, absent=[self.ravi], present=[self.asha], notes={self.ravi.pk: "Fever"})
        response = self.client.get(self.absent_url, {"date": MON.isoformat()})
        content = response.content.decode()
        self.assertIn('role="region" aria-label="Absent students" tabindex="0"', content)
        panel = table_html(content, "Absent students")
        self.assertIn("<caption", panel)
        self.assertEqual(
            re.findall(r'<th scope="col">([^<]+)</th>', panel), ["Section", "Student", "Absence note"]
        )
        self.assertIn("Ravi", panel)
        self.assertNotIn("Asha", panel)
        self.assertIn("Fever", panel)
        self.assertContains(response, "1 student recorded absent.")
        self.assertContains(response, "Absent on Monday, 6 July 2026")

    def test_rows_are_exactly_what_core_reports_returns(self):
        self.submitted(MON, absent=[self.ravi, self.asha])
        response = self.client.get(self.absent_url, {"date": MON.isoformat()})
        self.assertEqual(
            [entry.pk for entry in response.context["absentees"]],
            [entry.pk for entry in reports.daily_absentees(MON)],
        )

    def test_draft_register_absences_are_not_listed(self):
        self.draft(MON, absent=[self.ravi])
        response = self.client.get(self.absent_url, {"date": MON.isoformat()})
        self.assertContains(response, "No submitted absences on this date.")
        self.assertContains(response, "0 students recorded absent.")
        self.assertNotContains(response, "Ravi")

    def test_holiday_date_lists_nobody(self):
        self.submitted(TUE, absent=[self.ravi])
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=TUE, is_instructional=False, label="Holiday"
        )
        response = self.client.get(self.absent_url, {"date": TUE.isoformat()})
        self.assertEqual(list(response.context["absentees"]), [])
        self.assertContains(response, "No submitted absences on this date.")

    def test_future_date_lists_nobody(self):
        response = self.client.get(self.absent_url, {"date": "2999-01-01"})
        self.assertContains(response, "No submitted absences on this date.")

    def test_empty_date_shows_summary_and_field_errors_without_a_table(self):
        response = self.client.get(self.absent_url, {"date": ""})
        content = response.content.decode()
        self.assertContains(response, 'id="form-error-summary"')
        self.assertContains(response, 'role="alert"')
        self.assertEqual(content.count("This field is required."), 2)  # summary + field-local
        self.assertIn('href="#id_date"', content)
        self.assertDescribedByResolves(content, ["id_date"])
        self.assertNotIn("<table", content)
        self.assertNotIn("No submitted absences", content)

    def test_garbage_date_is_an_error_not_an_empty_result(self):
        content = self.client.get(self.absent_url, {"date": "not-a-date"}).content.decode()
        self.assertIn("Enter a valid date.", content)
        self.assertDescribedByResolves(content, ["id_date"])
        self.assertNotIn("<table", content)

    def test_register_detail_and_missing_links_follow_view_attendanceregister(self):
        register = self.submitted(MON, absent=[self.ravi])
        detail = reverse("core:attendance-register-detail", args=[register.pk])
        params = {"date": MON.isoformat()}
        full = self.client.get(self.absent_url, params).content.decode()
        self.assertIn(f'href="{detail}"', full)
        self.assertIn(f'href="{self.missing_url}"', full)
        content = self.client_with(ENTRY).get(self.absent_url, params).content.decode()
        self.assertNotIn(detail, content)
        self.assertNotIn(self.missing_url, content)
        self.assertIn("Missing attendance", content)  # still named, as plain text
        self.assertIn("Ravi", content)
        self.assertIn(reverse("core:student-attendance", args=[self.ravi.student_id]), content)

    def test_header_action_goes_to_the_reports_index(self):
        self.assertContains(self.client.get(self.absent_url), f'href="{self.index}"')


# --- Missing attendance -------------------------------------------------------------------


class MissingAttendanceTests(AriaAssertions, ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()
        self.window = {"start": MON.isoformat(), "end": WED.isoformat(), "section": self.six_a.pk}

    def tbody(self, response):
        return table_html(response.content.decode(), "Missing attendance").split("<tbody>")[1]

    def test_pristine_page_guides_without_errors_or_table(self):
        response = self.client.get(self.missing_url)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Choose a date range, and optionally a Section")
        self.assertNotIn("form-error-summary", content)
        self.assertNotIn("<table", content)

    def test_toolbar_fields_in_order_with_no_defaults(self):
        content = self.client.get(self.missing_url).content.decode()
        tag = content.split('aria-label="Choose a date range"')[1].split("</form>")[0]
        self.assertEqual(
            re.findall(r'<(?:select|input)[^>]* name="(\w+)"', tag), ["start", "end", "section"]
        )
        self.assertEqual(re.findall(r"<label[^>]*>([^<]+):</label>", tag), ["Start", "End", "Section"])
        self.assertNotIn('value="2', tag)
        self.assertEqual(tag.count("selected"), 1)  # only the empty "---------" Section option
        self.assertIn('<option value="" selected>', tag)

    def test_draft_and_not_taken_are_distinct_and_never_absent(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        self.draft(TUE, absent=[self.ravi])  # a saved Absent entry on a DRAFT register
        # WED has no register at all.
        body = self.tbody(self.client.get(self.missing_url, self.window))
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        self.assertEqual(len(rows), 2)
        tue, wed = rows
        self.assertIn("Tue", tue)
        self.assertIn("erp-status--draft", tue)
        self.assertIn("Draft", tue)
        self.assertIn("Open register", tue)
        self.assertIn("Wed", wed)
        self.assertIn("erp-status--neutral", wed)
        self.assertIn("Not taken", wed)
        self.assertNotIn("<a", wed)  # an unopened register has nothing to open
        self.assertNotIn("Absent", body)
        self.assertNotIn("Mon", body)  # the submitted day is not missing

    def test_rows_are_exactly_what_core_reports_returns(self):
        self.draft(TUE)
        response = self.client.get(self.missing_url, self.window)
        expected = reports.missing_attendance(MON, WED, section=self.six_a)
        self.assertEqual(
            [(row["date"], row["section"].pk, row["state"]) for row in response.context["rows"]],
            [(row["date"], row["section"].pk, row["state"]) for row in expected],
        )

    def test_holiday_and_sunday_are_never_listed(self):
        SchoolCalendarDay.objects.create(
            academic_year=self.year, date=TUE, is_instructional=False, label="Holiday"
        )
        response = self.client.get(
            self.missing_url, {"start": TUE.isoformat(), "end": SUN.isoformat(), "section": self.six_a.pk}
        )
        dates = {row["date"] for row in response.context["rows"]}
        self.assertNotIn(TUE, dates)
        self.assertNotIn(SUN, dates)
        self.assertIn(WED, dates)

    def test_empty_range_message(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        response = self.client.get(
            self.missing_url, {"start": MON.isoformat(), "end": MON.isoformat(), "section": self.six_a.pk}
        )
        self.assertContains(response, "No missing attendance in this range.")

    def test_inverted_range_is_a_non_field_error_in_the_summary_only(self):
        response = self.client.get(self.missing_url, {"start": WED.isoformat(), "end": MON.isoformat()})
        content = response.content.decode()
        self.assertEqual(content.count("Start date must not be after the end date."), 1)
        self.assertIn('id="form-error-summary"', content)
        self.assertNotIn("<table", content)
        self.assertNotIn("No missing attendance", content)

    def test_range_over_400_days_is_rejected(self):
        response = self.client.get(self.missing_url, {"start": "2026-01-01", "end": "2027-03-01"})
        self.assertContains(response, "Choose a range of at most 400 days.")
        self.assertNotContains(response, "<table")

    def test_missing_required_dates_associate_errors_with_inputs(self):
        content = self.client.get(self.missing_url, {"start": "", "end": ""}).content.decode()
        self.assertDescribedByResolves(content, ["id_start", "id_end"])
        self.assertIn('href="#id_start"', content)
        self.assertIn('href="#id_end"', content)

    def test_invalid_section_choice_associates_the_select(self):
        content = self.client.get(
            self.missing_url, {"start": MON.isoformat(), "end": WED.isoformat(), "section": "999999"}
        ).content.decode()
        self.assertIn("<select", content)
        self.assertDescribedByResolves(content, ["id_section"])
        self.assertNotIn("<table", content)

    def test_register_only_viewer_gets_register_list_action_and_plain_text_cross_link(self):
        self.draft(TUE)
        response = self.client_with(REGISTER).get(self.missing_url, self.window)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f'href="{self.index}"', content)
        self.assertNotIn(self.absent_url, content)
        self.assertIn("Daily absent students", content)  # named, not linked
        self.assertIn(f'href="{reverse("core:attendance-register-list")}"', content)
        self.assertIn("Open register", content)

    def test_viewer_with_both_permissions_links_to_reports_and_absentees(self):
        client = self.client_with(ENTRY, REGISTER)
        self.assertIn(f'href="{self.index}"', client.get(self.missing_url).content.decode())
        self.assertIn(f'href="{self.absent_url}"', client.get(self.missing_url, self.window).content.decode())


# --- phone fit and scoped CSS ---------------------------------------------------------------


class PhoneFitTests(ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def test_result_tables_fit_the_phone_instead_of_scrolling(self):
        self.submitted(MON, absent=[self.ravi])
        absent = self.client.get(self.absent_url, {"date": MON.isoformat()}).content.decode()
        missing = self.client.get(
            self.missing_url, {"start": MON.isoformat(), "end": WED.isoformat()}
        ).content.decode()
        for content in (absent, missing):
            self.assertIn('class="table erp-keep erp-attendance-report-table"', content)

    def test_report_css_is_scoped_and_precedes_the_d1_4b_and_d1_3d1_blocks(self):
        from pathlib import Path

        css = Path("static/css/erp.css").read_text(encoding="utf-8")
        start = css.index("/* UI-D1-4C-1")
        self.assertLess(start, css.index("/* UI-D1-4B"))
        self.assertLess(start, css.index("/* UI-D1-3D1 review fix"))
        block = css[start:css.index("/* UI-D1-4B")]
        for selector in re.findall(r"^\s+(\.[^{]+?)\s*(?:,|\{)", block, re.M):
            self.assertIn(".erp-attendance-report-table", selector)


# --- permissions (unchanged) ----------------------------------------------------------------


class PermissionBoundaryTests(ReportsFixture, TestCase):
    def setUp(self):
        self.build_reports()

    def test_anonymous_redirects_to_login(self):
        for url in (self.index, self.absent_url, self.missing_url):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client_class().get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )

    def test_teacher_is_forbidden(self):
        self.client.logout()
        self.client.login(username="rao", password="pass-12345")
        for url in (self.index, self.absent_url, self.missing_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_each_permission_opens_exactly_the_same_pages_as_before(self):
        urls = (self.index, self.absent_url, self.missing_url)
        entry_only = self.client_with(ENTRY)
        self.assertEqual([entry_only.get(url).status_code for url in urls], [200, 200, 403])
        register_only = self.client_with(REGISTER)
        self.assertEqual([register_only.get(url).status_code for url in urls], [403, 403, 200])
        self.assertEqual(self.client.get(self.index).status_code, 200)

    def test_pages_do_not_write(self):
        before = AttendanceRegister.objects.count()
        for url in (self.index, self.absent_url, self.missing_url):
            self.client.get(url)
        self.assertEqual(AttendanceRegister.objects.count(), before)
