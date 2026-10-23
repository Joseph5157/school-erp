"""UI-D1-4A: the administrator Attendance Register List is presentation-only.

Filters, sorting, 25-row pagination, permissions and reportable-attendance counts are
unchanged; these tests pin the toolbar/panel structure, the empty and invalid-filter
states, and that Draft or unmarked attendance is never counted as Absent.
"""

import re
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AttendanceEntry, AttendanceRegister, AttendanceStatus
from core.tests.phase4_fixtures import Phase4Fixture

User = get_user_model()


class AttendanceListFixture(Phase4Fixture):
    def build(self):
        self.build_phase4()
        self.url = reverse("core:attendance-register-list")
        self.client.login(username="admin", password="pass-12345")
        _, self.asha = self.make_student("Asha")
        _, self.ravi = self.make_student("Ravi")
        _, self.meena = self.make_student("Meena", section=self.six_b)

    def register(self, on_date, section=None, *, submitted=False, absent=(), present=()):
        section = section or self.six_a
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=section, date=on_date
        )
        for enrollment in present:
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.PRESENT)
        for enrollment in absent:
            register.save_draft_entry(enrollment=enrollment, status=AttendanceStatus.ABSENT)
        if submitted:
            AttendanceRegister.objects.filter(pk=register.pk).update(
                status="SUBMITTED", submitted_by=self.admin,
                submitted_at=timezone.make_aware(datetime(2026, 1, 1)),
            )
            register.refresh_from_db()
        return register

    def viewer(self, *codenames):
        user = User.objects.create_user(username="viewer-" + "-".join(codenames), password="pass-12345")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        client = self.client_class()
        client.login(username=user.username, password="pass-12345")
        return client


class StructureTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()
        self.register(date(2026, 7, 6), submitted=True, present=[self.asha], absent=[self.ravi])

    def test_one_h1_and_a_labelled_three_field_get_toolbar(self):
        content = self.client.get(self.url).content.decode()
        self.assertEqual(content.count("<h1"), 1)
        form = content.split('aria-label="Filter attendance registers"')[0].rsplit("<form", 1)[1]
        self.assertIn('method="get"', form)
        self.assertIn("erp-toolbar", form)
        tag = content.split('aria-label="Filter attendance registers"')[1].split("</form>")[0]
        self.assertEqual(re.findall(r"<label[^>]*>([^<]+):</label>", tag), ["Section", "Start", "End"])
        self.assertEqual(re.findall(r'<(?:select|input)[^>]* name="(section|start|end)"', tag),
                         ["section", "start", "end"])
        self.assertEqual(tag.count('type="date"'), 2)
        self.assertIn(">Filter</button>", tag)

    def test_table_panel_keeps_scroll_region_columns_and_status_label(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn('<div class="erp-panel">\n<div class="erp-table-scroll" role="region" '
                      'aria-label="Attendance registers" tabindex="0">', content)
        headers = re.findall(r'<th scope="col"[^>]*>\s*(?:<a [^>]*>)?([^<\s][^<]*?)(?:</a>)?\s*</th>',
                             content.split('aria-label="Attendance registers"')[1])
        self.assertEqual(headers, ["Date", "Academic year", "Class/Grade", "Section", "Status", "Entries"])
        self.assertContains(response, "Submitted")

    def test_no_summary_without_a_selected_section(self):
        response = self.client.get(self.url)
        self.assertIsNone(response.context["section_summary"])
        self.assertNotContains(response, "Section summary")

    def test_clear_filters_link_only_when_a_filter_was_supplied(self):
        self.assertNotContains(self.client.get(self.url), "Clear filters")
        self.assertContains(self.client.get(self.url, {"section": self.six_a.pk}), "Clear filters")
        self.assertContains(self.client.get(self.url, {"start": "2026-07-01"}), "Clear filters")

    def test_filter_form_does_not_carry_page_but_keeps_sort(self):
        content = self.client.get(self.url, {"sort": "section", "page": 1}).content.decode()
        tag = content.split('aria-label="Filter attendance registers"')[1].split("</form>")[0]
        self.assertIn('<input type="hidden" name="sort" value="section">', tag)
        self.assertNotIn('name="page"', tag)


class PermissionTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()

    def test_anonymous_redirects_and_non_admin_is_forbidden(self):
        self.assertRedirects(self.client_class().get(self.url),
                             f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)
        self.client.logout()
        self.client.login(username="rao", password="pass-12345")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_header_and_empty_state_actions_follow_their_own_permissions(self):
        create = reverse("core:attendance-register-create")
        reports = reverse("core:attendance-reports")
        full = self.client.get(self.url).content.decode()
        self.assertIn(f'href="{create}"', full)
        self.assertIn(f'href="{reports}"', full)

        view_only = self.viewer("view_attendanceregister").get(self.url)
        self.assertEqual(view_only.status_code, 200)
        self.assertNotContains(view_only, f'href="{create}"')
        self.assertNotContains(view_only, f'href="{reports}"')
        self.assertContains(view_only, "No attendance registers yet.")

        reports_only = self.viewer("view_attendanceregister", "view_attendanceentry").get(self.url)
        self.assertContains(reports_only, f'href="{reports}"')
        self.assertNotContains(reports_only, f'href="{create}"')

    def test_page_is_read_only(self):
        self.register(date(2026, 7, 6), present=[self.asha])
        before = (AttendanceRegister.objects.count(), AttendanceEntry.objects.count())
        self.client.get(self.url, {"section": self.six_a.pk, "start": "2026-08-01", "end": "2026-07-01"})
        self.assertEqual((AttendanceRegister.objects.count(), AttendanceEntry.objects.count()), before)


class SummarySemanticsTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()
        self.submitted = self.register(date(2026, 7, 6), submitted=True,
                                       present=[self.asha], absent=[self.ravi])
        # A Draft with a saved Absent mark and a Draft with no marks at all.
        self.draft = self.register(date(2026, 7, 7), absent=[self.ravi])
        self.empty_draft = self.register(date(2026, 7, 8))
        self.other = self.register(date(2026, 7, 6), self.six_b, submitted=True, absent=[self.meena])

    def summary(self, response):
        return {row["label"]: row["count"] for row in response.context["section_summary"]}

    def test_only_reportable_submitted_entries_count_and_drafts_are_never_absent(self):
        response = self.client.get(self.url, {"section": self.six_a.pk})
        self.assertEqual(self.summary(response), {"Present": 1, "Absent": 1})
        self.assertEqual(response.context["section_total"], 2)
        content = response.content.decode()
        panel = content.split('aria-labelledby="attendance-summary-title"')[1].split("</section>")[0]
        self.assertIn("Reportable submitted attendance only.", panel)
        self.assertEqual(re.findall(r'<th scope="row">([^<]+)</th><td>(\d+)</td>', panel),
                         [("Present", "1"), ("Absent", "1"), ("Total", "2")])

    def test_entries_column_is_the_raw_saved_count_including_drafts(self):
        by_date = {r.date: r for r in self.client.get(
            self.url, {"section": self.six_a.pk}).context["registers"]}
        self.assertEqual(by_date[date(2026, 7, 6)].entry_count, 2)
        self.assertEqual(by_date[date(2026, 7, 7)].entry_count, 1)
        self.assertEqual(by_date[date(2026, 7, 8)].entry_count, 0)
        content = self.client.get(self.url, {"section": self.six_a.pk}).content.decode()
        statuses = re.findall(r'</span>(Draft|Submitted)</span>', content)
        self.assertEqual(sorted(statuses), ["Draft", "Draft", "Submitted"])

    def test_summary_follows_the_date_window_and_not_the_visible_page(self):
        response = self.client.get(self.url, {"section": self.six_a.pk, "start": "2026-07-07"})
        self.assertEqual(self.summary(response), {"Present": 0, "Absent": 0})
        both = self.client.get(
            self.url, {"section": self.six_a.pk, "start": "2026-07-06", "end": "2026-07-06"})
        self.assertEqual(self.summary(both), {"Present": 1, "Absent": 1})
        self.assertEqual(len(both.context["registers"]), 1)


class FilterStateTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()

    def test_no_registers_at_all_shows_the_first_register_empty_state(self):
        response = self.client.get(self.url)
        self.assertContains(response, "No attendance registers yet.")
        self.assertContains(response, reverse("core:attendance-register-create"))
        self.assertNotContains(response, "match these filters")

    def test_valid_filter_with_no_matches_does_not_claim_there_are_none_at_all(self):
        self.register(date(2026, 7, 6), self.six_a)
        response = self.client.get(self.url, {"section": self.six_b.pk})
        self.assertContains(response, "No attendance registers match these filters.")
        self.assertNotContains(response, "No attendance registers yet.")
        self.assertContains(response, "No results")
        self.assertEqual(response.content.decode().count("Clear filters"), 2)  # toolbar + footer

    def test_section_with_no_registers_summarises_zero(self):
        response = self.client.get(self.url, {"section": self.six_b.pk})
        self.assertEqual(response.context["section_total"], 0)
        self.assertContains(response, "Section summary")

    def test_inverted_range_shows_the_error_once_and_all_registers_unfiltered(self):
        self.register(date(2026, 7, 6))
        self.register(date(2026, 9, 1), self.six_b)
        params = {"section": self.six_b.pk, "start": "2026-09-30", "end": "2026-07-01"}
        response = self.client.get(self.url, params)
        content = response.content.decode()
        self.assertEqual(content.count("Start date must not be after the end date."), 1)
        self.assertEqual(content.count("Filters were not applied; showing all registers."), 1)
        self.assertEqual(len(response.context["registers"]), 2)
        self.assertIsNone(response.context["section_summary"])
        self.assertIn('value="2026-09-30"', content)
        self.assertIn('value="2026-07-01"', content)
        self.assertNotContains(response, "match these filters")

    def test_invalid_date_reports_a_field_error_beside_its_input(self):
        content = self.client.get(self.url, {"start": "not-a-date"}).content.decode()
        self.assertEqual(content.count('class="erp-field-errors"'), 1)
        self.assertIn("Enter a valid date.", content)

    def test_invalid_filter_with_no_registers_is_not_reported_as_no_match(self):
        response = self.client.get(self.url, {"start": "not-a-date"})
        self.assertContains(response, "No attendance registers yet.")
        self.assertNotContains(response, "match these filters")


class PaginationAndSortTests(AttendanceListFixture, TestCase):
    def setUp(self):
        self.build()
        for index in range(30):
            self.register(date(2026, 8, 1) + timedelta(days=index))

    def test_25_per_page_newest_first_and_page_two_keeps_filters_and_sort(self):
        first = self.client.get(self.url, {"section": self.six_a.pk})
        dates = [r.date for r in first.context["registers"]]
        self.assertEqual(len(dates), 25)
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertContains(first, "Showing 1–25 of 30")
        self.assertContains(first, 'aria-sort="descending"')
        link = re.search(r'<a href="([^"]*page=2[^"]*)"', first.content.decode()).group(1)
        self.assertIn(f"section={self.six_a.pk}", link)
        self.assertIn("sort=-date", link)
        second = self.client.get(self.url + link.replace("&amp;", "&"))
        self.assertEqual(len(second.context["registers"]), 5)
        self.assertContains(second, "Showing 26–30 of 30")

    def test_sort_links_and_bad_inputs_still_work(self):
        asc = self.client.get(self.url, {"sort": "date"})
        dates = [r.date for r in asc.context["registers"]]
        self.assertEqual(dates, sorted(dates))
        self.assertContains(asc, 'aria-sort="ascending"')
        for params in ({"sort": "bogus"}, {"page": "abc"}, {"page": "999"}):
            self.assertEqual(self.client.get(self.url, params).status_code, 200)
