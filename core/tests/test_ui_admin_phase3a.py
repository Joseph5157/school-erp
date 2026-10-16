from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.dashboard import overview_cards
from core.models import Applicant, AttendanceRegister, Student
from core.tests.test_authorization import AttendanceFixtureMixin, AuthorizationClientsMixin


class AttendanceTableTests(AuthorizationClientsMixin, AttendanceFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.build_attendance_fixture()
        start = date(2026, 8, 1)
        for index in range(30):
            AttendanceRegister.objects.create(
                academic_year=self.year, class_grade=self.class_grade,
                section=self.section, date=start + timedelta(days=index),
            )
        self.url = reverse("core:attendance-register-list")

    def dates(self, response):
        return [register.date for register in response.context["registers"]]

    def test_first_page_has_25_rows_newest_first_and_second_page_the_rest(self):
        page1 = self.administrator.get(self.url)
        page2 = self.administrator.get(self.url, {"page": 2})
        self.assertEqual(len(self.dates(page1)), 25)
        self.assertEqual(self.dates(page1), sorted(self.dates(page1), reverse=True))
        self.assertGreater(min(self.dates(page1)), max(self.dates(page2)))

    def test_sort_by_date_ascending(self):
        response = self.administrator.get(self.url, {"sort": "date"})
        dates = self.dates(response)
        self.assertEqual(dates, sorted(dates))

    def test_bad_sort_and_page_values_do_not_error(self):
        for params in ({"sort": "bogus"}, {"page": "abc"}, {"page": "999"}, {"sort": "-"}):
            with self.subTest(params=params):
                self.assertEqual(self.administrator.get(self.url, params).status_code, 200)

    def test_semantics_caption_scope_aria_sort_and_pagination(self):
        response = self.administrator.get(self.url)
        self.assertContains(response, "<caption")
        self.assertContains(response, 'scope="col"')
        self.assertContains(response, 'aria-sort="descending"')
        self.assertContains(response, 'aria-label="Pagination"')
        self.assertContains(response, "Showing 1–25 of")

    def test_filters_are_carried_into_pagination_links(self):
        response = self.administrator.get(self.url, {"section": self.section.pk})
        self.assertContains(response, f"section={self.section.pk}")
        self.assertContains(response, "page=2")

    def test_section_summary_covers_whole_filtered_set_not_one_page(self):
        params = {"section": self.section.pk}
        first = self.administrator.get(self.url, params)
        second = self.administrator.get(self.url, {**params, "page": 2})
        self.assertIsNotNone(first.context["section_summary"])
        self.assertEqual(first.context["section_summary"], second.context["section_summary"])
        self.assertEqual(first.context["section_total"], second.context["section_total"])

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)


def make_students(count):
    students = []
    for index in range(count):
        applicant = Applicant.objects.create(full_name=f"Student {index:02d}")
        applicant.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        students.append(applicant.progress_to_student())
    return students


class StudentTableTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.students = make_students(30)
        self.url = reverse("core:student-list")

    def names(self, response):
        return [student.full_name for student in response.context["students"]]

    def test_pagination_25_then_remainder_sorted_by_name(self):
        page1 = self.administrator.get(self.url)
        page2 = self.administrator.get(self.url, {"page": 2})
        self.assertEqual(len(self.names(page1)), 25)
        self.assertEqual(len(self.names(page2)), 5)
        self.assertEqual(self.names(page1)[0], "Student 00")
        self.assertContains(page1, "Showing 1–25 of 30")

    def test_sort_descending_by_name(self):
        response = self.administrator.get(self.url, {"sort": "-name"})
        self.assertEqual(self.names(response)[0], "Student 29")
        self.assertContains(response, 'aria-sort="descending"')

    def test_status_filter(self):
        Student.objects.filter(pk=self.students[0].pk).update(status=Student.Status.INACTIVE)
        response = self.administrator.get(self.url, {"status": "INACTIVE"})
        self.assertEqual(self.names(response), ["Student 00"])
        self.assertContains(response, "Showing 1–1 of 1")

    def test_invalid_status_is_ignored(self):
        response = self.administrator.get(self.url, {"status": "BOGUS"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.names(response)), 25)

    def test_search_and_status_survive_pagination_links(self):
        response = self.administrator.get(self.url, {"q": "Student", "status": "ACTIVE"})
        self.assertContains(response, "q=Student")
        self.assertContains(response, "status=ACTIVE")
        self.assertContains(response, "page=2")

    def test_filter_with_no_matches_offers_clear_filters(self):
        response = self.administrator.get(self.url, {"q": "zzz-no-match"})
        self.assertContains(response, "No Students found.")
        self.assertContains(response, "No results")
        self.assertContains(response, "Clear filters")

    def test_search_label_and_clear_search_from_phase0_remain(self):
        response = self.administrator.get(self.url, {"q": "Student"})
        self.assertContains(response, 'for="student-search"')
        self.assertContains(response, "Clear search")

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)


class ApplicantTableTests(AuthorizationClientsMixin, TestCase):
    def setUp(self):
        super().setUp()
        for index in range(30):
            Applicant.objects.create(full_name=f"Applicant {index:02d}")
        accepted = Applicant.objects.get(full_name="Applicant 00")
        accepted.record_admission_decision(Applicant.AdmissionStatus.ACCEPTED)
        self.url = reverse("core:applicant-list")

    def names(self, response):
        return [applicant.full_name for applicant in response.context["applicants"]]

    def test_pagination_and_default_name_sort(self):
        page1 = self.administrator.get(self.url)
        self.assertEqual(len(self.names(page1)), 25)
        self.assertEqual(self.names(page1)[0], "Applicant 00")
        self.assertContains(page1, "Showing 1–25 of 30")
        self.assertContains(page1, "<caption")
        self.assertContains(page1, 'scope="col"')

    def test_sort_by_admission_status_descending_puts_pending_first(self):
        response = self.administrator.get(self.url, {"sort": "-status"})
        first = response.context["applicants"][0]
        self.assertEqual(first.admission_status, Applicant.AdmissionStatus.PENDING)
        self.assertNotIn("Applicant 00", self.names(response))  # the one ACCEPTED row is last
        self.assertContains(response, 'aria-sort="descending"')

    def test_status_filter_pending_excludes_decided(self):
        response = self.administrator.get(self.url, {"status": "PENDING"})
        self.assertNotIn("Applicant 00", self.names(response))
        self.assertContains(response, "Showing 1–25 of 29")

    def test_invalid_status_and_page_ignored(self):
        response = self.administrator.get(self.url, {"status": "BOGUS", "page": "999"})
        self.assertEqual(response.status_code, 200)

    def test_empty_filter_result_keeps_empty_row_and_clear_link(self):
        response = self.administrator.get(self.url, {"status": "REJECTED"})
        self.assertContains(response, "No Applicants yet.")
        self.assertContains(response, "Clear filters")

    def test_non_admin_still_forbidden(self):
        self.assertEqual(self.non_admin.get(self.url).status_code, 403)

    def test_overview_card_links_to_pending_filter(self):
        card = next(c for c in overview_cards(self.admin_user) if c["key"] == "applicants")
        self.assertEqual(card["url"], reverse("core:applicant-list") + "?status=PENDING")
        self.assertEqual(card["count"], 29)
