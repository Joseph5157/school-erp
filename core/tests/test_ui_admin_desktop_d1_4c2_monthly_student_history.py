"""UI-D1-4C-2: Monthly Class/Section summary and Student attendance history.

Presentation only. Percentages, the em dash for "nothing reportable", the reportable rules and the
view's own filter fallback are unchanged; these tests pin the structure, the error association, the
permission-gated navigation, and the honest disclosure when a Student-history filter is not applied.
"""

import re

from django.test import TestCase
from django.urls import resolve, reverse

from core import reports
from core.breadcrumbs import breadcrumb_context
from core.models import AttendanceRegister, AttendanceStatus
from core.tests.test_ui_admin_desktop_d1_4c1_attendance_reports import (
    ENTRY,
    MON,
    REGISTER,
    SCHOOL,
    STUDENT,
    TUE,
    WED,
    AriaAssertions,
    ReportsFixture,
    breadcrumb_labels,
    breadcrumb_nav,
    table_html,
)


class C2Fixture(ReportsFixture):
    def build_c2(self):
        self.build_reports()
        self.monthly = reverse("core:report-monthly-section")
        self.history = reverse("core:student-attendance", args=[self.ravi.student_id])
        self.params = {"section": self.six_a.pk, "month": "2026-07"}


# --- breadcrumbs --------------------------------------------------------------------------


class C2BreadcrumbTests(C2Fixture, TestCase):
    def setUp(self):
        self.build_c2()

    def labels(self, name, user=None, **kwargs):
        ctx = breadcrumb_context(resolve(reverse(name, kwargs=kwargs)), user)
        return [crumb["label"] for crumb in ctx["breadcrumbs"]], ctx["nav_section"]

    def test_monthly_trail(self):
        self.assertEqual(
            self.labels("core:report-monthly-section"),
            (["Overview", "Attendance reports", "Monthly summary"], "attendance-reports"),
        )
        self.assertEqual(
            self.labels("core:report-monthly-section", self.user_with(ENTRY))[0],
            ["Attendance reports", "Monthly summary"],
        )
        self.assertEqual(
            self.labels("core:report-monthly-section", self.user_with(SCHOOL, ENTRY))[0],
            ["Overview", "Attendance reports", "Monthly summary"],
        )

    def test_student_history_keeps_its_logical_parents_only_for_view_student(self):
        pk = self.ravi.student_id
        self.assertEqual(
            self.labels("core:student-attendance", pk=pk),
            (["Overview", "Students", "Student", "Attendance"], "student-list"),
        )
        self.assertEqual(
            self.labels("core:student-attendance", self.user_with(SCHOOL, ENTRY, STUDENT), pk=pk)[0],
            ["Overview", "Students", "Student", "Attendance"],
        )
        # Without view_student the parents are left out rather than linking to a 403.
        self.assertEqual(
            self.labels("core:student-attendance", self.user_with(SCHOOL, ENTRY), pk=pk)[0],
            ["Overview", "Attendance"],
        )
        self.assertEqual(self.labels("core:student-attendance", self.user_with(ENTRY), pk=pk)[0], [])

    def test_student_crumb_reuses_the_page_pk(self):
        pk = self.ravi.student_id
        ctx = breadcrumb_context(
            resolve(reverse("core:student-attendance", args=[pk])), self.user_with(SCHOOL, STUDENT)
        )
        self.assertEqual(ctx["breadcrumbs"][2]["url"], reverse("core:student-detail", args=[pk]))
        self.assertIsNone(ctx["breadcrumbs"][-1]["url"])

    def test_rendered_trails_and_active_sidebar(self):
        content = self.client.get(self.monthly).content.decode()
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Attendance reports", "Monthly summary"])
        response = self.client.get(self.history)
        self.assertEqual(
            breadcrumb_labels(response.content.decode()), ["Overview", "Students", "Student", "Attendance"]
        )

        def active(resp):
            return [
                link["label"] for group in resp.context["office_nav"]
                for link in group["links"] if link["active"]
            ]

        self.assertEqual(active(self.client.get(self.monthly)), ["Attendance reports"])
        self.assertEqual(active(response), ["Students"])

    def test_rendered_history_trail_has_no_student_links_without_view_student(self):
        content = self.client_with(SCHOOL, ENTRY).get(self.history).content.decode()
        nav = breadcrumb_nav(content)
        self.assertEqual(breadcrumb_labels(content), ["Overview", "Attendance"])
        self.assertNotIn(reverse("core:student-list"), nav)
        self.assertNotIn(reverse("core:student-detail", args=[self.ravi.student_id]), nav)


# --- Monthly summary ----------------------------------------------------------------------


class MonthlySummaryTests(AriaAssertions, C2Fixture, TestCase):
    def setUp(self):
        self.build_c2()

    def test_pristine_page_guides_without_errors_or_table(self):
        response = self.client.get(self.monthly)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertContains(response, "Choose a Section and a month to see the summary.")
        self.assertNotIn("form-error-summary", content)
        self.assertNotIn("<table", content)

    def test_toolbar_fields_labels_and_no_defaults(self):
        content = self.client.get(self.monthly).content.decode()
        form = content.split('aria-label="Choose a Section and month"')[0].rsplit("<form", 1)[1]
        self.assertIn('method="get"', form)
        self.assertIn("erp-toolbar erp-toolbar--inline erp-attendance-report-toolbar", form)
        tag = content.split('aria-label="Choose a Section and month"')[1].split("</form>")[0]
        self.assertEqual(re.findall(r'<(?:select|input)[^>]* name="(\w+)"', tag), ["section", "month"])
        self.assertEqual(re.findall(r"<label[^>]*>([^<]+):</label>", tag), ["Section", "Month"])
        self.assertIn(">Show summary</button>", tag)
        self.assertNotIn('value="2', tag)
        self.assertEqual(tag.count('class="erp-required-mark"'), 2)

    def test_results_structure_values_and_context(self):
        self.submitted(MON, absent=[self.ravi], present=[self.asha])
        response = self.client.get(self.monthly, self.params)
        content = response.content.decode()
        panel = table_html(content, "Monthly attendance by Student")
        self.assertIn('role="region" aria-label="Monthly attendance by Student" tabindex="0"', content)
        self.assertIn("<caption", panel)
        self.assertEqual(
            re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', panel),
            ["Student", "Present", "Absent", "Attendance %"],
        )
        self.assertEqual(content.count("<h1"), 1)
        self.assertIn("100.0%", panel)  # Asha
        self.assertIn("0.0%", panel)  # Ravi
        self.assertIn("50.0%", panel.split("<tfoot>")[1])  # total
        self.assertContains(response, "July 2026")
        expected = reports.monthly_section_summary(self.six_a, 2026, 7)
        self.assertEqual(response.context["summary"]["totals"], expected["totals"])
        self.assertEqual(
            [r["student"].pk for r in response.context["summary"]["rows"]],
            [r["student"].pk for r in expected["rows"]],
        )

    def test_the_three_day_counts_are_the_reports_values(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        self.draft(TUE, absent=[self.ravi])  # a Draft register: not submitted
        response = self.client.get(self.monthly, self.params)
        totals = response.context["summary"]["totals"]
        content = response.content.decode()
        for value, label in (
            (totals["expected_days"], "Days attendance was expected"),
            (totals["submitted_days"], "Registers submitted"),
            (totals["missing_days"], "Missing or draft"),
        ):
            self.assertRegex(content, rf"{label}</dt><dd class=\"h5 mb-0\">{value}</dd>")
        self.assertEqual(totals["submitted_days"], 1)

    def test_draft_absence_is_not_counted(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        self.draft(TUE, absent=[self.ravi])
        response = self.client.get(self.monthly, self.params)
        rows = {row["student"].full_name: row for row in response.context["summary"]["rows"]}
        self.assertEqual(rows["Ravi"]["absent"], 0)
        self.assertEqual(rows["Ravi"]["percentage"], 100.0)

    def test_nothing_reportable_shows_a_dash_with_a_legend_not_zero_percent(self):
        response = self.client.get(self.monthly, self.params)  # no registers at all
        content = response.content.decode()
        panel = table_html(content, "Monthly attendance by Student")
        self.assertIn(
            '<span aria-hidden="true">&mdash;</span><span class="visually-hidden">No reportable attendance</span>',
            panel,
        )
        self.assertNotIn("0.0%", panel)
        self.assertContains(response, "It is not 0% and not absent.")
        self.assertIsNone(response.context["summary"]["totals"]["percentage"])

    def test_a_student_with_only_a_draft_register_shows_a_dash(self):
        self.draft(MON, absent=[self.ravi])
        panel = table_html(
            self.client.get(self.monthly, self.params).content.decode(), "Monthly attendance by Student"
        )
        self.assertNotIn("0.0%", panel)
        self.assertIn("&mdash;", panel)

    def test_no_enrolled_students_message(self):
        response = self.client.get(self.monthly, {"section": self.six_a.pk, "month": "2026-05"})
        self.assertContains(response, "No Students enrolled in this Section during this month.")

    def test_student_links_go_to_student_history(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        content = self.client.get(self.monthly, self.params).content.decode()
        self.assertIn(f'href="{reverse("core:student-attendance", args=[self.ravi.student_id])}"', content)

    def test_missing_fields_show_summary_and_associated_errors(self):
        response = self.client.get(self.monthly, {"section": "", "month": ""})
        content = response.content.decode()
        self.assertContains(response, 'id="form-error-summary"')
        self.assertDescribedByResolves(content, ["id_section", "id_month"])
        self.assertIn('href="#id_section"', content)
        self.assertIn('href="#id_month"', content)
        self.assertNotIn("<table", content)

    def test_bad_month_and_unknown_section(self):
        bad_month = self.client.get(self.monthly, {"section": self.six_a.pk, "month": "bad"}).content.decode()
        self.assertIn("Enter a month as YYYY-MM.", bad_month)
        self.assertDescribedByResolves(bad_month, ["id_month"])  # help text id and error id both resolve
        self.assertNotIn("<table", bad_month)
        bad_section = self.client.get(
            self.monthly, {"section": "999999", "month": "2026-07"}
        ).content.decode()
        self.assertDescribedByResolves(bad_section, ["id_section"])
        self.assertNotIn("<table", bad_section)

    def test_permissions_unchanged(self):
        self.assertEqual(self.client_with(ENTRY).get(self.monthly).status_code, 200)
        self.assertEqual(self.client_with(REGISTER).get(self.monthly).status_code, 403)
        self.assertRedirects(
            self.client_class().get(self.monthly),
            f"{reverse('login')}?next={self.monthly}",
            fetch_redirect_response=False,
        )
        self.client.logout()
        self.client.login(username="rao", password="pass-12345")
        self.assertEqual(self.client.get(self.monthly).status_code, 403)


# --- Student history ----------------------------------------------------------------------


class StudentHistoryTests(AriaAssertions, C2Fixture, TestCase):
    NOT_APPLIED = "The date filter was not applied; showing all recorded attendance."

    def setUp(self):
        self.build_c2()
        self.submitted(MON, absent=[self.ravi], present=[self.asha], notes={self.ravi.pk: "Fever"})
        self.submitted(TUE, present=[self.asha, self.ravi])
        self.draft(WED, absent=[self.ravi])  # on a DRAFT register: listed, never counted

    def test_first_load_is_unfiltered_and_unflagged(self):
        response = self.client.get(self.history)
        content = response.content.decode()
        self.assertEqual(content.count("<h1"), 1)
        self.assertEqual(len(response.context["entries"]), 3)
        self.assertNotIn(self.NOT_APPLIED, content)
        self.assertNotIn("form-error-summary", content)
        self.assertNotIn("Summary:", content)
        self.assertNotIn("Clear filter", content)
        self.assertFalse(response.context["form"].is_bound)

    def test_summary_values_and_percentage_are_the_reports_values(self):
        response = self.client.get(self.history)
        expected = reports.student_summary(self.ravi.student)
        self.assertEqual(response.context["total"], expected["total"])
        self.assertEqual(response.context["percentage"], expected["percentage"])
        self.assertContains(response, "50.0%")
        self.assertEqual(expected["total"], 2)  # the Draft Absent is not counted

    def test_history_table_columns_status_badges_and_note(self):
        response = self.client.get(self.history)
        content = response.content.decode()
        panel = table_html(content, "Attendance history")
        self.assertIn('role="region" aria-label="Attendance history" tabindex="0"', content)
        self.assertIn("<caption", panel)
        self.assertEqual(
            re.findall(r'<th scope="col">([^<]+)</th>', panel),
            ["Date", "Academic year", "Section", "Register", "Status", "Absence note"],
        )
        self.assertIn("erp-status--draft", panel)
        self.assertIn("erp-status--submitted", panel)
        self.assertIn("Fever", panel)
        self.assertContains(response, "listed here may not be counted")
        self.assertContains(response, "on submitted registers, on instructional dates")

    def test_draft_only_student_shows_dash_not_zero(self):
        _, enrollment = self.make_student("Draft Only", section=self.six_b)
        self.draft(MON, section=self.six_b, absent=[enrollment])
        response = self.client.get(reverse("core:student-attendance", args=[enrollment.student_id]))
        self.assertIsNone(response.context["percentage"])
        content = response.content.decode()
        self.assertIn('<span class="visually-hidden">No reportable attendance</span>', content)
        self.assertContains(response, "It is not 0% and not absent.")
        self.assertNotContains(response, "0.0%")
        self.assertContains(response, "Draft")  # still listed

    def test_empty_history_message(self):
        _, enrollment = self.make_student("No Records", section=self.six_b)
        response = self.client.get(reverse("core:student-attendance", args=[enrollment.student_id]))
        self.assertContains(response, "No attendance recorded.")

    def test_inverted_range_discloses_that_the_filter_was_not_applied(self):
        response = self.client.get(self.history, {"start": WED.isoformat(), "end": MON.isoformat()})
        content = response.content.decode()
        self.assertEqual(content.count("Start date must not be after the end date."), 1)
        self.assertEqual(content.count(self.NOT_APPLIED), 2)  # above the Summary and the History
        self.assertIn('id="form-error-summary"', content)
        self.assertIn(f'value="{WED.isoformat()}"', content)  # entered values are kept
        self.assertEqual(len(response.context["entries"]), 3)  # the view still returns everything
        self.assertEqual(response.context["total"], 2)
        self.assertIn("Summary: all recorded attendance", content)
        self.assertIn("Attendance history: all recorded attendance", content)

    def test_garbage_date_associates_the_error_and_discloses(self):
        content = self.client.get(self.history, {"start": "x"}).content.decode()
        self.assertIn("Enter a valid date.", content)
        self.assertDescribedByResolves(content, ["id_start"])
        self.assertEqual(content.count(self.NOT_APPLIED), 2)

    def test_valid_filter_is_labelled_with_its_range_and_is_not_flagged(self):
        response = self.client.get(self.history, {"start": MON.isoformat(), "end": MON.isoformat()})
        content = response.content.decode()
        self.assertIn("Summary: 6 Jul 2026 to 6 Jul 2026", content)
        self.assertNotIn(self.NOT_APPLIED, content)
        self.assertEqual(len(response.context["entries"]), 1)
        self.assertIn("Clear filter", content)
        from_only = self.client.get(self.history, {"start": TUE.isoformat()}).content.decode()
        self.assertIn("Summary: from 7 Jul 2026", from_only)
        to_only = self.client.get(self.history, {"end": TUE.isoformat()}).content.decode()
        self.assertIn("Summary: up to 7 Jul 2026", to_only)

    def test_bound_but_empty_filter_is_just_the_unfiltered_page(self):
        response = self.client.get(self.history, {"start": "", "end": ""})
        content = response.content.decode()
        self.assertEqual(len(response.context["entries"]), 3)
        self.assertNotIn(self.NOT_APPLIED, content)
        self.assertNotIn("Summary:", content)
        self.assertNotIn("form-error-summary", content)

    def headings(self, params=None):
        """The Summary and History H2 texts (whitespace collapsed) and the History note."""
        content = self.client.get(self.history, params or {}).content.decode()

        def text(pattern):
            match = re.search(pattern, content, re.S)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()

        return (
            text(r'id="student-summary-title">(.*?)</h2>'),
            text(r'id="student-history-title">(.*?)</h2>'),
            text(r'(This list shows every recorded entry[^<]*?)\s*Only entries'),
            content,
        )

    def test_summary_and_history_headings_for_every_filter_state(self):
        both = {"start": MON.isoformat(), "end": TUE.isoformat()}
        cases = (
            # (query, summary heading, history heading, history note)
            ({}, "Summary", "Attendance history", "This list shows every recorded entry."),
            ({"start": "", "end": ""}, "Summary", "Attendance history", "This list shows every recorded entry."),
            (
                both,
                "Summary: 6 Jul 2026 to 7 Jul 2026",
                "Attendance history: 6 Jul 2026 to 7 Jul 2026",
                "This list shows every recorded entry in the selected date range.",
            ),
            (
                {"start": TUE.isoformat()},
                "Summary: from 7 Jul 2026",
                "Attendance history: from 7 Jul 2026",
                "This list shows every recorded entry in the selected date range.",
            ),
            (
                {"end": TUE.isoformat()},
                "Summary: up to 7 Jul 2026",
                "Attendance history: up to 7 Jul 2026",
                "This list shows every recorded entry in the selected date range.",
            ),
            (
                {"start": WED.isoformat(), "end": MON.isoformat()},
                "Summary: all recorded attendance",
                "Attendance history: all recorded attendance",
                "This list shows every recorded entry.",
            ),
            (
                {"start": "x"},
                "Summary: all recorded attendance",
                "Attendance history: all recorded attendance",
                "This list shows every recorded entry.",
            ),
        )
        for params, summary, history, note in cases:
            with self.subTest(params=params):
                got_summary, got_history, got_note, content = self.headings(params)
                self.assertEqual(got_summary, summary)
                self.assertEqual(got_history, history)
                self.assertEqual(got_note, note)
                # The counting rule is explained in every state.
                self.assertIn("listed here may not be counted", re.sub(r"\s+", " ", content))
                invalid = "all recorded attendance" in history
                self.assertEqual(content.count(self.NOT_APPLIED), 2 if invalid else 0)

    def test_a_filtered_history_never_claims_to_contain_entries_outside_the_range(self):
        response = self.client.get(self.history, {"start": MON.isoformat(), "end": MON.isoformat()})
        self.assertEqual([e.register.date for e in response.context["entries"]], [MON])
        content = re.sub(r"\s+", " ", response.content.decode())
        self.assertIn("every recorded entry in the selected date range", content)
        self.assertNotIn("This list shows every recorded entry.", content)
        self.assertNotIn("Every recorded attendance entry", content)  # the table caption is neutral too

    def test_toolbar_fields_and_button(self):
        content = self.client.get(self.history).content.decode()
        tag = content.split('aria-label="Filter attendance by date"')[1].split("</form>")[0]
        self.assertEqual(re.findall(r'<(?:select|input)[^>]* name="(\w+)"', tag), ["start", "end"])
        self.assertIn(">Filter history</button>", tag)
        self.assertNotIn('class="erp-required-mark"', tag)  # both dates are optional

    def test_back_to_student_needs_view_student(self):
        detail = reverse("core:student-detail", args=[self.ravi.student_id])
        full = self.client.get(self.history).content.decode()
        self.assertIn(f'href="{detail}"', full)
        self.assertIn(">Back to student</a>", full)
        entry_only = self.client_with(ENTRY).get(self.history).content.decode()
        self.assertNotIn(detail, entry_only)
        self.assertNotIn("Back to student", entry_only)
        self.assertIn(f'href="{reverse("core:attendance-reports")}"', entry_only)
        with_student = self.client_with(ENTRY, STUDENT).get(self.history).content.decode()
        self.assertIn(f'href="{detail}"', with_student)

    def test_permissions_unchanged(self):
        self.assertRedirects(
            self.client_class().get(self.history),
            f"{reverse('login')}?next={self.history}",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client_with(REGISTER).get(self.history).status_code, 403)
        self.assertEqual(self.client_with(ENTRY).get(self.history).status_code, 200)
        self.client.logout()
        self.client.login(username="rao", password="pass-12345")
        self.assertEqual(self.client.get(self.history).status_code, 403)

    def test_page_does_not_write(self):
        before = AttendanceRegister.objects.count()
        self.client.get(self.history, {"start": "x"})
        self.assertEqual(AttendanceRegister.objects.count(), before)
        self.assertEqual(AttendanceStatus.ABSENT.label, "Absent")


# --- phone fit and scoped CSS -----------------------------------------------------------------


class C2LayoutTests(C2Fixture, TestCase):
    def setUp(self):
        self.build_c2()

    def test_monthly_table_fits_the_phone_and_history_scrolls_locally(self):
        self.submitted(MON, present=[self.asha, self.ravi])
        monthly = self.client.get(self.monthly, self.params).content.decode()
        self.assertIn('class="table erp-keep erp-attendance-report-table"', monthly)
        self.assertIn("erp-num", monthly)
        history = self.client.get(self.history).content.decode()
        self.assertIn('<table class="table">', history)  # six columns: scrolls inside its labelled region

    def test_toolbars_carry_the_scoped_modifier(self):
        for url in (self.monthly, self.history):
            content = self.client.get(url).content.decode()
            self.assertIn("erp-toolbar erp-toolbar--inline erp-attendance-report-toolbar", content)

    def test_numeric_css_is_scoped_and_precedes_the_d1_4b_and_d1_3d1_blocks(self):
        from pathlib import Path

        css = Path("static/css/erp.css").read_text(encoding="utf-8")
        start = css.index("/* UI-D1-4C-2")
        self.assertLess(start, css.index("/* UI-D1-4B"))
        self.assertLess(start, css.index("/* UI-D1-3D1 review fix"))
        rule = css[start:css.index("/* UI-D1-4B")].split("*/", 1)[1].strip().splitlines()[0]
        self.assertIn(".erp-attendance-report-table", rule)
