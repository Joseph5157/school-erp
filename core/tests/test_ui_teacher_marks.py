"""U3 teacher marks and students: marks entry, gradebook, My students."""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.forms import ResultEntryForm
from core.models import AttendanceRegister, SectionClassTeacher
from core.tests.phase4_fixtures import Phase4Fixture

MONDAY = date(2026, 10, 12)


class MarksFixture(Phase4Fixture):
    def setUp(self):
        self.build_phase4()
        for patch in (mock.patch("core.views.business_today", new=lambda: MONDAY),
                      mock.patch("core.models.business_today", new=lambda: MONDAY)):
            patch.start()
            self.addCleanup(patch.stop)
        _, self.asha = self.make_student("Asha")
        _, self.bina = self.make_student("Bina")
        _, self.ravi = self.make_student("Ravi")
        self.duty = self.assign(self.rao, self.maths, self.six_a)
        self.test1 = self.make_assessment(name="Unit Test 1", on=date(2026, 7, 15))
        self.test2 = self.make_assessment(name="Unit Test 2", on=date(2026, 7, 22))
        self.teacher = self.client_class()
        self.teacher.login(username="rao", password="pass-12345")

    def entry_url(self, assessment):
        return reverse("core:assessment-marks-entry", args=[assessment.pk])

    def result(self, assessment, enrollment, status, score=None):
        assessment.save_draft_result(
            enrollment=enrollment, status=status,
            score=Decimal(score) if score is not None else None, actor=self.rao,
        )


class ResultFormTests(MarksFixture, TestCase):
    def test_counts_use_saved_results(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        form = ResultEntryForm(assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_counts_use_bound_data(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "12",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": "",
                f"status_{self.ravi.pk}": "", f"score_{self.ravi.pk}": ""}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts(), {"all": 3, "marked": 1, "absent": 1, "unmarked": 1})

    def test_zero_score_counts_as_marked(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0"}
        form = ResultEntryForm(data, assessment=self.test1)
        self.assertEqual(form.counts()["marked"], 1)

    def test_status_is_three_radios_and_score_has_keypad_hints(self):
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value=""')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="MARKED"')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="ABSENT"')
        self.assertContains(page, 'inputmode="decimal"')
        self.assertContains(page, 'enterkeyhint="next"')

    def test_saved_row_offers_no_not_entered_radio(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertNotContains(page, f'type="radio" name="status_{self.asha.pk}" value=""')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="MARKED"')
        self.assertContains(page, f'type="radio" name="status_{self.asha.pk}" value="ABSENT"')
        self.assertContains(page, f'type="radio" name="status_{self.bina.pk}" value=""')


class MarksEntryPageTests(MarksFixture, TestCase):
    def test_rows_are_fieldsets_with_static_counts(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, '<legend class="visually-hidden">Asha</legend>')
        self.assertEqual(page.content.decode().count("<fieldset"), 3)
        self.assertContains(page, "All 3 · Not entered 2 · Marked 1 · Absent 0")
        self.assertContains(page, "2 not entered")
        self.assertContains(page, "data-erp-marks")
        self.assertContains(page, "blank is <strong>not</strong> absent")

    def test_invalid_post_keeps_typed_values(self):
        data = {f"status_{self.asha.pk}": "ABSENT", f"score_{self.asha.pk}": "5",
                f"status_{self.bina.pk}": "", f"score_{self.bina.pk}": "11"}
        page = self.teacher.post(self.entry_url(self.test1), data)
        self.assertContains(page, "An absent Student has no score.")
        self.assertContains(page, 'value="11"')
        self.assertContains(page, "All 3 · Not entered 1 · Marked 1 · Absent 1")

    def test_invalid_post_highlights_only_the_bad_row(self):
        data = {f"status_{self.asha.pk}": "ABSENT", f"score_{self.asha.pk}": "5"}
        page = self.teacher.post(self.entry_url(self.test1), data)
        html = page.content.decode()
        self.assertEqual(html.count("is-invalid"), 1)
        self.assertContains(page, "Marks were not saved. Fix the highlighted rows.")
        self.assertRegex(html, r'<fieldset class="erp-roster-row is-invalid"')

    def test_saving_still_works(self):
        data = {f"status_{self.asha.pk}": "", f"score_{self.asha.pk}": "0",
                f"status_{self.bina.pk}": "ABSENT", f"score_{self.bina.pk}": ""}
        response = self.teacher.post(self.entry_url(self.test1), data, follow=True)
        self.assertContains(response, "Marks saved as draft.")
        results = {r.academic_enrollment_id: (r.status, r.score)
                   for r in self.test1.results.all()}
        self.assertEqual(results[self.asha.pk], ("MARKED", Decimal("0")))
        self.assertEqual(results[self.bina.pk][0], "ABSENT")
        self.assertNotIn(self.ravi.pk, results)

    def test_finalized_shows_cards_with_not_entered(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        self.force_finalize(self.test1)
        page = self.teacher.get(self.entry_url(self.test1))
        self.assertContains(page, "This assessment is finalized")
        self.assertContains(page, "18 / 20")
        self.assertContains(page, "Not entered")
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>')
        self.assertNotContains(page, "<table")


class GradebookTests(MarksFixture, TestCase):
    def url(self, duty=None):
        return reverse("core:my-gradebook", args=[(duty or self.duty).pk])

    def test_cells_show_score_abs_or_empty(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test1, self.bina, "ABSENT")
        page = self.teacher.get(self.url())
        rows = {row["student"].full_name: row["cells"] for row in page.context["rows"]}
        self.assertEqual(rows["Asha"][0].score, Decimal("18"))
        self.assertEqual(rows["Bina"][0].status, "ABSENT")
        self.assertIsNone(rows["Ravi"][0])
        self.assertIsNone(rows["Asha"][1])
        self.assertContains(page, ">Abs<")

    def test_zero_score_shows_zero(self):
        self.result(self.test1, self.asha, "MARKED", "0")
        self.assertContains(self.teacher.get(self.url()), ">0<")

    def test_no_totals_or_ranks(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        page = self.teacher.get(self.url())
        for word in ("Total", "Average", "Rank"):
            self.assertNotContains(page, word)

    def test_students_by_name_and_headers_link_to_entry(self):
        page = self.teacher.get(self.url())
        self.assertEqual([r["student"].full_name for r in page.context["rows"]],
                         ["Asha", "Bina", "Ravi"])
        self.assertContains(page, self.entry_url(self.test1))
        self.assertContains(page, self.entry_url(self.test2))

    def test_draft_and_finalized_columns_differ(self):
        self.result(self.test1, self.asha, "MARKED", "18")
        self.result(self.test2, self.asha, "MARKED", "15")
        self.force_finalize(self.test2)
        page = self.teacher.get(self.url()).content.decode()
        self.assertEqual(page.count('class="is-draft"'), 1)
        self.assertEqual(page.count("(draft)"), 1)

    def test_rows_union_of_rosters(self):
        later = self.make_assessment(name="Unit Test 3", on=date(2026, 9, 10))
        _, kiran = self.make_student("Kiran", start=date(2026, 8, 1))
        page = self.teacher.get(self.url())
        cells = {r["student"].full_name: r["cells"] for r in page.context["rows"]}
        self.assertEqual(len(cells["Kiran"]), 3)
        self.assertIsNone(cells["Kiran"][0])
        self.assertTrue(later.roster().filter(pk=kiran.pk).exists())

    def test_other_teachers_assignment_is_404(self):
        other = self.assign(self.iyer, self.sanskrit, self.six_b)
        self.assertEqual(self.teacher.get(self.url(other)).status_code, 404)

    def test_non_teacher_is_forbidden(self):
        self.client.login(username="admin", password="pass-12345")
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_my_assessments_links_gradebook(self):
        page = self.teacher.get(reverse("core:my-assessments"))
        self.assertContains(page, "My assessments")
        self.assertContains(page, self.url())
        self.assertContains(page, "Unit Test 1")


class MyStudentsTests(MarksFixture, TestCase):
    def setUp(self):
        super().setUp()
        SectionClassTeacher.assign(teacher=self.rao, academic_year=self.year,
                                   section=self.six_a, start_date=date(2026, 6, 1))
        self.url = reverse("core:my-students")

    def register(self, submit):
        register = AttendanceRegister.objects.create(
            academic_year=self.year, class_grade=self.grade6, section=self.six_a, date=MONDAY
        )
        register.save_draft_entry(enrollment=self.asha, status="PRESENT")
        register.save_draft_entry(enrollment=self.bina, status="ABSENT")
        register.save_draft_entry(enrollment=self.ravi, status="PRESENT")
        if submit:
            register.submit(actor=self.rao)
        return register

    def test_submitted_register_shows_chips(self):
        self.register(submit=True)
        page = self.teacher.get(self.url)
        self.assertContains(page, '<span class="erp-pill is-present">Present</span>', count=2)
        self.assertContains(page, '<span class="erp-pill is-absent">Absent</span>', count=1)
        self.assertNotContains(page, "not submitted yet")

    def test_draft_register_shows_no_chips(self):
        self.register(submit=False)
        page = self.teacher.get(self.url)
        self.assertNotContains(page, "erp-pill is-present")
        self.assertNotContains(page, "erp-pill is-absent")
        self.assertContains(page, "Today's attendance not submitted yet")

    def test_subject_only_section_has_no_chips_or_note(self):
        self.make_student("Kiran", section=self.six_b)
        self.assign(self.rao, self.sanskrit, self.six_b)
        self.register(submit=True)
        page = self.teacher.get(self.url).content.decode()
        six_b_part = page[page.index(str(self.six_b)):]
        self.assertNotIn("erp-pill is-present", six_b_part)
        self.assertNotIn("not submitted yet", six_b_part)

    def test_rows_have_initials_and_links(self):
        page = self.teacher.get(self.url)
        self.assertContains(page, 'class="erp-initials"')
        self.assertContains(page, reverse("core:my-student-detail", args=[self.asha.student.pk]))
